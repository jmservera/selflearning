"""Reasoner service entry point.

FastAPI application with:
- Health-check endpoint (``/health``)
- Startup / shutdown lifecycle hooks
- Background Service Bus consumer loop
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from config import ReasonerConfig
from llm_client import LLMClient
from models import ReasoningRequest, ReasoningResult
from reasoning import KnowledgeServiceClient, ReasoningEngine
from service_bus import ServiceBusHandler

# ---------------------------------------------------------------------------
# Globals (populated during startup)
# ---------------------------------------------------------------------------
config: ReasonerConfig = ReasonerConfig()
llm_client: LLMClient | None = None
knowledge_client: KnowledgeServiceClient | None = None
engine: ReasoningEngine | None = None
service_bus: ServiceBusHandler | None = None
_consumer_task: asyncio.Task | None = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------


async def handle_reasoning_request(body: dict[str, Any]) -> dict[str, Any]:
    """Process a single ``reasoning-requests`` message.

    Message schema::

        {
          "request_id": "uuid",
          "topic": "string",
          "reasoning_type": "gap_analysis|contradiction_resolution|synthesis|depth_probe",
          "context": {}
        }

    Returns a ``reasoning-complete`` payload.
    """
    assert engine is not None

    request = ReasoningRequest(
        request_id=body["request_id"],
        topic=body["topic"],
        reasoning_type=body["reasoning_type"],
        context=body.get("context", {}),
    )

    result: ReasoningResult = await engine.run(request)

    return result.model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_client, knowledge_client, engine, service_bus, _consumer_task

    logging.basicConfig(level=config.log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.info("Reasoner service starting up")

    llm_client = LLMClient(config)
    await llm_client.initialize()

    knowledge_client = KnowledgeServiceClient(config.knowledge_service_url)

    engine = ReasoningEngine(config, llm_client, knowledge_client)

    service_bus = ServiceBusHandler(config)
    await service_bus.initialize()

    _consumer_task = asyncio.create_task(
        service_bus.consume_loop(handle_reasoning_request),
        name="reasoner-consumer",
    )
    logger.info("Reasoner service ready — consuming from %s", config.reasoning_requests_queue)

    yield

    logger.info("Reasoner service shutting down")
    if _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass

    if service_bus:
        await service_bus.close()
    if knowledge_client:
        await knowledge_client.close()
    if llm_client:
        await llm_client.close()

    logger.info("Reasoner service stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Reasoner Service",
    description="Synthesizes knowledge, identifies gaps, and generates insights.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness / readiness probe."""
    return {"status": "healthy", "service": "reasoner"}
