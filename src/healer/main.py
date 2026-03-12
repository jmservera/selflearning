"""Healer Service — FastAPI application.

The healer is the self-healing immune system for the selflearning platform.
It monitors all services, processes dead-letter queues, manages circuit
breakers, restarts failed services, and analyses quality for prompt tuning.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from pydantic import BaseModel

from config import HealerSettings, get_settings
from healer import Healer
from health_monitor import HealthMonitor
from models import (
    CircuitState,
    DLQStats,
    HealerStatus,
    HealingAction,
    HealingActionType,
    HealingOutcome,
    ServiceHealth,
    ServiceStatus,
)
from service_bus import HealerServiceBus

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# ── Global singletons ────────────────────────────────────────────────

_settings: HealerSettings | None = None
_bus: HealerServiceBus | None = None
_monitor: HealthMonitor | None = None
_healer: Healer | None = None
_start_time: float = 0.0


# ── Request / response schemas ────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime
    uptime_seconds: float


class ServiceHealthResponse(BaseModel):
    service_name: str
    status: ServiceStatus
    latency_ms: float
    latency_p95_ms: float
    error_rate: float
    consecutive_failures: int
    circuit_state: CircuitState
    last_error: str | None
    last_check: datetime


class HealResponse(BaseModel):
    service: str
    actions: list[dict[str, Any]]
    message: str


class DLQStatsResponse(BaseModel):
    total_messages: int
    queues: list[DLQStats]


# ── Lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    global _settings, _bus, _monitor, _healer, _start_time

    _start_time = time.monotonic()
    _settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, _settings.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )

    # Configure OpenTelemetry
    if _settings.applicationinsights_connection_string:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(
                connection_string=_settings.applicationinsights_connection_string,
                service_name=_settings.otel_service_name,
            )
            logger.info("OpenTelemetry configured with Azure Monitor")
        except Exception as exc:
            logger.warning("Failed to configure Azure Monitor: %s", exc)

    # Initialise infrastructure
    _bus = HealerServiceBus(_settings)
    try:
        await _bus.initialize()
    except Exception as exc:
        logger.error("Service Bus init failed (non-fatal): %s", exc)

    _monitor = HealthMonitor(_settings, _bus)
    await _monitor.initialize()

    _healer = Healer(_settings, _bus, _monitor)
    await _healer.initialize()

    # Start monitoring and healing loops
    await _monitor.start()
    await _healer.start()
    logger.info("Healer service started — monitoring and healing active")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────
    logger.info("Healer shutting down")
    if _healer:
        await _healer.stop()
    if _monitor:
        await _monitor.stop()
    if _bus:
        await _bus.close()
    logger.info("Healer shutdown complete")


# ── Application ───────────────────────────────────────────────────────

app = FastAPI(
    title="selflearning Healer",
    description="Self-healing immune system — monitors, detects, and recovers from failures",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Health ────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(
        status="healthy",
        service="healer",
        timestamp=datetime.now(timezone.utc),
        uptime_seconds=time.monotonic() - _start_time,
    )


# ── Status ────────────────────────────────────────────────────────────

@app.get("/status", response_model=HealerStatus, tags=["status"])
async def get_status() -> HealerStatus:
    """Overall healer status including recent actions and current issues."""
    assert _monitor is not None and _healer is not None

    service_statuses = {
        name: health.status
        for name, health in _monitor.service_health.items()
    }
    circuit_states = {
        name: cb.state
        for name, cb in _monitor.circuits.items()
    }
    dlq_total = sum(s.message_count for s in _monitor.dlq_stats)

    return HealerStatus(
        services_monitored=list(_monitor.service_health.keys()),
        service_statuses=service_statuses,
        circuit_states=circuit_states,
        actions_taken_today=_monitor.actions_today,
        actions_taken_total=len(_healer.action_log),
        current_issues=_monitor.get_issues(),
        dlq_total_messages=dlq_total,
        uptime_seconds=time.monotonic() - _start_time,
        last_health_check=_monitor.last_health_check,
        last_dlq_scan=_monitor.last_dlq_scan,
    )


# ── Service health ────────────────────────────────────────────────────

@app.get(
    "/health/services",
    response_model=list[ServiceHealthResponse],
    tags=["monitoring"],
)
async def get_service_health() -> list[ServiceHealthResponse]:
    """Health status of all monitored services."""
    assert _monitor is not None

    results: list[ServiceHealthResponse] = []
    for name, health in _monitor.service_health.items():
        circuit = _monitor.circuits.get(name)
        results.append(
            ServiceHealthResponse(
                service_name=name,
                status=health.status,
                latency_ms=health.latency_ms,
                latency_p95_ms=health.latency_p95_ms,
                error_rate=health.error_rate,
                consecutive_failures=health.consecutive_failures,
                circuit_state=circuit.state if circuit else CircuitState.CLOSED,
                last_error=health.last_error,
                last_check=health.last_check,
            )
        )
    return results


@app.get(
    "/health/services/{service}",
    response_model=ServiceHealthResponse,
    tags=["monitoring"],
)
async def get_single_service_health(service: str) -> ServiceHealthResponse:
    """Health status of a specific service."""
    assert _monitor is not None

    health = _monitor.service_health.get(service)
    if health is None:
        raise HTTPException(status_code=404, detail=f"Service '{service}' not monitored")

    circuit = _monitor.circuits.get(service)
    return ServiceHealthResponse(
        service_name=service,
        status=health.status,
        latency_ms=health.latency_ms,
        latency_p95_ms=health.latency_p95_ms,
        error_rate=health.error_rate,
        consecutive_failures=health.consecutive_failures,
        circuit_state=circuit.state if circuit else CircuitState.CLOSED,
        last_error=health.last_error,
        last_check=health.last_check,
    )


# ── Healing ───────────────────────────────────────────────────────────

@app.post("/heal/{service}", response_model=HealResponse, tags=["healing"])
async def heal_service(service: str) -> HealResponse:
    """Manually trigger healing for a specific service."""
    assert _healer is not None

    with tracer.start_as_current_span("api.heal_service"):
        actions = await _healer.heal_service(service)
        return HealResponse(
            service=service,
            actions=[a.model_dump(mode="json") for a in actions],
            message=f"Executed {len(actions)} healing actions for {service}",
        )


# ── DLQ statistics ────────────────────────────────────────────────────

@app.get("/dlq/stats", response_model=DLQStatsResponse, tags=["monitoring"])
async def get_dlq_stats() -> DLQStatsResponse:
    """Dead-letter queue statistics across all monitored queues."""
    assert _monitor is not None

    stats = _monitor.dlq_stats
    total = sum(s.message_count for s in stats)
    return DLQStatsResponse(total_messages=total, queues=stats)


# ── Action history ────────────────────────────────────────────────────

@app.get("/actions", response_model=list[dict[str, Any]], tags=["monitoring"])
async def get_recent_actions(limit: int = 50) -> list[dict[str, Any]]:
    """Recent healing actions taken."""
    assert _healer is not None

    actions = _healer.action_log[-limit:]
    return [a.model_dump(mode="json") for a in reversed(actions)]


# ── Circuit breakers ──────────────────────────────────────────────────

@app.get("/circuits", tags=["monitoring"])
async def get_circuits() -> dict[str, dict[str, Any]]:
    """Current circuit breaker states for all services."""
    assert _monitor is not None

    return {
        name: cb.model_dump(mode="json")
        for name, cb in _monitor.circuits.items()
    }
