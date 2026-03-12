"""HTTP client for the internal Orchestrator Service API.

Used by the API Gateway to trigger learning cycles, manage topics,
and query learning status.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


class OrchestratorClient:
    """Async HTTP client to the Orchestrator Service."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=_TIMEOUT)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        assert self._client is not None, "Call initialize() first"
        return self._client

    # ── Health ─────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        with tracer.start_as_current_span("orchestrator_client.health"):
            resp = await self.client.get("/health")
            resp.raise_for_status()
            return resp.json()

    # ── Topic management ───────────────────────────────────────────────

    @tracer.start_as_current_span("orchestrator_client.create_topic")
    async def create_topic(self, payload: dict[str, Any]) -> dict[str, Any]:
        resp = await self.client.post("/topics", json=payload)
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("orchestrator_client.list_topics")
    async def list_topics(self) -> list[dict[str, Any]]:
        resp = await self.client.get("/topics")
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("orchestrator_client.get_topic")
    async def get_topic(self, topic_id: str) -> dict[str, Any] | None:
        resp = await self.client.get(f"/topics/{topic_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("orchestrator_client.trigger_learning")
    async def trigger_learning(self, topic_id: str) -> dict[str, Any]:
        resp = await self.client.post(f"/topics/{topic_id}/learn")
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("orchestrator_client.pause_topic")
    async def pause_topic(self, topic_id: str) -> dict[str, Any]:
        resp = await self.client.put(f"/topics/{topic_id}/pause")
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("orchestrator_client.resume_topic")
    async def resume_topic(self, topic_id: str) -> dict[str, Any]:
        resp = await self.client.put(f"/topics/{topic_id}/resume")
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("orchestrator_client.update_priority")
    async def update_priority(self, topic_id: str, priority: int) -> dict[str, Any]:
        resp = await self.client.put(
            f"/topics/{topic_id}/priority", json={"priority": priority}
        )
        resp.raise_for_status()
        return resp.json()

    # ── Status / progress ──────────────────────────────────────────────

    @tracer.start_as_current_span("orchestrator_client.get_status")
    async def get_status(self) -> dict[str, Any]:
        resp = await self.client.get("/status")
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("orchestrator_client.get_progress")
    async def get_progress(self) -> dict[str, Any]:
        resp = await self.client.get("/progress")
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("orchestrator_client.get_logs")
    async def get_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        resp = await self.client.get("/logs", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("orchestrator_client.get_decisions")
    async def get_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        resp = await self.client.get("/decisions", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()
