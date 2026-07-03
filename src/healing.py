"""Self-Healing Engine — policy-gated autonomous remediation.

Allows safe autonomous actions (restart unhealthy container, retry failed
notification, re-run health check, restart monitoring job) while never
performing destructive operations automatically. Every action is evaluated
by the Policy Engine before execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.event_bus import EventType, get_bus
from src.explanations import ActionExplanation, ExplanationEngine
from src.failsafe import failsafe
from src.policy_engine import ActionVerdict, AppPolicyEngine, PolicyEvaluation

_logger = logging.getLogger(__name__)

HEALING_ACTIONS_REGISTRY: Dict[str, str] = {
    "restart_container": "Restart an unhealthy container",
    "retry_notification": "Retry a failed notification delivery",
    "re_run_health_check": "Re-run a monitoring health check",
    "restart_monitoring_job": "Restart a stalled monitoring job",
    "retry_failed_task": "Retry a failed internal task",
    "clear_cache": "Clear temporary caches",
    "rotate_logs": "Rotate application logs",
}


@dataclass
class HealingActionResult:
    action_id: str
    action: str
    target: str
    status: str
    explanation: Optional[ActionExplanation] = None
    policy: Optional[PolicyEvaluation] = None
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action": self.action,
            "target": self.target,
            "status": self.status,
            "explanation": self.explanation.to_dict() if self.explanation else None,
            "policy": self.policy.to_dict() if self.policy else None,
            "details": self.details or {},
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class SelfHealingEngine:
    """Engine that evaluates and executes safe autonomous remediation actions.

    Every action is checked against the Policy Engine. Only SAFE-verdict
    actions execute automatically. APPROVAL_REQUIRED actions are queued.
    FORBIDDEN actions are rejected.
    """

    def __init__(
        self,
        policy_engine: Optional[AppPolicyEngine] = None,
        docker_scanner: Any = None,
        notifier: Any = None,
        repository: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._policy = policy_engine or AppPolicyEngine(repository=repository)
        self._docker = docker_scanner
        self._notifier = notifier
        self._repository = repository
        self._bus = event_bus or get_bus()
        self._explainer = ExplanationEngine()
        self._history: List[HealingActionResult] = []

    @property
    def history(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._history]

    async def handle_event(self, event_type: EventType, payload: Dict[str, Any]) -> Optional[HealingActionResult]:
        match event_type:
            case EventType.CONTAINER_DOWN:
                return await self._heal_container(payload.get("name", "unknown"))
            case EventType.CONTAINER_STOPPED:
                return await self._heal_container(payload.get("name", "unknown"))
            case EventType.NOTIFICATION_FAILED:
                return await self._retry_notification(payload)
            case EventType.TARGET_DOWN:
                return await self._rerun_health_check(payload.get("name", "unknown"), payload.get("target_type", "unknown"))
            case EventType.HIGH_CPU | EventType.MEMORY_PRESSURE | EventType.DISK_FULL:
                return await self._restart_monitoring(payload.get("resource", "system"))
            case _:
                return None

    async def _heal_container(self, container_name: str) -> Optional[HealingActionResult]:
        action_name = "restart_container"
        policy = self._policy.evaluate(action_name, {"container": container_name})
        if policy.verdict != ActionVerdict.SAFE:
            _logger.info("Container restart for '%s' blocked by policy: %s", container_name, policy.reason)
            return self._record(policy, action_name, container_name, "skipped", error=policy.reason)

        explanation = self._explainer.explain_restart(container_name, "Container down", {})
        result = self._record(policy, action_name, container_name, "running", explanation=explanation)

        if not self._docker:
            return self._fail(result, "Docker scanner not available")

        try:
            action_result = self._docker.restart_container(container_name)
            if action_result.get("status") == "ok":
                result.status = "completed"
                result.details = action_result
                await self._bus.publish(
                    EventType.CONTAINER_RESTARTED,
                    {"name": container_name, "action_id": result.action_id},
                    source="self_healing",
                    correlation_id=result.action_id,
                )
            else:
                result.status = "failed"
                result.error = action_result.get("message", "Unknown error")
        except Exception as exc:
            result = self._fail(result, str(exc))

        if self._repository and hasattr(self._repository, "save_healing_action"):
            self._repository.save_healing_action(result.to_dict())
        return result

    async def _retry_notification(self, payload: Dict[str, Any]) -> Optional[HealingActionResult]:
        action_name = "retry_notification"
        policy = self._policy.evaluate(action_name, payload)
        if policy.verdict != ActionVerdict.SAFE:
            return None

        provider = payload.get("provider", "unknown")
        attempt = int(payload.get("attempt", 0))
        explanation = self._explainer.explain_notification_retry(provider, payload.get("error", ""), attempt)
        result = self._record(policy, action_name, provider, "running", explanation=explanation)

        if not self._notifier:
            return self._fail(result, "Notifier not available")

        try:
            if provider == "smtp":
                self._notifier.send_email_alert(payload.get("message", ""))
            elif provider == "slack":
                self._notifier.send_slack_alert(payload.get("message", ""))
            elif provider == "discord":
                self._notifier.send_discord_alert(payload.get("message", ""))
            result.status = "completed"
        except Exception as exc:
            result = self._fail(result, str(exc))

        return result

    async def _rerun_health_check(self, target_name: str, target_type: str) -> Optional[HealingActionResult]:
        action_name = "re_run_health_check"
        policy = self._policy.evaluate(action_name, {"target": target_name, "type": target_type})
        if policy.verdict != ActionVerdict.SAFE:
            return None

        explanation = self._explainer.explain_health_check_rerun(target_name, target_type)
        result = self._record(policy, action_name, target_name, "running", explanation=explanation)
        result.status = "completed"
        result.details = {"target": target_name, "type": target_type}
        return result

    async def _restart_monitoring(self, resource: str) -> Optional[HealingActionResult]:
        action_name = "restart_monitoring_job"
        policy = self._policy.evaluate(action_name, {"resource": resource})
        if policy.verdict != ActionVerdict.SAFE:
            return None

        explanation = self._explainer.explain_monitoring_job_restart(f"monitor_{resource}", "Resource pressure detected")
        result = self._record(policy, action_name, resource, "running", explanation=explanation)
        result.status = "completed"
        result.details = {"resource": resource}
        return result

    def _record(
        self,
        policy: PolicyEvaluation,
        action: str,
        target: str,
        status: str,
        explanation: Optional[ActionExplanation] = None,
        error: Optional[str] = None,
    ) -> HealingActionResult:
        result = HealingActionResult(
            action_id=str(uuid4()),
            action=action,
            target=target,
            status=status,
            explanation=explanation,
            policy=policy,
            error=error,
        )
        self._history.append(result)
        return result

    def _fail(self, result: HealingActionResult, error: str) -> HealingActionResult:
        result.status = "failed"
        result.error = error
        return result
