"""Azure Service Bus integration for the Reasoner service.

Consumes from ``reasoning-requests`` queue (point-to-point) and publishes
results to the ``reasoning-complete`` topic (pub/sub).
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

from config import ReasonerConfig

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("reasoner.servicebus")

MessageHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ServiceBusHandler:
    """Consume reasoning requests and publish reasoning results."""

    def __init__(self, config: ReasonerConfig) -> None:
        self._config = config
        self._credential: DefaultAzureCredential | None = None
        self._client: ServiceBusClient | None = None
        self._running = False

    async def initialize(self) -> None:
        fqns = f"{self._config.servicebus_namespace}.servicebus.windows.net"
        self._credential = DefaultAzureCredential()
        self._client = ServiceBusClient(
            fully_qualified_namespace=fqns,
            credential=self._credential,
        )
        logger.info("Service Bus client ready (%s)", fqns)

    async def close(self) -> None:
        self._running = False
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish_reasoning_result(self, result: dict[str, Any]) -> None:
        """Publish a reasoning result to the reasoning-complete topic."""
        with tracer.start_as_current_span("servicebus.publish") as span:
            topic = self._config.reasoning_complete_topic
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

            logger.info("Published reasoning result request_id=%s to %s", request_id, topic)

    # ------------------------------------------------------------------
    # Consuming (from QUEUE, not topic subscription)
    # ------------------------------------------------------------------

    async def consume_loop(self, handler: MessageHandler) -> None:
        """Continuously receive messages from the reasoning-requests queue.

        Args:
            handler: ``async (body: dict) -> dict`` — reasoning pipeline.
        """
        assert self._client is not None, "ServiceBusHandler not initialized"
        self._running = True

        queue = self._config.reasoning_requests_queue
        logger.info("Starting consume loop on queue %s", queue)

        receiver = self._client.get_queue_receiver(
            queue_name=queue,
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

                logger.info("Processing reasoning request_id=%s", request_id)
                result = await handler(body)

                await self.publish_reasoning_result(result)
                await receiver.complete_message(msg)

                logger.info("Completed reasoning request_id=%s", request_id)
            except Exception:
                logger.exception("Failed to process reasoning message — abandoning")
                try:
                    await receiver.abandon_message(msg)
                except Exception:
                    logger.exception("Failed to abandon message")
