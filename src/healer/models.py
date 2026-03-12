"""Pydantic models for the Healer service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enumerations ──────────────────────────────────────────────────────


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class HealingActionType(str, Enum):
    RESTART = "restart"
    REPLAY = "replay"
    FAILOVER = "failover"
    SCALE = "scale"
    PROMPT_TUNE = "prompt_tune"
    CIRCUIT_OPEN = "circuit_open"
    CIRCUIT_CLOSE = "circuit_close"
    DLQ_DISCARD = "dlq_discard"


class HealingOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    PENDING = "pending"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ── Core domain models ────────────────────────────────────────────────


class ServiceHealth(BaseModel):
    """Health snapshot for a monitored service."""

    service_name: str
    status: ServiceStatus = ServiceStatus.UNKNOWN
    last_check: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    consecutive_failures: int = 0
    error_count_window: int = 0
    success_count_window: int = 0
    latency_ms: float = 0.0
    latency_p95_ms: float = 0.0
    last_error: str | None = None
    endpoint: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def error_rate(self) -> float:
        total = self.error_count_window + self.success_count_window
        if total == 0:
            return 0.0
        return self.error_count_window / total


class HealingAction(BaseModel):
    """A healing action taken by the Healer."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    service: str
    action_type: HealingActionType
    reason: str
    outcome: HealingOutcome = HealingOutcome.PENDING
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float | None = None


class DLQMessage(BaseModel):
    """A message read from a dead-letter queue."""

    message_id: str
    queue_or_topic: str
    body: dict[str, Any] = Field(default_factory=dict)
    dead_letter_reason: str | None = None
    dead_letter_description: str | None = None
    enqueued_time: datetime | None = None
    delivery_count: int = 0
    replay_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DLQStats(BaseModel):
    """Dead-letter queue statistics."""

    queue_name: str
    message_count: int = 0
    oldest_message_age_seconds: float | None = None
    error_patterns: dict[str, int] = Field(default_factory=dict)
    last_checked: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CircuitBreakerState(BaseModel):
    """Circuit breaker state for a service."""

    service: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure: datetime | None = None
    last_success: datetime | None = None
    opened_at: datetime | None = None
    half_open_calls: int = 0


class HealerStatus(BaseModel):
    """Overall Healer status snapshot."""

    services_monitored: list[str] = Field(default_factory=list)
    service_statuses: dict[str, ServiceStatus] = Field(default_factory=dict)
    circuit_states: dict[str, CircuitState] = Field(default_factory=dict)
    actions_taken_today: int = 0
    actions_taken_total: int = 0
    current_issues: list[str] = Field(default_factory=list)
    dlq_total_messages: int = 0
    uptime_seconds: float = 0.0
    last_health_check: datetime | None = None
    last_dlq_scan: datetime | None = None


class HealingEvent(BaseModel):
    """Event published to the healing-events topic."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: HealingActionType
    service: str
    details: dict[str, Any] = Field(default_factory=dict)
    action_taken: str
    outcome: HealingOutcome = HealingOutcome.PENDING
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScalingRecommendation(BaseModel):
    """A scaling recommendation based on queue depth analysis."""

    service: str
    current_queue_depth: int
    recommended_action: str  # scale_up | scale_down | no_change
    recommended_replicas: int | None = None
    reason: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PromptTuningResult(BaseModel):
    """Result of prompt tuning analysis."""

    service: str
    current_prompt_hash: str = ""
    suggested_changes: list[str] = Field(default_factory=list)
    quality_before: float = 0.0
    quality_after: float | None = None
    analysis: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
