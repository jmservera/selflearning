"""Cosmos DB client for pipeline state persistence.

Manages pipeline state, topic configuration, and learning strategies
in Azure Cosmos DB with partition-key-aligned operations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from azure.cosmos import ContainerProxy, CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential
from opentelemetry import trace

from config import OrchestratorSettings

# Cosmos DB emulator well-known master key
COSMOS_EMULATOR_KEY = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b5n7QOoRmP4MVTM+5CTVEX0Nz+6tg=="
from models import (
    LearningStrategy,
    LearningTopic,
    LoopIteration,
    PipelineState,
    TopicStatus,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _is_cosmos_emulator(endpoint: str) -> bool:
    """Check if endpoint is Cosmos DB emulator (localhost:8081 or cosmos:8081)."""
    return "localhost:8081" in endpoint or "cosmos:8081" in endpoint


class CosmosDBClient:
    """Manages all Cosmos DB operations for the Orchestrator.

    Containers:
      - pipeline-state: current pipeline state per topic (partitioned by topic)
      - topics: learning topic configuration (partitioned by name)
      - strategies: learning strategies per topic (partitioned by topic)
    """

    def __init__(self, settings: OrchestratorSettings) -> None:
        self._settings = settings
        self._client: CosmosClient | None = None
        self._pipeline_container: ContainerProxy | None = None
        self._topics_container: ContainerProxy | None = None
        self._strategies_container: ContainerProxy | None = None

    async def initialize(self) -> None:
        """Create the Cosmos client and ensure containers exist."""
        with tracer.start_as_current_span("cosmos.initialize"):
            if _is_cosmos_emulator(self._settings.cosmos_endpoint):
                logger.info("Using Cosmos DB emulator authentication")
                self._client = CosmosClient(
                    url=self._settings.cosmos_endpoint, credential=COSMOS_EMULATOR_KEY
                )
            else:
                credential = DefaultAzureCredential()
                self._client = CosmosClient(
                    url=self._settings.cosmos_endpoint, credential=credential
                )
            db = self._client.create_database_if_not_exists(self._settings.cosmos_database)

            self._pipeline_container = self._ensure_container(
                db, self._settings.cosmos_pipeline_container, "/topic"
            )
            self._topics_container = self._ensure_container(
                db, self._settings.cosmos_topics_container, "/name"
            )
            self._strategies_container = self._ensure_container(
                db, self._settings.cosmos_strategies_container, "/topic"
            )
            logger.info("Cosmos DB client initialized — database=%s", self._settings.cosmos_database)

    @staticmethod
    def _ensure_container(
        db: Any, container_id: str, partition_path: str
    ) -> ContainerProxy:
        """Create a container if it doesn't exist, or return the existing one."""
        try:
            return db.create_container(
                id=container_id,
                partition_key=PartitionKey(path=partition_path),
            )
        except CosmosResourceExistsError:
            return db.get_container_client(container_id)

    # ── Topic operations ──────────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.upsert_topic")
    def upsert_topic(self, topic: LearningTopic) -> LearningTopic:
        """Create or update a learning topic."""
        assert self._topics_container is not None
        doc = topic.model_dump(mode="json")
        doc["_partition_key"] = topic.name
        self._topics_container.upsert_item(doc)
        logger.debug("Upserted topic %s", topic.name)
        return topic

    @tracer.start_as_current_span("cosmos.get_topic")
    def get_topic(self, topic_name: str) -> LearningTopic | None:
        """Retrieve a topic by name."""
        assert self._topics_container is not None
        try:
            items = list(
                self._topics_container.query_items(
                    query="SELECT * FROM c WHERE c.name = @name",
                    parameters=[{"name": "@name", "value": topic_name}],
                    partition_key=topic_name,
                )
            )
            if items:
                return LearningTopic.model_validate(items[0])
            return None
        except CosmosResourceNotFoundError:
            return None

    @tracer.start_as_current_span("cosmos.list_topics")
    def list_topics(self, status: TopicStatus | None = None) -> list[LearningTopic]:
        """List topics, optionally filtered by status."""
        assert self._topics_container is not None
        if status is not None:
            query = "SELECT * FROM c WHERE c.status = @status"
            params = [{"name": "@status", "value": status.value}]
        else:
            query = "SELECT * FROM c"
            params = []
        items = list(
            self._topics_container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True,
            )
        )
        return [LearningTopic.model_validate(item) for item in items]

    @tracer.start_as_current_span("cosmos.update_topic_status")
    def update_topic_status(
        self, topic_name: str, status: TopicStatus
    ) -> LearningTopic | None:
        """Update the status of a topic."""
        topic = self.get_topic(topic_name)
        if topic is None:
            return None
        topic.status = status
        topic.updated_at = datetime.now(timezone.utc)
        return self.upsert_topic(topic)

    @tracer.start_as_current_span("cosmos.update_topic_score")
    def update_topic_score(
        self, topic_name: str, score: float, iteration: int
    ) -> LearningTopic | None:
        """Update a topic's current score and iteration count."""
        topic = self.get_topic(topic_name)
        if topic is None:
            return None
        topic.current_score = score
        topic.iteration_count = iteration
        topic.updated_at = datetime.now(timezone.utc)
        return self.upsert_topic(topic)

    # ── Pipeline state operations ─────────────────────────────────────

    @tracer.start_as_current_span("cosmos.upsert_pipeline_state")
    def upsert_pipeline_state(self, state: PipelineState) -> PipelineState:
        """Create or update pipeline state for a topic."""
        assert self._pipeline_container is not None
        doc = state.model_dump(mode="json")
        doc["_partition_key"] = state.topic
        self._pipeline_container.upsert_item(doc)
        logger.debug("Upserted pipeline state for topic=%s stage=%s", state.topic, state.current_stage)
        return state

    @tracer.start_as_current_span("cosmos.get_pipeline_state")
    def get_pipeline_state(self, topic: str) -> PipelineState | None:
        """Get current pipeline state for a topic."""
        assert self._pipeline_container is not None
        try:
            items = list(
                self._pipeline_container.query_items(
                    query="SELECT * FROM c WHERE c.topic = @topic ORDER BY c._ts DESC OFFSET 0 LIMIT 1",
                    parameters=[{"name": "@topic", "value": topic}],
                    partition_key=topic,
                )
            )
            if items:
                return PipelineState.model_validate(items[0])
            return None
        except CosmosResourceNotFoundError:
            return None

    @tracer.start_as_current_span("cosmos.save_iteration")
    def save_iteration(self, iteration: LoopIteration) -> None:
        """Persist a completed loop iteration record."""
        assert self._pipeline_container is not None
        doc = iteration.model_dump(mode="json")
        doc["doc_type"] = "iteration"
        doc["_partition_key"] = iteration.topic
        self._pipeline_container.upsert_item(doc)
        logger.info(
            "Saved iteration %d for topic=%s score=%.3f→%.3f",
            iteration.iteration_number,
            iteration.topic,
            iteration.score_before,
            iteration.score_after,
        )

    @tracer.start_as_current_span("cosmos.get_recent_iterations")
    def get_recent_iterations(self, topic: str, limit: int = 10) -> list[LoopIteration]:
        """Get recent iterations for a topic."""
        assert self._pipeline_container is not None
        items = list(
            self._pipeline_container.query_items(
                query=(
                    "SELECT * FROM c WHERE c.topic = @topic AND c.doc_type = 'iteration' "
                    "ORDER BY c.iteration_number DESC OFFSET 0 LIMIT @limit"
                ),
                parameters=[
                    {"name": "@topic", "value": topic},
                    {"name": "@limit", "value": limit},
                ],
                partition_key=topic,
            )
        )
        return [LoopIteration.model_validate(item) for item in items]

    # ── Strategy operations ───────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.upsert_strategy")
    def upsert_strategy(self, strategy: LearningStrategy) -> LearningStrategy:
        """Create or update a learning strategy for a topic."""
        assert self._strategies_container is not None
        strategy.updated_at = datetime.now(timezone.utc)
        doc = strategy.model_dump(mode="json")
        doc["_partition_key"] = strategy.topic
        self._strategies_container.upsert_item(doc)
        logger.debug("Upserted strategy for topic=%s mode=%s", strategy.topic, strategy.mode)
        return strategy

    @tracer.start_as_current_span("cosmos.get_strategy")
    def get_strategy(self, topic: str) -> LearningStrategy | None:
        """Get the learning strategy for a topic."""
        assert self._strategies_container is not None
        try:
            items = list(
                self._strategies_container.query_items(
                    query="SELECT * FROM c WHERE c.topic = @topic ORDER BY c._ts DESC OFFSET 0 LIMIT 1",
                    parameters=[{"name": "@topic", "value": topic}],
                    partition_key=topic,
                )
            )
            if items:
                return LearningStrategy.model_validate(items[0])
            return None
        except CosmosResourceNotFoundError:
            return None

    async def close(self) -> None:
        """Clean up resources."""
        if self._client:
            self._client.close()
            logger.info("Cosmos DB client closed")
