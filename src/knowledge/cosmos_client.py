"""Async Cosmos DB client for knowledge-graph CRUD.

All documents live in a single Cosmos container partitioned by `topic`.
The `type` discriminator field determines the document kind.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from azure.cosmos.aio import ContainerProxy, CosmosClient, DatabaseProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from opentelemetry import trace

from .config import CosmosConfig
from .models import (
    BulkIngestResponse,
    Claim,
    DocType,
    Entity,
    KnowledgeUnit,
    Relationship,
    Source,
    TopicStats,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_MODEL_MAP: dict[DocType, type] = {
    DocType.ENTITY: Entity,
    DocType.RELATIONSHIP: Relationship,
    DocType.CLAIM: Claim,
    DocType.SOURCE: Source,
}


class KnowledgeStore:
    """Async wrapper around Cosmos DB for knowledge-graph operations."""

    def __init__(self, config: CosmosConfig) -> None:
        self._config = config
        self._credential: DefaultAzureCredential | None = None
        self._client: CosmosClient | None = None
        self._database: DatabaseProxy | None = None
        self._container: ContainerProxy | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Create the async Cosmos client and obtain container handle."""
        with tracer.start_as_current_span("cosmos.initialize"):
            self._credential = DefaultAzureCredential()
            self._client = CosmosClient(
                url=self._config.endpoint,
                credential=self._credential,
            )
            self._database = self._client.get_database_client(
                self._config.database_name
            )
            self._container = self._database.get_container_client(
                self._config.container_name
            )
            logger.info(
                "Cosmos DB connected: %s/%s",
                self._config.database_name,
                self._config.container_name,
            )

    async def close(self) -> None:
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()

    @property
    def container(self) -> ContainerProxy:
        assert self._container is not None, "Call initialize() first"
        return self._container

    # ── Generic helpers ────────────────────────────────────────────────

    async def _read_item(self, item_id: str, partition_key: str) -> dict[str, Any] | None:
        try:
            return await self.container.read_item(item=item_id, partition_key=partition_key)
        except CosmosResourceNotFoundError:
            return None

    async def _upsert(self, doc: dict[str, Any]) -> dict[str, Any]:
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.container.upsert_item(body=doc)

    async def _query(
        self,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
        max_items: int = 50,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {"max_item_count": max_items}
        if partition_key is not None:
            kwargs["partition_key"] = partition_key
        else:
            kwargs["enable_cross_partition_query"] = True
        items: list[dict[str, Any]] = []
        async for page in self.container.query_items(
            query=query,
            parameters=parameters or [],
            **kwargs,
        ):
            items.append(page)
            if len(items) >= max_items:
                break
        return items

    # ── Entity CRUD ────────────────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.upsert_entity")
    async def upsert_entity(self, entity: Entity) -> Entity:
        """Upsert an entity; if a similar entity exists, merge fields."""
        existing = await self._find_similar_entity(entity)
        if existing is not None:
            merged = self._merge_entity(existing, entity)
            doc = await self._upsert(merged.model_dump(mode="json"))
            logger.info("Merged entity %s into %s", entity.name, existing.id)
        else:
            doc = await self._upsert(entity.model_dump(mode="json"))
            logger.info("Created entity %s (%s)", entity.name, entity.id)
        return Entity.model_validate(doc)

    @tracer.start_as_current_span("cosmos.get_entity")
    async def get_entity(self, entity_id: str, topic: str | None = None) -> Entity | None:
        if topic:
            raw = await self._read_item(entity_id, topic)
        else:
            results = await self._query(
                "SELECT * FROM c WHERE c.id = @id AND c.type = 'Entity'",
                [{"name": "@id", "value": entity_id}],
                max_items=1,
            )
            raw = results[0] if results else None
        if raw is None:
            return None
        return Entity.model_validate(raw)

    @tracer.start_as_current_span("cosmos.search_entities")
    async def search_entities(
        self,
        *,
        topic: str | None = None,
        entity_type: str | None = None,
        query_text: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Entity]:
        clauses = ["c.type = 'Entity'", "c.confidence >= @minConf"]
        params: list[dict[str, Any]] = [{"name": "@minConf", "value": min_confidence}]

        if entity_type:
            clauses.append("c.entity_type = @et")
            params.append({"name": "@et", "value": entity_type})
        if query_text:
            clauses.append("CONTAINS(LOWER(c.name), LOWER(@qt)) OR CONTAINS(LOWER(c.description), LOWER(@qt))")
            params.append({"name": "@qt", "value": query_text})

        sql = f"SELECT * FROM c WHERE {' AND '.join(clauses)} ORDER BY c.confidence DESC OFFSET @off LIMIT @lim"
        params += [
            {"name": "@off", "value": offset},
            {"name": "@lim", "value": limit},
        ]
        rows = await self._query(sql, params, partition_key=topic, max_items=limit)
        return [Entity.model_validate(r) for r in rows]

    # ── Relationship CRUD ──────────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.upsert_relationship")
    async def upsert_relationship(self, rel: Relationship) -> Relationship:
        doc = await self._upsert(rel.model_dump(mode="json"))
        logger.info("Upserted relationship %s", rel.id)
        return Relationship.model_validate(doc)

    @tracer.start_as_current_span("cosmos.query_relationships")
    async def query_relationships(
        self,
        *,
        entity_id: str | None = None,
        relationship_type: str | None = None,
        topic: str | None = None,
        limit: int = 50,
    ) -> list[Relationship]:
        clauses = ["c.type = 'Relationship'"]
        params: list[dict[str, Any]] = []
        if entity_id:
            clauses.append("(c.source_entity_id = @eid OR c.target_entity_id = @eid)")
            params.append({"name": "@eid", "value": entity_id})
        if relationship_type:
            clauses.append("c.relationship_type = @rt")
            params.append({"name": "@rt", "value": relationship_type})
        sql = f"SELECT * FROM c WHERE {' AND '.join(clauses)} OFFSET 0 LIMIT @lim"
        params.append({"name": "@lim", "value": limit})
        rows = await self._query(sql, params, partition_key=topic, max_items=limit)
        return [Relationship.model_validate(r) for r in rows]

    # ── Claim CRUD ─────────────────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.upsert_claim")
    async def upsert_claim(self, claim: Claim) -> Claim:
        doc = await self._upsert(claim.model_dump(mode="json"))
        logger.info("Upserted claim %s", claim.id)
        return Claim.model_validate(doc)

    @tracer.start_as_current_span("cosmos.query_claims")
    async def query_claims(
        self,
        *,
        topic: str | None = None,
        entity_id: str | None = None,
        min_confidence: float = 0.0,
        verified_only: bool = False,
        limit: int = 50,
    ) -> list[Claim]:
        clauses = ["c.type = 'Claim'", "c.confidence >= @mc"]
        params: list[dict[str, Any]] = [{"name": "@mc", "value": min_confidence}]
        if entity_id:
            clauses.append("ARRAY_CONTAINS(c.entities, @eid)")
            params.append({"name": "@eid", "value": entity_id})
        if verified_only:
            clauses.append("c.verified = true")
        sql = f"SELECT * FROM c WHERE {' AND '.join(clauses)} ORDER BY c.confidence DESC OFFSET 0 LIMIT @lim"
        params.append({"name": "@lim", "value": limit})
        rows = await self._query(sql, params, partition_key=topic, max_items=limit)
        return [Claim.model_validate(r) for r in rows]

    # ── Source CRUD ────────────────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.upsert_source")
    async def upsert_source(self, source: Source) -> Source:
        doc = await self._upsert(source.model_dump(mode="json"))
        logger.info("Upserted source %s", source.id)
        return Source.model_validate(doc)

    @tracer.start_as_current_span("cosmos.get_source")
    async def get_source(self, source_id: str, topic: str | None = None) -> Source | None:
        if topic:
            raw = await self._read_item(source_id, topic)
        else:
            results = await self._query(
                "SELECT * FROM c WHERE c.id = @id AND c.type = 'Source'",
                [{"name": "@id", "value": source_id}],
                max_items=1,
            )
            raw = results[0] if results else None
        return Source.model_validate(raw) if raw else None

    # ── Bulk operations ────────────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.bulk_ingest")
    async def bulk_ingest(self, unit: KnowledgeUnit) -> BulkIngestResponse:
        """Ingest a full knowledge unit from the extraction pipeline."""
        resp = BulkIngestResponse()
        errors: list[str] = []

        for source in unit.sources:
            try:
                await self.upsert_source(source)
                resp.sources_upserted += 1
            except Exception as exc:
                errors.append(f"source {source.id}: {exc}")

        for entity in unit.entities:
            try:
                existing = await self._find_similar_entity(entity)
                if existing:
                    resp.entities_merged += 1
                await self.upsert_entity(entity)
                resp.entities_upserted += 1
            except Exception as exc:
                errors.append(f"entity {entity.id}: {exc}")

        for rel in unit.relationships:
            try:
                await self.upsert_relationship(rel)
                resp.relationships_upserted += 1
            except Exception as exc:
                errors.append(f"relationship {rel.id}: {exc}")

        for claim in unit.claims:
            try:
                await self.upsert_claim(claim)
                resp.claims_upserted += 1
            except Exception as exc:
                errors.append(f"claim {claim.id}: {exc}")

        resp.errors = errors
        logger.info(
            "Bulk ingest complete: %d entities (%d merged), %d rels, %d claims, %d sources, %d errors",
            resp.entities_upserted,
            resp.entities_merged,
            resp.relationships_upserted,
            resp.claims_upserted,
            resp.sources_upserted,
            len(errors),
        )
        return resp

    # ── Topic analytics ────────────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.topic_stats")
    async def get_topic_stats(self, topic: str) -> TopicStats:
        """Compute aggregate stats for a topic partition."""
        count_sql = (
            "SELECT c.type, COUNT(1) AS cnt "
            "FROM c WHERE c.topic = @t GROUP BY c.type"
        )
        rows = await self._query(count_sql, [{"name": "@t", "value": topic}], partition_key=topic, max_items=10)
        counts = {r["type"]: r["cnt"] for r in rows}

        avg_sql = "SELECT VALUE AVG(c.confidence) FROM c WHERE c.topic = @t AND IS_NUMBER(c.confidence)"
        avg_rows = await self._query(avg_sql, [{"name": "@t", "value": topic}], partition_key=topic, max_items=1)
        avg_confidence = avg_rows[0] if avg_rows and avg_rows[0] is not None else 0.0

        types_sql = (
            "SELECT DISTINCT c.entity_type FROM c "
            "WHERE c.topic = @t AND c.type = 'Entity'"
        )
        type_rows = await self._query(types_sql, [{"name": "@t", "value": topic}], partition_key=topic, max_items=50)
        coverage = [r["entity_type"] for r in type_rows if "entity_type" in r]

        last_sql = "SELECT TOP 1 c.updated_at FROM c WHERE c.topic = @t ORDER BY c.updated_at DESC"
        last_rows = await self._query(last_sql, [{"name": "@t", "value": topic}], partition_key=topic, max_items=1)
        last_updated = last_rows[0]["updated_at"] if last_rows else None

        return TopicStats(
            topic=topic,
            entity_count=counts.get("Entity", 0),
            relationship_count=counts.get("Relationship", 0),
            claim_count=counts.get("Claim", 0),
            source_count=counts.get("Source", 0),
            avg_confidence=round(float(avg_confidence), 4),
            coverage_areas=coverage,
            last_updated=last_updated,
        )

    @tracer.start_as_current_span("cosmos.topic_summary")
    async def get_topic_summary(self, topic: str) -> dict[str, Any]:
        """Return raw material for the summary endpoint (entities + claims)."""
        top_entities_sql = (
            "SELECT c.name, c.entity_type, c.confidence FROM c "
            "WHERE c.topic = @t AND c.type = 'Entity' "
            "ORDER BY c.confidence DESC OFFSET 0 LIMIT 10"
        )
        entities = await self._query(
            top_entities_sql, [{"name": "@t", "value": topic}], partition_key=topic, max_items=10
        )
        top_claims_sql = (
            "SELECT c.statement, c.confidence FROM c "
            "WHERE c.topic = @t AND c.type = 'Claim' "
            "ORDER BY c.confidence DESC OFFSET 0 LIMIT 10"
        )
        claims = await self._query(
            top_claims_sql, [{"name": "@t", "value": topic}], partition_key=topic, max_items=10
        )
        return {"topic": topic, "top_entities": entities, "top_claims": claims}

    # ── Entity resolution helpers ──────────────────────────────────────

    async def _find_similar_entity(self, entity: Entity) -> Entity | None:
        """Find an existing entity that is likely a duplicate.

        Uses name similarity and alias overlap within the same topic.
        """
        candidates = await self._query(
            "SELECT * FROM c WHERE c.topic = @t AND c.type = 'Entity'",
            [{"name": "@t", "value": entity.topic}],
            partition_key=entity.topic,
            max_items=200,
        )
        best_match: dict[str, Any] | None = None
        best_score = 0.0
        entity_name_lower = entity.name.lower()
        entity_aliases_lower = {a.lower() for a in entity.aliases}

        for cand in candidates:
            if cand["id"] == entity.id:
                continue
            cand_name_lower = cand.get("name", "").lower()
            # Exact name match
            if cand_name_lower == entity_name_lower:
                return Entity.model_validate(cand)
            # Alias match
            cand_aliases = {a.lower() for a in cand.get("aliases", [])}
            if entity_name_lower in cand_aliases or cand_name_lower in entity_aliases_lower:
                return Entity.model_validate(cand)
            if entity_aliases_lower & cand_aliases:
                return Entity.model_validate(cand)
            # Fuzzy name similarity
            score = SequenceMatcher(None, entity_name_lower, cand_name_lower).ratio()
            if score > 0.85 and score > best_score:
                best_score = score
                best_match = cand

        if best_match is not None:
            return Entity.model_validate(best_match)
        return None

    @staticmethod
    def _merge_entity(existing: Entity, incoming: Entity) -> Entity:
        """Merge incoming entity data into the existing entity."""
        merged_aliases = list(set(existing.aliases) | set(incoming.aliases) | {incoming.name})
        if existing.name in merged_aliases:
            merged_aliases.remove(existing.name)

        merged_sources = list(set(existing.source_urls) | set(incoming.source_urls))
        description = incoming.description if len(incoming.description) > len(existing.description) else existing.description
        confidence = max(existing.confidence, incoming.confidence)
        embedding = incoming.embedding if incoming.embedding else existing.embedding

        return existing.model_copy(
            update={
                "aliases": merged_aliases,
                "source_urls": merged_sources,
                "source_count": len(merged_sources),
                "description": description,
                "confidence": confidence,
                "embedding": embedding,
                "updated_at": datetime.now(timezone.utc),
            }
        )
