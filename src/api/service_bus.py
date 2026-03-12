"""Service Bus integration for the API Gateway.

Publishes commands to the orchestrator and subscribes to system-status events
that are forwarded to WebSocket clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient, ServiceBusSender, ServiceBusReceiver
from opentelemetry import trace

from .config import ServiceBusConfig

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

StatusCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class GatewayServiceBus:
    """Publishes orchestrator commands and subscribes to status events."""

    def __init__(self, config: ServiceBusConfig) -> None:
        self._config = config
        self._credential: DefaultAzureCredential | None = None
        self._client: ServiceBusClient | None = None
        self._sender: ServiceBusSender | None = None
        self._receiver: ServiceBusReceiver | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._status_callbacks: list[StatusCallback] = []

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        self._credential = DefaultAzureCredential()
        fqns = f"{self._config.namespace}.servicebus.windows.net"
        self._client = ServiceBusClient(
            fully_qualified_namespace=fqns,
            credential=self._credential,
        )
        self._sender = self._client.get_queue_sender(
            queue_name=self._config.orchestrator_queue,
        )
        try:
            self._receiver = self._client.get_subscription_receiver(
                topic_name=self._config.status_topic,
                subscription_name=self._config.status_subscription,
                prefetch_count=10,
            )
            self._running = True
            self._task = asyncio.create_task(self._status_loop())
        except Exception:
            logger.warning("Status topic subscription unavailable (non-fatal)", exc_info=True)
        logger.info("Gateway Service Bus connected")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._sender:
            await self._sender.close()
        if self._receiver:
            await self._receiver.close()
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()
        logger.info("Gateway Service Bus disconnected")

    # ── Publish commands ───────────────────────────────────────────────

    @tracer.start_as_current_span("servicebus.publish_command")
    async def publish_command(self, command: str, payload: dict[str, Any]) -> None:
        """Send a command to the orchestrator queue."""
        assert self._sender is not None
        message_body = json.dumps({
            "command": command,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await self._sender.send_messages(ServiceBusMessage(body=message_body))
        logger.info("Published command: %s", command)

    async def publish_learn(self, topic_id: str) -> None:
        await self.publish_command("trigger_learning", {"topic_id": topic_id})

    async def publish_pause(self, topic_id: str) -> None:
        await self.publish_command("pause_topic", {"topic_id": topic_id})

    async def publish_resume(self, topic_id: str) -> None:
        await self.publish_command("resume_topic", {"topic_id": topic_id})

    # ── Status subscription ────────────────────────────────────────────

    def on_status(self, callback: StatusCallback) -> None:
        self._status_callbacks.append(callback)

    async def _status_loop(self) -> None:
        assert self._receiver is not None
        while self._running:
            try:
                messages = await self._receiver.receive_messages(
                    max_message_count=10, max_wait_time=5
                )
                for msg in messages:
                    try:
                        body = json.loads(str(msg))
                        for cb in self._status_callbacks:
                            await cb(body)
                        await self._receiver.complete_message(msg)
                    except Exception:
                        logger.exception("Failed to process status message")
                        await self._receiver.abandon_message(msg)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Status loop error; retrying")
                await asyncio.sleep(5)
