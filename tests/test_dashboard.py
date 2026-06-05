import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.dashboard import (
    DashboardServices,
    build_integrations_context,
    build_hourly_event_trend,
    build_metric_trends,
    build_notification_statistics,
    build_container_rows,
    build_remediation_actions,
    calculate_health_score,
    collect_dashboard_context,
    create_app,
    get_network_stats,
    load_restart_history,
)
from src.auth import AuthManager, UserStore
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


class FakeRepository:
    def __init__(self, database_path: Path) -> None:
        from src.storage import AegisNexRepository

        self.database_path = database_path
        AegisNexRepository(database_path)
        self.rows = {
            "metrics_snapshots": [
                {
                    "timestamp": "2026-06-04T11:00:00Z",
                    "cpu_percent": 10.0,
                    "memory_percent": 20.0,
                },
                {
                    "timestamp": "2026-06-04T12:00:00Z",
                    "cpu_percent": 30.0,
                    "memory_percent": 40.0,
                },
            ],
            "notifications": [
                {"provider": "email", "status": "ok"},
                {"provider": "slack", "status": "failed"},
                {"provider": "discord", "status": "sent"},
            ],
            "remediations": [
                {
                    "timestamp": "2026-06-04T12:00:00Z",
                    "service_name": "api",
                    "action": "restart",
                    "successful": 1,
                }
            ],
        }

    def fetch_all(self, table_name):
        return self.rows.get(table_name, [])


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
        storage_repository=FakeRepository(tmp_path / "dashboard.db"),
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
    assert context["health_score"]["score"] > 0
    assert context["chart_data"]["metrics"]["cpu"]["values"] == [10.0, 30.0]
    assert len(context["chart_data"]["incidents"]["labels"]) == 24
    assert context["notification_stats"] == {
        "email_count": 1,
        "slack_count": 1,
        "discord_count": 1,
        "failed_notifications": 1,
    }
    assert context["recent_incidents"]
    assert context["recent_remediations"][0]["service_name"] == "api"


def test_calculate_health_score_uses_metrics_containers_and_incidents() -> None:
    score = calculate_health_score(
        {"cpu_percent": 80, "ram_percent": 70},
        [
            {"status": "running", "health_status": "healthy"},
            {"status": "stopped", "health_status": "none"},
        ],
        active_incident_count=2,
    )

    assert score["score"] == 40
    assert score["indicator"] == "red"


def test_build_metric_trends_uses_last_24h_rows() -> None:
    trends = build_metric_trends(
        [
            {
                "timestamp": "2026-06-03T10:00:00Z",
                "cpu_percent": 99,
                "memory_percent": 99,
            },
            {
                "timestamp": "2026-06-04T11:00:00Z",
                "cpu_percent": 25,
                "memory_percent": 35,
            },
        ],
        {"cpu_percent": 1, "ram_percent": 2},
        now=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
    )

    assert trends["cpu"]["values"] == [25.0]
    assert trends["memory"]["values"] == [35.0]


def test_build_hourly_event_trend_counts_rows_by_hour() -> None:
    trend = build_hourly_event_trend(
        [
            {"timestamp": "2026-06-04T11:01:00Z"},
            {"timestamp": "2026-06-04T11:59:00Z"},
            {"timestamp": "2026-06-04T10:00:00Z"},
        ],
        now=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
    )

    assert len(trend["labels"]) == 24
    assert trend["values"][-2] == 2
    assert trend["values"][-3] == 1


def test_build_notification_statistics_counts_providers_and_failures() -> None:
    stats = build_notification_statistics(
        [
            {"provider": "email", "status": "ok"},
            {"provider": "slack", "status": "failed"},
            {"provider": "discord", "status": "success"},
            {"provider": "pagerduty", "status": "timeout"},
        ]
    )

    assert stats == {
        "email_count": 1,
        "slack_count": 1,
        "discord_count": 1,
        "failed_notifications": 2,
    }


def test_build_integrations_context_includes_required_platforms(tmp_path: Path) -> None:
    services = build_services(tmp_path)

    integrations = build_integrations_context(services)["integrations"]

    assert {item["name"] for item in integrations} == {
        "Grafana",
        "Prometheus",
        "Docker",
        "MCP",
        "SQLite",
    }


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

    auth_manager = AuthManager(
        UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret",
    )
    user, token = auth_manager.register("ops@example.com", "password123")
    app = create_app(build_services(tmp_path), auth_manager=auth_manager)

    for path, expected in (
        ("/", "Health Score"),
        ("/infrastructure", "Infrastructure"),
        ("/containers", "Containers"),
        ("/incidents", "Incidents"),
        ("/actions", "Remediation Actions"),
        ("/reports", "Reports"),
        ("/notifications", "Notifications"),
        ("/mcp", "MCP Server"),
        ("/integrations", "Integrations"),
        ("/settings", "Settings"),
    ):
        status_code, body = asyncio.run(
            asgi_get(app, path, cookies={"aegisnex_session": token})
        )
        assert status_code == 200
        assert expected in body

    status_code, body = asyncio.run(
        asgi_get(app, "/", cookies={"aegisnex_session": token})
    )
    assert status_code == 200
    assert "cdn.jsdelivr.net/npm/chart.js" in body
    assert "bootstrap" not in body.lower()
    assert "CPU Trend 24h" in body
    assert "Memory Trend 24h" in body
    assert "Incident Trend" in body
    assert "Remediation Trend" in body
    assert "Recent Incidents" in body
    assert "Recent Remediations" in body
    assert "Notification Statistics" in body
    assert user.email in body

    report_status, report_body, report_headers = asyncio.run(
        asgi_request(
            app,
            "GET",
            "/reports/weekly/json",
            cookies={"aegisnex_session": token},
        )
    )
    assert report_status == 200
    assert '"report_type": "weekly"' in report_body
    assert "attachment; filename=weekly_report.json" in report_headers["content-disposition"]


def test_dashboard_routes_redirect_to_login_without_session(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("jinja2")

    app = create_app(
        build_services(tmp_path),
        auth_manager=AuthManager(UserStore(tmp_path / "users.db"), jwt_secret="test-secret"),
    )

    status_code, body, headers = asyncio.run(asgi_request(app, "GET", "/"))

    assert status_code == 303
    assert headers["location"] == "/login"


def test_auth_pages_register_login_and_logout(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("jinja2")

    auth_manager = AuthManager(
        UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret",
    )
    app = create_app(build_services(tmp_path), auth_manager=auth_manager)

    register_status, _, register_headers = asyncio.run(
        asgi_request(
            app,
            "POST",
            "/register",
            body="email=ops%40example.com&password=password123",
        )
    )
    assert register_status == 303
    assert register_headers["location"] == "/"
    assert "aegisnex_session=" in register_headers["set-cookie"]

    login_status, _, login_headers = asyncio.run(
        asgi_request(
            app,
            "POST",
            "/login",
            body="email=ops%40example.com&password=password123",
        )
    )
    assert login_status == 303
    assert login_headers["location"] == "/"
    assert "aegisnex_session=" in login_headers["set-cookie"]

    logout_status, _, logout_headers = asyncio.run(asgi_request(app, "GET", "/logout"))
    assert logout_status == 303
    assert logout_headers["location"] == "/login"
    assert "aegisnex_session=" in logout_headers["set-cookie"]


async def asgi_get(
    app,
    path: str,
    cookies: dict[str, str] | None = None,
) -> tuple[int, str]:
    status_code, body, _headers = await asgi_request(app, "GET", path, cookies=cookies)
    return status_code, body


async def asgi_request(
    app,
    method: str,
    path: str,
    body: str = "",
    cookies: dict[str, str] | None = None,
) -> tuple[int, str, dict[str, str]]:
    messages = []
    request_sent = False
    headers = [(b"host", b"testserver")]
    if cookies:
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        headers.append((b"cookie", cookie_header.encode("utf-8")))
    if method == "POST":
        headers.append((b"content-type", b"application/x-www-form-urlencoded"))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {
                "type": "http.request",
                "body": body.encode("utf-8"),
                "more_body": False,
            }
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    status_code = start["status"]
    response_headers = {
        key.decode("utf-8"): value.decode("utf-8")
        for key, value in start.get("headers", [])
    }
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return status_code, body.decode("utf-8"), response_headers
