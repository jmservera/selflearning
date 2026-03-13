"""Tests for the Extractor service.

These tests define expected behavioral contracts for the extractor service.
They use inline reference implementations that validate the specified
requirements. When the extractor service is implemented, update imports
to reference the actual service modules.
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# ============================================================================
# Reference implementations — behavioral contracts for the extractor
# ============================================================================


def chunk_document(
    text: str, chunk_size: int = 1000, overlap: int = 200
) -> list[dict[str, Any]]:
    """Split a document into overlapping chunks.

    Each chunk includes positional metadata for provenance tracking.
    """
    if not text.strip():
        return []

    chunks = []
    words = text.split()
    if not words:
        return []

    # Chunk by word count to avoid splitting mid-word
    start_word = 0
    chunk_idx = 0
    while start_word < len(words):
        end_word = min(start_word + chunk_size, len(words))
        chunk_text = " ".join(words[start_word:end_word])
        chunks.append({
            "id": f"chunk-{chunk_idx}",
            "text": chunk_text,
            "index": chunk_idx,
            "start_word": start_word,
            "end_word": end_word,
            "word_count": end_word - start_word,
        })
        chunk_idx += 1
        # Advance by chunk_size minus overlap
        advance = max(1, chunk_size - overlap)
        start_word += advance

    return chunks


def extract_entities_from_llm_response(
    raw_response: str, source_id: str, topic: str
) -> list[dict[str, Any]]:
    """Parse entity extraction results from an LLM response (JSON)."""
    try:
        text = raw_response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        items = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return []

    entities = []
    for item in items:
        if "name" not in item:
            continue
        entities.append({
            "name": item["name"],
            "type": item.get("type", "concept"),
            "description": item.get("description", ""),
            "confidence": min(1.0, max(0.0, item.get("confidence", 0.5))),
            "source_id": source_id,
            "topic": topic,
        })
    return entities


def extract_relationships_from_llm_response(
    raw_response: str, source_id: str, topic: str
) -> list[dict[str, Any]]:
    """Parse relationship extraction results from an LLM response."""
    try:
        text = raw_response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        items = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return []

    relationships = []
    for item in items:
        if "source" not in item or "target" not in item or "type" not in item:
            continue
        relationships.append({
            "source": item["source"],
            "target": item["target"],
            "type": item["type"],
            "description": item.get("description", ""),
            "confidence": min(1.0, max(0.0, item.get("confidence", 0.5))),
            "source_id": source_id,
            "topic": topic,
        })
    return relationships


def extract_claims_from_llm_response(
    raw_response: str, source_id: str, topic: str
) -> list[dict[str, Any]]:
    """Parse claim extraction results from an LLM response."""
    try:
        text = raw_response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        items = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return []

    claims = []
    for item in items:
        if "text" not in item:
            continue
        claims.append({
            "text": item["text"],
            "confidence": min(1.0, max(0.0, item.get("confidence", 0.5))),
            "entities": item.get("entities", []),
            "source_id": source_id,
            "topic": topic,
        })
    return claims


async def run_extraction_pipeline(
    text: str, source_id: str, topic: str, llm_complete
) -> dict[str, Any]:
    """Full extraction pipeline: chunk → extract → compile."""
    chunks = chunk_document(text, chunk_size=500, overlap=100)

    all_entities: list[dict] = []
    all_relationships: list[dict] = []
    all_claims: list[dict] = []

    for chunk in chunks:
        entity_resp = await llm_complete(
            f"Extract entities from: {chunk['text'][:200]}", "gpt-4o"
        )
        all_entities.extend(
            extract_entities_from_llm_response(entity_resp, source_id, topic)
        )

        rel_resp = await llm_complete(
            f"Extract relationships from: {chunk['text'][:200]}", "gpt-4o"
        )
        all_relationships.extend(
            extract_relationships_from_llm_response(rel_resp, source_id, topic)
        )

        claim_resp = await llm_complete(
            f"Extract claims from: {chunk['text'][:200]}", "gpt-4o"
        )
        all_claims.extend(
            extract_claims_from_llm_response(claim_resp, source_id, topic)
        )

    return {
        "source_id": source_id,
        "topic": topic,
        "chunks": len(chunks),
        "entities": all_entities,
        "relationships": all_relationships,
        "claims": all_claims,
    }


# ============================================================================
# Tests
# ============================================================================


class TestDocumentChunking:
    """Test document chunking with overlap."""

    def test_short_document_single_chunk(self):
        text = "This is a short document with only a few words."
        chunks = chunk_document(text, chunk_size=100, overlap=20)
        assert len(chunks) == 1
        assert chunks[0]["text"] == text

    def test_long_document_multiple_chunks(self):
        text = " ".join(["word"] * 500)
        chunks = chunk_document(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1

    def test_chunks_have_overlap(self):
        words = [f"word{i}" for i in range(300)]
        text = " ".join(words)
        chunks = chunk_document(text, chunk_size=100, overlap=30)
        if len(chunks) >= 2:
            first_end = chunks[0]["end_word"]
            second_start = chunks[1]["start_word"]
            assert second_start < first_end  # overlap exists

    def test_chunk_metadata_present(self):
        text = " ".join(["test"] * 50)
        chunks = chunk_document(text, chunk_size=100, overlap=20)
        chunk = chunks[0]
        assert "id" in chunk
        assert "index" in chunk
        assert "word_count" in chunk
        assert chunk["word_count"] == 50

    def test_empty_document_no_chunks(self):
        assert chunk_document("") == []
        assert chunk_document("   ") == []

    def test_all_words_covered(self):
        words = [f"w{i}" for i in range(250)]
        text = " ".join(words)
        chunks = chunk_document(text, chunk_size=100, overlap=20)
        # Every word should appear in at least one chunk
        all_chunk_words: set[str] = set()
        for c in chunks:
            all_chunk_words.update(c["text"].split())
        for w in words:
            assert w in all_chunk_words

    def test_chunk_indices_sequential(self):
        text = " ".join(["word"] * 500)
        chunks = chunk_document(text, chunk_size=100, overlap=20)
        for i, chunk in enumerate(chunks):
            assert chunk["index"] == i

    def test_single_word_document(self):
        chunks = chunk_document("hello", chunk_size=100, overlap=20)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "hello"


class TestEntityExtraction:
    """Test entity extraction from LLM responses."""

    def test_parse_valid_entities(self):
        response = json.dumps([
            {"name": "Neural Network", "type": "concept", "description": "A model", "confidence": 0.95},
            {"name": "Geoffrey Hinton", "type": "person", "description": "Researcher", "confidence": 0.98},
        ])
        entities = extract_entities_from_llm_response(response, "s1", "ml")
        assert len(entities) == 2
        assert entities[0]["name"] == "Neural Network"
        assert entities[1]["type"] == "person"

    def test_entities_have_provenance(self):
        response = json.dumps([{"name": "X", "type": "concept"}])
        entities = extract_entities_from_llm_response(response, "source-1", "topic-1")
        assert entities[0]["source_id"] == "source-1"
        assert entities[0]["topic"] == "topic-1"

    def test_malformed_json_returns_empty(self):
        assert extract_entities_from_llm_response("not json", "s", "t") == []

    def test_missing_name_skipped(self):
        response = json.dumps([
            {"name": "Valid", "type": "concept"},
            {"type": "concept", "description": "no name"},
        ])
        entities = extract_entities_from_llm_response(response, "s", "t")
        assert len(entities) == 1

    def test_confidence_clamped(self):
        response = json.dumps([{"name": "X", "confidence": 1.5}])
        entities = extract_entities_from_llm_response(response, "s", "t")
        assert entities[0]["confidence"] <= 1.0

        response2 = json.dumps([{"name": "Y", "confidence": -0.5}])
        entities2 = extract_entities_from_llm_response(response2, "s", "t")
        assert entities2[0]["confidence"] >= 0.0

    def test_markdown_code_fence_stripped(self):
        response = '```json\n[{"name": "X", "type": "concept"}]\n```'
        entities = extract_entities_from_llm_response(response, "s", "t")
        assert len(entities) == 1

    def test_default_type_is_concept(self):
        response = json.dumps([{"name": "Something"}])
        entities = extract_entities_from_llm_response(response, "s", "t")
        assert entities[0]["type"] == "concept"


class TestRelationshipExtraction:
    """Test relationship extraction from LLM responses."""

    def test_parse_valid_relationships(self):
        response = json.dumps([
            {"source": "A", "target": "B", "type": "related_to", "confidence": 0.8},
        ])
        rels = extract_relationships_from_llm_response(response, "s1", "t1")
        assert len(rels) == 1
        assert rels[0]["source"] == "A"
        assert rels[0]["target"] == "B"

    def test_incomplete_relationship_skipped(self):
        response = json.dumps([
            {"source": "A", "type": "related_to"},  # missing target
            {"source": "A", "target": "B", "type": "is_a"},
        ])
        rels = extract_relationships_from_llm_response(response, "s", "t")
        assert len(rels) == 1

    def test_malformed_json_returns_empty(self):
        assert extract_relationships_from_llm_response("{bad", "s", "t") == []

    def test_relationships_have_provenance(self):
        response = json.dumps([
            {"source": "A", "target": "B", "type": "is_a"}
        ])
        rels = extract_relationships_from_llm_response(response, "src-1", "topic-1")
        assert rels[0]["source_id"] == "src-1"


class TestClaimExtraction:
    """Test claim extraction from LLM responses."""

    def test_parse_valid_claims(self):
        response = json.dumps([
            {"text": "Neural networks can approximate any function", "confidence": 0.92},
            {"text": "Deep learning requires large datasets", "confidence": 0.75},
        ])
        claims = extract_claims_from_llm_response(response, "s1", "ml")
        assert len(claims) == 2
        assert claims[0]["confidence"] == 0.92

    def test_claims_have_entity_references(self):
        response = json.dumps([
            {"text": "X is related to Y", "confidence": 0.8, "entities": ["X", "Y"]},
        ])
        claims = extract_claims_from_llm_response(response, "s", "t")
        assert claims[0]["entities"] == ["X", "Y"]

    def test_missing_text_skipped(self):
        response = json.dumps([
            {"text": "valid claim", "confidence": 0.9},
            {"confidence": 0.5},  # no text
        ])
        claims = extract_claims_from_llm_response(response, "s", "t")
        assert len(claims) == 1

    def test_malformed_json_returns_empty(self):
        assert extract_claims_from_llm_response("nope", "s", "t") == []


class TestFullExtractionPipeline:
    """Test the complete extraction pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_processes_all_chunks(self):
        text = " ".join(["knowledge"] * 200)
        call_count = 0

        async def mock_llm(prompt: str, model: str) -> str:
            nonlocal call_count
            call_count += 1
            if "entities" in prompt.lower() or "Extract entities" in prompt:
                return json.dumps([{"name": f"Entity{call_count}", "type": "concept"}])
            elif "relationships" in prompt.lower() or "Extract relationships" in prompt:
                return json.dumps([])
            elif "claims" in prompt.lower() or "Extract claims" in prompt:
                return json.dumps([{"text": "A claim", "confidence": 0.8}])
            return "[]"

        result = await run_extraction_pipeline(text, "src-1", "ml", mock_llm)
        assert result["chunks"] > 0
        assert len(result["entities"]) > 0
        assert result["source_id"] == "src-1"

    @pytest.mark.asyncio
    async def test_pipeline_handles_llm_failure(self):
        text = " ".join(["data"] * 100)

        async def failing_llm(prompt: str, model: str) -> str:
            return "not valid json"

        result = await run_extraction_pipeline(text, "src-1", "ml", failing_llm)
        assert result["entities"] == []
        assert result["relationships"] == []
        assert result["claims"] == []

    @pytest.mark.asyncio
    async def test_pipeline_empty_document(self):
        async def mock_llm(prompt: str, model: str) -> str:
            return "[]"

        result = await run_extraction_pipeline("", "src-1", "ml", mock_llm)
        assert result["chunks"] == 0
        assert result["entities"] == []


# ============================================================================
# FastAPI endpoint tests
# ============================================================================

_EXTRACTOR_BARE_MODULES = frozenset({
    "main", "config", "models", "blob_storage", "extraction", "llm_client", "service_bus",
})


def _setup_extractor_path() -> None:
    """Flush stale bare-module caches and add src/extractor/ to sys.path.

    Other service directories are removed to prevent cross-contamination
    when running the full test suite.
    """
    src_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src"))
    svc_dir = os.path.normpath(os.path.join(src_dir, "extractor"))
    # Remove all service directories to avoid cross-contamination
    other_svcs = {os.path.normpath(os.path.join(src_dir, s))
                  for s in ("scraper", "orchestrator", "healer", "reasoner")}
    for name in _EXTRACTOR_BARE_MODULES:
        sys.modules.pop(name, None)
    sys.path[:] = [p for p in sys.path
                   if os.path.normpath(p) not in other_svcs
                   and os.path.normpath(p) != svc_dir]
    src_positions = [i for i, p in enumerate(sys.path) if os.path.normpath(p) == src_dir]
    insert_pos = src_positions[0] if src_positions else 0
    sys.path.insert(insert_pos, svc_dir)


class TestEndpoints:
    """Tests for extractor FastAPI endpoints (/health, /status)."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked module-level globals."""
        saved_path = sys.path[:]
        _setup_extractor_path()
        import main as extractor_mod  # noqa: PLC0415

        mock_llm = MagicMock()
        mock_blob = MagicMock()
        mock_service_bus = MagicMock()
        mock_pipeline = MagicMock()

        extractor_mod.llm_client = mock_llm
        extractor_mod.blob_client = mock_blob
        extractor_mod.service_bus = mock_service_bus
        extractor_mod.pipeline = mock_pipeline
        extractor_mod._consumer_task = None
        extractor_mod._started_at = datetime.now(timezone.utc)

        transport = ASGITransport(app=extractor_mod.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, extractor_mod, mock_llm, mock_blob, mock_service_bus, mock_pipeline

        extractor_mod.llm_client = None
        extractor_mod.blob_client = None
        extractor_mod.service_bus = None
        extractor_mod.pipeline = None
        extractor_mod._started_at = None
        for name in _EXTRACTOR_BARE_MODULES:
            sys.modules.pop(name, None)
        sys.path[:] = saved_path

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        c, _, _, _, _, _ = client
        resp = await c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "extractor"

    @pytest.mark.asyncio
    async def test_status_healthy(self, client):
        c, _, _, _, _, _ = client
        resp = await c.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "extractor"
        assert data["components"]["llm_client"] == "connected"
        assert data["components"]["blob_storage"] == "connected"
        assert data["components"]["service_bus"] == "connected"
        assert data["components"]["pipeline"] == "ready"
        assert data["started_at"] is not None
        assert data["consumer_running"] is False

    @pytest.mark.asyncio
    async def test_status_degraded_llm_and_blob(self, client):
        c, extractor_mod, _, _, _, _ = client
        extractor_mod.llm_client = None
        extractor_mod.blob_client = None
        resp = await c.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["llm_client"] == "not_initialized"
        assert data["components"]["blob_storage"] == "not_initialized"

    @pytest.mark.asyncio
    async def test_status_degraded_service_bus_and_pipeline(self, client):
        c, extractor_mod, _, _, _, _ = client
        extractor_mod.service_bus = None
        extractor_mod.pipeline = None
        resp = await c.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["service_bus"] == "not_initialized"
        assert data["components"]["pipeline"] == "not_initialized"
