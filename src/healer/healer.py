"""Healing actions — the immune system of the selflearning platform.

Implements DLQ processing, circuit breaking, service restart, endpoint
failover, prompt tuning analysis, and scaling recommendations.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.appcontainers.aio import ContainerAppsAPIClient
from opentelemetry import trace

from config import HealerSettings
from health_monitor import HealthMonitor
from models import (
    CircuitState,
    DLQMessage,
    HealingAction,
    HealingActionType,
    HealingEvent,
    HealingOutcome,
    PromptTuningResult,
    ScalingRecommendation,
    ServiceStatus,
)
from service_bus import HealerServiceBus

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class Healer:
    """Executes healing actions based on monitoring data.

    Healing categories:
      1. DLQ processing: replay or discard dead-letter messages
      2. Circuit breaking: managed via HealthMonitor, Healer triggers actions
      3. Service restart: call Container Apps management API
      4. Endpoint failover: re-route around degraded AI Foundry models
      5. Prompt tuning: analyse extraction quality and suggest improvements
      6. Scaling: analyse queue depths, recommend scaling changes
    """

    def __init__(
        self,
        settings: HealerSettings,
        service_bus: HealerServiceBus,
        monitor: HealthMonitor,
    ) -> None:
        self._settings = settings
        self._bus = service_bus
        self._monitor = monitor
        self._running = False
        self._credential: DefaultAzureCredential | None = None
        self._container_client: ContainerAppsAPIClient | None = None
        self._http: httpx.AsyncClient | None = None
        self._action_log: list[HealingAction] = []

    async def initialize(self) -> None:
        """Set up Azure management clients."""
        with tracer.start_as_current_span("healer.initialize"):
            self._credential = DefaultAzureCredential()
            if self._settings.subscription_id:
                self._container_client = ContainerAppsAPIClient(
                    credential=self._credential,
                    subscription_id=self._settings.subscription_id,
                )
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
            logger.info("Healer initialized")

    async def start(self) -> None:
        """Start the healing loop."""
        self._running = True
        asyncio.create_task(self._healing_loop(), name="healing-loop")
        logger.info("Healing loop started")

    async def stop(self) -> None:
        """Stop the healing loop."""
        self._running = False
        if self._http:
            await self._http.aclose()
        if self._container_client:
            await self._container_client.close()
        if self._credential:
            await self._credential.close()
        logger.info("Healer stopped")

    # ── Main healing loop ─────────────────────────────────────────────

    async def _healing_loop(self) -> None:
        """Periodically evaluate system state and take healing actions."""
        while self._running:
            try:
                with tracer.start_as_current_span("healer.healing_tick"):
                    await self._healing_tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Healing tick error: %s", exc, exc_info=True)

            await asyncio.sleep(self._settings.health_check_interval_seconds)

    async def _healing_tick(self) -> None:
        """Single healing evaluation cycle."""
        # 1. Process DLQs
        await self._process_all_dlqs()

        # 2. Check for services that need restart
        await self._evaluate_restarts()

        # 3. Generate scaling recommendations
        await self._evaluate_scaling()

        # 4. Evaluate prompt tuning needs
        await self._evaluate_prompt_tuning()

    # ── DLQ processing ────────────────────────────────────────────────

    async def _process_all_dlqs(self) -> None:
        """Scan and process all dead-letter queues."""
        with tracer.start_as_current_span("healer.process_dlqs"):
            for queue_name in self._settings.monitored_queues:
                await self._process_queue_dlq(queue_name)

    async def _process_queue_dlq(self, queue_name: str) -> None:
        """Process dead-letter messages for a single queue."""
        with tracer.start_as_current_span("healer.process_queue_dlq") as span:
            span.set_attribute("queue", queue_name)

            messages = await self._bus.read_dlq_messages(queue_name)
            if not messages:
                return

            logger.info("Processing %d DLQ messages from %s", len(messages), queue_name)

            replayable: list[DLQMessage] = []
            discardable: list[DLQMessage] = []

            for msg in messages:
                decision = self._triage_dlq_message(msg)
                if decision == "replay":
                    replayable.append(msg)
                elif decision == "discard":
                    discardable.append(msg)

            # Replay messages back to the queue
            if replayable:
                replayed = await self._bus.replay_to_queue(queue_name, replayable)
                action = self._record_action(
                    service=queue_name,
                    action_type=HealingActionType.REPLAY,
                    reason=f"Replayed {replayed}/{len(replayable)} DLQ messages",
                    outcome=HealingOutcome.SUCCESS if replayed > 0 else HealingOutcome.FAILED,
                    details={"replayed": replayed, "total": len(replayable)},
                )
                await self._publish_healing_event(action)

            # Log discarded messages
            if discardable:
                action = self._record_action(
                    service=queue_name,
                    action_type=HealingActionType.DLQ_DISCARD,
                    reason=f"Discarded {len(discardable)} DLQ messages (exceeded replay limit or poison)",
                    outcome=HealingOutcome.SUCCESS,
                    details={
                        "discarded": len(discardable),
                        "reasons": [m.dead_letter_reason for m in discardable[:5]],
                    },
                )
                await self._publish_healing_event(action)

    def _triage_dlq_message(self, msg: DLQMessage) -> str:
        """Decide whether to replay or discard a DLQ message.

        Returns: 'replay', 'discard', or 'skip'
        """
        # Too many retries → discard
        if msg.delivery_count >= self._settings.dlq_max_replay_attempts:
            logger.info(
                "DLQ message %s exceeded max deliveries (%d) — discard",
                msg.message_id,
                msg.delivery_count,
            )
            return "discard"

        # Check replay count from metadata
        replay_count = msg.metadata.get("replay_count", 0)
        if isinstance(replay_count, int) and replay_count >= self._settings.dlq_max_replay_attempts:
            return "discard"

        # Check for known poison message patterns
        reason = (msg.dead_letter_reason or "").lower()
        if "poison" in reason or "malformed" in reason:
            return "discard"

        # Check if the target service's circuit is open
        # If the circuit is open, skip replay until service recovers
        service_name = self._infer_service_from_queue(msg.queue_or_topic)
        if service_name:
            circuit = self._monitor.circuits.get(service_name)
            if circuit and circuit.state == CircuitState.OPEN:
                logger.debug(
                    "Circuit open for %s — skipping replay of %s",
                    service_name,
                    msg.message_id,
                )
                return "skip"

        return "replay"

    @staticmethod
    def _infer_service_from_queue(queue_name: str) -> str | None:
        """Infer which service processes a given queue."""
        mapping = {
            "scrape-requests": "scraper",
            "reasoning-requests": "reasoner",
            "scrape-complete": "extractor",
            "extraction-complete": "knowledge",
            "reasoning-complete": "orchestrator",
            "evaluation-complete": "orchestrator",
        }
        for key, service in mapping.items():
            if key in queue_name:
                return service
        return None

    # ── Service restart ───────────────────────────────────────────────

    async def _evaluate_restarts(self) -> None:
        """Check if any services need to be restarted."""
        with tracer.start_as_current_span("healer.evaluate_restarts"):
            for name, health in self._monitor.service_health.items():
                if health.status == ServiceStatus.DOWN and health.consecutive_failures >= 3:
                    circuit = self._monitor.circuits.get(name)
                    if circuit and circuit.state == CircuitState.OPEN:
                        await self._restart_service(name)

    async def _restart_service(self, service_name: str) -> None:
        """Restart a Container App service via Azure management API."""
        with tracer.start_as_current_span("healer.restart_service") as span:
            span.set_attribute("service", service_name)

            if not self._container_client or not self._settings.resource_group:
                logger.warning(
                    "Cannot restart %s — Container Apps client not configured",
                    service_name,
                )
                self._record_action(
                    service=service_name,
                    action_type=HealingActionType.RESTART,
                    reason="Service DOWN with open circuit — restart needed",
                    outcome=HealingOutcome.FAILED,
                    details={"error": "Container Apps client not configured"},
                )
                return

            try:
                # Get current revision
                app = await self._container_client.container_apps.get(
                    resource_group_name=self._settings.resource_group,
                    container_app_name=f"selflearning-{service_name}",
                )

                if app and app.template:
                    # Restart by creating a new revision (updating a label forces restart)
                    revisions = self._container_client.container_apps_revisions.list_revisions(
                        resource_group_name=self._settings.resource_group,
                        container_app_name=f"selflearning-{service_name}",
                    )
                    active_revision = None
                    async for rev in revisions:
                        if rev.active:
                            active_revision = rev.name
                            break

                    if active_revision:
                        await self._container_client.container_apps_revisions.restart_revision(
                            resource_group_name=self._settings.resource_group,
                            container_app_name=f"selflearning-{service_name}",
                            revision_name=active_revision,
                        )
                        logger.info("Restarted service %s (revision=%s)", service_name, active_revision)
                        action = self._record_action(
                            service=service_name,
                            action_type=HealingActionType.RESTART,
                            reason=f"Service DOWN — restarted revision {active_revision}",
                            outcome=HealingOutcome.SUCCESS,
                            details={"revision": active_revision},
                        )
                        await self._publish_healing_event(action)
                        return

                logger.warning("No active revision found for %s", service_name)
                self._record_action(
                    service=service_name,
                    action_type=HealingActionType.RESTART,
                    reason="No active revision found",
                    outcome=HealingOutcome.FAILED,
                )

            except Exception as exc:
                logger.error(
                    "Failed to restart %s: %s", service_name, exc, exc_info=True
                )
                self._record_action(
                    service=service_name,
                    action_type=HealingActionType.RESTART,
                    reason=f"Restart failed: {exc}",
                    outcome=HealingOutcome.FAILED,
                    details={"error": str(exc)},
                )

    # ── Endpoint failover ─────────────────────────────────────────────

    async def failover_endpoint(
        self, service_name: str, primary_endpoint: str, backup_endpoint: str
    ) -> HealingAction:
        """Switch a service from a degraded endpoint to a backup.

        This is for AI Foundry model endpoints — if the primary model
        endpoint degrades, route to the backup.
        """
        with tracer.start_as_current_span("healer.failover_endpoint") as span:
            span.set_attribute("service", service_name)
            span.set_attribute("primary", primary_endpoint)
            span.set_attribute("backup", backup_endpoint)

            logger.info(
                "Failover for %s: %s → %s",
                service_name,
                primary_endpoint,
                backup_endpoint,
            )

            # Notify the service to switch endpoints via its API
            try:
                assert self._http is not None
                service_url = self._settings.service_urls.get(service_name, "")
                if service_url:
                    response = await self._http.post(
                        f"{service_url}/config/endpoint",
                        json={
                            "endpoint": backup_endpoint,
                            "reason": "failover",
                            "initiated_by": "healer",
                        },
                    )
                    if response.status_code in (200, 202):
                        action = self._record_action(
                            service=service_name,
                            action_type=HealingActionType.FAILOVER,
                            reason=f"Endpoint failover: {primary_endpoint} → {backup_endpoint}",
                            outcome=HealingOutcome.SUCCESS,
                            details={
                                "primary": primary_endpoint,
                                "backup": backup_endpoint,
                            },
                        )
                        await self._publish_healing_event(action)
                        return action

                action = self._record_action(
                    service=service_name,
                    action_type=HealingActionType.FAILOVER,
                    reason=f"Failover attempted but service unresponsive",
                    outcome=HealingOutcome.FAILED,
                )
                return action

            except Exception as exc:
                logger.error(
                    "Failover failed for %s: %s", service_name, exc, exc_info=True
                )
                action = self._record_action(
                    service=service_name,
                    action_type=HealingActionType.FAILOVER,
                    reason=f"Failover failed: {exc}",
                    outcome=HealingOutcome.FAILED,
                    details={"error": str(exc)},
                )
                return action

    # ── Prompt tuning analysis ────────────────────────────────────────

    async def _evaluate_prompt_tuning(self) -> None:
        """Analyse extraction quality and suggest prompt improvements.

        Only runs when the extractor service is healthy but quality metrics
        from the evaluator suggest extraction issues.
        """
        with tracer.start_as_current_span("healer.evaluate_prompt_tuning"):
            extractor_health = self._monitor.service_health.get("extractor")
            if not extractor_health or extractor_health.status != ServiceStatus.HEALTHY:
                return

            evaluator_health = self._monitor.service_health.get("evaluator")
            if not evaluator_health or evaluator_health.status != ServiceStatus.HEALTHY:
                return

            # Check extraction quality via evaluator API
            try:
                assert self._http is not None
                response = await self._http.get(
                    f"{self._settings.service_urls.get('evaluator', '')}/metrics/extraction"
                )
                if response.status_code != 200:
                    return

                metrics = response.json()
                quality = metrics.get("extraction_quality", 1.0)

                if quality < 0.6:
                    logger.warning(
                        "Extraction quality low (%.2f) — suggesting prompt tuning",
                        quality,
                    )
                    result = PromptTuningResult(
                        service="extractor",
                        quality_before=quality,
                        suggested_changes=[
                            "Add more specific entity extraction examples",
                            "Increase extraction temperature for creative content",
                            "Add domain-specific terminology guidance",
                        ],
                        analysis=f"Extraction quality at {quality:.2f}, below threshold of 0.6",
                    )
                    action = self._record_action(
                        service="extractor",
                        action_type=HealingActionType.PROMPT_TUNE,
                        reason=f"Low extraction quality ({quality:.2f})",
                        outcome=HealingOutcome.PENDING,
                        details=result.model_dump(mode="json"),
                    )
                    await self._publish_healing_event(action)

            except Exception as exc:
                logger.debug("Prompt tuning check failed: %s", exc)

    # ── Scaling analysis ──────────────────────────────────────────────

    async def _evaluate_scaling(self) -> None:
        """Analyse queue depths and generate scaling recommendations."""
        with tracer.start_as_current_span("healer.evaluate_scaling"):
            for queue_name in self._settings.monitored_queues:
                depth = await self._bus.get_queue_depth(queue_name)
                if depth < 0:
                    continue

                service_name = self._infer_service_from_queue(queue_name) or queue_name
                recommendation = self._generate_scaling_recommendation(
                    service_name, queue_name, depth
                )

                if recommendation.recommended_action != "no_change":
                    logger.info(
                        "Scaling recommendation for %s: %s (depth=%d)",
                        service_name,
                        recommendation.recommended_action,
                        depth,
                    )
                    action = self._record_action(
                        service=service_name,
                        action_type=HealingActionType.SCALE,
                        reason=recommendation.reason,
                        outcome=HealingOutcome.PENDING,
                        details=recommendation.model_dump(mode="json"),
                    )
                    await self._publish_healing_event(action)

    def _generate_scaling_recommendation(
        self, service_name: str, queue_name: str, depth: int
    ) -> ScalingRecommendation:
        """Generate a scaling recommendation based on queue depth."""
        if depth >= self._settings.scale_up_queue_threshold:
            # Estimate replicas: 1 per 50 messages, min 2, max 10
            replicas = min(max(depth // 50, 2), 10)
            return ScalingRecommendation(
                service=service_name,
                current_queue_depth=depth,
                recommended_action="scale_up",
                recommended_replicas=replicas,
                reason=f"Queue {queue_name} depth ({depth}) exceeds threshold ({self._settings.scale_up_queue_threshold})",
            )
        elif depth <= self._settings.scale_down_queue_threshold:
            return ScalingRecommendation(
                service=service_name,
                current_queue_depth=depth,
                recommended_action="scale_down",
                recommended_replicas=1,
                reason=f"Queue {queue_name} depth ({depth}) below threshold — scale down",
            )
        return ScalingRecommendation(
            service=service_name,
            current_queue_depth=depth,
            recommended_action="no_change",
            reason=f"Queue {queue_name} depth ({depth}) within normal range",
        )

    # ── Healing event publishing ──────────────────────────────────────

    async def _publish_healing_event(self, action: HealingAction) -> None:
        """Publish a healing event for the action taken."""
        try:
            event = HealingEvent(
                event_type=action.action_type,
                service=action.service,
                details=action.details,
                action_taken=action.reason,
                outcome=action.outcome,
            )
            await self._bus.publish_healing_event(event)
        except Exception as exc:
            logger.error("Failed to publish healing event: %s", exc, exc_info=True)

    # ── Manual healing trigger ────────────────────────────────────────

    async def heal_service(self, service_name: str) -> list[HealingAction]:
        """Manually trigger healing for a specific service.

        Runs all applicable healing actions:
          1. Check service health
          2. Process DLQs related to this service
          3. Restart if DOWN
          4. Generate scaling recommendation
        """
        with tracer.start_as_current_span("healer.manual_heal") as span:
            span.set_attribute("service", service_name)
            actions: list[HealingAction] = []

            # Process relevant DLQs
            for queue_name in self._settings.monitored_queues:
                inferred = self._infer_service_from_queue(queue_name)
                if inferred == service_name:
                    messages = await self._bus.read_dlq_messages(queue_name)
                    if messages:
                        replayable = [
                            m for m in messages if self._triage_dlq_message(m) == "replay"
                        ]
                        if replayable:
                            replayed = await self._bus.replay_to_queue(queue_name, replayable)
                            action = self._record_action(
                                service=service_name,
                                action_type=HealingActionType.REPLAY,
                                reason=f"Manual heal: replayed {replayed} DLQ messages from {queue_name}",
                                outcome=HealingOutcome.SUCCESS if replayed > 0 else HealingOutcome.FAILED,
                            )
                            actions.append(action)

            # Restart if DOWN
            health = self._monitor.service_health.get(service_name)
            if health and health.status == ServiceStatus.DOWN:
                await self._restart_service(service_name)
                actions.append(
                    self._record_action(
                        service=service_name,
                        action_type=HealingActionType.RESTART,
                        reason="Manual heal: service DOWN",
                        outcome=HealingOutcome.PENDING,
                    )
                )

            if not actions:
                actions.append(
                    self._record_action(
                        service=service_name,
                        action_type=HealingActionType.RESTART,
                        reason=f"Manual heal: no issues found for {service_name}",
                        outcome=HealingOutcome.SUCCESS,
                    )
                )

            return actions

    # ── Action recording ──────────────────────────────────────────────

    def _record_action(
        self,
        service: str,
        action_type: HealingActionType,
        reason: str,
        outcome: HealingOutcome,
        details: dict[str, Any] | None = None,
    ) -> HealingAction:
        """Record a healing action."""
        action = HealingAction(
            service=service,
            action_type=action_type,
            reason=reason,
            outcome=outcome,
            details=details or {},
        )
        self._action_log.append(action)
        logger.info(
            "Healing action recorded: %s on %s — %s",
            action_type.value,
            service,
            reason,
        )
        return action

    @property
    def action_log(self) -> list[HealingAction]:
        return list(self._action_log)
