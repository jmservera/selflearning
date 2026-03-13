"""Configuration for the Knowledge Service."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings


class CosmosConfig(BaseModel):
    """Cosmos DB connection and schema settings."""

    endpoint: str = "https://localhost:8081"
    database_name: str = "selflearning"
    container_name: str = "knowledge"
    partition_key: str = "/topic"
    max_retry_attempts: int = 3
    max_concurrency: int = 50


class SearchConfig(BaseModel):
    """Azure AI Search settings."""

    endpoint: str = "https://localhost"
    index_prefix: str = "selflearning"
    embedding_dimensions: int = 3072  # text-embedding-3-large
    vector_algorithm: str = "hnsw"
    similarity_metric: str = "cosine"


class ServiceBusConfig(BaseModel):
    """Azure Service Bus settings."""

    namespace: str = "localhost"
    extraction_complete_topic: str = "extraction-complete"
    subscription_name: str = "knowledge-service"
    max_concurrent_calls: int = 10
    prefetch_count: int = 20


class AIFoundryConfig(BaseModel):
    """Azure AI Foundry settings for embedding generation."""

    endpoint: str = "https://localhost"
    embedding_model: str = "text-embedding-3-large"


class Settings(BaseSettings):
    """Aggregated settings for the Knowledge Service."""

    model_config = {"env_file": ".env", "extra": "ignore"}

    cosmos: CosmosConfig = Field(default_factory=CosmosConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    service_bus: ServiceBusConfig = Field(default_factory=ServiceBusConfig)
    ai_foundry: AIFoundryConfig = Field(default_factory=AIFoundryConfig)
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    service_name: str = "knowledge-service"
    app_insights_connection_string: str = Field(
        default="", validation_alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )

    @model_validator(mode="before")
    @classmethod
    def _load_nested_from_env(cls, values: dict) -> dict:
        """Populate nested sub-configs from individual environment variables."""
        env = os.environ
        if not isinstance(values.get("cosmos"), dict):
            values.setdefault(
                "cosmos",
                CosmosConfig(
                    endpoint=env.get("AZURE_COSMOS_ENDPOINT", "https://localhost:8081"),
                    database_name=env.get("COSMOS_DATABASE_NAME", "selflearning"),
                    container_name=env.get("COSMOS_CONTAINER_NAME", "knowledge"),
                ),
            )
        if not isinstance(values.get("search"), dict):
            values.setdefault(
                "search",
                SearchConfig(
                    endpoint=env.get("AZURE_SEARCH_ENDPOINT", "https://localhost"),
                    index_prefix=env.get("SEARCH_INDEX_PREFIX", "selflearning"),
                ),
            )
        if not isinstance(values.get("service_bus"), dict):
            values.setdefault(
                "service_bus",
                ServiceBusConfig(
                    namespace=env.get("AZURE_SERVICEBUS_NAMESPACE", "localhost"),
                ),
            )
        if not isinstance(values.get("ai_foundry"), dict):
            values.setdefault(
                "ai_foundry",
                AIFoundryConfig(
                    endpoint=env.get("AZURE_AI_FOUNDRY_ENDPOINT", "https://localhost"),
                    embedding_model=env.get("EMBEDDING_MODEL", "text-embedding-3-large"),
                ),
            )
        return values


def get_settings() -> Settings:
    """Build and return settings from environment."""
    return Settings()
