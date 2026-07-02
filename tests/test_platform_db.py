from pathlib import Path
import sqlite3

from src.incidents import Incident
from src.platform_db import PlatformRepository


def _sqlite_columns(db_path: Path, table_name: str) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def test_platform_repository_crud_targets_and_audit(tmp_path: Path) -> None:
    repository = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")

    created = repository.create_monitoring_target(
        {
            "name": "api",
            "target_type": "http",
            "address": "http://localhost:8000/health",
            "expected_status": 200,
        },
        actor="ops@example.com",
    )
    updated = repository.update_monitoring_target(
        int(created["id"]),
        {"timeout_seconds": 10},
        actor="ops@example.com",
    )

    assert updated is not None
    assert updated["timeout_seconds"] == 10
    assert repository.list_monitoring_targets()[0]["name"] == "api"
    assert repository.delete_monitoring_target(int(created["id"]), actor="ops@example.com") is True
    assert repository.list_monitoring_targets() == []
    assert len(repository.list_audit_logs()) == 3


def test_platform_repository_saves_latest_check_results(tmp_path: Path) -> None:
    repository = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    target = repository.create_monitoring_target(
        {"name": "db", "target_type": "tcp", "address": "localhost:5432"}
    )

    repository.save_check_result(
        target,
        {
            "name": "db",
            "target_type": "tcp",
            "timestamp": "2026-06-21T12:00:00Z",
            "status": "ok",
            "reachable": True,
            "latency_ms": 3.2,
        },
    )

    latest = repository.latest_check_results()
    refreshed = repository.get_monitoring_target(int(target["id"]))
    history = repository.check_history(int(target["id"]))

    assert len(latest) == 1
    assert latest[0]["details"]["reachable"] is True
    assert refreshed is not None
    assert refreshed["last_response_time_ms"] == 3.2
    assert refreshed["last_successful_check_at"] == "2026-06-21T12:00:00Z"
    assert history[0]["details"]["status"] == "ok"


def test_platform_repository_persists_incident_lifecycle_fields(tmp_path: Path) -> None:
    repository = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    incident = Incident(
        incident_id="INC-42",
        timestamp="2026-06-21T12:00:00Z",
        severity="high",
        service_name="api",
        incident_type="health_check_failed",
        description="api failed",
        health_check_results=[],
        remediation_attempted=False,
        remediation_successful=False,
        status="acknowledged",
        acknowledged_by="ops@example.com",
        acknowledged_at="2026-06-21T12:05:00Z",
        resolved_by=None,
        resolved_timestamp=None,
        resolution_notes=None,
    )

    repository.save_incident(incident)
    repository.record_incident_transition(
        incident.incident_id,
        "active",
        "acknowledged",
        "ops@example.com",
        {"reason": "acknowledged"},
    )

    row = repository.get_incident("INC-42")
    transitions = repository.list_incident_transitions("INC-42")

    assert row is not None
    assert row["incident_status"] == "acknowledged"
    assert row["acknowledged_by"] == "ops@example.com"
    assert row["acknowledged_at"] == "2026-06-21T12:05:00Z"
    assert transitions[0]["to_status"] == "acknowledged"
    assert transitions[0]["details"]["reason"] == "acknowledged"


def test_platform_repository_auto_migrates_legacy_audit_logs_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                hashed_password TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_superuser INTEGER NOT NULL DEFAULT 0,
                is_verified INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                details TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO users (email, hashed_password, is_active, is_superuser, is_verified, created_at)
            VALUES ('old@example.com', 'hash', 1, 0, 1, '2026-06-21T12:00:00Z')
            """
        )
        connection.commit()

    repository = PlatformRepository(f"sqlite:///{db_path}")

    assert {"before_state", "after_state", "execution_id"}.issubset(_sqlite_columns(db_path, "audit_logs"))
    assert repository.list_audit_logs() == []


def test_platform_repository_creates_fresh_schema_with_audit_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    repository = PlatformRepository(f"sqlite:///{db_path}")

    assert {"before_state", "after_state", "execution_id"}.issubset(_sqlite_columns(db_path, "audit_logs"))
    repository.create_monitoring_target(
        {
            "name": "fresh-api",
            "target_type": "http",
            "address": "http://localhost:8080/health",
            "expected_status": 200,
        },
        actor="ops@example.com",
    )
    assert len(repository.list_audit_logs()) == 1
