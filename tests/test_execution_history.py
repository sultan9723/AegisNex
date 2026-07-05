"""Tests for the Execution History module."""

from __future__ import annotations

from pathlib import Path
from src.execution_history import ExecutionHistory, ExecutionStatus


def test_execution_history_start_and_complete(tmp_path: Path) -> None:
    history = ExecutionHistory(history_path=tmp_path / "exec.json")
    exec_id = history.start_execution("test_trigger")
    assert exec_id is not None
    assert history.get_active() is not None
    assert history.get_active().execution_id == exec_id
    assert history.get_active().trigger == "test_trigger"
    assert history.get_active().status == ExecutionStatus.RUNNING

    history.complete_execution()
    assert history.get_active() is None

    record = history.get_record(exec_id)
    assert record is not None
    assert record.status == ExecutionStatus.COMPLETED
    assert record.completed_at is not None


def test_execution_history_fail_execution(tmp_path: Path) -> None:
    history = ExecutionHistory(history_path=tmp_path / "exec.json")
    exec_id = history.start_execution("fail_test")
    history.fail_execution("Something went wrong")
    record = history.get_record(exec_id)
    assert record.status == ExecutionStatus.FAILED
    assert record.error == "Something went wrong"


def test_execution_history_add_steps(tmp_path: Path) -> None:
    history = ExecutionHistory(history_path=tmp_path / "exec.json")
    history.start_execution("step_test")
    step_id = history.add_step("planning", "Create plan", input={"task": "fix"})
    assert step_id is not None
    assert len(history.get_active().steps) == 1
    assert history.get_active().steps[0].step_type == "planning"
    assert history.get_active().steps[0].name == "Create plan"
    assert history.get_active().steps[0].input == {"task": "fix"}

    history.complete_step(step_id, output={"plan": "restart"}, agent="supervisor", tool="plan")
    step = history.get_active().steps[0]
    assert step.status == ExecutionStatus.COMPLETED
    assert step.agent == "supervisor"
    assert step.tool == "plan"
    assert step.duration_ms is not None


def test_execution_history_fail_step(tmp_path: Path) -> None:
    history = ExecutionHistory(history_path=tmp_path / "exec.json")
    history.start_execution("step_fail")
    step_id = history.add_step("execution", "Run command")
    history.fail_step(step_id, "Command failed")
    step = history.get_active().steps[0]
    assert step.status == ExecutionStatus.FAILED
    assert step.error == "Command failed"


def test_execution_history_metadata(tmp_path: Path) -> None:
    history = ExecutionHistory(history_path=tmp_path / "exec.json")
    history.start_execution("meta_test")
    history.set_planner({"agent": "supervisor"})
    history.add_agent({"agent_id": "infra", "result": "ok"})
    history.add_evidence({"type": "log", "value": "error found"})
    history.add_decision({"step": "analysis", "conclusion": "restart"})
    history.set_root_cause("OOM error")
    history.set_remediation_plan({"action": "restart_container"})
    history.set_verification({"verified": True})

    record = history.get_active()
    assert record.planner == {"agent": "supervisor"}
    assert len(record.agents) == 1
    assert len(record.evidence) == 1
    assert len(record.decisions) == 1
    assert record.root_cause == "OOM error"
    assert record.remediation_plan == {"action": "restart_container"}
    assert record.verification == {"verified": True}


def test_execution_history_get_stats(tmp_path: Path) -> None:
    history = ExecutionHistory(history_path=tmp_path / "exec.json")
    stats = history.get_stats()
    assert stats["total_executions"] == 0
    assert stats["success_rate"] == 0.0

    history.start_execution("t1")
    history.complete_execution()
    history.start_execution("t2")
    history.complete_execution()
    history.start_execution("t3")
    history.fail_execution("error")

    stats = history.get_stats()
    assert stats["total_executions"] == 3
    assert stats["completed"] == 2
    assert stats["failed"] == 1
    assert stats["success_rate"] == 66.7


def test_execution_history_get_records_with_filter(tmp_path: Path) -> None:
    history = ExecutionHistory(history_path=tmp_path / "exec.json")
    history.start_execution("t1")
    history.complete_execution()
    history.start_execution("t2")
    history.fail_execution("err")

    completed = history.get_records(status=ExecutionStatus.COMPLETED)
    failed = history.get_records(status=ExecutionStatus.FAILED)

    assert len(completed) == 1
    assert len(failed) == 1


def test_execution_history_persistence(tmp_path: Path) -> None:
    path = tmp_path / "exec.json"
    history = ExecutionHistory(history_path=path)
    eid = history.start_execution("persist_test")
    history.add_step("planning", "Plan A")
    history.complete_execution()

    # Reload
    history2 = ExecutionHistory(history_path=path)
    record = history2.get_record(eid)
    assert record is not None
    assert record.trigger == "persist_test"
    assert record.status == ExecutionStatus.COMPLETED


def test_execution_history_add_approval(tmp_path: Path) -> None:
    history = ExecutionHistory(history_path=tmp_path / "exec.json")
    history.start_execution("approval_test")
    history.add_approval({"approved": True, "by": "admin"})
    record = history.get_active()
    assert len(record.approvals) == 1
    assert record.approvals[0]["approved"] is True
