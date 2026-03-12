"""Pydantic models for the Reasoner service.

Defines request/response contracts for all reasoning operations.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


class ReasoningRequest(BaseModel):
    """Incoming reasoning request from the orchestrator."""

    request_id: str = Field(default_factory=_uuid)
    topic: str
    reasoning_type: str  # gap_analysis | contradiction_resolution | synthesis | depth_probe
    context: dict[str, Any] = Field(default_factory=dict)


class Insight(BaseModel):
    """A higher-order conclusion synthesized from atomic knowledge."""

    id: str = Field(default_factory=_uuid)
    topic: str = ""
    statement: str
    supporting_entities: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reasoning_chain: str = ""


class KnowledgeGap(BaseModel):
    """An area where knowledge is thin, missing, or low-confidence."""

    id: str = Field(default_factory=_uuid)
    topic: str = ""
    area: str
    severity: str = "moderate"  # critical | moderate | minor
    description: str = ""
    suggested_queries: list[str] = Field(default_factory=list)


class ContradictionResolution(BaseModel):
    """Resolution of conflicting claims."""

    claim_ids: list[str] = Field(default_factory=list)
    resolution: str = ""
    confidence: float = 0.0
    reasoning: str = ""


class ReasoningMeta(BaseModel):
    """Metadata about a reasoning run."""

    reasoning_type: str = ""
    model_used: str = ""
    total_tokens: int = 0
    latency_ms: float = 0.0
    knowledge_items_considered: int = 0


class ReasoningResult(BaseModel):
    """Complete output of a reasoning operation."""

    request_id: str
    topic: str
    insights: list[Insight] = Field(default_factory=list)
    gaps: list[KnowledgeGap] = Field(default_factory=list)
    resolutions: list[ContradictionResolution] = Field(default_factory=list)
    meta: Optional[ReasoningMeta] = None
