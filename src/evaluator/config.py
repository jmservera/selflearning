"""Evaluator service configuration — all settings via environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Evaluator service settings loaded from environment variables."""

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}

    azure_ai_endpoint: str = Field(default="", validation_alias="AZURE_AI_FOUNDRY_ENDPOINT")
    azure_servicebus_namespace: str = ""
    knowledge_service_url: str = "http://localhost:8003"
    evaluation_model: str = "gpt-4o"
    question_model: str = "gpt-4o-mini"
    service_bus_topic: str = Field(default="evaluation-complete", validation_alias="EVALUATION_TOPIC")
    max_questions_per_eval: int = 20
    scorecard_history_limit: int = 50
    # Cosmos DB (optional — falls back to in-memory when not set)
    cosmos_endpoint: str = ""
    cosmos_database: str = "selflearning"
    cosmos_container: str = Field(default="evaluations", validation_alias="COSMOS_EVALUATIONS_CONTAINER")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls()


def get_settings() -> Settings:
    """Return a Settings instance loaded from environment variables."""
    return Settings()
