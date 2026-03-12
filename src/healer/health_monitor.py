"""Health monitoring loop for the Healer service.

Periodically checks all service health endpoints, monitors Service Bus
dead-letter queues, tracks error rates and latency trends, and detects
service degradation patterns.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

import httpx
from opentelemetry import trace

from config import HealerSettings
from models import (
    CircuitBreakerState,
    CircuitState,
    DLQStats,
    HealingAction,
    HealingActionType,
    HealingOutcome,
    ServiceHealth,
    ServiceStatus,
)
from service_bus import HealerServiceBus

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Type alias for the check-result tuple
_CheckResult = tuple[str, ServiceHealth]


class HealthMonitor:
    """Monitors all selflearning services and Service Bus queues.

    Responsibilities:
      - Periodically call /health on every service
      - Track latency and error rates in sliding windows
      - Monitor DLQ depths for anomalies
      - Maintain circuit breaker states
      - Emit healing actions when degradation is detected
    """

    def __init__(
        self,
        settings: HealerSettings,
        service_bus: HealerServiceBus,
    ) -> None:
        self._settings = settings
        self._bus = service_bus
        self._running = False

        # Current health snapshots
        self._service_health: dict[str, ServiceHealth] = {}

        # Sliding windows for latency and error tracking
        self._latency_history: dict[str, deque[tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=100)
        )
        self._error_history: dict[str, deque[tuple[float, bool]]] = defaultdict(
            lambda: deque(maxlen=100)
        )

        # Circuit breaker states
        self._circuits: dict[str, CircuitBreakerState] = {}

        # DLQ stats cache
        self._dlq_stats: list[DLQStats] = []

        # Action log
        self._actions: list[HealingAction] = []
        self._actions_today: int = 0
        self._last_day: str = ""

        # Timestamps
        self._last_health_check: datetime | None = None
        self._last_dlq_scan: datetime | None = None

        # HTTP client for health checks
        self._http: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        """Initialise HTTP client and circuit breakers for all services."""
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
        for service_name in self._settings.service_urls:
            self._circuits[service_name] = CircuitBreakerState(service=service_name)
            self._service_health[service_name] = ServiceHealth(
                service_name=service_name,
                endpoint=self._settings.service_urls[service_name],
            )
        logger.info(
            "Health monitor initialised — monitoring %d services",
            len(self._settings.service_urls),
        )

    # ── Loop lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the monitoring loops (health + DLQ)."""
        self._running = True
        asyncio.create_task(self._health_loop(), name="health-check-loop")
        asyncio.create_task(self._dlq_loop(), name="dlq-check-loop")
        logger.info("Health monitoring loops started")

    async def stop(self) -> None:
        """Stop monitoring loops."""
        self._running = False
        if self._http:
            await self._http.aclose()
        logger.info("Health monitoring loops stopped")

    # ── Health check loop ─────────────────────────────────────────────

    async def _health_loop(self) -> None:
        """Periodically check all service /health endpoints."""
        while self._running:
            try:
                with tracer.start_as_current_span("healer.health_check_sweep"):
                    await self._check_all_services()
                    self._last_health_check = datetime.now(timezone.utc)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Health check sweep error: %s", exc, exc_info=True)

            await asyncio.sleep(self._settings.health_check_interval_seconds)

    async def _check_all_services(self) -> None:
        """Check every service endpoint concurrently."""
        tasks = []
        for name, url in self._settings.service_urls.items():
            tasks.append(self._check_service(name, url))
        results: list[_CheckResult] = await asyncio.gather(*tasks, return_exceptions=False)

        # Reset daily counter if day changed
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._last_day:
            self._actions_today = 0
            self._last_day = today

        # Evaluate results and trigger healing if needed
        for service_name, health in results:
            previous = self._service_health.get(service_name)
            self._service_health[service_name] = health

            if previous and previous.status != health.status:
                logger.warning(
                    "Service %s status changed: %s → %s",
                    service_name,
                    previous.status.value,
                    health.status.value,
                )

            # Update circuit breaker
            self._update_circuit(service_name, health)

    async def _check_service(self, name: str, url: str) -> _CheckResult:
        """Check a single service's /health endpoint."""
        health = ServiceHealth(service_name=name, endpoint=url)
        start_ts = time.monotonic()

        try:
            assert self._http is not None
            response = await self._http.get(f"{url}/health")
            latency = (time.monotonic() - start_ts) * 1000

            health.latency_ms = latency
            self._latency_history[name].append((time.time(), latency))

            if response.status_code == 200:
                health.status = ServiceStatus.HEALTHY
                health.consecutive_failures = 0
                self._error_history[name].append((time.time(), False))
            else:
                health.status = ServiceStatus.DEGRADED
                health.last_error = f"HTTP {response.status_code}"
                prev = self._service_health.get(name)
                health.consecutive_failures = (prev.consecutive_failures + 1) if prev else 1
                self._error_history[name].append((time.time(), True))

        except httpx.TimeoutException:
            latency = (time.monotonic() - start_ts) * 1000
            health.latency_ms = latency
            health.status = ServiceStatus.DOWN
            health.last_error = "Timeout"
            prev = self._service_health.get(name)
            health.consecutive_failures = (prev.consecutive_failures + 1) if prev else 1
            self._error_history[name].append((time.time(), True))

        except httpx.ConnectError:
            health.status = ServiceStatus.DOWN
            health.last_error = "Connection refused"
            prev = self._service_health.get(name)
            health.consecutive_failures = (prev.consecutive_failures + 1) if prev else 1
            self._error_history[name].append((time.time(), True))

        except Exception as exc:
            health.status = ServiceStatus.DOWN
            health.last_error = str(exc)
            prev = self._service_health.get(name)
            health.consecutive_failures = (prev.consecutive_failures + 1) if prev else 1
            self._error_history[name].append((time.time(), True))

        # Compute windowed error rate
        window_cutoff = time.time() - self._settings.error_rate_window_seconds
        errors_in_window = [
            is_err
            for ts, is_err in self._error_history[name]
            if ts >= window_cutoff
        ]
        if errors_in_window:
            health.error_count_window = sum(1 for e in errors_in_window if e)
            health.success_count_window = sum(1 for e in errors_in_window if not e)
        else:
            health.error_count_window = 0
            health.success_count_window = 0

        # Compute p95 latency
        latencies_in_window = [
            lat for ts, lat in self._latency_history[name] if ts >= window_cutoff
        ]
        if latencies_in_window:
            sorted_lats = sorted(latencies_in_window)
            p95_idx = int(len(sorted_lats) * 0.95)
            health.latency_p95_ms = sorted_lats[min(p95_idx, len(sorted_lats) - 1)]

        # Check degradation thresholds
        if health.status == ServiceStatus.HEALTHY:
            if health.latency_p95_ms > self._settings.latency_threshold_ms:
                health.status = ServiceStatus.DEGRADED
                health.last_error = f"High latency: p95={health.latency_p95_ms:.0f}ms"
            elif health.error_rate > self._settings.error_rate_threshold:
                health.status = ServiceStatus.DEGRADED
                health.last_error = f"High error rate: {health.error_rate:.1%}"

        health.last_check = datetime.now(timezone.utc)
        return (name, health)

    # ── Circuit breaker ───────────────────────────────────────────────

    def _update_circuit(self, service_name: str, health: ServiceHealth) -> None:
        """Update circuit breaker state based on health check result."""
        circuit = self._circuits.get(service_name)
        if circuit is None:
            circuit = CircuitBreakerState(service=service_name)
            self._circuits[service_name] = circuit

        now = datetime.now(timezone.utc)

        if health.status in (ServiceStatus.HEALTHY,):
            if circuit.state == CircuitState.HALF_OPEN:
                circuit.half_open_calls += 1
                circuit.success_count += 1
                if circuit.success_count >= self._settings.circuit_half_open_max_calls:
                    # Fully recovered — close circuit
                    circuit.state = CircuitState.CLOSED
                    circuit.failure_count = 0
                    circuit.success_count = 0
                    circuit.half_open_calls = 0
                    logger.info("Circuit CLOSED for %s — recovered", service_name)
                    self._record_action(
                        service_name,
                        HealingActionType.CIRCUIT_CLOSE,
                        "Service recovered — circuit closed",
                        HealingOutcome.SUCCESS,
                    )
            elif circuit.state == CircuitState.CLOSED:
                circuit.failure_count = max(0, circuit.failure_count - 1)
                circuit.last_success = now

        elif health.status in (ServiceStatus.DEGRADED, ServiceStatus.DOWN):
            if circuit.state == CircuitState.CLOSED:
                circuit.failure_count += 1
                circuit.last_failure = now
                if circuit.failure_count >= self._settings.circuit_failure_threshold:
                    circuit.state = CircuitState.OPEN
                    circuit.opened_at = now
                    logger.warning(
                        "Circuit OPENED for %s — %d consecutive failures",
                        service_name,
                        circuit.failure_count,
                    )
                    self._record_action(
                        service_name,
                        HealingActionType.CIRCUIT_OPEN,
                        f"Circuit opened after {circuit.failure_count} failures",
                        HealingOutcome.SUCCESS,
                    )
            elif circuit.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if circuit.opened_at:
                    elapsed = (now - circuit.opened_at).total_seconds()
                    if elapsed >= self._settings.circuit_recovery_timeout_seconds:
                        circuit.state = CircuitState.HALF_OPEN
                        circuit.half_open_calls = 0
                        circuit.success_count = 0
                        logger.info("Circuit HALF_OPEN for %s — testing recovery", service_name)
            elif circuit.state == CircuitState.HALF_OPEN:
                # Failed during half-open → back to open
                circuit.state = CircuitState.OPEN
                circuit.opened_at = now
                circuit.half_open_calls = 0
                circuit.success_count = 0
                logger.warning("Circuit re-OPENED for %s — half-open test failed", service_name)

    # ── DLQ monitoring loop ───────────────────────────────────────────

    async def _dlq_loop(self) -> None:
        """Periodically scan DLQs for messages."""
        while self._running:
            try:
                with tracer.start_as_current_span("healer.dlq_scan"):
                    self._dlq_stats = await self._bus.get_all_dlq_stats()
                    self._last_dlq_scan = datetime.now(timezone.utc)

                    total_dlq = sum(s.message_count for s in self._dlq_stats)
                    if total_dlq > 0:
                        logger.info(
                            "DLQ scan: %d total messages across %d queues",
                            total_dlq,
                            len(self._dlq_stats),
                        )
                        for stats in self._dlq_stats:
                            if stats.message_count > 0:
                                logger.warning(
                                    "DLQ %s: %d messages",
                                    stats.queue_name,
                                    stats.message_count,
                                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("DLQ scan error: %s", exc, exc_info=True)

            await asyncio.sleep(self._settings.dlq_check_interval_seconds)

    # ── Action logging ────────────────────────────────────────────────

    def _record_action(
        self,
        service: str,
        action_type: HealingActionType,
        reason: str,
        outcome: HealingOutcome,
        details: dict[str, Any] | None = None,
    ) -> HealingAction:
        """Record a healing action in the action log."""
        action = HealingAction(
            service=service,
            action_type=action_type,
            reason=reason,
            outcome=outcome,
            details=details or {},
        )
        self._actions.append(action)
        self._actions_today += 1
        logger.info(
            "Healing action: %s on %s — %s (outcome=%s)",
            action_type.value,
            service,
            reason,
            outcome.value,
        )
        return action

    # ── Public accessors ──────────────────────────────────────────────

    @property
    def service_health(self) -> dict[str, ServiceHealth]:
        return dict(self._service_health)

    @property
    def circuits(self) -> dict[str, CircuitBreakerState]:
        return dict(self._circuits)

    @property
    def dlq_stats(self) -> list[DLQStats]:
        return list(self._dlq_stats)

    @property
    def actions(self) -> list[HealingAction]:
        return list(self._actions)

    @property
    def actions_today(self) -> int:
        return self._actions_today

    @property
    def last_health_check(self) -> datetime | None:
        return self._last_health_check

    @property
    def last_dlq_scan(self) -> datetime | None:
        return self._last_dlq_scan

    def get_issues(self) -> list[str]:
        """Return a list of current issues."""
        issues: list[str] = []
        for name, health in self._service_health.items():
            if health.status == ServiceStatus.DOWN:
                issues.append(f"{name}: DOWN — {health.last_error}")
            elif health.status == ServiceStatus.DEGRADED:
                issues.append(f"{name}: DEGRADED — {health.last_error}")
        for circuit in self._circuits.values():
            if circuit.state == CircuitState.OPEN:
                issues.append(f"{circuit.service}: circuit OPEN")
            elif circuit.state == CircuitState.HALF_OPEN:
                issues.append(f"{circuit.service}: circuit HALF_OPEN")
        for stats in self._dlq_stats:
            if stats.message_count > 0:
                issues.append(f"DLQ {stats.queue_name}: {stats.message_count} messages")
        return issues
