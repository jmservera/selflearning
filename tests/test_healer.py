"""Tests for the Healer service.

Covers models, health monitor circuit breaker, healer DLQ triage/scaling,
and FastAPI endpoints.
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Azure SDK mock & bare-import isolation ────────────────────────────
# azure.mgmt.appcontainers is not installed at all
sys.modules.setdefault("azure.mgmt", MagicMock())
sys.modules.setdefault("azure.mgmt.appcontainers", MagicMock())
sys.modules.setdefault("azure.mgmt.appcontainers.aio", MagicMock())
# azure.servicebus IS installed but the .management.aio submodule is missing
sys.modules.setdefault("azure.servicebus.management.aio", MagicMock())

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
    svc_dirs = {os.path.normpath(os.path.join(src_dir, s))
                for s in ("orchestrator", "healer", "reasoner")}
    sys.path[:] = [p for p in sys.path if os.path.normpath(p) not in svc_dirs]
    src_positions = [i for i, p in enumerate(sys.path)
                     if os.path.normpath(p) == src_dir]
    insert_pos = (src_positions[0] + 1) if src_positions else 0
    sys.path.insert(insert_pos, svc_dir)


_setup_service_path("healer")

from healer.config import HealerSettings  # noqa: E402
from healer.models import (  # noqa: E402
    CircuitBreakerState,
    CircuitState,
    DLQMessage,
    DLQStats,
    HealerStatus,
    HealingAction,
    HealingActionType,
    HealingEvent,
    HealingOutcome,
    PromptTuningResult,
    ScalingRecommendation,
    ServiceHealth,
    ServiceStatus,
)
# Alias package-qualified modules as bare so internal bare imports
# resolve to the SAME class objects used in tests.
sys.modules["config"] = sys.modules["healer.config"]
sys.modules["models"] = sys.modules["healer.models"]

from healer.health_monitor import HealthMonitor  # noqa: E402
sys.modules["health_monitor"] = sys.modules["healer.health_monitor"]

from healer.healer import Healer  # noqa: E402

# healer.main does `from healer import Healer`; when imported as a package
# the bare name isn't exported.  Patch it onto the package.
import healer as _healer_pkg  # noqa: E402
_healer_pkg.Healer = Healer


# ── Helpers ───────────────────────────────────────────────────────────

def _make_settings(**overrides) -> HealerSettings:
    defaults = {
        "circuit_failure_threshold": 5,
        "circuit_recovery_timeout_seconds": 60,
        "circuit_half_open_max_calls": 3,
        "dlq_max_replay_attempts": 3,
        "scale_up_queue_threshold": 100,
        "scale_down_queue_threshold": 5,
        "latency_threshold_ms": 5000.0,
        "error_rate_threshold": 0.1,
    }
    defaults.update(overrides)
    return HealerSettings(**defaults)


def _make_dlq_message(**overrides) -> DLQMessage:
    defaults = {
        "message_id": "msg-1",
        "queue_or_topic": "scrape-requests",
        "body": {"data": "test"},
        "delivery_count": 1,
        "replay_count": 0,
    }
    defaults.update(overrides)
    return DLQMessage(**defaults)


# =====================================================================
# Model Tests
# =====================================================================

class TestModels:
    """Healer model construction, defaults, and properties."""

    def test_service_status_enum(self):
        assert ServiceStatus.HEALTHY == "healthy"
        assert ServiceStatus.DEGRADED == "degraded"
        assert ServiceStatus.DOWN == "down"
        assert ServiceStatus.UNKNOWN == "unknown"

    def test_healing_action_type_enum(self):
        assert len(HealingActionType) == 8
        assert HealingActionType.RESTART == "restart"
        assert HealingActionType.DLQ_DISCARD == "dlq_discard"

    def test_healing_outcome_enum(self):
        assert HealingOutcome.SUCCESS == "success"
        assert HealingOutcome.PENDING == "pending"

    def test_circuit_state_enum(self):
        assert CircuitState.CLOSED == "closed"
        assert CircuitState.OPEN == "open"
        assert CircuitState.HALF_OPEN == "half_open"

    def test_service_health_error_rate_no_data(self):
        h = ServiceHealth(service_name="test")
        assert h.error_rate == 0.0

    def test_service_health_error_rate_with_data(self):
        h = ServiceHealth(service_name="test", error_count_window=2, success_count_window=8)
        assert h.error_rate == pytest.approx(0.2)

    def test_service_health_error_rate_all_errors(self):
        h = ServiceHealth(service_name="test", error_count_window=5, success_count_window=0)
        assert h.error_rate == 1.0

    def test_service_health_defaults(self):
        h = ServiceHealth(service_name="svc")
        assert h.status == ServiceStatus.UNKNOWN
        assert h.consecutive_failures == 0
        assert h.latency_ms == 0.0

    def test_circuit_breaker_state_defaults(self):
        cb = CircuitBreakerState(service="svc")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.opened_at is None

    def test_dlq_message_defaults(self):
        msg = DLQMessage(message_id="m1", queue_or_topic="q1")
        assert msg.delivery_count == 0
        assert msg.replay_count == 0
        assert msg.dead_letter_reason is None

    def test_dlq_stats_defaults(self):
        s = DLQStats(queue_name="q1")
        assert s.message_count == 0
        assert s.oldest_message_age_seconds is None

    def test_healing_action_defaults(self):
        a = HealingAction(service="svc", action_type=HealingActionType.RESTART, reason="test")
        assert a.outcome == HealingOutcome.PENDING
        assert a.details == {}
        assert a.duration_ms is None

    def test_healer_status_defaults(self):
        s = HealerStatus()
        assert s.services_monitored == []
        assert s.dlq_total_messages == 0

    def test_healing_event_defaults(self):
        e = HealingEvent(event_type=HealingActionType.RESTART, service="svc", action_taken="restart")
        assert e.outcome == HealingOutcome.PENDING

    def test_scaling_recommendation_fields(self):
        r = ScalingRecommendation(service="svc", current_queue_depth=150,
                                   recommended_action="scale_up", recommended_replicas=4)
        assert r.recommended_replicas == 4
        assert r.reason == ""

    def test_prompt_tuning_result_defaults(self):
        p = PromptTuningResult(service="svc")
        assert p.current_prompt_hash == ""
        assert p.suggested_changes == []
        assert p.quality_before == 0.0


# =====================================================================
# Health Monitor Tests
# =====================================================================

class TestHealthMonitor:
    """Tests for HealthMonitor circuit breaker state machine."""

    def _make_monitor(self, **kwargs):
        settings = _make_settings(**kwargs)
        bus = MagicMock()
        monitor = HealthMonitor(settings, bus)
        return monitor, settings

    def test_update_circuit_closed_healthy_decrements_failures(self):
        monitor, _ = self._make_monitor()
        cb = CircuitBreakerState(service="svc", state=CircuitState.CLOSED, failure_count=3)
        monitor._circuits["svc"] = cb
        health = ServiceHealth(service_name="svc", status=ServiceStatus.HEALTHY)
        monitor._update_circuit("svc", health)
        assert cb.failure_count == 2
        assert cb.state == CircuitState.CLOSED

    def test_update_circuit_closed_healthy_no_negative_failures(self):
        monitor, _ = self._make_monitor()
        cb = CircuitBreakerState(service="svc", state=CircuitState.CLOSED, failure_count=0)
        monitor._circuits["svc"] = cb
        health = ServiceHealth(service_name="svc", status=ServiceStatus.HEALTHY)
        monitor._update_circuit("svc", health)
        assert cb.failure_count == 0

    def test_update_circuit_closed_degraded_increments_failures(self):
        monitor, _ = self._make_monitor()
        cb = CircuitBreakerState(service="svc", state=CircuitState.CLOSED, failure_count=0)
        monitor._circuits["svc"] = cb
        health = ServiceHealth(service_name="svc", status=ServiceStatus.DEGRADED)
        monitor._update_circuit("svc", health)
        assert cb.failure_count == 1

    def test_update_circuit_closed_to_open_at_threshold(self):
        monitor, _ = self._make_monitor(circuit_failure_threshold=3)
        cb = CircuitBreakerState(service="svc", state=CircuitState.CLOSED, failure_count=2)
        monitor._circuits["svc"] = cb
        health = ServiceHealth(service_name="svc", status=ServiceStatus.DOWN)
        monitor._update_circuit("svc", health)
        assert cb.state == CircuitState.OPEN
        assert cb.opened_at is not None

    def test_update_circuit_open_stays_open_before_timeout(self):
        monitor, _ = self._make_monitor(circuit_recovery_timeout_seconds=60)
        now = datetime.now(timezone.utc)
        cb = CircuitBreakerState(service="svc", state=CircuitState.OPEN,
                                  opened_at=now)
        monitor._circuits["svc"] = cb
        health = ServiceHealth(service_name="svc", status=ServiceStatus.DOWN)
        monitor._update_circuit("svc", health)
        assert cb.state == CircuitState.OPEN

    def test_update_circuit_open_to_half_open_after_timeout(self):
        monitor, _ = self._make_monitor(circuit_recovery_timeout_seconds=60)
        past = datetime.now(timezone.utc) - timedelta(seconds=120)
        cb = CircuitBreakerState(service="svc", state=CircuitState.OPEN, opened_at=past)
        monitor._circuits["svc"] = cb
        health = ServiceHealth(service_name="svc", status=ServiceStatus.DEGRADED)
        monitor._update_circuit("svc", health)
        assert cb.state == CircuitState.HALF_OPEN

    def test_update_circuit_half_open_healthy_increments(self):
        monitor, _ = self._make_monitor(circuit_half_open_max_calls=3)
        cb = CircuitBreakerState(service="svc", state=CircuitState.HALF_OPEN,
                                  success_count=1, half_open_calls=1)
        monitor._circuits["svc"] = cb
        health = ServiceHealth(service_name="svc", status=ServiceStatus.HEALTHY)
        monitor._update_circuit("svc", health)
        assert cb.success_count == 2
        assert cb.half_open_calls == 2
        assert cb.state == CircuitState.HALF_OPEN

    def test_update_circuit_half_open_to_closed(self):
        monitor, _ = self._make_monitor(circuit_half_open_max_calls=3)
        cb = CircuitBreakerState(service="svc", state=CircuitState.HALF_OPEN,
                                  success_count=2, half_open_calls=2)
        monitor._circuits["svc"] = cb
        health = ServiceHealth(service_name="svc", status=ServiceStatus.HEALTHY)
        monitor._update_circuit("svc", health)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0

    def test_update_circuit_half_open_degraded_reopens(self):
        monitor, _ = self._make_monitor()
        cb = CircuitBreakerState(service="svc", state=CircuitState.HALF_OPEN,
                                  success_count=1, half_open_calls=1)
        monitor._circuits["svc"] = cb
        health = ServiceHealth(service_name="svc", status=ServiceStatus.DOWN)
        monitor._update_circuit("svc", health)
        assert cb.state == CircuitState.OPEN
        assert cb.opened_at is not None

    def test_update_circuit_creates_new_if_missing(self):
        monitor, _ = self._make_monitor()
        health = ServiceHealth(service_name="new-svc", status=ServiceStatus.HEALTHY)
        monitor._update_circuit("new-svc", health)
        assert "new-svc" in monitor._circuits
        assert monitor._circuits["new-svc"].state == CircuitState.CLOSED

    def test_get_issues_empty(self):
        monitor, _ = self._make_monitor()
        assert monitor.get_issues() == []

    def test_get_issues_down_service(self):
        monitor, _ = self._make_monitor()
        monitor._service_health["svc"] = ServiceHealth(
            service_name="svc", status=ServiceStatus.DOWN, last_error="Timeout")
        issues = monitor.get_issues()
        assert any("DOWN" in i for i in issues)

    def test_get_issues_degraded_service(self):
        monitor, _ = self._make_monitor()
        monitor._service_health["svc"] = ServiceHealth(
            service_name="svc", status=ServiceStatus.DEGRADED, last_error="High latency")
        issues = monitor.get_issues()
        assert any("DEGRADED" in i for i in issues)

    def test_get_issues_open_circuit(self):
        monitor, _ = self._make_monitor()
        monitor._circuits["svc"] = CircuitBreakerState(service="svc", state=CircuitState.OPEN)
        issues = monitor.get_issues()
        assert any("circuit OPEN" in i for i in issues)

    def test_get_issues_half_open_circuit(self):
        monitor, _ = self._make_monitor()
        monitor._circuits["svc"] = CircuitBreakerState(service="svc", state=CircuitState.HALF_OPEN)
        issues = monitor.get_issues()
        assert any("HALF_OPEN" in i for i in issues)

    def test_get_issues_dlq_messages(self):
        monitor, _ = self._make_monitor()
        monitor._dlq_stats = [DLQStats(queue_name="q1", message_count=5)]
        issues = monitor.get_issues()
        assert any("DLQ" in i for i in issues)

    def test_properties_return_copies(self):
        monitor, _ = self._make_monitor()
        monitor._service_health["svc"] = ServiceHealth(service_name="svc")
        monitor._circuits["svc"] = CircuitBreakerState(service="svc")
        monitor._dlq_stats = [DLQStats(queue_name="q")]
        assert monitor.service_health is not monitor._service_health
        assert monitor.circuits is not monitor._circuits
        assert monitor.dlq_stats is not monitor._dlq_stats

    def test_record_action(self):
        monitor, _ = self._make_monitor()
        action = monitor._record_action("svc", HealingActionType.RESTART,
                                         "test reason", HealingOutcome.SUCCESS)
        assert isinstance(action, HealingAction)
        assert action.service == "svc"
        assert monitor._actions_today == 1
        assert len(monitor._actions) == 1


# =====================================================================
# Healer Tests
# =====================================================================

class TestHealer:
    """Tests for the Healer class."""

    def _make_healer(self, monitor=None, **kwargs):
        settings = _make_settings(**kwargs)
        bus = MagicMock()
        bus.read_dlq_messages = AsyncMock(return_value=[])
        bus.replay_to_queue = AsyncMock(return_value=0)
        bus.publish_healing_event = AsyncMock()
        if monitor is None:
            monitor = MagicMock()
            monitor.service_health = {}
            monitor.circuits = {}
        healer = Healer(settings, bus, monitor)
        return healer, bus, monitor

    def test_triage_discard_high_delivery_count(self):
        healer, _, _ = self._make_healer(dlq_max_replay_attempts=3)
        msg = _make_dlq_message(delivery_count=3)
        assert healer._triage_dlq_message(msg) == "discard"

    def test_triage_discard_high_replay_count_in_metadata(self):
        healer, _, _ = self._make_healer(dlq_max_replay_attempts=3)
        msg = _make_dlq_message(delivery_count=1, metadata={"replay_count": 3})
        assert healer._triage_dlq_message(msg) == "discard"

    def test_triage_discard_poison(self):
        healer, _, _ = self._make_healer()
        msg = _make_dlq_message(dead_letter_reason="Poison message detected")
        assert healer._triage_dlq_message(msg) == "discard"

    def test_triage_discard_malformed(self):
        healer, _, _ = self._make_healer()
        msg = _make_dlq_message(dead_letter_reason="Malformed body")
        assert healer._triage_dlq_message(msg) == "discard"

    def test_triage_skip_circuit_open(self):
        monitor = MagicMock()
        monitor.circuits = {
            "scraper": CircuitBreakerState(service="scraper", state=CircuitState.OPEN)
        }
        healer, _, _ = self._make_healer(monitor=monitor)
        msg = _make_dlq_message(queue_or_topic="scrape-requests")
        assert healer._triage_dlq_message(msg) == "skip"

    def test_triage_replay_default(self):
        monitor = MagicMock()
        monitor.circuits = {}
        healer, _, _ = self._make_healer(monitor=monitor)
        msg = _make_dlq_message(delivery_count=1)
        assert healer._triage_dlq_message(msg) == "replay"

    def test_infer_service_scrape_requests(self):
        assert Healer._infer_service_from_queue("scrape-requests") == "scraper"

    def test_infer_service_reasoning_requests(self):
        assert Healer._infer_service_from_queue("reasoning-requests") == "reasoner"

    def test_infer_service_scrape_complete(self):
        assert Healer._infer_service_from_queue("scrape-complete") == "extractor"

    def test_infer_service_extraction_complete(self):
        assert Healer._infer_service_from_queue("extraction-complete") == "knowledge"

    def test_infer_service_reasoning_complete(self):
        assert Healer._infer_service_from_queue("reasoning-complete") == "orchestrator"

    def test_infer_service_evaluation_complete(self):
        assert Healer._infer_service_from_queue("evaluation-complete") == "orchestrator"

    def test_infer_service_unknown(self):
        assert Healer._infer_service_from_queue("unknown-queue") is None

    def test_infer_service_partial_match(self):
        # "scrape-requests-dlq" should still match "scrape-requests"
        assert Healer._infer_service_from_queue("scrape-requests-dlq") == "scraper"

    def test_scaling_recommendation_scale_up(self):
        healer, _, _ = self._make_healer(scale_up_queue_threshold=100)
        rec = healer._generate_scaling_recommendation("svc", "q1", 200)
        assert rec.recommended_action == "scale_up"
        assert rec.recommended_replicas == min(max(200 // 50, 2), 10)
        assert rec.recommended_replicas == 4

    def test_scaling_recommendation_scale_up_max_replicas(self):
        healer, _, _ = self._make_healer(scale_up_queue_threshold=100)
        rec = healer._generate_scaling_recommendation("svc", "q1", 1000)
        assert rec.recommended_replicas == 10

    def test_scaling_recommendation_scale_down(self):
        healer, _, _ = self._make_healer(scale_down_queue_threshold=5)
        rec = healer._generate_scaling_recommendation("svc", "q1", 3)
        assert rec.recommended_action == "scale_down"
        assert rec.recommended_replicas == 1

    def test_scaling_recommendation_no_change(self):
        healer, _, _ = self._make_healer(scale_up_queue_threshold=100, scale_down_queue_threshold=5)
        rec = healer._generate_scaling_recommendation("svc", "q1", 50)
        assert rec.recommended_action == "no_change"

    def test_scaling_recommendation_at_threshold(self):
        healer, _, _ = self._make_healer(scale_up_queue_threshold=100)
        rec = healer._generate_scaling_recommendation("svc", "q1", 100)
        assert rec.recommended_action == "scale_up"

    @pytest.mark.asyncio
    async def test_heal_service_no_issues(self):
        monitor = MagicMock()
        monitor.service_health = {"scraper": ServiceHealth(service_name="scraper",
                                                           status=ServiceStatus.HEALTHY)}
        monitor.circuits = {}
        healer, bus, _ = self._make_healer(monitor=monitor)
        actions = await healer.heal_service("scraper")
        assert len(actions) == 1
        assert "no issues found" in actions[0].reason

    @pytest.mark.asyncio
    async def test_heal_service_restarts_down(self):
        monitor = MagicMock()
        monitor.service_health = {"scraper": ServiceHealth(service_name="scraper",
                                                           status=ServiceStatus.DOWN)}
        monitor.circuits = {}
        healer, bus, _ = self._make_healer(monitor=monitor)
        healer._restart_service = AsyncMock()
        actions = await healer.heal_service("scraper")
        # Should have restart action
        assert any(a.action_type == HealingActionType.RESTART for a in actions)

    @pytest.mark.asyncio
    async def test_heal_service_replays_dlq(self):
        monitor = MagicMock()
        monitor.service_health = {"scraper": ServiceHealth(service_name="scraper",
                                                           status=ServiceStatus.HEALTHY)}
        monitor.circuits = {}
        healer, bus, _ = self._make_healer(monitor=monitor,
                                           dlq_max_replay_attempts=3)
        # Configure bus to return DLQ messages for scrape-requests
        bus.read_dlq_messages = AsyncMock(
            return_value=[_make_dlq_message(delivery_count=1)]
        )
        bus.replay_to_queue = AsyncMock(return_value=1)
        actions = await healer.heal_service("scraper")
        assert any(a.action_type == HealingActionType.REPLAY for a in actions)

    def test_record_action_appends(self):
        healer, _, _ = self._make_healer()
        a = healer._record_action("svc", HealingActionType.RESTART, "reason",
                                   HealingOutcome.SUCCESS)
        assert len(healer._action_log) == 1
        assert a.service == "svc"

    def test_action_log_returns_copy(self):
        healer, _, _ = self._make_healer()
        healer._record_action("svc", HealingActionType.RESTART, "r", HealingOutcome.SUCCESS)
        log = healer.action_log
        assert log is not healer._action_log
        assert len(log) == 1


# =====================================================================
# FastAPI Endpoint Tests
# =====================================================================

class TestEndpoints:
    """Tests for healer FastAPI endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked globals."""
        _setup_service_path("healer")
        sys.modules["config"] = sys.modules["healer.config"]
        sys.modules["models"] = sys.modules["healer.models"]
        sys.modules["health_monitor"] = sys.modules["healer.health_monitor"]
        # Re-patch healer.Healer for healer.main's `from healer import Healer`
        import healer as _pkg
        _pkg.Healer = Healer
        import healer.main as healer_mod

        mock_monitor = MagicMock()
        mock_monitor.service_health = {
            "scraper": ServiceHealth(service_name="scraper", status=ServiceStatus.HEALTHY),
        }
        mock_monitor.circuits = {
            "scraper": CircuitBreakerState(service="scraper"),
        }
        mock_monitor.dlq_stats = [DLQStats(queue_name="scrape-requests", message_count=2)]
        mock_monitor.get_issues.return_value = []
        mock_monitor.actions_today = 0
        mock_monitor.last_health_check = datetime.now(timezone.utc)
        mock_monitor.last_dlq_scan = datetime.now(timezone.utc)

        mock_healer = MagicMock()
        mock_healer.action_log = []
        mock_healer.heal_service = AsyncMock(return_value=[
            HealingAction(service="scraper", action_type=HealingActionType.RESTART,
                         reason="Manual heal", outcome=HealingOutcome.SUCCESS)
        ])

        healer_mod._monitor = mock_monitor
        healer_mod._healer = mock_healer
        healer_mod._start_time = time.monotonic()
        healer_mod._settings = _make_settings()

        transport = ASGITransport(app=healer_mod.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, mock_monitor, mock_healer

        healer_mod._monitor = None
        healer_mod._healer = None

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        c, _, _ = client
        resp = await c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "healer"

    @pytest.mark.asyncio
    async def test_get_status(self, client):
        c, monitor, healer = client
        resp = await c.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "services_monitored" in data
        assert "uptime_seconds" in data

    @pytest.mark.asyncio
    async def test_get_service_health_list(self, client):
        c, _, _ = client
        resp = await c.get("/health/services")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["service_name"] == "scraper"

    @pytest.mark.asyncio
    async def test_get_service_health_single(self, client):
        c, _, _ = client
        resp = await c.get("/health/services/scraper")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service_name"] == "scraper"

    @pytest.mark.asyncio
    async def test_get_service_health_not_found(self, client):
        c, monitor, _ = client
        resp = await c.get("/health/services/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_heal_service_endpoint(self, client):
        c, _, healer = client
        resp = await c.post("/heal/scraper")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "scraper"
        assert len(data["actions"]) == 1

    @pytest.mark.asyncio
    async def test_get_dlq_stats(self, client):
        c, _, _ = client
        resp = await c.get("/dlq/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_messages"] == 2
        assert len(data["queues"]) == 1

    @pytest.mark.asyncio
    async def test_get_actions(self, client):
        c, _, healer = client
        resp = await c.get("/actions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_actions_with_limit(self, client):
        c, _, healer = client
        healer.action_log = [
            HealingAction(service="svc", action_type=HealingActionType.RESTART,
                         reason=f"reason-{i}", outcome=HealingOutcome.SUCCESS)
            for i in range(10)
        ]
        resp = await c.get("/actions?limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_get_circuits(self, client):
        c, _, _ = client
        resp = await c.get("/circuits")
        assert resp.status_code == 200
        data = resp.json()
        assert "scraper" in data
        assert data["scraper"]["state"] == "closed"
