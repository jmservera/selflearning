"""Integration tests for the end-to-end learning pipeline.

Tests message flow between services via mocked Service Bus.
Pipeline stages: Plan → Scrape → Extract → Organize (Knowledge) → Reason → Evaluate → Improve

Each test validates that:
  1. A message produced by Service A has the format that Service B can consume.
  2. Service B processes the message and produces output for Service C.
  3. The Orchestrator correctly coordinates the pipeline using completion buffers.

Run:
    python -m pytest tests/test_integration.py -v

No real Azure resources are needed — all external dependencies are mocked.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure src/ is importable
# ---------------------------------------------------------------------------
_SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# ---------------------------------------------------------------------------
# Import models via package notation (no bare-import conflicts because all
# service model files only import from pydantic / stdlib).
# ---------------------------------------------------------------------------
from orchestrator.models import (  # noqa: E402
    CompletionEvent,
    EvaluationResult,
    ReasoningRequest,
    ReasoningType,
    ScrapeRequest as OrchestratorScrapeRequest,
    SourceType as OrchestratorSourceType,
)
from scraper.models import (  # noqa: E402
    ScrapeCompleteEvent,
    ScrapeRequest as ScraperScrapeRequest,
    ScrapeResult,
    ScrapeStats,
    SourceType as ScraperSourceType,
)
from extractor.models import (  # noqa: E402
    Claim,
    Entity,
    ExtractionResult,
    Relationship,
)
from reasoner.models import (  # noqa: E402
    Insight,
    KnowledgeGap,
    ReasoningRequest as ReasonerRequest,
    ReasoningResult,
)

# ---------------------------------------------------------------------------
# In-process pipeline message bus
# ---------------------------------------------------------------------------


class PipelineMessageBus:
    """In-memory router that simulates Azure Service Bus without real Azure.

    Stores outgoing messages per topic/queue and exposes async helpers to
    inject incoming completion events into waiting coroutines.
    """

    def __init__(self) -> None:
        self._topic_messages: dict[str, list[dict]] = {}
        self._queue_messages: dict[str, list[dict]] = {}
        # Asyncio queues used by wait_for_message()
        self._listeners: dict[str, asyncio.Queue] = {}

    # ── Publishing ────────────────────────────────────────────────────

    def publish_to_topic(self, topic: str, message: dict) -> None:
        self._topic_messages.setdefault(topic, []).append(message)
        if topic in self._listeners:
            self._listeners[topic].put_nowait(message)

    def publish_to_queue(self, queue: str, message: dict) -> None:
        self._queue_messages.setdefault(queue, []).append(message)
        if queue in self._listeners:
            self._listeners[queue].put_nowait(message)

    # ── Consuming ─────────────────────────────────────────────────────

    def get_topic_messages(self, topic: str) -> list[dict]:
        return list(self._topic_messages.get(topic, []))

    def get_queue_messages(self, queue: str) -> list[dict]:
        return list(self._queue_messages.get(queue, []))

    async def wait_for_message(self, channel: str, timeout: float = 2.0) -> dict:
        """Wait for the next message on a topic or queue."""
        if channel not in self._listeners:
            self._listeners[channel] = asyncio.Queue()
        return await asyncio.wait_for(self._listeners[channel].get(), timeout=timeout)

    def clear(self) -> None:
        self._topic_messages.clear()
        self._queue_messages.clear()
        self._listeners.clear()


# ---------------------------------------------------------------------------
# Simplified service simulators (stand-ins for real service handlers)
# ---------------------------------------------------------------------------


class ScraperSimulator:
    """Minimal scraper that accepts a ScrapeRequest and returns a ScrapeCompleteEvent."""

    async def handle(self, request: ScraperScrapeRequest) -> ScrapeCompleteEvent:
        """Process a scrape request and return a completion event."""
        result = ScrapeResult(
            request_id=request.request_id,
            topic=request.topic,
            url=f"https://example.com/{request.topic.replace(' ', '-')}",
            blob_path=f"blobs/{request.topic}/{request.request_id}.html",
            content_hash="sha256:deadbeef",
            title=f"Introduction to {request.topic}",
            text_preview=f"Comprehensive overview of {request.topic}...",
            word_count=1200,
        )
        return ScrapeCompleteEvent(
            request_id=request.request_id,
            topic=request.topic,
            results=[result],
            stats=ScrapeStats(
                urls_attempted=1,
                urls_succeeded=1,
                total_bytes=len(result.text_preview.encode()),
                elapsed_seconds=0.5,
            ),
        )


class ExtractorSimulator:
    """Minimal extractor that accepts a ScrapeCompleteEvent and returns an ExtractionResult."""

    async def handle(self, event: ScrapeCompleteEvent) -> ExtractionResult:
        """Process a scrape-complete event and extract knowledge."""
        entities = [
            Entity(
                name="Neural Network",
                entity_type="concept",
                description="A computing model inspired by biological brains",
                topic=event.topic,
                confidence=0.9,
                source_url=event.results[0].url if event.results else "",
            ),
            Entity(
                name="Backpropagation",
                entity_type="method",
                description="Algorithm for training neural networks",
                topic=event.topic,
                confidence=0.88,
                source_url=event.results[0].url if event.results else "",
            ),
        ]
        claims = [
            Claim(
                statement="Neural networks can approximate any continuous function",
                topic=event.topic,
                confidence=0.92,
                source_url=event.results[0].url if event.results else "",
                supporting_evidence=["Universal approximation theorem"],
            )
        ]
        relationships = [
            Relationship(
                source_entity_id=entities[0].id,
                target_entity_id=entities[1].id,
                relationship_type="trained_by",
                description="Neural networks are trained using backpropagation",
                confidence=0.95,
            )
        ]
        return ExtractionResult(
            request_id=event.request_id,
            topic=event.topic,
            entities=entities,
            relationships=relationships,
            claims=claims,
            summaries=[],
        )


class ReasonerSimulator:
    """Minimal reasoner that accepts a ReasoningRequest and produces a ReasoningResult."""

    async def handle(self, request: ReasonerRequest) -> ReasoningResult:
        """Process a reasoning request and return insights and gaps."""
        insights = [
            Insight(
                topic=request.topic,
                statement=f"Key insight about {request.topic}: deep learning excels at pattern recognition",
                supporting_entities=["Neural Network", "Backpropagation"],
                confidence=0.85,
                reasoning_chain="Pattern recognition → Feature extraction → Learned representations",
            )
        ]
        gaps = [
            KnowledgeGap(
                topic=request.topic,
                area="Explainability",
                severity="moderate",
                description="Limited knowledge on why neural networks make specific decisions",
                suggested_queries=[
                    "neural network interpretability",
                    "explainable AI methods",
                ],
            )
        ]
        return ReasoningResult(
            request_id=request.request_id,
            topic=request.topic,
            insights=insights,
            gaps=gaps,
        )


class KnowledgeStoreSimulator:
    """Minimal in-memory knowledge store."""

    def __init__(self) -> None:
        self.entities: list[dict] = []
        self.claims: list[dict] = []
        self.relationships: list[dict] = []

    def ingest(self, extraction: ExtractionResult) -> dict:
        self.entities.extend(e.model_dump() for e in extraction.entities)
        self.claims.extend(c.model_dump() for c in extraction.claims)
        self.relationships.extend(r.model_dump() for r in extraction.relationships)
        return {
            "entities_ingested": len(extraction.entities),
            "claims_ingested": len(extraction.claims),
            "relationships_ingested": len(extraction.relationships),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scraper_request(orch_req: OrchestratorScrapeRequest) -> ScraperScrapeRequest:
    """Convert an orchestrator ScrapeRequest to a scraper ScrapeRequest via JSON round-trip.

    This simulates the actual wire format: the orchestrator serializes to JSON,
    and the scraper deserializes from JSON. Fields not present in the scraper model
    are ignored; missing optional fields use defaults.
    """
    payload = json.loads(orch_req.model_dump_json())
    # The scraper's ScrapeRequest uses Priority enum for `priority` and a
    # different SourceType; we normalize to the scraper's defaults for
    # fields that don't overlap.
    return ScraperScrapeRequest(
        request_id=payload["request_id"],
        topic=payload["topic"],
        query=payload["query"],
        url=payload.get("url"),
        metadata=payload.get("metadata", {}),
    )


def _scrape_complete_to_completion_event(event: ScrapeCompleteEvent) -> CompletionEvent:
    """Convert a ScrapeCompleteEvent to an orchestrator CompletionEvent."""
    return CompletionEvent(
        request_id=event.request_id,
        topic=event.topic,
        status="success",
        result={
            "summary": f"Scraped {len(event.results)} URL(s)",
            "url_count": len(event.results),
            "urls_succeeded": event.stats.urls_succeeded,
        },
    )


def _extraction_to_completion_event(result: ExtractionResult) -> CompletionEvent:
    """Convert an ExtractionResult to an orchestrator CompletionEvent."""
    return CompletionEvent(
        request_id=result.request_id,
        topic=result.topic,
        status="success",
        result={
            "entities_extracted": len(result.entities),
            "claims_extracted": len(result.claims),
            "relationships_extracted": len(result.relationships),
        },
    )


def _reasoning_to_completion_event(result: ReasoningResult) -> CompletionEvent:
    """Convert a ReasoningResult to an orchestrator CompletionEvent."""
    return CompletionEvent(
        request_id=result.request_id,
        topic=result.topic,
        status="success",
        result={
            "insights": [i.statement for i in result.insights],
            "gaps": [g.area for g in result.gaps],
            "insights_count": len(result.insights),
            "gaps_count": len(result.gaps),
        },
    )


# ===========================================================================
# Integration Test Suite
# ===========================================================================


@pytest.mark.integration
class TestScrapeExtractPipeline:
    """Test the Scrape → Extract → Knowledge ingestion stage of the pipeline."""

    @pytest.fixture
    def bus(self) -> PipelineMessageBus:
        return PipelineMessageBus()

    @pytest.fixture
    def scraper(self) -> ScraperSimulator:
        return ScraperSimulator()

    @pytest.fixture
    def extractor(self) -> ExtractorSimulator:
        return ExtractorSimulator()

    @pytest.fixture
    def store(self) -> KnowledgeStoreSimulator:
        return KnowledgeStoreSimulator()

    # ── Scrape request format compatibility ───────────────────────────

    async def test_orchestrator_publishes_scrape_request(self, bus: PipelineMessageBus) -> None:
        """Orchestrator should publish a well-formed scrape request to the queue."""
        req = OrchestratorScrapeRequest(
            topic="machine_learning",
            query="deep learning fundamentals",
            priority=7,
            source_type=OrchestratorSourceType.WEB,
        )

        # Simulate the orchestrator sending to the queue
        payload = json.loads(req.model_dump_json())
        bus.publish_to_queue("scrape-requests", payload)

        messages = bus.get_queue_messages("scrape-requests")
        assert len(messages) == 1
        msg = messages[0]
        assert msg["topic"] == "machine_learning"
        assert msg["query"] == "deep learning fundamentals"
        assert "request_id" in msg
        assert msg["priority"] == 7

    async def test_scraper_processes_request_and_produces_event(
        self, scraper: ScraperSimulator
    ) -> None:
        """Scraper should consume a ScrapeRequest and produce a ScrapeCompleteEvent."""
        req = ScraperScrapeRequest(
            topic="machine_learning",
            query="deep learning fundamentals",
        )
        event = await scraper.handle(req)

        assert event.request_id == req.request_id
        assert event.topic == "machine_learning"
        assert len(event.results) == 1
        assert event.stats.urls_succeeded == 1
        result = event.results[0]
        assert result.topic == "machine_learning"
        assert result.blob_path.startswith("blobs/")
        assert result.content_hash

    async def test_scrape_complete_event_is_json_serializable(
        self, scraper: ScraperSimulator
    ) -> None:
        """ScrapeCompleteEvent must round-trip through JSON (wire format)."""
        req = ScraperScrapeRequest(topic="machine_learning", query="neural networks")
        event = await scraper.handle(req)

        raw = event.model_dump_json()
        restored = ScrapeCompleteEvent.model_validate_json(raw)
        assert restored.request_id == event.request_id
        assert restored.topic == event.topic
        assert len(restored.results) == len(event.results)

    async def test_scrape_request_wire_format_roundtrip(self) -> None:
        """Orchestrator scrape request should survive JSON serialisation for the scraper."""
        orch_req = OrchestratorScrapeRequest(
            topic="quantum_computing",
            query="quantum entanglement basics",
        )
        scraper_req = _make_scraper_request(orch_req)

        assert scraper_req.request_id == orch_req.request_id
        assert scraper_req.topic == orch_req.topic
        assert scraper_req.query == orch_req.query

    # ── Extractor stage ───────────────────────────────────────────────

    async def test_extractor_processes_scrape_complete_event(
        self,
        scraper: ScraperSimulator,
        extractor: ExtractorSimulator,
    ) -> None:
        """Extractor should consume a ScrapeCompleteEvent and produce an ExtractionResult."""
        req = ScraperScrapeRequest(topic="machine_learning", query="backpropagation")
        scrape_event = await scraper.handle(req)

        extraction = await extractor.handle(scrape_event)

        assert extraction.request_id == scrape_event.request_id
        assert extraction.topic == "machine_learning"
        assert len(extraction.entities) > 0
        assert len(extraction.claims) > 0

    async def test_extraction_result_has_valid_entities(
        self,
        scraper: ScraperSimulator,
        extractor: ExtractorSimulator,
    ) -> None:
        """Each extracted entity should have required fields."""
        req = ScraperScrapeRequest(topic="machine_learning", query="transformers")
        scrape_event = await scraper.handle(req)
        extraction = await extractor.handle(scrape_event)

        for entity in extraction.entities:
            assert entity.id, "Entity must have an id"
            assert entity.name, "Entity must have a name"
            assert entity.topic == "machine_learning"
            assert 0.0 <= entity.confidence <= 1.0

    async def test_extraction_result_is_json_serializable(
        self,
        scraper: ScraperSimulator,
        extractor: ExtractorSimulator,
    ) -> None:
        """ExtractionResult must round-trip through JSON."""
        req = ScraperScrapeRequest(topic="machine_learning", query="deep learning")
        scrape_event = await scraper.handle(req)
        extraction = await extractor.handle(scrape_event)

        raw = extraction.model_dump_json()
        restored = ExtractionResult.model_validate_json(raw)
        assert restored.request_id == extraction.request_id
        assert len(restored.entities) == len(extraction.entities)
        assert len(restored.claims) == len(extraction.claims)

    async def test_extraction_completion_event_format(
        self,
        scraper: ScraperSimulator,
        extractor: ExtractorSimulator,
    ) -> None:
        """The CompletionEvent produced from an ExtractionResult must be valid for the Orchestrator."""
        req = ScraperScrapeRequest(topic="machine_learning", query="deep learning")
        scrape_event = await scraper.handle(req)
        extraction = await extractor.handle(scrape_event)

        completion = _extraction_to_completion_event(extraction)

        assert completion.request_id == extraction.request_id
        assert completion.topic == extraction.topic
        assert completion.status == "success"
        assert "entities_extracted" in completion.result
        assert completion.result["entities_extracted"] == len(extraction.entities)

    # ── Knowledge ingestion stage ─────────────────────────────────────

    async def test_knowledge_ingests_extraction_result(
        self,
        scraper: ScraperSimulator,
        extractor: ExtractorSimulator,
        store: KnowledgeStoreSimulator,
    ) -> None:
        """Knowledge store should accept an ExtractionResult and persist entities/claims."""
        req = ScraperScrapeRequest(topic="machine_learning", query="deep learning")
        scrape_event = await scraper.handle(req)
        extraction = await extractor.handle(scrape_event)

        stats = store.ingest(extraction)

        assert stats["entities_ingested"] == len(extraction.entities)
        assert stats["claims_ingested"] == len(extraction.claims)
        assert len(store.entities) == len(extraction.entities)
        assert len(store.claims) == len(extraction.claims)

    # ── Full Scrape→Extract→Knowledge flow ───────────────────────────

    async def test_full_scrape_to_knowledge_flow(
        self,
        bus: PipelineMessageBus,
        scraper: ScraperSimulator,
        extractor: ExtractorSimulator,
        store: KnowledgeStoreSimulator,
    ) -> None:
        """End-to-end: Orchestrator publishes scrape request → Scraper → Extractor → Knowledge."""
        # Step 1: Orchestrator creates and publishes a scrape request
        orch_req = OrchestratorScrapeRequest(
            topic="machine_learning",
            query="convolutional neural networks",
            priority=8,
        )
        bus.publish_to_queue("scrape-requests", json.loads(orch_req.model_dump_json()))

        # Step 2: Scraper receives the request and produces a ScrapeCompleteEvent
        queue_msgs = bus.get_queue_messages("scrape-requests")
        assert len(queue_msgs) == 1
        scraper_req = _make_scraper_request(orch_req)
        scrape_event = await scraper.handle(scraper_req)
        bus.publish_to_topic("scrape-complete", json.loads(scrape_event.model_dump_json()))

        # Step 3: Extractor consumes scrape-complete and produces extraction-complete
        topic_msgs = bus.get_topic_messages("scrape-complete")
        assert len(topic_msgs) == 1
        restored_event = ScrapeCompleteEvent.model_validate(topic_msgs[0])
        extraction = await extractor.handle(restored_event)
        completion = _extraction_to_completion_event(extraction)
        bus.publish_to_topic("extraction-complete", json.loads(completion.model_dump_json()))

        # Step 4: Knowledge service consumes extraction-complete and ingests
        extract_msgs = bus.get_topic_messages("extraction-complete")
        assert len(extract_msgs) == 1
        orch_completion = CompletionEvent.model_validate(extract_msgs[0])
        stats = store.ingest(extraction)

        # Orchestrator receives the completion event
        assert orch_completion.request_id == orch_req.request_id
        assert orch_completion.status == "success"
        assert orch_completion.result["entities_extracted"] >= 1

        # Knowledge store has the data
        assert len(store.entities) >= 1
        assert len(store.claims) >= 1
        assert stats["entities_ingested"] >= 1


@pytest.mark.integration
class TestReasoningPipeline:
    """Test the Reason stage of the pipeline (Orchestrator → Reasoner → Orchestrator)."""

    @pytest.fixture
    def bus(self) -> PipelineMessageBus:
        return PipelineMessageBus()

    @pytest.fixture
    def reasoner(self) -> ReasonerSimulator:
        return ReasonerSimulator()

    async def test_orchestrator_publishes_reasoning_request(
        self, bus: PipelineMessageBus
    ) -> None:
        """Orchestrator should publish a reasoning request to the queue."""
        req = ReasoningRequest(
            topic="machine_learning",
            reasoning_type=ReasoningType.GAP_ANALYSIS,
            context={"iteration": 1, "focus_areas": ["deep learning", "transformers"]},
            priority=6,
        )

        bus.publish_to_queue("reasoning-requests", json.loads(req.model_dump_json()))

        messages = bus.get_queue_messages("reasoning-requests")
        assert len(messages) == 1
        msg = messages[0]
        assert msg["topic"] == "machine_learning"
        assert msg["reasoning_type"] == "gap_analysis"
        assert "request_id" in msg
        assert "context" in msg

    async def test_reasoner_deserializes_orchestrator_request(self) -> None:
        """Reasoner should parse an orchestrator ReasoningRequest via JSON round-trip."""
        orch_req = ReasoningRequest(
            topic="machine_learning",
            reasoning_type=ReasoningType.INSIGHT_SYNTHESIS,
            context={"focus_areas": ["transformers"]},
        )
        payload = json.loads(orch_req.model_dump_json())

        # Reasoner parses the same payload
        reasoner_req = ReasonerRequest.model_validate(payload)
        assert reasoner_req.request_id == orch_req.request_id
        assert reasoner_req.topic == orch_req.topic
        assert reasoner_req.reasoning_type == "insight_synthesis"

    async def test_reasoner_processes_request_and_produces_result(
        self, reasoner: ReasonerSimulator
    ) -> None:
        """Reasoner should consume a ReasoningRequest and produce a ReasoningResult."""
        req = ReasonerRequest(
            topic="machine_learning",
            reasoning_type="gap_analysis",
            context={"iteration": 1},
        )
        result = await reasoner.handle(req)

        assert result.request_id == req.request_id
        assert result.topic == "machine_learning"
        assert len(result.insights) > 0
        assert len(result.gaps) > 0

    async def test_reasoning_result_insight_has_required_fields(
        self, reasoner: ReasonerSimulator
    ) -> None:
        """Each insight in the ReasoningResult must have required fields."""
        req = ReasonerRequest(
            topic="machine_learning",
            reasoning_type="insight_synthesis",
            context={},
        )
        result = await reasoner.handle(req)

        for insight in result.insights:
            assert insight.id, "Insight must have an id"
            assert insight.statement, "Insight must have a statement"
            assert 0.0 <= insight.confidence <= 1.0

    async def test_reasoning_result_gap_has_required_fields(
        self, reasoner: ReasonerSimulator
    ) -> None:
        """Each gap in the ReasoningResult must have required fields."""
        req = ReasonerRequest(
            topic="machine_learning",
            reasoning_type="gap_analysis",
            context={},
        )
        result = await reasoner.handle(req)

        for gap in result.gaps:
            assert gap.id, "Gap must have an id"
            assert gap.area, "Gap must have an area"
            assert gap.severity in ("critical", "moderate", "minor")

    async def test_reasoning_result_is_json_serializable(
        self, reasoner: ReasonerSimulator
    ) -> None:
        """ReasoningResult must survive JSON round-trip (wire format)."""
        req = ReasonerRequest(
            topic="machine_learning",
            reasoning_type="gap_analysis",
            context={"iteration": 2},
        )
        result = await reasoner.handle(req)

        raw = result.model_dump_json()
        restored = ReasoningResult.model_validate_json(raw)
        assert restored.request_id == result.request_id
        assert len(restored.insights) == len(result.insights)
        assert len(restored.gaps) == len(result.gaps)

    async def test_reasoning_completion_event_format(
        self, reasoner: ReasonerSimulator
    ) -> None:
        """The CompletionEvent produced from a ReasoningResult must be valid for the Orchestrator."""
        req = ReasonerRequest(
            topic="machine_learning",
            reasoning_type="insight_synthesis",
            context={},
        )
        result = await reasoner.handle(req)
        completion = _reasoning_to_completion_event(result)

        assert completion.request_id == result.request_id
        assert completion.topic == result.topic
        assert completion.status == "success"
        assert "insights" in completion.result
        assert "gaps" in completion.result
        assert isinstance(completion.result["insights"], list)

    async def test_full_reasoning_pipeline_flow(
        self,
        bus: PipelineMessageBus,
        reasoner: ReasonerSimulator,
    ) -> None:
        """End-to-end: Orchestrator publishes reasoning request → Reasoner → produces reasoning-complete."""
        # Step 1: Orchestrator publishes a reasoning request
        orch_req = ReasoningRequest(
            topic="machine_learning",
            reasoning_type=ReasoningType.INSIGHT_SYNTHESIS,
            context={"focus_areas": ["deep learning"], "iteration": 3},
            priority=7,
        )
        bus.publish_to_queue(
            "reasoning-requests", json.loads(orch_req.model_dump_json())
        )

        # Step 2: Reasoner receives and processes the request
        queue_msgs = bus.get_queue_messages("reasoning-requests")
        assert len(queue_msgs) == 1
        reasoner_req = ReasonerRequest.model_validate(queue_msgs[0])
        result = await reasoner.handle(reasoner_req)
        completion = _reasoning_to_completion_event(result)
        bus.publish_to_topic(
            "reasoning-complete", json.loads(completion.model_dump_json())
        )

        # Step 3: Orchestrator receives the completion event
        topic_msgs = bus.get_topic_messages("reasoning-complete")
        assert len(topic_msgs) == 1
        orch_completion = CompletionEvent.model_validate(topic_msgs[0])

        assert orch_completion.request_id == orch_req.request_id
        assert orch_completion.status == "success"
        assert orch_completion.result["insights_count"] >= 1
        assert orch_completion.result["gaps_count"] >= 1


@pytest.mark.integration
class TestEvaluationCycle:
    """Test the Evaluate stage (Evaluator assesses knowledge → produces scorecard)."""

    @pytest.fixture
    def bus(self) -> PipelineMessageBus:
        return PipelineMessageBus()

    @pytest.fixture
    def store(self) -> KnowledgeStoreSimulator:
        """A knowledge store pre-populated with sample data."""
        s = KnowledgeStoreSimulator()
        # Pre-populate with sample entities and claims
        s.entities = [
            {"id": "e1", "name": "Neural Network", "topic": "machine_learning", "confidence": 0.95},
            {"id": "e2", "name": "Backpropagation", "topic": "machine_learning", "confidence": 0.92},
            {"id": "e3", "name": "Transformer", "topic": "machine_learning", "confidence": 0.88},
        ]
        s.claims = [
            {
                "id": "c1",
                "statement": "Neural networks can approximate any continuous function",
                "topic": "machine_learning",
                "confidence": 0.90,
            },
            {
                "id": "c2",
                "statement": "Backpropagation uses gradient descent",
                "topic": "machine_learning",
                "confidence": 0.95,
            },
        ]
        return s

    async def test_evaluation_result_is_valid_model(self) -> None:
        """EvaluationResult should be constructable and validate field constraints."""
        result = EvaluationResult(
            request_id="eval-req-001",
            topic="machine_learning",
            overall_score=0.75,
            coverage_score=0.80,
            depth_score=0.70,
            accuracy_score=0.75,
            gaps=["Explainability", "Federated learning"],
            weak_areas=["Advanced optimization"],
            strong_areas=["Supervised learning"],
            recommendations=["Study gradient boosting"],
        )

        assert result.request_id == "eval-req-001"
        assert result.topic == "machine_learning"
        assert 0.0 <= result.overall_score <= 1.0
        assert 0.0 <= result.coverage_score <= 1.0
        assert 0.0 <= result.depth_score <= 1.0
        assert 0.0 <= result.accuracy_score <= 1.0
        assert len(result.gaps) == 2
        assert len(result.weak_areas) == 1
        assert len(result.strong_areas) == 1

    async def test_evaluation_score_improves_with_more_knowledge(
        self, store: KnowledgeStoreSimulator
    ) -> None:
        """A knowledge store with more entities/claims should achieve higher coverage scores."""
        base_score = _compute_coverage_score(store, topic="machine_learning")

        # Add more entities to the store
        store.entities.extend([
            {"id": "e4", "name": "Convolutional Network", "topic": "machine_learning", "confidence": 0.85},
            {"id": "e5", "name": "Reinforcement Learning", "topic": "machine_learning", "confidence": 0.88},
        ])
        richer_score = _compute_coverage_score(store, topic="machine_learning")

        assert richer_score > base_score

    async def test_evaluation_result_is_json_serializable(self) -> None:
        """EvaluationResult must survive JSON round-trip."""
        result = EvaluationResult(
            request_id="eval-002",
            topic="machine_learning",
            overall_score=0.82,
            coverage_score=0.85,
            depth_score=0.80,
            accuracy_score=0.82,
            gaps=["Explainability"],
        )
        raw = result.model_dump_json()
        restored = EvaluationResult.model_validate_json(raw)

        assert restored.request_id == result.request_id
        assert restored.overall_score == result.overall_score
        assert restored.gaps == result.gaps

    async def test_evaluator_publishes_to_evaluation_complete_topic(
        self, bus: PipelineMessageBus
    ) -> None:
        """Evaluator should publish EvaluationResult to the evaluation-complete topic."""
        result = EvaluationResult(
            request_id="eval-003",
            topic="machine_learning",
            overall_score=0.78,
            coverage_score=0.80,
            depth_score=0.75,
            accuracy_score=0.79,
        )
        bus.publish_to_topic("evaluation-complete", json.loads(result.model_dump_json()))

        messages = bus.get_topic_messages("evaluation-complete")
        assert len(messages) == 1
        msg = messages[0]
        assert msg["topic"] == "machine_learning"
        assert msg["overall_score"] == 0.78
        assert "request_id" in msg

    async def test_orchestrator_receives_evaluation_result(
        self, bus: PipelineMessageBus
    ) -> None:
        """Orchestrator should deserialize an evaluation-complete message as EvaluationResult."""
        published = EvaluationResult(
            request_id="eval-004",
            topic="machine_learning",
            overall_score=0.85,
            coverage_score=0.88,
            depth_score=0.82,
            accuracy_score=0.85,
            gaps=["Advanced topics"],
            recommendations=["Study recent papers"],
        )
        bus.publish_to_topic("evaluation-complete", json.loads(published.model_dump_json()))

        raw_msg = bus.get_topic_messages("evaluation-complete")[0]
        received = EvaluationResult.model_validate(raw_msg)

        assert received.request_id == published.request_id
        assert received.overall_score == published.overall_score
        assert received.gaps == published.gaps

    async def test_full_evaluation_cycle(
        self, bus: PipelineMessageBus, store: KnowledgeStoreSimulator
    ) -> None:
        """End-to-end: evaluation request → query knowledge → produce scorecard → publish."""
        # Step 1: Orchestrator publishes an evaluation request (as a ReasoningRequest)
        eval_req = ReasoningRequest(
            topic="machine_learning",
            reasoning_type=ReasoningType.GAP_ANALYSIS,
            context={"request_type": "evaluation", "iteration": 2, "current_score": 0.5},
            priority=10,
        )
        bus.publish_to_queue("reasoning-requests", json.loads(eval_req.model_dump_json()))

        # Step 2: Evaluator reads from queue, queries knowledge store, computes scores
        queue_msgs = bus.get_queue_messages("reasoning-requests")
        assert len(queue_msgs) == 1
        request = queue_msgs[0]
        assert request["context"]["request_type"] == "evaluation"

        # Simulate evaluator calling knowledge service
        entities_for_topic = [
            e for e in store.entities if e["topic"] == request["topic"]
        ]
        claims_for_topic = [
            c for c in store.claims if c["topic"] == request["topic"]
        ]
        coverage_score = _compute_coverage_score(store, topic=request["topic"])
        depth_score = min(1.0, len(claims_for_topic) * 0.3)
        accuracy_score = (
            sum(e.get("confidence", 0) for e in entities_for_topic) / len(entities_for_topic)
            if entities_for_topic
            else 0.0
        )
        overall = (coverage_score + depth_score + accuracy_score) / 3.0

        # Step 3: Evaluator publishes the scorecard
        scorecard = EvaluationResult(
            request_id=request["request_id"],
            topic=request["topic"],
            overall_score=round(overall, 4),
            coverage_score=round(coverage_score, 4),
            depth_score=round(depth_score, 4),
            accuracy_score=round(accuracy_score, 4),
            gaps=["Explainability"] if overall < 0.9 else [],
        )
        bus.publish_to_topic("evaluation-complete", json.loads(scorecard.model_dump_json()))

        # Step 4: Orchestrator receives the scorecard
        eval_msgs = bus.get_topic_messages("evaluation-complete")
        assert len(eval_msgs) == 1
        received = EvaluationResult.model_validate(eval_msgs[0])

        assert received.request_id == eval_req.request_id
        assert received.topic == "machine_learning"
        assert 0.0 <= received.overall_score <= 1.0
        assert received.coverage_score > 0.0


def _setup_orchestrator_path() -> None:
    """Configure sys.path and bare-module aliases so orchestrator.service_bus can be imported."""
    _orch_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "src", "orchestrator")
    )
    # Flush any stale bare-module entries that could conflict with other services
    for mod in ("config", "models", "service_bus", "working_memory", "strategy"):
        sys.modules.pop(mod, None)
    if _orch_dir not in sys.path:
        sys.path.insert(1, _orch_dir)
    # Ensure package imports are present so bare-name aliases can point to them
    import orchestrator.config as _oc  # noqa: F401
    import orchestrator.models as _om  # noqa: F401
    sys.modules.setdefault("config", sys.modules["orchestrator.config"])
    sys.modules.setdefault("models", sys.modules["orchestrator.models"])


def _make_orchestrator_settings():
    """Return a minimal OrchestratorSettings instance for tests."""
    from orchestrator.config import OrchestratorSettings

    return OrchestratorSettings(
        servicebus_namespace="test-ns.servicebus.windows.net",
        cosmos_endpoint="https://test.documents.azure.com:443/",
        scrape_complete_topic="scrape-complete",
        extraction_complete_topic="extraction-complete",
        reasoning_complete_topic="reasoning-complete",
        evaluation_complete_topic="evaluation-complete",
    )


@pytest.mark.integration
class TestOrchestratorCompletionBuffers:
    """Test that the OrchestratorServiceBus completion buffer correctly routes events.

    These tests validate the in-process buffer mechanism used by wait_for_completions()
    and wait_for_evaluation() without connecting to real Azure Service Bus.
    """

    @pytest.fixture(autouse=True)
    def _configure_imports(self) -> None:
        """Ensure orchestrator bare-module imports are available before each test."""
        _setup_orchestrator_path()

    @pytest.fixture
    def orch_bus(self):
        """Create an OrchestratorServiceBus instance with no real Azure connections."""
        from orchestrator.service_bus import OrchestratorServiceBus

        settings = _make_orchestrator_settings()
        return OrchestratorServiceBus(settings)

    async def test_completion_buffer_routes_event_to_waiter(self, orch_bus) -> None:
        """wait_for_completions should return an event when one is pre-placed in the buffer."""
        # Pre-populate the buffer directly (simulates listener delivering a message)
        event = CompletionEvent(
            request_id="req-001",
            topic="machine_learning",
            status="success",
            result={"urls_succeeded": 3},
        )
        buffer = orch_bus._get_buffer("scrape-complete")
        await buffer.put(event)

        # Orchestrator waits for the event
        completions = await orch_bus.wait_for_completions(
            request_ids={"req-001"},
            topic_name="scrape-complete",
            timeout_seconds=1.0,
        )

        assert len(completions) == 1
        assert completions[0].request_id == "req-001"
        assert completions[0].status == "success"

    async def test_completion_buffer_collects_multiple_events(self, orch_bus) -> None:
        """wait_for_completions should collect all expected events before returning."""
        request_ids = {"req-A", "req-B", "req-C"}
        buffer = orch_bus._get_buffer("extraction-complete")
        for rid in request_ids:
            await buffer.put(
                CompletionEvent(
                    request_id=rid,
                    topic="machine_learning",
                    status="success",
                    result={"entities_extracted": 5},
                )
            )

        completions = await orch_bus.wait_for_completions(
            request_ids=request_ids,
            topic_name="extraction-complete",
            timeout_seconds=1.0,
        )

        assert len(completions) == 3
        received_ids = {c.request_id for c in completions}
        assert received_ids == request_ids

    async def test_completion_buffer_times_out_for_missing_events(self, orch_bus) -> None:
        """wait_for_completions should return partial results when timeout is hit."""
        # Only provide 1 of 2 expected events
        buffer = orch_bus._get_buffer("reasoning-complete")
        await buffer.put(
            CompletionEvent(
                request_id="req-X",
                topic="machine_learning",
                status="success",
                result={},
            )
        )

        completions = await orch_bus.wait_for_completions(
            request_ids={"req-X", "req-Y-missing"},
            topic_name="reasoning-complete",
            timeout_seconds=0.1,  # Very short timeout — req-Y will never arrive
        )

        # Should return only what was received before the timeout
        assert len(completions) == 1
        assert completions[0].request_id == "req-X"

    async def test_evaluation_buffer_routes_result_to_waiter(self, orch_bus) -> None:
        """wait_for_evaluation should return the evaluation result from the buffer."""
        expected = EvaluationResult(
            request_id="eval-req-999",
            topic="machine_learning",
            overall_score=0.82,
            coverage_score=0.85,
            depth_score=0.80,
            accuracy_score=0.82,
        )
        await orch_bus._evaluation_buffer.put(expected)

        result = await orch_bus.wait_for_evaluation(timeout_seconds=1.0)

        assert result is not None
        assert result.request_id == "eval-req-999"
        assert result.overall_score == 0.82

    async def test_evaluation_buffer_returns_none_on_timeout(self, orch_bus) -> None:
        """wait_for_evaluation should return None when the buffer is empty and timeout hits."""
        result = await orch_bus.wait_for_evaluation(timeout_seconds=0.1)
        assert result is None


@pytest.mark.integration
class TestEndToEndPipelineMessageFlow:
    """Highest-level integration test — simulate a complete pipeline iteration.

    Orchestrator triggers: Plan → Scrape → Extract → Reason → Evaluate.
    The pipeline runs with all services mocked at the Service Bus level.
    """

    @pytest.fixture
    def bus(self) -> PipelineMessageBus:
        return PipelineMessageBus()

    @pytest.fixture
    def scraper(self) -> ScraperSimulator:
        return ScraperSimulator()

    @pytest.fixture
    def extractor(self) -> ExtractorSimulator:
        return ExtractorSimulator()

    @pytest.fixture
    def reasoner(self) -> ReasonerSimulator:
        return ReasonerSimulator()

    @pytest.fixture
    def store(self) -> KnowledgeStoreSimulator:
        return KnowledgeStoreSimulator()

    async def test_pipeline_message_counts_at_each_stage(
        self,
        bus: PipelineMessageBus,
        scraper: ScraperSimulator,
        extractor: ExtractorSimulator,
        reasoner: ReasonerSimulator,
        store: KnowledgeStoreSimulator,
    ) -> None:
        """Verify exactly one message is produced at each stage of the pipeline."""
        topic = "machine_learning"

        # ── Stage: SCRAPE ─────────────────────────────────────────────
        orch_req = OrchestratorScrapeRequest(topic=topic, query="transformers and attention")
        bus.publish_to_queue("scrape-requests", json.loads(orch_req.model_dump_json()))
        assert len(bus.get_queue_messages("scrape-requests")) == 1

        # Scraper processes and publishes
        scraper_req = _make_scraper_request(orch_req)
        scrape_event = await scraper.handle(scraper_req)
        scrape_completion = _scrape_complete_to_completion_event(scrape_event)
        bus.publish_to_topic("scrape-complete", json.loads(scrape_completion.model_dump_json()))
        assert len(bus.get_topic_messages("scrape-complete")) == 1

        # ── Stage: EXTRACT ────────────────────────────────────────────
        extraction = await extractor.handle(scrape_event)
        extract_completion = _extraction_to_completion_event(extraction)
        bus.publish_to_topic(
            "extraction-complete", json.loads(extract_completion.model_dump_json())
        )
        assert len(bus.get_topic_messages("extraction-complete")) == 1

        # ── Stage: ORGANIZE (Knowledge ingestion) ─────────────────────
        store.ingest(extraction)
        assert len(store.entities) >= 1
        assert len(store.claims) >= 1

        # ── Stage: REASON ─────────────────────────────────────────────
        reason_req = ReasoningRequest(
            topic=topic,
            reasoning_type=ReasoningType.INSIGHT_SYNTHESIS,
            context={"iteration": 1},
        )
        bus.publish_to_queue("reasoning-requests", json.loads(reason_req.model_dump_json()))
        assert len(bus.get_queue_messages("reasoning-requests")) == 1

        reasoner_req = ReasonerRequest.model_validate(
            bus.get_queue_messages("reasoning-requests")[0]
        )
        reasoning_result = await reasoner.handle(reasoner_req)
        reason_completion = _reasoning_to_completion_event(reasoning_result)
        bus.publish_to_topic(
            "reasoning-complete", json.loads(reason_completion.model_dump_json())
        )
        assert len(bus.get_topic_messages("reasoning-complete")) == 1

        # ── Stage: EVALUATE ───────────────────────────────────────────
        eval_req = ReasoningRequest(
            topic=topic,
            reasoning_type=ReasoningType.GAP_ANALYSIS,
            context={"request_type": "evaluation", "iteration": 1, "current_score": 0.0},
            priority=10,
        )
        bus.publish_to_queue("reasoning-requests", json.loads(eval_req.model_dump_json()))

        scorecard = EvaluationResult(
            request_id=eval_req.request_id,
            topic=topic,
            overall_score=0.68,
            coverage_score=0.72,
            depth_score=0.65,
            accuracy_score=0.68,
            gaps=["Explainability", "Fairness"],
            recommendations=["Study recent fairness papers"],
        )
        bus.publish_to_topic("evaluation-complete", json.loads(scorecard.model_dump_json()))
        assert len(bus.get_topic_messages("evaluation-complete")) == 1

        # ── Final assertions: all messages present and valid ──────────
        sc_msg = CompletionEvent.model_validate(bus.get_topic_messages("scrape-complete")[0])
        ex_msg = CompletionEvent.model_validate(bus.get_topic_messages("extraction-complete")[0])
        re_msg = CompletionEvent.model_validate(bus.get_topic_messages("reasoning-complete")[0])
        ev_msg = EvaluationResult.model_validate(bus.get_topic_messages("evaluation-complete")[0])

        assert sc_msg.request_id == orch_req.request_id
        assert ex_msg.request_id == orch_req.request_id
        assert re_msg.request_id == reason_req.request_id
        assert ev_msg.request_id == eval_req.request_id
        assert ev_msg.overall_score > 0.0


# ===========================================================================
# Helper functions
# ===========================================================================


def _compute_coverage_score(store: KnowledgeStoreSimulator, topic: str) -> float:
    """Compute a simple coverage score based on entity count (0.0–1.0)."""
    topic_entities = [e for e in store.entities if e.get("topic") == topic]
    # Normalize: 10 entities = full coverage
    return min(1.0, len(topic_entities) / 10.0)

