"""Tests for the Evaluator service.

Covers: question generation, self-testing pipeline, scorecard calculation,
gap analysis, and API endpoints.
"""

import json
from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio

from evaluator.evaluation import DEFAULT_TAXONOMY_AREAS, EvaluationEngine
from evaluator.knowledge_client import KnowledgeClient
from evaluator.models import (
    BenchmarkQuestion,
    CoverageMetric,
    Difficulty,
    EvaluationReport,
    ExpertiseScorecard,
    GapSeverity,
    HealthResponse,
    KnowledgeGap,
    QuestionCategory,
    SelfTestResult,
)
from evaluator.question_generator import QuestionGenerator


# ---------------------------------------------------------------------------
# Question Generation
# ---------------------------------------------------------------------------
class TestQuestionGeneration:
    """Tests for LLM-based question generation."""

    @pytest.mark.asyncio
    async def test_generate_questions_returns_benchmarks(
        self, mock_llm, sample_entities, sample_claims
    ):
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        questions = await qgen.generate_questions(
            "machine_learning", sample_entities, sample_claims, count=3
        )
        assert len(questions) == 3
        assert all(isinstance(q, BenchmarkQuestion) for q in questions)

    @pytest.mark.asyncio
    async def test_questions_have_correct_topic(
        self, mock_llm, sample_entities, sample_claims
    ):
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        questions = await qgen.generate_questions(
            "machine_learning", sample_entities, sample_claims, count=3
        )
        assert all(q.topic == "machine_learning" for q in questions)

    @pytest.mark.asyncio
    async def test_questions_have_difficulty_levels(
        self, mock_llm, sample_entities, sample_claims
    ):
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        questions = await qgen.generate_questions(
            "machine_learning", sample_entities, sample_claims, count=3
        )
        difficulties = {q.difficulty for q in questions}
        assert Difficulty.PHD in difficulties

    @pytest.mark.asyncio
    async def test_questions_have_expected_keywords(
        self, mock_llm, sample_entities, sample_claims
    ):
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        questions = await qgen.generate_questions(
            "machine_learning", sample_entities, sample_claims, count=3
        )
        for q in questions:
            assert len(q.expected_answer_keywords) > 0

    @pytest.mark.asyncio
    async def test_generate_handles_malformed_llm_response(
        self, mock_llm, sample_entities, sample_claims
    ):
        mock_llm.set_question_response = lambda qs: None
        mock_llm._question_response = "not valid json at all {{{"
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        questions = await qgen.generate_questions(
            "machine_learning", sample_entities, sample_claims, count=3
        )
        assert questions == []

    @pytest.mark.asyncio
    async def test_generate_handles_empty_entities(self, mock_llm):
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        questions = await qgen.generate_questions(
            "empty_topic", [], [], count=3
        )
        # Should still call LLM and parse response
        assert isinstance(questions, list)

    @pytest.mark.asyncio
    async def test_evaluate_answer_correct(self, mock_llm):
        mock_llm.set_eval_response(
            {"correct": True, "confidence": 0.9, "reasoning": "Accurate"}
        )
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        result = await qgen.evaluate_answer(
            "What is backpropagation?",
            ["gradient", "chain rule"],
            "Backpropagation computes gradients using the chain rule.",
        )
        assert result["correct"] is True
        assert result["confidence"] >= 0.8

    @pytest.mark.asyncio
    async def test_evaluate_answer_incorrect(self, mock_llm):
        mock_llm.set_eval_response(
            {"correct": False, "confidence": 0.2, "reasoning": "Irrelevant"}
        )
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        result = await qgen.evaluate_answer(
            "What is backpropagation?",
            ["gradient", "chain rule"],
            "I don't know.",
        )
        assert result["correct"] is False

    @pytest.mark.asyncio
    async def test_evaluate_answer_handles_parse_error(self, mock_llm):
        mock_llm._eval_response = "not json"
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        result = await qgen.evaluate_answer("Q?", ["kw"], "answer")
        assert result["correct"] is False
        assert "Parse error" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_question_generation_records_llm_calls(
        self, mock_llm, sample_entities, sample_claims
    ):
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        await qgen.generate_questions(
            "machine_learning", sample_entities, sample_claims, count=3
        )
        assert len(mock_llm.call_log) >= 1
        assert mock_llm.call_log[0]["model"] == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Self-Testing Pipeline
# ---------------------------------------------------------------------------
class TestSelfTesting:
    """Tests for the self-testing pipeline."""

    @pytest.mark.asyncio
    async def test_rag_answer_finds_relevant_entities(
        self, mock_llm, sample_entities, sample_claims, sample_relationships
    ):
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        engine = EvaluationEngine(
            KnowledgeClient.__new__(KnowledgeClient), qgen, max_questions=3
        )
        answer = engine._rag_answer(
            "What is backpropagation?", sample_entities, sample_claims
        )
        assert "Backpropagation" in answer or "backpropagation" in answer.lower()

    @pytest.mark.asyncio
    async def test_rag_answer_insufficient_knowledge(self, mock_llm):
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        engine = EvaluationEngine(
            KnowledgeClient.__new__(KnowledgeClient), qgen, max_questions=3
        )
        answer = engine._rag_answer("What is quantum entanglement?", [], [])
        assert "Insufficient knowledge" in answer

    @pytest.mark.asyncio
    async def test_rag_answer_uses_claims(
        self, mock_llm, sample_entities, sample_claims
    ):
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        engine = EvaluationEngine(
            KnowledgeClient.__new__(KnowledgeClient), qgen, max_questions=3
        )
        answer = engine._rag_answer(
            "How does gradient descent work?", sample_entities, sample_claims
        )
        # Should find gradient-related claims
        assert len(answer) > 0
        assert answer != "Insufficient knowledge to answer this question."


# ---------------------------------------------------------------------------
# Scorecard Calculation
# ---------------------------------------------------------------------------
class TestScorecardCalculation:
    """Tests for expertise scorecard computation."""

    def _make_engine(self, mock_llm) -> EvaluationEngine:
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        return EvaluationEngine(
            KnowledgeClient.__new__(KnowledgeClient), qgen, max_questions=3
        )

    def test_perfect_scores(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = [
            CoverageMetric(area=a, entity_count=15, relationship_count=5, avg_confidence=0.95)
            for a in DEFAULT_TAXONOMY_AREAS
        ]
        test_results = [
            SelfTestResult(
                question_id=f"q{i}", answer="correct", correct=True,
                confidence=0.95, reasoning="Good"
            )
            for i in range(10)
        ]
        conf_dist = {"high": 80, "medium": 15, "low": 5, "very_low": 0}
        gaps: list[KnowledgeGap] = []

        sc = engine._calculate_scorecard(
            "ml", coverage, test_results, conf_dist, gaps
        )
        assert sc.overall_score >= 80
        assert sc.coverage_score == 100.0
        assert sc.accuracy_score == 100.0

    def test_empty_knowledge_scores_zero(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = [
            CoverageMetric(area=a, entity_count=0, relationship_count=0, avg_confidence=0.0)
            for a in DEFAULT_TAXONOMY_AREAS
        ]
        conf_dist = {"high": 0, "medium": 0, "low": 0, "very_low": 0}
        gaps: list[KnowledgeGap] = []

        sc = engine._calculate_scorecard("empty", coverage, [], conf_dist, gaps)
        assert sc.overall_score == 0.0
        assert sc.coverage_score == 0.0
        assert sc.accuracy_score == 0.0

    def test_partial_coverage_scores(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = []
        for i, area in enumerate(DEFAULT_TAXONOMY_AREAS):
            count = 5 if i < 4 else 0
            coverage.append(
                CoverageMetric(area=area, entity_count=count, avg_confidence=0.7)
            )
        test_results = [
            SelfTestResult(
                question_id=f"q{i}", answer="a", correct=(i % 2 == 0),
                confidence=0.6, reasoning=""
            )
            for i in range(6)
        ]
        conf_dist = {"high": 10, "medium": 20, "low": 10, "very_low": 5}
        sc = engine._calculate_scorecard(
            "partial", coverage, test_results, conf_dist, []
        )
        assert 0 < sc.overall_score < 100
        assert sc.coverage_score == 50.0  # 4/8 areas

    def test_scorecard_has_all_fields(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = [
            CoverageMetric(area=a, entity_count=3) for a in DEFAULT_TAXONOMY_AREAS
        ]
        sc = engine._calculate_scorecard(
            "t", coverage, [], {"high": 1, "medium": 1, "low": 0, "very_low": 0}, []
        )
        assert isinstance(sc.evaluated_at, datetime)
        assert sc.topic == "t"
        assert 0 <= sc.overall_score <= 100


# ---------------------------------------------------------------------------
# Gap Analysis
# ---------------------------------------------------------------------------
class TestGapAnalysis:
    """Tests for knowledge gap detection."""

    def _make_engine(self, mock_llm) -> EvaluationEngine:
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        return EvaluationEngine(
            KnowledgeClient.__new__(KnowledgeClient), qgen, max_questions=3
        )

    def test_empty_area_creates_critical_gap(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = [CoverageMetric(area="history", entity_count=0)]
        gaps = engine._find_gaps("ml", coverage, [], {"high": 5, "medium": 5, "low": 0, "very_low": 0})
        critical = [g for g in gaps if g.severity == GapSeverity.CRITICAL]
        assert len(critical) >= 1
        assert any("history" in g.area for g in critical)

    def test_thin_area_creates_moderate_gap(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = [CoverageMetric(area="methodologies", entity_count=2)]
        gaps = engine._find_gaps("ml", coverage, [], {"high": 5, "medium": 5, "low": 0, "very_low": 0})
        moderate = [g for g in gaps if g.severity == GapSeverity.MODERATE]
        assert len(moderate) >= 1

    def test_low_confidence_creates_gap(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = [
            CoverageMetric(area="core", entity_count=10, avg_confidence=0.3)
        ]
        gaps = engine._find_gaps("ml", coverage, [], {"high": 0, "medium": 0, "low": 5, "very_low": 5})
        assert any("confidence" in g.description.lower() for g in gaps)

    def test_high_failure_rate_creates_critical_gap(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = [CoverageMetric(area="a", entity_count=10)]
        failed_results = [
            SelfTestResult(question_id=f"q{i}", answer="wrong", correct=False,
                           confidence=0.2, reasoning="")
            for i in range(8)
        ]
        passed_results = [
            SelfTestResult(question_id="qp", answer="right", correct=True,
                           confidence=0.9, reasoning="")
        ]
        gaps = engine._find_gaps(
            "ml", coverage, failed_results + passed_results,
            {"high": 5, "medium": 5, "low": 0, "very_low": 0}
        )
        assert any(
            g.area == "general_knowledge" and g.severity == GapSeverity.CRITICAL
            for g in gaps
        )

    def test_no_relationships_creates_minor_gap(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = [
            CoverageMetric(area="core", entity_count=5, relationship_count=0)
        ]
        gaps = engine._find_gaps("ml", coverage, [], {"high": 5, "medium": 5, "low": 0, "very_low": 0})
        minor = [g for g in gaps if g.severity == GapSeverity.MINOR]
        assert len(minor) >= 1

    def test_gaps_have_suggested_queries(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = [CoverageMetric(area="history", entity_count=0)]
        gaps = engine._find_gaps("ml", coverage, [], {"high": 5, "medium": 5, "low": 0, "very_low": 0})
        for gap in gaps:
            assert len(gap.suggested_queries) > 0

    def test_well_covered_area_no_entity_gap(self, mock_llm):
        engine = self._make_engine(mock_llm)
        coverage = [
            CoverageMetric(
                area="core", entity_count=10, relationship_count=5,
                avg_confidence=0.9
            )
        ]
        gaps = engine._find_gaps("ml", coverage, [], {"high": 10, "medium": 5, "low": 0, "very_low": 0})
        entity_gaps = [
            g for g in gaps
            if g.area == "core" and g.severity != GapSeverity.MINOR
        ]
        assert len(entity_gaps) == 0


# ---------------------------------------------------------------------------
# Taxonomy Coverage
# ---------------------------------------------------------------------------
class TestTaxonomyCoverage:
    """Tests for taxonomy coverage assessment."""

    def _make_engine(self, mock_llm) -> EvaluationEngine:
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        return EvaluationEngine(
            KnowledgeClient.__new__(KnowledgeClient), qgen, max_questions=3
        )

    def test_entities_classified_into_areas(
        self, mock_llm, sample_entities, sample_relationships
    ):
        engine = self._make_engine(mock_llm)
        metrics = engine._assess_taxonomy_coverage(
            sample_entities, sample_relationships
        )
        assert len(metrics) == len(DEFAULT_TAXONOMY_AREAS)
        total_entities = sum(m.entity_count for m in metrics)
        assert total_entities == len(sample_entities)

    def test_empty_entities_all_zero(self, mock_llm):
        engine = self._make_engine(mock_llm)
        metrics = engine._assess_taxonomy_coverage([], [])
        assert all(m.entity_count == 0 for m in metrics)

    def test_relationships_counted_per_area(
        self, mock_llm, sample_entities, sample_relationships
    ):
        engine = self._make_engine(mock_llm)
        metrics = engine._assess_taxonomy_coverage(
            sample_entities, sample_relationships
        )
        total_rels = sum(m.relationship_count for m in metrics)
        assert total_rels > 0

    def test_confidence_averaged_per_area(
        self, mock_llm, sample_entities, sample_relationships
    ):
        engine = self._make_engine(mock_llm)
        metrics = engine._assess_taxonomy_coverage(
            sample_entities, sample_relationships
        )
        for m in metrics:
            if m.entity_count > 0:
                assert 0 < m.avg_confidence <= 1.0


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
class TestRecommendations:
    """Tests for recommendation generation."""

    def _make_engine(self, mock_llm) -> EvaluationEngine:
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        return EvaluationEngine(
            KnowledgeClient.__new__(KnowledgeClient), qgen, max_questions=3
        )

    def test_critical_gaps_generate_urgent_recommendations(self, mock_llm):
        engine = self._make_engine(mock_llm)
        gaps = [
            KnowledgeGap(
                topic="ml", area="history", severity=GapSeverity.CRITICAL,
                description="Missing"
            )
        ]
        scorecard = ExpertiseScorecard(
            topic="ml", overall_score=20, coverage_score=20,
            depth_score=20, accuracy_score=20, recency_score=20
        )
        coverage = [CoverageMetric(area="history", entity_count=0)]
        recs = engine._generate_recommendations(gaps, scorecard, coverage)
        assert any("URGENT" in r for r in recs)

    def test_satisfactory_knowledge_gets_positive_recommendation(self, mock_llm):
        engine = self._make_engine(mock_llm)
        scorecard = ExpertiseScorecard(
            topic="ml", overall_score=90, coverage_score=90,
            depth_score=90, accuracy_score=90, recency_score=90
        )
        coverage = [
            CoverageMetric(area=a, entity_count=10)
            for a in DEFAULT_TAXONOMY_AREAS
        ]
        recs = engine._generate_recommendations([], scorecard, coverage)
        assert any("satisfactory" in r.lower() for r in recs)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
class TestEvaluatorAPI:
    """Tests for the evaluator FastAPI endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, evaluator_client):
        resp = await evaluator_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "evaluator"
        assert data["status"] in ("healthy", "degraded")

    @pytest.mark.asyncio
    async def test_evaluate_topic(self, evaluator_client):
        resp = await evaluator_client.post("/evaluate/machine_learning")
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic"] == "machine_learning"
        assert "scorecard" in data
        assert "gaps" in data
        assert 0 <= data["scorecard"]["overall_score"] <= 100

    @pytest.mark.asyncio
    async def test_scorecard_after_evaluation(self, evaluator_client):
        await evaluator_client.post("/evaluate/machine_learning")
        resp = await evaluator_client.get("/scorecards/machine_learning")
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic"] == "machine_learning"

    @pytest.mark.asyncio
    async def test_scorecard_not_found(self, evaluator_client):
        resp = await evaluator_client.get("/scorecards/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_scorecard_history(self, evaluator_client):
        await evaluator_client.post("/evaluate/machine_learning")
        await evaluator_client.post("/evaluate/machine_learning")
        resp = await evaluator_client.get("/scorecards/machine_learning/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_scorecard_history_empty(self, evaluator_client):
        resp = await evaluator_client.get("/scorecards/unknown/history")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_gaps_after_evaluation(self, evaluator_client):
        await evaluator_client.post("/evaluate/machine_learning")
        resp = await evaluator_client.get("/gaps/machine_learning")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_gaps_empty_topic(self, evaluator_client):
        resp = await evaluator_client.get("/gaps/unknown")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_evaluation_report_has_recommendations(self, evaluator_client):
        resp = await evaluator_client.post("/evaluate/machine_learning")
        data = resp.json()
        assert "recommendations" in data
        assert isinstance(data["recommendations"], list)
        assert len(data["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_evaluation_report_has_self_test_results(self, evaluator_client):
        resp = await evaluator_client.post("/evaluate/machine_learning")
        data = resp.json()
        assert "self_test_results" in data
        assert len(data["self_test_results"]) > 0


# ---------------------------------------------------------------------------
# Confidence Distribution
# ---------------------------------------------------------------------------
class TestConfidenceDistribution:
    """Tests for confidence analysis."""

    def _make_engine(self, mock_llm) -> EvaluationEngine:
        qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
        return EvaluationEngine(
            KnowledgeClient.__new__(KnowledgeClient), qgen, max_questions=3
        )

    def test_all_high_confidence(self, mock_llm):
        engine = self._make_engine(mock_llm)
        entities = [{"confidence": 0.95} for _ in range(10)]
        dist = engine._analyze_confidence_distribution(entities, [])
        assert dist["high"] == 10
        assert dist["low"] == 0

    def test_mixed_confidence(self, mock_llm):
        engine = self._make_engine(mock_llm)
        items = [
            {"confidence": 0.9},
            {"confidence": 0.7},
            {"confidence": 0.5},
            {"confidence": 0.3},
        ]
        dist = engine._analyze_confidence_distribution(items, [])
        assert dist["high"] == 1
        assert dist["medium"] == 1
        assert dist["low"] == 1
        assert dist["very_low"] == 1

    def test_empty_items(self, mock_llm):
        engine = self._make_engine(mock_llm)
        dist = engine._analyze_confidence_distribution([], [])
        assert sum(dist.values()) == 0


# ---------------------------------------------------------------------------
# Model Validation
# ---------------------------------------------------------------------------
class TestModels:
    """Tests for Pydantic model validation."""

    def test_scorecard_score_bounds(self):
        with pytest.raises(Exception):
            ExpertiseScorecard(
                topic="t", overall_score=101, coverage_score=0,
                depth_score=0, accuracy_score=0, recency_score=0
            )

    def test_scorecard_valid(self):
        sc = ExpertiseScorecard(
            topic="t", overall_score=50, coverage_score=50,
            depth_score=50, accuracy_score=50, recency_score=50
        )
        assert sc.topic == "t"

    def test_knowledge_gap_has_id(self):
        gap = KnowledgeGap(
            topic="t", area="core", severity=GapSeverity.CRITICAL,
            description="Missing"
        )
        assert gap.id  # auto-generated UUID

    def test_benchmark_question_defaults(self):
        q = BenchmarkQuestion(
            topic="t", question="Q?", difficulty=Difficulty.PHD
        )
        assert q.category == QuestionCategory.FACTUAL_RECALL
        assert q.id

    def test_self_test_result_confidence_bounds(self):
        with pytest.raises(Exception):
            SelfTestResult(
                question_id="q1", answer="a", correct=True, confidence=1.5
            )
