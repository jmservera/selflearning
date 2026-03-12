"""Pydantic models for the Orchestrator service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enumerations ──────────────────────────────────────────────────────


class TopicStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETE = "complete"


class PipelineStage(str, Enum):
    IDLE = "idle"
    PLAN = "plan"
    SCRAPE = "scrape"
    EXTRACT = "extract"
    ORGANIZE = "organize"
    REASON = "reason"
    EVALUATE = "evaluate"
    IMPROVE = "improve"


class SourceType(str, Enum):
    WEB = "web"
    ACADEMIC = "academic"
    RSS = "rss"
    SOCIAL = "social"
    API = "api"


class ReasoningType(str, Enum):
    GAP_ANALYSIS = "gap_analysis"
    CONTRADICTION_RESOLUTION = "contradiction_resolution"
    INSIGHT_SYNTHESIS = "insight_synthesis"
    DEPTH_EXPLORATION = "depth_exploration"


# ── Core domain models ────────────────────────────────────────────────


class LearningTopic(BaseModel):
    """A topic the system is learning about."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    priority: int = Field(default=5, ge=1, le=10, description="1=low, 10=critical")
    status: TopicStatus = TopicStatus.ACTIVE
    target_expertise_level: float = Field(
        default=0.9, ge=0.0, le=1.0, description="Target score to reach"
    )
    current_score: float = Field(default=0.0, ge=0.0, le=1.0)
    iteration_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Partition key for Cosmos DB
    @property
    def partition_key(self) -> str:
        return self.name


class PipelineState(BaseModel):
    """Current pipeline state for a topic."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    current_stage: PipelineStage = PipelineStage.IDLE
    iteration: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pending_requests: list[str] = Field(default_factory=list)
    completed_requests: list[str] = Field(default_factory=list)
    error_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class LearningPlan(BaseModel):
    """A plan for what to learn next for a topic."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    iteration: int
    target_areas: list[str] = Field(default_factory=list)
    scrape_queries: list[str] = Field(default_factory=list)
    reasoning_tasks: list[ReasoningType] = Field(default_factory=list)
    priority_weights: dict[str, float] = Field(default_factory=dict)
    rationale: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LoopIteration(BaseModel):
    """Record of a single learning loop iteration."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    iteration_number: int
    topic: str
    stages_completed: list[PipelineStage] = Field(default_factory=list)
    duration_seconds: float = 0.0
    improvements_made: list[str] = Field(default_factory=list)
    score_before: float = 0.0
    score_after: float = 0.0
    scrape_requests_sent: int = 0
    documents_extracted: int = 0
    insights_generated: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class ScrapeRequest(BaseModel):
    """A request to scrape content."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    query: str
    priority: int = Field(default=5, ge=1, le=10)
    source_type: SourceType = SourceType.WEB
    max_results: int = 10
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReasoningRequest(BaseModel):
    """A request for the Reasoner service."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    reasoning_type: ReasoningType
    context: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=1, le=10)


class OrchestratorStatus(BaseModel):
    """Current orchestrator status snapshot."""

    active_topics: list[str] = Field(default_factory=list)
    paused_topics: list[str] = Field(default_factory=list)
    current_stages: dict[str, PipelineStage] = Field(default_factory=dict)
    iterations_completed: dict[str, int] = Field(default_factory=dict)
    scores: dict[str, float] = Field(default_factory=dict)
    next_actions: dict[str, str] = Field(default_factory=dict)
    loop_running: bool = False
    uptime_seconds: float = 0.0


# ── Service Bus message envelopes ─────────────────────────────────────


class CompletionEvent(BaseModel):
    """Generic completion event from downstream services."""

    request_id: str
    topic: str
    status: str = "success"
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvaluationResult(BaseModel):
    """Evaluation scorecard from the Evaluator."""

    request_id: str
    topic: str
    overall_score: float = Field(ge=0.0, le=1.0)
    coverage_score: float = Field(ge=0.0, le=1.0)
    depth_score: float = Field(ge=0.0, le=1.0)
    accuracy_score: float = Field(ge=0.0, le=1.0)
    gaps: list[str] = Field(default_factory=list)
    weak_areas: list[str] = Field(default_factory=list)
    strong_areas: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Strategy models ───────────────────────────────────────────────────


class LearningStrategy(BaseModel):
    """Persisted learning strategy for a topic."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    mode: str = "breadth"  # breadth | depth | verification | diversify
    focus_areas: list[str] = Field(default_factory=list)
    source_diversity_target: int = 5
    confidence_threshold: float = 0.7
    recent_gaps: list[str] = Field(default_factory=list)
    iteration_scores: list[float] = Field(default_factory=list)
    stale_count: int = 0
    backoff_seconds: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Working memory models ─────────────────────────────────────────────


class MemoryItem(BaseModel):
    """A single item in working memory."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    content: str
    item_type: str = "finding"  # finding | gap | insight | plan | error
    relevance: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)
