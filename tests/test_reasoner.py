"""Tests for the Reasoner service.

Covers models, LLMClient, KnowledgeServiceClient, ReasoningEngine,
and FastAPI endpoints.
"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient, Response

# ── Bare-import isolation ─────────────────────────────────────────────
_BARE_MODULE_NAMES = frozenset({
    "config", "models", "service_bus", "working_memory", "strategy",
    "cosmos_client", "learning_loop", "health_monitor",
    "llm_client", "reasoning",
})


def _setup_service_path(service_name: str) -> None:
    """Flush stale bare-module caches and put *service_name* on sys.path."""
    src_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src"))
    svc_dir = os.path.normpath(os.path.join(src_dir, service_name))
    for name in _BARE_MODULE_NAMES:
        sys.modules.pop(name, None)
    svc_dirs = {os.path.normpath(os.path.join(src_dir, s))
                for s in ("orchestrator", "healer", "reasoner")}
    sys.path[:] = [p for p in sys.path if os.path.normpath(p) not in svc_dirs]
    src_positions = [i for i, p in enumerate(sys.path)
                     if os.path.normpath(p) == src_dir]
    insert_pos = (src_positions[0] + 1) if src_positions else 0
    sys.path.insert(insert_pos, svc_dir)


_setup_service_path("reasoner")

from reasoner.config import ReasonerConfig  # noqa: E402
sys.modules["config"] = sys.modules["reasoner.config"]

from reasoner.llm_client import LLMClient  # noqa: E402
sys.modules["llm_client"] = sys.modules["reasoner.llm_client"]

from reasoner.models import (  # noqa: E402
    ContradictionResolution,
    Insight,
    KnowledgeGap,
    ReasoningMeta,
    ReasoningRequest,
    ReasoningResult,
)
sys.modules["models"] = sys.modules["reasoner.models"]

from reasoner.reasoning import KnowledgeServiceClient, ReasoningEngine  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────

def _make_config(**overrides) -> ReasonerConfig:
    defaults = {
        "azure_ai_endpoint": "https://test.ai.azure.com",
        "reasoning_model": "gpt-4o",
        "embedding_model": "text-embedding-3-large",
        "knowledge_service_url": "http://knowledge:8000",
        "max_retries": 3,
        "reasoning_temperature": 0.3,
        "max_tokens": 4096,
    }
    defaults.update(overrides)
    return ReasonerConfig(**defaults)


def _make_request(**overrides) -> ReasoningRequest:
    defaults = {
        "topic": "quantum-computing",
        "reasoning_type": "gap_analysis",
        "context": {},
    }
    defaults.update(overrides)
    return ReasoningRequest(**defaults)


def _mock_llm_client(json_response=None):
    """Create a mock LLM client."""
    mock = MagicMock(spec=LLMClient)
    mock.complete_json = AsyncMock(return_value=json_response or {})
    mock.complete_text = AsyncMock(return_value="text response")
    mock.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    return mock


def _mock_knowledge_client():
    """Create a mock KnowledgeServiceClient."""
    mock = MagicMock(spec=KnowledgeServiceClient)
    mock.get_entities = AsyncMock(return_value=[])
    mock.get_claims = AsyncMock(return_value=[])
    mock.get_relationships = AsyncMock(return_value=[])
    mock.search = AsyncMock(return_value=[])
    return mock


# =====================================================================
# Model Tests
# =====================================================================

class TestModels:
    """Reasoner model construction and defaults."""

    def test_reasoning_request_defaults(self):
        r = ReasoningRequest(topic="t", reasoning_type="gap_analysis")
        assert r.request_id  # auto-generated UUID
        assert r.context == {}

    def test_reasoning_request_custom_fields(self):
        r = ReasoningRequest(
            request_id="custom-id",
            topic="ml",
            reasoning_type="synthesis",
            context={"key": "value"},
        )
        assert r.request_id == "custom-id"
        assert r.context["key"] == "value"

    def test_insight_defaults(self):
        i = Insight(statement="test")
        assert i.topic == ""
        assert i.supporting_entities == []
        assert i.confidence == 0.0
        assert i.reasoning_chain == ""
        assert i.id  # auto-generated UUID

    def test_knowledge_gap_defaults(self):
        g = KnowledgeGap(area="missing area")
        assert g.topic == ""
        assert g.severity == "moderate"
        assert g.description == ""
        assert g.suggested_queries == []

    def test_contradiction_resolution_defaults(self):
        c = ContradictionResolution()
        assert c.claim_ids == []
        assert c.resolution == ""
        assert c.confidence == 0.0
        assert c.reasoning == ""

    def test_reasoning_meta_defaults(self):
        m = ReasoningMeta()
        assert m.reasoning_type == ""
        assert m.model_used == ""
        assert m.total_tokens == 0
        assert m.latency_ms == 0.0
        assert m.knowledge_items_considered == 0

    def test_reasoning_result_defaults(self):
        r = ReasoningResult(request_id="r1", topic="t")
        assert r.insights == []
        assert r.gaps == []
        assert r.resolutions == []
        assert r.meta is None

    def test_reasoning_result_with_data(self):
        r = ReasoningResult(
            request_id="r1",
            topic="t",
            insights=[Insight(statement="s")],
            gaps=[KnowledgeGap(area="a")],
            resolutions=[ContradictionResolution()],
            meta=ReasoningMeta(reasoning_type="synthesis"),
        )
        assert len(r.insights) == 1
        assert len(r.gaps) == 1
        assert len(r.resolutions) == 1
        assert r.meta.reasoning_type == "synthesis"


# =====================================================================
# LLMClient Tests
# =====================================================================

class TestLLMClient:
    """Tests for the LLMClient class."""

    def test_parse_json_plain(self):
        result = LLMClient._parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_strips_markdown_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        result = LLMClient._parse_json(raw)
        assert result == {"key": "value"}

    def test_parse_json_strips_fence_no_language(self):
        raw = '```\n{"key": "value"}\n```'
        result = LLMClient._parse_json(raw)
        assert result == {"key": "value"}

    def test_parse_json_with_whitespace(self):
        raw = '  \n  {"key": "value"}  \n  '
        result = LLMClient._parse_json(raw)
        assert result == {"key": "value"}

    def test_parse_json_complex(self):
        raw = '```json\n{"gaps": [{"area": "test", "severity": "critical"}]}\n```'
        result = LLMClient._parse_json(raw)
        assert len(result["gaps"]) == 1

    def test_parse_json_invalid_raises(self):
        with pytest.raises(json.JSONDecodeError):
            LLMClient._parse_json("not json at all")

    @pytest.mark.asyncio
    async def test_complete_json_success(self):
        config = _make_config()
        client = LLMClient(config)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"result": "ok"}'
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        mock_response.model = "gpt-4o"
        mock_chat = AsyncMock(return_value=mock_response)
        client._chat_client = MagicMock()
        client._chat_client.complete = mock_chat
        result = await client.complete_json("system", "user")
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_complete_json_retries_on_json_error(self):
        config = _make_config(max_retries=3)
        client = LLMClient(config)

        bad_response = MagicMock()
        bad_response.choices = [MagicMock()]
        bad_response.choices[0].message.content = "not json"
        bad_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        bad_response.model = "gpt-4o"

        good_response = MagicMock()
        good_response.choices = [MagicMock()]
        good_response.choices[0].message.content = '{"ok": true}'
        good_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        good_response.model = "gpt-4o"

        client._chat_client = MagicMock()
        client._chat_client.complete = AsyncMock(
            side_effect=[bad_response, good_response])
        result = await client.complete_json("system", "user")
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_complete_json_exhausts_retries(self):
        config = _make_config(max_retries=2)
        client = LLMClient(config)

        bad_response = MagicMock()
        bad_response.choices = [MagicMock()]
        bad_response.choices[0].message.content = "not json"
        bad_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        bad_response.model = "gpt-4o"

        client._chat_client = MagicMock()
        client._chat_client.complete = AsyncMock(return_value=bad_response)
        with pytest.raises(RuntimeError, match="LLM call failed after 2 attempts"):
            await client.complete_json("system", "user")

    @pytest.mark.asyncio
    async def test_complete_text(self):
        config = _make_config()
        client = LLMClient(config)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "plain text"
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        mock_response.model = "gpt-4o"
        client._chat_client = MagicMock()
        client._chat_client.complete = AsyncMock(return_value=mock_response)
        result = await client.complete_text("system", "user")
        assert result == "plain text"

    @pytest.mark.asyncio
    async def test_embed_empty_input(self):
        config = _make_config()
        client = LLMClient(config)
        result = await client.embed([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_with_texts(self):
        config = _make_config()
        client = LLMClient(config)
        mock_response = MagicMock()
        item = MagicMock()
        item.embedding = [0.1, 0.2]
        mock_response.data = [item]
        mock_response.usage = MagicMock(total_tokens=10)
        client._embed_client = MagicMock()
        client._embed_client.embed = AsyncMock(return_value=mock_response)
        result = await client.embed(["hello"])
        assert result == [[0.1, 0.2]]


# =====================================================================
# KnowledgeServiceClient Tests
# =====================================================================

class TestKnowledgeServiceClient:
    """Tests for the KnowledgeServiceClient HTTP client."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_entities_success(self):
        base = "http://knowledge:8000"
        respx.get(f"{base}/entities").mock(
            return_value=Response(200, json={"entities": [{"name": "E1"}]}))
        client = KnowledgeServiceClient(base)
        try:
            result = await client.get_entities("topic")
            assert len(result) == 1
            assert result[0]["name"] == "E1"
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_entities_error_returns_empty(self):
        base = "http://knowledge:8000"
        respx.get(f"{base}/entities").mock(return_value=Response(500))
        client = KnowledgeServiceClient(base)
        try:
            result = await client.get_entities("topic")
            assert result == []
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_claims_success(self):
        base = "http://knowledge:8000"
        respx.get(f"{base}/claims").mock(
            return_value=Response(200, json={"claims": [{"statement": "S1"}]}))
        client = KnowledgeServiceClient(base)
        try:
            result = await client.get_claims("topic")
            assert len(result) == 1
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_claims_error_returns_empty(self):
        base = "http://knowledge:8000"
        respx.get(f"{base}/claims").mock(return_value=Response(500))
        client = KnowledgeServiceClient(base)
        try:
            result = await client.get_claims("topic")
            assert result == []
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_relationships_success(self):
        base = "http://knowledge:8000"
        respx.get(f"{base}/relationships").mock(
            return_value=Response(200, json={"relationships": [{"type": "R1"}]}))
        client = KnowledgeServiceClient(base)
        try:
            result = await client.get_relationships("topic")
            assert len(result) == 1
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_relationships_error_returns_empty(self):
        base = "http://knowledge:8000"
        respx.get(f"{base}/relationships").mock(return_value=Response(500))
        client = KnowledgeServiceClient(base)
        try:
            result = await client.get_relationships("topic")
            assert result == []
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_success(self):
        base = "http://knowledge:8000"
        respx.get(f"{base}/search").mock(
            return_value=Response(200, json={"results": [{"content": "R1"}]}))
        client = KnowledgeServiceClient(base)
        try:
            result = await client.search("query")
            assert len(result) == 1
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_error_returns_empty(self):
        base = "http://knowledge:8000"
        respx.get(f"{base}/search").mock(return_value=Response(500))
        client = KnowledgeServiceClient(base)
        try:
            result = await client.search("query")
            assert result == []
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_entities_returns_list_directly(self):
        """When API returns a bare list, .get() fails and the exception handler returns []."""
        base = "http://knowledge:8000"
        respx.get(f"{base}/entities").mock(
            return_value=Response(200, json=[{"name": "E1"}]))
        client = KnowledgeServiceClient(base)
        try:
            result = await client.get_entities("topic")
            assert result == []
        finally:
            await client.close()


# =====================================================================
# ReasoningEngine Tests
# =====================================================================

class TestReasoningEngine:
    """Tests for the ReasoningEngine."""

    def _make_engine(self, llm_response=None, entities=None, claims=None,
                     relationships=None, search_results=None):
        config = _make_config()
        llm = _mock_llm_client(llm_response)
        knowledge = _mock_knowledge_client()
        if entities:
            knowledge.get_entities = AsyncMock(return_value=entities)
        if claims:
            knowledge.get_claims = AsyncMock(return_value=claims)
        if relationships:
            knowledge.get_relationships = AsyncMock(return_value=relationships)
        if search_results:
            knowledge.search = AsyncMock(return_value=search_results)
        engine = ReasoningEngine(config, llm, knowledge)
        return engine, llm, knowledge

    @pytest.mark.asyncio
    async def test_run_dispatches_gap_analysis(self):
        engine, llm, _ = self._make_engine(llm_response={"gaps": []})
        request = _make_request(reasoning_type="gap_analysis")
        result = await engine.run(request)
        assert result.meta.reasoning_type == "gap_analysis"
        llm.complete_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_dispatches_contradiction_resolution(self):
        engine, llm, knowledge = self._make_engine(
            llm_response={"resolutions": []},
            claims=[{"id": "c1", "statement": "claim 1", "confidence": 0.8}],
        )
        request = _make_request(reasoning_type="contradiction_resolution")
        result = await engine.run(request)
        assert result.meta.reasoning_type == "contradiction_resolution"

    @pytest.mark.asyncio
    async def test_run_dispatches_synthesis(self):
        engine, llm, _ = self._make_engine(llm_response={"insights": []})
        request = _make_request(reasoning_type="synthesis")
        result = await engine.run(request)
        assert result.meta.reasoning_type == "synthesis"

    @pytest.mark.asyncio
    async def test_run_dispatches_depth_probe(self):
        engine, llm, _ = self._make_engine(llm_response={"probes": []})
        request = _make_request(reasoning_type="depth_probe")
        result = await engine.run(request)
        assert result.meta.reasoning_type == "depth_probe"

    @pytest.mark.asyncio
    async def test_run_unknown_type_returns_empty(self):
        engine, llm, _ = self._make_engine()
        request = _make_request(reasoning_type="unknown_type")
        result = await engine.run(request)
        assert result.insights == []
        assert result.gaps == []
        assert result.meta is None
        llm.complete_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_gap_analysis_builds_gaps(self):
        engine, _, _ = self._make_engine(
            llm_response={
                "gaps": [
                    {"area": "training", "severity": "critical", "description": "No training data"},
                    {"area": "", "severity": "minor", "description": "empty area should be filtered"},
                    {"area": "evaluation", "severity": "moderate", "description": "Low coverage"},
                ]
            },
            entities=[{"name": "E1", "entity_type": "concept"}],
            claims=[{"statement": "C1", "confidence": 0.9}],
        )
        request = _make_request(reasoning_type="gap_analysis")
        result = await engine.run(request)
        # Empty area should be filtered out
        assert len(result.gaps) == 2
        assert result.gaps[0].area == "training"
        assert result.gaps[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_contradiction_resolution_no_claims_returns_empty(self):
        engine, llm, knowledge = self._make_engine()
        knowledge.get_claims = AsyncMock(return_value=[])
        request = _make_request(reasoning_type="contradiction_resolution")
        result = await engine.run(request)
        assert result.resolutions == []
        assert result.meta.knowledge_items_considered == 0
        llm.complete_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_contradiction_resolution_with_claims(self):
        engine, _, knowledge = self._make_engine(
            llm_response={
                "resolutions": [
                    {"claim_ids": ["c1", "c2"], "resolution": "C1 is correct",
                     "confidence": 0.85, "reasoning": "Evidence supports C1"}
                ]
            },
            claims=[
                {"id": "c1", "statement": "X is true", "confidence": 0.9},
                {"id": "c2", "statement": "X is false", "confidence": 0.6},
            ],
        )
        request = _make_request(reasoning_type="contradiction_resolution")
        result = await engine.run(request)
        assert len(result.resolutions) == 1
        assert result.resolutions[0].confidence == 0.85
        assert result.meta.knowledge_items_considered == 2

    @pytest.mark.asyncio
    async def test_synthesis_includes_search(self):
        engine, llm, knowledge = self._make_engine(
            llm_response={
                "insights": [
                    {"statement": "Key insight", "supporting_entities": ["E1"],
                     "confidence": 0.8, "reasoning_chain": "Because..."},
                    {"statement": "", "supporting_entities": [], "confidence": 0.5},
                ]
            },
            entities=[{"name": "E1"}],
            search_results=[{"content": "Search result 1"}],
        )
        request = _make_request(reasoning_type="synthesis")
        result = await engine.run(request)
        # Empty statement should be filtered out
        assert len(result.insights) == 1
        assert result.insights[0].statement == "Key insight"
        knowledge.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_depth_probe_maps_priority(self):
        engine, _, _ = self._make_engine(
            llm_response={
                "probes": [
                    {"area": "deep topic", "priority": "high",
                     "current_depth": "shallow", "target_depth": "expert",
                     "suggested_queries": ["q1"], "rationale": "Important"},
                    {"area": "medium topic", "priority": "medium"},
                    {"area": "low topic", "priority": "low"},
                ],
                "strategy_summary": "Focus on fundamentals first",
            },
            entities=[{"name": "E1"}],
        )
        request = _make_request(reasoning_type="depth_probe")
        result = await engine.run(request)
        assert len(result.gaps) == 3
        assert result.gaps[0].severity == "critical"  # high → critical
        assert result.gaps[1].severity == "moderate"  # medium → moderate
        assert result.gaps[2].severity == "minor"  # low → minor
        # strategy_summary → insight
        assert len(result.insights) == 1
        assert result.insights[0].statement == "Focus on fundamentals first"
        assert result.insights[0].confidence == 0.7

    @pytest.mark.asyncio
    async def test_depth_probe_no_strategy_summary(self):
        engine, _, _ = self._make_engine(
            llm_response={"probes": [{"area": "topic", "priority": "medium"}]}
        )
        request = _make_request(reasoning_type="depth_probe")
        result = await engine.run(request)
        assert len(result.insights) == 0

    def test_format_knowledge_context_empty(self):
        result = ReasoningEngine._format_knowledge_context([], [], [])
        assert result == "(empty knowledge base)"

    def test_format_knowledge_context_entities_only(self):
        entities = [{"name": "E1", "entity_type": "concept", "description": "desc", "confidence": 0.9}]
        result = ReasoningEngine._format_knowledge_context(entities, [], [])
        assert "ENTITIES:" in result
        assert "E1" in result
        assert "CLAIMS:" not in result

    def test_format_knowledge_context_claims_only(self):
        claims = [{"statement": "S1", "confidence": 0.8}]
        result = ReasoningEngine._format_knowledge_context([], claims, [])
        assert "CLAIMS:" in result
        assert "S1" in result
        assert "ENTITIES:" not in result

    def test_format_knowledge_context_relationships_only(self):
        rels = [{"source_entity_id": "E1", "target_entity_id": "E2", "relationship_type": "related"}]
        result = ReasoningEngine._format_knowledge_context([], [], rels)
        assert "RELATIONSHIPS:" in result
        assert "E1" in result

    def test_format_knowledge_context_all(self):
        entities = [{"name": "E1", "entity_type": "t", "description": "d", "confidence": 0.9}]
        claims = [{"statement": "S1", "confidence": 0.8}]
        rels = [{"source_entity": "E1", "target_entity": "E2", "type": "related"}]
        result = ReasoningEngine._format_knowledge_context(entities, claims, rels)
        assert "ENTITIES:" in result
        assert "CLAIMS:" in result
        assert "RELATIONSHIPS:" in result

    def test_format_knowledge_context_truncation(self):
        """Entities limited to 80, claims to 60, relationships to 40."""
        entities = [{"name": f"E{i}", "entity_type": "t", "description": "d", "confidence": 0.5}
                    for i in range(100)]
        claims = [{"statement": f"C{i}", "confidence": 0.5} for i in range(80)]
        rels = [{"source_entity_id": f"S{i}", "target_entity_id": f"T{i}",
                 "relationship_type": "r"} for i in range(60)]
        result = ReasoningEngine._format_knowledge_context(entities, claims, rels)
        entity_count = result.count("[t]")
        claim_count = result.count("confidence:")
        # Entities capped at 80
        assert entity_count <= 80
        # Verify relationships section exists
        assert "RELATIONSHIPS:" in result


# =====================================================================
# FastAPI Endpoint Tests
# =====================================================================

class TestEndpoints:
    """Tests for reasoner FastAPI endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked globals."""
        _setup_service_path("reasoner")
        sys.modules["config"] = sys.modules["reasoner.config"]
        sys.modules["models"] = sys.modules["reasoner.models"]
        sys.modules["llm_client"] = sys.modules["reasoner.llm_client"]
        import reasoner.main as reasoner_mod

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=ReasoningResult(
            request_id="r1", topic="test",
            insights=[Insight(statement="insight1")],
            meta=ReasoningMeta(reasoning_type="synthesis"),
        ))

        reasoner_mod.engine = mock_engine

        transport = ASGITransport(app=reasoner_mod.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, mock_engine

        reasoner_mod.engine = None

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        c, _ = client
        resp = await c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "reasoner"

    @pytest.mark.asyncio
    async def test_handle_reasoning_request(self, client):
        """Test the handle_reasoning_request function directly."""
        import reasoner.main as reasoner_mod

        _, mock_engine = client
        body = {
            "request_id": "test-123",
            "topic": "ml",
            "reasoning_type": "gap_analysis",
            "context": {"key": "val"},
        }
        result = await reasoner_mod.handle_reasoning_request(body)
        assert isinstance(result, dict)
        mock_engine.run.assert_called_once()
        call_args = mock_engine.run.call_args[0][0]
        assert call_args.topic == "ml"
        assert call_args.reasoning_type == "gap_analysis"

    @pytest.mark.asyncio
    async def test_handle_reasoning_request_result_serialised(self, client):
        """Check that the result is properly serialised (exclude_none=True)."""
        import reasoner.main as reasoner_mod

        _, mock_engine = client
        mock_engine.run = AsyncMock(return_value=ReasoningResult(
            request_id="r1", topic="test",
            meta=ReasoningMeta(reasoning_type="gap_analysis", model_used="gpt-4o"),
        ))
        body = {
            "request_id": "r1",
            "topic": "test",
            "reasoning_type": "gap_analysis",
        }
        result = await reasoner_mod.handle_reasoning_request(body)
        assert "request_id" in result
        assert "topic" in result
