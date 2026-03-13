"""Orchestrator Service — FastAPI application.

The orchestrator is the autonomous learning agent that drives the entire
selflearning pipeline.  It manages topics, runs the learning loop, and
exposes status / control endpoints.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, status
from opentelemetry import trace
from pydantic import BaseModel

from config import OrchestratorSettings, get_settings
from cosmos_client import CosmosDBClient
from learning_loop import LearningLoop
from models import (
    LearningTopic,
    OrchestratorStatus,
    PipelineStage,
    TopicStatus,
)
from service_bus import OrchestratorServiceBus
from strategy import StrategyManager
from working_memory import WorkingMemory

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# ── Global singletons (initialised in lifespan) ──────────────────────

_settings: OrchestratorSettings | None = None
_cosmos: CosmosDBClient | None = None
_bus: OrchestratorServiceBus | None = None
_memory: WorkingMemory | None = None
_strategy: StrategyManager | None = None
_loop: LearningLoop | None = None
_start_time: float = 0.0


# ── Request / response schemas ────────────────────────────────────────

class TopicCreate(BaseModel):
    name: str
    description: str = ""
    priority: int = 5
    target_expertise_level: float = 0.9


class TopicResponse(BaseModel):
    id: str
    name: str
    description: str
    priority: int
    status: TopicStatus
    target_expertise_level: float
    current_score: float
    iteration_count: int
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime
    uptime_seconds: float


class MessageResponse(BaseModel):
    message: str


# ── Lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    global _settings, _cosmos, _bus, _memory, _strategy, _loop, _start_time

    _start_time = time.monotonic()
    _settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, _settings.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )

    # Configure OpenTelemetry (if connection string set)
    if _settings.applicationinsights_connection_string:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(
                connection_string=_settings.applicationinsights_connection_string,
                service_name=_settings.otel_service_name,
            )
            logger.info("OpenTelemetry configured with Azure Monitor")
        except Exception as exc:
            logger.warning("Failed to configure Azure Monitor: %s", exc)

    # Initialise infrastructure clients
    _cosmos = CosmosDBClient(_settings)
    _bus = OrchestratorServiceBus(_settings)
    _memory = WorkingMemory(_settings)

    try:
        await _cosmos.initialize()
    except Exception as exc:
        logger.error("Cosmos DB init failed (non-fatal): %s", exc)

    try:
        await _bus.initialize()
        await _bus.start_listeners()
    except Exception as exc:
        logger.error("Service Bus init failed (non-fatal): %s", exc)

    # Initialise strategy manager and learning loop
    _strategy = StrategyManager(_settings, _cosmos, _memory)
    _loop = LearningLoop(_settings, _cosmos, _bus, _memory, _strategy)

    # Start the autonomous learning loop
    await _loop.start()
    logger.info("Orchestrator service started — learning loop running")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────
    logger.info("Orchestrator shutting down")
    if _loop:
        await _loop.stop()
    if _bus:
        await _bus.close()
    if _cosmos:
        await _cosmos.close()
    logger.info("Orchestrator shutdown complete")


# ── Application ───────────────────────────────────────────────────────

app = FastAPI(
    title="selflearning Orchestrator",
    description="Autonomous learning agent — drives the self-learning pipeline",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Health ────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Liveness probe — confirms the service is running."""
    return HealthResponse(
        status="healthy",
        service="orchestrator",
        timestamp=datetime.now(timezone.utc),
        uptime_seconds=time.monotonic() - _start_time,
    )


# ── Status ────────────────────────────────────────────────────────────

@app.get("/status", response_model=OrchestratorStatus, tags=["status"])
async def get_status() -> OrchestratorStatus:
    """Return the current orchestrator state."""
    assert _loop is not None and _cosmos is not None

    active_topics = _cosmos.list_topics(status=TopicStatus.ACTIVE)
    paused_topics = _cosmos.list_topics(status=TopicStatus.PAUSED)
    loop_status = _loop.get_status()

    return OrchestratorStatus(
        active_topics=[t.name for t in active_topics],
        paused_topics=[t.name for t in paused_topics],
        current_stages={
            k: PipelineStage(v) for k, v in loop_status.get("current_stages", {}).items()
        },
        iterations_completed=loop_status.get("iterations_completed", {}),
        scores={t.name: t.current_score for t in active_topics},
        next_actions={},
        loop_running=loop_status.get("running", False),
        uptime_seconds=time.monotonic() - _start_time,
    )


# ── Topic management ─────────────────────────────────────────────────

@app.post(
    "/topics/{topic}/learn",
    response_model=TopicResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["topics"],
)
async def trigger_learning(topic: str, body: TopicCreate | None = None) -> TopicResponse:
    """Trigger a learning cycle for a topic.

    Creates the topic if it doesn't exist, or resumes if paused.
    """
    assert _cosmos is not None
    with tracer.start_as_current_span("api.trigger_learning"):
        existing = _cosmos.get_topic(topic)
        if existing:
            if existing.status == TopicStatus.PAUSED:
                existing = _cosmos.update_topic_status(topic, TopicStatus.ACTIVE)
            if existing is None:
                raise HTTPException(status_code=500, detail="Failed to update topic status")
            return TopicResponse(**existing.model_dump())

        # Create new topic
        new_topic = LearningTopic(
            name=topic,
            description=body.description if body else "",
            priority=body.priority if body else 5,
            target_expertise_level=body.target_expertise_level if body else 0.9,
        )
        _cosmos.upsert_topic(new_topic)
        logger.info("Created topic %s with priority=%d", topic, new_topic.priority)
        return TopicResponse(**new_topic.model_dump())


@app.put("/topics/{topic}/pause", response_model=MessageResponse, tags=["topics"])
async def pause_topic(topic: str) -> MessageResponse:
    """Pause learning for a topic."""
    assert _cosmos is not None
    updated = _cosmos.update_topic_status(topic, TopicStatus.PAUSED)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Topic '{topic}' not found")
    logger.info("Paused topic %s", topic)
    return MessageResponse(message=f"Topic '{topic}' paused")


@app.put("/topics/{topic}/resume", response_model=MessageResponse, tags=["topics"])
async def resume_topic(topic: str) -> MessageResponse:
    """Resume learning for a paused topic."""
    assert _cosmos is not None
    updated = _cosmos.update_topic_status(topic, TopicStatus.ACTIVE)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Topic '{topic}' not found")
    logger.info("Resumed topic %s", topic)
    return MessageResponse(message=f"Topic '{topic}' resumed")


@app.get("/topics/{topic}/pipeline", tags=["topics"])
async def get_pipeline(topic: str) -> dict[str, Any]:
    """Get current pipeline state for a topic."""
    assert _loop is not None
    return _loop.get_topic_pipeline(topic)


@app.get("/topics", response_model=list[TopicResponse], tags=["topics"])
async def list_topics(topic_status: TopicStatus | None = None) -> list[TopicResponse]:
    """List all topics, optionally filtered by status."""
    assert _cosmos is not None
    topics = _cosmos.list_topics(status=topic_status)
    return [TopicResponse(**t.model_dump()) for t in topics]


# ── Working memory debug ──────────────────────────────────────────────

@app.get("/memory/snapshot", tags=["debug"])
async def memory_snapshot() -> dict[str, Any]:
    """Return a snapshot of working memory (debug/observability)."""
    assert _memory is not None
    return _memory.snapshot()


@app.get("/memory/{topic}", tags=["debug"])
async def memory_context(topic: str) -> dict[str, str]:
    """Return the LLM prompt context for a topic."""
    assert _memory is not None
    return {"topic": topic, "context": _memory.build_prompt_context(topic)}
