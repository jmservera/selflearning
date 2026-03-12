"""Extractor service entry point.

FastAPI application with:
- Health-check endpoint (``/health``)
- Startup / shutdown lifecycle hooks that wire up the extraction pipeline
- Background Service Bus consumer loop
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from blob_storage import BlobStorageClient
from config import ExtractorConfig
from extraction import ExtractionPipeline
from llm_client import LLMClient
from models import ExtractionResult, RawContent
from service_bus import ServiceBusHandler

# ---------------------------------------------------------------------------
# Globals (populated during startup)
# ---------------------------------------------------------------------------
config: ExtractorConfig = ExtractorConfig()
llm_client: LLMClient | None = None
blob_client: BlobStorageClient | None = None
service_bus: ServiceBusHandler | None = None
pipeline: ExtractionPipeline | None = None
_consumer_task: asyncio.Task | None = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Message handler — glue between Service Bus and extraction pipeline
# ---------------------------------------------------------------------------


async def handle_scrape_complete(body: dict[str, Any]) -> dict[str, Any]:
    """Process a single ``scrape-complete`` message.

    Message schema::

        {
          "request_id": "uuid",
          "topic": "string",
          "results": [{"url": "str", "blob_path": "str", "content_type": "str", ...}]
        }

    Returns an ``extraction-complete`` payload.
    """
    assert pipeline is not None
    assert blob_client is not None

    request_id: str = body["request_id"]
    topic: str = body["topic"]
    results: list[dict] = body.get("results", [])

    all_entities: list = []
    all_relationships: list = []
    all_claims: list = []
    all_summaries: list = []

    for item in results:
        raw = RawContent(
            blob_path=item["blob_path"],
            url=item.get("url", ""),
            content_type=item.get("content_type", "text/html"),
            metadata=item.get("metadata", {}),
        )

        text = await blob_client.read_content(raw.blob_path)

        if not text.strip():
            logger.warning("Empty content for blob %s — skipping", raw.blob_path)
            continue

        result: ExtractionResult = await pipeline.run(
            text=text,
            topic=topic,
            source_url=raw.url,
            request_id=request_id,
        )

        all_entities.extend(e.model_dump(exclude_none=True) for e in result.entities)
        all_relationships.extend(r.model_dump() for r in result.relationships)
        all_claims.extend(c.model_dump() for c in result.claims)
        all_summaries.extend(s.model_dump() for s in result.summaries)

    return {
        "request_id": request_id,
        "topic": topic,
        "entities": all_entities,
        "relationships": all_relationships,
        "claims": all_claims,
        "summaries": all_summaries,
    }


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start all clients on startup, tear them down on shutdown."""
    global llm_client, blob_client, service_bus, pipeline, _consumer_task

    logging.basicConfig(level=config.log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.info("Extractor service starting up")

    # Initialise clients
    llm_client = LLMClient(config)
    await llm_client.initialize()

    blob_client = BlobStorageClient(config)
    await blob_client.initialize()

    service_bus = ServiceBusHandler(config)
    await service_bus.initialize()

    pipeline = ExtractionPipeline(config, llm_client)

    # Start Service Bus consumer in background
    _consumer_task = asyncio.create_task(
        service_bus.consume_loop(handle_scrape_complete),
        name="extractor-consumer",
    )
    logger.info("Extractor service ready — consuming from %s", config.scrape_complete_topic)

    yield

    # Shutdown
    logger.info("Extractor service shutting down")
    if _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass

    if service_bus:
        await service_bus.close()
    if blob_client:
        await blob_client.close()
    if llm_client:
        await llm_client.close()

    logger.info("Extractor service stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Extractor Service",
    description="Transforms raw scraped content into structured knowledge units.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness / readiness probe."""
    return {"status": "healthy", "service": "extractor"}
