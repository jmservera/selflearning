"""Service Bus consumer for the Knowledge Service.

Subscribes to the `extraction-complete` topic and processes knowledge units
into the graph (Cosmos DB) and search index (AI Search).
"""

from __future__ import annotations

import asyncio
import json
import logging

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus.aio import ServiceBusClient, ServiceBusReceiver
from azure.servicebus import ServiceBusReceivedMessage
from opentelemetry import trace

from .config import ServiceBusConfig
from .cosmos_client import KnowledgeStore
from .models import KnowledgeUnit
from .search_client import KnowledgeSearchClient

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class KnowledgeServiceBusConsumer:
    """Listens on the extraction-complete subscription and ingests knowledge."""

    def __init__(
        self,
        config: ServiceBusConfig,
        store: KnowledgeStore,
        search: KnowledgeSearchClient,
    ) -> None:
        self._config = config
        self._store = store
        self._search = search
        self._credential: DefaultAzureCredential | None = None
        self._client: ServiceBusClient | None = None
        self._receiver: ServiceBusReceiver | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Open Service Bus connection and start consuming messages."""
        self._credential = DefaultAzureCredential()
        fqns = f"{self._config.namespace}.servicebus.windows.net"
        self._client = ServiceBusClient(
            fully_qualified_namespace=fqns,
            credential=self._credential,
        )
        self._receiver = self._client.get_subscription_receiver(
            topic_name=self._config.extraction_complete_topic,
            subscription_name=self._config.subscription_name,
            prefetch_count=self._config.prefetch_count,
        )
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info(
            "Service Bus consumer started: %s/%s",
            self._config.extraction_complete_topic,
            self._config.subscription_name,
        )

    async def stop(self) -> None:
        """Gracefully stop the consumer."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._receiver:
            await self._receiver.close()
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()
        logger.info("Service Bus consumer stopped")

    # ── Message processing loop ────────────────────────────────────────

    async def _consume_loop(self) -> None:
        """Continuously receive and process messages."""
        assert self._receiver is not None
        while self._running:
            try:
                messages = await self._receiver.receive_messages(
                    max_message_count=self._config.max_concurrent_calls,
                    max_wait_time=5,
                )
                tasks = [self._handle_message(msg) for msg in messages]
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in Service Bus consume loop; will retry")
                await asyncio.sleep(5)

    async def _handle_message(self, message: ServiceBusReceivedMessage) -> None:
        """Process a single extraction-complete message."""
        assert self._receiver is not None
        with tracer.start_as_current_span("servicebus.handle_extraction_complete") as span:
            msg_id = message.message_id or "unknown"
            span.set_attribute("message.id", str(msg_id))
            try:
                body = json.loads(str(message))
                unit = KnowledgeUnit.model_validate(body)

                # Ingest into Cosmos DB
                result = await self._store.bulk_ingest(unit)
                logger.info(
                    "Ingested message %s: %d entities, %d rels, %d claims",
                    msg_id,
                    result.entities_upserted,
                    result.relationships_upserted,
                    result.claims_upserted,
                )

                # Index into AI Search
                await self._reindex_from_unit(unit)

                await self._receiver.complete_message(message)
                span.set_attribute("processing.success", True)

            except Exception as exc:
                logger.exception("Failed to process message %s: %s", msg_id, exc)
                span.set_attribute("processing.success", False)
                span.record_exception(exc)
                try:
                    await self._receiver.abandon_message(message)
                except Exception:
                    logger.exception("Failed to abandon message %s", msg_id)

    async def _reindex_from_unit(self, unit: KnowledgeUnit) -> None:
        """Push entities and claims from the ingested unit to AI Search."""
        docs: list[dict] = []
        topics_seen: set[str] = set()

        for entity in unit.entities:
            docs.append(entity.model_dump(mode="json"))
            topics_seen.add(entity.topic)
        for claim in unit.claims:
            docs.append(claim.model_dump(mode="json"))
            topics_seen.add(claim.topic)

        # Ensure indexes exist for all topics
        for topic in topics_seen:
            try:
                await self._search.ensure_index(topic)
            except Exception:
                logger.exception("Failed to ensure index for topic %s", topic)

        if docs:
            # Group by topic for correct index routing
            by_topic: dict[str, list[dict]] = {}
            for d in docs:
                t = d.get("topic", "global")
                by_topic.setdefault(t, []).append(d)
            for topic, topic_docs in by_topic.items():
                try:
                    await self._search.index_documents(topic_docs, topic=topic)
                except Exception:
                    logger.exception("Failed to index documents for topic %s", topic)
