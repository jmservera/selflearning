"""Orchestrator configuration — all settings via environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class OrchestratorSettings(BaseSettings):
    """Settings for the Orchestrator service."""

    model_config = {"env_prefix": "ORCHESTRATOR_", "env_file": ".env", "extra": "ignore"}

    # ── Service identity ──────────────────────────────────────────────
    service_name: str = "orchestrator"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # ── Azure Service Bus ─────────────────────────────────────────────
    servicebus_namespace: str = Field(
        default="", description="Fully-qualified Service Bus namespace (e.g. ns.servicebus.windows.net)"
    )
    # Queues (point-to-point)
    scrape_requests_queue: str = "scrape-requests"
    reasoning_requests_queue: str = "reasoning-requests"
    # Topics (pub/sub) — orchestrator subscribes to completion events
    scrape_complete_topic: str = "scrape-complete"
    extraction_complete_topic: str = "extraction-complete"
    reasoning_complete_topic: str = "reasoning-complete"
    evaluation_complete_topic: str = "evaluation-complete"
    # Subscription name for this service
    subscription_name: str = "orchestrator-sub"

    # ── Azure Cosmos DB ───────────────────────────────────────────────
    cosmos_endpoint: str = Field(default="", description="Cosmos DB account endpoint URL")
    cosmos_database: str = "selflearning"
    cosmos_pipeline_container: str = "pipeline-state"
    cosmos_topics_container: str = "topics"
    cosmos_strategies_container: str = "strategies"

    # ── Azure AI Foundry ──────────────────────────────────────────────
    ai_foundry_endpoint: str = Field(default="", description="AI Foundry endpoint URL")
    ai_foundry_model: str = "gpt-4o"
    ai_foundry_mini_model: str = "gpt-4o-mini"

    # ── Learning loop tuning ──────────────────────────────────────────
    loop_interval_seconds: float = Field(
        default=30.0, description="Seconds between loop ticks when idle"
    )
    max_concurrent_topics: int = Field(
        default=5, description="Maximum topics processed simultaneously"
    )
    scrape_wait_timeout_seconds: float = Field(
        default=300.0, description="Max seconds to wait for scrape completion"
    )
    extraction_wait_timeout_seconds: float = Field(
        default=300.0, description="Max seconds to wait for extraction completion"
    )
    reasoning_wait_timeout_seconds: float = Field(
        default=300.0, description="Max seconds to wait for reasoning completion"
    )
    evaluation_wait_timeout_seconds: float = Field(
        default=300.0, description="Max seconds to wait for evaluation completion"
    )
    max_stale_iterations: int = Field(
        default=3, description="Iterations without score improvement before backoff"
    )
    backoff_multiplier: float = Field(
        default=2.0, description="Multiplier applied to loop interval on backoff"
    )
    max_backoff_seconds: float = Field(
        default=600.0, description="Ceiling for exponential backoff"
    )
    min_sources_per_query: int = Field(
        default=3, description="Minimum unique sources before accepting breadth"
    )
    depth_threshold: float = Field(
        default=0.7, description="Coverage fraction that triggers depth-over-breadth mode"
    )

    # ── Working memory ────────────────────────────────────────────────
    working_memory_max_items: int = Field(
        default=50, description="Maximum items retained in working memory"
    )
    working_memory_decay_factor: float = Field(
        default=0.9, description="Relevance decay per tick for unfocused items"
    )

    # ── OpenTelemetry ─────────────────────────────────────────────────
    otel_service_name: str = "selflearning-orchestrator"
    applicationinsights_connection_string: str = ""

    # ── Service URLs (for direct health checks) ──────────────────────
    scraper_url: str = "http://scraper:8000"
    extractor_url: str = "http://extractor:8000"
    knowledge_url: str = "http://knowledge:8000"
    reasoner_url: str = "http://reasoner:8000"
    evaluator_url: str = "http://evaluator:8000"
    healer_url: str = "http://healer:8000"
    api_url: str = "http://api:8000"


def get_settings() -> OrchestratorSettings:
    """Return cached settings instance."""
    return OrchestratorSettings()
