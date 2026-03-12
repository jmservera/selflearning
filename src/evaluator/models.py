"""Pydantic models for the evaluator service."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Difficulty(str, Enum):
    PHD = "phd"
    MASTERS = "masters"
    UNDERGRAD = "undergrad"


class GapSeverity(str, Enum):
    CRITICAL = "critical"
    MODERATE = "moderate"
    MINOR = "minor"


class QuestionCategory(str, Enum):
    FACTUAL_RECALL = "factual_recall"
    REASONING = "reasoning"
    SYNTHESIS = "synthesis"
    APPLICATION = "application"


class CoverageMetric(BaseModel):
    """Coverage statistics for a single taxonomy area."""

    area: str
    entity_count: int = 0
    relationship_count: int = 0
    avg_confidence: float = 0.0


class ExpertiseScorecard(BaseModel):
    """Overall expertise assessment for a topic."""

    topic: str
    overall_score: float = Field(ge=0, le=100)
    coverage_score: float = Field(ge=0, le=100)
    depth_score: float = Field(ge=0, le=100)
    accuracy_score: float = Field(ge=0, le=100)
    recency_score: float = Field(ge=0, le=100)
    confidence_distribution: dict[str, int] = Field(default_factory=dict)
    gap_count: int = 0
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeGap(BaseModel):
    """An identified gap in the knowledge graph."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str
    area: str
    severity: GapSeverity
    description: str
    entity_count: int = 0
    suggested_queries: list[str] = Field(default_factory=list)


class BenchmarkQuestion(BaseModel):
    """A generated benchmark question for self-testing."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str
    question: str
    difficulty: Difficulty
    expected_answer_keywords: list[str] = Field(default_factory=list)
    category: QuestionCategory = QuestionCategory.FACTUAL_RECALL


class SelfTestResult(BaseModel):
    """Result of answering a single benchmark question."""

    question_id: str
    answer: str
    correct: bool
    confidence: float = Field(ge=0, le=1)
    reasoning: str = ""


class EvaluationReport(BaseModel):
    """Full evaluation report for a topic."""

    topic: str
    scorecard: ExpertiseScorecard
    gaps: list[KnowledgeGap] = Field(default_factory=list)
    self_test_results: list[SelfTestResult] = Field(default_factory=list)
    taxonomy_coverage: list[CoverageMetric] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class EvaluationRequest(BaseModel):
    """Request to evaluate a topic."""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str
    max_questions: int = 20


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    service: str = "evaluator"
    version: str = "0.1.0"
    checks: dict[str, str] = Field(default_factory=dict)
