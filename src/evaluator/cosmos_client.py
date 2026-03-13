"""Async Cosmos DB client for evaluation persistence.

All documents live in a single Cosmos container (``evaluations``) partitioned
by ``topic``.  A ``type`` discriminator field distinguishes scorecards, gaps,
and full reports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from azure.cosmos.aio import ContainerProxy, CosmosClient, DatabaseProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from opentelemetry import trace

from .config import Settings
from .models import EvaluationReport, ExpertiseScorecard, KnowledgeGap

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_DOC_SCORECARD = "scorecard"
_DOC_GAP = "gap"
_DOC_REPORT = "report"


class EvaluationCosmosClient:
    """Async Cosmos DB client for the Evaluator service.

    Stores scorecards, knowledge gaps, and evaluation reports in a single
    ``evaluations`` container partitioned by ``/topic``.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._credential: DefaultAzureCredential | None = None
        self._client: CosmosClient | None = None
        self._database: DatabaseProxy | None = None
        self._container: ContainerProxy | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Create the async Cosmos client and obtain the container handle."""
        with tracer.start_as_current_span("cosmos.evaluator.initialize"):
            self._credential = DefaultAzureCredential()
            self._client = CosmosClient(
                url=self._settings.cosmos_endpoint,
                credential=self._credential,
            )
            self._database = self._client.get_database_client(
                self._settings.cosmos_database
            )
            self._container = self._database.get_container_client(
                self._settings.cosmos_container
            )
            logger.info(
                "Evaluator Cosmos DB connected: %s/%s",
                self._settings.cosmos_database,
                self._settings.cosmos_container,
            )

    async def close(self) -> None:
        """Release Cosmos and credential resources."""
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()

    @property
    def container(self) -> ContainerProxy:
        assert self._container is not None, (
            "Container not initialized. Ensure initialize() was called and completed successfully."
        )
        return self._container

    async def ping(self) -> bool:
        """Return True if the container is reachable."""
        try:
            await self.container.read()
            return True
        except Exception:  # noqa: BLE001
            return False

    # ── Generic helpers ────────────────────────────────────────────────

    async def _upsert(self, doc: dict[str, Any]) -> dict[str, Any]:
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.container.upsert_item(body=doc)

    async def _query(
        self,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {}
        if partition_key is not None:
            kwargs["partition_key"] = partition_key
        else:
            kwargs["enable_cross_partition_query"] = True
        results: list[dict[str, Any]] = []
        async for item in self.container.query_items(
            query=query,
            parameters=parameters or [],
            **kwargs,
        ):
            results.append(item)
        return results

    # ── Scorecard operations ───────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.evaluator.upsert_scorecard")
    async def upsert_scorecard(
        self, topic: str, scorecard: ExpertiseScorecard
    ) -> None:
        """Persist a scorecard document."""
        doc = scorecard.model_dump(mode="json")
        doc["id"] = str(uuid4())
        doc["type"] = _DOC_SCORECARD
        doc["topic"] = topic
        await self._upsert(doc)
        logger.debug("Upserted scorecard for topic=%s score=%.1f", topic, scorecard.overall_score)

    @tracer.start_as_current_span("cosmos.evaluator.get_latest_scorecard")
    async def get_latest_scorecard(self, topic: str) -> ExpertiseScorecard | None:
        """Return the most recent scorecard for *topic*, or ``None``."""
        items = await self._query(
            "SELECT * FROM c WHERE c.topic = @topic AND c.type = @type"
            " ORDER BY c._ts DESC OFFSET 0 LIMIT 1",
            parameters=[
                {"name": "@topic", "value": topic},
                {"name": "@type", "value": _DOC_SCORECARD},
            ],
            partition_key=topic,
        )
        if not items:
            return None
        return ExpertiseScorecard.model_validate(items[0])

    @tracer.start_as_current_span("cosmos.evaluator.get_scorecard_history")
    async def get_scorecard_history(
        self, topic: str, limit: int = 50
    ) -> list[ExpertiseScorecard]:
        """Return up to *limit* scorecards for *topic*, newest first."""
        items = await self._query(
            "SELECT * FROM c WHERE c.topic = @topic AND c.type = @type"
            " ORDER BY c._ts DESC OFFSET 0 LIMIT @limit",
            parameters=[
                {"name": "@topic", "value": topic},
                {"name": "@type", "value": _DOC_SCORECARD},
                {"name": "@limit", "value": limit},
            ],
            partition_key=topic,
        )
        return [ExpertiseScorecard.model_validate(item) for item in items]

    # ── Gap operations ─────────────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.evaluator.upsert_gaps")
    async def upsert_gaps(self, topic: str, gaps: list[KnowledgeGap]) -> None:
        """Replace all gap documents for *topic* with *gaps*.

        A single sentinel document (with ``doc_subtype = 'gap_list'``) stores
        the full list so retrieval is a single read instead of N reads.
        """
        doc: dict[str, Any] = {
            "id": f"gaps-{topic}",
            "type": _DOC_GAP,
            "topic": topic,
            "gaps": [g.model_dump(mode="json") for g in gaps],
        }
        await self._upsert(doc)
        logger.debug("Upserted %d gaps for topic=%s", len(gaps), topic)

    @tracer.start_as_current_span("cosmos.evaluator.get_gaps")
    async def get_gaps(self, topic: str) -> list[KnowledgeGap]:
        """Return current knowledge gaps for *topic*."""
        try:
            item = await self.container.read_item(
                item=f"gaps-{topic}", partition_key=topic
            )
            return [KnowledgeGap.model_validate(g) for g in item.get("gaps", [])]
        except CosmosResourceNotFoundError:
            return []

    # ── Report operations ──────────────────────────────────────────────

    @tracer.start_as_current_span("cosmos.evaluator.upsert_report")
    async def upsert_report(self, topic: str, report: EvaluationReport) -> None:
        """Persist the latest evaluation report for *topic*."""
        doc = report.model_dump(mode="json")
        doc["id"] = f"report-{topic}"
        doc["type"] = _DOC_REPORT
        doc["topic"] = topic
        await self._upsert(doc)
        logger.debug("Upserted report for topic=%s", topic)

    @tracer.start_as_current_span("cosmos.evaluator.get_report")
    async def get_report(self, topic: str) -> EvaluationReport | None:
        """Return the latest evaluation report for *topic*, or ``None``."""
        try:
            item = await self.container.read_item(
                item=f"report-{topic}", partition_key=topic
            )
            return EvaluationReport.model_validate(item)
        except CosmosResourceNotFoundError:
            return None
