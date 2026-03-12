"""Azure AI Search integration for hybrid vector + keyword search.

Indexes entities and claims from the knowledge graph and serves
hybrid queries used by the Reasoner, API Gateway, and chat RAG pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import (
    VectorizableTextQuery,
    QueryType,
)
from opentelemetry import trace

from .config import SearchConfig
from .models import DocType, SearchResult, SearchResultItem

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _index_name(prefix: str, topic: str | None = None) -> str:
    """Build deterministic index name (one per topic or a global index)."""
    safe = (topic or "global").replace(" ", "-").lower()
    return f"{prefix}-{safe}"


class KnowledgeSearchClient:
    """Async wrapper for Azure AI Search operations."""

    def __init__(self, config: SearchConfig) -> None:
        self._config = config
        self._credential: DefaultAzureCredential | None = None
        self._index_client: SearchIndexClient | None = None
        self._search_clients: dict[str, SearchClient] = {}

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def initialize(self) -> None:
        self._credential = DefaultAzureCredential()
        self._index_client = SearchIndexClient(
            endpoint=self._config.endpoint,
            credential=self._credential,
        )
        logger.info("AI Search index client initialized: %s", self._config.endpoint)

    async def close(self) -> None:
        for sc in self._search_clients.values():
            await sc.close()
        if self._index_client:
            await self._index_client.close()
        if self._credential:
            await self._credential.close()

    def _get_search_client(self, index: str) -> SearchClient:
        if index not in self._search_clients:
            assert self._credential is not None
            self._search_clients[index] = SearchClient(
                endpoint=self._config.endpoint,
                index_name=index,
                credential=self._credential,
            )
        return self._search_clients[index]

    # ── Index management ───────────────────────────────────────────────

    @tracer.start_as_current_span("search.ensure_index")
    async def ensure_index(self, topic: str | None = None) -> str:
        """Create or update the search index for a topic."""
        name = _index_name(self._config.index_prefix, topic)
        assert self._index_client is not None

        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
            SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SearchableField(name="name", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
            SearchableField(name="description", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
            SearchableField(name="statement", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
            SimpleField(name="topic", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SimpleField(name="entity_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SimpleField(name="confidence", type=SearchFieldDataType.Double, filterable=True, sortable=True),
            SearchField(
                name="embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self._config.embedding_dimensions,
                vector_search_profile_name="default-vector-profile",
            ),
        ]

        vector_search = VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(
                    name="default-hnsw",
                    parameters={"m": 4, "efConstruction": 400, "efSearch": 500, "metric": self._config.similarity_metric},
                )
            ],
            profiles=[
                VectorSearchProfile(name="default-vector-profile", algorithm_configuration_name="default-hnsw"),
            ],
        )

        index = SearchIndex(name=name, fields=fields, vector_search=vector_search)
        await self._index_client.create_or_update_index(index)
        logger.info("Search index ensured: %s", name)
        return name

    # ── Document indexing ──────────────────────────────────────────────

    @tracer.start_as_current_span("search.index_documents")
    async def index_documents(self, documents: list[dict[str, Any]], topic: str | None = None) -> int:
        """Push documents to the search index. Returns count indexed."""
        idx = _index_name(self._config.index_prefix, topic)
        client = self._get_search_client(idx)

        batch: list[dict[str, Any]] = []
        for doc in documents:
            search_doc: dict[str, Any] = {
                "id": doc["id"],
                "doc_type": doc.get("type", ""),
                "name": doc.get("name", ""),
                "description": doc.get("description", ""),
                "statement": doc.get("statement", ""),
                "topic": doc.get("topic", ""),
                "entity_type": doc.get("entity_type", ""),
                "confidence": doc.get("confidence", 0.0),
            }
            if doc.get("embedding"):
                search_doc["embedding"] = doc["embedding"]
            batch.append(search_doc)

        if not batch:
            return 0

        result = await client.upload_documents(documents=batch)
        succeeded = sum(1 for r in result if r.succeeded)
        failed = len(result) - succeeded
        if failed:
            logger.warning("Search indexing: %d succeeded, %d failed", succeeded, failed)
        else:
            logger.info("Search indexing: %d documents indexed", succeeded)
        return succeeded

    # ── Hybrid search ──────────────────────────────────────────────────

    @tracer.start_as_current_span("search.hybrid_search")
    async def hybrid_search(
        self,
        query: str,
        *,
        topic: str | None = None,
        doc_types: list[DocType] | None = None,
        min_confidence: float = 0.0,
        limit: int = 20,
        search_mode: str = "hybrid",
        embedding: list[float] | None = None,
    ) -> SearchResult:
        """Execute hybrid, vector-only, or keyword-only search."""
        idx = _index_name(self._config.index_prefix, topic)
        client = self._get_search_client(idx)

        # Build filters
        filters: list[str] = []
        if doc_types:
            type_list = ",".join(f"'{dt.value}'" for dt in doc_types)
            filters.append(f"search.in(doc_type, '{type_list}', ',')")
        if min_confidence > 0:
            filters.append(f"confidence ge {min_confidence}")
        filter_str = " and ".join(filters) if filters else None

        search_kwargs: dict[str, Any] = {
            "top": limit,
            "include_total_count": True,
            "facets": ["doc_type", "entity_type", "topic"],
        }
        if filter_str:
            search_kwargs["filter"] = filter_str

        if search_mode == "vector" and embedding:
            search_kwargs["vector_queries"] = [
                VectorizableTextQuery(text=query, k_nearest_neighbors=limit, fields="embedding")
            ]
            search_kwargs["search_text"] = None
        elif search_mode == "keyword":
            search_kwargs["search_text"] = query
            search_kwargs["query_type"] = QueryType.SIMPLE
        else:
            # hybrid: both keyword and vector
            search_kwargs["search_text"] = query
            search_kwargs["query_type"] = QueryType.SIMPLE
            if embedding:
                search_kwargs["vector_queries"] = [
                    VectorizableTextQuery(text=query, k_nearest_neighbors=limit, fields="embedding")
                ]

        results = await client.search(**search_kwargs)

        items: list[SearchResultItem] = []
        async for result in results:
            highlights = {}
            if hasattr(result, "@search.highlights") and result.get("@search.highlights"):
                highlights = result["@search.highlights"]
            items.append(
                SearchResultItem(
                    id=result["id"],
                    doc_type=result.get("doc_type", "Entity"),
                    name=result.get("name", ""),
                    statement=result.get("statement", ""),
                    topic=result.get("topic", ""),
                    confidence=result.get("confidence", 0.0),
                    score=result.get("@search.score", 0.0),
                    highlights=highlights,
                )
            )
            if len(items) >= limit:
                break

        facets: dict[str, list[dict[str, Any]]] = {}
        if results.get_facets():
            for facet_name, facet_values in results.get_facets().items():
                facets[facet_name] = [{"value": f.value, "count": f.count} for f in facet_values]

        return SearchResult(
            items=items,
            total_count=results.get_count() or len(items),
            facets=facets,
        )

    # ── Convenience wrappers ───────────────────────────────────────────

    async def vector_search(
        self, query: str, *, topic: str | None = None, limit: int = 20, embedding: list[float] | None = None,
    ) -> SearchResult:
        return await self.hybrid_search(query, topic=topic, limit=limit, search_mode="vector", embedding=embedding)

    async def keyword_search(
        self, query: str, *, topic: str | None = None, limit: int = 20,
    ) -> SearchResult:
        return await self.hybrid_search(query, topic=topic, limit=limit, search_mode="keyword")
