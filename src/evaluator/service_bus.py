"""Azure Service Bus publisher for evaluation-complete events."""

import json
import logging
from typing import Any

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient, ServiceBusSender

logger = logging.getLogger(__name__)


class EvaluationPublisher:
    """Publishes evaluation-complete events to an Azure Service Bus topic."""

    def __init__(
        self,
        namespace: str,
        topic_name: str = "evaluation-complete",
        client: ServiceBusClient | None = None,
    ) -> None:
        self._namespace = namespace
        self._topic_name = topic_name
        self._client = client
        self._sender: ServiceBusSender | None = None

    async def initialize(self) -> None:
        """Create the Service Bus client and topic sender."""
        if self._client is None:
            credential = DefaultAzureCredential()
            fqns = f"{self._namespace}.servicebus.windows.net"
            self._client = ServiceBusClient(fqns, credential)
        self._sender = self._client.get_topic_sender(self._topic_name)
        logger.info(
            "Service Bus publisher initialized for topic '%s'", self._topic_name
        )

    async def publish(self, payload: dict[str, Any]) -> None:
        """Publish an evaluation-complete event."""
        if self._sender is None:
            raise RuntimeError(
                "Publisher not initialized. Call initialize() first."
            )
        message = ServiceBusMessage(
            body=json.dumps(payload, default=str),
            content_type="application/json",
            subject="evaluation-complete",
        )
        await self._sender.send_messages(message)
        logger.info(
            "Published evaluation-complete event for topic '%s'",
            payload.get("topic"),
        )

    async def close(self) -> None:
        """Close the sender and client."""
        if self._sender:
            await self._sender.close()
        if self._client:
            await self._client.close()
