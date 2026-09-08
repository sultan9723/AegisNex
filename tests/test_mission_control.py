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
    ExecutionType,
    STAGE_ORDER,
    ensure_table,
    create_execution,
    update_execution,
    get_execution,
    get_stage,
    list_executions,
    count_executions,
    get_execution_stats,
    get_execution_type_stats,
    delete_execution,
    complete_stage,
    update_stage,
    mark_stage_started,
    stage_to_stage_result,
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

    _MC_COLS = ["execution_id", "request", "user_name", "timestamp", "current_status",
                 "total_latency_ms", "total_cost", "confidence", "overall_result",
                 "stages", "error", "metadata", "execution_type", "organization",
                 "agents", "audit_links"]

    def mock_execute(sql, params=None):
        repo._id_counter += 1
        if "CREATE TABLE" in sql:
            if "mc_executions" not in repo._stored_data:
                repo._stored_data["mc_executions"] = []
            return repo._id_counter
        if "INSERT INTO" in sql:
            row = {"id": repo._id_counter}
            if params:
                for i, col in enumerate(_MC_COLS):
                    if i < len(params):
                        row[col] = params[i]
            repo._stored_data.setdefault("mc_executions", []).append(row)
            return repo._id_counter
        if "UPDATE" in sql:
            if params and len(params) >= 2:
                exec_id = params[-1]
                update_cols = ["request", "user_name", "timestamp", "current_status",
                               "total_latency_ms", "total_cost", "confidence", "overall_result",
                               "stages", "error", "metadata", "execution_type", "organization",
                               "agents", "audit_links"]
                for row in repo._stored_data.get("mc_executions", []):
                    if row.get("execution_id") == exec_id:
                        for i, col in enumerate(update_cols):
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

    def _mock_filter(rows, sql, params):
        """Simple WHERE clause filtering: extract column=param in order."""
        import re
        filtered = list(rows)
        p_iter = iter(params) if params else iter([])

        # Find all column = ? patterns in the WHERE clause, preserving order
        where_part = sql.split("WHERE")[-1] if "WHERE" in sql else ""
        # Split on AND
        conditions = re.split(r'\bAND\b', where_part)
        for cond in conditions:
            cond = cond.strip()
            m = re.match(r'\s*\(?\s*(\w+)\s*(>=|<=|!=|=|LIKE|>|<)\s*\?', cond, re.IGNORECASE)
            if m:
                col = m.group(1)
                op = m.group(2).upper()
                try:
                    val = next(p_iter)
                except StopIteration:
                    break
                if op == "LIKE":
                    pattern = str(val).replace("%", "")
                    filtered = [r for r in filtered if pattern in str(r.get(col, ""))]
                elif op == "=":
                    filtered = [r for r in filtered if str(r.get(col, "")) == str(val)]
                elif op == ">=":
                    filtered = [r for r in filtered if str(r.get(col, "")) >= str(val)]
                elif op == "<=":
                    filtered = [r for r in filtered if str(r.get(col, "")) <= str(val)]
                elif op == ">":
                    filtered = [r for r in filtered if str(r.get(col, "")) > str(val)]
                elif op == "<":
                    filtered = [r for r in filtered if str(r.get(col, "")) < str(val)]
                elif op == "!=":
                    filtered = [r for r in filtered if str(r.get(col, "")) != str(val)]
        return filtered

    def mock_fetch_all(sql, params=None):
        all_rows = repo._stored_data.get("mc_executions", [])
        params = tuple(params) if params else ()

        if "GROUP BY execution_type" in sql:
            counts: dict[str, dict] = {}
            for r in all_rows:
                et = r.get("execution_type", "unknown")
                if et not in counts:
                    counts[et] = {"count": 0, "completed": 0, "total_latency": 0.0, "confidence_sum": 0.0, "total_cost": 0.0}
                counts[et]["count"] += 1
                if r.get("current_status") == "completed":
                    counts[et]["completed"] += 1
                counts[et]["total_latency"] += r.get("total_latency_ms", 0.0)
                counts[et]["confidence_sum"] += r.get("confidence", 0.0)
                counts[et]["total_cost"] += r.get("total_cost", 0.0)
            result = []
            for et, vals in counts.items():
                result.append({
                    "execution_type": et,
                    "count": vals["count"],
                    "completed": vals["completed"],
                    "avg_latency": round(vals["total_latency"] / max(vals["count"], 1), 1),
                    "avg_confidence": round(vals["confidence_sum"] / max(vals["count"], 1), 3),
                    "total_cost": round(vals["total_cost"], 6),
                })
            return sorted(result, key=lambda x: x["count"], reverse=True)

        if "AVG" in sql and "total_latency_ms" in sql:
            rows = all_rows
            total = len(rows)
            completed = sum(1 for r in rows if r.get("current_status") == "completed")
            failed = sum(1 for r in rows if r.get("current_status") == "failed")
            running = sum(1 for r in rows if r.get("current_status") == "running")
            queued = sum(1 for r in rows if r.get("current_status") == "queued")
            avg_lat = sum(r.get("total_latency_ms", 0) for r in rows) / max(total, 1)
            avg_cost = sum(r.get("total_cost", 0) for r in rows) / max(total, 1)
            avg_conf = sum(r.get("confidence", 0) for r in rows) / max(total, 1)
            total_cost = sum(r.get("total_cost", 0) for r in rows)
            type_count = len({r.get("execution_type", "") for r in rows}) if rows else 0
            user_count = len({r.get("user_name", "") for r in rows}) if rows else 0
            return [{"total": total, "completed": completed, "failed": failed, "running": running, "queued": queued, "avg_latency": avg_lat, "avg_cost": avg_cost, "avg_confidence": avg_conf, "total_cost": total_cost, "type_count": type_count, "user_count": user_count}]

        rows = list(all_rows)
        if "WHERE" in sql and params:
            rows = _mock_filter(rows, sql, params)
        if "COUNT(*) as cnt" in sql or "COUNT(*)" in sql:
            return [{"cnt": len(rows)}]
        # Handle ORDER BY id DESC / LIMIT / OFFSET by ignoring them
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


class TestExecutionType:
    def test_all_types_have_values(self):
        assert ExecutionType.CHAT.value == "chat"
        assert ExecutionType.ANALYZE.value == "analyze"
        assert ExecutionType.PLAN.value == "plan"
        assert ExecutionType.KNOWLEDGE_SEARCH.value == "knowledge_search"
        assert ExecutionType.DOCKER_ACTION.value == "docker_action"
        assert ExecutionType.GOVERNANCE_APPROVAL.value == "governance_approval"
        assert ExecutionType.POLICY_CHECK.value == "policy_check"
        assert ExecutionType.WORKFLOW.value == "workflow"
        assert ExecutionType.AGENT_DISPATCH.value == "agent_dispatch"
        assert ExecutionType.SEARCH.value == "search"


class TestExecutionNewFields:
    def test_execution_with_organization(self):
        exec_ = Execution(
            execution_id="exec-org-1",
            request="Test org",
            user="admin",
            timestamp=utc_now(),
            organization="org-42",
            agents=["agent-alpha", "agent-beta"],
            audit_links={"audit_log": "log/123", "governance": "gov/456"},
            execution_type="chat",
        )
        assert exec_.organization == "org-42"
        assert exec_.agents == ["agent-alpha", "agent-beta"]
        assert exec_.audit_links["audit_log"] == "log/123"
        assert exec_.execution_type == "chat"

    def test_execution_to_dict_includes_new_fields(self):
        exec_ = Execution(
            execution_id="exec-new-1",
            request="Test",
            user="u",
            timestamp=utc_now(),
            organization="org-99",
            agents=["agent-x"],
            audit_links={"link": "val"},
            execution_type="docker_action",
        )
        d = exec_.to_dict()
        assert d["organization"] == "org-99"
        assert d["agents"] == ["agent-x"]
        assert d["audit_links"]["link"] == "val"
        assert d["execution_type"] == "docker_action"

    def test_execution_from_dict_includes_new_fields(self):
        d = {
            "execution_id": "exec-new-2",
            "request": "Test from dict",
            "user": "admin",
            "timestamp": "2026-01-01T00:00:00Z",
            "organization": "org-77",
            "agents": ["agent-a", "agent-b"],
            "audit_links": {"audit": "/audit/1"},
            "execution_type": "governance_approval",
        }
        exec_ = Execution.from_dict(d)
        assert exec_.organization == "org-77"
        assert len(exec_.agents) == 2
        assert exec_.audit_links["audit"] == "/audit/1"
        assert exec_.execution_type == "governance_approval"


class TestReplayData:
    def test_replay_data_returns_timeline(self):
        stages = [
            StageResult(stage_id="planner", status="completed", latency_ms=100.0, summary="Plan created", model="gpt-4", evidence=["ev1"], inputs={"q": "hello"}, outputs={"plan": "do it"}),
            StageResult(stage_id="verifier", status="completed", latency_ms=50.0, confidence=0.95),
        ]
        exec_ = Execution(
            execution_id="exec-replay-1",
            request="Test replay",
            user="admin",
            timestamp=utc_now(),
            current_status="completed",
            stages=stages,
            execution_type="chat",
            organization="org-1",
            agents=["agent-x"],
            audit_links={"log": "/log/1"},
        )
        replay = exec_.replay_data()
        assert replay["execution_id"] == "exec-replay-1"
        assert replay["execution_type"] == "chat"
        assert replay["organization"] == "org-1"
        assert replay["agents"] == ["agent-x"]
        assert replay["audit_links"]["log"] == "/log/1"
        assert len(replay["timeline"]) == 2
        assert replay["timeline"][0]["stage_id"] == "planner"
        assert replay["timeline"][0]["inputs"]["q"] == "hello"
        assert replay["timeline"][0]["evidence"] == ["ev1"]


class TestStageHelpers:
    def test_stage_to_stage_result(self):
        sr = stage_to_stage_result("planner", status="completed", latency_ms=200.0, confidence=0.9, model="gpt-4", provider="openai", tokens=150, estimated_cost=0.003, summary="Done", connected_tools=["tool1"], evidence=["ev"], policy_decisions=[{"effect": "allow"}], inputs={"q": "hi"}, outputs={"a": "ok"})
        assert sr.stage_id == "planner"
        assert sr.latency_ms == 200.0
        assert sr.model == "gpt-4"
        assert sr.connected_tools == ["tool1"]

    def test_complete_stage(self):
        stages = [StageResult(stage_id="planner")]
        exec_ = Execution(execution_id="exec-cs-1", request="Test", user="u", timestamp=utc_now(), stages=stages)
        result = complete_stage(exec_, "planner", status="completed", latency_ms=150.0, confidence=0.95, summary="Stage done")
        assert result is True
        assert exec_.stages[0].status == "completed"
        assert exec_.stages[0].latency_ms == 150.0
        assert exec_.stages[0].confidence == 0.95

    def test_complete_stage_not_found(self):
        exec_ = Execution(execution_id="exec-cs-2", request="Test", user="u", timestamp=utc_now())
        result = complete_stage(exec_, "nonexistent", status="completed")
        assert result is False

    def test_update_stage(self):
        stages = [StageResult(stage_id="risk", status="queued")]
        exec_ = Execution(execution_id="exec-us-1", request="Test", user="u", timestamp=utc_now(), stages=stages)
        result = update_stage(exec_, "risk", status="running", latency_ms=50.0)
        assert result is True
        assert exec_.stages[0].status == "running"
        assert exec_.stages[0].latency_ms == 50.0

    def test_update_stage_not_found(self):
        exec_ = Execution(execution_id="exec-us-2", request="Test", user="u", timestamp=utc_now())
        result = update_stage(exec_, "nonexistent", status="running")
        assert result is False

    def test_mark_stage_started(self):
        stages = [StageResult(stage_id="executor")]
        exec_ = Execution(execution_id="exec-ms-1", request="Test", user="u", timestamp=utc_now(), stages=stages)
        result = mark_stage_started(exec_, "executor")
        assert result is True
        assert exec_.stages[0].status == "running"
        assert exec_.stages[0].start_time is not None


class TestGetStage:
    def test_get_stage_returns_correct_stage(self, mock_repo):
        create_execution(mock_repo, "exec-gs-1", "Test", "admin")
        stage = get_stage(mock_repo, "exec-gs-1", "planner")
        assert stage is not None
        assert stage.stage_id == "planner"
        assert stage.status == "queued"

    def test_get_stage_not_found_execution(self, mock_repo):
        stage = get_stage(mock_repo, "nonexistent", "planner")
        assert stage is None

    def test_get_stage_not_found_stage(self, mock_repo):
        create_execution(mock_repo, "exec-gs-2", "Test", "admin")
        stage = get_stage(mock_repo, "exec-gs-2", "nonexistent")
        assert stage is None


class TestExecutionTypeStats:
    def test_get_execution_type_stats_returns_list(self, mock_repo):
        create_execution(mock_repo, "exec-ts-1", "Req", "admin", execution_type="chat")
        create_execution(mock_repo, "exec-ts-2", "Req2", "admin", execution_type="docker_action")
        stats = get_execution_type_stats(mock_repo)
        assert isinstance(stats, list)
        assert len(stats) >= 2
        types = {s["execution_type"] for s in stats}
        assert "chat" in types
        assert "docker_action" in types


class TestExecutionWithNewFieldsDB:
    def test_create_execution_with_new_fields(self, mock_repo):
        exec_ = create_execution(
            mock_repo, "exec-nf-1", "Test", "admin",
            execution_type="docker_action",
            organization="org-123",
            agents=["agent1", "agent2"],
            audit_links={"audit": "/log/1"},
        )
        assert exec_.execution_type == "docker_action"
        assert exec_.organization == "org-123"
        assert exec_.agents == ["agent1", "agent2"]
        assert exec_.audit_links["audit"] == "/log/1"

        retrieved = get_execution(mock_repo, "exec-nf-1")
        assert retrieved is not None
        assert retrieved.execution_type == "docker_action"
        assert retrieved.organization == "org-123"
        assert retrieved.agents == ["agent1", "agent2"]

    def test_update_execution_preserves_new_fields(self, mock_repo):
        exec_ = create_execution(mock_repo, "exec-nf-2", "Test", "admin", execution_type="policy_check", organization="org-456")
        exec_.current_status = "completed"
        exec_.confidence = 0.99
        update_execution(mock_repo, exec_)
        retrieved = get_execution(mock_repo, "exec-nf-2")
        assert retrieved is not None
        assert retrieved.execution_type == "policy_check"
        assert retrieved.organization == "org-456"
        assert retrieved.current_status == "completed"
        assert retrieved.confidence == 0.99

    def test_list_executions_filter_by_type(self, mock_repo):
        create_execution(mock_repo, "exec-flt-1", "Chat req", "admin", execution_type="chat")
        create_execution(mock_repo, "exec-flt-2", "Docker action", "admin", execution_type="docker_action")
        create_execution(mock_repo, "exec-flt-3", "Another chat", "admin", execution_type="chat")
        chats = list_executions(mock_repo, execution_type="chat")
        assert len(chats) == 2
        dockers = list_executions(mock_repo, execution_type="docker_action")
        assert len(dockers) == 1

    def test_count_executions_filter_by_type(self, mock_repo):
        create_execution(mock_repo, "exec-cnt-1", "Chat", "admin", execution_type="chat")
        create_execution(mock_repo, "exec-cnt-2", "Policy", "admin", execution_type="policy_check")
        chat_count = count_executions(mock_repo, execution_type="chat")
        assert chat_count == 1
