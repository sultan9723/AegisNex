from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.auth import AuthManager, UserStore
from src.dashboard import create_app
from src.incidents import Incident
from src.platform_db import PlatformRepository

from tests.test_dashboard import build_services


def _build_app(tmp_path: Path):
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    services = build_services(tmp_path)
    services.platform_repository = repo
    services.monitoring_engine = None
    auth_manager = AuthManager(
        UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )
    app = create_app(services, auth_manager=auth_manager, telemetry_db_path=str(tmp_path / "telemetry.db"))
    return app, auth_manager, repo


def _token(auth_manager: AuthManager, email: str = "clients@example.com") -> str:
    user = auth_manager.user_store.create_user(email, "password12345", role="administrator")
    return auth_manager.create_access_token(user)


def _incident(incident_id: str, status: str, service_name: str) -> Incident:
    return Incident(
        incident_id=incident_id,
        timestamp="2026-09-11T12:00:00Z",
        severity="high",
        service_name=service_name,
        incident_type="health_check_failed",
        description=f"{service_name} failed",
        health_check_results=[],
        remediation_attempted=False,
        remediation_successful=False,
        status=status,
    )


def test_created_client_list_and_detail_share_canonical_integer_id(tmp_path: Path) -> None:
    app, auth_manager, _repo = _build_app(tmp_path)
    token = _token(auth_manager)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/orgs",
            json={"name": "Kammand", "domain": "kammand.com"},
            cookies={"aegisnex_session": token},
        )
        list_response = client.get("/api/orgs", cookies={"aegisnex_session": token})

    assert create_response.status_code == 200
    created = create_response.json()
    assert isinstance(created["id"], int)
    assert created["name"] == "Kammand"

    listed = list_response.json()["organizations"][0]
    assert listed["id"] == created["id"]

    with TestClient(app) as client:
        detail_response = client.get(f"/api/orgs/{listed['id']}", cookies={"aegisnex_session": token})

    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == created["id"]
    assert detail_response.json()["domain"] == "kammand.com"


def test_invalid_numeric_client_id_returns_not_found(tmp_path: Path) -> None:
    app, auth_manager, _repo = _build_app(tmp_path)
    token = _token(auth_manager)

    with TestClient(app) as client:
        response = client.get("/api/orgs/9999", cookies={"aegisnex_session": token})

    assert response.status_code == 404
    assert response.text == "Organization not found"


def test_client_incident_counts_are_scoped_to_requested_client(tmp_path: Path) -> None:
    app, auth_manager, repo = _build_app(tmp_path)
    token = _token(auth_manager)
    org_one = app.state.tenant_manager.create_organization("Client One")
    org_two = app.state.tenant_manager.create_organization("Client Two")

    client_incident = _incident("INC-CLIENT-1", "active", "client-api")
    setattr(client_incident, "org_id", org_one.id)
    setattr(client_incident, "org_name", org_one.name)
    other_client_incident = _incident("INC-CLIENT-2", "active", "other-api")
    setattr(other_client_incident, "org_id", org_two.id)
    setattr(other_client_incident, "org_name", org_two.name)
    unassigned_incident = _incident("INC-GLOBAL-1", "resolved", "global-api")

    repo.save_incident(client_incident)
    repo.save_incident(other_client_incident)
    repo.save_incident(unassigned_incident)

    with TestClient(app) as client:
        response = client.get(f"/api/incidents?limit=1000&org_id={org_one.id}", cookies={"aegisnex_session": token})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["total"] == 1
    assert body["active_count"] == 1
    assert body["resolved_count"] == 0
    assert [incident["incident_id"] for incident in body["incidents"]] == ["INC-CLIENT-1"]


def test_assign_incident_client_persists_real_org_id(tmp_path: Path) -> None:
    app, auth_manager, repo = _build_app(tmp_path)
    token = _token(auth_manager)
    org = app.state.tenant_manager.create_organization("Evidence Client")
    repo.save_incident(_incident("INC-ASSIGN-1", "active", "evidence-api"))

    with TestClient(app) as client:
        assign_response = client.post(
            "/api/incidents/INC-ASSIGN-1/client",
            json={"org_id": org.id},
            cookies={"aegisnex_session": token},
        )
        list_response = client.get(f"/api/incidents?org_id={org.id}", cookies={"aegisnex_session": token})

    assert assign_response.status_code == 200
    assert assign_response.json()["org_id"] == org.id
    assert assign_response.json()["org_name"] == "Evidence Client"
    assert list_response.json()["count"] == 1
    assert list_response.json()["incidents"][0]["incident_id"] == "INC-ASSIGN-1"
