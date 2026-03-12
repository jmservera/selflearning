"""HTTP client for the internal Knowledge Service API.

Used by the API Gateway to proxy and aggregate knowledge-graph queries.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


class KnowledgeClient:
    """Async HTTP client to the Knowledge Service."""

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
        with tracer.start_as_current_span("knowledge_client.health"):
            resp = await self.client.get("/health")
            resp.raise_for_status()
            return resp.json()

    # ── Entity operations ──────────────────────────────────────────────

    @tracer.start_as_current_span("knowledge_client.get_entity")
    async def get_entity(self, entity_id: str, topic: str | None = None) -> dict[str, Any] | None:
        params: dict[str, str] = {}
        if topic:
            params["topic"] = topic
        resp = await self.client.get(f"/entities/{entity_id}", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("knowledge_client.search_entities")
    async def search_entities(
        self,
        *,
        topic: str | None = None,
        entity_type: str | None = None,
        q: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "min_confidence": min_confidence}
        if topic:
            params["topic"] = topic
        if entity_type:
            params["entity_type"] = entity_type
        if q:
            params["q"] = q
        resp = await self.client.get("/entities/search", params=params)
        resp.raise_for_status()
        return resp.json()

    # ── Relationship operations ────────────────────────────────────────

    @tracer.start_as_current_span("knowledge_client.query_relationships")
    async def query_relationships(
        self,
        *,
        entity_id: str | None = None,
        relationship_type: str | None = None,
        topic: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if entity_id:
            params["entity_id"] = entity_id
        if relationship_type:
            params["relationship_type"] = relationship_type
        if topic:
            params["topic"] = topic
        resp = await self.client.get("/relationships", params=params)
        resp.raise_for_status()
        return resp.json()

    # ── Claim operations ───────────────────────────────────────────────

    @tracer.start_as_current_span("knowledge_client.query_claims")
    async def query_claims(
        self,
        *,
        topic: str | None = None,
        entity_id: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "min_confidence": min_confidence}
        if topic:
            params["topic"] = topic
        if entity_id:
            params["entity_id"] = entity_id
        resp = await self.client.get("/claims", params=params)
        resp.raise_for_status()
        return resp.json()

    # ── Search ─────────────────────────────────────────────────────────

    @tracer.start_as_current_span("knowledge_client.search")
    async def search(
        self,
        q: str,
        *,
        topic: str | None = None,
        doc_type: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 20,
        mode: str = "hybrid",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"q": q, "limit": limit, "mode": mode, "min_confidence": min_confidence}
        if topic:
            params["topic"] = topic
        if doc_type:
            params["doc_type"] = doc_type
        resp = await self.client.get("/search", params=params)
        resp.raise_for_status()
        return resp.json()

    # ── Topic analytics ────────────────────────────────────────────────

    @tracer.start_as_current_span("knowledge_client.topic_stats")
    async def topic_stats(self, topic: str) -> dict[str, Any]:
        resp = await self.client.get(f"/topics/{topic}/stats")
        resp.raise_for_status()
        return resp.json()

    @tracer.start_as_current_span("knowledge_client.topic_summary")
    async def topic_summary(self, topic: str) -> dict[str, Any]:
        resp = await self.client.get(f"/topics/{topic}/summary")
        resp.raise_for_status()
        return resp.json()

    # ── Knowledge graph (entities + relationships for visualization) ───

    @tracer.start_as_current_span("knowledge_client.topic_graph")
    async def topic_graph(self, topic: str, limit: int = 100) -> dict[str, Any]:
        """Fetch entities and relationships for graph visualization."""
        entities = await self.search_entities(topic=topic, limit=limit)
        relationships = await self.query_relationships(topic=topic, limit=limit * 2)
        return {"entities": entities, "relationships": relationships, "topic": topic}
