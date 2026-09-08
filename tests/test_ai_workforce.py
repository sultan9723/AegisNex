"""Tests for AI Workforce — agent lifecycle, versions, prompts, permissions,
knowledge, executions, trust scoring, budget, health, clone, pause/resume."""

from __future__ import annotations

import json
import re
from unittest.mock import MagicMock

import pytest

from src.ai_workforce import (
    WorkforceManager, WorkforceAgent, AgentVersion, PromptVersion,
    ToolPermission, KnowledgeAssignment, WorkforceExecution, HealthRecord,
    LifecycleStatus, HealthStatus, ExecutionResult, PromptRole, AccessLevel,
    WorkforceExecutionBlocked, utc_now, new_id, ensure_all_tables,
    _calculate_trust_score, _calculate_success_rate, _calculate_avg_latency,
)

WORKFORCE_TABLES = (
    "workforce_agents", "workforce_agent_versions", "workforce_prompt_versions",
    "workforce_tool_permissions", "workforce_knowledge_assignments",
    "workforce_executions", "workforce_health_log",
)

# Column list per table for INSERT parsing
INSERT_COLUMNS: dict[str, list[str]] = {
    "workforce_agents": [
        "agent_id", "name", "description", "agent_type", "provider", "model",
        "version", "lifecycle_status", "trust_score", "confidence",
        "daily_budget", "monthly_budget", "total_cost", "success_rate",
        "average_latency_ms", "total_executions",
        "health_status", "health_last_checked", "tools", "permissions",
        "metadata", "tags", "owner", "team", "created_at", "updated_at", "last_active_at",
    ],
    "workforce_agent_versions": [
        "agent_id", "version", "config_snapshot", "prompt_ids", "change_summary", "created_by", "created_at",
    ],
    "workforce_prompt_versions": [
        "prompt_id", "agent_id", "name", "content", "version", "role", "variables", "hash", "description", "created_at",
    ],
    "workforce_tool_permissions": [
        "agent_id", "tool_name", "allowed", "config", "created_at", "updated_at",
    ],
    "workforce_knowledge_assignments": [
        "agent_id", "knowledge_source_id", "knowledge_source_type", "access_level", "priority", "created_at",
    ],
    "workforce_executions": [
        "execution_id", "agent_id", "task", "response", "latency_ms", "cost", "confidence",
        "tools_used", "status", "error", "prompt_version_id", "metadata", "created_at",
    ],
    "workforce_health_log": [
        "agent_id", "status", "check_type", "metric_value", "details", "checked_at",
    ],
}


# ---------------------------------------------------------------------------
# Mock repo fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def repo():
    """Mock PlatformRepository for workforce tests."""
    r = MagicMock()
    r.backend = "sqlite"
    r.placeholder = "?"
    r._stored_data: dict[str, list[dict]] = {}
    r._id_counter = 0

    def _table(sql: str) -> str | None:
        for t in WORKFORCE_TABLES:
            if t in sql:
                return t
        return None

    def table_exists(name: str) -> bool:
        return name in r._stored_data

    def mock_execute(sql: str, params=None):
        r._id_counter += 1
        params = list(params) if params else []
        is_create = "CREATE TABLE" in sql
        is_insert = "INSERT INTO" in sql or "INSERT OR REPLACE INTO" in sql
        is_update = "UPDATE " in sql and "UPDATE " == sql[:7]
        is_delete = "DELETE" in sql

        if is_create:
            for kw in WORKFORCE_TABLES:
                if kw in sql:
                    r._stored_data.setdefault(kw, [])
                    break
            return r._id_counter

        table = _table(sql)
        if not table:
            return r._id_counter

        if is_insert:
            cols = INSERT_COLUMNS.get(table, [])
            row: dict = {}
            for i, c in enumerate(cols):
                if i < len(params):
                    row[c] = params[i]
            r._stored_data.setdefault(table, []).append(row)
            return r._id_counter

        if is_update:
            # Extract SET column names from SQL
            # Pattern: UPDATE tbl SET col1=?, col2=?, ... WHERE agent_id=?
            # Note: '.' doesn't match newlines; use DOTALL for multi-line SET clauses
            set_match = re.search(r'SET\s+(.+?)\s*WHERE', sql, re.IGNORECASE | re.DOTALL)
            if set_match and params:
                set_part = set_match.group(1)
                cols = re.findall(r'(\w+)\s*=', set_part)
                # Last param is the WHERE value (agent_id)
                where_val = params[-1]
                set_params = params[:-1]
                for row in r._stored_data.get(table, []):
                    if row.get("agent_id") == where_val:
                        for i, col in enumerate(cols):
                            if i < len(set_params):
                                row[col] = set_params[i]
                        break
            return r._id_counter

        if is_delete:
            if params:
                aid = params[0]
                r._stored_data[table] = [
                    ro for ro in r._stored_data.get(table, [])
                    if ro.get("agent_id") != aid
                ]
            return r._id_counter

        return r._id_counter

    def _apply_where(rows: list[dict], sql: str, params: tuple) -> list[dict]:
        """Apply WHERE conditions from SQL to a list of rows.

        Handles:
        - Equality conditions (AND logic)
        - LIKE conditions (OR logic within each parenthesized group, case-insensitive)
        - Consumes LIMIT/OFFSET ? params
        """
        if "WHERE" not in sql or not params:
            return rows
        pi = 0
        where_part = sql.split("WHERE", 1)[1].strip()

        # Equality conditions: col = ?  (AND logic)
        for m in re.finditer(r'(\w+)\s*=\s*\?', where_part):
            col = m.group(1)
            if col == "id" or pi >= len(params):
                pi += 1
                continue
            val = params[pi]
            if isinstance(val, str):
                rows = [ro for ro in rows if str(ro.get(col, "")) == val]
            else:
                rows = [ro for ro in rows if ro.get(col) == val]
            pi += 1

        # LIKE conditions: col LIKE ?  (OR logic within group, case-insensitive)
        like_matches = list(re.finditer(r'(\w+)\s+LIKE\s+\?', where_part, re.IGNORECASE))
        if like_matches:
            new_rows = []
            for ro in rows:
                for i, m in enumerate(like_matches):
                    col = m.group(1)
                    idx = pi + i
                    if idx < len(params):
                        like_val = str(params[idx]).replace("%", "").lower()
                        if like_val in str(ro.get(col, "")).lower():
                            new_rows.append(ro)
                            break
            rows = new_rows
            pi += len(like_matches)

        # Consume LIMIT / OFFSET params (positional after WHERE values)
        for _ in re.finditer(r'\bLIMIT\s+\?|\bOFFSET\s+\?', where_part, re.IGNORECASE):
            if pi < len(params):
                pi += 1

        return rows

    def mock_fetch_all(sql: str, params=None):
        params = tuple(params) if params else ()
        table = _table(sql)
        if not table:
            return []
        all_rows = list(r._stored_data.get(table, []))

        # Aggregate queries (SUM / AVG / SUM(CASE...))
        if "SUM(" in sql or "AVG(" in sql:
            aggregated = _apply_where(all_rows, sql, params)
            total = len(aggregated)
            successes = sum(1 for ro in aggregated if ro.get("status") == "success")
            failures = sum(1 for ro in aggregated if ro.get("status") == "failed")
            avg_lat = sum(ro.get("latency_ms", 0) for ro in aggregated) / max(total, 1)
            avg_cost = sum(ro.get("cost", 0) for ro in aggregated) / max(total, 1)
            avg_conf = sum(ro.get("confidence", 0) for ro in aggregated) / max(total, 1)
            total_cost = sum(ro.get("cost", 0) for ro in aggregated)
            return [{
                "total": total, "successes": successes, "failures": failures,
                "avg_latency": avg_lat, "avg_cost": avg_cost,
                "avg_confidence": avg_conf, "total_cost": total_cost,
            }]

        # COUNT queries (standalone COUNT(*), not inside SUM(CASE...))
        if "COUNT(*)" in sql and "SUM(" not in sql:
            cnt_rows = _apply_where(all_rows, sql, params)
            return [{"cnt": len(cnt_rows), "mv": max((ro.get("version", 0) for ro in cnt_rows), default=0)}]

        # MAX(version) queries
        if "MAX(version)" in sql:
            max_rows = _apply_where(all_rows, sql, params)
            max_ver = max((ro.get("version", 0) for ro in max_rows), default=0)
            return [{"mv": max_ver}]

        # General SELECT
        rows = _apply_where(all_rows, sql, params)

        order_match = re.search(r'ORDER BY\s+(\w+)\s+(DESC|ASC)\b', sql, re.IGNORECASE)
        if order_match:
            col = order_match.group(1)
            desc = order_match.group(2).upper() == "DESC"
            rows = sorted(rows, key=lambda ro: str(ro.get(col, "")), reverse=desc)

        limit_match = re.search(r'LIMIT\s+(\d+)', sql, re.IGNORECASE)
        if limit_match:
            rows = rows[:int(limit_match.group(1))]

        return rows

    r.table_exists = table_exists
    r._execute = mock_execute
    r._fetch_all = mock_fetch_all
    return r


# =====================================================================
# Model Tests
# =====================================================================

class TestModels:
    def test_workforce_agent_creation(self):
        a = WorkforceAgent(agent_id="test-1", name="TestAgent", trust_score=75.0)
        assert a.agent_id == "test-1"
        assert a.name == "TestAgent"
        assert a.trust_score == 75.0
        assert a.lifecycle_status == LifecycleStatus.DRAFT.value

    def test_workforce_agent_to_dict(self):
        a = WorkforceAgent(agent_id="t1", name="T", tags=["prod"])
        d = a.to_dict()
        assert d["agent_id"] == "t1"
        assert d["tags"] == ["prod"]

    def test_workforce_agent_from_dict(self):
        a = WorkforceAgent.from_dict({"agent_id": "t2", "name": "Test", "trust_score": 88.0})
        assert a.agent_id == "t2"
        assert a.trust_score == 88.0
        assert a.lifecycle_status == LifecycleStatus.DRAFT.value

    def test_agent_version_creation(self):
        v = AgentVersion(agent_id="a1", version=1, change_summary="Initial")
        assert v.version == 1
        assert v.change_summary == "Initial"

    def test_prompt_version_creation(self):
        p = PromptVersion(prompt_id="p1", name="greeting", content="Hello", role="system")
        assert p.name == "greeting"
        assert p.role == "system"

    def test_tool_permission_creation(self):
        t = ToolPermission(agent_id="a1", tool_name="docker", allowed=False)
        assert t.tool_name == "docker"
        assert t.allowed is False

    def test_knowledge_assignment_creation(self):
        k = KnowledgeAssignment(agent_id="a1", knowledge_source_id="kb-1")
        assert k.knowledge_source_id == "kb-1"
        assert k.access_level == "read_write"

    def test_workforce_execution_creation(self):
        e = WorkforceExecution(execution_id="e1", agent_id="a1", task="test")
        assert e.status == ExecutionResult.SUCCESS.value

    def test_health_record_creation(self):
        h = HealthRecord(agent_id="a1", status="healthy", check_type="heartbeat", metric_value=1.0)
        assert h.status == "healthy"

    def test_utc_now_returns_string(self):
        now = utc_now()
        assert "T" in now
        assert now.endswith("Z")

    def test_new_id_generates_unique(self):
        ids = {new_id() for _ in range(100)}
        assert len(ids) == 100

    def test_enums_have_expected_values(self):
        assert LifecycleStatus.ACTIVE.value == "active"
        assert LifecycleStatus.PAUSED.value == "paused"
        assert HealthStatus.HEALTHY.value == "healthy"
        assert ExecutionResult.SUCCESS.value == "success"
        assert PromptRole.SYSTEM.value == "system"
        assert AccessLevel.READ_WRITE.value == "read_write"


# =====================================================================
# Trust score calculation tests
# =====================================================================

class TestTrustCalculation:
    def test_calculate_trust_score_all_success(self):
        execs = [WorkforceExecution(status="success", confidence=0.9) for _ in range(10)]
        score = _calculate_trust_score(execs, current_score=50.0)
        assert score > 60.0
        assert score <= 100.0

    def test_calculate_trust_score_all_failures(self):
        execs = [WorkforceExecution(status="failed", confidence=0.0) for _ in range(10)]
        score = _calculate_trust_score(execs, current_score=50.0)
        assert score < 50.0

    def test_calculate_trust_score_empty(self):
        score = _calculate_trust_score([], current_score=50.0)
        assert score == 50.0

    def test_calculate_success_rate(self):
        execs = [WorkforceExecution(status="success") for _ in range(7)] + [WorkforceExecution(status="failed") for _ in range(3)]
        rate = _calculate_success_rate(execs)
        assert rate == 70.0

    def test_calculate_success_rate_empty(self):
        assert _calculate_success_rate([]) == 100.0

    def test_calculate_avg_latency(self):
        execs = [WorkforceExecution(latency_ms=100.0), WorkforceExecution(latency_ms=200.0)]
        assert _calculate_avg_latency(execs) == 150.0

    def test_calculate_avg_latency_empty(self):
        assert _calculate_avg_latency([]) == 0.0


# =====================================================================
# WorkforceManager — Agent CRUD tests
# =====================================================================

class TestAgentCRUD:
    def test_register_agent(self, repo):
        mgr = WorkforceManager(repo)
        a = WorkforceAgent(name="TestBot", agent_type="monitoring")
        created = mgr.register_agent(a)
        assert created.agent_id
        assert created.name == "TestBot"
        assert created.lifecycle_status == "draft"

    def test_register_agent_sets_timestamps(self, repo):
        mgr = WorkforceManager(repo)
        a = WorkforceAgent(name="TimedBot")
        created = mgr.register_agent(a)
        assert created.created_at
        assert created.updated_at

    def test_get_agent_found(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="Finder"))
        found = mgr.get_agent(a.agent_id)
        assert found is not None
        assert found.name == "Finder"

    def test_get_agent_not_found(self, repo):
        mgr = WorkforceManager(repo)
        assert mgr.get_agent("nonexistent") is None

    def test_list_agents_empty(self, repo):
        mgr = WorkforceManager(repo)
        agents = mgr.list_agents()
        assert agents == []

    def test_list_agents_with_data(self, repo):
        mgr = WorkforceManager(repo)
        mgr.register_agent(WorkforceAgent(name="A", agent_type="general"))
        mgr.register_agent(WorkforceAgent(name="B", agent_type="security"))
        agents = mgr.list_agents()
        assert len(agents) == 2

    def test_list_agents_filter_by_type(self, repo):
        mgr = WorkforceManager(repo)
        mgr.register_agent(WorkforceAgent(name="A", agent_type="general"))
        mgr.register_agent(WorkforceAgent(name="B", agent_type="security"))
        agents = mgr.list_agents(agent_type="security")
        assert len(agents) == 1
        assert agents[0].name == "B"

    def test_list_agents_filter_by_status(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ActiveBot"))
        mgr.activate_agent(a.agent_id)
        mgr.register_agent(WorkforceAgent(name="DraftBot"))
        agents = mgr.list_agents(lifecycle_status="active")
        assert len(agents) == 1
        assert agents[0].name == "ActiveBot"

    def test_list_agents_search(self, repo):
        mgr = WorkforceManager(repo)
        mgr.register_agent(WorkforceAgent(name="AlphaBot", description="The alpha agent"))
        mgr.register_agent(WorkforceAgent(name="BetaBot"))
        agents = mgr.list_agents(search="Alpha")
        assert len(agents) == 1
        assert agents[0].name == "AlphaBot"

    def test_count_agents(self, repo):
        mgr = WorkforceManager(repo)
        mgr.register_agent(WorkforceAgent(name="A"))
        mgr.register_agent(WorkforceAgent(name="B"))
        assert mgr.count_agents() == 2

    def test_count_agents_filtered(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="A"))
        mgr.activate_agent(a.agent_id)
        mgr.register_agent(WorkforceAgent(name="B"))
        assert mgr.count_agents(lifecycle_status="active") == 1

    def test_update_agent(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="Original"))
        a.name = "Updated"
        a.trust_score = 95.0
        assert mgr.update_agent(a) is True
        updated = mgr.get_agent(a.agent_id)
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.trust_score == 95.0

    def test_update_agent_not_found(self, repo):
        mgr = WorkforceManager(repo)
        a = WorkforceAgent(agent_id="missing", name="Ghost")
        assert mgr.update_agent(a) is False

    def test_delete_agent(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="DeleteMe"))
        assert mgr.delete_agent(a.agent_id) is True
        assert mgr.get_agent(a.agent_id) is None

    def test_delete_agent_not_found(self, repo):
        mgr = WorkforceManager(repo)
        assert mgr.delete_agent("missing") is False

    def test_delete_agent_cascades(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="Cascade"))
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="test"))
        mgr.delete_agent(a.agent_id)
        assert len(mgr.list_executions(agent_id=a.agent_id)) == 0


# =====================================================================
# Lifecycle tests
# =====================================================================

class TestLifecycle:
    def test_activate_draft_agent(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ActivateMe"))
        activated = mgr.activate_agent(a.agent_id)
        assert activated is not None
        assert activated.lifecycle_status == "active"

    def test_activate_already_active(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ActiveBot"))
        mgr.activate_agent(a.agent_id)
        activated = mgr.activate_agent(a.agent_id)
        assert activated is not None
        assert activated.lifecycle_status == "active"

    def test_pause_active_agent(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="PauseMe"))
        mgr.activate_agent(a.agent_id)
        paused = mgr.pause_agent(a.agent_id)
        assert paused is not None
        assert paused.lifecycle_status == "paused"

    def test_pause_draft_agent_fails(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="DraftBot"))
        assert mgr.pause_agent(a.agent_id) is None

    def test_resume_paused_agent(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ResumeMe"))
        mgr.activate_agent(a.agent_id)
        mgr.pause_agent(a.agent_id)
        resumed = mgr.resume_agent(a.agent_id)
        assert resumed is not None
        assert resumed.lifecycle_status == "active"

    def test_resume_active_agent_fails(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ActiveBot"))
        mgr.activate_agent(a.agent_id)
        assert mgr.resume_agent(a.agent_id) is None

    def test_archive_agent(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ArchiveMe"))
        archived = mgr.archive_agent(a.agent_id)
        assert archived is not None
        assert archived.lifecycle_status == "archived"

    def test_cannot_activate_archived(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ArchivedBot"))
        mgr.archive_agent(a.agent_id)
        assert mgr.activate_agent(a.agent_id) is None


# =====================================================================
# Clone tests
# =====================================================================

class TestClone:
    def test_clone_agent_basic(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="Original", agent_type="security", tags=["prod"]))
        cloned = mgr.clone_agent(a.agent_id)
        assert cloned is not None
        assert cloned.name == "Original (Clone)"
        assert cloned.agent_type == "security"
        assert cloned.tags == ["prod"]
        assert cloned.lifecycle_status == "draft"

    def test_clone_agent_custom_name(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="Original"))
        cloned = mgr.clone_agent(a.agent_id, new_name="Custom Clone")
        assert cloned is not None
        assert cloned.name == "Custom Clone"

    def test_clone_nonexistent(self, repo):
        mgr = WorkforceManager(repo)
        assert mgr.clone_agent("missing") is None

    def test_clone_copies_tool_permissions(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="Source"))
        mgr.set_tool_permission(a.agent_id, "docker", True)
        cloned = mgr.clone_agent(a.agent_id)
        assert cloned is not None
        tools = mgr.get_tool_permissions(cloned.agent_id)
        assert any(t.tool_name == "docker" and t.allowed for t in tools)

    def test_clone_copies_knowledge(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="Source"))
        mgr.assign_knowledge(a.agent_id, "kb-1")
        cloned = mgr.clone_agent(a.agent_id)
        assert cloned is not None
        ka = mgr.list_knowledge_assignments(cloned.agent_id)
        assert any(k.knowledge_source_id == "kb-1" for k in ka)


# =====================================================================
# Version tests
# =====================================================================

class TestVersions:
    def test_create_agent_version(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="VersionBot"))
        v = mgr.create_agent_version(a.agent_id, "First version", "tester")
        assert v is not None
        assert v.version == 1
        assert v.change_summary == "First version"
        assert v.created_by == "tester"

    def test_create_version_nonexistent_agent(self, repo):
        mgr = WorkforceManager(repo)
        assert mgr.create_agent_version("missing") is None

    def test_list_agent_versions(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="VersionBot"))
        mgr.create_agent_version(a.agent_id, "v1")
        mgr.create_agent_version(a.agent_id, "v2")
        versions = mgr.list_agent_versions(a.agent_id)
        assert len(versions) == 2
        assert versions[0].version == 2  # DESC order

    def test_get_agent_version(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="VersionBot"))
        mgr.create_agent_version(a.agent_id, "v1")
        v = mgr.get_agent_version(a.agent_id, 1)
        assert v is not None
        assert v.version == 1

    def test_get_agent_version_not_found(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="VersionBot"))
        assert mgr.get_agent_version(a.agent_id, 99) is None

    def test_restore_agent_version(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="RestoreBot", trust_score=50.0, model="gpt-4o-mini"))
        a.trust_score = 90.0
        mgr.update_agent(a)
        mgr.create_agent_version(a.agent_id, "Improved trust")
        a.trust_score = 30.0
        mgr.update_agent(a)
        restored = mgr.restore_agent_version(a.agent_id, 1)
        assert restored is not None
        assert restored.trust_score == 90.0

    def test_restore_agent_version_not_found(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="Bot"))
        assert mgr.restore_agent_version(a.agent_id, 99) is None


# =====================================================================
# Prompt version tests
# =====================================================================

class TestPromptVersions:
    def test_save_prompt_version(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="PromptBot"))
        p = mgr.save_prompt_version(a.agent_id, "system_prompt", "You are helpful", "system")
        assert p.prompt_id
        assert p.version == 1
        assert p.hash

    def test_save_prompt_version_increments(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="PromptBot"))
        mgr.save_prompt_version(a.agent_id, "greeting", "Hello", "system")
        p2 = mgr.save_prompt_version(a.agent_id, "greeting", "Hi there", "system")
        assert p2.version == 2

    def test_get_prompt_version(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="PromptBot"))
        saved = mgr.save_prompt_version(a.agent_id, "test", "content")
        found = mgr.get_prompt_version(saved.prompt_id)
        assert found is not None
        assert found.content == "content"

    def test_list_prompt_versions_by_agent(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="PromptBot"))
        mgr.save_prompt_version(a.agent_id, "p1", "c1")
        mgr.save_prompt_version(a.agent_id, "p2", "c2")
        prompts = mgr.list_prompt_versions(agent_id=a.agent_id)
        assert len(prompts) == 2


# =====================================================================
# Tool permission tests
# =====================================================================

class TestToolPermissions:
    def test_set_tool_permission_create(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ToolBot"))
        perm = mgr.set_tool_permission(a.agent_id, "docker", True)
        assert perm.tool_name == "docker"
        assert perm.allowed is True

    def test_set_tool_permission_update(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ToolBot"))
        mgr.set_tool_permission(a.agent_id, "docker", True)
        perm = mgr.set_tool_permission(a.agent_id, "docker", False)
        assert perm.allowed is False

    def test_get_tool_permissions(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ToolBot"))
        mgr.set_tool_permission(a.agent_id, "docker", True)
        mgr.set_tool_permission(a.agent_id, "kubernetes", False)
        tools = mgr.get_tool_permissions(a.agent_id)
        assert len(tools) == 2
        assert any(t.tool_name == "docker" and t.allowed for t in tools)
        assert any(t.tool_name == "kubernetes" and not t.allowed for t in tools)

    def test_delete_tool_permission(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ToolBot"))
        mgr.set_tool_permission(a.agent_id, "docker", True)
        assert mgr.delete_tool_permission(a.agent_id, "docker") is True
        assert len(mgr.get_tool_permissions(a.agent_id)) == 0


# =====================================================================
# Knowledge assignment tests
# =====================================================================

class TestKnowledge:
    def test_assign_knowledge(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="KnowledgeBot"))
        ka = mgr.assign_knowledge(a.agent_id, "kb-1", "collection", "read")
        assert ka.knowledge_source_id == "kb-1"
        assert ka.access_level == "read"

    def test_list_knowledge_assignments(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="KnowledgeBot"))
        mgr.assign_knowledge(a.agent_id, "kb-1")
        mgr.assign_knowledge(a.agent_id, "kb-2")
        assignments = mgr.list_knowledge_assignments(a.agent_id)
        assert len(assignments) == 2

    def test_remove_knowledge_assignment(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="KnowledgeBot"))
        mgr.assign_knowledge(a.agent_id, "kb-1")
        assert mgr.remove_knowledge_assignment(a.agent_id, "kb-1") is True
        assert len(mgr.list_knowledge_assignments(a.agent_id)) == 0


# =====================================================================
# Execution tests
# =====================================================================

class TestExecutions:
    def test_record_execution(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ExecBot"))
        mgr.activate_agent(a.agent_id)
        e = mgr.record_execution(WorkforceExecution(
            agent_id=a.agent_id, task="Test task", latency_ms=150.0, cost=0.002, confidence=0.95,
        ))
        assert e.execution_id
        assert e.status == "success"

    def test_record_execution_updates_agent_stats(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="StatBot"))
        mgr.activate_agent(a.agent_id)
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="t1", latency_ms=100, cost=0.001, confidence=0.9, status="success"))
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="t2", latency_ms=200, cost=0.002, confidence=0.8, status="success"))
        updated = mgr.get_agent(a.agent_id)
        assert updated is not None
        assert updated.total_executions == 2
        assert updated.average_latency_ms == 150.0

    def test_record_execution_tracks_cost(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="CostBot"))
        mgr.activate_agent(a.agent_id)
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="t", cost=0.005, status="success"))
        updated = mgr.get_agent(a.agent_id)
        assert updated is not None
        assert updated.total_cost == 0.005

    def test_list_executions(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ExecBot"))
        mgr.activate_agent(a.agent_id)
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="t1"))
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="t2"))
        execs = mgr.list_executions(agent_id=a.agent_id)
        assert len(execs) == 2

    def test_list_executions_filter_by_status(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ExecBot"))
        mgr.activate_agent(a.agent_id)
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="good", status="success"))
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="bad", status="failed"))
        failed = mgr.list_executions(agent_id=a.agent_id, status="failed")
        assert len(failed) == 1
        assert failed[0].task == "bad"

    def test_get_execution_stats(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="StatBot"))
        mgr.activate_agent(a.agent_id)
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="t1", latency_ms=100, cost=0.001, confidence=0.9, status="success"))
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="t2", latency_ms=200, cost=0.002, confidence=0.8, status="failed"))
        stats = mgr.get_execution_stats(agent_id=a.agent_id)
        assert stats["total"] == 2
        assert stats["successes"] == 1
        assert stats["failures"] == 1
        assert stats["avg_latency"] == 150.0

    def test_get_execution_stats_global(self, repo):
        mgr = WorkforceManager(repo)
        a1 = mgr.register_agent(WorkforceAgent(name="Bot1"))
        a2 = mgr.register_agent(WorkforceAgent(name="Bot2"))
        mgr.activate_agent(a1.agent_id)
        mgr.activate_agent(a2.agent_id)
        mgr.record_execution(WorkforceExecution(agent_id=a1.agent_id, task="t1", status="success"))
        mgr.record_execution(WorkforceExecution(agent_id=a2.agent_id, task="t2", status="success"))
        stats = mgr.get_execution_stats()  # no agent_id filter
        assert stats["total"] >= 2  # may include other tests
        assert stats["successes"] >= 2


# =====================================================================
# Health tests
# =====================================================================

class TestHealth:
    def test_record_health_check(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="HealthBot"))
        h = mgr.record_health_check(a.agent_id, "healthy", "heartbeat", 1.0)
        assert h.status == "healthy"
        assert h.check_type == "heartbeat"

    def test_record_health_check_updates_agent(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="HealthBot"))
        mgr.record_health_check(a.agent_id, "degraded", "response_time", 5000)
        updated = mgr.get_agent(a.agent_id)
        assert updated is not None
        assert updated.health_status == "degraded"

    def test_get_health_history(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="HealthBot"))
        mgr.record_health_check(a.agent_id, "healthy")
        mgr.record_health_check(a.agent_id, "degraded")
        history = mgr.get_health_history(a.agent_id)
        assert len(history) == 2

    def test_get_latest_health(self, repo):
        import time
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="HealthBot"))
        mgr.record_health_check(a.agent_id, "healthy")
        time.sleep(0.002)
        mgr.record_health_check(a.agent_id, "degraded")
        latest = mgr.get_latest_health(a.agent_id)
        assert latest is not None
        assert latest.status == "degraded"

    def test_get_latest_health_none(self, repo):
        mgr = WorkforceManager(repo)
        assert mgr.get_latest_health("no-agent") is None


# =====================================================================
# Budget tests
# =====================================================================

class TestBudget:
    def test_get_budget_usage_no_executions(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="BudgetBot", daily_budget=50, monthly_budget=1000))
        usage = mgr.get_budget_usage(a.agent_id)
        assert usage["daily_used"] == 0
        assert usage["monthly_used"] == 0
        assert usage["daily_budget"] == 50
        assert usage["monthly_budget"] == 1000

    def test_get_budget_usage_with_executions(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="BudgetBot", daily_budget=50, monthly_budget=1000))
        mgr.activate_agent(a.agent_id)
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="t", cost=1.5, status="success"))
        usage = mgr.get_budget_usage(a.agent_id)
        assert usage["daily_budget"] == 50
        assert usage["monthly_budget"] == 1000

    def test_budget_agent_not_found(self, repo):
        mgr = WorkforceManager(repo)
        usage = mgr.get_budget_usage("missing")
        assert usage["daily_budget"] == 0


# =====================================================================
# Workforce stats tests
# =====================================================================

class TestWorkforceStats:
    def test_get_workforce_stats_empty(self, repo):
        mgr = WorkforceManager(repo)
        stats = mgr.get_workforce_stats()
        assert stats["total_agents"] == 0

    def test_get_workforce_stats_counts_types(self, repo):
        mgr = WorkforceManager(repo)
        mgr.register_agent(WorkforceAgent(name="A", agent_type="security"))
        mgr.register_agent(WorkforceAgent(name="B", agent_type="general"))
        stats = mgr.get_workforce_stats()
        assert stats["total_agents"] == 2
        assert stats["by_type"]["security"] == 1
        assert stats["by_type"]["general"] == 1

    def test_get_workforce_stats_lifecycle_counts(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="A"))
        mgr.activate_agent(a.agent_id)
        mgr.register_agent(WorkforceAgent(name="B"))
        stats = mgr.get_workforce_stats()
        assert stats["active_agents"] == 1
        assert stats["draft_agents"] == 1

    def test_get_workforce_stats_with_executions(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="A"))
        mgr.activate_agent(a.agent_id)
        mgr.record_execution(WorkforceExecution(agent_id=a.agent_id, task="t", status="success"))
        stats = mgr.get_workforce_stats()
        assert stats["total_executions"] >= 1


# =====================================================================
# Playground tests
# =====================================================================

class TestPlayground:
    def test_playground_execute_simulated(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="PlayBot"))
        mgr.activate_agent(a.agent_id)
        result = mgr.playground_execute(a.agent_id, "Hello world", simulate=True)
        assert result.status == "success"
        assert result.task == "Hello world"
        assert "Playground" in (result.response or "")

    def test_playground_execute_nonexistent_agent(self, repo):
        mgr = WorkforceManager(repo)
        with pytest.raises(ValueError, match="not found"):
            mgr.playground_execute("no-such-agent", "test")

    def test_playground_records_execution(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="PlayBot"))
        mgr.activate_agent(a.agent_id)
        result = mgr.playground_execute(a.agent_id, "test", simulate=True)
        execs = mgr.list_executions(agent_id=a.agent_id)
        assert any(e.execution_id == result.execution_id for e in execs)

    def test_playground_blocks_inactive_agent(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="PausedBot"))
        with pytest.raises(WorkforceExecutionBlocked, match="agent_not_active"):
            mgr.playground_execute(a.agent_id, "test", simulate=True)

    def test_playground_blocks_exhausted_budget(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="BudgetBot", daily_budget=0, monthly_budget=0))
        mgr.activate_agent(a.agent_id)
        with pytest.raises(WorkforceExecutionBlocked, match="budget_exceeded"):
            mgr.playground_execute(a.agent_id, "test", simulate=True)

    def test_live_playground_blocks_disallowed_tool(self, repo):
        mgr = WorkforceManager(repo)
        a = mgr.register_agent(WorkforceAgent(name="ToolBot", tools=[{"name": "docker"}]))
        mgr.activate_agent(a.agent_id)
        mgr.set_tool_permission(a.agent_id, "docker", False)
        with pytest.raises(WorkforceExecutionBlocked, match="tool_not_allowed"):
            mgr.require_tool_allowed(a.agent_id, "docker")


# =====================================================================
# Wizard tests
# =====================================================================

class TestWizard:
    def test_create_agent_wizard_basic(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="WizardBot",
            agent_type="security",
            description="Created by wizard",
            owner="admin@test.com",
        )
        assert agent.name == "WizardBot"
        assert agent.lifecycle_status == "draft"
        assert agent.owner == "admin@test.com"

    def test_create_agent_wizard_with_system_prompt(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="PromptBot",
            system_prompt="You are a security assistant",
        )
        prompts = mgr.list_prompt_versions(agent_id=agent.agent_id)
        assert len(prompts) >= 1
        assert prompts[0].name == "system_prompt"

    def test_create_agent_wizard_with_tools(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="ToolBot",
            tools=[{"name": "docker", "allowed": True}, {"name": "kubernetes", "allowed": False}],
        )
        tools = mgr.get_tool_permissions(agent.agent_id)
        assert len(tools) == 2
        assert any(t.tool_name == "docker" and t.allowed for t in tools)
        assert any(t.tool_name == "kubernetes" and not t.allowed for t in tools)

    def test_create_agent_wizard_with_knowledge(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="KnowledgeBot",
            knowledge_sources=["kb-1", "kb-2"],
        )
        ka = mgr.list_knowledge_assignments(agent.agent_id)
        assert len(ka) == 2

    def test_create_agent_wizard_creates_initial_version(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(name="VersionBot")
        versions = mgr.list_agent_versions(agent.agent_id)
        assert len(versions) >= 1
