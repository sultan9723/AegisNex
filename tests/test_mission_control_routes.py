from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.ai_workforce import (
    ExecutionResult,
    LifecycleStatus,
    WorkforceAgent,
    WorkforceExecution,
    WorkforceManager,
)
from src.auth import AuthManager, UserStore
from src.dashboard import create_app
from src.mission_control import complete_stage, create_execution, get_execution, update_execution
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


def _token(auth_manager: AuthManager, email: str = "operator@example.com") -> str:
    user = auth_manager.user_store.create_user(email, "password12345", role="operator")
    return auth_manager.create_access_token(user)


def test_mission_control_executions_requires_authentication(tmp_path: Path) -> None:
    app, _auth_manager, _repo = _build_app(tmp_path)

    with TestClient(app) as client:
        response = client.get("/api/mission-control/executions")

    assert response.status_code == 401


def test_mission_control_executions_loads_real_backend_rows(tmp_path: Path) -> None:
    app, auth_manager, repo = _build_app(tmp_path)
    token = _token(auth_manager)

    execution = create_execution(
        repo,
        "mc-real-001",
        "Investigate production API latency",
        user="operator@example.com",
        execution_type="analyze",
        agents=["ops-agent"],
        audit_links={"audit": "/audit/mc-real-001"},
    )
    complete_stage(execution, "planner", status="completed", latency_ms=120, confidence=0.91)
    execution.current_status = "completed"
    execution.total_latency_ms = 120
    execution.confidence = 0.91
    update_execution(repo, execution)

    with TestClient(app) as client:
        response = client.get(
            "/api/mission-control/executions?limit=20&offset=0&days=30",
            cookies={"aegisnex_session": token},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["count"] == 1
    assert body["executions"][0]["execution_id"] == "mc-real-001"
    assert body["executions"][0]["request"] == "Investigate production API latency"


def test_mission_control_invalid_days_does_not_500_or_create_fake_rows(tmp_path: Path) -> None:
    app, auth_manager, _repo = _build_app(tmp_path)
    token = _token(auth_manager)

    with TestClient(app) as client:
        response = client.get(
            "/api/mission-control/executions?days=not-an-int",
            cookies={"aegisnex_session": token},
        )

    assert response.status_code == 200
    assert response.json()["executions"] == []
    assert response.json()["total"] == 0


def test_mission_control_websocket_accepts_authenticated_query_token(tmp_path: Path) -> None:
    app, auth_manager, _repo = _build_app(tmp_path)
    token = _token(auth_manager)

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/mission-control?token={token}") as websocket:
            message = websocket.receive_json()

    assert message["type"] == "mc_stats_update"
    assert "stats" in message


def test_mission_control_websocket_rejects_missing_auth(tmp_path: Path) -> None:
    app, _auth_manager, _repo = _build_app(tmp_path)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/mission-control"):
                pass

    assert exc.value.code == 4001


def test_workforce_manager_direct_history_does_not_create_fake_mission_control_rows(tmp_path: Path) -> None:
    app, auth_manager, repo = _build_app(tmp_path)
    token = _token(auth_manager)
    manager = WorkforceManager(repo)
    manager.register_agent(
        WorkforceAgent(
            agent_id="agent-alpha",
            name="Agent Alpha",
            lifecycle_status=LifecycleStatus.ACTIVE.value,
        )
    )
    manager.record_execution(
        WorkforceExecution(
            execution_id="wf-real-001",
            agent_id="agent-alpha",
            task="Summarize open incidents",
            response="Done",
            status=ExecutionResult.SUCCESS.value,
        )
    )

    with TestClient(app) as client:
        workforce = client.get("/api/workforce/stats", cookies={"aegisnex_session": token})
        mission = client.get("/api/mission-control/executions", cookies={"aegisnex_session": token})

    assert workforce.status_code == 200
    assert workforce.json()["total_executions"] == 1
    assert mission.status_code == 200
    assert mission.json()["total"] == 0
    assert get_execution(repo, "wf-real-001") is None
