"""Tests for the API Gateway service.

These tests define expected behavioral contracts for the API gateway.
They use a mock FastAPI app that implements the expected endpoint
contracts. When the API service is implemented, update to test the
actual service.
"""

import json
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field


# ============================================================================
# Contract models — expected API schemas
# ============================================================================


class TopicCreate(BaseModel):
    name: str
    description: str = ""
    priority: int = Field(default=5, ge=1, le=10)


class TopicResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    priority: int = 5
    status: str = "active"
    entity_count: int = 0


class SearchRequest(BaseModel):
    query: str
    topic: str | None = None
    top_k: int = 10


class SearchResult(BaseModel):
    id: str
    name: str
    type: str
    score: float
    snippet: str = ""


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    topic: str
    messages: list[ChatMessage]


class HealthResponse(BaseModel):
    status: str
    services: dict[str, str] = Field(default_factory=dict)


class DashboardStatus(BaseModel):
    current_activity: str = "idle"
    active_topics: int = 0
    total_entities: int = 0
    total_claims: int = 0
    active_learning_cycles: int = 0
    system_health: str = "healthy"


class LearningProgress(BaseModel):
    overall_expertise: float = 0.0
    total_entities: int = 0
    total_claims: int = 0
    total_sources: int = 0
    learning_rate: float = 0.0


class ActivityLog(BaseModel):
    id: str
    service: str = ""
    action: str = ""
    details: str = ""
    topic: str | None = None
    success: bool = True


class DecisionLog(BaseModel):
    id: str
    decision: str = ""
    reasoning: str = ""
    topic: str | None = None
    outcome: str | None = None


# ============================================================================
# Mock API app — implements expected endpoint contracts
# ============================================================================

_topics: dict[str, TopicResponse] = {}
_ws_connections: list = []

mock_api = FastAPI(title="API Gateway (Test Contract)")


@mock_api.post("/topics", response_model=TopicResponse, status_code=201)
async def create_topic(body: TopicCreate) -> TopicResponse:
    topic_id = str(uuid4())[:8]
    topic = TopicResponse(
        id=topic_id,
        name=body.name,
        description=body.description,
        priority=body.priority,
    )
    _topics[topic_id] = topic
    return topic


@mock_api.get("/topics", response_model=list[TopicResponse])
async def list_topics() -> list[TopicResponse]:
    return list(_topics.values())


@mock_api.get("/topics/{topic_id}", response_model=TopicResponse)
async def get_topic(topic_id: str) -> TopicResponse:
    if topic_id not in _topics:
        raise HTTPException(status_code=404, detail="Topic not found")
    return _topics[topic_id]


@mock_api.delete("/topics/{topic_id}", status_code=204)
async def delete_topic(topic_id: str) -> None:
    if topic_id not in _topics:
        raise HTTPException(status_code=404, detail="Topic not found")
    del _topics[topic_id]


@mock_api.post("/topics/{topic_id}/learn", status_code=202)
async def trigger_learn(topic_id: str) -> dict:
    if topic_id not in _topics:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"message": "Learning cycle started", "topic_id": topic_id}


@mock_api.post("/knowledge/search", response_model=list[SearchResult])
async def search_knowledge(body: SearchRequest) -> list[SearchResult]:
    # Mock search returns canned results
    if not body.query.strip():
        return []
    return [
        SearchResult(
            id="r1",
            name="Neural Network",
            type="concept",
            score=0.95,
            snippet="A computing system inspired by biological neural networks",
        ),
        SearchResult(
            id="r2",
            name="Deep Learning",
            type="concept",
            score=0.87,
            snippet="Subset of machine learning using multi-layer neural networks",
        ),
    ]


@mock_api.post("/knowledge/chat")
async def chat(body: ChatRequest) -> dict:
    if not body.messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    last_msg = body.messages[-1].content
    return {
        "response": f"Based on knowledge about {body.topic}: {last_msg}",
        "sources": [{"id": "e1", "name": "Relevant Entity"}],
    }


@mock_api.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        services={
            "api": "ok",
            "knowledge": "ok",
            "evaluator": "ok",
            "scraper": "ok",
        },
    )


@mock_api.get("/health/services")
async def service_health() -> dict:
    return {
        "api": {"status": "healthy", "latency_ms": 5},
        "knowledge": {"status": "healthy", "latency_ms": 12},
        "evaluator": {"status": "healthy", "latency_ms": 8},
        "scraper": {"status": "degraded", "latency_ms": 150},
    }


@mock_api.get("/dashboard/status", response_model=DashboardStatus)
async def dashboard_status() -> DashboardStatus:
    return DashboardStatus(
        current_activity="learning",
        active_topics=3,
        total_entities=150,
        total_claims=45,
        active_learning_cycles=1,
        system_health="healthy",
    )


@mock_api.get("/dashboard/progress", response_model=LearningProgress)
async def dashboard_progress() -> LearningProgress:
    return LearningProgress(
        overall_expertise=0.65,
        total_entities=150,
        total_claims=45,
        total_sources=20,
        learning_rate=5.2,
    )


@mock_api.get("/dashboard/logs", response_model=list[ActivityLog])
async def dashboard_logs() -> list[ActivityLog]:
    return [
        ActivityLog(id="l1", service="scraper", action="scrape", details="Scraped 5 pages"),
        ActivityLog(id="l2", service="extractor", action="extract", details="Extracted 10 entities"),
    ]


@mock_api.get("/dashboard/decisions", response_model=list[DecisionLog])
async def dashboard_decisions() -> list[DecisionLog]:
    return [
        DecisionLog(id="d1", decision="Focus on neural networks", reasoning="High relevance"),
        DecisionLog(
            id="d2",
            decision="Skip low-quality content",
            reasoning="Low confidence score",
            outcome="filtered",
        ),
    ]


@mock_api.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "connected", "data": {"channel": "status", "message": "Connected to status stream"}})
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "data": {}})
    except WebSocketDisconnect:
        pass


@mock_api.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "connected", "data": {"channel": "logs", "message": "Connected to log stream"}})
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "data": {}})
    except WebSocketDisconnect:
        pass


@mock_api.websocket("/ws/updates")
async def websocket_updates(websocket: WebSocket):
    await websocket.accept()
    _ws_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back with a prefix
            await websocket.send_text(f"update: {data}")
    except WebSocketDisconnect:
        _ws_connections.remove(websocket)


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def api_client():
    """Test client for the mock API gateway."""
    _topics.clear()
    transport = ASGITransport(app=mock_api)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ============================================================================
# Tests
# ============================================================================


class TestTopicCRUD:
    """Test topic management endpoints."""

    @pytest.mark.asyncio
    async def test_create_topic(self, api_client):
        resp = await api_client.post(
            "/topics",
            json={"name": "Machine Learning", "description": "ML topic", "priority": 8},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Machine Learning"
        assert data["priority"] == 8
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_topics(self, api_client):
        await api_client.post("/topics", json={"name": "ML"})
        await api_client.post("/topics", json={"name": "Biology"})
        resp = await api_client.get("/topics")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_get_topic_by_id(self, api_client):
        create_resp = await api_client.post("/topics", json={"name": "ML"})
        topic_id = create_resp.json()["id"]
        resp = await api_client.get(f"/topics/{topic_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "ML"

    @pytest.mark.asyncio
    async def test_get_nonexistent_topic_404(self, api_client):
        resp = await api_client.get("/topics/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_topic(self, api_client):
        create_resp = await api_client.post("/topics", json={"name": "ML"})
        topic_id = create_resp.json()["id"]
        del_resp = await api_client.delete(f"/topics/{topic_id}")
        assert del_resp.status_code == 204
        get_resp = await api_client.get(f"/topics/{topic_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_topic_404(self, api_client):
        resp = await api_client.delete("/topics/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_trigger_learn(self, api_client):
        create_resp = await api_client.post("/topics", json={"name": "ML"})
        topic_id = create_resp.json()["id"]
        resp = await api_client.post(f"/topics/{topic_id}/learn")
        assert resp.status_code == 202
        assert "Learning cycle started" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_trigger_learn_nonexistent_404(self, api_client):
        resp = await api_client.post("/topics/nonexistent/learn")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_topic_priority_validation(self, api_client):
        resp = await api_client.post(
            "/topics", json={"name": "ML", "priority": 11}
        )
        assert resp.status_code == 422  # validation error


class TestSearchEndpoint:
    """Test knowledge search endpoint."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, api_client):
        resp = await api_client.post(
            "/knowledge/search",
            json={"query": "neural network", "top_k": 5},
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) > 0
        assert "name" in results[0]
        assert "score" in results[0]

    @pytest.mark.asyncio
    async def test_search_with_topic_filter(self, api_client):
        resp = await api_client.post(
            "/knowledge/search",
            json={"query": "neural", "topic": "ml", "top_k": 10},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_empty_search_returns_empty(self, api_client):
        resp = await api_client.post(
            "/knowledge/search", json={"query": "", "top_k": 5}
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestChatEndpoint:
    """Test chat/conversation endpoint."""

    @pytest.mark.asyncio
    async def test_chat_returns_response(self, api_client):
        resp = await api_client.post(
            "/knowledge/chat",
            json={
                "topic": "ml",
                "messages": [
                    {"role": "user", "content": "What is deep learning?"}
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "sources" in data

    @pytest.mark.asyncio
    async def test_chat_includes_sources(self, api_client):
        resp = await api_client.post(
            "/knowledge/chat",
            json={
                "topic": "ml",
                "messages": [{"role": "user", "content": "Explain transformers"}],
            },
        )
        data = resp.json()
        assert len(data["sources"]) > 0

    @pytest.mark.asyncio
    async def test_chat_empty_messages_400(self, api_client):
        resp = await api_client.post(
            "/knowledge/chat", json={"topic": "ml", "messages": []}
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_chat_multi_turn(self, api_client):
        resp = await api_client.post(
            "/knowledge/chat",
            json={
                "topic": "ml",
                "messages": [
                    {"role": "user", "content": "What is ML?"},
                    {"role": "assistant", "content": "ML is..."},
                    {"role": "user", "content": "Tell me more"},
                ],
            },
        )
        assert resp.status_code == 200


class TestHealthEndpoints:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, api_client):
        resp = await api_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "services" in data

    @pytest.mark.asyncio
    async def test_service_health_details(self, api_client):
        resp = await api_client.get("/health/services")
        assert resp.status_code == 200
        data = resp.json()
        assert "api" in data
        assert "knowledge" in data
        assert data["api"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_service_health_includes_latency(self, api_client):
        resp = await api_client.get("/health/services")
        data = resp.json()
        for service_info in data.values():
            assert "latency_ms" in service_info


class TestOpenAPIDocumentation:
    """Test that Swagger UI and ReDoc documentation endpoints are available."""

    @pytest.mark.asyncio
    async def test_swagger_ui_loads(self, api_client):
        resp = await api_client.get("/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_redoc_loads(self, api_client):
        resp = await api_client.get("/redoc")
        assert resp.status_code == 200
        assert "redoc" in resp.text.lower() or "openapi" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_openapi_json_schema(self, api_client):
        resp = await api_client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "API Gateway (Test Contract)"
        assert "paths" in schema



    """Test WebSocket connection for real-time updates."""

    @pytest.mark.asyncio
    async def test_websocket_connect_and_receive(self):
        httpx_ws = pytest.importorskip("httpx_ws")
        transport_mod = pytest.importorskip("httpx_ws.transport")
        async with httpx_ws.aconnect_ws(
            "http://test/ws/updates",
            transport=transport_mod.ASGIWebSocketTransport(app=mock_api),
        ) as ws:
            await ws.send_text("ping")
            response = await ws.receive_text()
            assert response == "update: ping"


class TestDashboardEndpoints:
    """Test dashboard endpoints for system status and progress data."""

    @pytest.mark.asyncio
    async def test_dashboard_status_returns_200(self, api_client):
        resp = await api_client.get("/dashboard/status")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_dashboard_status_schema(self, api_client):
        resp = await api_client.get("/dashboard/status")
        data = resp.json()
        assert "current_activity" in data
        assert "active_topics" in data
        assert "total_entities" in data
        assert "system_health" in data

    @pytest.mark.asyncio
    async def test_dashboard_status_health_value(self, api_client):
        resp = await api_client.get("/dashboard/status")
        data = resp.json()
        assert data["system_health"] in ("healthy", "degraded", "unknown")

    @pytest.mark.asyncio
    async def test_dashboard_progress_returns_200(self, api_client):
        resp = await api_client.get("/dashboard/progress")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_dashboard_progress_schema(self, api_client):
        resp = await api_client.get("/dashboard/progress")
        data = resp.json()
        assert "overall_expertise" in data
        assert "total_entities" in data
        assert "total_claims" in data
        assert "learning_rate" in data

    @pytest.mark.asyncio
    async def test_dashboard_progress_expertise_in_range(self, api_client):
        resp = await api_client.get("/dashboard/progress")
        data = resp.json()
        assert 0.0 <= data["overall_expertise"] <= 1.0

    @pytest.mark.asyncio
    async def test_dashboard_logs_returns_200(self, api_client):
        resp = await api_client.get("/dashboard/logs")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_dashboard_logs_returns_list(self, api_client):
        resp = await api_client.get("/dashboard/logs")
        logs = resp.json()
        assert isinstance(logs, list)
        assert len(logs) > 0

    @pytest.mark.asyncio
    async def test_dashboard_logs_entry_schema(self, api_client):
        resp = await api_client.get("/dashboard/logs")
        entry = resp.json()[0]
        assert "id" in entry
        assert "service" in entry
        assert "action" in entry
        assert "success" in entry

    @pytest.mark.asyncio
    async def test_dashboard_decisions_returns_200(self, api_client):
        resp = await api_client.get("/dashboard/decisions")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_dashboard_decisions_returns_list(self, api_client):
        resp = await api_client.get("/dashboard/decisions")
        decisions = resp.json()
        assert isinstance(decisions, list)
        assert len(decisions) > 0

    @pytest.mark.asyncio
    async def test_dashboard_decisions_entry_schema(self, api_client):
        resp = await api_client.get("/dashboard/decisions")
        entry = resp.json()[0]
        assert "id" in entry
        assert "decision" in entry
        assert "reasoning" in entry


class TestWebSocketEndpoints:
    """Test WebSocket endpoints for real-time status and log streaming."""

    def test_ws_status_connect_and_initial_message(self):
        from starlette.testclient import TestClient

        with TestClient(mock_api) as client:
            with client.websocket_connect("/ws/status") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "connected"
                assert msg["data"]["channel"] == "status"

    def test_ws_status_ping_pong(self):
        from starlette.testclient import TestClient

        with TestClient(mock_api) as client:
            with client.websocket_connect("/ws/status") as ws:
                ws.receive_json()  # consume "connected" message
                ws.send_text("ping")
                response = ws.receive_json()
                assert response["type"] == "pong"

    def test_ws_logs_connect_and_initial_message(self):
        from starlette.testclient import TestClient

        with TestClient(mock_api) as client:
            with client.websocket_connect("/ws/logs") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "connected"
                assert msg["data"]["channel"] == "logs"

    def test_ws_logs_ping_pong(self):
        from starlette.testclient import TestClient

        with TestClient(mock_api) as client:
            with client.websocket_connect("/ws/logs") as ws:
                ws.receive_json()  # consume "connected" message
                ws.send_text("ping")
                response = ws.receive_json()
                assert response["type"] == "pong"
