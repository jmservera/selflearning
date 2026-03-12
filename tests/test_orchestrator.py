"""Tests for the Orchestrator service.

Covers models, working memory, strategy manager, and FastAPI endpoints.
"""

import os
import sys
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Bare-import isolation ─────────────────────────────────────────────
# Services use bare imports internally (e.g. `from config import …`).
# Each service has its own config.py / models.py, so we must flush
# stale bare-module caches before importing a service's internals.
_BARE_MODULE_NAMES = frozenset({
    "config", "models", "service_bus", "working_memory", "strategy",
    "cosmos_client", "learning_loop", "health_monitor",
    "llm_client", "reasoning",
})


def _setup_service_path(service_name: str) -> None:
    """Flush stale bare-module caches and put *service_name* on sys.path.

    The service directory is inserted right AFTER src/ so that
    package-qualified ``import <service>`` still resolves to the package
    directory (critical when the service dir contains a file with the same
    name, e.g. ``src/healer/healer.py``).
    """
    src_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src"))
    svc_dir = os.path.normpath(os.path.join(src_dir, service_name))
    for name in _BARE_MODULE_NAMES:
        sys.modules.pop(name, None)
    # Remove ALL service directories from sys.path to avoid cross-contamination
    svc_dirs = {os.path.normpath(os.path.join(src_dir, s))
                for s in ("orchestrator", "healer", "reasoner")}
    sys.path[:] = [p for p in sys.path if os.path.normpath(p) not in svc_dirs]
    src_positions = [i for i, p in enumerate(sys.path)
                     if os.path.normpath(p) == src_dir]
    insert_pos = (src_positions[0] + 1) if src_positions else 0
    sys.path.insert(insert_pos, svc_dir)


_setup_service_path("orchestrator")

from orchestrator.config import OrchestratorSettings  # noqa: E402
from orchestrator.models import (  # noqa: E402
    EvaluationResult,
    LearningPlan,
    LearningStrategy,
    LearningTopic,
    LoopIteration,
    MemoryItem,
    OrchestratorStatus,
    PipelineStage,
    PipelineState,
    ReasoningType,
    ScrapeRequest,
    SourceType,
    TopicStatus,
)
# Alias package-qualified modules as bare so internal bare imports
# (e.g. `from models import MemoryItem` inside working_memory.py)
# resolve to the SAME class objects used in tests.
sys.modules["config"] = sys.modules["orchestrator.config"]
sys.modules["models"] = sys.modules["orchestrator.models"]

from orchestrator.working_memory import WorkingMemory  # noqa: E402
sys.modules["working_memory"] = sys.modules["orchestrator.working_memory"]

from orchestrator.strategy import StrategyManager  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────

def _make_settings(**overrides) -> OrchestratorSettings:
    defaults = {
        "working_memory_max_items": 50,
        "working_memory_decay_factor": 0.9,
        "min_sources_per_query": 3,
        "depth_threshold": 0.7,
        "max_stale_iterations": 3,
        "backoff_multiplier": 2.0,
        "max_backoff_seconds": 600.0,
        "loop_interval_seconds": 30.0,
    }
    defaults.update(overrides)
    return OrchestratorSettings(**defaults)


def _make_topic(**overrides) -> LearningTopic:
    defaults = {"name": "quantum-computing", "priority": 5}
    defaults.update(overrides)
    return LearningTopic(**defaults)


def _make_evaluation(**overrides) -> EvaluationResult:
    defaults = {
        "request_id": "eval-1",
        "topic": "quantum-computing",
        "overall_score": 0.5,
        "coverage_score": 0.5,
        "depth_score": 0.5,
        "accuracy_score": 0.5,
    }
    defaults.update(overrides)
    return EvaluationResult(**defaults)


def _make_strategy(**overrides) -> LearningStrategy:
    defaults = {"topic": "quantum-computing", "mode": "breadth"}
    defaults.update(overrides)
    return LearningStrategy(**defaults)


# =====================================================================
# Model Tests
# =====================================================================

class TestModels:
    """Pydantic model construction, validation, and defaults."""

    def test_topic_status_enum_values(self):
        assert TopicStatus.ACTIVE == "active"
        assert TopicStatus.PAUSED == "paused"
        assert TopicStatus.COMPLETE == "complete"

    def test_pipeline_stage_enum_values(self):
        assert len(PipelineStage) == 8
        assert PipelineStage.IDLE == "idle"
        assert PipelineStage.IMPROVE == "improve"

    def test_source_type_enum_values(self):
        assert SourceType.WEB == "web"
        assert SourceType.ACADEMIC == "academic"
        assert SourceType.RSS == "rss"
        assert SourceType.API == "api"
        assert SourceType.SOCIAL == "social"

    def test_reasoning_type_enum_values(self):
        assert len(ReasoningType) == 4

    def test_learning_topic_defaults(self):
        t = LearningTopic(name="ml")
        assert t.priority == 5
        assert t.status == TopicStatus.ACTIVE
        assert t.target_expertise_level == 0.9
        assert t.current_score == 0.0
        assert t.iteration_count == 0
        assert t.description == ""

    def test_learning_topic_partition_key(self):
        t = LearningTopic(name="physics")
        assert t.partition_key == "physics"

    def test_learning_topic_priority_bounds(self):
        t = LearningTopic(name="x", priority=1)
        assert t.priority == 1
        t = LearningTopic(name="x", priority=10)
        assert t.priority == 10
        with pytest.raises(Exception):
            LearningTopic(name="x", priority=0)
        with pytest.raises(Exception):
            LearningTopic(name="x", priority=11)

    def test_learning_topic_score_bounds(self):
        with pytest.raises(Exception):
            LearningTopic(name="x", current_score=-0.1)
        with pytest.raises(Exception):
            LearningTopic(name="x", current_score=1.1)

    def test_learning_topic_target_bounds(self):
        with pytest.raises(Exception):
            LearningTopic(name="x", target_expertise_level=-0.1)
        with pytest.raises(Exception):
            LearningTopic(name="x", target_expertise_level=1.1)

    def test_evaluation_result_defaults(self):
        e = _make_evaluation()
        assert e.gaps == []
        assert e.weak_areas == []
        assert e.strong_areas == []
        assert e.recommendations == []

    def test_evaluation_result_score_bounds(self):
        with pytest.raises(Exception):
            EvaluationResult(request_id="x", topic="t", overall_score=1.5,
                             coverage_score=0.5, depth_score=0.5, accuracy_score=0.5)

    def test_learning_strategy_defaults(self):
        s = LearningStrategy(topic="t")
        assert s.mode == "breadth"
        assert s.stale_count == 0
        assert s.backoff_seconds == 0.0
        assert s.confidence_threshold == 0.7

    def test_memory_item_defaults(self):
        m = MemoryItem(topic="t", content="c")
        assert m.item_type == "finding"
        assert m.relevance == 1.0
        assert m.metadata == {}

    def test_memory_item_relevance_bounds(self):
        with pytest.raises(Exception):
            MemoryItem(topic="t", content="c", relevance=-0.1)
        with pytest.raises(Exception):
            MemoryItem(topic="t", content="c", relevance=1.1)

    def test_pipeline_state_defaults(self):
        p = PipelineState(topic="t")
        assert p.current_stage == PipelineStage.IDLE
        assert p.iteration == 0

    def test_scrape_request_priority_bounds(self):
        with pytest.raises(Exception):
            ScrapeRequest(topic="t", query="q", priority=0)
        with pytest.raises(Exception):
            ScrapeRequest(topic="t", query="q", priority=11)

    def test_orchestrator_status_defaults(self):
        s = OrchestratorStatus()
        assert s.active_topics == []
        assert s.loop_running is False
        assert s.uptime_seconds == 0.0

    def test_loop_iteration_defaults(self):
        li = LoopIteration(iteration_number=1, topic="t")
        assert li.score_before == 0.0
        assert li.completed_at is None


# =====================================================================
# Working Memory Tests
# =====================================================================

class TestWorkingMemory:
    """Tests for the WorkingMemory class."""

    def _make_wm(self, **kwargs) -> WorkingMemory:
        return WorkingMemory(_make_settings(**kwargs))

    def test_add_returns_memory_item(self):
        wm = self._make_wm()
        item = wm.add("ml", "neural nets are cool")
        assert isinstance(item, MemoryItem)
        assert item.topic == "ml"
        assert item.content == "neural nets are cool"
        assert item.item_type == "finding"

    def test_add_caps_relevance_at_one(self):
        wm = self._make_wm()
        item = wm.add("ml", "x", relevance=5.0)
        assert item.relevance == 1.0

    def test_add_finding_default_relevance(self):
        wm = self._make_wm()
        item = wm.add_finding("t", "c")
        assert item.relevance == 1.0
        assert item.item_type == "finding"

    def test_add_gap_default_relevance(self):
        wm = self._make_wm()
        item = wm.add_gap("t", "c")
        assert item.relevance == 0.95
        assert item.item_type == "gap"

    def test_add_insight_default_relevance(self):
        wm = self._make_wm()
        item = wm.add_insight("t", "c")
        assert item.relevance == 0.9
        assert item.item_type == "insight"

    def test_add_plan_default_relevance(self):
        wm = self._make_wm()
        item = wm.add_plan("t", "c")
        assert item.relevance == 0.85
        assert item.item_type == "plan"

    def test_add_error_default_relevance(self):
        wm = self._make_wm()
        item = wm.add_error("t", "c")
        assert item.relevance == 0.8
        assert item.item_type == "error"

    def test_size_property(self):
        wm = self._make_wm()
        assert wm.size == 0
        wm.add("t", "a")
        wm.add("t", "b")
        assert wm.size == 2

    def test_capacity_enforcement(self):
        wm = self._make_wm(working_memory_max_items=3)
        wm.add("t", "a", relevance=0.1)
        wm.add("t", "b", relevance=0.5)
        wm.add("t", "c", relevance=0.9)
        wm.add("t", "d", relevance=1.0)
        assert wm.size == 3
        items = wm.get_context()
        contents = [i.content for i in items]
        # Lowest relevance item should be evicted
        assert "a" not in contents

    def test_set_focus_first_time_no_decay(self):
        wm = self._make_wm()
        wm.add("ml", "item1", relevance=0.5)
        wm.set_focus("ml")
        # First focus (previous is None) should not decay
        items = wm.get_context()
        assert items[0].relevance == 0.5

    def test_set_focus_shift_boosts_on_topic(self):
        wm = self._make_wm()
        wm.set_focus("old")
        item = wm.add("new", "content", relevance=0.8)
        wm.set_focus("new")
        # On-topic should be boosted by 1.1x
        updated = [i for i in wm.get_context() if i.id == item.id][0]
        assert updated.relevance == pytest.approx(0.8 * 1.1, rel=1e-3)

    def test_set_focus_shift_decays_off_topic(self):
        wm = self._make_wm(working_memory_decay_factor=0.9)
        wm.set_focus("old")
        item = wm.add("old", "content", relevance=0.5)
        wm.set_focus("new")
        updated = [i for i in wm.get_context() if i.id == item.id][0]
        assert updated.relevance == pytest.approx(0.5 * 0.9, rel=1e-3)

    def test_decay_evicts_below_threshold(self):
        wm = self._make_wm(working_memory_decay_factor=0.01)
        wm.set_focus("old")
        wm.add("old", "will_evict", relevance=0.06)
        wm.set_focus("new")
        # 0.06 * 0.01 = 0.0006, below 0.05 → evicted
        assert wm.size == 0

    def test_tick_decays_off_topic_only(self):
        wm = self._make_wm(working_memory_decay_factor=0.9)
        wm.set_focus("current")
        wm.add("current", "on-topic", relevance=0.5)
        wm.add("other", "off-topic", relevance=0.5)
        wm.tick()
        items = {i.topic: i.relevance for i in wm.get_context()}
        assert items["current"] == pytest.approx(0.5, rel=1e-3)
        assert items["other"] == pytest.approx(0.5 * 0.9, rel=1e-3)

    def test_tick_evicts_low_relevance(self):
        wm = self._make_wm(working_memory_decay_factor=0.5)
        wm.set_focus("current")
        wm.add("other", "low", relevance=0.06)
        wm.tick()
        # 0.06 * 0.5 = 0.03, below 0.05 → evicted
        assert wm.size == 0

    def test_get_context_sorted_by_relevance(self):
        wm = self._make_wm()
        wm.add("t", "low", relevance=0.1)
        wm.add("t", "high", relevance=0.9)
        wm.add("t", "mid", relevance=0.5)
        items = wm.get_context()
        assert items[0].content == "high"
        assert items[1].content == "mid"
        assert items[2].content == "low"

    def test_get_context_filtered_by_topic(self):
        wm = self._make_wm()
        wm.add("a", "x")
        wm.add("b", "y")
        items = wm.get_context(topic="a")
        assert len(items) == 1
        assert items[0].topic == "a"

    def test_get_context_max_items(self):
        wm = self._make_wm()
        for i in range(10):
            wm.add("t", f"item{i}")
        items = wm.get_context(max_items=3)
        assert len(items) == 3

    def test_get_gaps_filter(self):
        wm = self._make_wm()
        wm.add_gap("t", "gap1")
        wm.add_finding("t", "find1")
        gaps = wm.get_gaps(topic="t")
        assert len(gaps) == 1
        assert gaps[0].item_type == "gap"

    def test_get_insights_filter(self):
        wm = self._make_wm()
        wm.add_insight("t", "ins1")
        wm.add_finding("t", "find1")
        insights = wm.get_insights(topic="t")
        assert len(insights) == 1

    def test_get_errors_filter(self):
        wm = self._make_wm()
        wm.add_error("t", "err1")
        wm.add_finding("t", "find1")
        errors = wm.get_errors(topic="t")
        assert len(errors) == 1

    def test_get_gaps_no_topic_returns_all(self):
        wm = self._make_wm()
        wm.add_gap("a", "gap-a")
        wm.add_gap("b", "gap-b")
        assert len(wm.get_gaps()) == 2

    def test_get_all_topics(self):
        wm = self._make_wm()
        wm.add("ml", "x")
        wm.add("physics", "y")
        wm.add("ml", "z")
        assert wm.get_all_topics() == {"ml", "physics"}

    def test_clear_all(self):
        wm = self._make_wm()
        wm.add("a", "x")
        wm.add("b", "y")
        wm.set_topic_summary("a", "summary-a")
        removed = wm.clear()
        assert removed == 2
        assert wm.size == 0

    def test_clear_specific_topic(self):
        wm = self._make_wm()
        wm.add("a", "x")
        wm.add("b", "y")
        wm.set_topic_summary("a", "summary-a")
        removed = wm.clear(topic="a")
        assert removed == 1
        assert wm.size == 1
        assert wm.get_context()[0].topic == "b"

    def test_snapshot(self):
        wm = self._make_wm()
        wm.add_gap("t", "gap")
        wm.add_finding("t", "find")
        wm.set_focus("t")
        snap = wm.snapshot()
        assert snap["total_items"] == 2
        assert snap["current_topic"] == "t"
        assert "t" in snap["topics"]
        assert snap["items_by_type"]["gap"] == 1
        assert snap["items_by_type"]["finding"] == 1

    def test_build_prompt_context_with_items(self):
        wm = self._make_wm()
        wm.add_gap("t", "missing coverage")
        wm.add_plan("t", "plan to gather data")
        text = wm.build_prompt_context("t")
        assert "Working Memory: t" in text
        assert "[GAPS]" in text
        assert "[PLANS]" in text
        assert "missing coverage" in text

    def test_build_prompt_context_no_items(self):
        wm = self._make_wm()
        text = wm.build_prompt_context("empty")
        assert "No working memory" in text

    def test_build_prompt_context_truncation(self):
        wm = self._make_wm()
        for i in range(30):
            wm.add("t", f"item content number {i} " * 20, relevance=1.0)
        text = wm.build_prompt_context("t", max_tokens_approx=50)
        assert text.endswith("... (truncated)")

    def test_build_prompt_context_with_summary(self):
        wm = self._make_wm()
        wm.add_finding("t", "fact")
        wm.set_topic_summary("t", "This is the topic summary")
        text = wm.build_prompt_context("t")
        assert "This is the topic summary" in text

    def test_focus_counts_tracked(self):
        wm = self._make_wm()
        wm.set_focus("a")
        wm.set_focus("a")
        wm.set_focus("b")
        snap = wm.snapshot()
        assert snap["focus_counts"]["a"] == 2
        assert snap["focus_counts"]["b"] == 1


# =====================================================================
# Strategy Manager Tests
# =====================================================================

class TestStrategyManager:
    """Tests for the StrategyManager class."""

    def _make_manager(self, cosmos=None, memory=None, **kwargs):
        settings = _make_settings(**kwargs)
        cosmos = cosmos or MagicMock()
        memory = memory or WorkingMemory(settings)
        return StrategyManager(settings, cosmos, memory), cosmos, memory

    def test_get_or_create_new(self):
        mgr, cosmos, _ = self._make_manager()
        cosmos.get_strategy.return_value = None
        topic = _make_topic()
        strategy = mgr.get_or_create(topic)
        assert strategy.topic == topic.name
        assert strategy.mode == "breadth"
        cosmos.upsert_strategy.assert_called_once()

    def test_get_or_create_existing(self):
        mgr, cosmos, _ = self._make_manager()
        existing = _make_strategy(mode="depth")
        cosmos.get_strategy.return_value = existing
        strategy = mgr.get_or_create(_make_topic())
        assert strategy.mode == "depth"
        cosmos.upsert_strategy.assert_not_called()

    def test_determine_mode_stale_diversify(self):
        mgr, _, _ = self._make_manager()
        strategy = _make_strategy(stale_count=3)
        mode = mgr._determine_mode(strategy, _make_evaluation(), _make_topic())
        assert mode == "diversify"

    def test_determine_mode_high_coverage_low_depth(self):
        mgr, _, _ = self._make_manager(depth_threshold=0.7)
        strategy = _make_strategy(stale_count=0)
        evaluation = _make_evaluation(coverage_score=0.8, depth_score=0.3)
        mode = mgr._determine_mode(strategy, evaluation, _make_topic())
        assert mode == "depth"

    def test_determine_mode_low_accuracy(self):
        mgr, _, _ = self._make_manager()
        strategy = _make_strategy(stale_count=0, confidence_threshold=0.7)
        evaluation = _make_evaluation(coverage_score=0.5, depth_score=0.6, accuracy_score=0.5)
        mode = mgr._determine_mode(strategy, evaluation, _make_topic())
        assert mode == "verification"

    def test_determine_mode_many_gaps(self):
        mgr, _, _ = self._make_manager()
        strategy = _make_strategy(stale_count=0)
        evaluation = _make_evaluation(accuracy_score=0.9, gaps=["a", "b", "c", "d"])
        mode = mgr._determine_mode(strategy, evaluation, _make_topic())
        assert mode == "breadth"

    def test_determine_mode_weak_areas_depth(self):
        mgr, _, _ = self._make_manager()
        strategy = _make_strategy(stale_count=0)
        evaluation = _make_evaluation(accuracy_score=0.9, gaps=["a"], weak_areas=["x"])
        mode = mgr._determine_mode(strategy, evaluation, _make_topic())
        assert mode == "depth"

    def test_determine_mode_good_score_verification(self):
        mgr, _, _ = self._make_manager()
        strategy = _make_strategy(stale_count=0)
        topic = _make_topic(target_expertise_level=0.9)
        evaluation = _make_evaluation(overall_score=0.85, accuracy_score=0.9,
                                       coverage_score=0.5, depth_score=0.6)
        mode = mgr._determine_mode(strategy, evaluation, topic)
        assert mode == "verification"

    def test_determine_mode_default_breadth(self):
        mgr, _, _ = self._make_manager()
        strategy = _make_strategy(stale_count=0)
        evaluation = _make_evaluation(overall_score=0.3, accuracy_score=0.9, coverage_score=0.5,
                                       depth_score=0.6, gaps=["a"])
        mode = mgr._determine_mode(strategy, evaluation, _make_topic())
        assert mode == "breadth"

    def test_generate_reasoning_tasks_breadth(self):
        mgr, _, _ = self._make_manager()
        s = _make_strategy(mode="breadth")
        tasks = mgr._generate_reasoning_tasks(s)
        assert ReasoningType.GAP_ANALYSIS in tasks
        assert ReasoningType.INSIGHT_SYNTHESIS in tasks

    def test_generate_reasoning_tasks_depth(self):
        mgr, _, _ = self._make_manager()
        s = _make_strategy(mode="depth")
        tasks = mgr._generate_reasoning_tasks(s)
        assert ReasoningType.DEPTH_EXPLORATION in tasks

    def test_generate_reasoning_tasks_verification(self):
        mgr, _, _ = self._make_manager()
        s = _make_strategy(mode="verification")
        tasks = mgr._generate_reasoning_tasks(s)
        assert ReasoningType.CONTRADICTION_RESOLUTION in tasks

    def test_generate_reasoning_tasks_diversify(self):
        mgr, _, _ = self._make_manager()
        s = _make_strategy(mode="diversify")
        tasks = mgr._generate_reasoning_tasks(s)
        assert len(tasks) == 3

    def test_compute_priority_weights_breadth(self):
        mgr, _, _ = self._make_manager()
        w = mgr._compute_priority_weights(_make_strategy(mode="breadth"))
        assert w["scrape"] == 1.5
        assert w["extract"] == 1.3

    def test_compute_priority_weights_depth(self):
        mgr, _, _ = self._make_manager()
        w = mgr._compute_priority_weights(_make_strategy(mode="depth"))
        assert w["reason"] == 1.5
        assert w["scrape"] == 1.2

    def test_compute_priority_weights_verification(self):
        mgr, _, _ = self._make_manager()
        w = mgr._compute_priority_weights(_make_strategy(mode="verification"))
        assert w["reason"] == 1.5
        assert w["evaluate"] == 1.3

    def test_compute_priority_weights_diversify(self):
        mgr, _, _ = self._make_manager()
        w = mgr._compute_priority_weights(_make_strategy(mode="diversify"))
        assert w["scrape"] == 2.0

    def test_pick_source_type_arxiv(self):
        from orchestrator.strategy import StrategyManager
        assert StrategyManager._pick_source_type("arxiv deep learning", 0) == SourceType.ACADEMIC

    def test_pick_source_type_academic(self):
        from orchestrator.strategy import StrategyManager
        assert StrategyManager._pick_source_type("academic papers on RL", 0) == SourceType.ACADEMIC

    def test_pick_source_type_paper(self):
        from orchestrator.strategy import StrategyManager
        assert StrategyManager._pick_source_type("paper on CNNs", 0) == SourceType.ACADEMIC

    def test_pick_source_type_rss(self):
        from orchestrator.strategy import StrategyManager
        assert StrategyManager._pick_source_type("rss feeds for ML", 1) == SourceType.RSS

    def test_pick_source_type_api(self):
        from orchestrator.strategy import StrategyManager
        assert StrategyManager._pick_source_type("api endpoint data", 1) == SourceType.API

    def test_pick_source_type_index_modulo(self):
        from orchestrator.strategy import StrategyManager
        # index % 3 == 0 → ACADEMIC
        assert StrategyManager._pick_source_type("general query", 0) == SourceType.ACADEMIC
        assert StrategyManager._pick_source_type("general query", 3) == SourceType.ACADEMIC
        # others → WEB
        assert StrategyManager._pick_source_type("general query", 1) == SourceType.WEB
        assert StrategyManager._pick_source_type("general query", 2) == SourceType.WEB

    def test_create_scrape_requests(self):
        mgr, _, _ = self._make_manager()
        plan = LearningPlan(topic="ml", iteration=1, scrape_queries=["q1", "q2", "q3"])
        topic = _make_topic(name="ml", priority=7)
        requests = mgr.create_scrape_requests(plan, topic)
        assert len(requests) == 3
        assert requests[0].topic == "ml"
        # priority = min(7 + (5-0), 10) = 10
        assert requests[0].priority == 10
        # priority = min(7 + (5-1), 10) = 10
        assert requests[1].priority == 10
        # priority = min(7 + (5-2), 10) = 10
        assert requests[2].priority == 10

    def test_create_scrape_requests_priority_capped(self):
        mgr, _, _ = self._make_manager()
        plan = LearningPlan(topic="ml", iteration=1,
                           scrape_queries=["q1", "q2", "q3", "q4", "q5", "q6"])
        topic = _make_topic(name="ml", priority=3)
        requests = mgr.create_scrape_requests(plan, topic)
        # priority = min(3 + (5-5), 10) = 3
        assert requests[5].priority == 3

    def test_generate_queries_breadth(self):
        mgr, _, _ = self._make_manager()
        topic = _make_topic()
        s = _make_strategy(mode="breadth", recent_gaps=["gap1"])
        queries = mgr._generate_queries(topic, s)
        assert len(queries) > 0
        assert any("gap1" in q for q in queries)

    def test_generate_queries_diversify(self):
        mgr, _, _ = self._make_manager()
        topic = _make_topic()
        s = _make_strategy(mode="diversify")
        queries = mgr._generate_queries(topic, s)
        assert any("arxiv" in q.lower() or "scholar" in q.lower() for q in queries)

    def test_generate_queries_empty_fallback(self):
        mgr, _, _ = self._make_manager()
        topic = _make_topic()
        s = _make_strategy(mode="unknown_mode")
        queries = mgr._generate_queries(topic, s)
        assert len(queries) == 3
        assert "comprehensive overview" in queries[0]

    def test_update_after_evaluation_staleness(self):
        mgr, cosmos, memory = self._make_manager(max_stale_iterations=3,
                                                   loop_interval_seconds=30.0)
        s = _make_strategy(iteration_scores=[0.5, 0.5, 0.505])
        evaluation = _make_evaluation(overall_score=0.506)
        topic = _make_topic()
        result = mgr.update_after_evaluation(s, evaluation, topic)
        assert result.stale_count == 1
        assert result.backoff_seconds > 0

    def test_update_after_evaluation_resets_stale(self):
        mgr, cosmos, memory = self._make_manager(max_stale_iterations=3)
        s = _make_strategy(iteration_scores=[0.5, 0.5], stale_count=2, backoff_seconds=60.0)
        evaluation = _make_evaluation(overall_score=0.6)
        topic = _make_topic()
        result = mgr.update_after_evaluation(s, evaluation, topic)
        assert result.stale_count == 0
        assert result.backoff_seconds == 0.0

    def test_update_after_evaluation_mode_change_logs_plan(self):
        mgr, cosmos, memory = self._make_manager()
        s = _make_strategy(mode="breadth", stale_count=3, iteration_scores=[0.5])
        evaluation = _make_evaluation(overall_score=0.51)
        topic = _make_topic()
        result = mgr.update_after_evaluation(s, evaluation, topic)
        assert result.mode == "diversify"
        # Should have added a plan item to memory
        plans = memory.get_context()
        plan_items = [i for i in plans if i.item_type == "plan"]
        assert len(plan_items) >= 1

    def test_generate_plan(self):
        mgr, cosmos, memory = self._make_manager()
        topic = _make_topic()
        s = _make_strategy(mode="breadth", focus_areas=["area1"],
                          recent_gaps=["gap1"])
        plan = mgr.generate_plan(topic, s, iteration=1)
        assert isinstance(plan, LearningPlan)
        assert plan.topic == topic.name
        assert plan.iteration == 1
        assert len(plan.scrape_queries) > 0
        assert len(plan.reasoning_tasks) > 0


# =====================================================================
# FastAPI Endpoint Tests
# =====================================================================

class TestEndpoints:
    """Tests for orchestrator FastAPI endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked globals."""
        _setup_service_path("orchestrator")
        sys.modules["config"] = sys.modules["orchestrator.config"]
        sys.modules["models"] = sys.modules["orchestrator.models"]
        sys.modules["working_memory"] = sys.modules["orchestrator.working_memory"]
        import orchestrator.main as orch_mod

        mock_cosmos = MagicMock()
        mock_loop = MagicMock()
        mock_memory = WorkingMemory(_make_settings())

        orch_mod._cosmos = mock_cosmos
        orch_mod._loop = mock_loop
        orch_mod._memory = mock_memory
        orch_mod._start_time = time.monotonic()

        transport = ASGITransport(app=orch_mod.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, mock_cosmos, mock_loop, mock_memory

        # Cleanup
        orch_mod._cosmos = None
        orch_mod._loop = None
        orch_mod._memory = None

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        c, _, _, _ = client
        resp = await c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "orchestrator"

    @pytest.mark.asyncio
    async def test_get_status(self, client):
        c, cosmos, loop, _ = client
        cosmos.list_topics.return_value = []
        loop.get_status.return_value = {"running": True, "current_stages": {}, "iterations_completed": {}}
        resp = await c.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "loop_running" in data

    @pytest.mark.asyncio
    async def test_trigger_learning_new_topic(self, client):
        c, cosmos, _, _ = client
        cosmos.get_topic.return_value = None
        resp = await c.post("/topics/new-topic/learn",
                           json={"name": "new-topic", "description": "desc", "priority": 7})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "new-topic"
        assert data["priority"] == 7
        cosmos.upsert_topic.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_learning_existing_active(self, client):
        c, cosmos, _, _ = client
        existing = _make_topic(name="existing", status=TopicStatus.ACTIVE)
        cosmos.get_topic.return_value = existing
        resp = await c.post("/topics/existing/learn")
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "existing"

    @pytest.mark.asyncio
    async def test_trigger_learning_resumes_paused(self, client):
        c, cosmos, _, _ = client
        paused = _make_topic(name="paused-t", status=TopicStatus.PAUSED)
        cosmos.get_topic.return_value = paused
        resumed = _make_topic(name="paused-t", status=TopicStatus.ACTIVE)
        cosmos.update_topic_status.return_value = resumed
        resp = await c.post("/topics/paused-t/learn")
        assert resp.status_code == 201
        cosmos.update_topic_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_topic(self, client):
        c, cosmos, _, _ = client
        cosmos.update_topic_status.return_value = _make_topic(status=TopicStatus.PAUSED)
        resp = await c.put("/topics/some-topic/pause")
        assert resp.status_code == 200
        assert "paused" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_pause_topic_not_found(self, client):
        c, cosmos, _, _ = client
        cosmos.update_topic_status.return_value = None
        resp = await c.put("/topics/missing/pause")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_topic(self, client):
        c, cosmos, _, _ = client
        cosmos.update_topic_status.return_value = _make_topic(status=TopicStatus.ACTIVE)
        resp = await c.put("/topics/some-topic/resume")
        assert resp.status_code == 200
        assert "resumed" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_resume_topic_not_found(self, client):
        c, cosmos, _, _ = client
        cosmos.update_topic_status.return_value = None
        resp = await c.put("/topics/missing/resume")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_topics(self, client):
        c, cosmos, _, _ = client
        cosmos.list_topics.return_value = [_make_topic(name="a"), _make_topic(name="b")]
        resp = await c.get("/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_list_topics_filtered(self, client):
        c, cosmos, _, _ = client
        cosmos.list_topics.return_value = [_make_topic(name="a", status=TopicStatus.ACTIVE)]
        resp = await c.get("/topics?topic_status=active")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_pipeline(self, client):
        c, _, loop, _ = client
        loop.get_topic_pipeline.return_value = {"stage": "scrape", "progress": 0.5}
        resp = await c.get("/topics/some-topic/pipeline")
        assert resp.status_code == 200
        assert resp.json()["stage"] == "scrape"

    @pytest.mark.asyncio
    async def test_memory_snapshot(self, client):
        c, _, _, memory = client
        memory.add_finding("t", "fact")
        resp = await c.get("/memory/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_items"] == 1

    @pytest.mark.asyncio
    async def test_memory_context(self, client):
        c, _, _, memory = client
        memory.add_gap("t", "missing info")
        resp = await c.get("/memory/t")
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic"] == "t"
        assert "missing info" in data["context"]
