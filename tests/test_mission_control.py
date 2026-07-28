"""Tests for Mission Control execution tracking."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.mission_control import (
    Execution,
    StageResult,
    ExecutionStatus,
    StageStatus,
    STAGE_ORDER,
    ensure_table,
    create_execution,
    update_execution,
    get_execution,
    list_executions,
    count_executions,
    get_execution_stats,
    delete_execution,
    utc_now,
)


@pytest.fixture
def mock_repo():
    """Create a mock PlatformRepository for testing."""
    repo = MagicMock()
    repo.backend = "sqlite"
    repo.placeholder = "?"
    repo._stored_data = {}
    repo._id_counter = 0

    def mock_table_exists(name):
        return name in repo._stored_data

    def mock_execute(sql, params=None):
        repo._id_counter += 1
        if "CREATE TABLE" in sql:
            if "mc_executions" not in repo._stored_data:
                repo._stored_data["mc_executions"] = []
            return repo._id_counter
        if "INSERT INTO" in sql:
            row = {"id": repo._id_counter}
            if params:
                for i, col in enumerate(["execution_id", "request", "user_name", "timestamp", "current_status", "total_latency_ms", "total_cost", "confidence", "overall_result", "stages", "error", "metadata"]):
                    if i < len(params):
                        row[col] = params[i]
            repo._stored_data.setdefault("mc_executions", []).append(row)
            return repo._id_counter
        if "UPDATE" in sql:
            if params and len(params) >= 2:
                exec_id = params[-1]
                for row in repo._stored_data.get("mc_executions", []):
                    if row.get("execution_id") == exec_id:
                        for i, col in enumerate(["request", "user_name", "timestamp", "current_status", "total_latency_ms", "total_cost", "confidence", "overall_result", "stages", "error", "metadata"]):
                            if i < len(params) - 1:
                                row[col] = params[i]
                        break
        if "DELETE" in sql:
            if params:
                exec_id = params[0]
                repo._stored_data["mc_executions"] = [
                    r for r in repo._stored_data.get("mc_executions", [])
                    if r.get("execution_id") != exec_id
                ]
        if "COUNT(*)" in sql:
            return repo._id_counter
        return repo._id_counter

    def mock_fetch_all(sql, params=None):
        if "AVG" in sql or ("SUM(" in sql and "COUNT(*)" in sql):
            rows = repo._stored_data.get("mc_executions", [])
            total = len(rows)
            completed = sum(1 for r in rows if r.get("current_status") == "completed")
            failed = sum(1 for r in rows if r.get("current_status") == "failed")
            running = sum(1 for r in rows if r.get("current_status") == "running")
            queued = sum(1 for r in rows if r.get("current_status") == "queued")
            avg_lat = sum(r.get("total_latency_ms", 0) for r in rows) / max(total, 1)
            avg_cost = sum(r.get("total_cost", 0) for r in rows) / max(total, 1)
            avg_conf = sum(r.get("confidence", 0) for r in rows) / max(total, 1)
            total_cost = sum(r.get("total_cost", 0) for r in rows)
            return [{"total": total, "completed": completed, "failed": failed, "running": running, "queued": queued, "avg_latency": avg_lat, "avg_cost": avg_cost, "avg_confidence": avg_conf, "total_cost": total_cost}]
        if "COUNT(*)" in sql:
            cnt = len(repo._stored_data.get("mc_executions", []))
            return [{"cnt": cnt}]
        rows = list(repo._stored_data.get("mc_executions", []))
        if "WHERE execution_id =" in sql and params:
            exec_id = params[0]
            rows = [r for r in rows if r.get("execution_id") == exec_id]
        return rows

    repo.table_exists = mock_table_exists
    repo._execute = mock_execute
    repo._fetch_all = mock_fetch_all
    return repo


class TestStageResult:
    def test_creation(self):
        stage = StageResult(stage_id="planner")
        assert stage.stage_id == "planner"
        assert stage.status == "queued"
        assert stage.latency_ms == 0.0
        assert stage.confidence == 0.0

    def test_to_dict(self):
        stage = StageResult(stage_id="planner", status="completed", latency_ms=150.5)
        d = stage.to_dict()
        assert d["stage_id"] == "planner"
        assert d["status"] == "completed"
        assert d["latency_ms"] == 150.5

    def test_from_dict(self):
        d = {"stage_id": "verifier", "status": "running", "confidence": 0.85, "model": "gpt-4"}
        stage = StageResult.from_dict(d)
        assert stage.stage_id == "verifier"
        assert stage.status == "running"
        assert stage.confidence == 0.85
        assert stage.model == "gpt-4"

    def test_connected_tools(self):
        stage = StageResult(stage_id="executor", connected_tools=["docker", "metrics"])
        d = stage.to_dict()
        assert d["connected_tools"] == ["docker", "metrics"]

    def test_policy_decisions(self):
        decisions = [{"policy": "auto-approve", "effect": "allow", "reason": "low risk"}]
        stage = StageResult(stage_id="policy", policy_decisions=decisions)
        d = stage.to_dict()
        assert len(d["policy_decisions"]) == 1
        assert d["policy_decisions"][0]["effect"] == "allow"


class TestExecution:
    def test_creation(self):
        exec = Execution(
            execution_id="exec-001",
            request="Check container health",
            user="admin",
            timestamp=utc_now(),
        )
        assert exec.execution_id == "exec-001"
        assert exec.current_status == "queued"
        assert len(exec.stages) == 0

    def test_with_stages(self):
        stages = [StageResult(stage_id=sid) for sid in STAGE_ORDER]
        exec = Execution(
            execution_id="exec-002",
            request="Analyze incident",
            user="analyst",
            timestamp=utc_now(),
            stages=stages,
        )
        assert len(exec.stages) == 8
        assert exec.stages[0].stage_id == "planner"
        assert exec.stages[-1].stage_id == "executor"

    def test_to_dict(self):
        exec = Execution(
            execution_id="exec-003",
            request="Test",
            user="test",
            timestamp="2026-01-01T00:00:00Z",
            current_status="completed",
            confidence=0.95,
        )
        d = exec.to_dict()
        assert d["execution_id"] == "exec-003"
        assert d["current_status"] == "completed"
        assert d["confidence"] == 0.95
        assert isinstance(d["stages"], list)

    def test_from_dict(self):
        d = {
            "execution_id": "exec-004",
            "request": "Test request",
            "user": "user1",
            "timestamp": "2026-01-01T00:00:00Z",
            "current_status": "running",
            "total_latency_ms": 1500.0,
            "total_cost": 0.005,
            "confidence": 0.8,
            "overall_result": "Analysis complete",
            "stages": [
                {"stage_id": "planner", "status": "completed", "latency_ms": 200},
                {"stage_id": "verifier", "status": "running"},
            ],
        }
        exec = Execution.from_dict(d)
        assert exec.execution_id == "exec-004"
        assert len(exec.stages) == 2
        assert exec.stages[0].stage_id == "planner"
        assert exec.stages[0].status == "completed"


class TestDatabaseOperations:
    def test_ensure_table(self, mock_repo):
        ensure_table(mock_repo)
        assert mock_repo.table_exists("mc_executions")

    def test_create_execution(self, mock_repo):
        exec = create_execution(mock_repo, "exec-001", "Check health", "admin")
        assert exec.execution_id == "exec-001"
        assert exec.request == "Check health"
        assert exec.user == "admin"
        assert exec.current_status == "queued"
        assert len(exec.stages) == 8

    def test_get_execution(self, mock_repo):
        create_execution(mock_repo, "exec-002", "Test request")
        result = get_execution(mock_repo, "exec-002")
        assert result is not None
        assert result.execution_id == "exec-002"

    def test_get_execution_not_found(self, mock_repo):
        result = get_execution(mock_repo, "nonexistent")
        assert result is None

    def test_list_executions(self, mock_repo):
        create_execution(mock_repo, "exec-003", "Request 1")
        create_execution(mock_repo, "exec-004", "Request 2")
        create_execution(mock_repo, "exec-005", "Request 3")
        results = list_executions(mock_repo, limit=10)
        assert len(results) == 3

    def test_list_executions_with_status_filter(self, mock_repo):
        create_execution(mock_repo, "exec-006", "Request 1")
        create_execution(mock_repo, "exec-007", "Request 2")
        results = list_executions(mock_repo, status="queued")
        assert len(results) == 2

    def test_count_executions(self, mock_repo):
        create_execution(mock_repo, "exec-008", "Request 1")
        create_execution(mock_repo, "exec-009", "Request 2")
        count = count_executions(mock_repo)
        assert count == 2

    def test_update_execution(self, mock_repo):
        exec = create_execution(mock_repo, "exec-010", "Original")
        exec.current_status = "running"
        exec.confidence = 0.5
        update_execution(mock_repo, exec)
        result = get_execution(mock_repo, "exec-010")
        assert result is not None
        assert result.current_status == "running"
        assert result.confidence == 0.5

    def test_delete_execution(self, mock_repo):
        create_execution(mock_repo, "exec-011", "To delete")
        delete_execution(mock_repo, "exec-011")
        result = get_execution(mock_repo, "exec-011")
        assert result is None

    def test_get_execution_stats(self, mock_repo):
        create_execution(mock_repo, "exec-012", "Request 1")
        create_execution(mock_repo, "exec-013", "Request 2")
        stats = get_execution_stats(mock_repo)
        assert isinstance(stats, dict)
        assert "total" in stats
        assert "completed" in stats
        assert "failed" in stats
        assert "running" in stats
        assert "queued" in stats
        assert "avg_latency" in stats
        assert "avg_cost" in stats
        assert "avg_confidence" in stats
        assert "total_cost" in stats


class TestStageOrder:
    def test_all_stages_present(self):
        assert len(STAGE_ORDER) == 8
        expected = ["planner", "knowledge", "metrics", "docker", "policy", "risk", "verifier", "executor"]
        assert STAGE_ORDER == expected

    def test_stages_unique(self):
        assert len(STAGE_ORDER) == len(set(STAGE_ORDER))


class TestExecutionStatuses:
    def test_execution_status_values(self):
        assert ExecutionStatus.QUEUED.value == "queued"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"

    def test_stage_status_values(self):
        assert StageStatus.QUEUED.value == "queued"
        assert StageStatus.RUNNING.value == "running"
        assert StageStatus.COMPLETED.value == "completed"
        assert StageStatus.FAILED.value == "failed"
        assert StageStatus.SKIPPED.value == "skipped"
