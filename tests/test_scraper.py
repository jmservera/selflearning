"""Tests for the Scraper service.

These tests define expected behavioral contracts for the scraper service.
They use inline reference implementations that validate the specified
requirements. When the scraper service is implemented, update imports
to reference the actual service modules.
"""

import asyncio
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from bs4 import BeautifulSoup
from httpx import ASGITransport, AsyncClient


# ============================================================================
# Reference implementations — behavioral contracts for the scraper
# ============================================================================


class RobotsParser:
    """Parses and enforces robots.txt rules."""

    def __init__(self, content: str, user_agent: str = "*") -> None:
        self._rules: dict[str, list[str]] = defaultdict(list)
        self._sitemaps: list[str] = []
        self._crawl_delay: float | None = None
        self._parse(content, user_agent)

    def _parse(self, content: str, target_agent: str) -> None:
        current_agents: list[str] = []
        for line in content.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()

            if key == "user-agent":
                current_agents = [value]
            elif key == "disallow" and value:
                for agent in current_agents:
                    if agent == target_agent or agent == "*":
                        self._rules["disallow"].append(value)
            elif key == "allow" and value:
                for agent in current_agents:
                    if agent == target_agent or agent == "*":
                        self._rules["allow"].append(value)
            elif key == "sitemap":
                self._sitemaps.append(value)
            elif key == "crawl-delay":
                for agent in current_agents:
                    if agent == target_agent or agent == "*":
                        try:
                            self._crawl_delay = float(value)
                        except ValueError:
                            pass

    def is_allowed(self, path: str) -> bool:
        """Check if a path is allowed by the robots.txt rules."""
        # Allow rules take precedence over disallow for more specific paths
        for allowed in self._rules.get("allow", []):
            if path.startswith(allowed):
                return True
        for disallowed in self._rules.get("disallow", []):
            if path.startswith(disallowed):
                return False
        return True

    @property
    def crawl_delay(self) -> float | None:
        return self._crawl_delay

    @property
    def sitemaps(self) -> list[str]:
        return self._sitemaps


class RateLimiter:
    """Token-bucket rate limiter for polite scraping."""

    def __init__(self, requests_per_second: float = 1.0) -> None:
        self._interval = 1.0 / requests_per_second
        self._last_request: dict[str, float] = {}

    def can_request(self, domain: str) -> bool:
        now = time.monotonic()
        last = self._last_request.get(domain, 0)
        return (now - last) >= self._interval

    def record_request(self, domain: str) -> None:
        self._last_request[domain] = time.monotonic()

    async def wait_if_needed(self, domain: str) -> None:
        now = time.monotonic()
        last = self._last_request.get(domain, 0)
        wait_time = self._interval - (now - last)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self.record_request(domain)


def extract_content(html: str) -> dict[str, Any]:
    """Extract structured content from an HTML page."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # Extract main text
    text = soup.get_text(separator="\n", strip=True)

    # Extract links
    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        link_text = a_tag.get_text(strip=True)
        if href and not href.startswith(("#", "javascript:", "mailto:")):
            links.append({"href": href, "text": link_text})

    # Extract headings
    headings = []
    for level in range(1, 7):
        for h in soup.find_all(f"h{level}"):
            headings.append({"level": level, "text": h.get_text(strip=True)})

    # Extract metadata
    meta: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name", tag.get("property", ""))
        content = tag.get("content", "")
        if name and content:
            meta[name] = content

    return {
        "title": title,
        "text": text,
        "links": links,
        "headings": headings,
        "meta": meta,
        "word_count": len(text.split()),
    }


class URLDeduplicator:
    """Tracks seen URLs to avoid duplicate crawls."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def normalize(self, url: str) -> str:
        """Normalize a URL for deduplication."""
        parsed = urlparse(url)
        # Remove fragments, normalize scheme and host
        normalized = f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path}"
        # Remove trailing slash for consistency
        if normalized.endswith("/") and len(parsed.path) > 1:
            normalized = normalized[:-1]
        return normalized

    def is_new(self, url: str) -> bool:
        """Check if URL hasn't been seen before."""
        normalized = self.normalize(url)
        if normalized in self._seen:
            return False
        self._seen.add(normalized)
        return True

    @property
    def count(self) -> int:
        return len(self._seen)


@dataclass
class ServiceBusMessage:
    """Expected Service Bus message format for scrape events."""

    request_id: str
    url: str
    topic: str
    status: str
    content_type: str = "text/html"
    blob_path: str = ""
    word_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "request_id": self.request_id,
            "url": self.url,
            "topic": self.topic,
            "status": self.status,
            "content_type": self.content_type,
            "blob_path": self.blob_path,
            "word_count": self.word_count,
        }
        if self.error:
            result["error"] = self.error
        return result


# ============================================================================
# Tests
# ============================================================================


class TestRobotsRespect:
    """Test robots.txt parsing and compliance."""

    ROBOTS_TXT = """
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /private/public-page
Crawl-delay: 2

User-agent: BadBot
Disallow: /

Sitemap: https://example.com/sitemap.xml
"""

    def test_disallowed_path_rejected(self):
        parser = RobotsParser(self.ROBOTS_TXT)
        assert parser.is_allowed("/private/secret") is False

    def test_allowed_path_accepted(self):
        parser = RobotsParser(self.ROBOTS_TXT)
        assert parser.is_allowed("/public/page") is True

    def test_allow_overrides_disallow_for_specific_path(self):
        parser = RobotsParser(self.ROBOTS_TXT)
        assert parser.is_allowed("/private/public-page") is True

    def test_admin_path_blocked(self):
        parser = RobotsParser(self.ROBOTS_TXT)
        assert parser.is_allowed("/admin/dashboard") is False

    def test_root_path_allowed(self):
        parser = RobotsParser(self.ROBOTS_TXT)
        assert parser.is_allowed("/") is True

    def test_crawl_delay_parsed(self):
        parser = RobotsParser(self.ROBOTS_TXT)
        assert parser.crawl_delay == 2.0

    def test_sitemap_extracted(self):
        parser = RobotsParser(self.ROBOTS_TXT)
        assert "https://example.com/sitemap.xml" in parser.sitemaps

    def test_empty_robots_allows_everything(self):
        parser = RobotsParser("")
        assert parser.is_allowed("/anything") is True
        assert parser.crawl_delay is None

    def test_disallow_all(self):
        parser = RobotsParser("User-agent: *\nDisallow: /")
        assert parser.is_allowed("/anything") is False

    def test_comments_ignored(self):
        parser = RobotsParser(
            "User-agent: * # all bots\nDisallow: /secret # no access"
        )
        assert parser.is_allowed("/secret") is False
        assert parser.is_allowed("/public") is True


class TestRateLimiting:
    """Test rate limiting for polite scraping."""

    def test_first_request_always_allowed(self):
        limiter = RateLimiter(requests_per_second=1.0)
        assert limiter.can_request("example.com") is True

    def test_immediate_second_request_blocked(self):
        limiter = RateLimiter(requests_per_second=1.0)
        limiter.record_request("example.com")
        assert limiter.can_request("example.com") is False

    def test_different_domains_independent(self):
        limiter = RateLimiter(requests_per_second=1.0)
        limiter.record_request("a.com")
        assert limiter.can_request("b.com") is True

    def test_request_allowed_after_interval(self):
        limiter = RateLimiter(requests_per_second=100.0)  # 10ms interval
        limiter.record_request("example.com")
        time.sleep(0.015)
        assert limiter.can_request("example.com") is True

    @pytest.mark.asyncio
    async def test_wait_if_needed_respects_rate(self):
        limiter = RateLimiter(requests_per_second=100.0)
        limiter.record_request("example.com")
        start = time.monotonic()
        await limiter.wait_if_needed("example.com")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.005  # at least some wait occurred

    def test_high_rate_limit(self):
        limiter = RateLimiter(requests_per_second=1000.0)
        limiter.record_request("example.com")
        # With 1000 rps, 1ms interval — almost always allowed
        time.sleep(0.002)
        assert limiter.can_request("example.com") is True


class TestContentExtraction:
    """Test HTML content extraction."""

    SAMPLE_HTML = """
    <html>
    <head>
        <title>Machine Learning Overview</title>
        <meta name="description" content="An overview of ML concepts">
        <meta property="og:title" content="ML Overview">
    </head>
    <body>
        <nav><a href="/home">Home</a></nav>
        <h1>Introduction to Machine Learning</h1>
        <p>Machine learning is a subset of artificial intelligence.</p>
        <h2>Supervised Learning</h2>
        <p>Supervised learning uses labeled data.</p>
        <a href="https://example.com/deep-learning">Deep Learning</a>
        <a href="https://example.com/reinforcement">RL Guide</a>
        <script>console.log("remove me");</script>
        <style>.hidden { display: none; }</style>
        <footer><p>Copyright 2024</p></footer>
    </body>
    </html>
    """

    def test_title_extracted(self):
        result = extract_content(self.SAMPLE_HTML)
        assert result["title"] == "Machine Learning Overview"

    def test_scripts_removed(self):
        result = extract_content(self.SAMPLE_HTML)
        assert "console.log" not in result["text"]

    def test_styles_removed(self):
        result = extract_content(self.SAMPLE_HTML)
        assert ".hidden" not in result["text"]

    def test_nav_removed(self):
        result = extract_content(self.SAMPLE_HTML)
        # Nav content should be removed
        assert "Home" not in result["text"] or "Machine learning" in result["text"]

    def test_links_extracted(self):
        result = extract_content(self.SAMPLE_HTML)
        hrefs = [l["href"] for l in result["links"]]
        assert "https://example.com/deep-learning" in hrefs

    def test_javascript_links_excluded(self):
        html = '<html><body><a href="javascript:void(0)">Click</a></body></html>'
        result = extract_content(html)
        assert len(result["links"]) == 0

    def test_headings_extracted(self):
        result = extract_content(self.SAMPLE_HTML)
        h1s = [h for h in result["headings"] if h["level"] == 1]
        assert len(h1s) >= 1
        assert "Machine Learning" in h1s[0]["text"]

    def test_metadata_extracted(self):
        result = extract_content(self.SAMPLE_HTML)
        assert result["meta"]["description"] == "An overview of ML concepts"

    def test_word_count_positive(self):
        result = extract_content(self.SAMPLE_HTML)
        assert result["word_count"] > 0

    def test_empty_html(self):
        result = extract_content("<html><body></body></html>")
        assert result["title"] == ""
        assert result["word_count"] == 0


class TestURLDeduplication:
    """Test URL deduplication logic."""

    def test_first_url_is_new(self):
        dedup = URLDeduplicator()
        assert dedup.is_new("https://example.com/page") is True

    def test_duplicate_url_rejected(self):
        dedup = URLDeduplicator()
        dedup.is_new("https://example.com/page")
        assert dedup.is_new("https://example.com/page") is False

    def test_different_urls_both_accepted(self):
        dedup = URLDeduplicator()
        assert dedup.is_new("https://a.com") is True
        assert dedup.is_new("https://b.com") is True

    def test_fragment_ignored(self):
        dedup = URLDeduplicator()
        dedup.is_new("https://example.com/page#section1")
        assert dedup.is_new("https://example.com/page#section2") is False

    def test_case_normalized(self):
        dedup = URLDeduplicator()
        dedup.is_new("https://EXAMPLE.COM/page")
        assert dedup.is_new("https://example.com/page") is False

    def test_trailing_slash_normalized(self):
        dedup = URLDeduplicator()
        dedup.is_new("https://example.com/page/")
        assert dedup.is_new("https://example.com/page") is False

    def test_count_tracks_unique_urls(self):
        dedup = URLDeduplicator()
        dedup.is_new("https://a.com")
        dedup.is_new("https://b.com")
        dedup.is_new("https://a.com")  # duplicate
        assert dedup.count == 2


class TestServiceBusMessage:
    """Test Service Bus message format for scrape events."""

    def test_success_message_format(self):
        msg = ServiceBusMessage(
            request_id="abc-123",
            url="https://example.com/page",
            topic="machine_learning",
            status="completed",
            blob_path="raw-content/ml/abc.html",
            word_count=500,
        )
        d = msg.to_dict()
        assert d["request_id"] == "abc-123"
        assert d["status"] == "completed"
        assert "error" not in d

    def test_error_message_includes_error(self):
        msg = ServiceBusMessage(
            request_id="abc-124",
            url="https://example.com/broken",
            topic="ml",
            status="failed",
            error="HTTP 404 Not Found",
        )
        d = msg.to_dict()
        assert d["status"] == "failed"
        assert d["error"] == "HTTP 404 Not Found"

    def test_message_requires_essential_fields(self):
        msg = ServiceBusMessage(
            request_id="id", url="https://x.com", topic="t", status="pending"
        )
        d = msg.to_dict()
        assert all(k in d for k in ["request_id", "url", "topic", "status"])


# ============================================================================
# FastAPI endpoint tests
# ============================================================================

_SCRAPER_BARE_MODULES = frozenset({
    "main", "config", "models", "scraper", "service_bus", "storage",
})


def _setup_scraper_path() -> None:
    """Flush stale bare-module caches and put src/scraper/ first on sys.path.

    src/scraper/ must come BEFORE src/ so that ``import scraper`` inside
    main.py resolves to scraper.py (the WebScraper module) rather than the
    src/scraper/ package directory.  Other service directories are removed
    to prevent cross-contamination when running the full test suite.
    """
    src_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src"))
    svc_dir = os.path.normpath(os.path.join(src_dir, "scraper"))
    # Remove all service directories to avoid cross-contamination
    other_svcs = {os.path.normpath(os.path.join(src_dir, s))
                  for s in ("extractor", "orchestrator", "healer", "reasoner")}
    for name in _SCRAPER_BARE_MODULES:
        sys.modules.pop(name, None)
    sys.path[:] = [p for p in sys.path
                   if os.path.normpath(p) not in other_svcs
                   and os.path.normpath(p) != svc_dir]
    # Insert BEFORE src/ so bare `import scraper` finds scraper.py, not the package
    src_positions = [i for i, p in enumerate(sys.path) if os.path.normpath(p) == src_dir]
    insert_pos = src_positions[0] if src_positions else 0
    sys.path.insert(insert_pos, svc_dir)


class TestEndpoints:
    """Tests for scraper FastAPI endpoints (/health, /status)."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked module-level globals."""
        saved_path = sys.path[:]
        _setup_scraper_path()
        import main as scraper_mod  # noqa: PLC0415

        mock_blob = MagicMock()
        mock_history = MagicMock()
        mock_history.get_crawl_stats = AsyncMock(return_value={"total": 10, "failed": 1})
        mock_consumer = MagicMock()
        mock_consumer.stats = {"messages_processed": 5}
        mock_publisher = MagicMock()
        mock_publisher.stats = {"messages_published": 3}

        scraper_mod._blob_client = mock_blob
        scraper_mod._history_client = mock_history
        scraper_mod._consumer = mock_consumer
        scraper_mod._publisher = mock_publisher
        scraper_mod._started_at = datetime.now(timezone.utc)

        transport = ASGITransport(app=scraper_mod.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, scraper_mod, mock_blob, mock_history, mock_consumer, mock_publisher

        scraper_mod._blob_client = None
        scraper_mod._history_client = None
        scraper_mod._consumer = None
        scraper_mod._publisher = None
        scraper_mod._started_at = None
        for name in _SCRAPER_BARE_MODULES:
            sys.modules.pop(name, None)
        sys.path[:] = saved_path

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        c, _, _, _, _, _ = client
        resp = await c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "scraper"

    @pytest.mark.asyncio
    async def test_status_healthy(self, client):
        c, _, _, mock_history, _, _ = client
        mock_history.get_crawl_stats.return_value = {"total": 42, "failed": 0}
        resp = await c.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "scraper"
        assert data["components"]["blob_storage"] == "connected"
        assert data["components"]["cosmos_db"] == "connected"
        assert data["components"]["service_bus_consumer"] == "running"
        assert data["components"]["service_bus_publisher"] == "connected"
        assert data["started_at"] is not None
        assert data["crawl_history"] == {"total": 42, "failed": 0}

    @pytest.mark.asyncio
    async def test_status_includes_consumer_and_publisher_stats(self, client):
        c, _, _, _, mock_consumer, mock_publisher = client
        mock_consumer.stats = {"messages_processed": 7}
        mock_publisher.stats = {"messages_published": 5}
        resp = await c.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["consumer"] == {"messages_processed": 7}
        assert data["publisher"] == {"messages_published": 5}

    @pytest.mark.asyncio
    async def test_status_degraded_blob_and_cosmos(self, client):
        c, scraper_mod, _, _, _, _ = client
        scraper_mod._blob_client = None
        scraper_mod._history_client = None
        resp = await c.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["blob_storage"] == "not_initialized"
        assert data["components"]["cosmos_db"] == "not_initialized"

    @pytest.mark.asyncio
    async def test_status_degraded_service_bus(self, client):
        c, scraper_mod, _, _, _, _ = client
        scraper_mod._consumer = None
        scraper_mod._publisher = None
        resp = await c.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["service_bus_consumer"] == "not_initialized"
        assert data["components"]["service_bus_publisher"] == "not_initialized"
