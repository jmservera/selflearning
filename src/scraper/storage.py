"""Azure Storage integration — Blob Storage for raw content, Cosmos DB for crawl history.

All clients authenticate via DefaultAzureCredential (managed identity in prod,
az login / env vars locally).  Operations are async for pipeline throughput.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from azure.cosmos.aio import CosmosClient, ContainerProxy as CosmosContainerProxy
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient, ContainerClient
from opentelemetry import trace

from config import ScraperSettings
from models import CrawlHistoryEntry, CrawlStatus

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def content_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower()


# ---------------------------------------------------------------------------
# Blob Storage client
# ---------------------------------------------------------------------------

class BlobStorageClient:
    """Async wrapper around Azure Blob Storage for storing scraped content."""

    def __init__(self, settings: ScraperSettings, credential: DefaultAzureCredential) -> None:
        self._settings = settings
        self._credential = credential
        self._service_client: BlobServiceClient | None = None
        self._container_client: ContainerClient | None = None

    async def initialize(self) -> None:
        """Create the blob service client and ensure the container exists."""
        with tracer.start_as_current_span("blob_storage.initialize"):
            self._service_client = BlobServiceClient(
                account_url=self._settings.blob_account_url,
                credential=self._credential,
            )
            self._container_client = self._service_client.get_container_client(
                self._settings.blob_container_name,
            )
            try:
                await self._container_client.get_container_properties()
                logger.info("Blob container '%s' exists", self._settings.blob_container_name)
            except Exception:
                logger.info(
                    "Creating blob container '%s'", self._settings.blob_container_name,
                )
                await self._container_client.create_container()

    async def close(self) -> None:
        if self._service_client:
            await self._service_client.close()

    async def upload_content(
        self,
        blob_path: str,
        data: bytes,
        content_type: str = "text/html",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload raw content and return the blob path."""
        with tracer.start_as_current_span("blob_storage.upload_content") as span:
            span.set_attribute("blob.path", blob_path)
            span.set_attribute("blob.size_bytes", len(data))

            if self._container_client is None:
                raise RuntimeError("BlobStorageClient not initialised — call initialize() first")

            blob_client = self._container_client.get_blob_client(blob_path)
            await blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings={"content_type": content_type},
                metadata=metadata or {},
            )
            logger.info("Uploaded %d bytes to blob '%s'", len(data), blob_path)
            return blob_path

    async def blob_exists(self, blob_path: str) -> bool:
        """Check whether a blob already exists (for dedup fast-path)."""
        if self._container_client is None:
            return False
        blob_client = self._container_client.get_blob_client(blob_path)
        try:
            await blob_client.get_blob_properties()
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Cosmos DB client — crawl history
# ---------------------------------------------------------------------------

class CrawlHistoryClient:
    """Async Cosmos DB client for crawl history and URL deduplication."""

    def __init__(self, settings: ScraperSettings, credential: DefaultAzureCredential) -> None:
        self._settings = settings
        self._credential = credential
        self._cosmos_client: CosmosClient | None = None
        self._container: CosmosContainerProxy | None = None

    async def initialize(self) -> None:
        """Open the Cosmos client and get the crawl-history container handle."""
        with tracer.start_as_current_span("crawl_history.initialize"):
            self._cosmos_client = CosmosClient(
                url=self._settings.cosmos_endpoint,
                credential=self._credential,
            )
            database = self._cosmos_client.get_database_client(self._settings.cosmos_database_name)
            self._container = database.get_container_client(self._settings.cosmos_container_name)
            logger.info(
                "Cosmos DB crawl-history client ready (db=%s, container=%s)",
                self._settings.cosmos_database_name,
                self._settings.cosmos_container_name,
            )

    async def close(self) -> None:
        if self._cosmos_client:
            await self._cosmos_client.close()

    # -- Deduplication queries -------------------------------------------------

    async def url_already_crawled(self, url: str, max_age_hours: int = 24) -> bool:
        """Return True if *url* was successfully crawled within *max_age_hours*."""
        with tracer.start_as_current_span("crawl_history.url_already_crawled") as span:
            span.set_attribute("url", url)
            if self._container is None:
                return False

            domain = _domain_from_url(url)
            query = (
                "SELECT c.last_crawled FROM c "
                "WHERE c.url = @url AND c.status = @status"
            )
            params: list[dict[str, Any]] = [
                {"name": "@url", "value": url},
                {"name": "@status", "value": CrawlStatus.SUCCESS.value},
            ]
            items = self._container.query_items(
                query=query,
                parameters=params,
                partition_key=domain,
            )
            async for item in items:
                last_crawled = datetime.fromisoformat(item["last_crawled"])
                age_hours = (datetime.now(timezone.utc) - last_crawled).total_seconds() / 3600
                if age_hours < max_age_hours:
                    logger.debug("URL already crawled within %dh: %s", max_age_hours, url)
                    return True
            return False

    async def content_hash_exists(self, hash_value: str) -> bool:
        """Return True if content with the given hash has already been stored."""
        with tracer.start_as_current_span("crawl_history.content_hash_exists"):
            if self._container is None:
                return False
            query = (
                "SELECT VALUE COUNT(1) FROM c "
                "WHERE c.content_hash = @hash AND c.status = @status"
            )
            params: list[dict[str, Any]] = [
                {"name": "@hash", "value": hash_value},
                {"name": "@status", "value": CrawlStatus.SUCCESS.value},
            ]
            items = self._container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True,
            )
            async for count in items:
                if count > 0:
                    return True
            return False

    # -- Write operations ------------------------------------------------------

    async def upsert_entry(self, entry: CrawlHistoryEntry) -> None:
        """Insert or update a crawl history entry."""
        with tracer.start_as_current_span("crawl_history.upsert_entry") as span:
            span.set_attribute("url", entry.url)
            span.set_attribute("status", entry.status.value)
            if self._container is None:
                raise RuntimeError("CrawlHistoryClient not initialised")

            doc = entry.model_dump(mode="json")
            doc["partitionKey"] = entry.partition_key
            await self._container.upsert_item(doc)
            logger.debug("Upserted crawl history for %s (status=%s)", entry.url, entry.status.value)

    async def record_crawl(
        self,
        url: str,
        *,
        status: CrawlStatus,
        content_hash_value: str = "",
        blob_path: str = "",
        topic: str = "",
    ) -> None:
        """Convenience method to record a crawl attempt."""
        entry = CrawlHistoryEntry(
            url=url,
            domain=_domain_from_url(url),
            content_hash=content_hash_value,
            last_crawled=datetime.now(timezone.utc),
            status=status,
            blob_path=blob_path,
            topic=topic,
        )
        await self.upsert_entry(entry)

    # -- Stats -----------------------------------------------------------------

    async def get_crawl_stats(self) -> dict[str, int]:
        """Return aggregate crawl counts by status."""
        if self._container is None:
            return {}
        query = "SELECT c.status, COUNT(1) AS cnt FROM c GROUP BY c.status"
        stats: dict[str, int] = {}
        items = self._container.query_items(
            query=query,
            enable_cross_partition_query=True,
        )
        async for item in items:
            stats[item["status"]] = item["cnt"]
        return stats
