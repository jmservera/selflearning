"""Tests for the Knowledge service.

These tests define expected behavioral contracts for the knowledge service.
They use inline reference implementations that validate the specified
requirements. When the knowledge service is implemented, update imports
to reference the actual service modules.
"""

import json
import math
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest


# ============================================================================
# Reference implementations — behavioral contracts for knowledge service
# ============================================================================


class InMemoryKnowledgeStore:
    """In-memory knowledge graph store for testing behavioral contracts.

    Mirrors the expected Cosmos DB-backed knowledge service API.
    """

    def __init__(self) -> None:
        self.entities: dict[str, dict[str, Any]] = {}
        self.relationships: dict[str, dict[str, Any]] = {}
        self.claims: dict[str, dict[str, Any]] = {}
        self.sources: dict[str, dict[str, Any]] = {}

    # --- Entity CRUD ---

    def create_entity(self, entity: dict[str, Any]) -> dict[str, Any]:
        entity_id = entity.get("id", str(uuid4()))
        entity["id"] = entity_id
        if entity_id in self.entities:
            raise ValueError(f"Entity {entity_id} already exists")
        self.entities[entity_id] = entity
        return entity

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        return self.entities.get(entity_id)

    def update_entity(
        self, entity_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        if entity_id not in self.entities:
            return None
        self.entities[entity_id].update(updates)
        return self.entities[entity_id]

    def delete_entity(self, entity_id: str) -> bool:
        return self.entities.pop(entity_id, None) is not None

    def list_entities(
        self, topic: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        results = list(self.entities.values())
        if topic:
            results = [e for e in results if e.get("topic") == topic]
        return results[:limit]

    # --- Entity Resolution / Merge ---

    def resolve_entity(
        self, name: str, topic: str
    ) -> dict[str, Any] | None:
        """Find an existing entity by name within a topic (case-insensitive)."""
        name_lower = name.lower()
        for entity in self.entities.values():
            if (
                entity.get("name", "").lower() == name_lower
                and entity.get("topic") == topic
            ):
                return entity
        return None

    def merge_entities(
        self, source_id: str, target_id: str
    ) -> dict[str, Any] | None:
        """Merge source entity into target, combining metadata."""
        source = self.entities.get(source_id)
        target = self.entities.get(target_id)
        if not source or not target:
            return None

        # Merge descriptions (keep longer)
        if len(source.get("description", "")) > len(
            target.get("description", "")
        ):
            target["description"] = source["description"]

        # Average confidence
        src_conf = source.get("confidence", 0.5)
        tgt_conf = target.get("confidence", 0.5)
        target["confidence"] = (src_conf + tgt_conf) / 2

        # Track merge history
        aliases = target.get("aliases", [])
        aliases.append(source.get("name", ""))
        target["aliases"] = aliases

        # Remove source, update relationships
        del self.entities[source_id]
        for rel in self.relationships.values():
            if rel.get("source_id") == source_id:
                rel["source_id"] = target_id
            if rel.get("target_id") == source_id:
                rel["target_id"] = target_id

        return target

    # --- Search ---

    def keyword_search(
        self, query: str, topic: str | None = None, top_k: int = 10
    ) -> list[dict[str, Any]]:
        """Simple keyword search over entity names and descriptions."""
        query_lower = query.lower()
        results = []
        for entity in self.entities.values():
            if topic and entity.get("topic") != topic:
                continue
            name = entity.get("name", "").lower()
            desc = entity.get("description", "").lower()
            if query_lower in name or query_lower in desc:
                results.append(entity)
        return results[:top_k]

    def vector_search(
        self, embedding: list[float], topic: str | None = None, top_k: int = 10
    ) -> list[dict[str, Any]]:
        """Mock vector search using cosine similarity on stored embeddings."""
        results = []
        for entity in self.entities.values():
            if topic and entity.get("topic") != topic:
                continue
            stored_emb = entity.get("embedding")
            if stored_emb:
                sim = self._cosine_similarity(embedding, stored_emb)
                results.append((sim, entity))
        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results[:top_k]]

    def hybrid_search(
        self,
        query: str,
        embedding: list[float] | None = None,
        topic: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Combine keyword and vector search results."""
        keyword_results = self.keyword_search(query, topic, top_k)
        if embedding:
            vector_results = self.vector_search(embedding, topic, top_k)
            # Merge, deduplicate, keyword results first
            seen = {r.get("id") for r in keyword_results}
            for r in vector_results:
                if r.get("id") not in seen:
                    keyword_results.append(r)
                    seen.add(r.get("id"))
        return keyword_results[:top_k]

    # --- Bulk Operations ---

    def bulk_ingest(
        self, items: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Ingest multiple items, resolving duplicates."""
        created = 0
        updated = 0
        for item in items:
            doc_type = item.get("doc_type", "entity")
            if doc_type == "entity":
                existing = self.resolve_entity(
                    item.get("name", ""), item.get("topic", "")
                )
                if existing:
                    self.update_entity(existing["id"], item)
                    updated += 1
                else:
                    self.create_entity(item)
                    created += 1
            elif doc_type == "claim":
                claim_id = item.get("id", str(uuid4()))
                item["id"] = claim_id
                self.claims[claim_id] = item
                created += 1
            elif doc_type == "relationship":
                rel_id = item.get("id", str(uuid4()))
                item["id"] = rel_id
                self.relationships[rel_id] = item
                created += 1
        return {"created": created, "updated": updated}

    # --- Topic Stats ---

    def get_topic_stats(self, topic: str) -> dict[str, Any]:
        entities = [e for e in self.entities.values() if e.get("topic") == topic]
        claims = [c for c in self.claims.values() if c.get("topic") == topic]
        rels = [r for r in self.relationships.values() if r.get("topic") == topic]
        confidences = [
            e.get("confidence", 0.5) for e in entities
        ] + [c.get("confidence", 0.5) for c in claims]
        avg_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )
        return {
            "topic": topic,
            "entity_count": len(entities),
            "claim_count": len(claims),
            "relationship_count": len(rels),
            "avg_confidence": round(avg_confidence, 3),
        }

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


# ============================================================================
# Tests
# ============================================================================


@pytest.fixture
def store() -> InMemoryKnowledgeStore:
    return InMemoryKnowledgeStore()


class TestEntityCRUD:
    """Test entity create, read, update, delete."""

    def test_create_entity(self, store):
        entity = store.create_entity(
            {"name": "Neural Network", "type": "concept", "topic": "ml"}
        )
        assert entity["id"]
        assert entity["name"] == "Neural Network"

    def test_get_entity(self, store):
        created = store.create_entity(
            {"id": "e1", "name": "NN", "topic": "ml"}
        )
        found = store.get_entity("e1")
        assert found is not None
        assert found["name"] == "NN"

    def test_get_nonexistent_entity(self, store):
        assert store.get_entity("nonexistent") is None

    def test_update_entity(self, store):
        store.create_entity({"id": "e1", "name": "NN", "topic": "ml"})
        updated = store.update_entity("e1", {"description": "A model"})
        assert updated is not None
        assert updated["description"] == "A model"

    def test_update_nonexistent_returns_none(self, store):
        assert store.update_entity("nope", {"x": 1}) is None

    def test_delete_entity(self, store):
        store.create_entity({"id": "e1", "name": "NN", "topic": "ml"})
        assert store.delete_entity("e1") is True
        assert store.get_entity("e1") is None

    def test_delete_nonexistent_returns_false(self, store):
        assert store.delete_entity("nope") is False

    def test_list_entities_by_topic(self, store):
        store.create_entity({"name": "A", "topic": "ml"})
        store.create_entity({"name": "B", "topic": "ml"})
        store.create_entity({"name": "C", "topic": "bio"})
        results = store.list_entities(topic="ml")
        assert len(results) == 2

    def test_duplicate_id_raises(self, store):
        store.create_entity({"id": "e1", "name": "A", "topic": "ml"})
        with pytest.raises(ValueError):
            store.create_entity({"id": "e1", "name": "B", "topic": "ml"})

    def test_list_with_limit(self, store):
        for i in range(10):
            store.create_entity({"name": f"E{i}", "topic": "ml"})
        results = store.list_entities(topic="ml", limit=5)
        assert len(results) == 5


class TestEntityResolution:
    """Test entity resolution and merging."""

    def test_resolve_by_name(self, store):
        store.create_entity(
            {"id": "e1", "name": "Neural Network", "topic": "ml"}
        )
        found = store.resolve_entity("neural network", "ml")
        assert found is not None
        assert found["id"] == "e1"

    def test_resolve_case_insensitive(self, store):
        store.create_entity({"id": "e1", "name": "CNN", "topic": "ml"})
        assert store.resolve_entity("cnn", "ml") is not None
        assert store.resolve_entity("CNN", "ml") is not None

    def test_resolve_wrong_topic_returns_none(self, store):
        store.create_entity({"id": "e1", "name": "DNA", "topic": "bio"})
        assert store.resolve_entity("DNA", "ml") is None

    def test_merge_entities(self, store):
        store.create_entity(
            {
                "id": "e1",
                "name": "NN",
                "description": "Short",
                "confidence": 0.8,
                "topic": "ml",
            }
        )
        store.create_entity(
            {
                "id": "e2",
                "name": "Neural Net",
                "description": "A longer description of neural networks",
                "confidence": 0.9,
                "topic": "ml",
            }
        )
        merged = store.merge_entities("e2", "e1")
        assert merged is not None
        assert "Neural Net" in merged["aliases"]
        assert merged["confidence"] == pytest.approx(0.85)
        assert "longer" in merged["description"]
        assert store.get_entity("e2") is None

    def test_merge_updates_relationships(self, store):
        store.create_entity({"id": "e1", "name": "A", "topic": "ml"})
        store.create_entity({"id": "e2", "name": "B", "topic": "ml"})
        store.create_entity({"id": "e3", "name": "C", "topic": "ml"})
        store.relationships["r1"] = {
            "id": "r1",
            "source_id": "e2",
            "target_id": "e3",
            "type": "related",
        }
        store.merge_entities("e2", "e1")
        assert store.relationships["r1"]["source_id"] == "e1"

    def test_merge_nonexistent_returns_none(self, store):
        store.create_entity({"id": "e1", "name": "A", "topic": "ml"})
        assert store.merge_entities("nonexistent", "e1") is None


class TestSearch:
    """Test search capabilities."""

    def test_keyword_search_by_name(self, store):
        store.create_entity(
            {"id": "e1", "name": "Backpropagation", "topic": "ml", "description": ""}
        )
        store.create_entity(
            {"id": "e2", "name": "CNN", "topic": "ml", "description": ""}
        )
        results = store.keyword_search("backprop", topic="ml")
        assert len(results) == 1
        assert results[0]["id"] == "e1"

    def test_keyword_search_by_description(self, store):
        store.create_entity(
            {
                "id": "e1",
                "name": "NN",
                "description": "uses gradient descent optimization",
                "topic": "ml",
            }
        )
        results = store.keyword_search("gradient", topic="ml")
        assert len(results) == 1

    def test_keyword_search_respects_topic(self, store):
        store.create_entity(
            {"id": "e1", "name": "Cell", "topic": "bio", "description": ""}
        )
        store.create_entity(
            {"id": "e2", "name": "Cell", "topic": "cs", "description": ""}
        )
        results = store.keyword_search("cell", topic="bio")
        assert len(results) == 1
        assert results[0]["topic"] == "bio"

    def test_vector_search(self, store):
        store.create_entity(
            {
                "id": "e1",
                "name": "A",
                "topic": "ml",
                "embedding": [1.0, 0.0, 0.0],
            }
        )
        store.create_entity(
            {
                "id": "e2",
                "name": "B",
                "topic": "ml",
                "embedding": [0.0, 1.0, 0.0],
            }
        )
        results = store.vector_search([1.0, 0.1, 0.0], topic="ml")
        assert len(results) == 2
        assert results[0]["id"] == "e1"  # most similar

    def test_hybrid_search_combines_results(self, store):
        store.create_entity(
            {
                "id": "e1",
                "name": "Transformer",
                "topic": "ml",
                "description": "",
                "embedding": [0.0, 0.0, 1.0],
            }
        )
        store.create_entity(
            {
                "id": "e2",
                "name": "Attention",
                "topic": "ml",
                "description": "mechanism used in transformers",
                "embedding": [1.0, 0.0, 0.0],
            }
        )
        results = store.hybrid_search(
            "transformer", embedding=[1.0, 0.0, 0.0], topic="ml"
        )
        ids = {r["id"] for r in results}
        assert "e1" in ids  # keyword match
        assert "e2" in ids  # vector match + keyword match

    def test_search_top_k_limits(self, store):
        for i in range(20):
            store.create_entity(
                {"name": f"Entity neural {i}", "topic": "ml", "description": ""}
            )
        results = store.keyword_search("neural", topic="ml", top_k=5)
        assert len(results) == 5

    def test_empty_search_returns_empty(self, store):
        results = store.keyword_search("nonexistent", topic="ml")
        assert results == []


class TestBulkIngest:
    """Test bulk ingestion of knowledge items."""

    def test_bulk_create_entities(self, store):
        items = [
            {"doc_type": "entity", "name": f"E{i}", "topic": "ml"} for i in range(5)
        ]
        result = store.bulk_ingest(items)
        assert result["created"] == 5
        assert result["updated"] == 0

    def test_bulk_updates_existing(self, store):
        store.create_entity({"name": "NN", "topic": "ml", "description": "old"})
        items = [
            {"doc_type": "entity", "name": "NN", "topic": "ml", "description": "new"}
        ]
        result = store.bulk_ingest(items)
        assert result["updated"] == 1

    def test_bulk_mixed_types(self, store):
        items = [
            {"doc_type": "entity", "name": "E1", "topic": "ml"},
            {"doc_type": "claim", "text": "A fact", "topic": "ml"},
            {"doc_type": "relationship", "source_id": "e1", "target_id": "e2", "type": "is_a", "topic": "ml"},
        ]
        result = store.bulk_ingest(items)
        assert result["created"] == 3

    def test_bulk_empty_list(self, store):
        result = store.bulk_ingest([])
        assert result["created"] == 0
        assert result["updated"] == 0


class TestTopicStats:
    """Test topic statistics."""

    def test_stats_for_populated_topic(self, store):
        store.create_entity({"name": "A", "topic": "ml", "confidence": 0.9})
        store.create_entity({"name": "B", "topic": "ml", "confidence": 0.8})
        store.claims["c1"] = {"id": "c1", "text": "X", "topic": "ml", "confidence": 0.7}
        store.relationships["r1"] = {"id": "r1", "topic": "ml"}
        stats = store.get_topic_stats("ml")
        assert stats["entity_count"] == 2
        assert stats["claim_count"] == 1
        assert stats["relationship_count"] == 1
        assert 0.7 <= stats["avg_confidence"] <= 0.9

    def test_stats_for_empty_topic(self, store):
        stats = store.get_topic_stats("empty")
        assert stats["entity_count"] == 0
        assert stats["avg_confidence"] == 0.0

    def test_stats_topic_isolation(self, store):
        store.create_entity({"name": "A", "topic": "ml"})
        store.create_entity({"name": "B", "topic": "bio"})
        ml_stats = store.get_topic_stats("ml")
        bio_stats = store.get_topic_stats("bio")
        assert ml_stats["entity_count"] == 1
        assert bio_stats["entity_count"] == 1


# ============================================================================
# FastAPI Endpoint Tests
# ============================================================================

import sys  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

# azure.monitor.opentelemetry is not in the test dependency set; pre-mock it
# so that `import knowledge.main` succeeds without the package installed.
sys.modules.setdefault("azure.monitor.opentelemetry", MagicMock())

import knowledge.main as _knowledge_mod  # noqa: E402
from knowledge.models import (  # noqa: E402
    BulkIngestResponse,
    Claim,
    DocType,
    Entity,
    KnowledgeUnit,
    Relationship,
    SearchResult,
    SearchResultItem,
    Source,
    TopicStats,
    TopicSummary,
)


# ── Test data helpers ─────────────────────────────────────────────────────


def _make_entity(**overrides) -> Entity:
    defaults: dict = {"name": "Neural Network", "topic": "ml"}
    defaults.update(overrides)
    return Entity(**defaults)


def _make_relationship(**overrides) -> Relationship:
    defaults: dict = {
        "source_entity_id": "e1",
        "target_entity_id": "e2",
        "relationship_type": "is_a",
        "topic": "ml",
    }
    defaults.update(overrides)
    return Relationship(**defaults)


def _make_claim(**overrides) -> Claim:
    defaults: dict = {
        "statement": "Neural networks are universal function approximators",
        "topic": "ml",
    }
    defaults.update(overrides)
    return Claim(**defaults)


def _make_source(**overrides) -> Source:
    defaults: dict = {"url": "https://example.com/paper", "topic": "ml"}
    defaults.update(overrides)
    return Source(**defaults)


# ============================================================================
# TestFastAPIEndpoints
# ============================================================================


class TestFastAPIEndpoints:
    """Tests for all 13 Knowledge Service FastAPI endpoints.

    Uses httpx.AsyncClient + ASGITransport against the real FastAPI app
    with module-level singletons (store, search, consumer) replaced by
    AsyncMocks — the same pattern as test_orchestrator.py / test_healer.py.
    """

    @pytest_asyncio.fixture
    async def client(self):
        """Swap module-level singletons for AsyncMocks; yield (client, store, search)."""
        orig_store = _knowledge_mod.store
        orig_search = _knowledge_mod.search
        orig_consumer = _knowledge_mod.consumer

        mock_store = AsyncMock()
        mock_search = AsyncMock()
        mock_consumer = AsyncMock()

        _knowledge_mod.store = mock_store
        _knowledge_mod.search = mock_search
        _knowledge_mod.consumer = mock_consumer

        transport = ASGITransport(app=_knowledge_mod.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, mock_store, mock_search

        _knowledge_mod.store = orig_store
        _knowledge_mod.search = orig_search
        _knowledge_mod.consumer = orig_consumer

    # ── 1. GET /health ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        c, _, _ = client
        resp = await c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "knowledge-service"

    # ── 2. POST /entities ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_upsert_entity_success(self, client):
        c, mock_store, mock_search = client
        entity = _make_entity()
        mock_store.upsert_entity.return_value = entity
        resp = await c.post("/entities", json={"name": "Neural Network", "topic": "ml"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Neural Network"
        assert data["topic"] == "ml"
        mock_store.upsert_entity.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_entity_search_failure_nonfatal(self, client):
        """Search indexing failures must not cause the entity upsert to fail."""
        c, mock_store, mock_search = client
        mock_store.upsert_entity.return_value = _make_entity()
        mock_search.ensure_index.side_effect = RuntimeError("Search unavailable")
        resp = await c.post("/entities", json={"name": "Neural Network", "topic": "ml"})
        assert resp.status_code == 201

    # ── 3. GET /entities/{id} ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_entity_success(self, client):
        c, mock_store, _ = client
        entity = _make_entity(id="entity-1")
        mock_store.get_entity.return_value = entity
        resp = await c.get("/entities/entity-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "entity-1"

    @pytest.mark.asyncio
    async def test_get_entity_not_found(self, client):
        c, mock_store, _ = client
        mock_store.get_entity.return_value = None
        resp = await c.get("/entities/nonexistent-id")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    # ── 4. GET /entities/search ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_search_entities_returns_list(self, client):
        c, mock_store, _ = client
        mock_store.search_entities.return_value = [_make_entity(name=f"E{i}") for i in range(3)]
        resp = await c.get("/entities/search")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    @pytest.mark.asyncio
    async def test_search_entities_with_filters(self, client):
        c, mock_store, _ = client
        mock_store.search_entities.return_value = [_make_entity()]
        resp = await c.get("/entities/search?topic=ml&q=neural&min_confidence=0.5")
        assert resp.status_code == 200
        kwargs = mock_store.search_entities.call_args.kwargs
        assert kwargs["topic"] == "ml"
        assert kwargs["query_text"] == "neural"
        assert kwargs["min_confidence"] == pytest.approx(0.5)

    # ── 5. POST /relationships ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_upsert_relationship_success(self, client):
        c, mock_store, _ = client
        rel = _make_relationship()
        mock_store.upsert_relationship.return_value = rel
        resp = await c.post(
            "/relationships",
            json={
                "source_entity_id": "e1",
                "target_entity_id": "e2",
                "relationship_type": "is_a",
                "topic": "ml",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["relationship_type"] == "is_a"
        mock_store.upsert_relationship.assert_called_once()

    # ── 6. GET /relationships ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_query_relationships_success(self, client):
        c, mock_store, _ = client
        mock_store.query_relationships.return_value = [_make_relationship(), _make_relationship()]
        resp = await c.get("/relationships?topic=ml")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_query_relationships_empty(self, client):
        c, mock_store, _ = client
        mock_store.query_relationships.return_value = []
        resp = await c.get("/relationships")
        assert resp.status_code == 200
        assert resp.json() == []

    # ── 7. POST /claims ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_upsert_claim_success(self, client):
        c, mock_store, mock_search = client
        claim = _make_claim()
        mock_store.upsert_claim.return_value = claim
        resp = await c.post(
            "/claims",
            json={
                "statement": "Neural networks are universal function approximators",
                "topic": "ml",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["statement"] == "Neural networks are universal function approximators"

    @pytest.mark.asyncio
    async def test_upsert_claim_search_failure_nonfatal(self, client):
        c, mock_store, mock_search = client
        mock_store.upsert_claim.return_value = _make_claim()
        mock_search.ensure_index.side_effect = RuntimeError("Search down")
        resp = await c.post("/claims", json={"statement": "A claim", "topic": "ml"})
        assert resp.status_code == 201

    # ── 8. GET /claims ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_query_claims_success(self, client):
        c, mock_store, _ = client
        mock_store.query_claims.return_value = [_make_claim(), _make_claim()]
        resp = await c.get("/claims?topic=ml")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_query_claims_with_filters(self, client):
        c, mock_store, _ = client
        mock_store.query_claims.return_value = []
        resp = await c.get("/claims?verified_only=true&min_confidence=0.8")
        assert resp.status_code == 200
        kwargs = mock_store.query_claims.call_args.kwargs
        assert kwargs["verified_only"] is True
        assert kwargs["min_confidence"] == pytest.approx(0.8)

    # ── 9. POST /sources ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_upsert_source_success(self, client):
        c, mock_store, _ = client
        mock_store.upsert_source.return_value = _make_source()
        resp = await c.post(
            "/sources",
            json={"url": "https://example.com/paper", "topic": "ml"},
        )
        assert resp.status_code == 201
        assert resp.json()["url"] == "https://example.com/paper"

    # ── 10. GET /search ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_hybrid_search_success(self, client):
        c, _, mock_search = client
        result = SearchResult(
            items=[
                SearchResultItem(
                    id="e1",
                    doc_type=DocType.ENTITY,
                    name="Neural Network",
                    topic="ml",
                    confidence=0.9,
                    score=0.85,
                )
            ],
            total_count=1,
        )
        mock_search.hybrid_search.return_value = result
        resp = await c.get("/search?q=neural+network&topic=ml")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["items"][0]["name"] == "Neural Network"

    @pytest.mark.asyncio
    async def test_hybrid_search_invalid_mode(self, client):
        c, _, _ = client
        resp = await c.get("/search?q=neural&mode=invalid")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_hybrid_search_all_modes(self, client):
        c, _, mock_search = client
        mock_search.hybrid_search.return_value = SearchResult(items=[], total_count=0)
        for mode in ("hybrid", "vector", "keyword"):
            resp = await c.get(f"/search?q=test&mode={mode}")
            assert resp.status_code == 200

    # ── 11. POST /bulk ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_bulk_ingest_success(self, client):
        c, mock_store, _ = client
        mock_store.bulk_ingest.return_value = BulkIngestResponse(
            entities_upserted=2, claims_upserted=1
        )
        payload = {
            "entities": [
                {"name": "Neural Network", "topic": "ml"},
                {"name": "Backpropagation", "topic": "ml"},
            ],
            "claims": [{"statement": "NNs are powerful", "topic": "ml"}],
        }
        resp = await c.post("/bulk", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["entities_upserted"] == 2
        assert data["claims_upserted"] == 1
        mock_store.bulk_ingest.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_ingest_empty_payload(self, client):
        c, mock_store, _ = client
        mock_store.bulk_ingest.return_value = BulkIngestResponse()
        resp = await c.post("/bulk", json={})
        assert resp.status_code == 201
        assert resp.json()["entities_upserted"] == 0

    @pytest.mark.asyncio
    async def test_bulk_ingest_search_failure_nonfatal(self, client):
        c, mock_store, mock_search = client
        mock_store.bulk_ingest.return_value = BulkIngestResponse(entities_upserted=1)
        mock_search.ensure_index.side_effect = RuntimeError("Search unavailable")
        resp = await c.post(
            "/bulk", json={"entities": [{"name": "Neural Network", "topic": "ml"}]}
        )
        assert resp.status_code == 201

    # ── 12. GET /topics/{topic}/stats ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_topic_stats_success(self, client):
        c, mock_store, _ = client
        mock_store.get_topic_stats.return_value = TopicStats(
            topic="ml",
            entity_count=10,
            relationship_count=5,
            claim_count=7,
            source_count=3,
            avg_confidence=0.85,
        )
        resp = await c.get("/topics/ml/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic"] == "ml"
        assert data["entity_count"] == 10
        assert data["claim_count"] == 7
        assert data["avg_confidence"] == pytest.approx(0.85)

    # ── 13. GET /topics/{topic}/summary ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_topic_summary_with_entities_and_claims(self, client):
        c, mock_store, _ = client
        mock_store.get_topic_summary.return_value = {
            "topic": "ml",
            "top_entities": [
                {"name": "Neural Network", "confidence": 0.95},
                {"name": "Backpropagation", "confidence": 0.92},
            ],
            "top_claims": [
                {"statement": "NNs approximate any function", "confidence": 0.9}
            ],
        }
        resp = await c.get("/topics/ml/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic"] == "ml"
        assert "Neural Network" in data["key_entities"]
        assert "NNs approximate any function" in data["key_claims"]
        assert data["confidence"] > 0

    @pytest.mark.asyncio
    async def test_topic_summary_empty_topic(self, client):
        c, mock_store, _ = client
        mock_store.get_topic_summary.return_value = {
            "topic": "empty",
            "top_entities": [],
            "top_claims": [],
        }
        resp = await c.get("/topics/empty/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic"] == "empty"
        assert data["key_entities"] == []
        assert data["key_claims"] == []
        assert data["confidence"] == pytest.approx(0.0)
