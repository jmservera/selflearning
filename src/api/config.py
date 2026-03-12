"""Configuration for the API Gateway service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class InternalServiceURLs:
    """Base URLs for downstream micro-services."""

    knowledge: str = field(
        default_factory=lambda: os.environ.get(
            "KNOWLEDGE_SERVICE_URL", "http://knowledge:8000"
        )
    )
    orchestrator: str = field(
        default_factory=lambda: os.environ.get(
            "ORCHESTRATOR_SERVICE_URL", "http://orchestrator:8000"
        )
    )
    evaluator: str = field(
        default_factory=lambda: os.environ.get(
            "EVALUATOR_SERVICE_URL", "http://evaluator:8000"
        )
    )
    healer: str = field(
        default_factory=lambda: os.environ.get(
            "HEALER_SERVICE_URL", "http://healer:8000"
        )
    )
    scraper: str = field(
        default_factory=lambda: os.environ.get(
            "SCRAPER_SERVICE_URL", "http://scraper:8000"
        )
    )
    extractor: str = field(
        default_factory=lambda: os.environ.get(
            "EXTRACTOR_SERVICE_URL", "http://extractor:8000"
        )
    )
    reasoner: str = field(
        default_factory=lambda: os.environ.get(
            "REASONER_SERVICE_URL", "http://reasoner:8000"
        )
    )


@dataclass(frozen=True)
class ServiceBusConfig:
    """Azure Service Bus settings for the API Gateway."""

    namespace: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_SERVICEBUS_NAMESPACE", "localhost"
        )
    )
    orchestrator_queue: str = "orchestrator-commands"
    status_topic: str = "system-status"
    status_subscription: str = "api-gateway"


@dataclass(frozen=True)
class AIFoundryConfig:
    """Azure AI Foundry settings for chat completions."""

    endpoint: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_AI_FOUNDRY_ENDPOINT", "https://localhost"
        )
    )
    chat_model: str = field(
        default_factory=lambda: os.environ.get("CHAT_MODEL", "gpt-4o")
    )
    embedding_model: str = field(
        default_factory=lambda: os.environ.get(
            "EMBEDDING_MODEL", "text-embedding-3-large"
        )
    )
    max_tokens: int = 4096
    temperature: float = 0.3


@dataclass(frozen=True)
class CORSConfig:
    """CORS middleware settings."""

    allowed_origins: list[str] = field(
        default_factory=lambda: os.environ.get(
            "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
        ).split(",")
    )
    allow_methods: list[str] = field(default_factory=lambda: ["*"])
    allow_headers: list[str] = field(default_factory=lambda: ["*"])
    allow_credentials: bool = True


@dataclass(frozen=True)
class Settings:
    """Aggregated settings for the API Gateway."""

    services: InternalServiceURLs = field(default_factory=InternalServiceURLs)
    service_bus: ServiceBusConfig = field(default_factory=ServiceBusConfig)
    ai_foundry: AIFoundryConfig = field(default_factory=AIFoundryConfig)
    cors: CORSConfig = field(default_factory=CORSConfig)
    log_level: str = field(
        default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO")
    )
    service_name: str = "api-gateway"
    app_insights_connection_string: str = field(
        default_factory=lambda: os.environ.get(
            "APPLICATIONINSIGHTS_CONNECTION_STRING", ""
        )
    )


def get_settings() -> Settings:
    return Settings()
