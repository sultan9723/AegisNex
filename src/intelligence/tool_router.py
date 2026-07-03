"""Tool Router for the AegisNex Intelligence Engine.

Maps abstract tasks from the Planner to concrete tools from the Tool Registry.
Performs validation, enrichment, and logging without executing tools.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.intelligence.tools import TOOL_REGISTRY, get_tool


def utc_now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ToolRouterConfig:
    """Configuration for the Tool Router."""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        strict_mode: bool = False,
    ):
        """Initialize router configuration.

        Args:
            logger: Logger instance for routing decisions
            strict_mode: If True, fail on unknown tool; if False, skip with warning
        """
        self.logger = logger or logging.getLogger("tool_router")
        self.strict_mode = strict_mode


class ToolRouterDecision:
    """Represents a single tool routing decision."""

    def __init__(
        self,
        tool_name: str,
        found: bool,
        description: str = "",
        category: str = "",
        permission_level: str = "",
        risk_level: str = "",
        reason: str = "",
        timestamp: str = "",
    ):
        self.tool_name = tool_name
        self.found = found
        self.description = description
        self.category = category
        self.permission_level = permission_level
        self.risk_level = risk_level
        self.reason = reason
        self.timestamp = timestamp or utc_now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary."""
        return {
            "tool_name": self.tool_name,
            "found": self.found,
            "description": self.description,
            "category": self.category,
            "permission_level": self.permission_level,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class ToolRouter:
    """Routes abstract tasks to concrete tools from the registry."""

    def __init__(self, config: Optional[ToolRouterConfig] = None):
        """Initialize the Tool Router.

        Args:
            config: Router configuration (logger, strictness)
        """
        self.config = config or ToolRouterConfig()
        self.logger = self.config.logger
        self.decisions: List[ToolRouterDecision] = []

    def route_task(self, task_name: str) -> Optional[ToolRouterDecision]:
        """Route a single task to a tool.

        Args:
            task_name: Abstract task name (should match a tool in registry)

        Returns:
            ToolRouterDecision with routing details, or None if not found and strict_mode=True
        """
        tool = get_tool(task_name)

        if tool is None:
            reason = f"Tool '{task_name}' not found in registry"
            self.logger.warning(reason)
            if self.config.strict_mode:
                return None
            decision = ToolRouterDecision(
                tool_name=task_name,
                found=False,
                reason=reason,
            )
            self.decisions.append(decision)
            return decision

        # Tool found and valid
        decision = ToolRouterDecision(
            tool_name=task_name,
            found=True,
            description=tool.description,
            category=tool.category,
            permission_level=tool.permission_level.value,
            risk_level=tool.risk_level.value,
            reason=f"Tool matched from registry ({tool.category})",
        )
        self.decisions.append(decision)

        self.logger.info(
            "Routing decision: task=%s, tool=%s, category=%s, risk=%s",
            task_name,
            task_name,
            tool.category,
            tool.risk_level.value,
        )

        return decision

    def route_plan(self, plan: List[str]) -> Dict[str, Any]:
        """Route all tasks in a plan.

        Args:
            plan: List of task names from the Planner

        Returns:
            Dictionary with routing results and metadata
        """
        self.decisions.clear()

        if not plan:
            self.logger.warning("Empty plan provided to router")
            return {
                "success": True,
                "total_tasks": 0,
                "routed_tools": [],
                "invalid_tasks": [],
                "decisions": [],
                "timestamp": utc_now(),
            }

        routed_tools: List[str] = []
        invalid_tasks: List[str] = []

        for task in plan:
            if not task or not isinstance(task, str):
                self.logger.warning("Invalid task in plan: %s (type=%s)", task, type(task))
                invalid_tasks.append(str(task))
                continue

            task = task.strip()
            decision = self.route_task(task)

            if decision and decision.found:
                routed_tools.append(task)
                self.logger.debug("Routed task '%s' → tool '%s'", task, task)
            elif decision:
                invalid_tasks.append(task)

        # Log summary
        self.logger.info(
            "Plan routing complete: total=%d, routed=%d, invalid=%d",
            len(plan),
            len(routed_tools),
            len(invalid_tasks),
        )

        return {
            "success": len(invalid_tasks) == 0 or not self.config.strict_mode,
            "total_tasks": len(plan),
            "routed_tools": routed_tools,
            "invalid_tasks": invalid_tasks,
            "decisions": [d.to_dict() for d in self.decisions],
            "timestamp": utc_now(),
        }

    def get_tool_metadata(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a tool without routing.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool metadata dictionary or None if not found
        """
        tool = get_tool(tool_name)
        if tool is None:
            return None

        return {
            "name": tool_name,
            "description": tool.description,
            "category": tool.category,
            "parameters": tool.parameters,
            "permission_level": tool.permission_level.value,
            "access_mode": tool.access_mode.value,
            "risk_level": tool.risk_level.value,
            "destructive": tool.destructive,
            "requires_approval": tool.requires_approval,
        }

    def get_routing_log(self) -> List[Dict[str, Any]]:
        """Get the complete routing decision log.

        Returns:
            List of all routing decisions made by this router instance
        """
        return [d.to_dict() for d in self.decisions]

    def clear_decisions(self) -> None:
        """Clear the routing decision history."""
        self.decisions.clear()
