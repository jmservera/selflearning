"""Evaluator service configuration."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Evaluator service settings loaded from environment variables."""

    azure_ai_endpoint: str = ""
    azure_servicebus_namespace: str = ""
    knowledge_service_url: str = "http://localhost:8003"
    evaluation_model: str = "gpt-4o"
    question_model: str = "gpt-4o-mini"
    service_bus_topic: str = "evaluation-complete"
    max_questions_per_eval: int = 20
    scorecard_history_limit: int = 50
    # Cosmos DB (optional — falls back to in-memory when not set)
    cosmos_endpoint: str = ""
    cosmos_database: str = "selflearning"
    cosmos_container: str = "evaluations"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            azure_ai_endpoint=os.getenv("AZURE_AI_FOUNDRY_ENDPOINT", ""),
            azure_servicebus_namespace=os.getenv("AZURE_SERVICEBUS_NAMESPACE", ""),
            knowledge_service_url=os.getenv(
                "KNOWLEDGE_SERVICE_URL", "http://localhost:8003"
            ),
            evaluation_model=os.getenv("EVALUATION_MODEL", "gpt-4o"),
            question_model=os.getenv("QUESTION_MODEL", "gpt-4o-mini"),
            service_bus_topic=os.getenv("EVALUATION_TOPIC", "evaluation-complete"),
            max_questions_per_eval=int(os.getenv("MAX_QUESTIONS_PER_EVAL", "20")),
            scorecard_history_limit=int(os.getenv("SCORECARD_HISTORY_LIMIT", "50")),
            cosmos_endpoint=os.getenv("COSMOS_ENDPOINT", ""),
            cosmos_database=os.getenv("COSMOS_DATABASE", "selflearning"),
            cosmos_container=os.getenv("COSMOS_EVALUATIONS_CONTAINER", "evaluations"),
        )
