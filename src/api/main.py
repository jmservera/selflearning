"""API Gateway — FastAPI application.

The external HTTP (and WebSocket) interface for the selflearning system.
Proxies to internal micro-services and adds cross-cutting concerns like
CORS, telemetry, health aggregation, chat, and live WebSockets.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx
from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace

from .chat import ChatHandler
from .config import get_settings
from .knowledge_client import KnowledgeClient
from .models import (
    ActivityLog,
    ChatRequest,
    ChatResponse,
    DashboardStatus,
    DecisionLog,
    LearningProgress,
    PriorityUpdate,
    SearchResponse,
    SearchResultItem,
    ServiceHealth,
    SystemHealth,
    TopicCreate,
    TopicDetail,
    TopicResponse,
)
from .orchestrator_client import OrchestratorClient
from .service_bus import GatewayServiceBus
from .websocket import (
    broadcast_status,
    ws_logs_handler,
    ws_status_handler,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

settings = get_settings()

# ── Telemetry ──────────────────────────────────────────────────────────────

if settings.app_insights_connection_string:
    configure_azure_monitor(
        connection_string=settings.app_insights_connection_string,
        service_name=settings.service_name,
    )

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s")

# ── Service clients (singletons) ──────────────────────────────────────────

knowledge = KnowledgeClient(settings.services.knowledge)
orchestrator = OrchestratorClient(settings.services.orchestrator)
bus = GatewayServiceBus(settings.service_bus)
chat_handler = ChatHandler(settings.ai_foundry, knowledge)


# ── App lifecycle ──────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("API Gateway starting up …")
    await knowledge.initialize()
    await orchestrator.initialize()
    await chat_handler.initialize()
    try:
        await bus.start()
        bus.on_status(broadcast_status)
    except Exception:
        logger.warning("Service Bus failed to start (non-fatal in dev)", exc_info=True)
    yield
    logger.info("API Gateway shutting down …")
    await bus.stop()
    await chat_handler.close()
    await orchestrator.close()
    await knowledge.close()


app = FastAPI(
    title="selflearning API Gateway",
    description="External API for the self-learning AI system",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.allowed_origins,
    allow_credentials=settings.cors.allow_credentials,
    allow_methods=settings.cors.allow_methods,
    allow_headers=settings.cors.allow_headers,
)


# ─────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": settings.service_name}


@app.get("/health/services", response_model=SystemHealth)
async def health_services() -> SystemHealth:
    """Check health of all downstream services."""
    with tracer.start_as_current_span("api.health_services"):
        service_urls: dict[str, str] = {
            "knowledge": settings.services.knowledge,
            "orchestrator": settings.services.orchestrator,
            "evaluator": settings.services.evaluator,
            "scraper": settings.services.scraper,
            "extractor": settings.services.extractor,
            "reasoner": settings.services.reasoner,
            "healer": settings.services.healer,
        }

        async def _check(name: str, url: str) -> ServiceHealth:
            start = asyncio.get_event_loop().time()
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as c:
                    resp = await c.get(f"{url}/health")
                    latency = (asyncio.get_event_loop().time() - start) * 1000
                    status = "healthy" if resp.status_code == 200 else "unhealthy"
                    return ServiceHealth(name=name, url=url, status=status, latency_ms=round(latency, 2))
            except Exception:
                latency = (asyncio.get_event_loop().time() - start) * 1000
                return ServiceHealth(name=name, url=url, status="unreachable", latency_ms=round(latency, 2))

        results = await asyncio.gather(*[_check(n, u) for n, u in service_urls.items()])
        services = list(results)
        overall = "healthy" if all(s.status == "healthy" for s in services) else "degraded"
        return SystemHealth(status=overall, services=services)


# ─────────────────────────────────────────────────────────────────────────
# Topic management
# ─────────────────────────────────────────────────────────────────────────


@app.post("/topics", response_model=TopicResponse, status_code=201)
async def create_topic(body: TopicCreate) -> TopicResponse:
    """Create a new learning topic."""
    with tracer.start_as_current_span("api.create_topic"):
        try:
            result = await orchestrator.create_topic(body.model_dump())
            return TopicResponse.model_validate(result)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail="Orchestrator rejected topic creation") from exc
        except httpx.ConnectError:
            # Orchestrator down — create a pending topic record and queue command
            logger.warning("Orchestrator unreachable; queuing topic creation")
            topic = TopicResponse(name=body.name, description=body.description, priority=body.priority, target_expertise=body.target_expertise)
            try:
                await bus.publish_command("create_topic", body.model_dump())
            except Exception:
                logger.warning("Service Bus publish also failed", exc_info=True)
            return topic


@app.get("/topics", response_model=list[TopicResponse])
async def list_topics() -> list[TopicResponse]:
    with tracer.start_as_current_span("api.list_topics"):
        try:
            items = await orchestrator.list_topics()
            return [TopicResponse.model_validate(t) for t in items]
        except Exception:
            logger.warning("Failed to list topics from orchestrator", exc_info=True)
            return []


@app.get("/topics/{topic_id}", response_model=TopicDetail)
async def get_topic(topic_id: str) -> TopicDetail:
    with tracer.start_as_current_span("api.get_topic"):
        try:
            topic_data = await orchestrator.get_topic(topic_id)
            if topic_data is None:
                raise HTTPException(status_code=404, detail="Topic not found")

            # Enrich with knowledge stats
            try:
                stats = await knowledge.topic_stats(topic_id)
                topic_data.update({
                    "entity_count": stats.get("entity_count", 0),
                    "relationship_count": stats.get("relationship_count", 0),
                    "claim_count": stats.get("claim_count", 0),
                    "source_count": stats.get("source_count", 0),
                    "avg_confidence": stats.get("avg_confidence", 0.0),
                    "coverage_areas": stats.get("coverage_areas", []),
                })
            except Exception:
                logger.warning("Knowledge stats unavailable for topic %s", topic_id, exc_info=True)

            return TopicDetail.model_validate(topic_data)
        except HTTPException:
            raise
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail="Failed to fetch topic") from exc


@app.post("/topics/{topic_id}/learn")
async def trigger_learning(topic_id: str) -> dict:
    with tracer.start_as_current_span("api.trigger_learning"):
        try:
            result = await orchestrator.trigger_learning(topic_id)
            return result
        except httpx.ConnectError:
            await bus.publish_learn(topic_id)
            return {"status": "queued", "topic_id": topic_id, "message": "Learning command queued via Service Bus"}


@app.put("/topics/{topic_id}/pause")
async def pause_topic(topic_id: str) -> dict:
    with tracer.start_as_current_span("api.pause_topic"):
        try:
            return await orchestrator.pause_topic(topic_id)
        except httpx.ConnectError:
            await bus.publish_pause(topic_id)
            return {"status": "queued", "topic_id": topic_id, "message": "Pause command queued"}


@app.put("/topics/{topic_id}/resume")
async def resume_topic(topic_id: str) -> dict:
    with tracer.start_as_current_span("api.resume_topic"):
        try:
            return await orchestrator.resume_topic(topic_id)
        except httpx.ConnectError:
            await bus.publish_resume(topic_id)
            return {"status": "queued", "topic_id": topic_id, "message": "Resume command queued"}


@app.put("/topics/{topic_id}/priority")
async def update_priority(topic_id: str, body: PriorityUpdate) -> dict:
    with tracer.start_as_current_span("api.update_priority"):
        try:
            return await orchestrator.update_priority(topic_id, body.priority)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail="Failed to update priority") from exc


# ─────────────────────────────────────────────────────────────────────────
# Knowledge query
# ─────────────────────────────────────────────────────────────────────────


@app.get("/knowledge/search", response_model=SearchResponse)
async def search_knowledge(
    q: str,
    topic: str | None = None,
    doc_type: str | None = None,
    min_confidence: float = 0.0,
    limit: int = Query(default=20, le=100),
    mode: str = Query(default="hybrid", pattern="^(hybrid|vector|keyword)$"),
) -> SearchResponse:
    with tracer.start_as_current_span("api.search_knowledge"):
        try:
            result = await knowledge.search(
                q=q, topic=topic, doc_type=doc_type,
                min_confidence=min_confidence, limit=limit, mode=mode,
            )
            return SearchResponse(
                items=[SearchResultItem.model_validate(i) for i in result.get("items", [])],
                total_count=result.get("total_count", 0),
                facets=result.get("facets", {}),
            )
        except Exception:
            logger.exception("Knowledge search failed")
            raise HTTPException(status_code=502, detail="Knowledge service unavailable")


@app.get("/knowledge/entities/{entity_id}")
async def get_entity(entity_id: str, topic: str | None = None) -> dict:
    with tracer.start_as_current_span("api.get_entity"):
        entity = await knowledge.get_entity(entity_id, topic=topic)
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found")
        return entity


@app.get("/knowledge/topics/{topic}/graph")
async def knowledge_graph(topic: str, limit: int = Query(default=100, le=500)) -> dict:
    """Get knowledge graph (entities + relationships) for visualization."""
    with tracer.start_as_current_span("api.knowledge_graph"):
        try:
            return await knowledge.topic_graph(topic, limit=limit)
        except Exception:
            logger.exception("Knowledge graph query failed")
            raise HTTPException(status_code=502, detail="Knowledge service unavailable")


# ─────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────


@app.get("/dashboard/status", response_model=DashboardStatus)
async def dashboard_status() -> DashboardStatus:
    with tracer.start_as_current_span("api.dashboard_status"):
        try:
            status = await orchestrator.get_status()
            return DashboardStatus.model_validate(status)
        except Exception:
            logger.warning("Orchestrator status unavailable", exc_info=True)
            return DashboardStatus(current_activity="unknown — orchestrator unreachable")


@app.get("/dashboard/progress", response_model=LearningProgress)
async def dashboard_progress() -> LearningProgress:
    with tracer.start_as_current_span("api.dashboard_progress"):
        try:
            progress = await orchestrator.get_progress()
            return LearningProgress.model_validate(progress)
        except Exception:
            logger.warning("Orchestrator progress unavailable", exc_info=True)
            return LearningProgress()


@app.get("/dashboard/logs", response_model=list[ActivityLog])
async def dashboard_logs(limit: int = Query(default=50, le=200)) -> list[ActivityLog]:
    with tracer.start_as_current_span("api.dashboard_logs"):
        try:
            logs = await orchestrator.get_logs(limit=limit)
            return [ActivityLog.model_validate(log) for log in logs]
        except Exception:
            logger.warning("Orchestrator logs unavailable", exc_info=True)
            return []


@app.get("/dashboard/decisions", response_model=list[DecisionLog])
async def dashboard_decisions(limit: int = Query(default=50, le=200)) -> list[DecisionLog]:
    with tracer.start_as_current_span("api.dashboard_decisions"):
        try:
            decisions = await orchestrator.get_decisions(limit=limit)
            return [DecisionLog.model_validate(d) for d in decisions]
        except Exception:
            logger.warning("Orchestrator decisions unavailable", exc_info=True)
            return []


# ─────────────────────────────────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────────────────────────────────


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    """Ask the expert agent a question — RAG-powered response with citations."""
    with tracer.start_as_current_span("api.chat"):
        return await chat_handler.handle(body)


# ─────────────────────────────────────────────────────────────────────────
# WebSocket
# ─────────────────────────────────────────────────────────────────────────


@app.websocket("/ws/status")
async def ws_status(websocket: WebSocket) -> None:
    await ws_status_handler(websocket)


@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket) -> None:
    await ws_logs_handler(websocket)
