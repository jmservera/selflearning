"""Configuration for the Reasoner service.

All settings are loaded from environment variables using pydantic-settings.
"""

from pydantic_settings import BaseSettings


class ReasonerConfig(BaseSettings):
    """Environment-based configuration for the Reasoner service."""

    # Azure AI Foundry
    azure_ai_endpoint: str = ""
    reasoning_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-large"

    # Knowledge Service (HTTP)
    knowledge_service_url: str = "http://knowledge:8000"

    # Azure Service Bus
    servicebus_namespace: str = ""
    reasoning_requests_queue: str = "reasoning-requests"
    reasoning_complete_topic: str = "reasoning-complete"

    # LLM parameters
    max_retries: int = 3
    request_timeout_seconds: int = 180
    reasoning_temperature: float = 0.3
    max_tokens: int = 4096

    # Service
    service_name: str = "reasoner"
    log_level: str = "INFO"

    model_config = {"env_prefix": "", "case_sensitive": False}
