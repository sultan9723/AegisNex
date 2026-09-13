from pathlib import Path
from typing import Any, List

from fastapi.testclient import TestClient

from src.ai_governance import GovernanceManager
from src.auth import AuthManager, UserStore
from src.dashboard import create_app
from src.incidents import IncidentManager
from src.intelligence.providers.base import Message, ModelProvider, ProviderConfig
from src.platform_db import PlatformRepository
from src.policy_engine import AppPolicyEngine
from tests.test_dashboard import build_services


class MockProvider(ModelProvider):
    """Matches the MockProvider pattern already used in test_intelligence_pipeline.py."""

    def __init__(self, content: str = "OBSERVED EVIDENCE:\n- mock evidence", raise_on_chat: bool = False) -> None:
        super().__init__(ProviderConfig(model="mock-model"))
        self._content = content
        self._raise_on_chat = raise_on_chat

    def chat(self, messages: List[Message], **kwargs: Any) -> Message:
        if self._raise_on_chat:
            raise RuntimeError("simulated provider failure")
        return Message(role="assistant", content=self._content)

    def chat_with_tools(self, messages: List[Message], tools: List[dict], **kwargs: Any) -> Message:
        return self.chat(messages, **kwargs)

    def embed(self, text: str, **kwargs: Any) -> List[float]:
        return [0.0]

    @property
    def provider_name(self) -> str:
        return "mock"


def make_app(tmp_path: Path):
    # These routes need get_incident/list_incident_transitions/fetch_all/
    # save_incident, which the lightweight FakeRepository in test_dashboard.py
    # doesn't implement - use a real PlatformRepository, same pattern already
    # proven in test_demo_login.py's production-tenant-enforcement test.
    real_repo = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    real_repo.initialize()
    incident_manager = IncidentManager(
        history_path=tmp_path / "incident_history.json",
        notification_history_path=tmp_path / "notifications.json",
        storage_repository=real_repo,
    )
    services = build_services(tmp_path)
    services.platform_repository = real_repo
    services.incident_manager = incident_manager
    services.policy_engine = AppPolicyEngine(repository=real_repo)

    auth_manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )
    app = create_app(
        services=services,
        auth_manager=auth_manager,
        telemetry_db_path=str(tmp_path / "telemetry.db"),
    )
    # governance_manager() defaults to the real project-root governance.db if
    # app.state.governance isn't already set - isolate it, same pattern as
    # tests/test_governance_routes.py.
    app.state.governance = GovernanceManager(tmp_path / "governance.db")
    return app, incident_manager


def login_as_operator(app, client: TestClient) -> None:
    app.state.auth_manager.user_store.create_user(
        "operator@example.com", "operator-password-not-real", role="operator",
    )
    response = client.post(
        "/api/login",
        data={"username": "operator@example.com", "password": "operator-password-not-real"},
    )
    assert response.status_code == 200


def create_test_incident(incident_manager: IncidentManager):
    return incident_manager.create_incident(
        severity="high",
        service_name="kammand-website",
        incident_type="http_endpoint_failure",
        description="HTTP endpoint failed: connection refused",
        health_check_results=[{"status_code": 503, "error": "connection refused"}],
    )


DIAGNOSTIC_PLAN = {
    "mode": "diagnostics_only",
    "read_only": True,
    "actions": [
        {
            "action": "collect_incident_context",
            "target": "kammand-website",
            "read_only": True,
            "destructive": False,
            "reason": "Collect the current incident description, severity, status, and service context.",
        },
        {
            "action": "review_health_check_results",
            "target": "kammand-website",
            "read_only": True,
            "destructive": False,
            "reason": "Review health check output already attached to this incident.",
        },
    ],
}

FULL_DIAGNOSTIC_PLAN = {
    "mode": "diagnostics_only",
    "read_only": True,
    "actions": [
        {"action": "collect_incident_context", "target": "kammand-website", "read_only": True, "destructive": False},
        {"action": "review_health_check_results", "target": "kammand-website", "read_only": True, "destructive": False},
        {"action": "review_incident_timeline", "target": "incident", "read_only": True, "destructive": False},
        {"action": "prepare_evidence_packet", "target": "incident", "read_only": True, "destructive": False},
    ],
}


# ---- /explain ----


def test_explain_success_with_mocked_provider(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    mock = MockProvider("OBSERVED EVIDENCE:\n- HTTP endpoint returned 503\n\nPOSSIBLE EXPLANATIONS (unconfirmed hypotheses):\n- Upstream service may be down")
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: mock)

    response = client.post(f"/api/incidents/{incident.incident_id}/explain")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == incident.incident_id
    assert "OBSERVED EVIDENCE" in body["analysis"]
    assert isinstance(body["similar_incidents"], list)
    assert isinstance(body["runbooks"], list)
    assert isinstance(body["audit_context"], list)
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["timestamp"]


def test_explain_nonexistent_incident_returns_404(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    response = client.post("/api/incidents/INC-does-not-exist/explain")

    assert response.status_code == 404


def test_explain_missing_ai_configuration_is_graceful(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    def _raise(*args, **kwargs):
        raise ValueError("Unknown AI provider: bogus")

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", _raise)

    response = client.post(f"/api/incidents/{incident.incident_id}/explain")

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_explain_provider_failure_is_graceful(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    failing = MockProvider(raise_on_chat=True)
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: failing)

    response = client.post(f"/api/incidents/{incident.incident_id}/explain")

    assert response.status_code == 502
    assert "request failed" in response.json()["detail"].lower()


# ---- /propose-remediation ----


def test_propose_remediation_success_with_mocked_provider(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    mock = MockProvider("These steps are reasonable given the observed 503 response.")
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: mock)

    response = client.post(
        f"/api/incidents/{incident.incident_id}/propose-remediation",
        json={"plan": DIAGNOSTIC_PLAN, "proposed_by": "operator", "confidence": 0.72},
    )

    assert response.status_code == 200
    body = response.json()
    proposed = body["incident"]["proposed_remediation"]
    assert proposed["mode"] == "diagnostics_only"
    assert len(proposed["actions"]) == 2
    for action in proposed["actions"]:
        assert action["governance"]["verdict"] in {"safe", "approval_required", "forbidden"}
    assert body["incident"]["remediation_approval_status"] == "pending"
    assert body["incident"]["remediation_proposed_by"] == "operator"


def test_propose_remediation_degrades_gracefully_without_ai(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    def _raise(*args, **kwargs):
        raise ValueError("Unknown AI provider: bogus")

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", _raise)

    response = client.post(
        f"/api/incidents/{incident.incident_id}/propose-remediation",
        json={"plan": DIAGNOSTIC_PLAN, "proposed_by": "operator", "confidence": 0.72},
    )

    # AI is optional enrichment here - a missing/broken provider must not
    # block the (already-real, non-AI) governance classification + proposal.
    assert response.status_code == 200
    body = response.json()
    assert body["incident"]["remediation_approval_status"] == "pending"
    assert "ai_rationale" not in body["incident"]["proposed_remediation"]
    assert "unavailable" in body["message"].lower()


def test_propose_remediation_does_not_execute_anything(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    mock = MockProvider()
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: mock)

    response = client.post(
        f"/api/incidents/{incident.incident_id}/propose-remediation",
        json={"plan": DIAGNOSTIC_PLAN, "proposed_by": "operator", "confidence": 0.72},
    )

    assert response.status_code == 200
    body = response.json()["incident"]
    # Proposing a plan must never itself perform remediation.
    assert body["remediation_attempted"] is False
    assert body["remediation_successful"] is False
    assert body["incident_status"] == "active"


def test_approved_diagnostics_persist_and_return_client_scoped_evidence(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    org = app.state.tenant_manager.create_organization("Kammand")
    incident.org_id = org.id
    incident.org_name = org.name
    app.state.services.platform_repository.save_incident(incident)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    operator = app.state.auth_manager.user_store.get_user_by_email("operator@example.com")
    app.state.tenant_manager.assign_user_to_org(operator.id, org.id, role="operator")
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: MockProvider("rationale"))

    proposal = client.post(
        f"/api/incidents/{incident.incident_id}/propose-remediation",
        json={"plan": FULL_DIAGNOSTIC_PLAN, "proposed_by": "operator", "confidence": 0.9},
    )
    assert proposal.status_code == 200
    approval = app.state.services.platform_repository.list_approval_requests(
        status="pending", limit=10,
    )[0]
    approval_id = approval["approval_id"]

    response = client.post(
        f"/api/approvals/{approval_id}/respond",
        json={"decision": "approved", "comment": "Run approved diagnostics"},
    )
    assert response.status_code == 200

    stored = app.state.services.platform_repository.get_incident(incident.incident_id)
    assert stored["org_id"] == org.id
    assert len(stored["remediation_history"]) == 1
    packet = stored["remediation_history"][0]["details"]["evidence_packet"]
    assert packet["incident_id"] == incident.incident_id
    assert set(packet["actions"]) == {item["action"] for item in FULL_DIAGNOSTIC_PLAN["actions"]}

    client_incidents = client.get(f"/api/incidents?org_id={org.id}").json()["incidents"]
    assert len(client_incidents) == 1
    assert client_incidents[0]["incident_id"] == incident.incident_id
    assert client_incidents[0]["remediation_history"][0]["details"]["evidence_packet"] == packet


def test_rejected_diagnostics_do_not_persist_evidence_and_unassigned_stays_out_of_client(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    org = app.state.tenant_manager.create_organization("Kammand")
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    operator = app.state.auth_manager.user_store.get_user_by_email("operator@example.com")
    app.state.tenant_manager.assign_user_to_org(operator.id, org.id, role="operator")
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: MockProvider("rationale"))

    proposal = client.post(
        f"/api/incidents/{incident.incident_id}/propose-remediation",
        json={"plan": FULL_DIAGNOSTIC_PLAN, "proposed_by": "operator", "confidence": 0.9},
    )
    assert proposal.status_code == 200
    approval = app.state.services.platform_repository.list_approval_requests(status="pending", limit=10)[0]
    response = client.post(
        f"/api/approvals/{approval['approval_id']}/respond",
        json={"decision": "rejected", "comment": "Do not collect"},
    )
    assert response.status_code == 200
    stored = app.state.services.platform_repository.get_incident(incident.incident_id)
    assert stored["org_id"] is None
    assert stored["remediation_history"] in (None, [])
    assert client.get(f"/api/incidents?org_id={org.id}").json()["incidents"] == []


def test_propose_remediation_requires_operator_role(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    app.state.auth_manager.user_store.create_user(
        "viewer@example.com", "viewer-password-not-real", role="read_only",
    )
    login_response = client.post(
        "/api/login", data={"username": "viewer@example.com", "password": "viewer-password-not-real"},
    )
    assert login_response.status_code == 200

    mock = MockProvider()
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: mock)

    response = client.post(
        f"/api/incidents/{incident.incident_id}/propose-remediation",
        json={"plan": DIAGNOSTIC_PLAN, "proposed_by": "viewer", "confidence": 0.5},
    )

    assert response.status_code == 403


# ---- governance wiring: real explain/propose-remediation calls should show
# up in /governance's own agent registry and action audit ----


def test_explain_registers_agent_and_records_governance_action(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    mock = MockProvider("OBSERVED EVIDENCE:\n- mock evidence")
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: mock)

    # Before any real AI action: governance is genuinely empty, not stale.
    before = app.state.governance.get_agent_stats()
    assert before["total_agents"] == 0
    assert before["total_actions"] == 0

    response = client.post(f"/api/incidents/{incident.incident_id}/explain")
    assert response.status_code == 200

    agent = app.state.governance.get_agent("incident-ai")
    assert agent is not None
    assert agent.provider  # real configured provider, not a placeholder

    actions = app.state.governance.list_actions(agent_id="incident-ai")
    assert len(actions) == 1
    assert actions[0].action_type == "incident_explain"
    assert actions[0].target_resource == f"incident:{incident.incident_id}"
    assert actions[0].policy_verdict == "allowed"

    after = app.state.governance.get_agent_stats()
    assert after["total_agents"] == 1
    assert after["total_actions"] == 1


def test_propose_remediation_records_one_governance_action_per_proposed_action(
    tmp_path: Path, monkeypatch,
) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    mock = MockProvider("rationale text")
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: mock)

    response = client.post(
        f"/api/incidents/{incident.incident_id}/propose-remediation",
        json={"plan": DIAGNOSTIC_PLAN, "proposed_by": "operator", "confidence": 0.72},
    )
    assert response.status_code == 200

    actions = app.state.governance.list_actions(agent_id="incident-ai", action_type="propose_remediation")
    assert len(actions) == len(DIAGNOSTIC_PLAN["actions"])
    for action in actions:
        # Real verdicts from the real policy engine, mapped into governance's
        # own vocabulary - never a fabricated/placeholder verdict.
        assert action.policy_verdict in {"allowed", "pending_approval", "denied"}
        assert action.target_resource == f"incident:{incident.incident_id}"


def test_propose_remediation_governance_recording_survives_ai_being_unavailable(
    tmp_path: Path, monkeypatch,
) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    def _raise(*args, **kwargs):
        raise ValueError("Unknown AI provider: bogus")

    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", _raise)

    response = client.post(
        f"/api/incidents/{incident.incident_id}/propose-remediation",
        json={"plan": DIAGNOSTIC_PLAN, "proposed_by": "operator", "confidence": 0.72},
    )
    assert response.status_code == 200

    # Governance classification is real and independent of AI availability,
    # so the action audit must still be populated.
    actions = app.state.governance.list_actions(agent_id="incident-ai", action_type="propose_remediation")
    assert len(actions) == len(DIAGNOSTIC_PLAN["actions"])
