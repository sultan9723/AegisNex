"""Tests for the Autonomous Incident Pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from src.autonomous import AutonomousPipeline
from src.event_bus import EventType, reset_bus
from src.execution_history import ExecutionHistory
from src.incidents import IncidentManager

pytestmark = pytest.mark.asyncio


class FakeIncidentManager:
    def __init__(self) -> None:
        self.incidents: List[Dict[str, Any]] = []
        self.resolved: List[str] = []

    def create_incident(self, severity: str, service_name: str, incident_type: str, description: str) -> Any:
        from src.incidents import Incident
        inc = Incident(
            incident_id=f"inc-{len(self.incidents) + 1}",
            timestamp="2026-01-01T00:00:00Z",
            severity=severity,
            service_name=service_name,
            incident_type=incident_type,
            description=description,
            health_check_results=[],
            remediation_attempted=False,
            remediation_successful=False,
            status="active",
        )
        self.incidents.append(inc)
        return inc

    def resolve_incident(self, incident_id: str, actor: str = "", resolution_notes: str = "") -> Any:
        self.resolved.append(incident_id)
        return None

    def update_incident(self, incident_id: str, **updates: Any) -> Any:
        return None


class FakeAgentRegistry:
    async def dispatch_task(self, task: str, target_agent: str = "") -> Dict[str, Any]:
        return {
            "success": True,
            "summary": "Investigated and found root cause: resource exhaustion",
            "data": {
                "tool_results": {"health": {"status": "unhealthy"}},
                "summary": "Root cause identified",
                "confidence": 0.85,
            },
            "confidence": 0.85,
            "agent_id": target_agent or "supervisor-agent",
        }


async def test_autonomous_pipeline_runs_full_flow(tmp_path: Path) -> None:
    reset_bus()
    incidents = FakeIncidentManager()
    agents = FakeAgentRegistry()
    history = ExecutionHistory(history_path=tmp_path / "exec.json")

    pipeline = AutonomousPipeline(
        incident_manager=incidents,
        agent_registry=agents,
        execution_history=history,
    )

    result = await pipeline.run_pipeline(
        incident_id="inc-1",
        service_name="nginx",
        description="Container nginx is down",
    )

    assert result.status == "completed"
    assert result.pipeline_id is not None
    assert result.incident_id == "inc-1"
    assert len(result.steps_completed) >= 8
    assert result.root_cause is not None
    assert result.remediation_plan is not None
    assert result.explanation is not None
    assert result.duration_ms is not None


async def test_autonomous_pipeline_handles_incident_created_event(tmp_path: Path) -> None:
    reset_bus()
    incidents = FakeIncidentManager()
    agents = FakeAgentRegistry()
    history = ExecutionHistory(history_path=tmp_path / "exec.json")

    pipeline = AutonomousPipeline(
        incident_manager=incidents,
        agent_registry=agents,
        execution_history=history,
    )

    from src.event_bus import get_bus
    bus = get_bus()
    await pipeline.start()
    await bus.publish(EventType.INCIDENT_CREATED, {"incident_id": "inc-2", "service_name": "api", "description": "API timeout"})

    results = pipeline.get_results()
    assert len(results) >= 1


async def test_autonomous_pipeline_fail_execution(tmp_path: Path) -> None:
    reset_bus()

    class FailingRegistry:
        async def dispatch_task(self, task: str, target_agent: str = "") -> Dict[str, Any]:
            raise RuntimeError("Agent crashed")

    incidents = FakeIncidentManager()
    agents = FailingRegistry()
    history = ExecutionHistory(history_path=tmp_path / "exec.json")

    pipeline = AutonomousPipeline(
        incident_manager=incidents,
        agent_registry=agents,  # type: ignore
        execution_history=history,
    )

    result = await pipeline.run_pipeline(
        incident_id="inc-3",
        service_name="redis",
        description="Redis not responding",
    )

    assert result.status == "failed"
    assert result.error is not None


async def test_autonomous_pipeline_get_results(tmp_path: Path) -> None:
    reset_bus()
    incidents = FakeIncidentManager()
    agents = FakeAgentRegistry()
    history = ExecutionHistory(history_path=tmp_path / "exec.json")

    pipeline = AutonomousPipeline(
        incident_manager=incidents,
        agent_registry=agents,
        execution_history=history,
    )

    assert pipeline.get_results() == []
    await pipeline.run_pipeline(incident_id="inc-4", service_name="test", description="test")
    assert len(pipeline.get_results()) == 1

    detail = pipeline.get_result(pipeline.get_results()[0]["pipeline_id"])
    assert detail is not None
    assert detail["incident_id"] == "inc-4"
