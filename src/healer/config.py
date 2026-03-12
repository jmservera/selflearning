"""Healer configuration — all settings via environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class HealerSettings(BaseSettings):
    """Settings for the Healer service."""

    model_config = {"env_prefix": "HEALER_", "env_file": ".env", "extra": "ignore"}

    # ── Service identity ──────────────────────────────────────────────
    service_name: str = "healer"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # ── Azure Service Bus ─────────────────────────────────────────────
    servicebus_namespace: str = Field(
        default="", description="Fully-qualified Service Bus namespace"
    )
    healing_events_topic: str = "healing-events"
    # Queues to monitor DLQs
    monitored_queues: list[str] = Field(
        default=["scrape-requests", "reasoning-requests"],
        description="Queues whose DLQs we monitor",
    )
    # Topics to monitor DLQs
    monitored_topics: list[str] = Field(
        default=[
            "scrape-complete",
            "extraction-complete",
            "reasoning-complete",
            "evaluation-complete",
        ],
        description="Topics whose subscription DLQs we monitor",
    )

    # ── Azure Container Apps management ───────────────────────────────
    subscription_id: str = Field(default="", description="Azure subscription ID")
    resource_group: str = Field(default="", description="Resource group name")
    container_app_env: str = Field(default="", description="Container Apps environment name")

    # ── Health monitoring ─────────────────────────────────────────────
    health_check_interval_seconds: float = Field(
        default=30.0, description="Seconds between health check sweeps"
    )
    dlq_check_interval_seconds: float = Field(
        default=60.0, description="Seconds between DLQ scans"
    )
    error_rate_window_seconds: float = Field(
        default=300.0, description="Window for error rate calculation"
    )
    latency_threshold_ms: float = Field(
        default=5000.0, description="Latency above this triggers degradation alert"
    )
    error_rate_threshold: float = Field(
        default=0.1, description="Error rate above 10% triggers degradation"
    )

    # ── Circuit breaker ───────────────────────────────────────────────
    circuit_failure_threshold: int = Field(
        default=5, description="Consecutive failures before opening circuit"
    )
    circuit_recovery_timeout_seconds: float = Field(
        default=60.0, description="Seconds before half-open test"
    )
    circuit_half_open_max_calls: int = Field(
        default=3, description="Test calls in half-open state"
    )

    # ── DLQ processing ────────────────────────────────────────────────
    dlq_max_replay_attempts: int = Field(
        default=3, description="Max times to replay a DLQ message"
    )
    dlq_replay_backoff_seconds: float = Field(
        default=5.0, description="Base backoff for DLQ replays"
    )
    dlq_batch_size: int = Field(
        default=10, description="Messages to read per DLQ scan"
    )

    # ── Scaling ───────────────────────────────────────────────────────
    scale_up_queue_threshold: int = Field(
        default=100, description="Queue depth triggering scale-up recommendation"
    )
    scale_down_queue_threshold: int = Field(
        default=5, description="Queue depth below which scale-down is safe"
    )

    # ── OpenTelemetry ─────────────────────────────────────────────────
    otel_service_name: str = "selflearning-healer"
    applicationinsights_connection_string: str = ""

    # ── Service URLs ──────────────────────────────────────────────────
    scraper_url: str = "http://scraper:8000"
    extractor_url: str = "http://extractor:8000"
    knowledge_url: str = "http://knowledge:8000"
    reasoner_url: str = "http://reasoner:8000"
    evaluator_url: str = "http://evaluator:8000"
    orchestrator_url: str = "http://orchestrator:8000"
    api_url: str = "http://api:8000"

    # ── AI Foundry (for prompt tuning analysis) ───────────────────────
    ai_foundry_endpoint: str = Field(default="", description="AI Foundry endpoint URL")
    ai_foundry_model: str = "gpt-4o-mini"

    @property
    def service_urls(self) -> dict[str, str]:
        """All monitored service URLs."""
        return {
            "scraper": self.scraper_url,
            "extractor": self.extractor_url,
            "knowledge": self.knowledge_url,
            "reasoner": self.reasoner_url,
            "evaluator": self.evaluator_url,
            "orchestrator": self.orchestrator_url,
            "api": self.api_url,
        }


def get_settings() -> HealerSettings:
    """Return cached settings instance."""
    return HealerSettings()
