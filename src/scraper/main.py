"""FastAPI application — health check, status, Service Bus consumer lifecycle.

Startup wires together all components; shutdown tears them down gracefully.
OpenTelemetry is configured via azure-monitor-opentelemetry for automatic
instrumentation of FastAPI, httpx, and the Azure SDK.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from azure.identity.aio import DefaultAzureCredential
from fastapi import FastAPI
from opentelemetry import trace

from config import ScraperSettings, get_settings
from models import ScrapeCompleteEvent, ScrapeRequest
from scraper import WebScraper
from service_bus import ScrapeCompletePublisher, ScrapeRequestConsumer
from storage import BlobStorageClient, CrawlHistoryClient

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _configure_logging(settings: ScraperSettings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

def _configure_telemetry(settings: ScraperSettings) -> None:
    """Activate Azure Monitor OpenTelemetry if a connection string is provided."""
    if settings.applicationinsights_connection_string:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(
                connection_string=settings.applicationinsights_connection_string,
                service_name=settings.otel_service_name,
                service_version=settings.service_version,
            )
            logging.getLogger(__name__).info("Azure Monitor OpenTelemetry configured")
        except ImportError:
            logging.getLogger(__name__).warning(
                "azure-monitor-opentelemetry not installed — telemetry disabled"
            )
    else:
        logging.getLogger(__name__).info(
            "No Application Insights connection string — telemetry export disabled"
        )


# ---------------------------------------------------------------------------
# Application state (module-level singletons set during lifespan)
# ---------------------------------------------------------------------------

_credential: DefaultAzureCredential | None = None
_blob_client: BlobStorageClient | None = None
_history_client: CrawlHistoryClient | None = None
_web_scraper: WebScraper | None = None
_consumer: ScrapeRequestConsumer | None = None
_publisher: ScrapeCompletePublisher | None = None
_started_at: datetime | None = None

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


# ---------------------------------------------------------------------------
# Request handler — glue between consumer and scraper
# ---------------------------------------------------------------------------

async def _handle_scrape_request(request: ScrapeRequest) -> ScrapeCompleteEvent | None:
    """Called by the Service Bus consumer for each incoming message."""
    assert _web_scraper is not None
    assert _publisher is not None

    with tracer.start_as_current_span("handle_scrape_request") as span:
        span.set_attribute("request_id", request.request_id)

        event = await _web_scraper.process_request(request)
        await _publisher.publish(event)
        return event


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage the lifecycle of all async clients and background tasks."""
    global _credential, _blob_client, _history_client
    global _web_scraper, _consumer, _publisher, _started_at

    settings = get_settings()
    _configure_logging(settings)
    _configure_telemetry(settings)

    logger.info("Starting scraper service v%s", settings.service_version)

    # Credential
    _credential = DefaultAzureCredential()

    # Storage clients
    _blob_client = BlobStorageClient(settings, _credential)
    _history_client = CrawlHistoryClient(settings, _credential)

    # Initialize storage (creates containers if needed)
    init_errors: list[str] = []
    for name, client in [("blob", _blob_client), ("cosmos", _history_client)]:
        try:
            await client.initialize()
        except Exception as exc:
            logger.warning("Failed to initialize %s client (will retry on first use): %s", name, exc)
            init_errors.append(name)

    # Core scraper
    _web_scraper = WebScraper(settings, _blob_client, _history_client)

    # Service Bus publisher + consumer
    _publisher = ScrapeCompletePublisher(settings, _credential)
    _consumer = ScrapeRequestConsumer(settings, _credential, _handle_scrape_request)

    for name, svc in [("publisher", _publisher), ("consumer", _consumer)]:
        try:
            await svc.start()
        except Exception as exc:
            logger.warning("Failed to start %s (will retry): %s", name, exc)
            init_errors.append(name)

    _started_at = datetime.now(timezone.utc)

    if init_errors:
        logger.warning("Service started with degraded components: %s", init_errors)
    else:
        logger.info("All components initialized successfully")

    yield  # ← application runs here

    # Shutdown
    logger.info("Shutting down scraper service…")
    if _consumer:
        await _consumer.stop()
    if _publisher:
        await _publisher.stop()
    if _web_scraper:
        await _web_scraper.close()
    if _blob_client:
        await _blob_client.close()
    if _history_client:
        await _history_client.close()
    if _credential:
        await _credential.close()
    logger.info("Scraper service shut down cleanly")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Scraper Service",
    description="Discovers and retrieves web content for the selflearning knowledge pipeline.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "healthy", "service": "scraper"}


@app.get("/status")
async def status() -> dict[str, Any]:
    """Readiness / status endpoint — shows current crawl stats and component health."""
    with tracer.start_as_current_span("status_endpoint"):
        components: dict[str, str] = {}
        components["blob_storage"] = "connected" if _blob_client else "not_initialized"
        components["cosmos_db"] = "connected" if _history_client else "not_initialized"
        components["service_bus_consumer"] = "running" if _consumer else "not_initialized"
        components["service_bus_publisher"] = "connected" if _publisher else "not_initialized"

        consumer_stats = _consumer.stats if _consumer else {}
        publisher_stats = _publisher.stats if _publisher else {}

        crawl_stats: dict[str, int] = {}
        if _history_client:
            try:
                crawl_stats = await _history_client.get_crawl_stats()
            except Exception as exc:
                logger.warning("Could not fetch crawl stats: %s", exc)

        return {
            "service": "scraper",
            "version": "0.1.0",
            "started_at": _started_at.isoformat() if _started_at else None,
            "components": components,
            "consumer": consumer_stats,
            "publisher": publisher_stats,
            "crawl_history": crawl_stats,
        }
