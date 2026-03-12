"""The autonomous learning loop — the core brain of the selflearning system.

Continuously cycles through:
  Plan → Scrape → Extract → Organize → Reason → Evaluate → Improve

Each iteration is self-directing: evaluation results drive the next plan.
Multiple topics are managed concurrently with priority-based scheduling.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace

from config import OrchestratorSettings
from cosmos_client import CosmosDBClient
from models import (
    CompletionEvent,
    EvaluationResult,
    LearningPlan,
    LearningTopic,
    LoopIteration,
    PipelineStage,
    PipelineState,
    ReasoningRequest,
    ReasoningType,
    ScrapeRequest,
    TopicStatus,
)
from service_bus import OrchestratorServiceBus
from strategy import StrategyManager
from working_memory import WorkingMemory

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class LearningLoop:
    """The autonomous learning loop that drives the selflearning pipeline.

    Architecture:
      - Manages multiple topics concurrently (up to max_concurrent_topics)
      - Each topic goes through the full pipeline: Plan→Scrape→Extract→
        Organize→Reason→Evaluate→Improve
      - Priority-based scheduling: higher-priority topics run first
      - Backoff on stale topics (no score improvement)
      - Robust error handling: individual stage failures don't crash the loop
      - All state persisted to Cosmos DB for crash recovery
    """

    def __init__(
        self,
        settings: OrchestratorSettings,
        cosmos: CosmosDBClient,
        service_bus: OrchestratorServiceBus,
        memory: WorkingMemory,
        strategy_mgr: StrategyManager,
    ) -> None:
        self._settings = settings
        self._cosmos = cosmos
        self._bus = service_bus
        self._memory = memory
        self._strategy = strategy_mgr

        self._running = False
        self._started_at: datetime | None = None
        self._iterations_completed: dict[str, int] = {}
        self._current_stages: dict[str, PipelineStage] = {}
        self._active_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the main learning loop."""
        if self._running:
            logger.warning("Learning loop already running")
            return
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        logger.info("Learning loop starting")
        asyncio.create_task(self._main_loop(), name="learning-loop-main")

    async def stop(self) -> None:
        """Gracefully stop the learning loop."""
        logger.info("Learning loop stopping — waiting for active tasks")
        self._running = False
        # Cancel all active per-topic tasks
        for topic_name, task in self._active_tasks.items():
            task.cancel()
            logger.info("Cancelled task for topic=%s", topic_name)
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)
        self._active_tasks.clear()
        logger.info("Learning loop stopped")

    # ── Main loop ─────────────────────────────────────────────────────

    async def _main_loop(self) -> None:
        """Main scheduling loop — picks topics and dispatches pipeline runs."""
        logger.info("Main loop entered")
        while self._running:
            try:
                with tracer.start_as_current_span("learning_loop.tick"):
                    await self._tick()
            except asyncio.CancelledError:
                logger.info("Main loop cancelled")
                break
            except Exception as exc:
                logger.error("Main loop error: %s", exc, exc_info=True)
                await asyncio.sleep(5.0)

            # Adaptive sleep — shorter when topics are active
            active_count = len(self._active_tasks)
            sleep_time = (
                self._settings.loop_interval_seconds
                if active_count == 0
                else max(5.0, self._settings.loop_interval_seconds / 2)
            )
            await asyncio.sleep(sleep_time)

        logger.info("Main loop exited")

    async def _tick(self) -> None:
        """Single tick of the main loop: schedule topics that need work."""
        # Clean up completed tasks
        done_topics = [
            name
            for name, task in self._active_tasks.items()
            if task.done()
        ]
        for topic_name in done_topics:
            task = self._active_tasks.pop(topic_name)
            if task.exception():
                logger.error(
                    "Topic %s task failed: %s", topic_name, task.exception()
                )

        # Load active topics from Cosmos DB
        active_topics = self._cosmos.list_topics(status=TopicStatus.ACTIVE)
        if not active_topics:
            logger.debug("No active topics — idle")
            return

        # Sort by priority (highest first)
        active_topics.sort(key=lambda t: t.priority, reverse=True)

        # Schedule topics up to concurrency limit
        available_slots = self._settings.max_concurrent_topics - len(self._active_tasks)
        if available_slots <= 0:
            logger.debug(
                "All %d slots occupied — skipping scheduling",
                self._settings.max_concurrent_topics,
            )
            return

        for topic in active_topics[:available_slots]:
            if topic.name in self._active_tasks:
                continue

            # Check backoff
            strategy = self._strategy.get_or_create(topic)
            if strategy.backoff_seconds > 0:
                state = self._cosmos.get_pipeline_state(topic.name)
                if state and state.last_activity:
                    elapsed = (datetime.now(timezone.utc) - state.last_activity).total_seconds()
                    if elapsed < strategy.backoff_seconds:
                        logger.debug(
                            "Topic %s in backoff (%.0f/%.0fs)",
                            topic.name,
                            elapsed,
                            strategy.backoff_seconds,
                        )
                        continue

            # Launch pipeline for this topic
            task = asyncio.create_task(
                self._run_topic_pipeline(topic),
                name=f"pipeline-{topic.name}",
            )
            self._active_tasks[topic.name] = task
            logger.info(
                "Scheduled pipeline for topic=%s priority=%d",
                topic.name,
                topic.priority,
            )

    # ── Per-topic pipeline ────────────────────────────────────────────

    async def _run_topic_pipeline(self, topic: LearningTopic) -> None:
        """Run one full learning iteration for a topic.

        Stages: Plan → Scrape → Extract → Organize → Reason → Evaluate → Improve
        """
        iteration_num = topic.iteration_count + 1
        iteration = LoopIteration(
            iteration_number=iteration_num,
            topic=topic.name,
            score_before=topic.current_score,
        )
        self._memory.set_focus(topic.name)
        logger.info(
            "=== Starting iteration %d for topic=%s (score=%.3f) ===",
            iteration_num,
            topic.name,
            topic.current_score,
        )

        pipeline_state = PipelineState(
            topic=topic.name,
            iteration=iteration_num,
        )

        try:
            # ── PLAN ──────────────────────────────────────────────
            await self._stage_plan(topic, pipeline_state, iteration)

            # ── SCRAPE ────────────────────────────────────────────
            await self._stage_scrape(topic, pipeline_state, iteration)

            # ── EXTRACT (wait for extractor completion) ───────────
            await self._stage_extract(topic, pipeline_state, iteration)

            # ── ORGANIZE (handled by knowledge service on extract)
            await self._stage_organize(topic, pipeline_state, iteration)

            # ── REASON ────────────────────────────────────────────
            await self._stage_reason(topic, pipeline_state, iteration)

            # ── EVALUATE ──────────────────────────────────────────
            evaluation = await self._stage_evaluate(topic, pipeline_state, iteration)

            # ── IMPROVE ───────────────────────────────────────────
            await self._stage_improve(topic, pipeline_state, iteration, evaluation)

        except asyncio.CancelledError:
            logger.info("Pipeline cancelled for topic=%s", topic.name)
            iteration.errors.append("Pipeline cancelled")
            raise
        except Exception as exc:
            logger.error(
                "Pipeline error for topic=%s: %s", topic.name, exc, exc_info=True
            )
            iteration.errors.append(str(exc))
            self._memory.add_error(topic.name, f"Pipeline error: {exc}")
        finally:
            # Record completion
            iteration.completed_at = datetime.now(timezone.utc)
            iteration.duration_seconds = (
                iteration.completed_at - iteration.started_at
            ).total_seconds()
            self._cosmos.save_iteration(iteration)
            self._iterations_completed[topic.name] = iteration_num
            self._current_stages[topic.name] = PipelineStage.IDLE
            pipeline_state.current_stage = PipelineStage.IDLE
            pipeline_state.last_activity = datetime.now(timezone.utc)
            self._cosmos.upsert_pipeline_state(pipeline_state)
            self._memory.tick()

            logger.info(
                "=== Iteration %d complete for topic=%s: %.3f → %.3f (%.1fs) ===",
                iteration_num,
                topic.name,
                iteration.score_before,
                iteration.score_after,
                iteration.duration_seconds,
            )

    # ── Individual stages ─────────────────────────────────────────────

    async def _stage_plan(
        self,
        topic: LearningTopic,
        state: PipelineState,
        iteration: LoopIteration,
    ) -> LearningPlan:
        """Planning phase: analyse gaps and generate a learning plan."""
        with tracer.start_as_current_span("learning_loop.plan") as span:
            span.set_attribute("topic", topic.name)
            self._update_stage(topic.name, state, PipelineStage.PLAN)

            strategy = self._strategy.get_or_create(topic)
            plan = self._strategy.generate_plan(topic, strategy, iteration.iteration_number)

            iteration.stages_completed.append(PipelineStage.PLAN)
            logger.info(
                "PLAN complete: %d queries, %d reasoning tasks for %s",
                len(plan.scrape_queries),
                len(plan.reasoning_tasks),
                topic.name,
            )
            return plan

    async def _stage_scrape(
        self,
        topic: LearningTopic,
        state: PipelineState,
        iteration: LoopIteration,
    ) -> list[CompletionEvent]:
        """Scrape phase: publish scrape requests and wait for completions."""
        with tracer.start_as_current_span("learning_loop.scrape") as span:
            span.set_attribute("topic", topic.name)
            self._update_stage(topic.name, state, PipelineStage.SCRAPE)

            strategy = self._strategy.get_or_create(topic)
            plan = self._strategy.generate_plan(topic, strategy, iteration.iteration_number)
            scrape_requests = self._strategy.create_scrape_requests(plan, topic)

            if not scrape_requests:
                logger.warning("No scrape requests generated for topic=%s", topic.name)
                iteration.stages_completed.append(PipelineStage.SCRAPE)
                return []

            # Track pending request IDs
            request_ids = set()
            for req in scrape_requests:
                request_ids.add(req.request_id)
                state.pending_requests.append(req.request_id)

            # Publish all scrape requests
            await self._bus.publish_scrape_requests_batch(scrape_requests)
            iteration.scrape_requests_sent = len(scrape_requests)
            span.set_attribute("requests_sent", len(scrape_requests))

            # Wait for completion events
            completions = await self._bus.wait_for_completions(
                request_ids=request_ids,
                topic_name=self._settings.scrape_complete_topic,
                timeout_seconds=self._settings.scrape_wait_timeout_seconds,
            )

            # Update state
            for event in completions:
                state.completed_requests.append(event.request_id)
                if event.status == "success":
                    self._memory.add_finding(
                        topic.name,
                        f"Scrape completed: {event.result.get('summary', 'content retrieved')}",
                    )
                else:
                    state.error_count += 1
                    self._memory.add_error(
                        topic.name,
                        f"Scrape failed for {event.request_id}: {event.error}",
                    )

            iteration.stages_completed.append(PipelineStage.SCRAPE)
            logger.info(
                "SCRAPE complete: %d/%d succeeded for %s",
                len([c for c in completions if c.status == "success"]),
                len(scrape_requests),
                topic.name,
            )
            return completions

    async def _stage_extract(
        self,
        topic: LearningTopic,
        state: PipelineState,
        iteration: LoopIteration,
    ) -> list[CompletionEvent]:
        """Extract phase: wait for extraction-complete events.

        The extractor is triggered by scrape-complete events, so we just
        listen for extraction completions that reference our topic.
        """
        with tracer.start_as_current_span("learning_loop.extract") as span:
            span.set_attribute("topic", topic.name)
            self._update_stage(topic.name, state, PipelineStage.EXTRACT)

            # Wait for extraction completions based on our scrape request IDs
            pending = set(state.completed_requests)
            if not pending:
                logger.info("No completed scrapes to extract for %s", topic.name)
                iteration.stages_completed.append(PipelineStage.EXTRACT)
                return []

            completions = await self._bus.wait_for_completions(
                request_ids=pending,
                topic_name=self._settings.extraction_complete_topic,
                timeout_seconds=self._settings.extraction_wait_timeout_seconds,
            )

            extracted_count = 0
            for event in completions:
                if event.status == "success":
                    extracted_count += 1
                    entities = event.result.get("entities_extracted", 0)
                    self._memory.add_finding(
                        topic.name,
                        f"Extracted {entities} entities from document",
                    )
                else:
                    self._memory.add_error(
                        topic.name,
                        f"Extraction failed: {event.error}",
                    )

            iteration.documents_extracted = extracted_count
            iteration.stages_completed.append(PipelineStage.EXTRACT)
            logger.info(
                "EXTRACT complete: %d documents extracted for %s",
                extracted_count,
                topic.name,
            )
            return completions

    async def _stage_organize(
        self,
        topic: LearningTopic,
        state: PipelineState,
        iteration: LoopIteration,
    ) -> None:
        """Organize phase: knowledge service ingests extracted data.

        The knowledge service processes extraction-complete events directly.
        We mark this stage as a checkpoint — the organize step is event-driven
        on the knowledge service side.
        """
        with tracer.start_as_current_span("learning_loop.organize") as span:
            span.set_attribute("topic", topic.name)
            self._update_stage(topic.name, state, PipelineStage.ORGANIZE)

            # Allow time for the knowledge service to process
            await asyncio.sleep(2.0)
            iteration.stages_completed.append(PipelineStage.ORGANIZE)
            logger.info("ORGANIZE stage complete for %s (event-driven)", topic.name)

    async def _stage_reason(
        self,
        topic: LearningTopic,
        state: PipelineState,
        iteration: LoopIteration,
    ) -> list[CompletionEvent]:
        """Reason phase: publish reasoning requests and wait for results."""
        with tracer.start_as_current_span("learning_loop.reason") as span:
            span.set_attribute("topic", topic.name)
            self._update_stage(topic.name, state, PipelineStage.REASON)

            strategy = self._strategy.get_or_create(topic)
            plan = self._strategy.generate_plan(topic, strategy, iteration.iteration_number)

            # Build context from working memory for the reasoner
            wm_context = self._memory.build_prompt_context(topic.name)

            request_ids: set[str] = set()
            for reasoning_type in plan.reasoning_tasks:
                req = ReasoningRequest(
                    topic=topic.name,
                    reasoning_type=reasoning_type,
                    context={
                        "working_memory": wm_context,
                        "iteration": iteration.iteration_number,
                        "focus_areas": strategy.focus_areas,
                        "gaps": strategy.recent_gaps,
                    },
                )
                request_ids.add(req.request_id)
                await self._bus.publish_reasoning_request(req)

            if not request_ids:
                iteration.stages_completed.append(PipelineStage.REASON)
                return []

            # Wait for reasoning completions
            completions = await self._bus.wait_for_completions(
                request_ids=request_ids,
                topic_name=self._settings.reasoning_complete_topic,
                timeout_seconds=self._settings.reasoning_wait_timeout_seconds,
            )

            insights_count = 0
            for event in completions:
                if event.status == "success":
                    insights = event.result.get("insights", [])
                    insights_count += len(insights)
                    for insight in insights[:5]:
                        self._memory.add_insight(topic.name, str(insight))
                    gaps = event.result.get("gaps", [])
                    for gap in gaps[:5]:
                        self._memory.add_gap(topic.name, str(gap))
                else:
                    self._memory.add_error(
                        topic.name,
                        f"Reasoning failed: {event.error}",
                    )

            iteration.insights_generated = insights_count
            iteration.stages_completed.append(PipelineStage.REASON)
            logger.info(
                "REASON complete: %d insights generated for %s",
                insights_count,
                topic.name,
            )
            return completions

    async def _stage_evaluate(
        self,
        topic: LearningTopic,
        state: PipelineState,
        iteration: LoopIteration,
    ) -> EvaluationResult | None:
        """Evaluate phase: request evaluation and receive scorecard."""
        with tracer.start_as_current_span("learning_loop.evaluate") as span:
            span.set_attribute("topic", topic.name)
            self._update_stage(topic.name, state, PipelineStage.EVALUATE)

            # Publish evaluation request as a reasoning request of type gap_analysis
            eval_req = ReasoningRequest(
                topic=topic.name,
                reasoning_type=ReasoningType.GAP_ANALYSIS,
                context={
                    "request_type": "evaluation",
                    "iteration": iteration.iteration_number,
                    "current_score": topic.current_score,
                },
                priority=10,
            )
            await self._bus.publish_reasoning_request(eval_req)

            # Wait for evaluation result
            evaluation = await self._bus.wait_for_evaluation(
                timeout_seconds=self._settings.evaluation_wait_timeout_seconds
            )

            if evaluation:
                iteration.score_after = evaluation.overall_score
                self._cosmos.update_topic_score(
                    topic.name, evaluation.overall_score, iteration.iteration_number
                )
                self._memory.add_finding(
                    topic.name,
                    f"Evaluation score: {evaluation.overall_score:.3f} "
                    f"(coverage={evaluation.coverage_score:.3f}, "
                    f"depth={evaluation.depth_score:.3f}, "
                    f"accuracy={evaluation.accuracy_score:.3f})",
                )
                for gap in evaluation.gaps[:5]:
                    self._memory.add_gap(topic.name, gap)
                logger.info(
                    "EVALUATE complete: score=%.3f for %s",
                    evaluation.overall_score,
                    topic.name,
                )
            else:
                logger.warning("No evaluation received for %s — using previous score", topic.name)
                iteration.score_after = topic.current_score
                iteration.errors.append("Evaluation timeout")

            iteration.stages_completed.append(PipelineStage.EVALUATE)
            return evaluation

    async def _stage_improve(
        self,
        topic: LearningTopic,
        state: PipelineState,
        iteration: LoopIteration,
        evaluation: EvaluationResult | None,
    ) -> None:
        """Improve phase: analyse what worked, adjust strategy for next iteration."""
        with tracer.start_as_current_span("learning_loop.improve") as span:
            span.set_attribute("topic", topic.name)
            self._update_stage(topic.name, state, PipelineStage.IMPROVE)

            strategy = self._strategy.get_or_create(topic)

            if evaluation:
                strategy = self._strategy.update_after_evaluation(
                    strategy, evaluation, topic
                )
                improvements = self._analyse_improvements(iteration, evaluation, strategy)
                iteration.improvements_made = improvements
                for imp in improvements:
                    self._memory.add_insight(topic.name, f"Improvement: {imp}")
            else:
                iteration.improvements_made = ["No evaluation data — maintaining current strategy"]

            # Check if topic has reached target
            if iteration.score_after >= topic.target_expertise_level:
                logger.info(
                    "🎓 Topic %s reached target (%.3f >= %.3f) — marking complete!",
                    topic.name,
                    iteration.score_after,
                    topic.target_expertise_level,
                )
                self._cosmos.update_topic_status(topic.name, TopicStatus.COMPLETE)
                self._memory.set_topic_summary(
                    topic.name,
                    f"Target expertise reached: {iteration.score_after:.3f}",
                )

            iteration.stages_completed.append(PipelineStage.IMPROVE)
            logger.info(
                "IMPROVE complete for %s: %d improvements identified",
                topic.name,
                len(iteration.improvements_made),
            )

    # ── Helpers ───────────────────────────────────────────────────────

    def _update_stage(
        self, topic_name: str, state: PipelineState, stage: PipelineStage
    ) -> None:
        """Update and persist the current pipeline stage."""
        self._current_stages[topic_name] = stage
        state.current_stage = stage
        state.last_activity = datetime.now(timezone.utc)
        self._cosmos.upsert_pipeline_state(state)
        logger.debug("Stage → %s for topic=%s", stage.value, topic_name)

    @staticmethod
    def _analyse_improvements(
        iteration: LoopIteration,
        evaluation: EvaluationResult,
        strategy: Any,
    ) -> list[str]:
        """Analyse what improvements to make based on iteration results."""
        improvements: list[str] = []

        score_delta = iteration.score_after - iteration.score_before
        if score_delta > 0.05:
            improvements.append(
                f"Score improved by {score_delta:.3f} — current strategy effective"
            )
        elif score_delta > 0:
            improvements.append(
                f"Marginal improvement ({score_delta:.3f}) — may need strategy adjustment"
            )
        else:
            improvements.append(
                f"No improvement (delta={score_delta:.3f}) — strategy shift needed"
            )

        if evaluation.coverage_score < 0.5:
            improvements.append("Coverage below 50% — prioritize breadth in next iteration")

        if evaluation.depth_score < 0.3:
            improvements.append("Depth critically low — queue deep-dive queries")

        if evaluation.accuracy_score < 0.7:
            improvements.append("Accuracy concerns — trigger verification mode")

        if len(evaluation.gaps) > 5:
            improvements.append(
                f"{len(evaluation.gaps)} gaps identified — focus on top 3: "
                f"{', '.join(evaluation.gaps[:3])}"
            )

        if iteration.errors:
            improvements.append(
                f"{len(iteration.errors)} errors this iteration — investigate reliability"
            )

        if hasattr(strategy, "stale_count") and strategy.stale_count > 0:
            improvements.append(
                f"Stale for {strategy.stale_count} iterations — backoff and diversify"
            )

        return improvements

    # ── Status for API ────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Return a snapshot of loop status for the API."""
        return {
            "running": self._running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "active_tasks": list(self._active_tasks.keys()),
            "current_stages": {k: v.value for k, v in self._current_stages.items()},
            "iterations_completed": dict(self._iterations_completed),
        }

    def get_topic_pipeline(self, topic_name: str) -> dict[str, Any]:
        """Return pipeline state for a specific topic."""
        state = self._cosmos.get_pipeline_state(topic_name)
        if state:
            return state.model_dump(mode="json")
        return {
            "topic": topic_name,
            "current_stage": self._current_stages.get(topic_name, PipelineStage.IDLE).value,
            "iteration": self._iterations_completed.get(topic_name, 0),
        }
