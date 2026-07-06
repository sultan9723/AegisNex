import json
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.dashboard import DashboardServices, create_app
from src.incidents import IncidentManager
from src.notifications.base import NotificationProvider
from src.prometheus_exporter import PrometheusExporter, load_restart_history


class FakeMonitor:
    def run(self, params):
        return {
            "status": "ok",
            "cpu_percent": 11.0,
            "ram_percent": 22.0,
            "disk_percent": 33.0,
        }


class FakeDockerScanner:
    def run(self, params):
        return {
            "status": "ok",
            "containers": [
                {"name": "api", "status": "running", "health_status": "healthy"},
                {"name": "db", "status": "stopped", "health_status": "none"},
                {"name": "job", "status": "running", "health_status": "unhealthy"},
                {"name": "cache", "status": "error", "health_status": "none"},
            ],
        }


class SuccessfulProvider(NotificationProvider):
    name = "successful"

    def _send(self, message: str) -> None:
        return


class FailedProvider(NotificationProvider):
    name = "failed"

    def _send(self, message: str) -> None:
        raise RuntimeError("failed")


def build_services(tmp_path: Path) -> DashboardServices:
    restart_history = tmp_path / "restart_history.json"
    restart_history.write_text(
        json.dumps(
            {
                "api": {"attempts": 2, "last_restart": "2026-06-04T12:00:00Z"},
                "db": {"attempts": 1, "last_restart": "2026-06-04T12:01:00Z"},
            }
        ),
        encoding="utf-8",
    )
    incident_manager = IncidentManager(
        tmp_path / "incident_history.json",
        notification_providers=[
            SuccessfulProvider(enabled=True),
            FailedProvider(enabled=True, retry_attempts=1),
        ],
        notification_history_path=tmp_path / "notification_history.json",
    )
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
    incident_manager.update_incident(
        resolved.incident_id,
        remediation_attempted=True,
        remediation_successful=False,
    )
    incident_manager.resolve_incident(resolved.incident_id)
    return DashboardServices(
        monitor=FakeMonitor(),
        docker_scanner=FakeDockerScanner(),
        incident_manager=incident_manager,
        guardian=SimpleNamespace(),
        restart_history_path=restart_history,
    )


def test_load_restart_history_handles_valid_and_invalid_files(tmp_path: Path) -> None:
    history = tmp_path / "restart_history.json"
    history.write_text(json.dumps({"api": {"attempts": 2}}), encoding="utf-8")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("bad json", encoding="utf-8")

    assert load_restart_history(history) == {"api": {"attempts": 2}}
    assert load_restart_history(invalid) == {}
    assert load_restart_history(tmp_path / "missing.json") == {}


def test_prometheus_exporter_collects_requested_metrics(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.prometheus_exporter.PrometheusExporter._network_stats",
        staticmethod(lambda: {"bytes_sent": 100, "bytes_recv": 200}),
    )
    snapshot = PrometheusExporter(build_services(tmp_path)).collect()

    assert snapshot.values["aegisnex_system_cpu_usage_percent"] == 11.0
    assert snapshot.values["aegisnex_system_memory_usage_percent"] == 22.0
    assert snapshot.values["aegisnex_system_disk_usage_percent"] == 33.0
    assert snapshot.values["aegisnex_system_network_bytes_sent"] == 100.0
    assert snapshot.values["aegisnex_system_network_bytes_received"] == 200.0
    assert snapshot.values["aegisnex_containers_running"] == 2.0
    assert snapshot.values["aegisnex_containers_stopped"] == 1.0
    assert snapshot.values["aegisnex_containers_unhealthy"] == 2.0
    assert snapshot.values["aegisnex_incidents_active"] == 1.0
    assert snapshot.values["aegisnex_incidents_resolved"] == 1.0
    assert snapshot.values["aegisnex_incidents_total"] == 2.0
    assert snapshot.values["aegisnex_remediation_restart_attempts_total"] == 3.0
    assert snapshot.values["aegisnex_remediation_successful_restarts_total"] == 1.0
    assert snapshot.values["aegisnex_remediation_failed_restarts_total"] == 1.0
    assert snapshot.values["aegisnex_notifications_sent_total"] == 3.0
    assert snapshot.values["aegisnex_notifications_failed_total"] == 3.0


def test_prometheus_exporter_renders_metrics_text(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.prometheus_exporter.PrometheusExporter._network_stats",
        staticmethod(lambda: {"bytes_sent": 100, "bytes_recv": 200}),
    )
    payload, content_type = PrometheusExporter(build_services(tmp_path)).render()
    body = payload.decode("utf-8")

    assert content_type.split(";", 1)[0] in {
        "text/plain",
        "application/openmetrics-text",
    }
    assert "aegisnex_system_cpu_usage_percent" in body
    assert "aegisnex_incidents_total" in body


def test_dashboard_metrics_route_returns_prometheus_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pytest.importorskip("fastapi")
    monkeypatch.setenv("AEGISNEX_JWT_SECRET", "test-jwt-secret-for-metrics")
    monkeypatch.setenv("AEGISNEX_METRICS_TOKEN", "test-metrics-token")
    monkeypatch.setattr(
        "src.prometheus_exporter.PrometheusExporter._network_stats",
        staticmethod(lambda: {"bytes_sent": 100, "bytes_recv": 200}),
    )
    app = create_app(build_services(tmp_path))

    status_code, body = asyncio.run(
        asgi_get(app, "/metrics", {"Authorization": "Bearer test-metrics-token"})
    )

    assert status_code == 200
    assert "aegisnex_system_cpu_usage_percent" in body
    assert "aegisnex_notifications_failed_total" in body


async def asgi_get(app, path: str, extra_headers: dict[str, str] | None = None) -> tuple[int, str]:
    messages = []
    request_sent = False
    headers = [(b"host", b"testserver")]
    if extra_headers:
        headers.extend((k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in extra_headers.items())
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
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
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    status_code = next(
        message["status"]
        for message in messages
        if message["type"] == "http.response.start"
    )
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return status_code, body.decode("utf-8")
