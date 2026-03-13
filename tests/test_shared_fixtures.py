"""Tests that validate all shared service-client fixtures from conftest.py.

Each test exercises the corresponding ``*_client`` fixture by hitting at
least the ``/health`` endpoint, confirming the fixture creates a working
``httpx.AsyncClient`` targeting the real service app with mocked deps.
"""

import pytest


class TestAPIClientFixture:
    """Smoke-tests for the ``api_client`` fixture."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, api_client):
        resp = await api_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_list_topics_returns_empty(self, api_client):
        resp = await api_client.get("/topics")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_knowledge_search_returns_empty(self, api_client):
        resp = await api_client.get("/knowledge/search", params={"q": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total_count"] == 0


class TestScraperClientFixture:
    """Smoke-tests for the ``scraper_client`` fixture."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, scraper_client):
        resp = await scraper_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "scraper"

    @pytest.mark.asyncio
    async def test_status_endpoint_returns_service_info(self, scraper_client):
        resp = await scraper_client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "scraper"


class TestExtractorClientFixture:
    """Smoke-tests for the ``extractor_client`` fixture."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, extractor_client):
        resp = await extractor_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "extractor"


class TestKnowledgeClientFixture:
    """Smoke-tests for the ``knowledge_client`` fixture."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, knowledge_client):
        resp = await knowledge_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_get_nonexistent_entity_returns_404(self, knowledge_client):
        resp = await knowledge_client.get("/entities/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_relationships_returns_empty(self, knowledge_client):
        resp = await knowledge_client.get("/relationships")
        assert resp.status_code == 200
        assert resp.json() == []


class TestReasonerClientFixture:
    """Smoke-tests for the ``reasoner_client`` fixture."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, reasoner_client):
        resp = await reasoner_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "reasoner"


class TestOrchestratorClientFixture:
    """Smoke-tests for the ``orchestrator_client`` fixture."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, orchestrator_client):
        resp = await orchestrator_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "orchestrator"

    @pytest.mark.asyncio
    async def test_status_returns_loop_info(self, orchestrator_client):
        resp = await orchestrator_client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "loop_running" in data

    @pytest.mark.asyncio
    async def test_list_topics_returns_empty(self, orchestrator_client):
        resp = await orchestrator_client.get("/topics")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_memory_snapshot(self, orchestrator_client):
        resp = await orchestrator_client.get("/memory/snapshot")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_mock_accessible_via_module(self, orchestrator_client):
        """Demonstrate that tests can configure mocks by accessing the module."""
        import orchestrator.main as orch_mod

        orch_mod._cosmos.list_topics.return_value = []
        resp = await orchestrator_client.get("/topics")
        assert resp.status_code == 200


class TestHealerClientFixture:
    """Smoke-tests for the ``healer_client`` fixture."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, healer_client):
        resp = await healer_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "healer"

    @pytest.mark.asyncio
    async def test_status_returns_service_info(self, healer_client):
        resp = await healer_client.get("/status")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_service_health_list_empty(self, healer_client):
        resp = await healer_client.get("/health/services")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_dlq_stats_empty(self, healer_client):
        resp = await healer_client.get("/dlq/stats")
        assert resp.status_code == 200


class TestEvaluatorClientFixture:
    """Smoke-test that the existing ``evaluator_client`` fixture is still intact."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, evaluator_client):
        resp = await evaluator_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
