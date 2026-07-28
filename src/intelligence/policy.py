"""Policy Engine — organizational policies the Supervisor must obey."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

PolicyCheckFn = Callable[..., str]


@dataclass
class Policy:
    name: str
    description: str
    action_pattern: str
    condition: str
    effect: str
    priority: int = 0
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "action_pattern": self.action_pattern,
            "condition": self.condition,
            "effect": self.effect,
            "priority": self.priority,
            "enabled": self.enabled,
        }


@dataclass
class PolicyResult:
    allowed: bool
    policy_name: str
    reason: str
    requires_approval: bool = False
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "policy_name": self.policy_name,
            "reason": self.reason,
            "requires_approval": self.requires_approval,
            "suggested_action": self.suggested_action,
        }


_UTC_NOW_CACHE: str = ""


def _utc_now() -> str:
    global _UTC_NOW_CACHE
    _UTC_NOW_CACHE = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return _UTC_NOW_CACHE


class PolicyEngine:
    def __init__(self) -> None:
        self._policies: list[Policy] = []
        self._load_defaults()

    def _load_defaults(self) -> None:
        self.add_policy(
            Policy(
                name="no-production-restart-business-hours",
                description="Never restart production during business hours (08:00-18:00 Mon-Fri)",
                action_pattern="restart|stop|reboot",
                condition="business_hours AND environment=production",
                effect="deny",
                priority=100,
            )
        )
        self.add_policy(
            Policy(
                name="require-approval-delete-target",
                description="Require approval for deleting monitoring targets",
                action_pattern="delete.*target|remove.*monitor",
                condition="always",
                effect="require_approval",
                priority=90,
            )
        )
        self.add_policy(
            Policy(
                name="max-restart-attempts",
                description="Maximum three restart attempts within one hour",
                action_pattern="restart",
                condition="restart_count >= 3",
                effect="deny",
                priority=80,
            )
        )
        self.add_policy(
            Policy(
                name="require-approval-destructive",
                description="Any destructive action requires human approval",
                action_pattern="*",
                condition="destructive=True",
                effect="require_approval",
                priority=70,
            )
        )
        self.add_policy(
            Policy(
                name="max-retries-policy",
                description="Maximum three retries per action sequence",
                action_pattern="retry|re-run",
                condition="retry_count >= 3",
                effect="deny",
                priority=60,
            )
        )
        self.add_policy(
            Policy(
                name="approval-container-restart",
                description="Container restarts in production require approval",
                action_pattern="restart.*container|container.*restart",
                condition="environment=production",
                effect="require_approval",
                priority=50,
            )
        )

    def add_policy(self, policy: Policy) -> None:
        self._policies.append(policy)
        self._policies.sort(key=lambda p: p.priority, reverse=True)

    def clear_policies(self) -> None:
        self._policies.clear()

    def list_policies(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._policies if p.enabled]

    def check_action(
        self,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> PolicyResult:
        ctx = context or {}
        action_lower = action.lower()

        for policy in self._policies:
            if not policy.enabled:
                continue

            if not self._matches_pattern(action_lower, policy.action_pattern):
                continue

            if not self._evaluate_condition(policy.condition, ctx):
                continue

            if policy.effect == "deny":
                return PolicyResult(
                    allowed=False, policy_name=policy.name, reason=policy.description
                )
            if policy.effect == "require_approval":
                return PolicyResult(
                    allowed=True,
                    policy_name=policy.name,
                    reason=policy.description,
                    requires_approval=True,
                    suggested_action="Request human approval",
                )
            if policy.effect == "allow":
                return PolicyResult(
                    allowed=True, policy_name=policy.name, reason=policy.description
                )

        return PolicyResult(allowed=True, policy_name="default", reason="No matching policies")

    def _matches_pattern(self, action: str, pattern: str) -> bool:
        if pattern == "*":
            return True
        parts = pattern.split(" AND ")
        return all(
            any(re.search(p.strip(), action) for p in part.split(" OR ") if p.strip())
            for part in parts
        )

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        if condition == "always":
            return True

        parts = condition.split(" AND ")
        for part in parts:
            part = part.strip()
            if part == "business_hours":
                now = datetime.now(UTC)
                hour = now.hour
                weekday = now.weekday()
                if weekday >= 5 or hour < 8 or hour >= 18:
                    return False
            elif part.startswith("environment="):
                env = part.split("=")[1].strip().strip("'\"")
                if context.get("environment") != env:
                    return False
            elif ">=" in part:
                key, val = part.split(">=")
                if context.get(key.strip(), 0) < int(val.strip()):
                    return False
            elif ">=" not in part and "=" in part:
                key, val = part.split("=")
                if str(context.get(key.strip(), "")).lower() != val.strip().lower():
                    return False
        return True
