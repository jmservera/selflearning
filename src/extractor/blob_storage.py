"""Azure Blob Storage client for reading raw scraped content.

Uses DefaultAzureCredential (managed identity) — no connection strings needed.
"""

from __future__ import annotations

import logging

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient
from opentelemetry import trace

from config import ExtractorConfig

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("extractor.blob")


class BlobStorageClient:
    """Reads raw scraped content from Azure Blob Storage."""

    def __init__(self, config: ExtractorConfig) -> None:
        self._config = config
        self._credential: DefaultAzureCredential | None = None
        self._client: BlobServiceClient | None = None

    async def initialize(self) -> None:
        """Create the blob service client with managed-identity auth."""
        self._credential = DefaultAzureCredential()
        self._client = BlobServiceClient(
            account_url=self._config.storage_account_url,
            credential=self._credential,
        )
        logger.info("Blob storage client initialized (%s)", self._config.storage_account_url)

    async def close(self) -> None:
        """Release blob client and credential."""
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()

    async def read_content(
        self,
        blob_path: str,
        container: str | None = None,
    ) -> str:
        """Download and decode text content from a blob.

        Args:
            blob_path: Path within the container (e.g. "topic/abc123.html").
            container: Override the default container name.

        Returns:
            The decoded text content of the blob.
        """
        container = container or self._config.raw_content_container

        with tracer.start_as_current_span("blob.read_content") as span:
            span.set_attribute("blob.container", container)
            span.set_attribute("blob.path", blob_path)

            assert self._client is not None, "BlobStorageClient not initialized"
            container_client = self._client.get_container_client(container)
            blob_client = container_client.get_blob_client(blob_path)

            downloader = await blob_client.download_blob()
            data = await downloader.readall()
            text = data.decode("utf-8", errors="replace")

            span.set_attribute("blob.size_bytes", len(data))
            logger.debug("Read blob %s/%s (%d bytes)", container, blob_path, len(data))
            return text
