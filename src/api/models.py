"""API request / response models for the API Gateway."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Topic models ───────────────────────────────────────────────────────────


class TopicStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"


class TopicCreate(BaseModel):
    """Request body for creating a new learning topic."""

    name: str
    description: str = ""
    priority: int = Field(default=5, ge=1, le=10)
    target_expertise: float = Field(default=0.8, ge=0.0, le=1.0)
    seed_urls: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class TopicResponse(BaseModel):
    """Summary representation of a topic."""

    id: str = Field(default_factory=_new_id)
    name: str
    description: str = ""
    status: TopicStatus = TopicStatus.PENDING
    priority: int = 5
    current_expertise: float = 0.0
    target_expertise: float = 0.8
    entity_count: int = 0
    claim_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class TopicDetail(TopicResponse):
    """Detailed topic information including expertise scorecard."""

    seed_urls: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    coverage_areas: list[str] = Field(default_factory=list)
    avg_confidence: float = 0.0
    relationship_count: int = 0
    source_count: int = 0
    learning_cycles_completed: int = 0
    last_learning_cycle: datetime | None = None
    gap_areas: list[str] = Field(default_factory=list)


class PriorityUpdate(BaseModel):
    """Request body for adjusting topic priority."""

    priority: int = Field(ge=1, le=10)


# ── Search models ──────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    """Parameters for a knowledge graph search."""

    q: str
    topic: str | None = None
    doc_type: str | None = None
    min_confidence: float = 0.0
    limit: int = Field(default=20, le=100)
    mode: str = Field(default="hybrid", pattern="^(hybrid|vector|keyword)$")


class SearchResultItem(BaseModel):
    id: str
    doc_type: str = ""
    name: str = ""
    statement: str = ""
    topic: str = ""
    confidence: float = 0.0
    score: float = 0.0
    highlights: dict[str, list[str]] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    items: list[SearchResultItem] = Field(default_factory=list)
    total_count: int = 0
    facets: dict[str, Any] = Field(default_factory=dict)


# ── Chat models ────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    question: str
    topic: str | None = None
    context: str | None = None
    include_sources: bool = True


class Citation(BaseModel):
    """A source citation in a chat response."""

    entity_id: str = ""
    name: str = ""
    source_url: str = ""
    confidence: float = 0.0
    snippet: str = ""


class ChatResponse(BaseModel):
    """Response from the expert chat endpoint."""

    answer: str
    confidence: float = 0.0
    sources: list[Citation] = Field(default_factory=list)
    topic: str | None = None
    model: str = ""
    tokens_used: int = 0


# ── Dashboard models ───────────────────────────────────────────────────────


class ServiceHealth(BaseModel):
    """Health status of a single service."""

    name: str
    url: str
    status: str = "unknown"  # healthy, unhealthy, unreachable
    latency_ms: float = 0.0
    last_checked: datetime = Field(default_factory=_utcnow)


class SystemHealth(BaseModel):
    """Overall system health."""

    status: str = "healthy"
    services: list[ServiceHealth] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_utcnow)


class DashboardStatus(BaseModel):
    """Current system status for the dashboard."""

    current_activity: str = "idle"
    active_topics: int = 0
    total_entities: int = 0
    total_claims: int = 0
    active_learning_cycles: int = 0
    system_health: str = "healthy"
    last_activity: datetime | None = None


class LearningProgress(BaseModel):
    """Learning progress across all topics."""

    topics: list[TopicResponse] = Field(default_factory=list)
    overall_expertise: float = 0.0
    total_entities: int = 0
    total_claims: int = 0
    total_sources: int = 0
    learning_rate: float = 0.0  # entities per hour


class ActivityLog(BaseModel):
    """A single activity log entry."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utcnow)
    service: str = ""
    action: str = ""
    details: str = ""
    topic: str | None = None
    success: bool = True


class DecisionLog(BaseModel):
    """A decision the agent made."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utcnow)
    decision: str = ""
    reasoning: str = ""
    topic: str | None = None
    outcome: str | None = None


# ── WebSocket models ───────────────────────────────────────────────────────


class WSMessage(BaseModel):
    """Generic WebSocket message."""

    type: str  # status_update, log_entry, error
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)
