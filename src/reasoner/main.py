"""Reasoner service entry point.

FastAPI application with:
- Health-check endpoint (``/health``)
- Status endpoint (``/status``)
- Direct reasoning endpoint (``POST /reason``)
- Result retrieval endpoints (``GET /results``, ``GET /results/{request_id}``)
- Startup / shutdown lifecycle hooks
- Background Service Bus consumer loop
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException

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

# In-memory result store (request_id → result)
_results: dict[str, ReasoningResult] = {}
_MAX_STORED_RESULTS = 100

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

    _store_result(result)

    return result.model_dump(exclude_none=True)


def _store_result(result: ReasoningResult) -> None:
    """Persist *result* in the in-memory store, evicting oldest entries."""
    _results[result.request_id] = result
    if len(_results) > _MAX_STORED_RESULTS:
        oldest_key = next(iter(_results))
        _results.pop(oldest_key, None)


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


@app.get("/status")
async def status() -> dict[str, Any]:
    """Service status including readiness of sub-components."""
    return {
        "service": "reasoner",
        "engine": "ready" if engine is not None else "not_initialized",
        "knowledge_client": "ready" if knowledge_client is not None else "not_initialized",
        "service_bus": "ready" if service_bus is not None else "not_configured",
        "stored_results": len(_results),
    }


@app.post("/reason", response_model=ReasoningResult)
async def reason(request: ReasoningRequest) -> ReasoningResult:
    """Trigger a reasoning operation directly via HTTP."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Reasoning engine not initialized")

    result = await engine.run(request)
    _store_result(result)
    return result


@app.get("/results/{request_id}", response_model=ReasoningResult)
async def get_result(request_id: str) -> ReasoningResult:
    """Retrieve a reasoning result by its request ID."""
    result = _results.get(request_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No result found for request_id '{request_id}'",
        )
    return result


@app.get("/results", response_model=list[ReasoningResult])
async def list_results(limit: int = 20) -> list[ReasoningResult]:
    """List the most recent reasoning results, newest first."""
    if limit < 1:
        limit = 20
    all_results = list(_results.values())
    return list(reversed(all_results))[:limit]
