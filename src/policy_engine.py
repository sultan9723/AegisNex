"""Policy Engine — classifies every autonomous action as Safe, Approval Required, or Forbidden.

Builds on src/intelligence/policy.py and src/intelligence/risk.py with additional
persistence, categorization, and a clean API for the autonomous pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.intelligence.policy import PolicyEngine as _InnerPolicyEngine, Policy
from src.intelligence.risk import RiskEngine, RiskLevel

_logger = logging.getLogger(__name__)


class ActionVerdict(str, Enum):
    SAFE = "safe"
    APPROVAL_REQUIRED = "approval_required"
    FORBIDDEN = "forbidden"


AUTONOMOUS_ACTIONS_SAFE: List[str] = [
    "restart_container",
    "retry_notification",
    "re_run_health_check",
    "restart_monitoring_job",
    "restart_service",
    "retry_failed_task",
    "clear_cache",
    "rotate_logs",
]

AUTONOMOUS_ACTIONS_APPROVAL: List[str] = [
    "delete_container",
    "stop_container",
    "delete_target",
    "disable_monitoring",
    "scale_down_service",
    "update_configuration",
    "rollback_deployment",
]

AUTONOMOUS_ACTIONS_FORBIDDEN: List[str] = [
    "delete_database",
    "delete_volume",
    "delete_cluster",
    "terminate_instance",
    "format_disk",
    "drop_table",
    "shutdown_host",
]

SENSITIVE_TARGET_MARKERS = {"critical", "production", "prod"}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _context_values(context: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for key in ("environment", "env", "criticality", "service_criticality", "tier"):
        value = context.get(key)
        if value is not None:
            values.append(str(value).strip().lower())

    for key in ("tags", "service_tags"):
        values.extend(str(value).strip().lower() for value in _as_list(context.get(key)))

    labels = context.get("labels")
    if isinstance(labels, dict):
        for key, value in labels.items():
            values.append(str(key).strip().lower())
            values.append(str(value).strip().lower())
    elif labels is not None:
        values.extend(str(value).strip().lower() for value in _as_list(labels))

    container = context.get("container")
    if isinstance(container, dict):
        nested = {
            "environment": container.get("environment") or container.get("env"),
            "criticality": container.get("criticality"),
            "tags": container.get("tags"),
            "labels": container.get("labels"),
        }
        values.extend(_context_values(nested))

    return [value for value in values if value]


def _restart_count(context: Dict[str, Any]) -> int:
    for key in ("restart_count", "recent_restart_count", "restart_attempts"):
        try:
            return int(context.get(key, 0))
        except (TypeError, ValueError):
            continue

    container = context.get("container")
    if isinstance(container, dict):
        name = container.get("name")
    else:
        name = container

    history = context.get("restart_history")
    if isinstance(history, dict):
        if isinstance(name, str) and isinstance(history.get(name), dict):
            try:
                return int(history[name].get("attempts", 0))
            except (TypeError, ValueError):
                return 0
        try:
            return int(history.get("attempts", 0))
        except (TypeError, ValueError):
            return 0
    return 0


def _sensitive_target_reason(context: Dict[str, Any]) -> str:
    values = set(_context_values(context))
    matched = sorted(values & SENSITIVE_TARGET_MARKERS)
    if matched:
        return f"Target context is tagged {', '.join(matched)}"
    if _restart_count(context) >= 2:
        return "Target has repeated recent restart attempts"
    return ""


@dataclass
class PolicyEvaluation:
    action: str
    verdict: ActionVerdict
    reason: str
    confidence: float = 1.0
    policy_name: Optional[str] = None
    risk_level: Optional[str] = None
    risk_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "policy_name": self.policy_name,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
        }


class AppPolicyEngine:
    """High-level policy engine for the autonomous pipeline.

    Wraps the existing intelligence/policy and intelligence/risk modules,
    adding action categorization (safe/approval/forbidden) and persistence.
    """

    def __init__(
        self,
        repository: Any = None,
        auto_execute_threshold: float = 0.3,
    ) -> None:
        self._inner = _InnerPolicyEngine()
        self._risk = RiskEngine(auto_execute_threshold=auto_execute_threshold)
        self._repository = repository
        self._load_persisted_policies()

    def _load_persisted_policies(self) -> None:
        if not self._repository:
            return
        try:
            if hasattr(self._repository, "list_policies"):
                for row in self._repository.list_policies():
                    self._inner.add_policy(Policy(
                        name=row.get("name", "custom"),
                        description=row.get("description", ""),
                        action_pattern=row.get("action_pattern", "*"),
                        condition=row.get("condition", "always"),
                        effect=row.get("effect", "deny"),
                        priority=int(row.get("priority", 0)),
                        enabled=bool(row.get("enabled", True)),
                    ))
        except Exception:
            _logger.exception("Failed to load persisted policies")

    def evaluate(self, action: str, context: Optional[Dict[str, Any]] = None) -> PolicyEvaluation:
        ctx = context or {}
        action_lower = action.strip().lower()

        if action_lower in AUTONOMOUS_ACTIONS_FORBIDDEN:
            return PolicyEvaluation(
                action=action,
                verdict=ActionVerdict.FORBIDDEN,
                reason=f"Action '{action}' is classified as forbidden",
                risk_level=RiskLevel.CRITICAL.value,
                risk_score=1.0,
            )

        risk = self._risk.assess_tool(action, ctx)
        inner_result = self._inner.check_action(action, ctx)

        if not inner_result.allowed:
            return PolicyEvaluation(
                action=action,
                verdict=ActionVerdict.FORBIDDEN,
                reason=inner_result.reason,
                policy_name=inner_result.policy_name,
                risk_level=risk.level.value,
                risk_score=risk.score,
            )

        if action_lower in AUTONOMOUS_ACTIONS_APPROVAL:
            return PolicyEvaluation(
                action=action,
                verdict=ActionVerdict.APPROVAL_REQUIRED,
                reason=f"Action '{action}' requires human approval",
                risk_level=risk.level.value,
                risk_score=risk.score,
            )

        if inner_result.requires_approval:
            return PolicyEvaluation(
                action=action,
                verdict=ActionVerdict.APPROVAL_REQUIRED,
                reason=inner_result.reason,
                policy_name=inner_result.policy_name,
                risk_level=risk.level.value,
                risk_score=risk.score,
            )

        context_reason = _sensitive_target_reason(ctx)
        if context_reason:
            return PolicyEvaluation(
                action=action,
                verdict=ActionVerdict.APPROVAL_REQUIRED,
                reason=f"{context_reason}; action '{action}' requires human approval",
                risk_level=risk.level.value,
                risk_score=risk.score,
            )

        if action_lower in AUTONOMOUS_ACTIONS_SAFE:
            return PolicyEvaluation(
                action=action,
                verdict=ActionVerdict.SAFE,
                reason=f"Action '{action}' is classified as safe",
                risk_level=risk.level.value,
                risk_score=risk.score,
            )

        if risk.requires_approval:
            return PolicyEvaluation(
                action=action,
                verdict=ActionVerdict.APPROVAL_REQUIRED,
                reason=f"Risk assessment indicates approval needed (score={risk.score})",
                risk_level=risk.level.value,
                risk_score=risk.score,
            )

        return PolicyEvaluation(
            action=action,
            verdict=ActionVerdict.SAFE,
            reason=f"No policies restrict action '{action}'",
            risk_level=risk.level.value,
            risk_score=risk.score,
        )

    def get_safe_actions(self) -> List[str]:
        return list(AUTONOMOUS_ACTIONS_SAFE)

    def get_approval_actions(self) -> List[str]:
        return list(AUTONOMOUS_ACTIONS_APPROVAL)

    def get_forbidden_actions(self) -> List[str]:
        return list(AUTONOMOUS_ACTIONS_FORBIDDEN)

    def list_policies(self) -> List[Dict[str, Any]]:
        return self._inner.list_policies()
