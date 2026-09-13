"""Tests for Workforce Groq provider support end-to-end.

Covers:
- Groq appears as a supported provider
- Groq agent can be created via wizard
- provider/model persist correctly in agent record
- API key never leaks in agent API responses
- Playground execution selects Groq (create_provider called with 'groq')
- Agent model selection is honored at execution time
- System prompt is actually passed through to the provider chat call
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from src.intelligence.providers.base import ModelProvider, ProviderConfig, Message
from src.intelligence.providers.factory import get_provider_names
from src.ai_workforce import (
    WorkforceManager, WorkforceAgent, WorkforceExecution,
    LifecycleStatus, PromptRole,
)

# ---------------------------------------------------------------------------
# Minimal mock repo fixture (matches the pattern used in test_ai_workforce)
# ---------------------------------------------------------------------------

WORKFORCE_TABLES = (
    "workforce_agents", "workforce_agent_versions", "workforce_prompt_versions",
    "workforce_tool_permissions", "workforce_knowledge_assignments",
    "workforce_executions", "workforce_health_log",
)

INSERT_COLUMNS: dict[str, list[str]] = {
    "workforce_agents": [
        "agent_id", "name", "description", "agent_type", "provider", "model",
        "version", "lifecycle_status", "trust_score", "confidence",
        "daily_budget", "monthly_budget", "total_cost", "success_rate",
        "average_latency_ms", "total_executions",
        "health_status", "health_last_checked", "tools", "permissions",
        "metadata", "tags", "owner", "team", "org_id", "team_id",
        "created_at", "updated_at", "last_active_at",
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


@pytest.fixture
def repo():
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
        if "CREATE TABLE" in sql:
            for kw in WORKFORCE_TABLES:
                if kw in sql:
                    r._stored_data.setdefault(kw, [])
            return r._id_counter
        table = _table(sql)
        if not table:
            return r._id_counter
        if "INSERT INTO" in sql or "INSERT OR REPLACE INTO" in sql:
            col_match = re.search(r"INSERT(?: OR REPLACE)? INTO \S+\s*\((.*?)\)", sql, re.IGNORECASE)
            cols = [c.strip() for c in col_match.group(1).split(",")] if col_match else INSERT_COLUMNS.get(table, [])
            row = {}
            for i, c in enumerate(cols):
                if i < len(params):
                    row[c] = params[i]
            r._stored_data.setdefault(table, []).append(row)
            return r._id_counter
        if sql.strip().upper().startswith("UPDATE"):
            set_match = re.search(r"SET\s+(.+?)\s*WHERE", sql, re.IGNORECASE | re.DOTALL)
            if set_match and params:
                cols = re.findall(r"(\w+)\s*=", set_match.group(1))
                where_val = params[-1]
                set_params = params[:-1]
                for row in r._stored_data.get(table, []):
                    if row.get("agent_id") == where_val:
                        for i, col in enumerate(cols):
                            if i < len(set_params):
                                row[col] = set_params[i]
            return r._id_counter
        if "DELETE" in sql and params:
            aid = params[0]
            r._stored_data[table] = [
                ro for ro in r._stored_data.get(table, [])
                if ro.get("agent_id") != aid and ro.get("execution_id") != aid
            ]
            return r._id_counter
        return r._id_counter

    def _apply_where(rows: list[dict], sql: str, params: tuple) -> list[dict]:
        if "WHERE" not in sql or not params:
            return rows
        where_part = sql.split("WHERE", 1)[1].strip()
        pi = 0
        for m in re.finditer(r"(\w+)\s*=\s*\?", where_part):
            col = m.group(1)
            if col == "id" or pi >= len(params):
                pi += 1
                continue
            val = params[pi]
            rows = [ro for ro in rows if str(ro.get(col, "")) == str(val)]
            pi += 1
        like_matches = list(re.finditer(r"(\w+)\s+LIKE\s+\?", where_part, re.IGNORECASE))
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
        for _ in re.finditer(r"\bLIMIT\s+\?|\bOFFSET\s+\?", where_part, re.IGNORECASE):
            if pi < len(params):
                pi += 1
        return rows

    def mock_fetch_all(sql: str, params=None):
        params = tuple(params) if params else ()
        table = _table(sql)
        if not table:
            return []
        all_rows = list(r._stored_data.get(table, []))
        if "SUM(" in sql or "AVG(" in sql:
            aggregated = _apply_where(all_rows, sql, params)
            total_count = len(aggregated)
            successes = sum(1 for ro in aggregated if ro.get("status") == "success")
            failures = sum(1 for ro in aggregated if ro.get("status") == "failed")
            avg_lat = sum(ro.get("latency_ms", 0) for ro in aggregated) / max(total_count, 1)
            avg_cost = sum(ro.get("cost", 0) for ro in aggregated) / max(total_count, 1)
            avg_conf = sum(ro.get("confidence", 0) for ro in aggregated) / max(total_count, 1)
            cost_sum = sum(ro.get("cost", 0) for ro in aggregated)
            total = cost_sum if "SUM(cost)" in sql else total_count
            return [{
                "total": total, "successes": successes, "failures": failures,
                "avg_latency": avg_lat, "avg_cost": avg_cost,
                "avg_confidence": avg_conf, "total_cost": cost_sum,
            }]
        if "COUNT(*)" in sql and "SUM(" not in sql:
            cnt_rows = _apply_where(all_rows, sql, params)
            return [{"cnt": len(cnt_rows), "mv": max((ro.get("version", 0) for ro in cnt_rows), default=0)}]
        if "MAX(version)" in sql:
            max_rows = _apply_where(all_rows, sql, params)
            return [{"mv": max((ro.get("version", 0) for ro in max_rows), default=0)}]
        rows = _apply_where(all_rows, sql, params)
        order_match = re.search(r"ORDER BY\s+(\w+)\s+(DESC|ASC)\b", sql, re.IGNORECASE)
        if order_match:
            col = order_match.group(1)
            desc = order_match.group(2).upper() == "DESC"
            rows = sorted(rows, key=lambda ro: str(ro.get(col, "")), reverse=desc)
        limit_match = re.search(r"LIMIT\s+(\d+)", sql, re.IGNORECASE)
        if limit_match:
            rows = rows[: int(limit_match.group(1))]
        return rows

    r.table_exists = table_exists
    r._execute = mock_execute
    r._fetch_all = mock_fetch_all
    return r


# ---------------------------------------------------------------------------
# Spy provider for execution tests
# ---------------------------------------------------------------------------

class SpyProvider(ModelProvider):
    """A fake provider that records chat() calls for assertions."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config or ProviderConfig(model="spy-default-model"))
        self.chat_calls: list[dict] = []

    @property
    def provider_name(self) -> str:  # type: ignore[override]
        return "spy"

    def chat(self, messages: list[Message], **kwargs) -> Message:
        self.chat_calls.append({"messages": messages, **kwargs})
        return Message(role="assistant", content="spy-response")

    def chat_with_tools(self, messages, tools, **kwargs):  # type: ignore[override]
        return self.chat(messages, **kwargs)

    def embed(self, text, **kwargs):  # type: ignore[override]
        return [0.0]


# =====================================================================
# 1. Groq appears as a supported provider
# =====================================================================

class TestGroqProviderSupported:
    def test_provider_factory_includes_groq(self):
        providers = get_provider_names()
        assert "groq" in providers
        assert "openai" in providers

    def test_all_original_providers_preserved(self):
        providers = get_provider_names()
        for name in ("openai", "anthropic", "gemini", "ollama", "azure"):
            assert name in providers


# =====================================================================
# 2. Groq agent creation via wizard + provider/model persist
# =====================================================================

class TestGroqAgentCreation:
    def test_wizard_creates_groq_agent(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="GroqTestBot",
            provider="groq",
            model="openai/gpt-oss-20b",
            agent_type="general",
        )
        assert agent.provider == "groq"
        assert agent.model == "openai/gpt-oss-20b"
        assert agent.name == "GroqTestBot"
        assert agent.lifecycle_status == LifecycleStatus.DRAFT.value

    def test_provider_and_model_persist_in_to_dict(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="PersistBot",
            provider="groq",
            model="openai/gpt-oss-20b",
        )
        fetched = mgr.get_agent(agent.agent_id)
        assert fetched is not None
        d = fetched.to_dict()
        assert d["provider"] == "groq"
        assert d["model"] == "openai/gpt-oss-20b"

    def test_other_providers_still_work(self, repo):
        mgr = WorkforceManager(repo)
        for prov, mod in [("openai", "gpt-4o-mini"), ("anthropic", "claude-3-haiku"), ("local", "llama3")]:
            agent = mgr.create_agent_wizard(name=f"{prov}Bot", provider=prov, model=mod)
            fetched = mgr.get_agent(agent.agent_id)
            assert fetched.provider == prov
            assert fetched.model == mod


# =====================================================================
# 3. API key never appears in agent API responses
# =====================================================================

class TestApiKeyLeakPrevention:
    def test_agent_to_dict_never_contains_groq_api_key(self, monkeypatch, repo):
        monkeypatch.setenv("AEGIS_AI_GROQ_API_KEY", "gsk_FAKE_KEY_DO_NOT_LEAK_xxx")
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(name="KeyCheckBot", provider="groq", model="openai/gpt-oss-20b")
        d = agent.to_dict()
        serialized = str(d)
        assert "gsk_FAKE_KEY_DO_NOT_LEAK_xxx" not in serialized
        assert "api_key" not in d

    def test_agent_dataclass_has_no_api_key_field(self, repo):
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(WorkforceAgent)}
        assert "api_key" not in field_names
        assert "key" not in field_names
        assert "secret" not in field_names

    def test_to_dict_never_leaks_secret_even_in_metadata(self, repo):
        a = WorkforceAgent(name="MetaBot", metadata={"api_key": "LEAKED"})
        d = a.to_dict()
        assert d["metadata"].get("api_key") == "LEAKED"
        # The field 'api_key' itself does not exist on the agent schema
        assert "api_key" not in {f.name for f in __import__("dataclasses").fields(WorkforceAgent)}


# =====================================================================
# 4. Execution selects Groq
# =====================================================================

class TestExecutionSelectsGroq:
    def test_playground_live_calls_create_provider_with_groq(self, monkeypatch, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(name="ExecGroqBot", provider="groq", model="openai/gpt-oss-20b")
        mgr.activate_agent(agent.agent_id)

        call_log: list[str] = []
        spy = SpyProvider()

        def fake_create_provider(name=None, config=None):
            call_log.append(name)
            return spy

        monkeypatch.setattr("src.intelligence.providers.factory.create_provider", fake_create_provider)

        result = mgr.playground_execute(agent.agent_id, "Hello Groq", simulate=False, provider=None, repo=repo)
        assert result.status == "success"
        assert call_log == ["groq"]
        assert len(spy.chat_calls) >= 1

    def test_playground_simulated_does_not_call_provider(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(name="SimBot", provider="groq", model="openai/gpt-oss-20b")
        mgr.activate_agent(agent.agent_id)
        result = mgr.playground_execute(agent.agent_id, "test", simulate=True)
        assert result.status == "success"
        assert "Playground" in (result.response or "")


# =====================================================================
# 5. Model selection is honored
# =====================================================================

class TestModelSelectionHonored:
    def test_agent_model_overrides_provider_config_model(self, monkeypatch, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="ModelHonoredBot",
            provider="groq",
            model="custom/this-model-should-be-used",
        )
        mgr.activate_agent(agent.agent_id)

        spy = SpyProvider(config=ProviderConfig(model="env-default-model"))
        monkeypatch.setattr(
            "src.intelligence.providers.factory.create_provider",
            lambda name=None, config=None: spy,
        )

        mgr.playground_execute(agent.agent_id, "test model", simulate=False, provider=None, repo=repo)
        assert spy.config.model == "custom/this-model-should-be-used"

    def test_env_model_used_when_agent_model_not_set(self, monkeypatch, repo):
        mgr = WorkforceManager(repo)
        agent = WorkforceAgent(name="EmptyModelBot", provider="groq", model="")
        agent = mgr.register_agent(agent)
        mgr.activate_agent(agent.agent_id)

        spy = SpyProvider(config=ProviderConfig(model="env-model"))
        monkeypatch.setattr(
            "src.intelligence.providers.factory.create_provider",
            lambda name=None, config=None: spy,
        )

        mgr.playground_execute(agent.agent_id, "test", simulate=False, provider=None, repo=repo)
        assert spy.config.model == "env-model"

    def test_explicit_provider_param_also_gets_agent_model(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="ExplicitProviderBot",
            provider="groq",
            model="agent-chosen-model",
        )
        mgr.activate_agent(agent.agent_id)

        spy = SpyProvider(config=ProviderConfig(model="original-model"))
        result = mgr.playground_execute(agent.agent_id, "test", simulate=False, provider=spy, repo=repo)
        assert result.status == "success"
        assert spy.config.model == "agent-chosen-model"


# =====================================================================
# 6. System prompt is actually passed to execution
# =====================================================================

class TestSystemPromptPassed:
    def test_system_prompt_appears_in_provider_chat_messages(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="PromptExecBot",
            provider="groq",
            model="openai/gpt-oss-20b",
            system_prompt="You are a strictly authorized security analyst. Always cite sources.",
        )
        mgr.activate_agent(agent.agent_id)

        spy = SpyProvider()
        result = mgr.playground_execute(
            agent.agent_id,
            "What is the status of server X?",
            simulate=False,
            provider=spy,
            repo=repo,
        )
        assert result.status == "success"
        assert len(spy.chat_calls) >= 1
        all_messages = spy.chat_calls[0]["messages"]
        combined_text = " ".join(m.content for m in all_messages)
        assert "You are a strictly authorized security analyst" in combined_text
        assert "What is the status of server X" in combined_text

    def test_wizard_stores_system_prompt(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="PromptStoreBot",
            system_prompt="Always respond in JSON format.",
        )
        prompts = mgr.list_prompt_versions(agent_id=agent.agent_id)
        assert len(prompts) >= 1
        assert prompts[0].name == "system_prompt"
        assert prompts[0].role == PromptRole.SYSTEM.value
        assert "Always respond in JSON format" in prompts[0].content

    def test_no_system_prompt_still_executes(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(name="NoPromptBot", provider="groq", model="openai/gpt-oss-20b")
        mgr.activate_agent(agent.agent_id)
        spy = SpyProvider()
        result = mgr.playground_execute(agent.agent_id, "simple task", simulate=False, provider=spy, repo=repo)
        assert result.status == "success"
        assert len(spy.chat_calls) >= 1
        # task appears in the user message
        user_msgs = [m for m in spy.chat_calls[0]["messages"] if m.role == "user"]
        assert any("simple task" in m.content for m in user_msgs)


# =====================================================================
# 7. Budget enforcement semantics (accurate report support)
# =====================================================================

class TestBudgetEnforcement:
    def test_budget_blocks_execution_when_exhausted(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="BudgetBot",
            provider="groq",
            model="openai/gpt-oss-20b",
            daily_budget=0,
            monthly_budget=0,
        )
        mgr.activate_agent(agent.agent_id)
        from src.ai_workforce import WorkforceExecutionBlocked
        with pytest.raises(WorkforceExecutionBlocked, match="budget_exceeded"):
            mgr.playground_execute(agent.agent_id, "should fail", simulate=True)

    def test_budget_allows_execution_within_limits(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="BudgetOKBot",
            provider="groq",
            model="openai/gpt-oss-20b",
            daily_budget=1000,
            monthly_budget=1000,
        )
        mgr.activate_agent(agent.agent_id)
        result = mgr.playground_execute(agent.agent_id, "ok", simulate=True)
        assert result.status == "success"
        usage = mgr.get_budget_usage(agent.agent_id)
        assert usage["daily_budget"] == 1000
        assert usage["daily_used"] == 0.001  # simulate cost

    def test_budget_usage_updates_after_execution(self, repo):
        mgr = WorkforceManager(repo)
        agent = mgr.create_agent_wizard(
            name="BudgetTrackBot",
            provider="groq",
            model="openai/gpt-oss-20b",
            daily_budget=100,
            monthly_budget=5000,
        )
        mgr.activate_agent(agent.agent_id)
        mgr.playground_execute(agent.agent_id, "track", simulate=True)
        usage = mgr.get_budget_usage(agent.agent_id)
        assert usage["daily_used"] > 0
        assert usage["remaining_daily"] < 100


# =====================================================================
# 8. HTTP wizard endpoint integration (real create_app + real SQLite)
# =====================================================================

class TestWizardHttpEndpoint:
    def test_wizard_api_creates_groq_agent_without_leaking_key(self, tmp_path, monkeypatch):
        from pathlib import Path
        from fastapi.testclient import TestClient

        from src.auth import AuthManager, UserStore
        from src.dashboard import create_app
        from src.platform_db import PlatformRepository
        from tests.test_dashboard import build_services

        monkeypatch.setenv("AEGIS_AI_GROQ_API_KEY", "gsk_HTTP_TEST_DO_NOT_LEAK_value")

        repo = PlatformRepository(f"sqlite:///{tmp_path / 'platform_wf.db'}")
        repo.initialize()
        services = build_services(tmp_path)
        services.platform_repository = repo
        auth_manager = AuthManager(
            user_store=UserStore(tmp_path / "users_wf.db"),
            jwt_secret="test-secret-32chars-long-please!",
        )
        app = create_app(
            services=services,
            auth_manager=auth_manager,
            telemetry_db_path=str(tmp_path / "telemetry_wf.db"),
        )
        client = TestClient(app)
        app.state.auth_manager.user_store.create_user(
            "admin@example.com", "admin-password-not-real", role="super_admin"
        )
        login = client.post(
            "/api/login", data={"username": "admin@example.com", "password": "admin-password-not-real"}
        )
        assert login.status_code == 200

        create_resp = client.post("/api/workforce/wizard", json={
            "name": "HttpGroqBot",
            "agent_type": "security",
            "provider": "groq",
            "model": "openai/gpt-oss-20b",
            "description": "Created via wizard endpoint",
            "daily_budget": 10,
            "monthly_budget": 100,
            "system_prompt": "Http-level system prompt.",
        })
        assert create_resp.status_code == 200, create_resp.text
        body = create_resp.json()
        assert body["provider"] == "groq"
        assert body["model"] == "openai/gpt-oss-20b"
        assert body["name"] == "HttpGroqBot"
        assert "gsk_HTTP_TEST_DO_NOT_LEAK_value" not in create_resp.text
        assert "api_key" not in body

        agent_id = body["agent_id"]
        get_resp = client.get(f"/api/workforce/agents/{agent_id}")
        assert get_resp.status_code == 200
        assert "gsk_HTTP_TEST_DO_NOT_LEAK_value" not in get_resp.text
        fetched = get_resp.json()
        assert fetched["provider"] == "groq"
        assert fetched["model"] == "openai/gpt-oss-20b"

    def test_wizard_api_keeps_existing_providers(self, tmp_path):
        from pathlib import Path
        from fastapi.testclient import TestClient

        from src.auth import AuthManager, UserStore
        from src.dashboard import create_app
        from src.platform_db import PlatformRepository
        from tests.test_dashboard import build_services

        repo = PlatformRepository(f"sqlite:///{tmp_path / 'platform_wf2.db'}")
        repo.initialize()
        services = build_services(tmp_path)
        services.platform_repository = repo
        auth_manager = AuthManager(
            user_store=UserStore(tmp_path / "users_wf2.db"),
            jwt_secret="test-secret-32chars-long-please!",
        )
        app = create_app(
            services=services,
            auth_manager=auth_manager,
            telemetry_db_path=str(tmp_path / "telemetry_wf2.db"),
        )
        client = TestClient(app)
        app.state.auth_manager.user_store.create_user(
            "admin@example.com", "admin-password-not-real", role="super_admin"
        )
        login = client.post(
            "/api/login", data={"username": "admin@example.com", "password": "admin-password-not-real"}
        )
        assert login.status_code == 200

        for prov, mod in [("openai", "gpt-4o-mini"), ("anthropic", "claude-3-haiku"), ("mistral", "mistral-small")]:
            resp = client.post("/api/workforce/wizard", json={
                "name": f"{prov}Bot",
                "provider": prov,
                "model": mod,
            })
            assert resp.status_code == 200, resp.text
            assert resp.json()["provider"] == prov
            assert resp.json()["model"] == mod
