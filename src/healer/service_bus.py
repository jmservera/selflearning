"""Service Bus client for the Healer.

Monitors dead-letter queues across all Service Bus queues and topic subscriptions.
Publishes healing-events to a dedicated topic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient, ServiceBusSender
from azure.servicebus.management.aio import ServiceBusAdministrationClient
from opentelemetry import trace

from config import HealerSettings
from models import DLQMessage, DLQStats, HealingEvent

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class HealerServiceBus:
    """Manages Service Bus interactions for the Healer.

    Responsibilities:
      - Read messages from dead-letter queues (DLQs)
      - Replay messages from DLQs back to their original queues
      - Publish healing-events to the healing-events topic
      - Collect DLQ statistics across all monitored queues/topics
    """

    def __init__(self, settings: HealerSettings) -> None:
        self._settings = settings
        self._credential: DefaultAzureCredential | None = None
        self._client: ServiceBusClient | None = None
        self._admin_client: ServiceBusAdministrationClient | None = None
        self._healing_sender: ServiceBusSender | None = None

    async def initialize(self) -> None:
        """Open the Service Bus connection."""
        with tracer.start_as_current_span("healer.servicebus.initialize"):
            self._credential = DefaultAzureCredential()
            self._client = ServiceBusClient(
                fully_qualified_namespace=self._settings.servicebus_namespace,
                credential=self._credential,
            )
            self._admin_client = ServiceBusAdministrationClient(
                fully_qualified_namespace=self._settings.servicebus_namespace,
                credential=self._credential,
            )
            self._healing_sender = self._client.get_topic_sender(
                topic_name=self._settings.healing_events_topic
            )
            logger.info(
                "Healer Service Bus initialized — namespace=%s",
                self._settings.servicebus_namespace,
            )

    # ── DLQ reading ───────────────────────────────────────────────────

    async def read_dlq_messages(
        self, queue_name: str, max_count: int | None = None
    ) -> list[DLQMessage]:
        """Read messages from a queue's dead-letter sub-queue.

        Messages are peeked (not consumed) to allow analysis before replay/discard.
        """
        with tracer.start_as_current_span("healer.servicebus.read_dlq") as span:
            span.set_attribute("queue", queue_name)
            max_count = max_count or self._settings.dlq_batch_size
            assert self._client is not None

            receiver = self._client.get_queue_receiver(
                queue_name=queue_name,
                sub_queue="deadletter",
                max_wait_time=5,
            )
            messages: list[DLQMessage] = []
            try:
                async with receiver:
                    batch = await receiver.receive_messages(
                        max_message_count=max_count, max_wait_time=5
                    )
                    for msg in batch:
                        try:
                            body = json.loads(str(msg))
                        except (json.JSONDecodeError, TypeError):
                            body = {"raw": str(msg)}

                        dlq_msg = DLQMessage(
                            message_id=msg.message_id or "",
                            queue_or_topic=queue_name,
                            body=body,
                            dead_letter_reason=msg.dead_letter_reason,
                            dead_letter_description=msg.dead_letter_error_description,
                            enqueued_time=msg.enqueued_time_utc,
                            delivery_count=msg.delivery_count or 0,
                            metadata=dict(msg.application_properties or {}),
                        )
                        messages.append(dlq_msg)
                        # Complete the DLQ message so we don't re-read it
                        await receiver.complete_message(msg)

            except Exception as exc:
                logger.error("Error reading DLQ for %s: %s", queue_name, exc, exc_info=True)

            span.set_attribute("message_count", len(messages))
            logger.debug("Read %d DLQ messages from %s", len(messages), queue_name)
            return messages

    async def read_topic_dlq_messages(
        self, topic_name: str, subscription_name: str, max_count: int | None = None
    ) -> list[DLQMessage]:
        """Read messages from a topic subscription's dead-letter sub-queue."""
        with tracer.start_as_current_span("healer.servicebus.read_topic_dlq") as span:
            span.set_attribute("topic", topic_name)
            span.set_attribute("subscription", subscription_name)
            max_count = max_count or self._settings.dlq_batch_size
            assert self._client is not None

            receiver = self._client.get_subscription_receiver(
                topic_name=topic_name,
                subscription_name=subscription_name,
                sub_queue="deadletter",
                max_wait_time=5,
            )
            messages: list[DLQMessage] = []
            try:
                async with receiver:
                    batch = await receiver.receive_messages(
                        max_message_count=max_count, max_wait_time=5
                    )
                    for msg in batch:
                        try:
                            body = json.loads(str(msg))
                        except (json.JSONDecodeError, TypeError):
                            body = {"raw": str(msg)}

                        dlq_msg = DLQMessage(
                            message_id=msg.message_id or "",
                            queue_or_topic=f"{topic_name}/{subscription_name}",
                            body=body,
                            dead_letter_reason=msg.dead_letter_reason,
                            dead_letter_description=msg.dead_letter_error_description,
                            enqueued_time=msg.enqueued_time_utc,
                            delivery_count=msg.delivery_count or 0,
                            metadata=dict(msg.application_properties or {}),
                        )
                        messages.append(dlq_msg)
                        await receiver.complete_message(msg)

            except Exception as exc:
                logger.error(
                    "Error reading topic DLQ for %s/%s: %s",
                    topic_name,
                    subscription_name,
                    exc,
                    exc_info=True,
                )

            span.set_attribute("message_count", len(messages))
            return messages

    # ── DLQ replay ────────────────────────────────────────────────────

    async def replay_to_queue(
        self, queue_name: str, messages: list[DLQMessage]
    ) -> int:
        """Replay DLQ messages back to the original queue with backoff metadata."""
        with tracer.start_as_current_span("healer.servicebus.replay_to_queue") as span:
            span.set_attribute("queue", queue_name)
            span.set_attribute("message_count", len(messages))
            assert self._client is not None

            replayed = 0
            sender = self._client.get_queue_sender(queue_name=queue_name)
            try:
                async with sender:
                    for dlq_msg in messages:
                        new_replay_count = dlq_msg.replay_count + 1
                        if new_replay_count > self._settings.dlq_max_replay_attempts:
                            logger.warning(
                                "Message %s exceeded max replays (%d) — skipping",
                                dlq_msg.message_id,
                                self._settings.dlq_max_replay_attempts,
                            )
                            continue

                        props = dict(dlq_msg.metadata)
                        props["replay_count"] = new_replay_count
                        props["replayed_by"] = "healer"
                        props["original_dlq_reason"] = dlq_msg.dead_letter_reason or "unknown"

                        msg = ServiceBusMessage(
                            body=json.dumps(dlq_msg.body),
                            content_type="application/json",
                            application_properties=props,
                        )

                        # Exponential backoff scheduling
                        backoff_secs = self._settings.dlq_replay_backoff_seconds * (2 ** (new_replay_count - 1))
                        msg.scheduled_enqueue_time_utc = datetime.now(timezone.utc).__class__(
                            *datetime.now(timezone.utc).timetuple()[:6],
                            tzinfo=timezone.utc,
                        )
                        await sender.send_messages(msg)
                        replayed += 1
                        logger.info(
                            "Replayed message %s to %s (attempt %d, backoff %.1fs)",
                            dlq_msg.message_id,
                            queue_name,
                            new_replay_count,
                            backoff_secs,
                        )
            except Exception as exc:
                logger.error("Error replaying to %s: %s", queue_name, exc, exc_info=True)

            span.set_attribute("replayed_count", replayed)
            return replayed

    # ── DLQ statistics ────────────────────────────────────────────────

    async def get_queue_dlq_stats(self, queue_name: str) -> DLQStats:
        """Get DLQ statistics for a queue."""
        with tracer.start_as_current_span("healer.servicebus.queue_dlq_stats"):
            assert self._admin_client is not None
            try:
                runtime = await self._admin_client.get_queue_runtime_properties(queue_name)
                count = runtime.dead_letter_message_count or 0
                return DLQStats(
                    queue_name=queue_name,
                    message_count=count,
                    last_checked=datetime.now(timezone.utc),
                )
            except Exception as exc:
                logger.error("Error getting DLQ stats for %s: %s", queue_name, exc)
                return DLQStats(
                    queue_name=queue_name,
                    error_patterns={"stats_error": 1},
                    last_checked=datetime.now(timezone.utc),
                )

    async def get_topic_dlq_stats(
        self, topic_name: str, subscription_name: str
    ) -> DLQStats:
        """Get DLQ statistics for a topic subscription."""
        with tracer.start_as_current_span("healer.servicebus.topic_dlq_stats"):
            assert self._admin_client is not None
            try:
                runtime = await self._admin_client.get_subscription_runtime_properties(
                    topic_name, subscription_name
                )
                count = runtime.dead_letter_message_count or 0
                return DLQStats(
                    queue_name=f"{topic_name}/{subscription_name}",
                    message_count=count,
                    last_checked=datetime.now(timezone.utc),
                )
            except Exception as exc:
                logger.error(
                    "Error getting topic DLQ stats for %s/%s: %s",
                    topic_name,
                    subscription_name,
                    exc,
                )
                return DLQStats(
                    queue_name=f"{topic_name}/{subscription_name}",
                    error_patterns={"stats_error": 1},
                    last_checked=datetime.now(timezone.utc),
                )

    async def get_all_dlq_stats(self) -> list[DLQStats]:
        """Gather DLQ statistics across all monitored queues and topics."""
        with tracer.start_as_current_span("healer.servicebus.all_dlq_stats"):
            tasks = []
            for queue in self._settings.monitored_queues:
                tasks.append(self.get_queue_dlq_stats(queue))
            for topic in self._settings.monitored_topics:
                # Each topic may have multiple subscriptions — we check common ones
                for sub in ["orchestrator-sub", "knowledge-sub", "healer-sub"]:
                    tasks.append(self.get_topic_dlq_stats(topic, sub))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            stats = []
            for r in results:
                if isinstance(r, DLQStats):
                    stats.append(r)
                elif isinstance(r, Exception):
                    logger.warning("DLQ stats task failed: %s", r)
            return stats

    # ── Queue depth (for scaling analysis) ────────────────────────────

    async def get_queue_depth(self, queue_name: str) -> int:
        """Get active message count for a queue."""
        assert self._admin_client is not None
        try:
            runtime = await self._admin_client.get_queue_runtime_properties(queue_name)
            return runtime.active_message_count or 0
        except Exception as exc:
            logger.error("Error getting queue depth for %s: %s", queue_name, exc)
            return -1

    # ── Healing events ────────────────────────────────────────────────

    async def publish_healing_event(self, event: HealingEvent) -> None:
        """Publish a healing event to the healing-events topic."""
        with tracer.start_as_current_span("healer.servicebus.publish_healing_event") as span:
            span.set_attribute("event_type", event.event_type.value)
            span.set_attribute("service", event.service)
            assert self._healing_sender is not None

            msg = ServiceBusMessage(
                body=event.model_dump_json(),
                content_type="application/json",
                subject=event.service,
                application_properties={
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "service": event.service,
                },
            )
            async with self._healing_sender:
                await self._healing_sender.send_messages(msg)
            logger.info(
                "Published healing event %s type=%s service=%s",
                event.event_id,
                event.event_type.value,
                event.service,
            )

    # ── Cleanup ───────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close all connections."""
        if self._healing_sender:
            await self._healing_sender.close()
        if self._admin_client:
            await self._admin_client.close()
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()
        logger.info("Healer Service Bus client closed")
