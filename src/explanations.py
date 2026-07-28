"""AI Explanation Generator — provides transparent reasoning for every autonomous action.

Every autonomous action includes:
- Why the action was taken
- Evidence that led to the decision
- Confidence level
- Alternative actions considered
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionExplanation:
    action: str
    why: str
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    risk_level: str | None = None
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "why": self.why,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "risk_level": self.risk_level,
            "duration_ms": self.duration_ms,
        }


class ExplanationEngine:
    """Generates structured explanations for autonomous actions."""

    def explain_remediation(
        self,
        action: str,
        incident_type: str,
        service_name: str,
        evidence: list[str],
        confidence: float,
        alternatives: list[str] | None = None,
        risk_level: str | None = None,
    ) -> ActionExplanation:
        return ActionExplanation(
            action=action,
            why=self._why_remediation(action, incident_type, service_name),
            evidence=evidence,
            confidence=confidence,
            alternatives=self._build_alternatives(action, alternatives),
            risk_level=risk_level,
        )

    def explain_restart(
        self, service_name: str, reason: str, health_data: dict[str, Any]
    ) -> ActionExplanation:
        evidence = [
            f"Service '{service_name}' reported unhealthy status",
            f"Reason: {reason}",
        ]
        if health_data.get("health_checks"):
            for check in health_data["health_checks"]:
                if not check.get("healthy", True):
                    evidence.append(
                        f"Health check '{check.get('name', '?')}' failed: {check.get('message', '')}"
                    )

        return ActionExplanation(
            action="restart_container",
            why=f"Container '{service_name}' is unhealthy — automatic restart initiated to restore service",
            evidence=evidence,
            confidence=0.85,
            alternatives=[
                {
                    "action": "manual_inspection",
                    "reason": "Slower but allows human analysis before action",
                },
                {
                    "action": "escalate_to_operator",
                    "reason": "Recommended if restart cooldown is active",
                },
            ],
            risk_level="low",
        )

    def explain_notification_retry(
        self, provider: str, error: str, attempt: int
    ) -> ActionExplanation:
        return ActionExplanation(
            action="retry_notification",
            why=f"Notification via '{provider}' failed on attempt {attempt}: {error}",
            evidence=[f"Provider: {provider}", f"Error: {error}", f"Attempt: {attempt}"],
            confidence=0.7,
            alternatives=[
                {"action": "fallback_provider", "reason": "Try alternate notification channel"},
                {"action": "silence", "reason": "Accept notification loss"},
            ],
            risk_level="none",
        )

    def explain_health_check_rerun(self, target_name: str, target_type: str) -> ActionExplanation:
        return ActionExplanation(
            action="re_run_health_check",
            why=f"Monitoring target '{target_name}' ({target_type}) previously failed — re-running to confirm status",
            evidence=[f"Target: {target_name}", f"Type: {target_type}"],
            confidence=0.9,
            alternatives=[
                {
                    "action": "escalate_to_incident",
                    "reason": "Treat as confirmed failure immediately",
                },
            ],
            risk_level="none",
        )

    def explain_monitoring_job_restart(self, job_name: str, error: str) -> ActionExplanation:
        return ActionExplanation(
            action="restart_monitoring_job",
            why=f"Monitoring job '{job_name}' failed with error: {error}",
            evidence=[f"Job: {job_name}", f"Error: {error}"],
            confidence=0.8,
            alternatives=[
                {"action": "escalate_to_operator", "reason": "Let operator investigate root cause"},
            ],
            risk_level="low",
        )

    def explain_verification(self, action: str, success: bool, details: str) -> ActionExplanation:
        return ActionExplanation(
            action=f"verify_{action}",
            why=details,
            evidence=[f"Action: {action}", f"Success: {success}"],
            confidence=0.95 if success else 0.5,
            risk_level="none",
        )

    def _why_remediation(self, action: str, incident_type: str, service_name: str) -> str:
        templates = {
            "restart_container": f"Container '{service_name}' triggered '{incident_type}' — restarting to restore healthy state",
            "retry_notification": f"Notification delivery failed for incident on '{service_name}' — retrying to ensure alert reaches operator",
            "re_run_health_check": f"Target '{service_name}' showed '{incident_type}' — re-running to confirm if transient",
            "restart_monitoring_job": f"Monitoring job for '{service_name}' stopped — restarting to maintain observability",
        }
        return templates.get(
            action,
            f"Autonomous action '{action}' triggered by '{incident_type}' on '{service_name}'",
        )

    def _build_alternatives(self, action: str, custom: list[str] | None) -> list[dict[str, Any]]:
        if custom:
            return [{"action": c, "reason": "Considered alternative"} for c in custom]
        return [
            {"action": "escalate_to_operator", "reason": "Let human operator handle the situation"},
            {"action": "monitor_only", "reason": "Take no action, continue monitoring"},
        ]
