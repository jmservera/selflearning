"""Knowledge Service — FastAPI application.

Exposes the internal HTTP API for knowledge-graph CRUD, search, and analytics.
Other services (Reasoner, Evaluator, API Gateway) call these endpoints.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI, HTTPException, Query
from opentelemetry import trace

from .config import get_settings
from .cosmos_client import KnowledgeStore
from .models import (
    BulkIngestResponse,
    Claim,
    ClaimQuery,
    DocType,
    Entity,
    EntitySearchParams,
    EntityType,
    HybridSearchRequest,
    KnowledgeUnit,
    Relationship,
    RelationshipQuery,
    SearchResult,
    Source,
    TopicStats,
    TopicSummary,
)
from .search_client import KnowledgeSearchClient
from .service_bus import KnowledgeServiceBusConsumer

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

settings = get_settings()

# ── Telemetry ──────────────────────────────────────────────────────────────

if settings.app_insights_connection_string:
    configure_azure_monitor(
        connection_string=settings.app_insights_connection_string,
        service_name=settings.service_name,
    )

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s")

# ── Service singletons ────────────────────────────────────────────────────

store = KnowledgeStore(settings.cosmos)
search = KnowledgeSearchClient(settings.search)
consumer = KnowledgeServiceBusConsumer(settings.service_bus, store, search)


# ── App lifecycle ──────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    logger.info("Knowledge Service starting up …")
    await store.initialize()
    await search.initialize()
    try:
        await consumer.start()
    except Exception:
        logger.warning("Service Bus consumer failed to start (non-fatal in dev)", exc_info=True)
    yield
    logger.info("Knowledge Service shutting down …")
    await consumer.stop()
    await search.close()
    await store.close()


app = FastAPI(
    title="Knowledge Service",
    description="Internal API for the selflearning knowledge graph",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Health ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": settings.service_name}


# ── Entity endpoints ──────────────────────────────────────────────────────


@app.post("/entities", response_model=Entity, status_code=201)
async def upsert_entity(entity: Entity) -> Entity:
    """Upsert an entity into the knowledge graph (merge if duplicate found)."""
    with tracer.start_as_current_span("api.upsert_entity"):
        result = await store.upsert_entity(entity)
        # Fire-and-forget search indexing
        try:
            await search.ensure_index(entity.topic)
            await search.index_documents([entity.model_dump(mode="json")], topic=entity.topic)
        except Exception:
            logger.warning("Search indexing failed for entity %s", entity.id, exc_info=True)
        return result


@app.get("/entities/search", response_model=list[Entity])
async def search_entities(
    topic: str | None = None,
    entity_type: EntityType | None = None,
    q: str | None = None,
    min_confidence: float = 0.0,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
) -> list[Entity]:
    """Search entities by topic, type, or text query."""
    with tracer.start_as_current_span("api.search_entities"):
        return await store.search_entities(
            topic=topic,
            entity_type=entity_type.value if entity_type else None,
            query_text=q,
            min_confidence=min_confidence,
            limit=limit,
            offset=offset,
        )


@app.get("/entities/{entity_id}", response_model=Entity)
async def get_entity(entity_id: str, topic: str | None = None) -> Entity:
    """Retrieve an entity by ID."""
    with tracer.start_as_current_span("api.get_entity"):
        entity = await store.get_entity(entity_id, topic=topic)
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found")
        return entity


# ── Relationship endpoints ────────────────────────────────────────────────


@app.post("/relationships", response_model=Relationship, status_code=201)
async def upsert_relationship(rel: Relationship) -> Relationship:
    """Upsert a relationship between two entities."""
    with tracer.start_as_current_span("api.upsert_relationship"):
        return await store.upsert_relationship(rel)


@app.get("/relationships", response_model=list[Relationship])
async def query_relationships(
    entity_id: str | None = None,
    relationship_type: str | None = None,
    topic: str | None = None,
    limit: int = Query(default=50, le=200),
) -> list[Relationship]:
    """Query relationships by entity, type, or topic."""
    with tracer.start_as_current_span("api.query_relationships"):
        return await store.query_relationships(
            entity_id=entity_id,
            relationship_type=relationship_type,
            topic=topic,
            limit=limit,
        )


# ── Claim endpoints ───────────────────────────────────────────────────────


@app.post("/claims", response_model=Claim, status_code=201)
async def upsert_claim(claim: Claim) -> Claim:
    """Upsert a claim."""
    with tracer.start_as_current_span("api.upsert_claim"):
        result = await store.upsert_claim(claim)
        try:
            await search.ensure_index(claim.topic)
            await search.index_documents([claim.model_dump(mode="json")], topic=claim.topic)
        except Exception:
            logger.warning("Search indexing failed for claim %s", claim.id, exc_info=True)
        return result


@app.get("/claims", response_model=list[Claim])
async def query_claims(
    topic: str | None = None,
    entity_id: str | None = None,
    min_confidence: float = 0.0,
    verified_only: bool = False,
    limit: int = Query(default=50, le=200),
) -> list[Claim]:
    """Query claims by topic, entity, confidence, or verification status."""
    with tracer.start_as_current_span("api.query_claims"):
        return await store.query_claims(
            topic=topic,
            entity_id=entity_id,
            min_confidence=min_confidence,
            verified_only=verified_only,
            limit=limit,
        )


# ── Source endpoints ──────────────────────────────────────────────────────


@app.post("/sources", response_model=Source, status_code=201)
async def upsert_source(source: Source) -> Source:
    """Upsert a content source."""
    with tracer.start_as_current_span("api.upsert_source"):
        return await store.upsert_source(source)


# ── Search ────────────────────────────────────────────────────────────────


@app.get("/search", response_model=SearchResult)
async def hybrid_search(
    q: str,
    topic: str | None = None,
    doc_type: DocType | None = None,
    min_confidence: float = 0.0,
    limit: int = Query(default=20, le=100),
    mode: str = Query(default="hybrid", pattern="^(hybrid|vector|keyword)$"),
) -> SearchResult:
    """Hybrid vector + keyword search across knowledge graph."""
    with tracer.start_as_current_span("api.hybrid_search"):
        doc_types = [doc_type] if doc_type else None
        return await search.hybrid_search(
            query=q,
            topic=topic,
            doc_types=doc_types,
            min_confidence=min_confidence,
            limit=limit,
            search_mode=mode,
        )


# ── Bulk ingest ───────────────────────────────────────────────────────────


@app.post("/bulk", response_model=BulkIngestResponse, status_code=201)
async def bulk_ingest(unit: KnowledgeUnit) -> BulkIngestResponse:
    """Bulk ingest entities, relationships, claims, and sources."""
    with tracer.start_as_current_span("api.bulk_ingest"):
        result = await store.bulk_ingest(unit)

        # Index into search asynchronously
        topics: set[str] = set()
        docs: list[dict] = []
        for e in unit.entities:
            docs.append(e.model_dump(mode="json"))
            topics.add(e.topic)
        for c in unit.claims:
            docs.append(c.model_dump(mode="json"))
            topics.add(c.topic)

        for topic in topics:
            try:
                await search.ensure_index(topic)
                topic_docs = [d for d in docs if d.get("topic") == topic]
                if topic_docs:
                    await search.index_documents(topic_docs, topic=topic)
            except Exception:
                logger.warning("Search indexing failed for topic %s", topic, exc_info=True)

        return result


# ── Topic analytics ───────────────────────────────────────────────────────


@app.get("/topics/{topic}/stats", response_model=TopicStats)
async def topic_stats(topic: str) -> TopicStats:
    """Aggregate knowledge statistics for a topic."""
    with tracer.start_as_current_span("api.topic_stats"):
        return await store.get_topic_stats(topic)


@app.get("/topics/{topic}/summary", response_model=TopicSummary)
async def topic_summary(topic: str) -> TopicSummary:
    """High-level summary of knowledge for a topic."""
    with tracer.start_as_current_span("api.topic_summary"):
        raw = await store.get_topic_summary(topic)
        key_entities = [e["name"] for e in raw.get("top_entities", [])]
        key_claims = [c["statement"] for c in raw.get("top_claims", [])]
        confidences = [
            e.get("confidence", 0) for e in raw.get("top_entities", [])
        ] + [c.get("confidence", 0) for c in raw.get("top_claims", [])]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        summary_text = f"Topic '{topic}' contains {len(key_entities)} key entities and {len(key_claims)} key claims."
        if key_entities:
            summary_text += f" Key entities include: {', '.join(key_entities[:5])}."
        if key_claims:
            summary_text += f" Notable claims: {key_claims[0]}"

        return TopicSummary(
            topic=topic,
            summary=summary_text,
            key_entities=key_entities,
            key_claims=key_claims,
            confidence=round(avg_conf, 4),
        )
