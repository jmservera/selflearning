"""Learning strategy management.

Drives *what* the orchestrator learns next based on evaluation gaps,
source diversity, confidence scores, and depth/breadth balance.
Strategies are persisted in Cosmos DB so the agent resumes intelligently.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace

from config import OrchestratorSettings
from cosmos_client import CosmosDBClient
from models import (
    EvaluationResult,
    LearningPlan,
    LearningStrategy,
    LearningTopic,
    PipelineStage,
    ReasoningType,
    ScrapeRequest,
    SourceType,
)
from working_memory import WorkingMemory

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# ── Query templates for gap-driven learning ──────────────────────────

_GAP_QUERY_TEMPLATES = [
    "{topic} {area} overview",
    "{topic} {area} latest research",
    "{topic} {area} key concepts",
    "{topic} {area} expert analysis",
    "{area} in the context of {topic}",
    "what is {area} in {topic}",
    "{topic} {area} academic papers",
    "{area} applications in {topic}",
]

_DEPTH_QUERY_TEMPLATES = [
    "{topic} {area} detailed analysis",
    "{topic} {area} advanced techniques",
    "{topic} {area} state of the art",
    "{topic} {area} open problems",
    "{topic} {area} recent breakthroughs",
    "deep dive into {area} within {topic}",
]

_DIVERSIFY_QUERY_TEMPLATES = [
    "{topic} site:arxiv.org",
    "{topic} site:scholar.google.com",
    "{topic} conference proceedings",
    "{topic} textbook",
    "{topic} tutorial",
    "{topic} review paper",
]


class StrategyManager:
    """Manages learning strategies for topics.

    Responsibilities:
      - Analyse evaluation results to determine next learning actions
      - Generate scrape queries based on gaps and strategy mode
      - Decide when to shift between breadth/depth/verification/diversify modes
      - Track staleness and trigger backoff
      - Persist strategies to Cosmos DB
    """

    def __init__(
        self,
        settings: OrchestratorSettings,
        cosmos: CosmosDBClient,
        memory: WorkingMemory,
    ) -> None:
        self._settings = settings
        self._cosmos = cosmos
        self._memory = memory

    # ── Strategy lifecycle ────────────────────────────────────────────

    @tracer.start_as_current_span("strategy.get_or_create")
    def get_or_create(self, topic: LearningTopic) -> LearningStrategy:
        """Load or initialise a strategy for a topic."""
        strategy = self._cosmos.get_strategy(topic.name)
        if strategy is None:
            strategy = LearningStrategy(
                topic=topic.name,
                mode="breadth",
                source_diversity_target=self._settings.min_sources_per_query,
                confidence_threshold=0.7,
            )
            self._cosmos.upsert_strategy(strategy)
            logger.info("Created new strategy for topic=%s mode=breadth", topic.name)
        return strategy

    @tracer.start_as_current_span("strategy.update_after_evaluation")
    def update_after_evaluation(
        self,
        strategy: LearningStrategy,
        evaluation: EvaluationResult,
        topic: LearningTopic,
    ) -> LearningStrategy:
        """Update strategy based on evaluation results.

        Decision logic:
          1. Record the score and check for staleness
          2. If gaps identified → focus on gap areas (breadth or depth)
          3. If coverage > threshold but depth is low → switch to depth mode
          4. If too few sources → switch to diversify mode
          5. If confidence on claims is low → switch to verification mode
          6. If no progress for N iterations → increase backoff
        """
        # Track score history
        strategy.iteration_scores.append(evaluation.overall_score)
        strategy.recent_gaps = evaluation.gaps[:10]
        strategy.focus_areas = evaluation.weak_areas[:5]

        # Check staleness — no improvement over N iterations
        if len(strategy.iteration_scores) >= 2:
            recent_scores = strategy.iteration_scores[-self._settings.max_stale_iterations :]
            if len(recent_scores) >= self._settings.max_stale_iterations:
                improvement = recent_scores[-1] - recent_scores[0]
                if improvement <= 0.01:
                    strategy.stale_count += 1
                    strategy.backoff_seconds = min(
                        strategy.backoff_seconds * self._settings.backoff_multiplier
                        if strategy.backoff_seconds > 0
                        else self._settings.loop_interval_seconds,
                        self._settings.max_backoff_seconds,
                    )
                    logger.warning(
                        "Topic %s is stale (count=%d, backoff=%.0fs)",
                        strategy.topic,
                        strategy.stale_count,
                        strategy.backoff_seconds,
                    )
                else:
                    # Progress detected — reset staleness
                    strategy.stale_count = 0
                    strategy.backoff_seconds = 0.0

        # Determine mode
        previous_mode = strategy.mode
        strategy.mode = self._determine_mode(strategy, evaluation, topic)
        if strategy.mode != previous_mode:
            logger.info(
                "Strategy mode change for %s: %s → %s",
                strategy.topic,
                previous_mode,
                strategy.mode,
            )
            self._memory.add_plan(
                strategy.topic,
                f"Strategy shifted from {previous_mode} to {strategy.mode}. "
                f"Focus areas: {strategy.focus_areas[:3]}",
            )

        strategy.updated_at = datetime.now(timezone.utc)
        self._cosmos.upsert_strategy(strategy)
        return strategy

    def _determine_mode(
        self,
        strategy: LearningStrategy,
        evaluation: EvaluationResult,
        topic: LearningTopic,
    ) -> str:
        """Determine the optimal learning mode based on evaluation metrics."""
        # Stale for too long → diversify to break out
        if strategy.stale_count >= 3:
            return "diversify"

        # Coverage is good but depth is lacking → go deep
        if (
            evaluation.coverage_score >= self._settings.depth_threshold
            and evaluation.depth_score < 0.5
        ):
            return "depth"

        # Accuracy issues → verify existing claims
        if evaluation.accuracy_score < strategy.confidence_threshold:
            return "verification"

        # Big gaps remain → breadth first
        if len(evaluation.gaps) > 3:
            return "breadth"

        # Few gaps but specific weak areas → targeted depth
        if evaluation.weak_areas:
            return "depth"

        # Everything looks good — maintain with verification
        if evaluation.overall_score >= topic.target_expertise_level * 0.9:
            return "verification"

        return "breadth"

    # ── Plan generation ───────────────────────────────────────────────

    @tracer.start_as_current_span("strategy.generate_plan")
    def generate_plan(
        self,
        topic: LearningTopic,
        strategy: LearningStrategy,
        iteration: int,
    ) -> LearningPlan:
        """Generate a learning plan based on current strategy.

        Returns a plan with scrape queries and reasoning tasks
        tailored to the current strategy mode.
        """
        queries = self._generate_queries(topic, strategy)
        reasoning_tasks = self._generate_reasoning_tasks(strategy)
        priority_weights = self._compute_priority_weights(strategy)

        plan = LearningPlan(
            topic=topic.name,
            iteration=iteration,
            target_areas=list(strategy.focus_areas),
            scrape_queries=queries,
            reasoning_tasks=reasoning_tasks,
            priority_weights=priority_weights,
            rationale=self._build_rationale(strategy),
        )

        self._memory.add_plan(
            topic.name,
            f"Plan for iteration {iteration}: mode={strategy.mode}, "
            f"{len(queries)} queries, {len(reasoning_tasks)} reasoning tasks. "
            f"Focus: {strategy.focus_areas[:3]}",
        )

        logger.info(
            "Generated plan for %s iteration=%d mode=%s queries=%d tasks=%d",
            topic.name,
            iteration,
            strategy.mode,
            len(queries),
            len(reasoning_tasks),
        )
        return plan

    def _generate_queries(
        self, topic: LearningTopic, strategy: LearningStrategy
    ) -> list[str]:
        """Generate scrape queries based on strategy mode and gaps."""
        queries: list[str] = []

        if strategy.mode == "breadth":
            templates = _GAP_QUERY_TEMPLATES
            areas = strategy.recent_gaps or strategy.focus_areas or [topic.name]
            for area in areas[:5]:
                template = random.choice(templates)
                queries.append(template.format(topic=topic.name, area=area))

        elif strategy.mode == "depth":
            templates = _DEPTH_QUERY_TEMPLATES
            areas = strategy.focus_areas or [topic.name]
            for area in areas[:3]:
                for template in random.sample(templates, min(2, len(templates))):
                    queries.append(template.format(topic=topic.name, area=area))

        elif strategy.mode == "verification":
            # Queries to verify existing claims
            areas = strategy.focus_areas or strategy.recent_gaps or [topic.name]
            for area in areas[:4]:
                queries.append(f"{topic.name} {area} fact check")
                queries.append(f"{topic.name} {area} common misconceptions")

        elif strategy.mode == "diversify":
            templates = _DIVERSIFY_QUERY_TEMPLATES
            for template in templates:
                queries.append(template.format(topic=topic.name))
            # Also add gap-driven queries with diverse sources
            for area in (strategy.recent_gaps or [topic.name])[:3]:
                queries.append(f"{topic.name} {area} alternative perspectives")

        # Ensure at least some queries
        if not queries:
            queries = [
                f"{topic.name} comprehensive overview",
                f"{topic.name} latest developments",
                f"{topic.name} key principles",
            ]

        return queries

    def _generate_reasoning_tasks(
        self, strategy: LearningStrategy
    ) -> list[ReasoningType]:
        """Determine which reasoning tasks to request based on strategy mode."""
        tasks: list[ReasoningType] = []

        if strategy.mode == "breadth":
            tasks.append(ReasoningType.GAP_ANALYSIS)
            tasks.append(ReasoningType.INSIGHT_SYNTHESIS)

        elif strategy.mode == "depth":
            tasks.append(ReasoningType.DEPTH_EXPLORATION)
            tasks.append(ReasoningType.INSIGHT_SYNTHESIS)

        elif strategy.mode == "verification":
            tasks.append(ReasoningType.CONTRADICTION_RESOLUTION)
            tasks.append(ReasoningType.GAP_ANALYSIS)

        elif strategy.mode == "diversify":
            tasks.append(ReasoningType.GAP_ANALYSIS)
            tasks.append(ReasoningType.CONTRADICTION_RESOLUTION)
            tasks.append(ReasoningType.INSIGHT_SYNTHESIS)

        return tasks

    def _compute_priority_weights(
        self, strategy: LearningStrategy
    ) -> dict[str, float]:
        """Compute priority weights for pipeline stages based on strategy."""
        weights = {
            "scrape": 1.0,
            "extract": 1.0,
            "reason": 1.0,
            "evaluate": 1.0,
        }

        if strategy.mode == "breadth":
            weights["scrape"] = 1.5
            weights["extract"] = 1.3

        elif strategy.mode == "depth":
            weights["reason"] = 1.5
            weights["scrape"] = 1.2

        elif strategy.mode == "verification":
            weights["reason"] = 1.5
            weights["evaluate"] = 1.3

        elif strategy.mode == "diversify":
            weights["scrape"] = 2.0

        return weights

    def _build_rationale(self, strategy: LearningStrategy) -> str:
        """Build a human-readable rationale for the current plan."""
        parts = [f"Mode: {strategy.mode}."]

        if strategy.recent_gaps:
            parts.append(f"Gaps to address: {', '.join(strategy.recent_gaps[:5])}.")

        if strategy.focus_areas:
            parts.append(f"Focus areas: {', '.join(strategy.focus_areas[:3])}.")

        if strategy.stale_count > 0:
            parts.append(
                f"Stale for {strategy.stale_count} iterations — "
                f"backoff {strategy.backoff_seconds:.0f}s."
            )

        score_history = strategy.iteration_scores[-5:]
        if score_history:
            parts.append(
                f"Recent scores: {', '.join(f'{s:.3f}' for s in score_history)}."
            )

        return " ".join(parts)

    # ── Scrape request creation ───────────────────────────────────────

    def create_scrape_requests(
        self, plan: LearningPlan, topic: LearningTopic
    ) -> list[ScrapeRequest]:
        """Convert a learning plan into concrete scrape requests."""
        requests: list[ScrapeRequest] = []
        for i, query in enumerate(plan.scrape_queries):
            source_type = self._pick_source_type(query, i)
            priority = min(topic.priority + (5 - i), 10)
            requests.append(
                ScrapeRequest(
                    topic=topic.name,
                    query=query,
                    priority=priority,
                    source_type=source_type,
                )
            )
        return requests

    @staticmethod
    def _pick_source_type(query: str, index: int) -> SourceType:
        """Pick source type based on query hints."""
        query_lower = query.lower()
        if "arxiv" in query_lower or "academic" in query_lower or "paper" in query_lower:
            return SourceType.ACADEMIC
        if "rss" in query_lower:
            return SourceType.RSS
        if "api" in query_lower:
            return SourceType.API
        # Alternate web and academic for diversity
        if index % 3 == 0:
            return SourceType.ACADEMIC
        return SourceType.WEB
