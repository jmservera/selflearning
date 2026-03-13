"""Shared pytest fixtures for the selflearning test suite.

Provides mock Azure clients, mock LLM, sample data, and FastAPI test clients
for all 8 selflearning micro-services.
"""

import importlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# pytest-asyncio configuration
# ---------------------------------------------------------------------------
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "slow: slow-running tests")


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------
class MockLLMClient:
    """Mock LLM that returns canned JSON responses."""

    def __init__(self) -> None:
        self.call_log: list[dict[str, str]] = []
        self._question_response: str | None = None
        self._eval_response: str | None = None

    def set_question_response(self, questions: list[dict]) -> None:
        self._question_response = json.dumps(questions)

    def set_eval_response(self, result: dict) -> None:
        self._eval_response = json.dumps(result)

    async def complete(self, prompt: str, model: str) -> str:
        self.call_log.append({"prompt": prompt[:200], "model": model})
        if "qualifying-exam" in prompt or "Generate" in prompt:
            return self._question_response or json.dumps(
                [
                    {
                        "question": "What is the primary mechanism of neural plasticity?",
                        "difficulty": "phd",
                        "expected_answer_keywords": [
                            "synaptic",
                            "plasticity",
                            "neurons",
                            "learning",
                        ],
                        "category": "factual_recall",
                    },
                    {
                        "question": "Explain the role of backpropagation in deep learning.",
                        "difficulty": "masters",
                        "expected_answer_keywords": [
                            "gradient",
                            "loss",
                            "weights",
                            "chain rule",
                        ],
                        "category": "reasoning",
                    },
                    {
                        "question": "What is a neural network?",
                        "difficulty": "undergrad",
                        "expected_answer_keywords": [
                            "layers",
                            "neurons",
                            "activation",
                        ],
                        "category": "factual_recall",
                    },
                ]
            )
        if "Evaluate" in prompt or "evaluating" in prompt:
            return self._eval_response or json.dumps(
                {"correct": True, "confidence": 0.85, "reasoning": "Good answer"}
            )
        return "[]"


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient()


# ---------------------------------------------------------------------------
# Mock Azure Service Bus
# ---------------------------------------------------------------------------
class MockServiceBusSender:
    """In-memory Service Bus sender that records messages."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_messages(self, message: Any) -> None:
        body = message.body if hasattr(message, "body") else str(message)
        if isinstance(body, bytes):
            body = body.decode()
        self.messages.append(json.loads(body) if isinstance(body, str) else body)

    async def close(self) -> None:
        pass


class MockServiceBusClient:
    """Mock Service Bus client."""

    def __init__(self) -> None:
        self.senders: dict[str, MockServiceBusSender] = {}

    def get_topic_sender(self, topic_name: str) -> MockServiceBusSender:
        if topic_name not in self.senders:
            self.senders[topic_name] = MockServiceBusSender()
        return self.senders[topic_name]

    def get_queue_sender(self, queue_name: str) -> MockServiceBusSender:
        return self.get_topic_sender(queue_name)

    async def close(self) -> None:
        pass


@pytest.fixture
def mock_servicebus() -> MockServiceBusClient:
    return MockServiceBusClient()


# ---------------------------------------------------------------------------
# Mock Cosmos DB
# ---------------------------------------------------------------------------
class MockCosmosContainer:
    """In-memory Cosmos DB container."""

    def __init__(self) -> None:
        self.items: dict[str, dict] = {}

    async def create_item(self, body: dict) -> dict:
        item_id = body.get("id", str(uuid4()))
        body["id"] = item_id
        self.items[item_id] = body
        return body

    async def read_item(self, item: str, partition_key: str) -> dict:
        if item not in self.items:
            raise KeyError(f"Item {item} not found")
        return self.items[item]

    async def upsert_item(self, body: dict) -> dict:
        return await self.create_item(body)

    async def delete_item(self, item: str, partition_key: str) -> None:
        self.items.pop(item, None)

    def query_items(
        self, query: str, parameters: list | None = None, **kwargs
    ) -> list[dict]:
        return list(self.items.values())


class MockCosmosDatabase:
    """Mock Cosmos DB database."""

    def __init__(self) -> None:
        self.containers: dict[str, MockCosmosContainer] = {}

    def get_container_client(self, container_name: str) -> MockCosmosContainer:
        if container_name not in self.containers:
            self.containers[container_name] = MockCosmosContainer()
        return self.containers[container_name]


class MockCosmosClient:
    """Mock Cosmos DB client."""

    def __init__(self) -> None:
        self.databases: dict[str, MockCosmosDatabase] = {}

    def get_database_client(self, database_name: str) -> MockCosmosDatabase:
        if database_name not in self.databases:
            self.databases[database_name] = MockCosmosDatabase()
        return self.databases[database_name]


@pytest.fixture
def mock_cosmos() -> MockCosmosClient:
    return MockCosmosClient()


# ---------------------------------------------------------------------------
# Mock Blob Storage
# ---------------------------------------------------------------------------
class MockBlobClient:
    """In-memory blob storage."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    async def upload_blob(
        self, name: str, data: bytes, overwrite: bool = True
    ) -> None:
        self.blobs[name] = data

    async def download_blob(self, name: str) -> bytes:
        if name not in self.blobs:
            raise KeyError(f"Blob {name} not found")
        return self.blobs[name]


@pytest.fixture
def mock_blob_storage() -> MockBlobClient:
    return MockBlobClient()


# ---------------------------------------------------------------------------
# Mock AI Search
# ---------------------------------------------------------------------------
class MockSearchClient:
    """In-memory search index."""

    def __init__(self) -> None:
        self.documents: list[dict] = []

    async def upload_documents(self, documents: list[dict]) -> None:
        self.documents.extend(documents)

    async def search(
        self, search_text: str, top: int = 10, **kwargs
    ) -> list[dict]:
        results = []
        for doc in self.documents:
            text = json.dumps(doc).lower()
            if search_text.lower() in text:
                results.append(doc)
        return results[:top]


@pytest.fixture
def mock_search() -> MockSearchClient:
    return MockSearchClient()


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_entities() -> list[dict[str, Any]]:
    """Sample knowledge graph entities for testing."""
    return [
        {
            "id": "e1",
            "name": "Neural Network",
            "type": "concept",
            "category": "core_concepts",
            "description": "A computing system inspired by biological neural networks",
            "confidence": 0.95,
            "topic": "machine_learning",
        },
        {
            "id": "e2",
            "name": "Geoffrey Hinton",
            "type": "person",
            "category": "key_figures",
            "description": "Pioneer of deep learning and backpropagation",
            "confidence": 0.98,
            "topic": "machine_learning",
        },
        {
            "id": "e3",
            "name": "Backpropagation",
            "type": "method",
            "category": "methodologies",
            "description": "Algorithm for training neural networks using gradient descent",
            "confidence": 0.92,
            "topic": "machine_learning",
        },
        {
            "id": "e4",
            "name": "Image Classification",
            "type": "concept",
            "category": "applications",
            "description": "Using ML models to categorize images into classes",
            "confidence": 0.88,
            "topic": "machine_learning",
        },
        {
            "id": "e5",
            "name": "Perceptron",
            "type": "concept",
            "category": "history",
            "description": "Early single-layer neural network model from 1958",
            "confidence": 0.90,
            "topic": "machine_learning",
        },
        {
            "id": "e6",
            "name": "Transformer Architecture",
            "type": "method",
            "category": "current_research",
            "description": "Attention-based architecture for sequence modeling",
            "confidence": 0.94,
            "topic": "machine_learning",
        },
        {
            "id": "e7",
            "name": "Bias in AI",
            "type": "concept",
            "category": "controversies",
            "description": "Systematic errors in AI systems that create unfair outcomes",
            "confidence": 0.85,
            "topic": "machine_learning",
        },
        {
            "id": "e8",
            "name": "Statistics",
            "type": "concept",
            "category": "related_fields",
            "description": "Mathematical discipline underlying machine learning theory",
            "confidence": 0.91,
            "topic": "machine_learning",
        },
        {
            "id": "e9",
            "name": "Convolutional Neural Network",
            "type": "concept",
            "category": "core_concepts",
            "description": "Neural network using convolutional layers for spatial data",
            "confidence": 0.93,
            "topic": "machine_learning",
        },
        {
            "id": "e10",
            "name": "Yann LeCun",
            "type": "person",
            "category": "key_figures",
            "description": "Pioneer of convolutional neural networks",
            "confidence": 0.96,
            "topic": "machine_learning",
        },
    ]


@pytest.fixture
def sample_claims() -> list[dict[str, Any]]:
    """Sample knowledge graph claims for testing."""
    return [
        {
            "id": "c1",
            "text": "Neural networks can approximate any continuous function",
            "confidence": 0.92,
            "source_id": "s1",
            "topic": "machine_learning",
        },
        {
            "id": "c2",
            "text": "Backpropagation computes gradients using the chain rule",
            "confidence": 0.98,
            "source_id": "s1",
            "topic": "machine_learning",
        },
        {
            "id": "c3",
            "text": "Deep learning requires large amounts of labeled training data",
            "confidence": 0.75,
            "source_id": "s2",
            "topic": "machine_learning",
        },
        {
            "id": "c4",
            "text": "Transformers use self-attention mechanisms for parallel processing",
            "confidence": 0.95,
            "source_id": "s3",
            "topic": "machine_learning",
        },
        {
            "id": "c5",
            "text": "Gradient descent can converge to local minima in non-convex problems",
            "confidence": 0.88,
            "source_id": "s2",
            "topic": "machine_learning",
        },
    ]


@pytest.fixture
def sample_relationships() -> list[dict[str, Any]]:
    """Sample knowledge graph relationships for testing."""
    return [
        {
            "id": "r1",
            "source_id": "e1",
            "target_id": "e3",
            "type": "trained_by",
            "topic": "machine_learning",
        },
        {
            "id": "r2",
            "source_id": "e2",
            "target_id": "e3",
            "type": "invented",
            "topic": "machine_learning",
        },
        {
            "id": "r3",
            "source_id": "e9",
            "target_id": "e4",
            "type": "used_for",
            "topic": "machine_learning",
        },
        {
            "id": "r4",
            "source_id": "e10",
            "target_id": "e9",
            "type": "developed",
            "topic": "machine_learning",
        },
    ]


# ---------------------------------------------------------------------------
# Evaluator service test client
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def evaluator_client(
    mock_llm: MockLLMClient,
    sample_entities: list[dict],
    sample_claims: list[dict],
    sample_relationships: list[dict],
):
    """Create a test client for the evaluator FastAPI app with mocked deps."""
    import respx

    from evaluator.config import Settings
    from evaluator.evaluation import EvaluationEngine
    from evaluator.knowledge_client import KnowledgeClient
    from evaluator.main import (
        _gap_store,
        _reports,
        _scorecard_history,
        app,
    )
    from evaluator.main import engine as _engine
    from evaluator.main import knowledge_client as _kc
    from evaluator.question_generator import QuestionGenerator

    # Clear any previous state
    _scorecard_history.clear()
    _gap_store.clear()
    _reports.clear()

    settings = Settings(
        knowledge_service_url="http://mock-knowledge:8003",
        evaluation_model="gpt-4o",
        question_model="gpt-4o-mini",
        max_questions_per_eval=3,
    )

    # Create mock knowledge service using respx
    mock_router = respx.MockRouter(assert_all_mocked=False, assert_all_called=False)
    mock_router.get("http://mock-knowledge:8003/entities").respond(
        json=sample_entities
    )
    mock_router.get("http://mock-knowledge:8003/claims").respond(
        json=sample_claims
    )
    mock_router.get("http://mock-knowledge:8003/relationships").respond(
        json=sample_relationships
    )

    async with httpx.AsyncClient(base_url="http://mock-knowledge:8003") as http:
        with mock_router:
            kc = KnowledgeClient("http://mock-knowledge:8003", client=http)
            qgen = QuestionGenerator(mock_llm, model="gpt-4o-mini")
            eval_engine = EvaluationEngine(kc, qgen, max_questions=3)

            # Inject mocked dependencies into the app module
            import evaluator.main as main_module

            main_module.engine = eval_engine
            main_module.knowledge_client = kc
            main_module.publisher = None
            main_module.cosmos_client = None
            main_module.settings = settings

            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                yield client

            # Cleanup
            main_module.engine = None
            main_module.knowledge_client = None
            main_module.cosmos_client = None


# ---------------------------------------------------------------------------
# Shared service-path helper for bare-import services
# ---------------------------------------------------------------------------

# Bare module names that must be evicted from sys.modules before switching
# between services that use non-package-qualified imports (e.g.
# ``from config import …`` instead of ``from orchestrator.config import …``).
_BARE_MODULE_NAMES: frozenset[str] = frozenset({
    "config", "models", "service_bus",
    # orchestrator
    "working_memory", "strategy", "cosmos_client", "learning_loop",
    # healer
    "health_monitor",
    # reasoner
    "llm_client", "reasoning",
    # scraper
    "storage",
    # extractor
    "blob_storage", "extraction",
})

# Service sub-directories managed by _setup_service_path
_BARE_SERVICE_NAMES: frozenset[str] = frozenset({
    "orchestrator", "healer", "reasoner", "scraper", "extractor",
})


def _setup_service_path(service_name: str) -> None:
    """Flush stale bare-module caches and configure sys.path for *service_name*.

    Services that use bare imports (``from config import …``) instead of
    package-qualified imports need their directory on ``sys.path`` so that
    Python can resolve those bare module names.  This helper removes stale
    entries and inserts the correct service directory after the ``src/``
    entry so that package-qualified imports still take precedence.

    Must be called before importing a bare-import service's ``main`` module.
    """
    src_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src"))
    svc_dir = os.path.normpath(os.path.join(src_dir, service_name))
    for name in _BARE_MODULE_NAMES:
        sys.modules.pop(name, None)
    # Remove all bare-import service directories to avoid cross-contamination.
    svc_dirs = {
        os.path.normpath(os.path.join(src_dir, s)) for s in _BARE_SERVICE_NAMES
    }
    sys.path[:] = [p for p in sys.path if os.path.normpath(p) not in svc_dirs]
    src_positions = [
        i for i, p in enumerate(sys.path) if os.path.normpath(p) == src_dir
    ]
    insert_pos = (src_positions[0] + 1) if src_positions else 0
    sys.path.insert(insert_pos, svc_dir)


def _alias_service_modules(service_name: str, module_names: list[str]) -> None:
    """Register bare-name sys.modules aliases for *service_name*'s submodules.

    After calling ``_setup_service_path(service_name)``, the service's
    submodules can be imported as bare names (e.g. ``import config``).
    This function forces those submodule imports and records them in
    ``sys.modules`` under both the bare name and the qualified name so
    that in-module ``from config import …`` statements resolve correctly.
    """
    for name in module_names:
        mod = importlib.import_module(f"{service_name}.{name}")
        sys.modules[name] = mod


# ---------------------------------------------------------------------------
# API Gateway service test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def api_client():
    """Create a test client for the API Gateway (src/api/main.py) with mocked downstream services.

    Replaces the module-level ``orchestrator``, ``knowledge``, ``bus``, and
    ``chat_handler`` singletons with ``MagicMock`` / ``AsyncMock`` objects so
    that the FastAPI endpoints can be exercised without real network connections.

    Yields:
        httpx.AsyncClient: Configured test client targeting the API Gateway app.
    """
    import api.main as api_mod
    from api.models import ChatResponse

    mock_orch = MagicMock()
    mock_orch.create_topic = AsyncMock(
        return_value={
            "id": "t1",
            "name": "test",
            "description": "",
            "priority": 5,
            "target_expertise": 0.9,
            "status": "active",
        }
    )
    mock_orch.list_topics = AsyncMock(return_value=[])
    mock_orch.get_topic = AsyncMock(return_value=None)
    mock_orch.trigger_learning = AsyncMock(return_value={"status": "started"})
    mock_orch.pause_topic = AsyncMock(return_value={"status": "paused"})
    mock_orch.resume_topic = AsyncMock(return_value={"status": "resumed"})
    mock_orch.update_priority = AsyncMock(return_value={"status": "updated"})
    mock_orch.get_status = AsyncMock(return_value={"current_activity": "idle"})
    mock_orch.get_progress = AsyncMock(return_value={})
    mock_orch.get_logs = AsyncMock(return_value=[])
    mock_orch.get_decisions = AsyncMock(return_value=[])

    mock_knowledge = MagicMock()
    mock_knowledge.search = AsyncMock(
        return_value={"items": [], "total_count": 0, "facets": {}}
    )
    mock_knowledge.get_entity = AsyncMock(return_value=None)
    mock_knowledge.topic_stats = AsyncMock(return_value={})
    mock_knowledge.topic_graph = AsyncMock(
        return_value={"entities": [], "relationships": []}
    )

    mock_bus = MagicMock()
    mock_bus.publish_command = AsyncMock()
    mock_bus.publish_learn = AsyncMock()
    mock_bus.publish_pause = AsyncMock()
    mock_bus.publish_resume = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.handle = AsyncMock(
        return_value=ChatResponse(answer="mocked answer", confidence=1.0)
    )

    # Save originals and inject mocks
    orig = {
        "orchestrator": api_mod.orchestrator,
        "knowledge": api_mod.knowledge,
        "bus": api_mod.bus,
        "chat_handler": api_mod.chat_handler,
    }
    api_mod.orchestrator = mock_orch
    api_mod.knowledge = mock_knowledge
    api_mod.bus = mock_bus
    api_mod.chat_handler = mock_chat

    transport = ASGITransport(app=api_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Restore original singletons
    api_mod.orchestrator = orig["orchestrator"]
    api_mod.knowledge = orig["knowledge"]
    api_mod.bus = orig["bus"]
    api_mod.chat_handler = orig["chat_handler"]


# ---------------------------------------------------------------------------
# Scraper service test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def scraper_client():
    """Create a test client for the Scraper service (src/scraper/main.py) with mocked deps.

    Calls ``_setup_service_path("scraper")`` to make the service's bare imports
    (``from config import …``) resolvable, patches the ``scraper`` package so
    that ``from scraper import WebScraper`` resolves to ``scraper.scraper``, and
    injects ``MagicMock`` objects for all module-level singletons.

    Yields:
        httpx.AsyncClient: Configured test client targeting the Scraper app.
    """
    _setup_service_path("scraper")
    _alias_service_modules(
        "scraper", ["config", "models", "service_bus", "storage"]
    )

    # ``scraper/main.py`` does ``from scraper import WebScraper`` — the bare name
    # ``scraper`` resolves to the package, so we expose WebScraper on it.
    import scraper as _scraper_pkg
    from scraper.scraper import WebScraper

    _scraper_pkg.WebScraper = WebScraper

    import scraper.main as scraper_mod

    mock_scraper = MagicMock()
    mock_publisher = MagicMock()
    mock_history = MagicMock()
    mock_history.get_crawl_stats = AsyncMock(return_value={})
    mock_blob = MagicMock()
    mock_consumer = MagicMock()
    mock_consumer.stats = {}

    scraper_mod._web_scraper = mock_scraper
    scraper_mod._publisher = mock_publisher
    scraper_mod._history_client = mock_history
    scraper_mod._blob_client = mock_blob
    scraper_mod._consumer = mock_consumer
    scraper_mod._started_at = datetime.now(timezone.utc)

    transport = ASGITransport(app=scraper_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Cleanup
    scraper_mod._web_scraper = None
    scraper_mod._publisher = None
    scraper_mod._history_client = None
    scraper_mod._blob_client = None
    scraper_mod._consumer = None
    scraper_mod._started_at = None


# ---------------------------------------------------------------------------
# Extractor service test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def extractor_client():
    """Create a test client for the Extractor service (src/extractor/main.py) with mocked deps.

    Calls ``_setup_service_path("extractor")`` and registers bare-name aliases
    for the service's internal modules, then injects ``MagicMock`` objects for
    the module-level singletons used by the FastAPI endpoints.

    Yields:
        httpx.AsyncClient: Configured test client targeting the Extractor app.
    """
    _setup_service_path("extractor")
    _alias_service_modules(
        "extractor",
        ["config", "blob_storage", "extraction", "llm_client", "models", "service_bus"],
    )

    import extractor.main as extractor_mod

    mock_pipeline = MagicMock()
    mock_llm = MagicMock()
    mock_blob = MagicMock()
    mock_bus = MagicMock()

    extractor_mod.pipeline = mock_pipeline
    extractor_mod.llm_client = mock_llm
    extractor_mod.blob_client = mock_blob
    extractor_mod.service_bus = mock_bus
    extractor_mod._consumer_task = None

    transport = ASGITransport(app=extractor_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Cleanup
    extractor_mod.pipeline = None
    extractor_mod.llm_client = None
    extractor_mod.blob_client = None
    extractor_mod.service_bus = None


# ---------------------------------------------------------------------------
# Knowledge service test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def knowledge_client():
    """Create a test client for the Knowledge service (src/knowledge/main.py) with mocked deps.

    Replaces the module-level ``store``, ``search``, and ``consumer`` singletons
    with ``MagicMock`` / ``AsyncMock`` objects.  The Knowledge service uses
    package-qualified imports so no sys.path manipulation is required.

    Yields:
        httpx.AsyncClient: Configured test client targeting the Knowledge app.
    """
    import knowledge.main as knowledge_mod

    mock_store = MagicMock()
    mock_store.upsert_entity = AsyncMock()
    mock_store.get_entity = AsyncMock(return_value=None)
    mock_store.search_entities = AsyncMock(return_value=[])
    mock_store.upsert_relationship = AsyncMock()
    mock_store.query_relationships = AsyncMock(return_value=[])
    mock_store.upsert_claim = AsyncMock()
    mock_store.query_claims = AsyncMock(return_value=[])
    mock_store.upsert_source = AsyncMock()
    mock_store.topic_stats = AsyncMock(return_value={})
    mock_store.topic_summary = AsyncMock(return_value={})

    mock_search = MagicMock()
    mock_search.ensure_index = AsyncMock()
    mock_search.index_documents = AsyncMock()
    mock_search.search = AsyncMock(
        return_value=MagicMock(items=[], total_count=0, facets={})
    )

    mock_consumer = MagicMock()

    orig_store = knowledge_mod.store
    orig_search = knowledge_mod.search
    orig_consumer = knowledge_mod.consumer

    knowledge_mod.store = mock_store
    knowledge_mod.search = mock_search
    knowledge_mod.consumer = mock_consumer

    transport = ASGITransport(app=knowledge_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Restore originals
    knowledge_mod.store = orig_store
    knowledge_mod.search = orig_search
    knowledge_mod.consumer = orig_consumer


# ---------------------------------------------------------------------------
# Reasoner service test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def reasoner_client():
    """Create a test client for the Reasoner service (src/reasoner/main.py) with mocked deps.

    Calls ``_setup_service_path("reasoner")`` and registers bare-name aliases,
    then injects ``MagicMock`` objects for the module-level singletons used by
    the FastAPI app.

    Yields:
        httpx.AsyncClient: Configured test client targeting the Reasoner app.
    """
    _setup_service_path("reasoner")
    _alias_service_modules(
        "reasoner", ["config", "models", "llm_client", "reasoning", "service_bus"]
    )

    import reasoner.main as reasoner_mod

    mock_engine = MagicMock()
    mock_engine.run = AsyncMock(return_value=MagicMock(model_dump=lambda **_: {}))
    mock_llm = MagicMock()
    mock_kc = MagicMock()
    mock_bus = MagicMock()

    reasoner_mod.engine = mock_engine
    reasoner_mod.llm_client = mock_llm
    reasoner_mod.knowledge_client = mock_kc
    reasoner_mod.service_bus = mock_bus
    reasoner_mod._consumer_task = None

    transport = ASGITransport(app=reasoner_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Cleanup
    reasoner_mod.engine = None
    reasoner_mod.llm_client = None
    reasoner_mod.knowledge_client = None
    reasoner_mod.service_bus = None


# ---------------------------------------------------------------------------
# Orchestrator service test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def orchestrator_client():
    """Create a test client for the Orchestrator service (src/orchestrator/main.py) with mocked deps.

    Calls ``_setup_service_path("orchestrator")`` and registers bare-name aliases,
    then injects ``MagicMock`` objects for the module-level singletons.  Sensible
    default return values are configured so that most endpoint tests work
    without additional mock setup.

    Yields:
        httpx.AsyncClient: Configured test client targeting the Orchestrator app.
    """
    _setup_service_path("orchestrator")
    _alias_service_modules(
        "orchestrator",
        [
            "config",
            "models",
            "service_bus",
            "working_memory",
            "strategy",
            "cosmos_client",
            "learning_loop",
        ],
    )

    import orchestrator.main as orch_mod
    from orchestrator.config import OrchestratorSettings

    mock_cosmos = MagicMock()
    mock_cosmos.list_topics.return_value = []
    mock_cosmos.get_topic.return_value = None
    mock_cosmos.update_topic_status.return_value = None

    mock_loop = MagicMock()
    mock_loop.get_status.return_value = {
        "running": False,
        "current_stages": {},
        "iterations_completed": {},
    }
    mock_loop.get_topic_pipeline.return_value = {}

    mock_memory = MagicMock()
    mock_memory.snapshot.return_value = {}
    mock_memory.build_prompt_context.return_value = ""

    orch_mod._cosmos = mock_cosmos
    orch_mod._loop = mock_loop
    orch_mod._memory = mock_memory
    orch_mod._settings = OrchestratorSettings()
    orch_mod._start_time = time.monotonic()

    transport = ASGITransport(app=orch_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Cleanup
    orch_mod._cosmos = None
    orch_mod._loop = None
    orch_mod._memory = None


# ---------------------------------------------------------------------------
# Healer service test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def healer_client():
    """Create a test client for the Healer service (src/healer/main.py) with mocked deps.

    Calls ``_setup_service_path("healer")`` and registers bare-name aliases,
    patches the ``healer`` package so that ``from healer import Healer``
    resolves correctly, and injects ``MagicMock`` objects for the module-level
    singletons.

    Some Azure SDK submodules used by the Healer are not available in the test
    environment; they are pre-empted with ``MagicMock`` stubs via
    ``sys.modules.setdefault`` before any healer imports are attempted.

    Yields:
        httpx.AsyncClient: Configured test client targeting the Healer app.
    """
    # Pre-empt Azure SDK submodules that are unavailable in the test environment.
    # Using setdefault avoids overwriting the real module if it is installed.
    sys.modules.setdefault("azure.mgmt", MagicMock())
    sys.modules.setdefault("azure.mgmt.appcontainers", MagicMock())
    sys.modules.setdefault("azure.mgmt.appcontainers.aio", MagicMock())
    sys.modules.setdefault("azure.servicebus.management.aio", MagicMock())

    _setup_service_path("healer")
    _alias_service_modules(
        "healer", ["config", "models", "service_bus", "health_monitor"]
    )

    # ``healer/main.py`` does ``from healer import Healer`` — expose it on the pkg.
    import healer as _healer_pkg
    from healer.healer import Healer

    _healer_pkg.Healer = Healer

    import healer.main as healer_mod
    from healer.config import HealerSettings

    mock_monitor = MagicMock()
    mock_monitor.service_health = {}
    mock_monitor.circuits = {}
    mock_monitor.dlq_stats = []
    mock_monitor.get_issues.return_value = []
    mock_monitor.actions_today = 0
    mock_monitor.last_health_check = datetime.now(timezone.utc)
    mock_monitor.last_dlq_scan = datetime.now(timezone.utc)

    mock_healer = MagicMock()
    mock_healer.action_log = []
    mock_healer.heal_service = AsyncMock(return_value=[])

    healer_mod._monitor = mock_monitor
    healer_mod._healer = mock_healer
    healer_mod._settings = HealerSettings()
    healer_mod._start_time = time.monotonic()

    transport = ASGITransport(app=healer_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Cleanup
    healer_mod._monitor = None
    healer_mod._healer = None
