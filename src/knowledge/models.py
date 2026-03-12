"""Pydantic models for the Knowledge Service.

Document types stored in Cosmos DB: Entity, Relationship, Claim, Source.
All documents share a common `topic` partition key.
"""

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


# ── Enums ──────────────────────────────────────────────────────────────────


class DocType(str, Enum):
    ENTITY = "Entity"
    RELATIONSHIP = "Relationship"
    CLAIM = "Claim"
    SOURCE = "Source"


class EntityType(str, Enum):
    CONCEPT = "Concept"
    PERSON = "Person"
    ORGANIZATION = "Organization"
    EVENT = "Event"
    LOCATION = "Location"
    TECHNOLOGY = "Technology"
    THEORY = "Theory"
    METHOD = "Method"
    ARTIFACT = "Artifact"
    OTHER = "Other"


# ── Core Documents ─────────────────────────────────────────────────────────


class Entity(BaseModel):
    """A knowledge-graph entity stored in Cosmos DB."""

    id: str = Field(default_factory=_new_id)
    type: DocType = DocType.ENTITY
    name: str
    entity_type: EntityType = EntityType.CONCEPT
    description: str = ""
    topic: str
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_urls: list[str] = Field(default_factory=list)
    source_count: int = 0
    embedding: list[float] | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Relationship(BaseModel):
    """A directed edge between two entities."""

    id: str = Field(default_factory=_new_id)
    type: DocType = DocType.RELATIONSHIP
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    description: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    topic: str
    sources: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Claim(BaseModel):
    """An assertive statement extracted from sources."""

    id: str = Field(default_factory=_new_id)
    type: DocType = DocType.CLAIM
    statement: str
    topic: str
    entities: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_url: str = ""
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    verified: bool = False
    verified_at: datetime | None = None
    contradictions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Source(BaseModel):
    """A content source the system has scraped."""

    id: str = Field(default_factory=_new_id)
    type: DocType = DocType.SOURCE
    url: str
    title: str = ""
    content_type: str = ""
    credibility_score: float = Field(default=0.5, ge=0.0, le=1.0)
    content_hash: str = ""
    last_accessed: datetime = Field(default_factory=_utcnow)
    topic: str = ""
    blob_path: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ── Composite / Request / Response Models ──────────────────────────────────


class KnowledgeUnit(BaseModel):
    """Bulk ingest payload from the extraction pipeline."""

    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    """Single item returned from a hybrid search."""

    id: str
    doc_type: DocType
    name: str = ""
    statement: str = ""
    topic: str = ""
    confidence: float = 0.0
    score: float = 0.0
    highlights: dict[str, list[str]] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Paged search response."""

    items: list[SearchResultItem] = Field(default_factory=list)
    total_count: int = 0
    facets: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class TopicStats(BaseModel):
    """Aggregate knowledge statistics for a topic."""

    topic: str
    entity_count: int = 0
    relationship_count: int = 0
    claim_count: int = 0
    source_count: int = 0
    avg_confidence: float = 0.0
    coverage_areas: list[str] = Field(default_factory=list)
    last_updated: datetime | None = None


class TopicSummary(BaseModel):
    """Human-readable summary for a topic."""

    topic: str
    summary: str = ""
    key_entities: list[str] = Field(default_factory=list)
    key_claims: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    generated_at: datetime = Field(default_factory=_utcnow)


class EntitySearchParams(BaseModel):
    """Query parameters for entity search."""

    topic: str | None = None
    entity_type: EntityType | None = None
    query: str | None = None
    min_confidence: float = 0.0
    limit: int = Field(default=50, le=200)
    offset: int = 0


class RelationshipQuery(BaseModel):
    """Query parameters for relationship lookup."""

    entity_id: str | None = None
    relationship_type: str | None = None
    topic: str | None = None
    limit: int = Field(default=50, le=200)


class ClaimQuery(BaseModel):
    """Query parameters for claim lookup."""

    topic: str | None = None
    entity_id: str | None = None
    min_confidence: float = 0.0
    verified_only: bool = False
    limit: int = Field(default=50, le=200)


class HybridSearchRequest(BaseModel):
    """Request for hybrid vector + keyword search."""

    query: str
    topic: str | None = None
    doc_types: list[DocType] | None = None
    min_confidence: float = 0.0
    limit: int = Field(default=20, le=100)
    search_mode: str = Field(default="hybrid", pattern="^(hybrid|vector|keyword)$")


class BulkIngestResponse(BaseModel):
    """Response from a bulk ingest operation."""

    entities_upserted: int = 0
    relationships_upserted: int = 0
    claims_upserted: int = 0
    sources_upserted: int = 0
    entities_merged: int = 0
    errors: list[str] = Field(default_factory=list)
