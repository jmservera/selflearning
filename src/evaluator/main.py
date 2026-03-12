"""Evaluator service — FastAPI application."""

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import trace

from .config import Settings
from .evaluation import EvaluationEngine
from .knowledge_client import KnowledgeClient
from .models import (
    EvaluationReport,
    ExpertiseScorecard,
    HealthResponse,
    KnowledgeGap,
)
from .question_generator import QuestionGenerator
from .service_bus import EvaluationPublisher

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# In-memory stores (production would use Cosmos DB)
_scorecard_history: dict[str, list[ExpertiseScorecard]] = {}
_gap_store: dict[str, list[KnowledgeGap]] = {}
_reports: dict[str, EvaluationReport] = {}

settings: Settings | None = None
engine: EvaluationEngine | None = None
publisher: EvaluationPublisher | None = None
knowledge_client: KnowledgeClient | None = None


class AzureAIClient:
    """Wraps Azure AI Inference for LLM completions."""

    def __init__(self, endpoint: str, model: str = "gpt-4o") -> None:
        self._endpoint = endpoint
        self._model = model
        self._client: Any = None

    async def _ensure_client(self) -> None:
        if self._client is None:
            try:
                from azure.ai.inference.aio import ChatCompletionsClient
                from azure.identity.aio import DefaultAzureCredential

                credential = DefaultAzureCredential()
                self._client = ChatCompletionsClient(
                    endpoint=self._endpoint, credential=credential
                )
            except Exception:
                logger.warning("Azure AI client unavailable, using stub")
                self._client = "stub"

    async def complete(self, prompt: str, model: str | None = None) -> str:
        await self._ensure_client()
        if self._client == "stub":
            return "[]"
        try:
            from azure.ai.inference.models import UserMessage

            response = await self._client.complete(
                model=model or self._model,
                messages=[UserMessage(content=prompt)],
            )
            return response.choices[0].message.content
        except Exception as exc:
            logger.error("LLM completion failed: %s", exc)
            return "[]"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown service dependencies."""
    global settings, engine, publisher, knowledge_client

    settings = Settings.from_env()

    http_client = httpx.AsyncClient(
        base_url=settings.knowledge_service_url, timeout=30.0
    )
    knowledge_client = KnowledgeClient(
        settings.knowledge_service_url, client=http_client
    )

    llm_client = AzureAIClient(settings.azure_ai_endpoint, settings.evaluation_model)
    qgen = QuestionGenerator(llm_client, model=settings.question_model)
    engine = EvaluationEngine(
        knowledge_client, qgen, max_questions=settings.max_questions_per_eval
    )

    if settings.azure_servicebus_namespace:
        publisher = EvaluationPublisher(
            settings.azure_servicebus_namespace, settings.service_bus_topic
        )
        try:
            await publisher.initialize()
        except Exception as exc:
            logger.warning("Service Bus initialization failed: %s", exc)
            publisher = None

    logger.info("Evaluator service started")
    yield

    if knowledge_client:
        await knowledge_client.close()
    if publisher:
        await publisher.close()
    logger.info("Evaluator service stopped")


app = FastAPI(
    title="Evaluator Service",
    description="Measures expertise level and identifies knowledge gaps",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check."""
    checks = {
        "engine": "ok" if engine else "not_initialized",
        "knowledge_client": "ok" if knowledge_client else "not_initialized",
        "service_bus": "ok" if publisher else "not_configured",
    }
    status = "healthy" if engine and knowledge_client else "degraded"
    return HealthResponse(status=status, checks=checks)


@app.post("/evaluate/{topic}", response_model=EvaluationReport)
async def evaluate_topic(topic: str) -> EvaluationReport:
    """Trigger a full evaluation for a topic."""
    if engine is None:
        raise HTTPException(
            status_code=503, detail="Evaluation engine not initialized"
        )

    with tracer.start_as_current_span("evaluate_topic", attributes={"topic": topic}):
        report = await engine.evaluate(topic)

    # Store results
    if topic not in _scorecard_history:
        _scorecard_history[topic] = []
    _scorecard_history[topic].append(report.scorecard)
    _gap_store[topic] = report.gaps
    _reports[topic] = report

    # Publish to Service Bus
    if publisher:
        try:
            await publisher.publish(
                {
                    "request_id": str(id(report)),
                    "topic": topic,
                    "scorecard": {
                        "overall_score": report.scorecard.overall_score,
                        "coverage_score": report.scorecard.coverage_score,
                        "depth_score": report.scorecard.depth_score,
                        "accuracy_score": report.scorecard.accuracy_score,
                        "gap_count": report.scorecard.gap_count,
                    },
                    "gaps": [
                        {
                            "area": g.area,
                            "severity": g.severity.value,
                            "suggested_queries": g.suggested_queries,
                        }
                        for g in report.gaps
                    ],
                    "recommendations": report.recommendations,
                }
            )
        except Exception as exc:
            logger.error("Failed to publish evaluation event: %s", exc)

    return report


@app.get("/scorecards/{topic}", response_model=ExpertiseScorecard | None)
async def get_scorecard(topic: str) -> ExpertiseScorecard:
    """Get the latest expertise scorecard for a topic."""
    history = _scorecard_history.get(topic, [])
    if not history:
        raise HTTPException(
            status_code=404, detail=f"No scorecard found for topic '{topic}'"
        )
    return history[-1]


@app.get("/scorecards/{topic}/history", response_model=list[ExpertiseScorecard])
async def get_scorecard_history(
    topic: str, limit: int = 50
) -> list[ExpertiseScorecard]:
    """Get scorecard history over time for a topic."""
    history = _scorecard_history.get(topic, [])
    return history[-limit:]


@app.get("/gaps/{topic}", response_model=list[KnowledgeGap])
async def get_gaps(topic: str) -> list[KnowledgeGap]:
    """Get current knowledge gaps for a topic."""
    return _gap_store.get(topic, [])
