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
