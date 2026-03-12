"""Pydantic models for the Extractor service.

Defines the structured knowledge units produced by the extraction pipeline.
"""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


class RawContent(BaseModel):
    """Reference to raw scraped content stored in blob storage."""

    blob_path: str
    url: str
    content_type: str = "text/html"
    metadata: dict = Field(default_factory=dict)


class Entity(BaseModel):
    """An extracted named entity, concept, or key term."""

    id: str = Field(default_factory=_uuid)
    name: str
    entity_type: str  # person|organization|concept|technology|method|metric|location|event|other
    description: str = ""
    topic: str = ""
    confidence: float = 0.0
    source_url: str = ""
    embedding: Optional[list[float]] = None


class Relationship(BaseModel):
    """A directed relationship between two entities."""

    id: str = Field(default_factory=_uuid)
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    description: str = ""
    confidence: float = 0.0


class Claim(BaseModel):
    """A factual assertion extracted from content with evidence tracking."""

    id: str = Field(default_factory=_uuid)
    statement: str
    topic: str = ""
    confidence: float = 0.0
    source_url: str = ""
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)


class Summary(BaseModel):
    """A summary at a specific level of detail."""

    id: str = Field(default_factory=_uuid)
    topic: str = ""
    level: str = "overview"  # overview | subtopic | finding
    content: str = ""
    entity_refs: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Complete result of an extraction pipeline run."""

    request_id: str
    topic: str
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    summaries: list[Summary] = Field(default_factory=list)
