"""Azure Service Bus integration — consume scrape-requests, publish scrape-complete.

Uses the azure-servicebus async SDK with DefaultAzureCredential.  Messages that
fail repeatedly are automatically dead-lettered by the SDK's built-in mechanism;
we also manually dead-letter when deserialization fails.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient, ServiceBusReceiver, ServiceBusSender
from opentelemetry import trace

from config import ScraperSettings
from models import ScrapeCompleteEvent, ScrapeRequest

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Type alias for the callback that processes a single ScrapeRequest
MessageHandler = Callable[[ScrapeRequest], Awaitable[ScrapeCompleteEvent | None]]


# ---------------------------------------------------------------------------
# Consumer — reads from scrape-requests queue
# ---------------------------------------------------------------------------

class ScrapeRequestConsumer:
    """Continuously receives messages from the scrape-requests queue and
    dispatches them to a handler coroutine.
    """

    def __init__(
        self,
        settings: ScraperSettings,
        credential: DefaultAzureCredential,
        handler: MessageHandler,
    ) -> None:
        self._settings = settings
        self._credential = credential
        self._handler = handler
        self._client: ServiceBusClient | None = None
        self._receiver: ServiceBusReceiver | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._messages_processed = 0
        self._messages_failed = 0

    # -- Lifecycle -------------------------------------------------------------

    async def start(self) -> None:
        """Open the Service Bus connection and begin consuming in background."""
        with tracer.start_as_current_span("servicebus.consumer.start"):
            self._client = ServiceBusClient(
                fully_qualified_namespace=self._settings.servicebus_namespace,
                credential=self._credential,
            )
            self._receiver = self._client.get_queue_receiver(
                queue_name=self._settings.servicebus_queue_name,
                max_wait_time=self._settings.servicebus_max_wait_time,
            )
            self._running = True
            self._task = asyncio.create_task(self._consume_loop(), name="scrape-request-consumer")
            logger.info(
                "Service Bus consumer started on queue '%s'",
                self._settings.servicebus_queue_name,
            )

    async def stop(self) -> None:
        """Gracefully stop the consumer loop and close connections."""
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
        logger.info("Service Bus consumer stopped")

    # -- Core loop -------------------------------------------------------------

    async def _consume_loop(self) -> None:
        """Receive messages in batches and dispatch to handler."""
        assert self._receiver is not None
        sem = asyncio.Semaphore(self._settings.servicebus_max_concurrent)

        while self._running:
            try:
                messages = await self._receiver.receive_messages(
                    max_message_count=self._settings.servicebus_max_concurrent,
                    max_wait_time=self._settings.servicebus_max_wait_time,
                )
                if not messages:
                    continue

                tasks = [
                    self._process_message(msg, sem)
                    for msg in messages
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in consumer loop — will retry in 5s")
                await asyncio.sleep(5)

    async def _process_message(
        self,
        message: Any,
        sem: asyncio.Semaphore,
    ) -> None:
        """Deserialize, process, and complete/dead-letter a single message."""
        async with sem:
            with tracer.start_as_current_span("servicebus.process_message") as span:
                assert self._receiver is not None
                try:
                    body = _deserialize_message(message)
                    request = ScrapeRequest.model_validate(body)
                    span.set_attribute("request_id", request.request_id)
                    span.set_attribute("topic", request.topic)

                    logger.info(
                        "Processing scrape request %s (topic=%s, source=%s)",
                        request.request_id,
                        request.topic,
                        request.source_type.value,
                    )

                    result = await self._handler(request)
                    await self._receiver.complete_message(message)
                    self._messages_processed += 1

                    if result:
                        logger.info(
                            "Request %s completed: %d URLs succeeded / %d attempted",
                            request.request_id,
                            result.stats.urls_succeeded,
                            result.stats.urls_attempted,
                        )

                except (json.JSONDecodeError, ValueError) as exc:
                    logger.error("Invalid message — dead-lettering: %s", exc)
                    await self._receiver.dead_letter_message(
                        message,
                        reason="InvalidMessage",
                        error_description=str(exc),
                    )
                    self._messages_failed += 1

                except Exception as exc:
                    logger.exception("Handler failed for message: %s", exc)
                    delivery_count = message.delivery_count or 0
                    if delivery_count >= self._settings.max_retries:
                        logger.warning(
                            "Max delivery count (%d) reached — dead-lettering",
                            delivery_count,
                        )
                        await self._receiver.dead_letter_message(
                            message,
                            reason="MaxRetriesExceeded",
                            error_description=str(exc),
                        )
                    else:
                        await self._receiver.abandon_message(message)
                    self._messages_failed += 1

    @property
    def stats(self) -> dict[str, int]:
        return {
            "messages_processed": self._messages_processed,
            "messages_failed": self._messages_failed,
        }


# ---------------------------------------------------------------------------
# Publisher — sends to scrape-complete topic
# ---------------------------------------------------------------------------

class ScrapeCompletePublisher:
    """Publishes ScrapeCompleteEvent messages to the scrape-complete topic."""

    def __init__(
        self,
        settings: ScraperSettings,
        credential: DefaultAzureCredential,
    ) -> None:
        self._settings = settings
        self._credential = credential
        self._client: ServiceBusClient | None = None
        self._sender: ServiceBusSender | None = None
        self._messages_sent = 0

    async def start(self) -> None:
        with tracer.start_as_current_span("servicebus.publisher.start"):
            self._client = ServiceBusClient(
                fully_qualified_namespace=self._settings.servicebus_namespace,
                credential=self._credential,
            )
            self._sender = self._client.get_topic_sender(
                topic_name=self._settings.servicebus_topic_name,
            )
            logger.info(
                "Service Bus publisher ready on topic '%s'",
                self._settings.servicebus_topic_name,
            )

    async def stop(self) -> None:
        if self._sender:
            await self._sender.close()
        if self._client:
            await self._client.close()
        logger.info("Service Bus publisher stopped")

    async def publish(self, event: ScrapeCompleteEvent) -> None:
        """Serialize and send a ScrapeCompleteEvent to the topic."""
        with tracer.start_as_current_span("servicebus.publish_event") as span:
            span.set_attribute("request_id", event.request_id)
            span.set_attribute("results_count", len(event.results))
            if self._sender is None:
                raise RuntimeError("Publisher not started")

            body = event.model_dump_json()
            message = ServiceBusMessage(
                body=body,
                content_type="application/json",
                subject=event.topic,
                application_properties={
                    "request_id": event.request_id,
                    "topic": event.topic,
                    "urls_succeeded": event.stats.urls_succeeded,
                },
            )
            await self._sender.send_messages(message)
            self._messages_sent += 1
            logger.info(
                "Published scrape-complete event for request %s (%d results)",
                event.request_id,
                len(event.results),
            )

    @property
    def stats(self) -> dict[str, int]:
        return {"messages_sent": self._messages_sent}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deserialize_message(message: Any) -> dict[str, Any]:
    """Extract the JSON body from a Service Bus message."""
    raw = b""
    body = message.body
    if isinstance(body, bytes):
        raw = body
    else:
        for chunk in body:
            raw += chunk
    return json.loads(raw.decode("utf-8"))
