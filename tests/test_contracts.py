"""Contract validation tests for the 4 inter-service boundaries.

Each class validates that messages produced by the *sender* service can be
deserialised by the *receiver* service without any manual field mapping.
This covers the four contract mismatches identified in the architecture audit:

  1. Orchestrator → Scraper   (ScrapeRequest wire format)
  2. Extractor   → Knowledge  (extraction-complete payload shape)
  3. Reasoner    → Knowledge  (KnowledgeServiceClient HTTP API calls)
  4. Evaluator   → Orchestrator (evaluation-complete event schema)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import pytest
import respx
from httpx import Response

# ---------------------------------------------------------------------------
# Ensure src/ packages are importable
# ---------------------------------------------------------------------------
_SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# ---------------------------------------------------------------------------
# Service models — pure Pydantic models, no bare-import conflicts
# ---------------------------------------------------------------------------
from orchestrator.models import (  # noqa: E402
    EvaluationResult,
    ScrapeRequest as OrchestratorScrapeRequest,
    SourceType as OrchestratorSourceType,
)
from scraper.models import (  # noqa: E402
    Priority as ScraperPriority,
    ScrapeRequest as ScraperScrapeRequest,
    SourceType as ScraperSourceType,
)
from knowledge.models import (  # noqa: E402
    Entity,
    EntityType,
    KnowledgeUnit,
    Relationship,
)

# ---------------------------------------------------------------------------
# Reasoner: requires bare-module path setup before importing reasoning.py
# (reasoning.py does `from config import ReasonerConfig`)
# ---------------------------------------------------------------------------
_BARE_MODULE_NAMES = frozenset({
    "config", "models", "service_bus", "working_memory", "strategy",
    "cosmos_client", "learning_loop", "health_monitor",
    "llm_client", "reasoning",
})


def _setup_reasoner_path() -> None:
    svc_dir = os.path.normpath(os.path.join(_SRC, "reasoner"))
    for name in _BARE_MODULE_NAMES:
        sys.modules.pop(name, None)
    # Remove any other service directories that may conflict
    svc_dirs = {
        os.path.normpath(os.path.join(_SRC, s))
        for s in ("orchestrator", "healer", "reasoner")
    }
    sys.path[:] = [p for p in sys.path if os.path.normpath(p) not in svc_dirs]
    src_positions = [i for i, p in enumerate(sys.path)
                     if os.path.normpath(p) == _SRC]
    insert_pos = (src_positions[0] + 1) if src_positions else 0
    sys.path.insert(insert_pos, svc_dir)


_setup_reasoner_path()

import reasoner.config  # noqa: E402
sys.modules["config"] = sys.modules["reasoner.config"]
import reasoner.llm_client  # noqa: E402
sys.modules["llm_client"] = sys.modules["reasoner.llm_client"]
import reasoner.models  # noqa: E402
sys.modules["models"] = sys.modules["reasoner.models"]

from reasoner.reasoning import KnowledgeServiceClient  # noqa: E402


# ===========================================================================
# Boundary 1: Orchestrator → Scraper (scrape-requests queue)
# ===========================================================================


@pytest.mark.integration
class TestContractBoundary1_OrchestratorScraper:
    """Contract: Orchestrator → Scraper (scrape-requests queue).

    The Orchestrator serialises an OrchestratorScrapeRequest. The Scraper
    deserialises the raw JSON as a ScraperScrapeRequest. Both must agree on
    the wire format without any manual field mapping.
    """

    def _orch_to_scraper(self, **kwargs: Any) -> ScraperScrapeRequest:
        """Simulate the wire round-trip: orchestrator serialises → scraper parses."""
        orch_req = OrchestratorScrapeRequest(topic="t", query="q", **kwargs)
        return ScraperScrapeRequest.model_validate_json(orch_req.model_dump_json())

    def test_integer_priority_8_maps_to_high(self) -> None:
        """Integer priority 8-10 maps to Priority.HIGH."""
        req = self._orch_to_scraper(priority=8)
        assert req.priority == ScraperPriority.HIGH

    def test_integer_priority_9_maps_to_high(self) -> None:
        """Integer priority 9 maps to Priority.HIGH."""
        req = self._orch_to_scraper(priority=9)
        assert req.priority == ScraperPriority.HIGH

    def test_integer_priority_10_maps_to_high(self) -> None:
        """Integer priority 10 maps to Priority.HIGH."""
        req = self._orch_to_scraper(priority=10)
        assert req.priority == ScraperPriority.HIGH

    def test_integer_priority_5_maps_to_medium(self) -> None:
        """Integer priority 4-7 maps to Priority.MEDIUM."""
        req = self._orch_to_scraper(priority=5)
        assert req.priority == ScraperPriority.MEDIUM

    def test_integer_priority_4_maps_to_medium(self) -> None:
        """Integer priority 4 maps to Priority.MEDIUM."""
        req = self._orch_to_scraper(priority=4)
        assert req.priority == ScraperPriority.MEDIUM

    def test_integer_priority_2_maps_to_low(self) -> None:
        """Integer priority 1-3 maps to Priority.LOW."""
        req = self._orch_to_scraper(priority=2)
        assert req.priority == ScraperPriority.LOW

    def test_integer_priority_1_maps_to_low(self) -> None:
        """Integer priority 1 maps to Priority.LOW."""
        req = self._orch_to_scraper(priority=1)
        assert req.priority == ScraperPriority.LOW

    def test_source_type_web_maps_to_web_search(self) -> None:
        """Orchestrator's SourceType.WEB ('web') maps to scraper's SourceType.WEB_SEARCH."""
        req = self._orch_to_scraper(source_type=OrchestratorSourceType.WEB)
        assert req.source_type == ScraperSourceType.WEB_SEARCH

    def test_source_type_academic_preserved(self) -> None:
        """Orchestrator's SourceType.ACADEMIC maps to scraper's SourceType.ACADEMIC."""
        req = self._orch_to_scraper(source_type=OrchestratorSourceType.ACADEMIC)
        assert req.source_type == ScraperSourceType.ACADEMIC

    def test_source_type_rss_preserved(self) -> None:
        """Orchestrator's SourceType.RSS maps to scraper's SourceType.RSS."""
        req = self._orch_to_scraper(source_type=OrchestratorSourceType.RSS)
        assert req.source_type == ScraperSourceType.RSS

    def test_max_results_field_is_silently_ignored(self) -> None:
        """Orchestrator's max_results field is silently ignored by the scraper."""
        orch_req = OrchestratorScrapeRequest(topic="t", query="q", max_results=20)
        payload = json.loads(orch_req.model_dump_json())
        assert "max_results" in payload  # orchestrator includes it
        req = ScraperScrapeRequest.model_validate(payload)  # scraper ignores it
        assert req.topic == "t"
        assert req.query == "q"

    def test_full_wire_roundtrip_preserves_core_fields(self) -> None:
        """Orchestrator ScrapeRequest can be deserialised by scraper without adaptation."""
        orch_req = OrchestratorScrapeRequest(
            topic="machine_learning",
            query="neural networks",
            priority=7,
            source_type=OrchestratorSourceType.WEB,
            metadata={"iteration": 1},
        )
        raw = orch_req.model_dump_json()
        scraper_req = ScraperScrapeRequest.model_validate_json(raw)

        assert scraper_req.request_id == orch_req.request_id
        assert scraper_req.topic == orch_req.topic
        assert scraper_req.query == orch_req.query
        assert scraper_req.metadata == orch_req.metadata


# ===========================================================================
# Boundary 2: Extractor → Knowledge (extraction-complete topic)
# ===========================================================================


@pytest.mark.integration
class TestContractBoundary2_ExtractorKnowledge:
    """Contract: Extractor → Knowledge (extraction-complete topic).

    The Extractor publishes an extraction-complete message with entities,
    relationships, claims, and summaries.  The Knowledge service deserialises
    this as a KnowledgeUnit.  Field differences between the two services'
    entity models must be resolved automatically.
    """

    def _make_extractor_payload(self) -> dict:
        """Return a representative extraction-complete payload as the extractor sends it."""
        return {
            "request_id": "req-123",
            "topic": "machine_learning",
            "entities": [
                {
                    "id": "e1",
                    "name": "Neural Network",
                    "entity_type": "concept",       # lowercase — extractor format
                    "description": "A computing model",
                    "topic": "machine_learning",
                    "confidence": 0.9,
                    "source_url": "https://example.com",  # singular — extractor format
                }
            ],
            "relationships": [
                {
                    "id": "r1",
                    "source_entity_id": "e1",
                    "target_entity_id": "e2",
                    "relationship_type": "uses",
                    "confidence": 0.8,
                    # No 'topic' field — extractor Relationship has no topic
                }
            ],
            "claims": [
                {
                    "id": "c1",
                    "statement": "Neural networks learn from data",
                    "topic": "machine_learning",
                    "confidence": 0.95,
                    "source_url": "https://example.com",
                }
            ],
            "summaries": [
                {"id": "s1", "topic": "machine_learning", "content": "Overview..."}
            ],
        }

    def test_extractor_payload_validates_as_knowledge_unit(self) -> None:
        """The extraction-complete payload must deserialise as KnowledgeUnit."""
        unit = KnowledgeUnit.model_validate(self._make_extractor_payload())
        assert len(unit.entities) == 1
        assert len(unit.relationships) == 1
        assert len(unit.claims) == 1
        assert unit.request_id == "req-123"
        assert unit.topic == "machine_learning"

    def test_entity_type_concept_normalised(self) -> None:
        """entity_type='concept' (lowercase) maps to EntityType.CONCEPT."""
        entity = Entity.model_validate(
            {"name": "X", "entity_type": "concept", "topic": "t"}
        )
        assert entity.entity_type == EntityType.CONCEPT

    def test_entity_type_method_normalised(self) -> None:
        """entity_type='method' (lowercase) maps to EntityType.METHOD."""
        entity = Entity.model_validate(
            {"name": "X", "entity_type": "method", "topic": "t"}
        )
        assert entity.entity_type == EntityType.METHOD

    def test_entity_type_person_normalised(self) -> None:
        """entity_type='person' (lowercase) maps to EntityType.PERSON."""
        entity = Entity.model_validate(
            {"name": "X", "entity_type": "person", "topic": "t"}
        )
        assert entity.entity_type == EntityType.PERSON

    def test_entity_type_technology_normalised(self) -> None:
        """entity_type='technology' (lowercase) maps to EntityType.TECHNOLOGY."""
        entity = Entity.model_validate(
            {"name": "X", "entity_type": "technology", "topic": "t"}
        )
        assert entity.entity_type == EntityType.TECHNOLOGY

    def test_entity_type_metric_maps_to_other(self) -> None:
        """entity_type='metric' (not in knowledge enum) maps to EntityType.OTHER."""
        entity = Entity.model_validate(
            {"name": "X", "entity_type": "metric", "topic": "t"}
        )
        assert entity.entity_type == EntityType.OTHER

    def test_entity_source_url_mapped_to_source_urls(self) -> None:
        """Singular source_url from extractor is added to source_urls list."""
        entity = Entity.model_validate({
            "name": "X",
            "entity_type": "concept",
            "topic": "t",
            "source_url": "https://example.com/paper",
        })
        assert "https://example.com/paper" in entity.source_urls

    def test_relationship_without_topic_defaults_to_empty_string(self) -> None:
        """Extractor Relationship (no topic field) validates with empty default topic."""
        rel = Relationship.model_validate({
            "source_entity_id": "e1",
            "target_entity_id": "e2",
            "relationship_type": "related_to",
        })
        assert rel.topic == ""

    def test_knowledge_unit_accepts_request_id_and_topic(self) -> None:
        """KnowledgeUnit accepts the top-level request_id and topic fields from extractor."""
        unit = KnowledgeUnit.model_validate({
            "request_id": "req-abc",
            "topic": "deep_learning",
        })
        assert unit.request_id == "req-abc"
        assert unit.topic == "deep_learning"

    def test_knowledge_unit_accepts_summaries(self) -> None:
        """KnowledgeUnit accepts the summaries field from extractor."""
        unit = KnowledgeUnit.model_validate({
            "summaries": [{"id": "s1", "content": "Summary text"}],
        })
        assert len(unit.summaries) == 1

    def test_full_extractor_payload_roundtrip(self) -> None:
        """Full extraction-complete payload from extractor can be ingested by knowledge."""
        unit = KnowledgeUnit.model_validate(self._make_extractor_payload())

        # Entities should be properly typed
        assert unit.entities[0].entity_type == EntityType.CONCEPT
        # source_url should be in source_urls
        assert "https://example.com" in unit.entities[0].source_urls
        # Relationship should have empty topic default
        assert unit.relationships[0].topic == ""
        # Claims should have the correct statement
        assert unit.claims[0].statement == "Neural networks learn from data"


# ===========================================================================
# Boundary 3: Reasoner → Knowledge (HTTP API)
# ===========================================================================


@pytest.mark.integration
class TestContractBoundary3_ReasonerKnowledge:
    """Contract: Reasoner → Knowledge (HTTP API calls).

    The Reasoner's KnowledgeServiceClient must call the correct endpoints with
    the correct parameter names as defined by the Knowledge service's HTTP API.
    """

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_entities_calls_entities_search_endpoint(self) -> None:
        """get_entities must call GET /entities/search (not GET /entities)."""
        base = "http://knowledge:8000"
        route = respx.get(f"{base}/entities/search").mock(
            return_value=Response(200, json=[{"name": "E1", "topic": "ml"}])
        )
        client = KnowledgeServiceClient(base)
        try:
            result = await client.get_entities("ml")
            assert route.called, "GET /entities/search was not called"
            assert len(result) == 1
            assert result[0]["name"] == "E1"
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_entities_uses_limit_not_top_k(self) -> None:
        """get_entities must send 'limit' not 'top_k' as the query parameter."""
        base = "http://knowledge:8000"
        route = respx.get(f"{base}/entities/search").mock(
            return_value=Response(200, json=[])
        )
        client = KnowledgeServiceClient(base)
        try:
            await client.get_entities("ml", top_k=25)
            request = route.calls[0].request
            url_str = str(request.url)
            assert "limit=25" in url_str, f"Expected 'limit=25' in URL: {url_str}"
            assert "top_k" not in url_str, f"Unexpected 'top_k' in URL: {url_str}"
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_claims_uses_limit_not_top_k(self) -> None:
        """get_claims must send 'limit' not 'top_k' as the query parameter."""
        base = "http://knowledge:8000"
        route = respx.get(f"{base}/claims").mock(
            return_value=Response(200, json=[])
        )
        client = KnowledgeServiceClient(base)
        try:
            await client.get_claims("ml", top_k=30)
            request = route.calls[0].request
            url_str = str(request.url)
            assert "limit=30" in url_str, f"Expected 'limit=30' in URL: {url_str}"
            assert "top_k" not in url_str, f"Unexpected 'top_k' in URL: {url_str}"
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_relationships_uses_entity_id_singular(self) -> None:
        """get_relationships must send 'entity_id' (singular) not 'entity_ids'."""
        base = "http://knowledge:8000"
        route = respx.get(f"{base}/relationships").mock(
            return_value=Response(200, json=[])
        )
        client = KnowledgeServiceClient(base)
        try:
            await client.get_relationships("ml", entity_ids=["e1", "e2"])
            request = route.calls[0].request
            url_str = str(request.url)
            assert "entity_id=" in url_str, f"Expected 'entity_id=' in URL: {url_str}"
            assert "entity_ids=" not in url_str, f"Unexpected 'entity_ids=' in URL: {url_str}"
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_uses_q_param(self) -> None:
        """search must send 'q' not 'query' as the search parameter."""
        base = "http://knowledge:8000"
        route = respx.get(f"{base}/search").mock(
            return_value=Response(200, json={"items": [], "total_count": 0})
        )
        client = KnowledgeServiceClient(base)
        try:
            await client.search("neural networks")
            request = route.calls[0].request
            url_str = str(request.url)
            assert "q=" in url_str, f"Expected 'q=' in URL: {url_str}"
            assert "query=" not in url_str, f"Unexpected 'query=' in URL: {url_str}"
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_uses_limit_not_top_k(self) -> None:
        """search must send 'limit' not 'top_k' as the count parameter."""
        base = "http://knowledge:8000"
        route = respx.get(f"{base}/search").mock(
            return_value=Response(200, json={"items": [], "total_count": 0})
        )
        client = KnowledgeServiceClient(base)
        try:
            await client.search("neural networks", top_k=15)
            request = route.calls[0].request
            url_str = str(request.url)
            assert "limit=15" in url_str, f"Expected 'limit=15' in URL: {url_str}"
            assert "top_k=" not in url_str, f"Unexpected 'top_k=' in URL: {url_str}"
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_parses_items_field_from_knowledge_response(self) -> None:
        """search must parse the 'items' field from knowledge's SearchResult response."""
        base = "http://knowledge:8000"
        respx.get(f"{base}/search").mock(
            return_value=Response(200, json={
                "items": [{"id": "e1", "name": "Neural Network"}],
                "total_count": 1,
                "facets": {},
            })
        )
        client = KnowledgeServiceClient(base)
        try:
            result = await client.search("neural")
            assert len(result) == 1
            assert result[0]["name"] == "Neural Network"
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_claims_returns_list(self) -> None:
        """get_claims correctly handles a list response from knowledge."""
        base = "http://knowledge:8000"
        respx.get(f"{base}/claims").mock(
            return_value=Response(200, json=[{"statement": "S1"}, {"statement": "S2"}])
        )
        client = KnowledgeServiceClient(base)
        try:
            result = await client.get_claims("ml")
            assert len(result) == 2
            assert result[0]["statement"] == "S1"
        finally:
            await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_relationships_returns_list(self) -> None:
        """get_relationships correctly handles a list response from knowledge."""
        base = "http://knowledge:8000"
        respx.get(f"{base}/relationships").mock(
            return_value=Response(200, json=[{"relationship_type": "uses"}])
        )
        client = KnowledgeServiceClient(base)
        try:
            result = await client.get_relationships("ml")
            assert len(result) == 1
        finally:
            await client.close()


# ===========================================================================
# Boundary 4: Evaluator → Orchestrator (evaluation-complete topic)
# ===========================================================================


@pytest.mark.integration
class TestContractBoundary4_EvaluatorOrchestrator:
    """Contract: Evaluator → Orchestrator (evaluation-complete topic).

    The Evaluator must publish events in the format that the Orchestrator's
    EvaluationResult model can deserialise directly from the wire.
    """

    def _make_evaluator_event(self, **overrides: Any) -> dict:
        """Build a representative evaluation-complete event as the evaluator now publishes."""
        event: dict = {
            "request_id": "eval-req-42",
            "topic": "machine_learning",
            "overall_score": 0.78,
            "coverage_score": 0.82,
            "depth_score": 0.75,
            "accuracy_score": 0.78,
            "gaps": ["Explainability", "Fairness"],
            "weak_areas": ["Explainability", "Fairness"],
            "strong_areas": [],
            "recommendations": ["Study recent explainability papers"],
        }
        event.update(overrides)
        return event

    def test_evaluator_event_validates_as_evaluation_result(self) -> None:
        """The evaluation-complete event must be deserialisable as EvaluationResult."""
        result = EvaluationResult.model_validate(self._make_evaluator_event())
        assert result.request_id == "eval-req-42"
        assert result.topic == "machine_learning"
        assert 0.0 <= result.overall_score <= 1.0

    def test_scores_are_in_0_1_range(self) -> None:
        """EvaluationResult scores must be in 0.0–1.0 range."""
        result = EvaluationResult.model_validate(self._make_evaluator_event())
        assert 0.0 <= result.overall_score <= 1.0
        assert 0.0 <= result.coverage_score <= 1.0
        assert 0.0 <= result.depth_score <= 1.0
        assert 0.0 <= result.accuracy_score <= 1.0

    def test_normalisation_from_100_scale(self) -> None:
        """Scores from ExpertiseScorecard (0-100) divided by 100 must be valid."""
        # Simulates what evaluator/main.py does: scorecard.overall_score / 100.0
        raw_score = 78.5
        normalised = round(raw_score / 100.0, 4)
        event = self._make_evaluator_event(overall_score=normalised)
        result = EvaluationResult.model_validate(event)
        assert result.overall_score == pytest.approx(0.785)

    def test_gaps_are_strings_not_objects(self) -> None:
        """EvaluationResult.gaps must be a list of strings, not structured objects."""
        result = EvaluationResult.model_validate(
            self._make_evaluator_event(gaps=["Gap Area 1", "Gap Area 2"])
        )
        assert all(isinstance(g, str) for g in result.gaps)

    def test_evaluator_event_json_roundtrip(self) -> None:
        """Evaluation event must survive JSON serialisation round-trip."""
        event = self._make_evaluator_event()
        raw = json.dumps(event)
        received = EvaluationResult.model_validate(json.loads(raw))

        assert received.request_id == event["request_id"]
        assert received.overall_score == pytest.approx(event["overall_score"])
        assert received.gaps == event["gaps"]
        assert received.recommendations == event["recommendations"]

    def test_weak_areas_accepted(self) -> None:
        """EvaluationResult accepts the weak_areas field."""
        result = EvaluationResult.model_validate(
            self._make_evaluator_event(weak_areas=["Area A", "Area B"])
        )
        assert result.weak_areas == ["Area A", "Area B"]

    def test_strong_areas_accepted(self) -> None:
        """EvaluationResult accepts the strong_areas field."""
        result = EvaluationResult.model_validate(
            self._make_evaluator_event(strong_areas=["Supervised learning"])
        )
        assert result.strong_areas == ["Supervised learning"]

    def test_orchestrator_can_receive_evaluator_event(self) -> None:
        """Evaluator's published event is accepted by orchestrator's EvaluationResult model."""
        # Simulate the orchestrator _listen_loop receiving the event from the evaluator
        raw_message = json.dumps(self._make_evaluator_event(
            request_id="eval-orch-1",
            topic="reinforcement_learning",
            overall_score=0.65,
        ))
        event = EvaluationResult.model_validate(json.loads(raw_message))

        assert event.topic == "reinforcement_learning"
        assert event.overall_score == pytest.approx(0.65)
        assert isinstance(event.gaps, list)
        assert isinstance(event.recommendations, list)
