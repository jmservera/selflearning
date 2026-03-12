"""Configuration for the Extractor service.

All settings are loaded from environment variables using pydantic-settings.
"""

from pydantic_settings import BaseSettings


class ExtractorConfig(BaseSettings):
    """Environment-based configuration for the Extractor service."""

    # Azure AI Foundry
    azure_ai_endpoint: str = ""
    extraction_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-large"

    # Azure Service Bus
    servicebus_namespace: str = ""
    scrape_complete_topic: str = "scrape-complete"
    scrape_complete_subscription: str = "extractor"
    extraction_complete_topic: str = "extraction-complete"

    # Azure Blob Storage
    storage_account_url: str = ""
    raw_content_container: str = "raw-content"

    # Chunking parameters
    chunk_size: int = 4000
    chunk_overlap: int = 200

    # LLM parameters
    max_retries: int = 3
    request_timeout_seconds: int = 120
    extraction_temperature: float = 0.1
    max_tokens: int = 4096
    embedding_batch_size: int = 16

    # Service
    service_name: str = "extractor"
    log_level: str = "INFO"

    model_config = {"env_prefix": "", "case_sensitive": False}
