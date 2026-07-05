"""Integration tests for Sprint D multi-agent collaboration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from src.agents.base import AgentConfig, AgentMessage, AgentResult, AgentType, BaseAgent
from src.agents.orchestrator import AgentOrchestrator
from src.agents.registry import AgentRegistry, create_default_registry


class StubDomainAgent(BaseAgent):
    def __init__(self, agent_id: str, name: str, signal_value: str, confidence: float = 0.75, approvals: List[Dict[str, Any]] | None = None) -> None:
        super().__init__(AgentConfig(
            agent_id=agent_id,
            name=name,
            agent_type=AgentType.GENERAL,
            description=f"Stub {name}",
        ))
        self._signal_value = signal_value
        self._confidence = confidence
        self._approvals = approvals or []

    async def process(self, task: str, shared_state: dict) -> AgentResult:
        data = {
            "task": task,
            "confidence": self._confidence,
            "tool_results": {
                self.agent_id: {"status": "ok", "count": 1, "task": task},
            },
            "pending_approvals": list(self._approvals),
            "primary_signal": {
                "signal": "system_health",
                "value": self._signal_value,
                "source": self.agent_id,
            },
            "execution_log": {"node_name": self.agent_id, "execution_status": "success"},
            "execution_trace": {"node": self.agent_id, "status": "success"},
            "metrics": {"duration_ms": 1.0},
        }
        return AgentResult(
            agent_id=self.agent_id,
            success=not self._approvals,
            summary=f"{self.config.name}: {self._signal_value}",
            data=data,
            duration_ms=1.0,
        )

    async def collaborate(self, messages: list[AgentMessage]) -> list[AgentMessage]:
        return [AgentMessage(source=self.agent_id, target=m.source, message_type="stub_result", payload={"ok": True}) for m in messages]


class StubSupervisor(BaseAgent):
    def __init__(self, selected_agents: List[str], subtasks: Dict[str, str]) -> None:
        super().__init__(AgentConfig(
            agent_id="supervisor-agent",
            name="Supervisor Agent",
            agent_type=AgentType.GENERAL,
            description="Stub supervisor",
        ))
        self._selected_agents = selected_agents
        self._subtasks = subtasks

    async def process(self, task: str, shared_state: dict) -> AgentResult:
        return AgentResult(
            agent_id=self.agent_id,
            success=True,
            summary="Planned collaboration",
            data={
                "collaboration_plan": {
                    "selected_agents": list(self._selected_agents),
                    "parallel_groups": [list(self._selected_agents)],
                    "subtasks": dict(self._subtasks),
                    "estimated_confidence": 0.8,
                    "needs_approval": False,
                    "reason": "stub plan",
                }
            },
            duration_ms=1.0,
        )

    async def collaborate(self, messages: list[AgentMessage]) -> list[AgentMessage]:
        responses: list[AgentMessage] = []
        for message in messages:
            responses.append(
                AgentMessage(
                    source=self.agent_id,
                    target=message.source,
                    message_type="supervisor_summary",
                    payload={
                        "task": message.payload.get("task", ""),
                        "confidence": 0.8,
                        "selected_agents": list(self._selected_agents),
                        "conflicts": message.payload.get("conflicts", []),
                    },
                )
            )
        return responses


def test_registry_collaborate_resolves_conflicts_and_updates_shared_state() -> None:
    context: Dict[str, Any] = {}

    async def _run() -> Dict[str, Any]:
        registry = AgentRegistry()
        context["registry"] = registry
        registry.register(StubDomainAgent("monitoring-agent", "Monitoring Agent", "healthy", confidence=0.92))
        registry.register(StubDomainAgent("infrastructure-agent", "Infrastructure Agent", "degraded", confidence=0.61))

        return await registry.collaborate(["monitoring-agent", "infrastructure-agent"], "check health")

    result = asyncio.run(_run())

    assert result["success"] is True
    assert result["message_count"] == 2
    assert result["conflicts"]
    assert result["conflicts"][0]["signal"] == "system_health"
    assert result["conflicts"][0]["resolved_by"] == "monitoring-agent"
    assert result["metrics"]["agent_count"] == 2
    shared_state = context["registry"].get_shared_state()
    assert shared_state["goal_completed"] is True
    assert shared_state["agent_collaboration"]
    assert shared_state["shared_state"]["conflicts"]


def test_registry_dispatch_task_uses_supervisor_plan() -> None:
    context: Dict[str, Any] = {}

    async def _run() -> Dict[str, Any]:
        registry = AgentRegistry()
        context["registry"] = registry
        registry.register(StubSupervisor(["monitoring-agent", "incident-agent"], {
            "monitoring-agent": "Check health metrics",
            "incident-agent": "Review incidents",
        }))
        registry.register(StubDomainAgent("monitoring-agent", "Monitoring Agent", "healthy", confidence=0.9))
        registry.register(StubDomainAgent("incident-agent", "Incident Agent", "clear", confidence=0.85))

        return await registry.dispatch_task("check health and incidents")

    result = asyncio.run(_run())

    assert result["success"] is True
    assert result["selected_agents"] == ["monitoring-agent", "incident-agent"]
    assert len(result["data"]["agent_results"]) == 2
    assert result["data"]["supervisor_summary"]["confidence"] == pytest.approx(0.8, abs=0.01)
    assert context["registry"].get_shared_state()["goal_completed"] is True


def test_registry_blocks_pending_approvals() -> None:
    context: Dict[str, Any] = {}

    async def _run() -> Dict[str, Any]:
        registry = AgentRegistry()
        context["registry"] = registry
        registry.register(StubDomainAgent(
            "incident-agent",
            "Incident Agent",
            "pending",
            confidence=0.4,
            approvals=[{"tool_name": "incident", "reason": "requires approval", "status": "pending"}],
        ))

        return await registry.dispatch_task("remediate incident", target_agent="incident-agent")

    result = asyncio.run(_run())

    assert result["success"] is False
    assert result["data"]["pending_approvals"]
    assert context["registry"].get_shared_state()["approval_required"] is True
    assert context["registry"].get_shared_state()["pending_approvals"]


def test_default_registry_contains_specialized_agents() -> None:
    registry = create_default_registry()
    agents = registry.list_agents()

    agent_ids = {agent["agent_id"] for agent in agents}
    assert agent_ids == {
        "supervisor-agent",
        "infrastructure-agent",
        "docker-agent",
        "monitoring-agent",
        "incident-agent",
        "reporting-agent",
        "knowledge-agent",
        "compliance-agent",
    }


def test_orchestrator_exposes_new_collaborative_agents() -> None:
    orchestrator = AgentOrchestrator()
    agents = orchestrator.list_agents()

    assert len(agents) == 8
    assert any(agent["agent_id"] == "supervisor-agent" for agent in agents)
    assert any(agent["agent_id"] == "monitoring-agent" for agent in agents)
