"""Pydantic data models for scrape requests, results, events, and crawl history.

These models define the message contracts between the scraper service and the
rest of the selflearning pipeline (via Azure Service Bus).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceType(str, Enum):
    WEB_SEARCH = "web_search"
    DIRECT_URL = "direct_url"
    ACADEMIC = "academic"
    RSS = "rss"


class CrawlStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_ROBOTS = "skipped_robots"
    TIMEOUT = "timeout"


# ---------------------------------------------------------------------------
# Service Bus — inbound message (scrape-requests queue)
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    """A request to scrape content for a given topic/query."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = Field(..., description="Knowledge topic this scrape is for")
    query: str = Field(..., description="Search query or description of what to scrape")
    url: str | None = Field(default=None, description="Specific URL to fetch (optional)")
    priority: Priority = Field(default=Priority.MEDIUM)
    source_type: SourceType = Field(default=SourceType.WEB_SEARCH)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scrape result — one per successfully-scraped URL
# ---------------------------------------------------------------------------

class ScrapeResult(BaseModel):
    """Result of scraping a single URL."""

    request_id: str
    topic: str
    url: str
    content_type: str = Field(default="text/html")
    blob_path: str = Field(..., description="Path in blob storage where raw content is stored")
    content_hash: str = Field(..., description="SHA-256 hash of the content for deduplication")
    title: str = Field(default="")
    text_preview: str = Field(
        default="",
        description="First 500 characters of extracted text",
    )
    word_count: int = Field(default=0)
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scrape stats — aggregate per request
# ---------------------------------------------------------------------------

class ScrapeStats(BaseModel):
    urls_attempted: int = 0
    urls_succeeded: int = 0
    urls_failed: int = 0
    total_bytes: int = 0
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Service Bus — outbound message (scrape-complete topic)
# ---------------------------------------------------------------------------

class ScrapeCompleteEvent(BaseModel):
    """Published to the scrape-complete topic after processing a request."""

    request_id: str
    topic: str
    results: list[ScrapeResult] = Field(default_factory=list)
    stats: ScrapeStats = Field(default_factory=ScrapeStats)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Cosmos DB — crawl history entry
# ---------------------------------------------------------------------------

class CrawlHistoryEntry(BaseModel):
    """Persisted in Cosmos DB to track crawl history per URL."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Cosmos DB document id")
    url: str
    domain: str = Field(default="")
    content_hash: str = Field(default="")
    last_crawled: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: CrawlStatus = Field(default=CrawlStatus.SUCCESS)
    blob_path: str = Field(default="")
    topic: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def partition_key(self) -> str:
        """Cosmos DB partition key — using the domain keeps locality for dedup queries."""
        return self.domain
