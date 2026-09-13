"""End-to-end integration tests for the Approval decision flow.

These tests reproduce the real AegisNex E2E validation against fresh,
diagnostics-only approval requests created through the same storage path the
production CommandMesh governance gate uses (``PlatformRepository.create_approval_request``).

Covered expected behaviors:
  - a pending approval can be approved
  - a pending approval can be rejected
  - an approved request cannot be decided again and stays immutable
  - a rejected request cannot be decided again and stays immutable
  - every decision writes an audit-log entry
  - RBAC is enforced: operator+ can decide, read-only users cannot
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.auth import AuthManager, UserStore
from src.dashboard import create_app
from src.platform_db import PlatformRepository
from tests.test_dashboard import build_services


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
    return app, repo


def login(app, client: TestClient, email: str = "operator@example.com", password: str = "operator-password-not-real", role: str = "operator") -> None:
    app.state.auth_manager.user_store.create_user(email, password, role=role)
    response = client.post("/api/login", data={"username": email, "password": password})
    assert response.status_code == 200


def create_pending(repo: PlatformRepository, approval_id: str, request_type: str = "container_restart") -> dict[str, Any]:
    return repo.create_approval_request(
        approval_id=approval_id,
        request_type=request_type,
        requester="auto-pipeline",
        summary=f"Approve {request_type} for {approval_id}",
        details={
            "container": "web-api",
            "env": "production",
            "mode": "diagnostics_only",
            "read_only": True,
        },
    )


def audit_entries(repo: PlatformRepository, resource_id: str) -> list[dict[str, Any]]:
    logs = repo.list_audit_logs_enhanced(limit=100, resource_type_filter="approval")
    return [entry for entry in logs if entry.get("resource_id") == resource_id]


def respond(client: TestClient, approval_id: str, decision: str, comment: str = ""):
    return client.post(
        f"/api/approvals/{approval_id}/respond",
        json={"decision": decision, "comment": comment},
    )


@pytest.fixture
def app_session(tmp_path: Path):
    app, repo = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    login(app, client)
    return app, repo, client


def test_pending_approval_can_be_approved(app_session) -> None:
    _, repo, client = app_session
    create_pending(repo, "apr-approve-001")

    listed = client.get("/api/approvals")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["approvals"][0]["status"] == "pending"

    response = respond(client, "apr-approve-001", "approved", comment="Explained to owner")
    assert response.status_code == 200
    body = response.json()
    assert body["approval_id"] == "apr-approve-001"
    assert body["status"] == "approved"
    assert body["reviewed_by"] == "operator@example.com"
    assert body["reviewed_at"]

    refreshed = client.get("/api/approvals").json()["approvals"][0]
    assert refreshed["status"] == "approved"
    assert refreshed["reviewed_by"] == "operator@example.com"

    entries = audit_entries(repo, "apr-approve-001")
    assert len(entries) == 1
    assert entries[0]["action"] == "approved"
    assert entries[0]["actor"] == "operator@example.com"


def test_pending_approval_can_be_rejected(app_session) -> None:
    _, repo, client = app_session
    create_pending(repo, "apr-reject-001")

    response = respond(client, "apr-reject-001", "rejected", comment="Not enough context")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["reviewed_by"] == "operator@example.com"
    assert body["reviewed_at"]

    refreshed = client.get("/api/approvals").json()["approvals"][0]
    assert refreshed["status"] == "rejected"
    assert refreshed["reviewed_by"] == "operator@example.com"

    entries = audit_entries(repo, "apr-reject-001")
    assert len(entries) == 1
    assert entries[0]["action"] == "rejected"
    assert entries[0]["actor"] == "operator@example.com"


def test_approved_request_cannot_be_decided_again(app_session) -> None:
    _, repo, client = app_session
    create_pending(repo, "apr-immutable-approve")

    first = respond(client, "apr-immutable-approve", "approved").json()
    original_reviewed_at = first["reviewed_at"]
    assert len(audit_entries(repo, "apr-immutable-approve")) == 1

    # A repeat decision must not silently succeed as if it had just happened -
    # it should say clearly that the request was already decided, and the
    # stored record must stay exactly as the first decision left it.
    second = respond(client, "apr-immutable-approve", "approved")
    assert second.status_code == 409
    assert "already approved" in second.json()["detail"].lower()

    third = respond(client, "apr-immutable-approve", "rejected")
    assert third.status_code == 409

    unchanged = repo.get_approval_request("apr-immutable-approve")
    assert unchanged["status"] == "approved"
    assert unchanged["reviewed_at"] == original_reviewed_at

    entries = audit_entries(repo, "apr-immutable-approve")
    assert len(entries) == 1


def test_rejected_request_cannot_be_decided_again(app_session) -> None:
    _, repo, client = app_session
    create_pending(repo, "apr-immutable-reject")

    first = respond(client, "apr-immutable-reject", "rejected").json()
    original_reviewed_at = first["reviewed_at"]
    assert len(audit_entries(repo, "apr-immutable-reject")) == 1

    second = respond(client, "apr-immutable-reject", "approved")
    assert second.status_code == 409
    assert "already rejected" in second.json()["detail"].lower()

    third = respond(client, "apr-immutable-reject", "rejected")
    assert third.status_code == 409

    unchanged = repo.get_approval_request("apr-immutable-reject")
    assert unchanged["status"] == "rejected"
    assert unchanged["reviewed_at"] == original_reviewed_at

    entries = audit_entries(repo, "apr-immutable-reject")
    assert len(entries) == 1


def test_respond_requires_authentication(tmp_path: Path) -> None:
    app, repo = make_app(tmp_path)
    create_pending(repo, "apr-unauth")
    client = TestClient(app, base_url="https://testserver")

    response = respond(client, "apr-unauth", "approved")
    assert response.status_code == 401


def test_respond_requires_operator_role(tmp_path: Path) -> None:
    app, repo = make_app(tmp_path)
    create_pending(repo, "apr-viewer")
    client = TestClient(app, base_url="https://testserver")
    login(app, client, email="viewer@example.com", role="read_only")

    listed = client.get("/api/approvals")
    assert listed.status_code == 403

    response = respond(client, "apr-viewer", "approved")
    assert response.status_code == 403

    assert repo.get_approval_request("apr-viewer")["status"] == "pending"


def test_respond_to_unknown_approval_returns_404(app_session) -> None:
    _, _, client = app_session
    response = respond(client, "apr-does-not-exist", "approved")
    assert response.status_code == 404