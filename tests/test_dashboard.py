import json
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.dashboard import (
    DashboardServices,
    build_container_rows,
    build_remediation_actions,
    collect_dashboard_context,
    create_app,
    get_network_stats,
    load_restart_history,
)
from src.incidents import IncidentManager


class FakeMonitor:
    def run(self, params):
        return {
            "status": "ok",
            "cpu_percent": 12.0,
            "ram_percent": 34.0,
            "disk_percent": 56.0,
            "warnings": [],
        }


class FakeDockerScanner:
    def run(self, params):
        return {
            "status": "ok",
            "containers": [
                {
                    "id": "abc",
                    "name": "api",
                    "status": "running",
                    "raw_status": "running",
                    "health_status": "healthy",
                },
                {
                    "id": "def",
                    "name": "db",
                    "status": "stopped",
                    "raw_status": "exited",
                    "health_status": "none",
                },
            ],
        }


def build_services(tmp_path: Path) -> DashboardServices:
    incident_manager = IncidentManager(tmp_path / "incident_history.json")
    active = incident_manager.create_incident(
        "high",
        "api",
        "health_check_failed",
        "api failed",
    )
    incident_manager.update_incident(
        active.incident_id,
        remediation_attempted=True,
        remediation_successful=True,
    )
    resolved = incident_manager.create_incident(
        "critical",
        "db",
        "container_status",
        "db stopped",
    )
    incident_manager.resolve_incident(resolved.incident_id)
    restart_history = tmp_path / "restart_history.json"
    restart_history.write_text(
        json.dumps(
            {
                "api": {
                    "attempts": 2,
                    "last_restart": "2026-06-04T12:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    return DashboardServices(
        monitor=FakeMonitor(),
        docker_scanner=FakeDockerScanner(),
        incident_manager=incident_manager,
        guardian=SimpleNamespace(),
        restart_history_path=restart_history,
    )


def test_load_restart_history_reads_valid_file(tmp_path: Path) -> None:
    history_path = tmp_path / "restart_history.json"
    history_path.write_text(json.dumps({"api": {"attempts": 2}}), encoding="utf-8")

    assert load_restart_history(history_path) == {"api": {"attempts": 2}}


def test_load_restart_history_handles_missing_or_invalid_file(tmp_path: Path) -> None:
    assert load_restart_history(tmp_path / "missing.json") == {}
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert load_restart_history(invalid) == {}


def test_build_container_rows_adds_restart_count_and_timestamp() -> None:
    rows = build_container_rows(
        [{"name": "api", "status": "running", "health_status": "healthy"}],
        {"api": {"attempts": 3}},
        "2026-06-04T12:00:00Z",
    )

    assert rows == [
        {
            "name": "api",
            "status": "running",
            "health_status": "healthy",
            "restart_count": 3,
            "last_check_timestamp": "2026-06-04T12:00:00Z",
        }
    ]


def test_build_remediation_actions_combines_incidents_and_restart_history(
    tmp_path: Path,
) -> None:
    manager = IncidentManager(tmp_path / "incident_history.json")
    incident = manager.create_incident("high", "api", "health_check_failed", "failed")
    manager.update_incident(
        incident.incident_id,
        remediation_attempted=True,
        remediation_successful=False,
    )

    actions = build_remediation_actions(
        manager.list_incidents(),
        {"api": {"attempts": 1, "last_restart": "2026-06-04T12:00:00Z"}},
    )

    assert len(actions) == 2
    assert {action["source"] for action in actions} == {"incident", "restart_history"}


def test_collect_dashboard_context(tmp_path: Path, monkeypatch) -> None:
    services = build_services(tmp_path)
    monkeypatch.setattr(
        "src.dashboard.get_network_stats",
        lambda: {
            "status": "ok",
            "bytes_sent": 1,
            "bytes_recv": 2,
            "packets_sent": 3,
            "packets_recv": 4,
        },
    )

    context = collect_dashboard_context(services)

    assert context["metrics"]["cpu_percent"] == 12.0
    assert len(context["containers"]) == 2
    assert len(context["running_containers"]) == 1
    assert len(context["active_incidents"]) == 1
    assert len(context["resolved_incidents"]) == 1
    assert context["containers"][0]["restart_count"] == 2
    assert context["actions"]


def test_get_network_stats_returns_shape(monkeypatch) -> None:
    fake_psutil = SimpleNamespace(
        net_io_counters=lambda: SimpleNamespace(
            bytes_sent=1,
            bytes_recv=2,
            packets_sent=3,
            packets_recv=4,
        )
    )
    monkeypatch.setitem(__import__("sys").modules, "psutil", fake_psutil)

    assert get_network_stats() == {
        "bytes_sent": 1,
        "bytes_recv": 2,
        "packets_sent": 3,
        "packets_recv": 4,
        "status": "ok",
    }


def test_dashboard_routes_render_pages(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("jinja2")

    app = create_app(build_services(tmp_path))

    for path, expected in (
        ("/", "Dashboard"),
        ("/containers", "Containers"),
        ("/incidents", "Incidents"),
        ("/actions", "Remediation Actions"),
    ):
        status_code, body = asyncio.run(asgi_get(app, path))
        assert status_code == 200
        assert expected in body


async def asgi_get(app, path: str) -> tuple[int, str]:
    messages = []
    request_sent = False

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    status_code = next(message["status"] for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return status_code, body.decode("utf-8")
