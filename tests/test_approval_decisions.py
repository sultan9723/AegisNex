import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_incident_ai_routes import (
    DIAGNOSTIC_PLAN,
    MockProvider,
    create_test_incident,
    login_as_operator,
    make_app,
)


def _propose_and_find_approval(app, client: TestClient, incident_id: str, monkeypatch):
    mock = MockProvider("rationale text")
    monkeypatch.setattr("src.intelligence.providers.factory.create_provider", lambda *a, **k: mock)

    response = client.post(
        f"/api/incidents/{incident_id}/propose-remediation",
        json={"plan": DIAGNOSTIC_PLAN, "proposed_by": "operator", "confidence": 0.72},
    )
    assert response.status_code == 200

    approvals = client.get("/api/approvals?status=pending&limit=50").json()["approvals"]
    matches = [a for a in approvals if a["approval_id"].startswith(f"incident-remediation-{incident_id}-")]
    assert len(matches) == 1, "propose-remediation should create exactly one pending approval"
    approval = matches[0]
    details = json.loads(approval["details"]) if isinstance(approval["details"], str) else approval["details"]
    return approval, details


def test_propose_remediation_creates_a_real_pending_approval(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    approval, details = _propose_and_find_approval(app, client, incident.incident_id, monkeypatch)

    assert approval["status"] == "pending"
    assert approval["request_type"] == "incident_diagnostic_remediation"
    assert details["incident_id"] == incident.incident_id
    assert details["read_only"] is True
    assert len(details["governance_action_ids"]) == len(DIAGNOSTIC_PLAN["actions"])


def test_pending_to_approved_persists_reviewer_and_timestamp(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    approval, _ = _propose_and_find_approval(app, client, incident.incident_id, monkeypatch)

    response = client.post(
        f"/api/approvals/{approval['approval_id']}/respond",
        json={"decision": "approved", "comment": "looks safe"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == "operator@example.com"
    assert body["reviewed_at"]
    assert body["comment"] == "looks safe"


def test_pending_to_rejected_persists_reviewer_and_timestamp(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    approval, _ = _propose_and_find_approval(app, client, incident.incident_id, monkeypatch)

    response = client.post(
        f"/api/approvals/{approval['approval_id']}/respond",
        json={"decision": "rejected", "comment": "not needed"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["reviewed_by"] == "operator@example.com"
    assert body["reviewed_at"]


def test_approved_request_cannot_be_changed_again(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    approval, _ = _propose_and_find_approval(app, client, incident.incident_id, monkeypatch)
    client.post(f"/api/approvals/{approval['approval_id']}/respond", json={"decision": "approved"})

    second = client.post(f"/api/approvals/{approval['approval_id']}/respond", json={"decision": "rejected"})

    assert second.status_code == 409
    assert "already approved" in second.json()["detail"].lower()
    current = client.get("/api/approvals?limit=50").json()["approvals"]
    row = next(a for a in current if a["approval_id"] == approval["approval_id"])
    assert row["status"] == "approved"  # unchanged - immutable


def test_rejected_request_cannot_be_changed_again(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    approval, _ = _propose_and_find_approval(app, client, incident.incident_id, monkeypatch)
    client.post(f"/api/approvals/{approval['approval_id']}/respond", json={"decision": "rejected"})

    second = client.post(f"/api/approvals/{approval['approval_id']}/respond", json={"decision": "approved"})

    assert second.status_code == 409
    current = client.get("/api/approvals?limit=50").json()["approvals"]
    row = next(a for a in current if a["approval_id"] == approval["approval_id"])
    assert row["status"] == "rejected"  # unchanged - immutable


def test_unknown_approval_returns_404(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)

    response = client.post("/api/approvals/does-not-exist/respond", json={"decision": "approved"})

    assert response.status_code == 404


def test_unauthorized_role_returns_403(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    operator_client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, operator_client)
    approval, _ = _propose_and_find_approval(app, operator_client, incident.incident_id, monkeypatch)

    viewer_client = TestClient(app, base_url="https://testserver")
    app.state.auth_manager.user_store.create_user(
        "viewer@example.com", "viewer-password-not-real", role="read_only",
    )
    login_response = viewer_client.post(
        "/api/login", data={"username": "viewer@example.com", "password": "viewer-password-not-real"},
    )
    assert login_response.status_code == 200

    response = viewer_client.post(f"/api/approvals/{approval['approval_id']}/respond", json={"decision": "approved"})

    assert response.status_code == 403


def test_audit_event_recorded_for_decision(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    approval, _ = _propose_and_find_approval(app, client, incident.incident_id, monkeypatch)

    client.post(f"/api/approvals/{approval['approval_id']}/respond", json={"decision": "approved"})

    repo = app.state.services.platform_repository
    audit_rows = repo.fetch_all("audit_logs")
    matching = [
        r for r in audit_rows
        if r.get("resource_type") == "approval" and r.get("resource_id") == approval["approval_id"]
    ]
    assert len(matching) == 1
    assert matching[0]["action"] == "approved"
    assert matching[0]["actor"] == "operator@example.com"


def test_approving_updates_linked_governance_actions_to_allowed(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    approval, details = _propose_and_find_approval(app, client, incident.incident_id, monkeypatch)
    gov_action_ids = details["governance_action_ids"]
    assert gov_action_ids

    client.post(f"/api/approvals/{approval['approval_id']}/respond", json={"decision": "approved"})

    for action_id in gov_action_ids:
        action = app.state.governance.get_action(action_id)
        assert action is not None
        assert action.policy_verdict == "allowed"


def test_rejecting_updates_linked_governance_actions_to_denied(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    approval, details = _propose_and_find_approval(app, client, incident.incident_id, monkeypatch)
    gov_action_ids = details["governance_action_ids"]

    client.post(f"/api/approvals/{approval['approval_id']}/respond", json={"decision": "rejected"})

    for action_id in gov_action_ids:
        action = app.state.governance.get_action(action_id)
        assert action.policy_verdict == "denied"


def test_decision_has_no_remediation_execution_side_effect(tmp_path: Path, monkeypatch) -> None:
    app, incident_manager = make_app(tmp_path)
    incident = create_test_incident(incident_manager)
    client = TestClient(app, base_url="https://testserver")
    login_as_operator(app, client)
    approval, details = _propose_and_find_approval(app, client, incident.incident_id, monkeypatch)

    response = client.post(f"/api/approvals/{approval['approval_id']}/respond", json={"decision": "approved"})
    assert response.status_code == 200

    # Approving a diagnostic proposal must never itself execute anything.
    # (SQLite stores these as 0/1, not Python bool, hence the `not` checks.)
    updated_incident = client.get(f"/api/incidents/{incident.incident_id}").json()["incident"]
    assert not updated_incident["remediation_attempted"]
    assert not updated_incident["remediation_successful"]
    assert updated_incident["incident_status"] == "active"
    # ... but the incident's own approval-status view does stay in sync with the real decision.
    assert updated_incident["remediation_approval_status"] == "approved"
