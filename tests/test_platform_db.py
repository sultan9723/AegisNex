import sqlite3
from pathlib import Path
from typing import Any

import pytest

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


def test_platform_repository_fetch_dashboard_rows_is_bounded_and_recent(
    tmp_path: Path,
) -> None:
    repository = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    repository.save_metrics_snapshot(
        {"aegisnex_system_cpu_usage_percent": 10},
        timestamp="2026-06-03T00:00:00Z",
    )
    repository.save_metrics_snapshot(
        {"aegisnex_system_cpu_usage_percent": 20},
        timestamp="2026-06-04T00:00:00Z",
    )
    repository.save_metrics_snapshot(
        {"aegisnex_system_cpu_usage_percent": 30},
        timestamp="2026-06-05T00:00:00Z",
    )

    rows = repository.fetch_dashboard_rows(
        "metrics_snapshots",
        since="2026-06-04T00:00:00Z",
        limit=1,
    )

    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2026-06-05T00:00:00Z"


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
    repository.initialize()

    assert {"before_state", "after_state", "execution_id"}.issubset(
        _sqlite_columns(db_path, "audit_logs")
    )
    assert repository.list_audit_logs() == []


def test_platform_repository_creates_fresh_schema_with_audit_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    repository = PlatformRepository(f"sqlite:///{db_path}")
    repository.initialize()

    assert {"before_state", "after_state", "execution_id"}.issubset(
        _sqlite_columns(db_path, "audit_logs")
    )
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


# ============================================================================
# PostgreSQL pooled-connection transaction handling
#
# A connection obtained from psycopg_pool must always be returned via
# pool.putconn() (repository._close_connection), never closed directly and
# never left mid-transaction. `with connection:` (psycopg3) commits/rolls
# back *and closes* the physical connection on exit instead of returning it
# to the pool - that silently leaks a pool slot. Returning a connection that
# still has an open (uncommitted) transaction makes psycopg_pool log
# "rolling back returned connection ... INTRANS" and pay for an extra
# round-trip on every reuse. These tests simulate the postgresql backend
# with a fake connection/pool so they run without a real Postgres server.
# ============================================================================


class FakePgCursor:
    lastrowid = None

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class FakePgConnection:
    def __init__(self, raise_on_execute: Exception | None = None) -> None:
        self.raise_on_execute = raise_on_execute
        self.commit_calls = 0
        self.rollback_calls = 0
        self.closed = False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakePgCursor:
        if self.raise_on_execute is not None:
            raise self.raise_on_execute
        return FakePgCursor()

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.closed = True


def _fake_postgres_repository(
    tmp_path: Path, connection: FakePgConnection
) -> tuple[PlatformRepository, list[Any]]:
    repository = PlatformRepository(f"sqlite:///{tmp_path / 'unused.db'}")
    repository.backend = "postgresql"
    repository._initialized = True
    repository._connect = lambda: connection
    returned: list[Any] = []
    repository._close_connection = lambda conn: returned.append(conn)
    return repository, returned


def test_execute_commits_and_returns_connection_on_success(tmp_path: Path) -> None:
    connection = FakePgConnection()
    repository, returned = _fake_postgres_repository(tmp_path, connection)

    repository._execute("INSERT INTO x VALUES (?)", (1,))

    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0
    assert connection.closed is False
    assert returned == [connection]


def test_execute_rolls_back_and_still_returns_connection_on_error(tmp_path: Path) -> None:
    connection = FakePgConnection(raise_on_execute=RuntimeError("boom"))
    repository, returned = _fake_postgres_repository(tmp_path, connection)

    with pytest.raises(RuntimeError):
        repository._execute("INSERT INTO x VALUES (?)", (1,))

    assert connection.commit_calls == 0
    assert connection.rollback_calls == 1
    assert returned == [connection]


def test_fetch_all_commits_and_returns_connection_on_success(tmp_path: Path) -> None:
    connection = FakePgConnection()
    repository, returned = _fake_postgres_repository(tmp_path, connection)

    rows = repository._fetch_all("SELECT * FROM x")

    assert rows == []
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0
    assert returned == [connection]


def test_fetch_all_rolls_back_and_still_returns_connection_on_error(tmp_path: Path) -> None:
    connection = FakePgConnection(raise_on_execute=RuntimeError("boom"))
    repository, returned = _fake_postgres_repository(tmp_path, connection)

    with pytest.raises(RuntimeError):
        repository._fetch_all("SELECT * FROM x")

    assert connection.commit_calls == 0
    assert connection.rollback_calls == 1
    assert returned == [connection]


def test_health_check_returns_connection_to_pool_instead_of_closing_it(tmp_path: Path) -> None:
    connection = FakePgConnection()
    repository, returned = _fake_postgres_repository(tmp_path, connection)

    result = repository.health_check()

    assert result == {"status": "connected", "backend": "postgresql"}
    assert connection.commit_calls == 1
    assert connection.closed is False
    assert returned == [connection]


def test_health_check_failure_still_returns_connection_to_pool(tmp_path: Path) -> None:
    connection = FakePgConnection(raise_on_execute=RuntimeError("no route to host"))
    repository, returned = _fake_postgres_repository(tmp_path, connection)

    result = repository.health_check()

    assert result["status"] == "disconnected"
    assert connection.rollback_calls == 1
    assert connection.closed is False
    assert returned == [connection]


def test_create_monitoring_target_returns_every_connection_to_pool(tmp_path: Path) -> None:
    connection = FakePgConnection()
    repository, returned = _fake_postgres_repository(tmp_path, connection)

    repository.create_monitoring_target(
        {
            "name": "api",
            "target_type": "http",
            "address": "http://localhost:8000/health",
            "expected_status": 200,
        },
        actor="ops@example.com",
    )

    # insert + the read-back lookup + the audit log write all reuse the same
    # connection and must each be returned, never left checked out.
    assert connection.closed is False
    assert returned.count(connection) == len(returned)
    assert len(returned) >= 3
