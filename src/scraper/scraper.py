"""Core scraping engine — fetches web content, respects robots.txt, deduplicates.

Design principles:
- Always honour robots.txt — cached per domain to avoid re-fetching.
- Rate-limit per domain with a token-bucket algorithm.
- Content cleaning strips navigation, ads, and scripts; extracts main text.
- Every operation is async for pipeline throughput.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup, Comment
from opentelemetry import trace

from config import ScraperSettings
from models import (
    CrawlStatus,
    ScrapeCompleteEvent,
    ScrapeRequest,
    ScrapeResult,
    ScrapeStats,
    SourceType,
)
from storage import BlobStorageClient, CrawlHistoryClient, content_hash

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


# ---------------------------------------------------------------------------
# Token-bucket rate limiter (per domain)
# ---------------------------------------------------------------------------

class TokenBucket:
    """Simple async token-bucket rate limiter."""

    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last = now

            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self.rate
                logger.debug("Rate limiter: waiting %.2fs for token", wait)
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


# ---------------------------------------------------------------------------
# Robots.txt cache
# ---------------------------------------------------------------------------

class RobotsCache:
    """Per-domain robots.txt parser cache."""

    def __init__(self, user_agent: str, http_client: httpx.AsyncClient) -> None:
        self._user_agent = user_agent
        self._http = http_client
        self._cache: dict[str, RobotFileParser] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, url: str) -> bool:
        """Return True if the user-agent is permitted to fetch *url*."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        robots_url = f"{parsed.scheme}://{domain}/robots.txt"

        async with self._lock:
            if domain not in self._cache:
                parser = RobotFileParser()
                try:
                    resp = await self._http.get(robots_url, timeout=10)
                    if resp.status_code == 200:
                        parser.parse(resp.text.splitlines())
                    else:
                        # No robots.txt or error → allow everything
                        parser.allow_all = True
                except Exception:
                    logger.debug("Could not fetch robots.txt for %s — allowing", domain)
                    parser.allow_all = True
                self._cache[domain] = parser

        return self._cache[domain].can_fetch(self._user_agent, url)


# ---------------------------------------------------------------------------
# Content extraction helpers
# ---------------------------------------------------------------------------

# Tags whose content is never useful
_STRIP_TAGS = {
    "script", "style", "noscript", "iframe", "svg", "nav", "footer",
    "header", "aside", "form", "button",
}

# CSS classes/IDs that usually wrap ads or chrome
_NOISE_PATTERNS = [
    "sidebar", "advertisement", "ad-", "cookie", "popup", "modal",
    "social-share", "newsletter", "promo", "banner",
]


def extract_content(html: str, url: str = "") -> dict[str, Any]:
    """Parse HTML and return cleaned text content plus metadata.

    Returns a dict with keys: title, text, word_count, links.
    """
    with tracer.start_as_current_span("extract_content"):
        soup = BeautifulSoup(html, "html.parser")

        # Title
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Remove noisy elements
        for tag in soup.find_all(_STRIP_TAGS):
            tag.decompose()

        # Remove HTML comments
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            comment.extract()

        # Remove elements with noisy class/id names
        for el in soup.find_all(True):
            css_classes = " ".join(el.get("class", []))
            el_id = el.get("id", "")
            combined = f"{css_classes} {el_id}".lower()
            if any(pattern in combined for pattern in _NOISE_PATTERNS):
                el.decompose()

        # Prefer <main> or <article> if present
        main_content = soup.find("main") or soup.find("article")
        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
        else:
            body = soup.find("body")
            text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)

        # Collapse blank lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned_text = "\n".join(lines)

        # Extract outbound links
        links: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if href.startswith("http"):
                links.append(href)

        word_count = len(cleaned_text.split())

        return {
            "title": title,
            "text": cleaned_text,
            "word_count": word_count,
            "links": links[:50],  # cap for sanity
        }


# ---------------------------------------------------------------------------
# Web scraper
# ---------------------------------------------------------------------------

class WebScraper:
    """Async web scraper with robots.txt compliance, rate limiting,
    deduplication, and content extraction.
    """

    def __init__(
        self,
        settings: ScraperSettings,
        blob_client: BlobStorageClient,
        history_client: CrawlHistoryClient,
    ) -> None:
        self._settings = settings
        self._blob = blob_client
        self._history = history_client

        self._http = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(settings.request_timeout),
            headers={"User-Agent": settings.user_agent},
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )
        self._robots = RobotsCache(settings.user_agent, self._http)
        self._rate_limiters: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self._http.aclose()

    # -- Rate limiter per domain -----------------------------------------------

    async def _get_limiter(self, domain: str) -> TokenBucket:
        async with self._lock:
            if domain not in self._rate_limiters:
                self._rate_limiters[domain] = TokenBucket(
                    rate=self._settings.rate_limit_requests_per_second,
                    burst=self._settings.rate_limit_burst,
                )
            return self._rate_limiters[domain]

    # -- Public API ------------------------------------------------------------

    async def process_request(self, request: ScrapeRequest) -> ScrapeCompleteEvent:
        """Process a full ScrapeRequest and return a ScrapeCompleteEvent."""
        with tracer.start_as_current_span("scraper.process_request") as span:
            span.set_attribute("request_id", request.request_id)
            span.set_attribute("topic", request.topic)
            span.set_attribute("source_type", request.source_type.value)

            start_time = time.monotonic()
            urls = await self._resolve_urls(request)
            stats = ScrapeStats(urls_attempted=len(urls))
            results: list[ScrapeResult] = []

            for url in urls[: self._settings.max_urls_per_request]:
                try:
                    result = await self._scrape_url(url, request)
                    if result:
                        results.append(result)
                        stats.urls_succeeded += 1
                        stats.total_bytes += len(result.text_preview.encode())
                    else:
                        stats.urls_failed += 1
                except Exception:
                    logger.exception("Failed to scrape URL: %s", url)
                    stats.urls_failed += 1

            stats.elapsed_seconds = round(time.monotonic() - start_time, 2)

            return ScrapeCompleteEvent(
                request_id=request.request_id,
                topic=request.topic,
                results=results,
                stats=stats,
            )

    # -- URL resolution --------------------------------------------------------

    async def _resolve_urls(self, request: ScrapeRequest) -> list[str]:
        """Turn a ScrapeRequest into a concrete list of URLs to fetch."""
        with tracer.start_as_current_span("scraper.resolve_urls"):
            if request.url:
                return [request.url]

            if request.source_type == SourceType.DIRECT_URL:
                if request.url:
                    return [request.url]
                logger.warning("direct_url request without a URL — skipping")
                return []

            if request.source_type == SourceType.WEB_SEARCH:
                return await self._web_search(request.query)

            # For academic/RSS — placeholder for future adapters
            logger.info(
                "Source type '%s' not yet implemented — falling back to web search",
                request.source_type.value,
            )
            return await self._web_search(request.query)

    async def _web_search(self, query: str) -> list[str]:
        """Execute a web search and return result URLs.

        Uses a simple Bing-style search scrape as a starting point.
        A production deployment would use the Bing Search API with an API key.
        For now, we construct plausible search URLs as a best-effort approach.
        """
        with tracer.start_as_current_span("scraper.web_search") as span:
            span.set_attribute("query", query)
            search_url = f"https://html.duckduckgo.com/html/?q={query}"

            try:
                domain = urlparse(search_url).netloc
                limiter = await self._get_limiter(domain)
                await limiter.acquire()

                resp = await self._http.get(search_url)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")
                urls: list[str] = []
                for link in soup.find_all("a", class_="result__a", href=True):
                    href = link["href"]
                    if href.startswith("http"):
                        urls.append(href)

                # Fallback: extract any outbound links if the class selector didn't match
                if not urls:
                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        if href.startswith("http") and "duckduckgo" not in href:
                            urls.append(href)

                logger.info("Web search for '%s' returned %d URLs", query, len(urls))
                span.set_attribute("urls_found", len(urls))
                return urls[: self._settings.max_urls_per_request]

            except Exception:
                logger.exception("Web search failed for query: %s", query)
                return []

    # -- Single URL scrape -----------------------------------------------------

    async def _scrape_url(
        self,
        url: str,
        request: ScrapeRequest,
    ) -> ScrapeResult | None:
        """Fetch, extract, deduplicate, and store content from a single URL."""
        with tracer.start_as_current_span("scraper.scrape_url") as span:
            span.set_attribute("url", url)

            # 1. Robots.txt check
            if not await self._robots.is_allowed(url):
                logger.info("Blocked by robots.txt: %s", url)
                await self._history.record_crawl(url, status=CrawlStatus.SKIPPED_ROBOTS, topic=request.topic)
                return None

            # 2. Deduplication — already crawled recently?
            if await self._history.url_already_crawled(url):
                logger.info("Skipping duplicate URL: %s", url)
                await self._history.record_crawl(url, status=CrawlStatus.SKIPPED_DUPLICATE, topic=request.topic)
                return None

            # 3. Rate limit
            domain = urlparse(url).netloc.lower()
            limiter = await self._get_limiter(domain)
            await limiter.acquire()

            # 4. Fetch with retries
            raw_content = await self._fetch_with_retries(url)
            if raw_content is None:
                await self._history.record_crawl(url, status=CrawlStatus.FAILED, topic=request.topic)
                return None

            # 5. Content hash dedup
            hash_value = content_hash(raw_content)
            if await self._history.content_hash_exists(hash_value):
                logger.info("Skipping content-hash duplicate for %s", url)
                await self._history.record_crawl(
                    url,
                    status=CrawlStatus.SKIPPED_DUPLICATE,
                    content_hash_value=hash_value,
                    topic=request.topic,
                )
                return None

            # 6. Extract text
            extracted = extract_content(raw_content.decode("utf-8", errors="replace"), url)

            # 7. Store raw content in blob
            blob_path = self._build_blob_path(request, url, hash_value)
            await self._blob.upload_content(
                blob_path=blob_path,
                data=raw_content,
                content_type="text/html",
                metadata={
                    "url": url,
                    "topic": request.topic,
                    "request_id": request.request_id,
                },
            )

            # 8. Record in crawl history
            await self._history.record_crawl(
                url,
                status=CrawlStatus.SUCCESS,
                content_hash_value=hash_value,
                blob_path=blob_path,
                topic=request.topic,
            )

            text_preview = extracted["text"][:500]

            return ScrapeResult(
                request_id=request.request_id,
                topic=request.topic,
                url=url,
                content_type="text/html",
                blob_path=blob_path,
                content_hash=hash_value,
                title=extracted["title"],
                text_preview=text_preview,
                word_count=extracted["word_count"],
                scraped_at=datetime.now(timezone.utc),
            )

    # -- HTTP fetch with exponential backoff -----------------------------------

    async def _fetch_with_retries(self, url: str) -> bytes | None:
        """Fetch *url* with exponential backoff on transient failures."""
        with tracer.start_as_current_span("scraper.fetch_with_retries") as span:
            span.set_attribute("url", url)
            max_size = self._settings.max_content_size_mb * 1024 * 1024

            for attempt in range(1, self._settings.max_retries + 1):
                try:
                    resp = await self._http.get(url)
                    resp.raise_for_status()

                    content_length = int(resp.headers.get("content-length", 0))
                    if content_length > max_size:
                        logger.warning("Content too large (%d bytes): %s", content_length, url)
                        return None

                    data = resp.content
                    if len(data) > max_size:
                        logger.warning("Downloaded content exceeds max size: %s", url)
                        return None

                    span.set_attribute("response_size", len(data))
                    span.set_attribute("status_code", resp.status_code)
                    return data

                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status in (403, 404, 410):
                        logger.info("Non-retryable HTTP %d for %s", status, url)
                        return None
                    logger.warning(
                        "HTTP %d on attempt %d/%d for %s",
                        status, attempt, self._settings.max_retries, url,
                    )

                except (httpx.TimeoutException, httpx.ConnectError) as exc:
                    logger.warning(
                        "Network error on attempt %d/%d for %s: %s",
                        attempt, self._settings.max_retries, url, exc,
                    )

                # Exponential backoff
                if attempt < self._settings.max_retries:
                    delay = self._settings.retry_base_delay * (2 ** (attempt - 1))
                    logger.debug("Retrying in %.1fs…", delay)
                    await asyncio.sleep(delay)

            logger.error("All %d attempts failed for %s", self._settings.max_retries, url)
            return None

    # -- Blob path builder -----------------------------------------------------

    @staticmethod
    def _build_blob_path(request: ScrapeRequest, url: str, hash_value: str) -> str:
        """Construct a deterministic blob path: <topic>/<domain>/<hash>.html"""
        domain = urlparse(url).netloc.lower().replace(":", "_")
        safe_topic = request.topic.lower().replace(" ", "-")[:50]
        return f"{safe_topic}/{domain}/{hash_value[:16]}.html"
