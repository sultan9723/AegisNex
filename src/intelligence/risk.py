"""Risk Engine — scores actions by risk and determines approval requirements."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskAssessment:
    score: float
    level: RiskLevel
    confidence: float = 0.0
    requires_approval: bool = False
    impact_estimate: str = ""
    factors: List[str] = field(default_factory=list)
    auto_execute_allowed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level.value,
            "confidence": self.confidence,
            "requires_approval": self.requires_approval,
            "impact_estimate": self.impact_estimate,
            "factors": self.factors,
            "auto_execute_allowed": self.auto_execute_allowed,
        }


class RiskEngine:
    def __init__(self, auto_execute_threshold: float = 0.3) -> None:
        self._auto_execute_threshold = float(os.getenv("AEGIS_AI_AUTO_EXECUTE_THRESHOLD", str(auto_execute_threshold)))

    def assess_tool(self, tool_name: str, params: Optional[Dict[str, Any]] = None) -> RiskAssessment:
        from src.intelligence.tools import get_tool

        tool = get_tool(tool_name)
        if tool is None:
            return RiskAssessment(score=0.5, level=RiskLevel.MEDIUM, requires_approval=True, impact_estimate=f"Unknown tool: {tool_name}", factors=["Tool not in registry"])

        factors: List[str] = []
        score = 0.0

        if tool.risk_level.value == "none":
            score = 0.0
            factors.append("No risk (read-only tool)")
        elif tool.risk_level.value == "low":
            score = 0.2
            factors.append("Low risk operation")
        elif tool.risk_level.value == "medium":
            score = 0.5
            factors.append("Medium risk operation")
        elif tool.risk_level.value == "high":
            score = 0.7
            factors.append("High risk operation")
        elif tool.risk_level.value == "critical":
            score = 0.9
            factors.append("Critical risk operation")

        if tool.access_mode.value == "write":
            score = max(score, 0.5)
            factors.append("Write operation — modifies system state")
        if tool.destructive:
            score = max(score, 0.8)
            factors.append("Destructive operation — may cause service disruption")
        if tool.requires_approval:
            factors.append("Tool explicitly requires approval")

        impact = self._estimate_impact(tool_name, score, factors)
        requires_approval = tool.requires_approval or score >= 0.5
        auto_execute = not requires_approval and score <= self._auto_execute_threshold

        return RiskAssessment(
            score=round(score, 2),
            level=self._score_to_level(score),
            confidence=0.8 if tool is not None else 0.3,
            requires_approval=requires_approval,
            impact_estimate=impact,
            factors=factors,
            auto_execute_allowed=auto_execute,
        )

    def assess_runbook(self, runbook_name: str, steps: List[Dict[str, Any]]) -> RiskAssessment:
        factors: List[str] = []
        scores = []
        for step in steps:
            if step.get("requires_approval"):
                scores.append(0.7)
                factors.append(f"Step '{step.get('name', '?')}' requires approval")
            tool_name = step.get("tool", "")
            if tool_name:
                ta = self.assess_tool(tool_name, step.get("params"))
                scores.append(ta.score)
                factors.extend(ta.factors)

        max_score = max(scores) if scores else 0.0
        avg_score = sum(scores) / len(scores) if scores else 0.0
        final_score = max(max_score, avg_score)

        impact = self._estimate_impact(runbook_name, final_score, factors)
        requires_approval = final_score >= 0.5 or any(s.get("requires_approval") for s in steps)

        return RiskAssessment(
            score=round(final_score, 2),
            level=self._score_to_level(final_score),
            confidence=0.7,
            requires_approval=requires_approval,
            impact_estimate=impact,
            factors=list(set(factors)),
            auto_execute_allowed=not requires_approval and final_score <= self._auto_execute_threshold,
        )

    def assess_workflow(self, workflow_name: str, steps: List[Dict[str, Any]]) -> RiskAssessment:
        return self.assess_runbook(workflow_name, steps)

    def _score_to_level(self, score: float) -> RiskLevel:
        if score <= 0.1:
            return RiskLevel.NONE
        elif score <= 0.3:
            return RiskLevel.LOW
        elif score <= 0.5:
            return RiskLevel.MEDIUM
        elif score <= 0.75:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    def _estimate_impact(self, name: str, score: float, factors: List[str]) -> str:
        if score >= 0.8:
            return f"Critical impact — {name} may cause significant service disruption"
        elif score >= 0.5:
            return f"Moderate impact — {name} affects running services"
        elif score >= 0.2:
            return f"Minor impact — {name} has limited effect on operations"
        else:
            return f"Negligible impact — {name} is read-only or informational"
