"""Configuration management for the scraper service.

All settings are loaded from environment variables via Pydantic Settings.
No secrets are hardcoded — Azure auth uses DefaultAzureCredential (managed identity).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class ScraperSettings(BaseSettings):
    """Scraper service configuration loaded from environment variables."""

    model_config = {"env_prefix": "SCRAPER_", "env_file": ".env", "extra": "ignore"}

    # --- Service identity ---
    service_name: str = Field(default="scraper", description="Service name for telemetry")
    service_version: str = Field(default="0.1.0")
    log_level: str = Field(default="INFO")

    # --- FastAPI ---
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # --- Azure Service Bus ---
    servicebus_namespace: str = Field(
        default="",
        description="Fully-qualified Service Bus namespace (e.g. myns.servicebus.windows.net)",
    )
    servicebus_queue_name: str = Field(
        default="scrape-requests",
        description="Queue to consume scrape requests from",
    )
    servicebus_topic_name: str = Field(
        default="scrape-complete",
        description="Topic to publish scrape-complete events to",
    )
    servicebus_max_concurrent: int = Field(
        default=5,
        description="Max messages processed concurrently",
    )
    servicebus_max_wait_time: int = Field(
        default=30,
        description="Max seconds to wait for messages before cycling",
    )

    # --- Azure Blob Storage ---
    blob_account_url: str = Field(
        default="",
        description="Blob account URL (e.g. https://myaccount.blob.core.windows.net)",
    )
    blob_container_name: str = Field(
        default="raw-content",
        description="Container for storing scraped content",
    )

    # --- Azure Cosmos DB ---
    cosmos_endpoint: str = Field(
        default="",
        description="Cosmos DB endpoint (e.g. https://myaccount.documents.azure.com:443/)",
    )
    cosmos_database_name: str = Field(
        default="selflearning",
        description="Cosmos DB database name",
    )
    cosmos_container_name: str = Field(
        default="crawl-history",
        description="Cosmos DB container for crawl history",
    )

    # --- Rate limiting ---
    rate_limit_requests_per_second: float = Field(
        default=2.0,
        description="Default max requests per second per domain",
    )
    rate_limit_burst: int = Field(
        default=5,
        description="Burst allowance for rate limiter",
    )

    # --- Scraping behaviour ---
    request_timeout: int = Field(default=30, description="HTTP request timeout in seconds")
    max_retries: int = Field(default=3, description="Max retries per URL")
    retry_base_delay: float = Field(default=1.0, description="Base delay for exponential backoff")
    max_content_size_mb: int = Field(default=10, description="Max downloaded content size in MB")
    user_agent: str = Field(
        default="SelfLearningBot/0.1 (+https://github.com/jmservera/selflearning)",
        description="User-Agent header for HTTP requests",
    )
    max_urls_per_request: int = Field(
        default=10,
        description="Max URLs to process per scrape request",
    )

    # --- Telemetry ---
    otel_service_name: str = Field(default="scraper-service")
    applicationinsights_connection_string: str = Field(
        default="",
        description="Application Insights connection string (optional for local dev)",
    )


def get_settings() -> ScraperSettings:
    """Create and return a validated settings instance."""
    return ScraperSettings()
