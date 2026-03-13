"""Configuration for the API Gateway service."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings


class InternalServiceURLs(BaseModel):
    """Base URLs for downstream micro-services."""

    knowledge: str = "http://knowledge:8000"
    orchestrator: str = "http://orchestrator:8000"
    evaluator: str = "http://evaluator:8000"
    healer: str = "http://healer:8000"
    scraper: str = "http://scraper:8000"
    extractor: str = "http://extractor:8000"
    reasoner: str = "http://reasoner:8000"


class ServiceBusConfig(BaseModel):
    """Azure Service Bus settings for the API Gateway."""

    namespace: str = "localhost"
    orchestrator_queue: str = "orchestrator-commands"
    status_topic: str = "system-status"
    status_subscription: str = "api-gateway"


class AIFoundryConfig(BaseModel):
    """Azure AI Foundry settings for chat completions."""

    endpoint: str = "https://localhost"
    chat_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-large"
    max_tokens: int = 4096
    temperature: float = 0.3


class CORSConfig(BaseModel):
    """CORS middleware settings."""

    allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"]
    )
    allow_methods: list[str] = Field(default=["*"])
    allow_headers: list[str] = Field(default=["*"])
    allow_credentials: bool = True


class Settings(BaseSettings):
    """Aggregated settings for the API Gateway."""

    model_config = {"env_file": ".env", "extra": "ignore"}

    services: InternalServiceURLs = Field(default_factory=InternalServiceURLs)
    service_bus: ServiceBusConfig = Field(default_factory=ServiceBusConfig)
    ai_foundry: AIFoundryConfig = Field(default_factory=AIFoundryConfig)
    cors: CORSConfig = Field(default_factory=CORSConfig)
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    service_name: str = "api-gateway"
    app_insights_connection_string: str = Field(
        default="", validation_alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )

    @model_validator(mode="before")
    @classmethod
    def _load_nested_from_env(cls, values: dict) -> dict:
        """Populate nested sub-configs from individual environment variables."""
        env = os.environ
        if not isinstance(values.get("services"), dict):
            values.setdefault(
                "services",
                InternalServiceURLs(
                    knowledge=env.get("KNOWLEDGE_SERVICE_URL", "http://knowledge:8000"),
                    orchestrator=env.get("ORCHESTRATOR_SERVICE_URL", "http://orchestrator:8000"),
                    evaluator=env.get("EVALUATOR_SERVICE_URL", "http://evaluator:8000"),
                    healer=env.get("HEALER_SERVICE_URL", "http://healer:8000"),
                    scraper=env.get("SCRAPER_SERVICE_URL", "http://scraper:8000"),
                    extractor=env.get("EXTRACTOR_SERVICE_URL", "http://extractor:8000"),
                    reasoner=env.get("REASONER_SERVICE_URL", "http://reasoner:8000"),
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
                    chat_model=env.get("CHAT_MODEL", "gpt-4o"),
                    embedding_model=env.get("EMBEDDING_MODEL", "text-embedding-3-large"),
                ),
            )
        if not isinstance(values.get("cors"), dict):
            cors_origins = env.get(
                "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
            ).split(",")
            values.setdefault("cors", CORSConfig(allowed_origins=cors_origins))
        return values


def get_settings() -> Settings:
    return Settings()
