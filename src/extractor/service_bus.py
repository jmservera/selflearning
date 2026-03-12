"""Azure Service Bus integration for the Extractor service.

Subscribes to ``scrape-complete`` topic and publishes to ``extraction-complete``.
Uses DefaultAzureCredential — no connection strings.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient
from opentelemetry import trace

from config import ExtractorConfig

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("extractor.servicebus")

MessageHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ServiceBusHandler:
    """Consume scrape-complete messages and publish extraction results."""

    def __init__(self, config: ExtractorConfig) -> None:
        self._config = config
        self._credential: DefaultAzureCredential | None = None
        self._client: ServiceBusClient | None = None
        self._running = False

    async def initialize(self) -> None:
        """Open the Service Bus connection."""
        fqns = f"{self._config.servicebus_namespace}.servicebus.windows.net"
        self._credential = DefaultAzureCredential()
        self._client = ServiceBusClient(
            fully_qualified_namespace=fqns,
            credential=self._credential,
        )
        logger.info("Service Bus client ready (%s)", fqns)

    async def close(self) -> None:
        """Stop the consume loop and release resources."""
        self._running = False
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish_extraction_result(self, result: dict[str, Any]) -> None:
        """Publish a completed extraction result to the extraction-complete topic."""
        with tracer.start_as_current_span("servicebus.publish") as span:
            topic = self._config.extraction_complete_topic
            request_id = result.get("request_id", "")
            span.set_attribute("servicebus.topic", topic)
            span.set_attribute("servicebus.request_id", request_id)

            assert self._client is not None, "ServiceBusHandler not initialized"
            sender = self._client.get_topic_sender(topic_name=topic)
            async with sender:
                body = json.dumps(result, default=str)
                message = ServiceBusMessage(
                    body=body,
                    content_type="application/json",
                    subject=request_id,
                )
                await sender.send_messages(message)

            logger.info(
                "Published extraction result request_id=%s to %s",
                request_id, topic,
            )

    # ------------------------------------------------------------------
    # Consuming
    # ------------------------------------------------------------------

    async def consume_loop(self, handler: MessageHandler) -> None:
        """Continuously receive and process messages from scrape-complete.

        For each message the *handler* is called with the parsed JSON body.
        The handler must return a dict (the extraction result) which is then
        published to the extraction-complete topic.  On handler failure the
        message is abandoned (returned to the queue for retry / DLQ).

        Args:
            handler: ``async (body: dict) -> dict`` — extraction pipeline.
        """
        assert self._client is not None, "ServiceBusHandler not initialized"
        self._running = True

        topic = self._config.scrape_complete_topic
        sub = self._config.scrape_complete_subscription

        logger.info("Starting consume loop on %s/%s", topic, sub)

        receiver = self._client.get_subscription_receiver(
            topic_name=topic,
            subscription_name=sub,
            max_wait_time=30,
        )

        async with receiver:
            while self._running:
                try:
                    messages = await receiver.receive_messages(
                        max_message_count=1,
                        max_wait_time=30,
                    )
                    for msg in messages:
                        await self._process_message(receiver, msg, handler)

                except asyncio.CancelledError:
                    logger.info("Consume loop cancelled, shutting down")
                    break
                except Exception:
                    logger.exception("Unhandled error in consume loop — retrying in 5 s")
                    await asyncio.sleep(5)

        logger.info("Consume loop stopped")

    async def _process_message(
        self,
        receiver: Any,
        msg: Any,
        handler: MessageHandler,
    ) -> None:
        """Deserialize, handle, and settle a single message."""
        with tracer.start_as_current_span("servicebus.process") as span:
            try:
                body = json.loads(str(msg))
                request_id = body.get("request_id", "unknown")
                span.set_attribute("servicebus.request_id", request_id)

                logger.info("Processing message request_id=%s", request_id)
                result = await handler(body)

                await self.publish_extraction_result(result)
                await receiver.complete_message(msg)

                logger.info("Completed message request_id=%s", request_id)
            except Exception:
                logger.exception("Failed to process message — abandoning")
                try:
                    await receiver.abandon_message(msg)
                except Exception:
                    logger.exception("Failed to abandon message")
