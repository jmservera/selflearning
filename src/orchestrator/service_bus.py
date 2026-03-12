"""Service Bus client for the Orchestrator.

Publishes scrape-requests and reasoning-requests to queues.
Subscribes to scrape-complete, extraction-complete, reasoning-complete,
and evaluation-complete topics for pipeline coordination.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient, ServiceBusReceiver, ServiceBusSender
from opentelemetry import trace

from config import OrchestratorSettings
from models import CompletionEvent, EvaluationResult, ReasoningRequest, ScrapeRequest

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

EventHandler = Callable[[CompletionEvent], Coroutine[Any, Any, None]]


class OrchestratorServiceBus:
    """Manages all Service Bus interactions for the Orchestrator.

    Publishing:
      - scrape-requests queue: ScrapeRequest messages
      - reasoning-requests queue: ReasoningRequest messages

    Subscribing:
      - scrape-complete topic → orchestrator-sub
      - extraction-complete topic → orchestrator-sub
      - reasoning-complete topic → orchestrator-sub
      - evaluation-complete topic → orchestrator-sub
    """

    def __init__(self, settings: OrchestratorSettings) -> None:
        self._settings = settings
        self._credential: DefaultAzureCredential | None = None
        self._client: ServiceBusClient | None = None
        self._senders: dict[str, ServiceBusSender] = {}
        self._receivers: dict[str, ServiceBusReceiver] = {}
        self._running = False
        self._listener_tasks: list[asyncio.Task[None]] = []
        # Per-topic completion buffers — filled by subscription listeners
        self._completion_buffers: dict[str, asyncio.Queue[CompletionEvent]] = {}
        self._evaluation_buffer: asyncio.Queue[EvaluationResult] = asyncio.Queue()

    async def initialize(self) -> None:
        """Open the Service Bus connection and create senders/receivers."""
        with tracer.start_as_current_span("servicebus.initialize"):
            self._credential = DefaultAzureCredential()
            self._client = ServiceBusClient(
                fully_qualified_namespace=self._settings.servicebus_namespace,
                credential=self._credential,
            )
            # Create senders for outgoing queues
            self._senders["scrape-requests"] = self._client.get_queue_sender(
                queue_name=self._settings.scrape_requests_queue
            )
            self._senders["reasoning-requests"] = self._client.get_queue_sender(
                queue_name=self._settings.reasoning_requests_queue
            )
            # Create receivers for completion topics
            for topic_name in [
                self._settings.scrape_complete_topic,
                self._settings.extraction_complete_topic,
                self._settings.reasoning_complete_topic,
                self._settings.evaluation_complete_topic,
            ]:
                self._receivers[topic_name] = self._client.get_subscription_receiver(
                    topic_name=topic_name,
                    subscription_name=self._settings.subscription_name,
                )
            logger.info("Service Bus client initialized — namespace=%s", self._settings.servicebus_namespace)

    async def start_listeners(self) -> None:
        """Launch background tasks that listen to completion topics."""
        self._running = True
        for topic_name, receiver in self._receivers.items():
            task = asyncio.create_task(
                self._listen_loop(topic_name, receiver),
                name=f"sb-listener-{topic_name}",
            )
            self._listener_tasks.append(task)
        logger.info("Started %d Service Bus listeners", len(self._listener_tasks))

    async def stop_listeners(self) -> None:
        """Stop all listener tasks gracefully."""
        self._running = False
        for task in self._listener_tasks:
            task.cancel()
        await asyncio.gather(*self._listener_tasks, return_exceptions=True)
        self._listener_tasks.clear()
        logger.info("All Service Bus listeners stopped")

    # ── Publishing ────────────────────────────────────────────────────

    async def publish_scrape_request(self, request: ScrapeRequest) -> None:
        """Publish a scrape request to the scrape-requests queue."""
        with tracer.start_as_current_span("servicebus.publish_scrape_request") as span:
            span.set_attribute("request_id", request.request_id)
            span.set_attribute("topic", request.topic)
            span.set_attribute("query", request.query)
            sender = self._senders.get("scrape-requests")
            if sender is None:
                raise RuntimeError("Scrape-requests sender not initialized")
            body = request.model_dump_json()
            message = ServiceBusMessage(
                body=body,
                content_type="application/json",
                subject=request.topic,
                application_properties={
                    "request_id": request.request_id,
                    "topic": request.topic,
                    "priority": request.priority,
                    "source_type": request.source_type.value,
                },
            )
            async with sender:
                await sender.send_messages(message)
            logger.info(
                "Published scrape request %s for topic=%s query=%s",
                request.request_id,
                request.topic,
                request.query[:80],
            )

    async def publish_scrape_requests_batch(self, requests: list[ScrapeRequest]) -> None:
        """Publish multiple scrape requests as a batch."""
        with tracer.start_as_current_span("servicebus.publish_scrape_batch") as span:
            span.set_attribute("batch_size", len(requests))
            sender = self._senders.get("scrape-requests")
            if sender is None:
                raise RuntimeError("Scrape-requests sender not initialized")
            messages = []
            for req in requests:
                msg = ServiceBusMessage(
                    body=req.model_dump_json(),
                    content_type="application/json",
                    subject=req.topic,
                    application_properties={
                        "request_id": req.request_id,
                        "topic": req.topic,
                        "priority": req.priority,
                        "source_type": req.source_type.value,
                    },
                )
                messages.append(msg)
            async with sender:
                await sender.send_messages(messages)
            logger.info("Published batch of %d scrape requests", len(requests))

    async def publish_reasoning_request(self, request: ReasoningRequest) -> None:
        """Publish a reasoning request to the reasoning-requests queue."""
        with tracer.start_as_current_span("servicebus.publish_reasoning_request") as span:
            span.set_attribute("request_id", request.request_id)
            span.set_attribute("topic", request.topic)
            span.set_attribute("reasoning_type", request.reasoning_type.value)
            sender = self._senders.get("reasoning-requests")
            if sender is None:
                raise RuntimeError("Reasoning-requests sender not initialized")
            body = request.model_dump_json()
            message = ServiceBusMessage(
                body=body,
                content_type="application/json",
                subject=request.topic,
                application_properties={
                    "request_id": request.request_id,
                    "topic": request.topic,
                    "reasoning_type": request.reasoning_type.value,
                },
            )
            async with sender:
                await sender.send_messages(message)
            logger.info(
                "Published reasoning request %s type=%s topic=%s",
                request.request_id,
                request.reasoning_type.value,
                request.topic,
            )

    # ── Waiting for completions ───────────────────────────────────────

    def _get_buffer(self, key: str) -> asyncio.Queue[CompletionEvent]:
        """Get or create a completion buffer for a given key."""
        if key not in self._completion_buffers:
            self._completion_buffers[key] = asyncio.Queue()
        return self._completion_buffers[key]

    async def wait_for_completions(
        self,
        request_ids: set[str],
        topic_name: str,
        timeout_seconds: float,
    ) -> list[CompletionEvent]:
        """Wait for completion events matching the given request IDs.

        Returns all received events (may be fewer than requested if timeout hit).
        """
        with tracer.start_as_current_span("servicebus.wait_for_completions") as span:
            span.set_attribute("expected_count", len(request_ids))
            span.set_attribute("topic", topic_name)
            span.set_attribute("timeout", timeout_seconds)

            buffer = self._get_buffer(topic_name)
            collected: list[CompletionEvent] = []
            remaining = set(request_ids)
            deadline = asyncio.get_event_loop().time() + timeout_seconds

            while remaining:
                time_left = deadline - asyncio.get_event_loop().time()
                if time_left <= 0:
                    logger.warning(
                        "Timeout waiting for completions on %s — got %d/%d",
                        topic_name,
                        len(collected),
                        len(request_ids),
                    )
                    break
                try:
                    event = await asyncio.wait_for(buffer.get(), timeout=min(time_left, 10.0))
                    if event.request_id in remaining:
                        collected.append(event)
                        remaining.discard(event.request_id)
                        logger.debug(
                            "Received completion for %s — %d remaining",
                            event.request_id,
                            len(remaining),
                        )
                except asyncio.TimeoutError:
                    continue

            span.set_attribute("received_count", len(collected))
            return collected

    async def wait_for_evaluation(self, timeout_seconds: float) -> EvaluationResult | None:
        """Wait for an evaluation-complete event."""
        with tracer.start_as_current_span("servicebus.wait_for_evaluation"):
            try:
                event = await asyncio.wait_for(
                    self._evaluation_buffer.get(), timeout=timeout_seconds
                )
                return event
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for evaluation result")
                return None

    # ── Listener loop ─────────────────────────────────────────────────

    async def _listen_loop(self, topic_name: str, receiver: ServiceBusReceiver) -> None:
        """Continuously receive messages from a topic subscription."""
        logger.info("Listener started for topic=%s", topic_name)
        is_evaluation = topic_name == self._settings.evaluation_complete_topic

        while self._running:
            try:
                async with receiver:
                    async for message in receiver:
                        with tracer.start_as_current_span(f"servicebus.receive.{topic_name}"):
                            try:
                                body_str = str(message)
                                data = json.loads(body_str)

                                if is_evaluation:
                                    event = EvaluationResult.model_validate(data)
                                    await self._evaluation_buffer.put(event)
                                    logger.info(
                                        "Received evaluation for topic=%s score=%.3f",
                                        event.topic,
                                        event.overall_score,
                                    )
                                else:
                                    event = CompletionEvent.model_validate(data)
                                    buffer = self._get_buffer(topic_name)
                                    await buffer.put(event)
                                    logger.debug(
                                        "Received %s completion request_id=%s",
                                        topic_name,
                                        event.request_id,
                                    )

                                await receiver.complete_message(message)
                            except Exception as exc:
                                logger.error(
                                    "Error processing message from %s: %s",
                                    topic_name,
                                    exc,
                                    exc_info=True,
                                )
                                await receiver.abandon_message(message)
            except asyncio.CancelledError:
                logger.info("Listener cancelled for topic=%s", topic_name)
                break
            except Exception as exc:
                logger.error(
                    "Listener error for %s — reconnecting in 5s: %s",
                    topic_name,
                    exc,
                    exc_info=True,
                )
                await asyncio.sleep(5.0)

    # ── Cleanup ───────────────────────────────────────────────────────

    async def close(self) -> None:
        """Stop listeners and close the Service Bus client."""
        await self.stop_listeners()
        for sender in self._senders.values():
            await sender.close()
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()
        logger.info("Service Bus client closed")
