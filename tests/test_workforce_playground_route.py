"""HTTP-level regression tests for the AI Workforce Playground endpoint.

Reproduces the real E2E bug report: a Groq-backed agent
(provider="groq", model="openai/gpt-oss-20b") created through the wizard
with a 0 daily/monthly budget, activated, then executed in the Playground.
The manager-level behavior (WorkforceExecutionBlocked -> "budget_exceeded")
already has unit coverage in test_ai_workforce.py and test_workforce_groq.py;
what was missing - and what actually surfaced the bug for the user - is
coverage of the real HTTP route: the exact status code and JSON body shape
returned by POST /api/workforce/agents/{id}/playground, and confirmation
that the LLM provider is never invoked when the block fires.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.auth import AuthManager, UserStore
from src.dashboard import create_app
from src.mission_control import create_execution, get_execution, list_executions
from src.platform_db import PlatformRepository
from src.intelligence.providers.base import Message, ModelProvider, ProviderConfig
from tests.test_dashboard import build_services


class SpyProvider(ModelProvider):
    def __init__(self) -> None:
        super().__init__(ProviderConfig(model="spy-default-model"))
        self.chat_calls: list[dict] = []

    @property
    def provider_name(self) -> str:  # type: ignore[override]
        return "spy"

    def chat(self, messages, **kwargs) -> Message:
        self.chat_calls.append({"messages": messages, **kwargs})
        return Message(role="assistant", content="spy-response")

    def chat_with_tools(self, messages, tools, **kwargs):  # type: ignore[override]
        return self.chat(messages, **kwargs)

    def embed(self, text, **kwargs):  # type: ignore[override]
        return [0.0]


def make_app(tmp_path: Path):
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    repo.initialize()
    services = build_services(tmp_path)
    services.platform_repository = repo
    auth_manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )
    app = create_app(
        services=services,
        auth_manager=auth_manager,
        telemetry_db_path=str(tmp_path / "telemetry.db"),
    )
    return app


def login_as_operator(app, client: TestClient) -> None:
    # super_admin (not "operator") to avoid the org_id-assignment requirement
    # in the wizard/create routes - same pattern as
    # test_workforce_groq.py::TestWizardHttpEndpoint.
    app.state.auth_manager.user_store.create_user(
        "admin@example.com", "admin-password-not-real", role="super_admin",
    )
    response = client.post(
        "/api/login",
        data={"username": "admin@example.com", "password": "admin-password-not-real"},
    )
    assert response.status_code == 200


def create_and_activate_agent(client: TestClient, *, daily_budget: float, monthly_budget: float) -> str:
    create_resp = client.post("/api/workforce/wizard", json={
        "name": "Incident Triage Agent",
        "agent_type": "security",
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "daily_budget": daily_budget,
        "monthly_budget": monthly_budget,
        "tools": [{"name": "metrics", "allowed": True}, {"name": "knowledge", "allowed": True}],
        "permissions": ["read_incidents", "read_metrics"],
    })
    assert create_resp.status_code == 200, create_resp.text
    agent_id = create_resp.json()["agent_id"]

    activate_resp = client.post(f"/api/workforce/agents/{agent_id}/activate")
    assert activate_resp.status_code == 200, activate_resp.text
    assert activate_resp.json()["lifecycle_status"] == "active"

    return agent_id


def test_playground_returns_409_budget_exceeded_for_zero_budget_agent(tmp_path: Path, monkeypatch) -> None:
    """Reproduces the exact reported bug: a groq/openai/gpt-oss-20b agent
    created with 0/0 budget, activated, then executed non-simulated."""
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=0, monthly_budget=0)

    call_log: list[str] = []
    monkeypatch.setattr(
        "src.intelligence.providers.factory.create_provider",
        lambda *a, **k: call_log.append("called") or SpyProvider(),
    )

    response = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "Summarize the current incident", "simulate": False},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "budget_exceeded"
    assert body["details"]["allowed"] is False

    # The LLM/Groq provider must never be reached once the budget check blocks execution.
    assert call_log == []


def test_playground_returns_409_agent_not_active(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    create_resp = client.post("/api/workforce/wizard", json={
        "name": "Draft Agent", "provider": "groq", "model": "openai/gpt-oss-20b",
    })
    assert create_resp.status_code == 200, create_resp.text
    agent_id = create_resp.json()["agent_id"]
    assert create_resp.json()["lifecycle_status"] == "draft"

    response = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "test", "simulate": False},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "agent_not_active"


def test_playground_succeeds_once_budget_is_positive(tmp_path: Path, monkeypatch) -> None:
    """Same agent shape as the bug report, but funded - the legitimate fix
    path: PUT /api/workforce/agents/{id} with a positive budget unblocks it."""
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    spy = SpyProvider()
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: spy)

    response = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "Summarize the current incident", "simulate": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert len(spy.chat_calls) == 1
    assert spy.config.model == "openai/gpt-oss-20b"


def test_successful_workforce_playground_execution_is_visible_in_mission_control(tmp_path: Path, monkeypatch) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    spy = SpyProvider()
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: spy)

    response = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "Triage the current incident", "simulate": False},
    )

    assert response.status_code == 200
    workforce_execution = response.json()
    assert workforce_execution["status"] == "success"

    agent_history = client.get(f"/api/workforce/agents/{agent_id}/executions")
    mission = client.get("/api/mission-control/executions?limit=20")
    mission_detail = client.get(f"/api/mission-control/executions/{workforce_execution['execution_id']}")

    assert agent_history.status_code == 200
    assert [e["execution_id"] for e in agent_history.json()["executions"]] == [workforce_execution["execution_id"]]
    assert mission.status_code == 200
    assert mission.json()["total"] == 1
    assert [e["execution_id"] for e in mission.json()["executions"]] == [workforce_execution["execution_id"]]
    mission_execution = mission_detail.json()["execution"]
    assert mission_execution["current_status"] == "completed"
    assert mission_execution["request"] == "Triage the current incident"
    assert mission_execution["agents"] == ["Incident Triage Agent"]
    assert mission_execution["total_latency_ms"] == workforce_execution["latency_ms"]
    assert mission_execution["confidence"] == workforce_execution["confidence"]
    assert mission_execution["total_cost"] == workforce_execution["cost"]
    assert mission_execution["metadata"]["source"] == "ai_workforce_playground"


def test_failed_workforce_playground_execution_is_visible_in_mission_control(tmp_path: Path, monkeypatch) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    def fail_provider(*_args: Any, **_kwargs: Any) -> SpyProvider:
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", fail_provider)

    response = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "This should fail", "simulate": False},
    )

    assert response.status_code == 200
    workforce_execution = response.json()
    assert workforce_execution["status"] == "error"

    mission = client.get("/api/mission-control/executions?limit=20")
    assert mission.status_code == 200
    assert mission.json()["total"] == 1
    mission_execution = mission.json()["executions"][0]
    assert mission_execution["execution_id"] == workforce_execution["execution_id"]
    assert mission_execution["current_status"] == "failed"
    assert mission_execution["error"] == "provider unavailable"


def test_one_workforce_playground_execution_produces_one_mission_control_execution(tmp_path: Path, monkeypatch) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: SpyProvider())

    response = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "Count this once", "simulate": False},
    )

    assert response.status_code == 200
    execution_id = response.json()["execution_id"]
    rows = list_executions(app.state.services.platform_repository, limit=20)
    assert [row.execution_id for row in rows] == [execution_id]
    assert get_execution(app.state.services.platform_repository, execution_id) is not None


def test_workforce_playground_execution_broadcasts_one_mission_control_update(tmp_path: Path, monkeypatch) -> None:
    class SpyWebSocketManager:
        def __init__(self) -> None:
            self.events: list[tuple[dict[str, Any], str]] = []

        async def broadcast(self, event: dict[str, Any], channel: str = "dashboard") -> None:
            self.events.append((event, channel))

    app = make_app(tmp_path)
    spy_ws = SpyWebSocketManager()
    app.state.websocket_manager = spy_ws
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: SpyProvider())

    response = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "Broadcast this once", "simulate": False},
    )

    assert response.status_code == 200
    deadline = time.monotonic() + 2
    while not spy_ws.events and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(spy_ws.events) == 1
    event, channel = spy_ws.events[0]
    assert event["type"] == "execution_update"
    assert "stats" in event
    assert channel == "mission_control"


def test_existing_mission_control_execution_types_still_work(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    create_execution(
        app.state.services.platform_repository,
        "mc-existing-chat",
        "Existing chat request",
        user="admin@example.com",
        execution_type="chat",
    )

    response = client.get("/api/mission-control/executions?execution_type=chat")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["executions"][0]["execution_id"] == "mc-existing-chat"


def test_a_zero_budget_agent_can_be_unblocked_via_the_update_endpoint(tmp_path: Path, monkeypatch) -> None:
    """The real, product-supported remediation for an already-created 0-budget
    agent: PUT its budget through the update endpoint (never a direct DB edit)."""
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=0, monthly_budget=0)

    update_resp = client.put(
        f"/api/workforce/agents/{agent_id}",
        json={"daily_budget": 25, "monthly_budget": 750},
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["daily_budget"] == 25
    assert update_resp.json()["monthly_budget"] == 750

    spy = SpyProvider()
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: spy)

    response = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "test", "simulate": False},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


# ---------------------------------------------------------------------------
# Governance + Audit Log linkage
#
# Before this, a real Workforce Playground execution never touched
# GovernanceManager (governance.db) or the platform audit_logs table - the
# two subsystems had no wiring between them (Workforce and Governance keep
# entirely separate agent registries/stores). These tests cover the wiring
# added in src/dashboard.py's _track_workforce_execution_in_governance:
# the real agent mirrored into governance, one governance action recorded
# per execution, one audit log entry per execution, and correlation by the
# same execution_id across every subsystem.
# ---------------------------------------------------------------------------


def test_successful_execution_registers_the_real_agent_in_governance(tmp_path: Path, monkeypatch) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: SpyProvider())
    exec_resp = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "Triage the current incident", "simulate": False},
    )
    assert exec_resp.status_code == 200

    gov_agent_resp = client.get(f"/api/governance/agents/{agent_id}")
    assert gov_agent_resp.status_code == 200
    gov_agent = gov_agent_resp.json()
    assert gov_agent["agent_id"] == agent_id
    assert gov_agent["name"] == "Incident Triage Agent"
    assert gov_agent["provider"] == "groq"
    assert gov_agent["model"] == "openai/gpt-oss-20b"


def test_successful_execution_records_exactly_one_governance_action(tmp_path: Path, monkeypatch) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: SpyProvider())
    exec_resp = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "Triage the current incident", "simulate": False},
    )
    execution_id = exec_resp.json()["execution_id"]

    actions_resp = client.get(f"/api/governance/actions?agent_id={agent_id}")
    assert actions_resp.status_code == 200
    actions = actions_resp.json()["actions"]

    # Exactly one governance action for this one execution - no duplicates.
    assert len(actions) == 1
    action = actions[0]
    assert action["agent_id"] == agent_id
    assert action["action_id"] == f"workforce-{execution_id}"
    assert action["action_type"] == "workforce_playground_execution"
    assert action["policy_verdict"] == "allowed"
    assert action["status"] == "success"
    assert action["confidence_score"] == exec_resp.json()["confidence"]
    # A real, tamper-evident audit chain entry - not fabricated.
    assert action["entry_hash"]


def test_failed_execution_records_a_failed_governance_action(tmp_path: Path, monkeypatch) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    def fail_provider(*_args: Any, **_kwargs: Any) -> SpyProvider:
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", fail_provider)
    exec_resp = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "This should fail", "simulate": False},
    )
    assert exec_resp.json()["status"] == "error"

    actions = client.get(f"/api/governance/actions?agent_id={agent_id}").json()["actions"]
    assert len(actions) == 1
    assert actions[0]["status"] == "failed"


def test_successful_execution_is_recorded_in_audit_logs(tmp_path: Path, monkeypatch) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: SpyProvider())
    exec_resp = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "Triage the current incident", "simulate": False},
    )
    execution_id = exec_resp.json()["execution_id"]

    logs_resp = client.get(f"/api/audit-logs/filter?execution_id={execution_id}")
    assert logs_resp.status_code == 200
    logs = logs_resp.json()["logs"]

    # Exactly one audit log row for this one execution - no duplicates.
    assert len(logs) == 1
    entry = logs[0]
    assert entry["execution_id"] == execution_id
    assert entry["actor"] == "admin@example.com"
    assert entry["action"] == "workforce_playground_execution"
    assert entry["resource_type"] == "workforce_agent"
    assert entry["resource_id"] == agent_id
    assert entry["timestamp"]
    details = json.loads(entry["details"]) if isinstance(entry["details"], str) else entry["details"]
    assert details["status"] == "success"
    assert details["provider"] == "groq"
    assert details["model"] == "openai/gpt-oss-20b"


def test_audit_log_details_never_contain_the_raw_task_or_response_text(tmp_path: Path, monkeypatch) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    secret_task = "SENSITIVE-TASK-MARKER-do-not-leak-this-prompt-4f9c"
    monkeypatch.setattr(
        "src.intelligence.providers.factory.create_provider",
        lambda *a, **k: SpyProvider(),
    )
    exec_resp = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": secret_task, "simulate": False},
    )
    execution_id = exec_resp.json()["execution_id"]
    raw_response_text = exec_resp.json()["response"]

    logs = client.get(f"/api/audit-logs/filter?execution_id={execution_id}").json()["logs"]
    assert len(logs) == 1
    raw_log_text = json.dumps(logs[0])
    assert secret_task not in raw_log_text
    assert raw_response_text not in raw_log_text

    # Same guarantee on the governance action row.
    actions = client.get(f"/api/governance/actions?agent_id={agent_id}").json()["actions"]
    raw_action_text = json.dumps(actions[0])
    assert secret_task not in raw_action_text
    assert raw_response_text not in raw_action_text


def test_execution_id_correlates_across_workforce_mission_control_governance_and_audit(
    tmp_path: Path, monkeypatch,
) -> None:
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    agent_id = create_and_activate_agent(client, daily_budget=25, monthly_budget=750)

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: SpyProvider())
    exec_resp = client.post(
        f"/api/workforce/agents/{agent_id}/playground",
        json={"task": "Triage the current incident", "simulate": False},
    )
    execution_id = exec_resp.json()["execution_id"]

    workforce_history = client.get(f"/api/workforce/agents/{agent_id}/executions").json()["executions"]
    mission_control = client.get("/api/mission-control/executions?limit=20").json()["executions"]
    governance_actions = client.get(f"/api/governance/actions?agent_id={agent_id}").json()["actions"]
    audit_logs = client.get(f"/api/audit-logs/filter?execution_id={execution_id}").json()["logs"]

    assert [e["execution_id"] for e in workforce_history] == [execution_id]
    assert [e["execution_id"] for e in mission_control] == [execution_id]
    assert governance_actions[0]["action_id"] == f"workforce-{execution_id}"
    assert governance_actions[0]["agent_id"] == agent_id
    assert audit_logs[0]["execution_id"] == execution_id
    assert audit_logs[0]["resource_id"] == agent_id
