from pathlib import Path

from src.incidents import Incident
from src.platform_db import PlatformRepository


def sample_incident() -> Incident:
    return Incident(
        incident_id="INC-1",
        timestamp="2026-06-04T12:00:00Z",
        severity="high",
        service_name="api",
        incident_type="health_check_failed",
        description="api failed",
        health_check_results=[
            {"name": "http", "status": "503", "healthy": False, "message": "down"}
        ],
        remediation_attempted=False,
        remediation_successful=False,
        status="active",
        resolved_timestamp=None,
    )


def test_repository_creates_database_and_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "aegisnex.db"

    repository = PlatformRepository(str(db_path))
    repository.initialize()

    assert db_path.exists()
    assert {
        "incidents",
        "notifications",
        "remediation_actions",
        "metrics_snapshots",
        "check_results",
    }.issubset(repository.table_names())


def test_repository_saves_and_updates_incident(tmp_path: Path) -> None:
    repository = PlatformRepository(str(tmp_path / "aegisnex.db"))
    incident = sample_incident()

    repository.save_incident(incident)
    incident.status = "resolved"
    incident.resolved_timestamp = "2026-06-04T12:05:00Z"
    incident.remediation_attempted = True
    incident.remediation_successful = True
    repository.save_incident(incident)

    rows = repository.fetch_all("incidents")
    assert len(rows) == 1
    assert rows[0]["incident_id"] == "INC-1"
    assert rows[0]["status"] == "resolved"
    assert rows[0]["remediation_successful"] == 1
    assert "http" in rows[0]["health_check_results"]


def test_repository_saves_notification_event(tmp_path: Path) -> None:
    repository = PlatformRepository(str(tmp_path / "aegisnex.db"))

    repository.save_notification_event(
        {
            "timestamp": "2026-06-04T12:00:00Z",
            "event_type": "incident_created",
            "incident_id": "INC-1",
            "service_name": "api",
            "provider": "slack",
            "status": "ok",
            "attempts": 2,
            "message": "",
        }
    )

    rows = repository.fetch_all("notifications")
    assert len(rows) == 1
    assert rows[0]["provider"] == "slack"
    assert rows[0]["status"] == "ok"
    assert rows[0]["attempts"] == 2


def test_repository_saves_remediation_action(tmp_path: Path) -> None:
    repository = PlatformRepository(str(tmp_path / "aegisnex.db"))

    repository.save_remediation_action(
        service_name="api",
        action="restart",
        successful=True,
        incident_id="INC-1",
        details={"container": "api", "action": "restarted"},
        timestamp="2026-06-04T12:00:00Z",
    )

    rows = repository.fetch_all("remediation_actions")
    assert len(rows) == 1
    assert rows[0]["service_name"] == "api"
    assert rows[0]["action"] == "restart"
    assert rows[0]["successful"] == 1
    assert "restarted" in rows[0]["details"]


def test_repository_saves_metrics_snapshot(tmp_path: Path) -> None:
    repository = PlatformRepository(str(tmp_path / "aegisnex.db"))

    repository.save_metrics_snapshot(
        {
            "aegisnex_system_cpu_usage_percent": 10,
            "aegisnex_system_memory_usage_percent": 20,
            "aegisnex_system_disk_usage_percent": 30,
            "aegisnex_system_network_bytes_sent": 100,
            "aegisnex_system_network_bytes_received": 200,
            "aegisnex_containers_running": 3,
            "aegisnex_containers_stopped": 1,
            "aegisnex_containers_unhealthy": 0,
            "aegisnex_incidents_active": 2,
            "aegisnex_incidents_resolved": 4,
            "aegisnex_incidents_total": 6,
            "aegisnex_remediation_restart_attempts_total": 5,
            "aegisnex_remediation_successful_restarts_total": 4,
            "aegisnex_remediation_failed_restarts_total": 1,
            "aegisnex_notifications_sent_total": 8,
            "aegisnex_notifications_failed_total": 2,
        },
        timestamp="2026-06-04T12:00:00Z",
    )

    rows = repository.fetch_all("metrics_snapshots")
    assert len(rows) == 1
    assert rows[0]["cpu_percent"] == 10
    assert rows[0]["running_containers"] == 3
    assert rows[0]["notifications_failed"] == 2


def test_repository_saves_http_checks(tmp_path: Path) -> None:
    repository = PlatformRepository(str(tmp_path / "aegisnex.db"))

    repository.save_http_check(
        {
            "timestamp": "2026-06-20T12:00:00Z",
            "name": "api",
            "url": "http://localhost:8000/health",
            "status": "ok",
            "available": True,
            "expected_status": 200,
            "status_code": 200,
            "latency_ms": 12.5,
            "error": "",
        }
    )

    rows = repository.fetch_all("check_results")
    http_rows = [r for r in rows if r.get("target_type") == "http"]

    assert len(http_rows) == 1
    assert http_rows[0]["target_name"] == "api"
    assert http_rows[0]["status"] == "ok"
    assert http_rows[0]["latency_ms"] == 12.5


def test_repository_saves_ssl_checks(tmp_path: Path) -> None:
    repository = PlatformRepository(str(tmp_path / "aegisnex.db"))

    repository.save_ssl_check(
        {
            "timestamp": "2026-06-20T12:00:00Z",
            "name": "api",
            "target": "example.com:443",
            "host": "example.com",
            "port": 443,
            "status": "warning",
            "valid": False,
            "issuer": "Example CA",
            "expires_at": "2026-07-01T00:00:00Z",
            "days_remaining": 10,
            "warning_days": 30,
            "error": "",
        }
    )

    rows = repository.fetch_all("check_results")
    ssl_rows = [r for r in rows if r.get("target_type") == "ssl"]

    assert len(ssl_rows) == 1
    assert ssl_rows[0]["target_name"] == "api"
    assert ssl_rows[0]["status"] == "warning"


def test_repository_saves_tcp_checks(tmp_path: Path) -> None:
    repository = PlatformRepository(str(tmp_path / "aegisnex.db"))

    repository.save_tcp_check(
        {
            "timestamp": "2026-06-20T12:00:00Z",
            "name": "db",
            "target": "localhost:5432",
            "host": "localhost",
            "port": 5432,
            "status": "ok",
            "reachable": True,
            "latency_ms": 4.2,
            "error": "",
        }
    )

    rows = repository.fetch_all("check_results")
    tcp_rows = [r for r in rows if r.get("target_type") == "tcp"]

    assert len(tcp_rows) == 1
    assert tcp_rows[0]["target_name"] == "db"
    assert tcp_rows[0]["status"] == "ok"
    assert tcp_rows[0]["latency_ms"] == 4.2


def test_repository_rejects_unknown_table(tmp_path: Path) -> None:
    repository = PlatformRepository(str(tmp_path / "aegisnex.db"))

    try:
        repository.fetch_all("sqlite_master")
    except ValueError as exc:
        assert "Unsupported table" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported table")
