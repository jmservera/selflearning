"""HTTP client for the Knowledge Service."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class KnowledgeClient:
    """Async HTTP client to query the Knowledge Service's internal API."""

    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url, timeout=30.0
        )

    async def get_entities(
        self, topic: str, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Fetch entities for a topic from the knowledge graph."""
        resp = await self._client.get(
            "/entities", params={"topic": topic, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_claims(
        self, topic: str, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Fetch claims for a topic from the knowledge graph."""
        resp = await self._client.get(
            "/claims", params={"topic": topic, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_relationships(
        self, topic: str, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Fetch relationships for a topic from the knowledge graph."""
        resp = await self._client.get(
            "/relationships", params={"topic": topic, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_topic_stats(self, topic: str) -> dict[str, Any]:
        """Get statistics for a topic."""
        resp = await self._client.get(f"/topics/{topic}/stats")
        resp.raise_for_status()
        return resp.json()

    async def search(
        self, topic: str, query: str, top_k: int = 10
    ) -> list[dict[str, Any]]:
        """Hybrid search over the knowledge graph."""
        resp = await self._client.post(
            "/search", json={"topic": topic, "query": query, "top_k": top_k}
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
