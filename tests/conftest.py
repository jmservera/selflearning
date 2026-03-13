"""Shared pytest fixtures for the selflearning test suite.

Provides mock Azure clients, mock LLM, sample data, and FastAPI test clients.
"""

import json
import os
import sys
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
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
