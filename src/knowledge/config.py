"""Configuration for the Knowledge Service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CosmosConfig:
    """Cosmos DB connection and schema settings."""

    endpoint: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_COSMOS_ENDPOINT", "https://localhost:8081"
        )
    )
    database_name: str = field(
        default_factory=lambda: os.environ.get("COSMOS_DATABASE_NAME", "selflearning")
    )
    container_name: str = field(
        default_factory=lambda: os.environ.get("COSMOS_CONTAINER_NAME", "knowledge")
    )
    partition_key: str = "/topic"
    max_retry_attempts: int = 3
    max_concurrency: int = 50


@dataclass(frozen=True)
class SearchConfig:
    """Azure AI Search settings."""

    endpoint: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_SEARCH_ENDPOINT", "https://localhost"
        )
    )
    index_prefix: str = field(
        default_factory=lambda: os.environ.get("SEARCH_INDEX_PREFIX", "selflearning")
    )
    embedding_dimensions: int = 3072  # text-embedding-3-large
    vector_algorithm: str = "hnsw"
    similarity_metric: str = "cosine"


@dataclass(frozen=True)
class ServiceBusConfig:
    """Azure Service Bus settings."""

    namespace: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_SERVICEBUS_NAMESPACE", "localhost"
        )
    )
    extraction_complete_topic: str = "extraction-complete"
    subscription_name: str = "knowledge-service"
    max_concurrent_calls: int = 10
    prefetch_count: int = 20


@dataclass(frozen=True)
class AIFoundryConfig:
    """Azure AI Foundry settings for embedding generation."""

    endpoint: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_AI_FOUNDRY_ENDPOINT", "https://localhost"
        )
    )
    embedding_model: str = field(
        default_factory=lambda: os.environ.get(
            "EMBEDDING_MODEL", "text-embedding-3-large"
        )
    )


@dataclass(frozen=True)
class Settings:
    """Aggregated settings for the Knowledge Service."""

    cosmos: CosmosConfig = field(default_factory=CosmosConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    service_bus: ServiceBusConfig = field(default_factory=ServiceBusConfig)
    ai_foundry: AIFoundryConfig = field(default_factory=AIFoundryConfig)
    log_level: str = field(
        default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO")
    )
    service_name: str = "knowledge-service"
    app_insights_connection_string: str = field(
        default_factory=lambda: os.environ.get(
            "APPLICATIONINSIGHTS_CONNECTION_STRING", ""
        )
    )


def get_settings() -> Settings:
    """Build and return immutable settings from environment."""
    return Settings()
