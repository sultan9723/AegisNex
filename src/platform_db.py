"""Production data models and repository for AegisNex.

Consolidated single-repository pattern. All data operations go through
PlatformRepository. AegisNexRepository (src/storage.py) is deprecated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import sqlite3
from typing import Any, Dict, Iterable, List, Mapping
from urllib.parse import urlparse

from src.incidents import Incident, utc_timestamp


MONITORING_TARGET_TYPES = {"http", "tcp", "ssl"}

# Tables accessible via fetch_all (whitelist for safety)
ALLOWED_FETCH_TABLES = {
    "incidents",
    "notifications",
    "remediation_actions",
    "remediations",
    "metrics_snapshots",
    "http_checks",
    "ssl_checks",
    "tcp_checks",
    "check_results",
    "audit_logs",
    "reports",
    "users",
    "monitoring_targets",
    "incident_transitions",
}


@dataclass(frozen=True)
class DatabaseModel:
    name: str
    fields: tuple[str, ...]


DATABASE_MODELS = {
    "users": DatabaseModel(
        "users",
        ("id", "email", "hashed_password", "is_active", "is_superuser", "is_verified", "created_at"),
    ),
    "monitoring_targets": DatabaseModel(
        "monitoring_targets",
        (
            "id",
            "name",
            "target_type",
            "address",
            "expected_status",
            "timeout_seconds",
            "warning_days",
            "is_active",
            "last_error",
            "last_status_code",
            "last_response_time_ms",
            "last_successful_check_at",
            "created_at",
            "updated_at",
        ),
    ),
    "incidents": DatabaseModel(
        "incidents",
        (
            "incident_id",
            "timestamp",
            "severity",
            "service_name",
            "incident_type",
            "description",
            "health_check_results",
            "remediation_attempted",
            "remediation_successful",
            "status",
            "incident_status",
            "acknowledged_by",
            "acknowledged_at",
            "resolved_by",
            "resolved_at",
            "resolved_timestamp",
            "resolution_notes",
        ),
    ),
    "notifications": DatabaseModel(
        "notifications",
        ("id", "timestamp", "event_type", "incident_id", "service_name", "provider", "status", "attempts", "message"),
    ),
    "remediation_actions": DatabaseModel(
        "remediation_actions",
        ("id", "timestamp", "service_name", "action", "successful", "incident_id", "details"),
    ),
    "audit_logs": DatabaseModel(
        "audit_logs",
        ("id", "timestamp", "actor", "action", "resource_type", "resource_id", "details"),
    ),
    "reports": DatabaseModel(
        "reports",
        ("id", "timestamp", "report_type", "status", "path", "summary"),
    ),
}


@dataclass(frozen=True)
class DatabaseSettings:
    url: str

    @property
    def backend(self) -> str:
        scheme = urlparse(self.url).scheme.lower()
        if scheme.startswith("postgres"):
            return "postgresql"
        return "sqlite"


def load_database_settings(default_sqlite_path: str = "aegisnex.db") -> DatabaseSettings:
    return DatabaseSettings(
        os.getenv("AEGISNEX_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or f"sqlite:///{default_sqlite_path}"
    )


class PlatformRepository:
    """Single consolidated repository for all AegisNex persistence.

    PostgreSQL is selected with postgresql:// URLs. SQLite is used for local
    development and tests when no database URL is provided.

    This is the successor to AegisNexRepository (src/storage.py) and
    consolidates all data operations into one unified repository.
    """

    def __init__(self, settings: DatabaseSettings | str | None = None) -> None:
        if settings is None:
            self.settings = load_database_settings()
        elif isinstance(settings, str):
            self.settings = DatabaseSettings(settings)
        else:
            self.settings = settings
        self.backend = self.settings.backend
        if self.backend == "sqlite":
            path = self._sqlite_path()
            path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _sqlite_path(self) -> Path:
        parsed = urlparse(self.settings.url)
        if parsed.scheme == "sqlite":
            return Path(parsed.path.lstrip("/") or "aegisnex.db")
        return Path(self.settings.url)

    def _connect(self) -> Any:
        if self.backend == "postgresql":
            return self._pg_connect()
        return self._sqlite_connect()

    def _sqlite_connect(self) -> sqlite3.Connection:
        """Create (or reuse) a SQLite connection with WAL mode and busy timeout."""
        if hasattr(self, "_sqlite_conn") and self._sqlite_conn is not None:
            try:
                self._sqlite_conn.execute("SELECT 1")
                return self._sqlite_conn
            except (sqlite3.OperationalError, sqlite3.ProgrammingError):
                pass
        connection = sqlite3.connect(
            self._sqlite_path(),
            check_same_thread=False,
            timeout=30,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA cache_size=-8000")  # 8MB cache
        connection.execute("PRAGMA foreign_keys=ON")
        self._sqlite_conn = connection
        return connection

    def _pg_connect(self) -> Any:
        """Connect to PostgreSQL with connection pooling."""
        pool = getattr(self, "_pg_pool", None)
        if pool is not None:
            try:
                conn = pool.getconn()
                if conn is not None:
                    return conn
            except Exception:
                pool.close()
                self._pg_pool = None
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "PostgreSQL requires psycopg and psycopg_pool. "
                "Install requirements.txt in production."
            ) from exc

        pool_size = int(os.getenv("AEGISNEX_DB_POOL_SIZE", "10"))
        pool = ConnectionPool(
            self.settings.url,
            min_size=2,
            max_size=pool_size,
            row_factory=dict_row,
            kwargs={"connect_timeout": 5},
        )
        self._pg_pool = pool
        return pool.getconn()

    def _close_connection(self, connection: Any) -> None:
        """Return or close a connection after use."""
        if self.backend == "postgresql":
            pool = getattr(self, "_pg_pool", None)
            if pool is not None:
                try:
                    pool.putconn(connection)
                    return
                except Exception:
                    pass
        try:
            connection.close()
        except Exception:
            pass

    def close(self) -> None:
        """Close all database connections and pools."""
        if self.backend == "postgresql":
            pool = getattr(self, "_pg_pool", None)
            if pool is not None:
                pool.close()
                self._pg_pool = None
        sqlite_conn = getattr(self, "_sqlite_conn", None)
        if sqlite_conn is not None:
            try:
                sqlite_conn.close()
            except Exception:
                pass
            self._sqlite_conn = None

    def initialize(self) -> None:
        with self._connect() as connection:
            for statement in self._schema_statements():
                connection.execute(statement)
            for statement in self._migration_statements(connection):
                connection.execute(statement)
            if self.backend == "postgresql":
                connection.commit()

    def _schema_statements(self) -> List[str]:
        if self.backend == "postgresql":
            serial = "BIGSERIAL PRIMARY KEY"
            bool_type = "BOOLEAN"
            true_default = "TRUE"
            false_default = "FALSE"
            text = "TEXT"
            integer = "INTEGER"
            real = "DOUBLE PRECISION"
        else:
            serial = "INTEGER PRIMARY KEY AUTOINCREMENT"
            bool_type = "INTEGER"
            true_default = "1"
            false_default = "0"
            text = "TEXT"
            integer = "INTEGER"
            real = "REAL"
        return [
            f"""
            CREATE TABLE IF NOT EXISTS users (
                id {serial},
                email {text} NOT NULL UNIQUE,
                hashed_password {text} NOT NULL,
                is_active {bool_type} NOT NULL DEFAULT {true_default},
                is_superuser {bool_type} NOT NULL DEFAULT {false_default},
                is_verified {bool_type} NOT NULL DEFAULT {true_default},
                created_at {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS monitoring_targets (
                id {serial},
                name {text} NOT NULL UNIQUE,
                target_type {text} NOT NULL,
                address {text} NOT NULL,
                expected_status {integer},
                timeout_seconds {integer} NOT NULL DEFAULT 5,
                warning_days {integer} NOT NULL DEFAULT 30,
                is_active {bool_type} NOT NULL DEFAULT {true_default},
                last_error {text},
                last_status_code {integer},
                last_response_time_ms {real},
                last_successful_check_at {text},
                created_at {text} NOT NULL,
                updated_at {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS check_results (
                id {serial},
                target_id {integer},
                target_name {text} NOT NULL,
                target_type {text} NOT NULL,
                timestamp {text} NOT NULL,
                status {text} NOT NULL,
                latency_ms {real},
                details {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS incidents (
                incident_id {text} PRIMARY KEY,
                timestamp {text} NOT NULL,
                severity {text} NOT NULL,
                service_name {text} NOT NULL,
                incident_type {text} NOT NULL,
                description {text} NOT NULL,
                health_check_results {text} NOT NULL,
                remediation_attempted {bool_type} NOT NULL DEFAULT {false_default},
                remediation_successful {bool_type} NOT NULL DEFAULT {false_default},
                status {text} NOT NULL,
                incident_status {text} NOT NULL DEFAULT 'active',
                acknowledged_by {text},
                acknowledged_at {text},
                resolved_by {text},
                resolved_at {text},
                resolved_timestamp {text},
                resolution_notes {text}
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS notifications (
                id {serial},
                timestamp {text} NOT NULL,
                event_type {text} NOT NULL,
                incident_id {text} NOT NULL,
                service_name {text} NOT NULL,
                provider {text} NOT NULL,
                status {text} NOT NULL,
                attempts {integer} NOT NULL,
                message {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS remediation_actions (
                id {serial},
                timestamp {text} NOT NULL,
                service_name {text} NOT NULL,
                action {text} NOT NULL,
                successful {bool_type} NOT NULL,
                incident_id {text},
                details {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS incident_transitions (
                id {serial},
                incident_id {text} NOT NULL,
                timestamp {text} NOT NULL,
                from_status {text},
                to_status {text} NOT NULL,
                actor {text} NOT NULL,
                details {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id {serial},
                timestamp {text} NOT NULL,
                actor {text} NOT NULL,
                action {text} NOT NULL,
                resource_type {text} NOT NULL,
                resource_id {text} NOT NULL,
                details {text} NOT NULL
            )
            """,
            # metrics_snapshots — migrated from AegisNexRepository
            f"""
            CREATE TABLE IF NOT EXISTS metrics_snapshots (
                id {serial},
                timestamp {text} NOT NULL,
                cpu_percent {real} NOT NULL,
                memory_percent {real} NOT NULL,
                disk_percent {real} NOT NULL,
                network_bytes_sent {real} NOT NULL,
                network_bytes_received {real} NOT NULL,
                running_containers {real} NOT NULL,
                stopped_containers {real} NOT NULL,
                unhealthy_containers {real} NOT NULL,
                active_incidents {real} NOT NULL,
                resolved_incidents {real} NOT NULL,
                total_incidents {real} NOT NULL,
                restart_attempts {real} NOT NULL,
                successful_restarts {real} NOT NULL,
                failed_restarts {real} NOT NULL,
                notifications_sent {real} NOT NULL,
                notifications_failed {real} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS reports (
                id {serial},
                timestamp {text} NOT NULL,
                report_type {text} NOT NULL,
                status {text} NOT NULL,
                path {text} NOT NULL,
                summary {text} NOT NULL
            )
            """,
        ]

    def _migration_statements(self, connection: Any) -> List[str]:
        columns = {
            "incident_status": "TEXT",
            "acknowledged_by": "TEXT",
            "acknowledged_at": "TEXT",
            "resolved_by": "TEXT",
            "resolved_at": "TEXT",
            "resolution_notes": "TEXT",
            "last_error": "TEXT",
            "last_status_code": "INTEGER",
            "last_response_time_ms": "DOUBLE PRECISION" if self.backend == "postgresql" else "REAL",
            "last_successful_check_at": "TEXT",
        }
        if self.backend == "postgresql":
            return [
                f"ALTER TABLE monitoring_targets ADD COLUMN IF NOT EXISTS {name} {column_type}"
                for name, column_type in columns.items()
            ]
        existing = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(monitoring_targets)").fetchall()
        }
        alter_statements = [
            f"ALTER TABLE monitoring_targets ADD COLUMN {name} {column_type}"
            for name, column_type in columns.items()
            if name not in existing
        ]
        # Migrate legacy incident data
        updates = [
            "UPDATE incidents SET incident_status = status",
            "UPDATE incidents SET resolved_at = resolved_timestamp WHERE resolved_timestamp IS NOT NULL",
        ]
        return alter_statements + updates

    @property
    def placeholder(self) -> str:
        return "%s" if self.backend == "postgresql" else "?"

    def _execute(self, sql: str, values: Iterable[Any] = ()) -> None:
        connection = self._connect()
        try:
            connection.execute(sql, tuple(values))
            if self.backend == "postgresql":
                connection.commit()
        finally:
            if self.backend == "postgresql":
                self._close_connection(connection)

    def _fetch_all(self, sql: str, values: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(sql, tuple(values)).fetchall()
        finally:
            if self.backend == "postgresql":
                self._close_connection(connection)
        return [dict(row) for row in rows]

    # ========================================================================
    # Generic table operations (migrated from AegisNexRepository.fetch_all)
    # ========================================================================

    def fetch_all(self, table_name: str, limit: int = 0, offset: int = 0) -> List[Dict[str, Any]]:
        """Fetch all rows from a table. Pagination supported via limit/offset.

        Only whitelisted tables are accessible.
        """
        if table_name not in ALLOWED_FETCH_TABLES:
            raise ValueError(f"Unsupported table: {table_name}")
        sql = f"SELECT * FROM {table_name}"
        if limit > 0:
            sql += f" LIMIT {int(limit)}"
            if offset > 0:
                sql += f" OFFSET {int(offset)}"
        return self._fetch_all(sql)

    def table_names(self) -> set[str]:
        """Return the set of table names in the database."""
        if self.backend == "postgresql":
            rows = self._fetch_all(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        else:
            rows = self._fetch_all(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        return {str(row["name"] if self.backend == "postgresql" else row["name"]) for row in rows}

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        return table_name in self.table_names()

    # ========================================================================
    # Metrics snapshots (migrated from AegisNexRepository)
    # ========================================================================

    def save_metrics_snapshot(
        self,
        metrics: Dict[str, float],
        timestamp: str | None = None,
    ) -> None:
        """Save a metrics snapshot to the metrics_snapshots table."""
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO metrics_snapshots (
                timestamp,
                cpu_percent, memory_percent, disk_percent,
                network_bytes_sent, network_bytes_received,
                running_containers, stopped_containers, unhealthy_containers,
                active_incidents, resolved_incidents, total_incidents,
                restart_attempts, successful_restarts, failed_restarts,
                notifications_sent, notifications_failed
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                timestamp or utc_timestamp(),
                _safe_float(metrics.get("aegisnex_system_cpu_usage_percent", 0.0)),
                _safe_float(metrics.get("aegisnex_system_memory_usage_percent", 0.0)),
                _safe_float(metrics.get("aegisnex_system_disk_usage_percent", 0.0)),
                _safe_float(metrics.get("aegisnex_system_network_bytes_sent", 0.0)),
                _safe_float(metrics.get("aegisnex_system_network_bytes_received", 0.0)),
                _safe_float(metrics.get("aegisnex_containers_running", 0.0)),
                _safe_float(metrics.get("aegisnex_containers_stopped", 0.0)),
                _safe_float(metrics.get("aegisnex_containers_unhealthy", 0.0)),
                _safe_float(metrics.get("aegisnex_incidents_active", 0.0)),
                _safe_float(metrics.get("aegisnex_incidents_resolved", 0.0)),
                _safe_float(metrics.get("aegisnex_incidents_total", 0.0)),
                _safe_float(metrics.get("aegisnex_remediation_restart_attempts_total", 0.0)),
                _safe_float(metrics.get("aegisnex_remediation_successful_restarts_total", 0.0)),
                _safe_float(metrics.get("aegisnex_remediation_failed_restarts_total", 0.0)),
                _safe_float(metrics.get("aegisnex_notifications_sent_total", 0.0)),
                _safe_float(metrics.get("aegisnex_notifications_failed_total", 0.0)),
            ),
        )

    # ========================================================================
    # Health check results (migrated from AegisNexRepository)
    # These are stored in the check_results table via save_check_result,
    # but legacy callers may use these individual save methods.
    # ========================================================================

    def save_http_check(self, check: Dict[str, Any]) -> None:
        """Save an HTTP check result (legacy compatibility)."""
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO check_results (
                target_name, target_type, timestamp, status, latency_ms, details
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                str(check.get("name", check.get("endpoint_name", ""))),
                "http",
                str(check.get("timestamp", utc_timestamp())),
                str(check.get("status", "")),
                check.get("latency_ms"),
                json.dumps(dict(check), sort_keys=True),
            ),
        )

    def save_ssl_check(self, check: Dict[str, Any]) -> None:
        """Save an SSL check result (legacy compatibility)."""
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO check_results (
                target_name, target_type, timestamp, status, latency_ms, details
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                str(check.get("name", check.get("target_name", ""))),
                "ssl",
                str(check.get("timestamp", utc_timestamp())),
                str(check.get("status", "")),
                check.get("latency_ms"),
                json.dumps(dict(check), sort_keys=True),
            ),
        )

    def save_tcp_check(self, check: Dict[str, Any]) -> None:
        """Save a TCP check result (legacy compatibility)."""
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO check_results (
                target_name, target_type, timestamp, status, latency_ms, details
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                str(check.get("name", check.get("target_name", ""))),
                "tcp",
                str(check.get("timestamp", utc_timestamp())),
                str(check.get("status", "")),
                check.get("latency_ms"),
                json.dumps(dict(check), sort_keys=True),
            ),
        )

    # ========================================================================
    # Monitoring targets
    # ========================================================================

    def list_monitoring_targets(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        if include_inactive:
            return self._fetch_all("SELECT * FROM monitoring_targets ORDER BY name")
        return self._fetch_all(
            f"SELECT * FROM monitoring_targets WHERE is_active = {self.placeholder} ORDER BY name",
            (True,),
        )

    def create_monitoring_target(self, payload: Mapping[str, Any], actor: str = "system") -> Dict[str, Any]:
        target = self._normalize_target(payload)
        now = utc_timestamp()
        p = self.placeholder
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                INSERT INTO monitoring_targets (
                    name, target_type, address, expected_status, timeout_seconds,
                    warning_days, is_active, created_at, updated_at
                )
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                """,
                (
                    target["name"],
                    target["target_type"],
                    target["address"],
                    target.get("expected_status"),
                    target["timeout_seconds"],
                    target["warning_days"],
                    target["is_active"],
                    now,
                    now,
                ),
            )
            if self.backend == "postgresql":
                connection.commit()
        created = self.get_monitoring_target_by_name(target["name"]) or target
        self.record_audit_log(actor, "create", "monitoring_target", str(created.get("id", target["name"])), created)
        return created

    def update_monitoring_target(self, target_id: int, payload: Mapping[str, Any], actor: str = "system") -> Dict[str, Any] | None:
        existing = self.get_monitoring_target(target_id)
        if existing is None:
            return None
        merged = dict(existing)
        merged.update({key: value for key, value in payload.items() if value is not None})
        target = self._normalize_target(merged)
        p = self.placeholder
        self._execute(
            f"""
            UPDATE monitoring_targets
            SET name = {p}, target_type = {p}, address = {p}, expected_status = {p},
                timeout_seconds = {p}, warning_days = {p}, is_active = {p}, updated_at = {p}
            WHERE id = {p}
            """,
            (
                target["name"],
                target["target_type"],
                target["address"],
                target.get("expected_status"),
                target["timeout_seconds"],
                target["warning_days"],
                target["is_active"],
                utc_timestamp(),
                target_id,
            ),
        )
        updated = self.get_monitoring_target(target_id)
        self.record_audit_log(actor, "update", "monitoring_target", str(target_id), updated or target)
        return updated

    def delete_monitoring_target(self, target_id: int, actor: str = "system") -> bool:
        existing = self.get_monitoring_target(target_id)
        if existing is None:
            return False
        self._execute(f"DELETE FROM monitoring_targets WHERE id = {self.placeholder}", (target_id,))
        self.record_audit_log(actor, "delete", "monitoring_target", str(target_id), existing)
        return True

    def get_monitoring_target(self, target_id: int) -> Dict[str, Any] | None:
        rows = self._fetch_all(
            f"SELECT * FROM monitoring_targets WHERE id = {self.placeholder}",
            (target_id,),
        )
        return rows[0] if rows else None

    def get_monitoring_target_by_name(self, name: str) -> Dict[str, Any] | None:
        rows = self._fetch_all(
            f"SELECT * FROM monitoring_targets WHERE name = {self.placeholder}",
            (name,),
        )
        return rows[0] if rows else None

    # ========================================================================
    # Check results
    # ========================================================================

    def save_check_result(self, target: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO check_results (
                target_id, target_name, target_type, timestamp, status, latency_ms, details
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                target.get("id"),
                target.get("name", result.get("name", "")),
                target.get("target_type", result.get("target_type", "")),
                result.get("timestamp", utc_timestamp()),
                result.get("status", "unknown"),
                result.get("latency_ms"),
                json.dumps(dict(result), sort_keys=True),
            ),
        )
        self.update_target_check_state(target, result)

    def update_target_check_state(self, target: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        target_id = target.get("id")
        if target_id is None:
            return
        target_type = str(target.get("target_type", result.get("target_type", ""))).lower()
        successful = self._result_successful(target_type, result)
        p = self.placeholder
        self._execute(
            f"""
            UPDATE monitoring_targets
            SET last_error = {p},
                last_status_code = {p},
                last_response_time_ms = {p},
                last_successful_check_at = CASE WHEN {p} THEN {p} ELSE last_successful_check_at END,
                updated_at = {p}
            WHERE id = {p}
            """,
            (
                str(result.get("error") or "") or None,
                result.get("status_code"),
                result.get("latency_ms"),
                successful,
                result.get("timestamp", utc_timestamp()),
                utc_timestamp(),
                target_id,
            ),
        )

    # ========================================================================
    # Incidents
    # ========================================================================

    def save_incident(self, incident: Any) -> None:
        incident_status = str(getattr(incident, "incident_status", getattr(incident, "status", "active")))
        acknowledged_by = getattr(incident, "acknowledged_by", None)
        acknowledged_at = getattr(incident, "acknowledged_at", None)
        resolved_by = getattr(incident, "resolved_by", None)
        resolved_at = getattr(incident, "resolved_at", getattr(incident, "resolved_timestamp", None))
        resolution_notes = getattr(incident, "resolution_notes", None)
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO incidents (
                incident_id, timestamp, severity, service_name, incident_type,
                description, health_check_results, remediation_attempted,
                remediation_successful, status, incident_status, acknowledged_by,
                acknowledged_at, resolved_by, resolved_at, resolved_timestamp, resolution_notes
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            ON CONFLICT(incident_id) DO UPDATE SET
                severity = excluded.severity,
                description = excluded.description,
                health_check_results = excluded.health_check_results,
                remediation_attempted = excluded.remediation_attempted,
                remediation_successful = excluded.remediation_successful,
                status = excluded.status,
                incident_status = excluded.incident_status,
                acknowledged_by = excluded.acknowledged_by,
                acknowledged_at = excluded.acknowledged_at,
                resolved_by = excluded.resolved_by,
                resolved_at = excluded.resolved_at,
                resolved_timestamp = excluded.resolved_timestamp,
                resolution_notes = excluded.resolution_notes
            """,
            (
                incident.incident_id,
                incident.timestamp,
                incident.severity,
                incident.service_name,
                incident.incident_type,
                incident.description,
                json.dumps(incident.health_check_results),
                bool(incident.remediation_attempted),
                bool(incident.remediation_successful),
                incident_status,
                incident_status,
                acknowledged_by,
                acknowledged_at,
                resolved_by,
                resolved_at,
                resolved_at,
                resolution_notes,
            ),
        )

    def list_incidents(self, incident_status: str | None = None,
                       limit: int = 0, offset: int = 0) -> List[Dict[str, Any]]:
        """List incidents with optional pagination.

        Args:
            incident_status: Filter by status, or None for all.
            limit: Max rows (0 = no limit).
            offset: Row offset for pagination.
        """
        if incident_status is None:
            sql = "SELECT * FROM incidents ORDER BY timestamp DESC"
        else:
            sql = f"SELECT * FROM incidents WHERE incident_status = {self.placeholder} ORDER BY timestamp DESC"
        if limit > 0:
            sql += f" LIMIT {int(limit)}"
            if offset > 0:
                sql += f" OFFSET {int(offset)}"
        if incident_status is None:
            rows = self._fetch_all(sql)
        else:
            rows = self._fetch_all(sql, (incident_status,))
        return [self._normalize_incident_row(row) for row in rows]

    def get_incident(self, incident_id: str) -> Dict[str, Any] | None:
        rows = self._fetch_all(
            f"SELECT * FROM incidents WHERE incident_id = {self.placeholder}",
            (incident_id,),
        )
        if not rows:
            return None
        return self._normalize_incident_row(rows[0])

    def list_incident_transitions(self, incident_id: str) -> List[Dict[str, Any]]:
        rows = self._fetch_all(
            f"""
            SELECT * FROM incident_transitions
            WHERE incident_id = {self.placeholder}
            ORDER BY timestamp ASC, id ASC
            """,
            (incident_id,),
        )
        return [self._normalize_transition_row(row) for row in rows]

    def save_notification_event(self, event: Mapping[str, Any]) -> None:
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO notifications (
                timestamp, event_type, incident_id, service_name, provider,
                status, attempts, message
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                str(event.get("timestamp", utc_timestamp())),
                str(event.get("event_type", "")),
                str(event.get("incident_id", "")),
                str(event.get("service_name", "")),
                str(event.get("provider", "")),
                str(event.get("status", "")),
                int(event.get("attempts", 0)),
                str(event.get("message", "")),
            ),
        )

    def save_remediation_action(
        self,
        service_name: str,
        action: str,
        successful: bool,
        incident_id: str | None = None,
        details: Mapping[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> None:
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO remediation_actions (
                timestamp, service_name, action, successful, incident_id, details
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                timestamp or utc_timestamp(),
                service_name,
                action,
                bool(successful),
                incident_id,
                json.dumps(dict(details or {}), sort_keys=True),
            ),
        )

    # ========================================================================
    # Check results queries
    # ========================================================================

    def latest_check_results(self) -> List[Dict[str, Any]]:
        """Return the latest check result per target using SQL.

        Uses DISTINCT ON for PostgreSQL, subquery with MAX for SQLite.
        Replaces previous Python-deduplication approach (O(n) memory → O(m)).
        """
        if self.backend == "postgresql":
            sql = """
                SELECT DISTINCT ON (target_id) *
                FROM check_results
                ORDER BY target_id, timestamp DESC
            """
        else:
            sql = """
                SELECT cr.* FROM check_results cr
                INNER JOIN (
                    SELECT target_id, MAX(timestamp) AS max_ts
                    FROM check_results
                    GROUP BY target_id
                ) latest ON cr.target_id = latest.target_id AND cr.timestamp = latest.max_ts
                ORDER BY cr.timestamp DESC
            """
        rows = self._fetch_all(sql)
        for row in rows:
            try:
                row["details"] = json.loads(str(row.get("details", "{}")))
            except json.JSONDecodeError:
                row["details"] = {}
        return rows

    def check_history(self, target_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._fetch_all(
            f"""
            SELECT * FROM check_results
            WHERE target_id = {self.placeholder}
            ORDER BY timestamp DESC
            LIMIT {int(limit)}
            """,
            (target_id,),
        )
        for row in rows:
            try:
                row["details"] = json.loads(str(row.get("details", "{}")))
            except json.JSONDecodeError:
                row["details"] = {}
        return rows

    # ========================================================================
    # Helpers
    # ========================================================================

    @staticmethod
    def _result_successful(target_type: str, result: Mapping[str, Any]) -> bool:
        if target_type == "http":
            return bool(result.get("available"))
        if target_type == "tcp":
            return bool(result.get("reachable"))
        if target_type == "ssl":
            return str(result.get("status")) == "ok"
        return str(result.get("status")) == "ok"

    def record_incident_transition(
        self,
        incident_id: str,
        from_status: str | None,
        to_status: str,
        actor: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO incident_transitions (
                incident_id, timestamp, from_status, to_status, actor, details
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                incident_id,
                utc_timestamp(),
                from_status,
                to_status,
                actor,
                json.dumps(dict(details or {}), sort_keys=True),
            ),
        )

    def record_audit_log(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO audit_logs (
                timestamp, actor, action, resource_type, resource_id, details
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                utc_timestamp(),
                actor,
                action,
                resource_type,
                resource_id,
                json.dumps(dict(details or {}), sort_keys=True),
            ),
        )

    def list_audit_logs(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List audit logs with optional pagination."""
        sql = f"SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT {int(limit)}"
        if offset > 0:
            sql += f" OFFSET {int(offset)}"
        return self._fetch_all(sql)

    # ========================================================================
    # Health check
    # ========================================================================

    def health_check(self) -> Dict[str, Any]:
        """Check database connectivity and return status."""
        try:
            with self._connect() as connection:
                if self.backend == "postgresql":
                    connection.execute("SELECT 1")
                else:
                    connection.execute("SELECT 1")
            return {"status": "connected", "backend": self.backend}
        except Exception as exc:
            return {"status": "disconnected", "backend": self.backend, "error": str(exc)}

    # ========================================================================
    # Normalization
    # ========================================================================

    @staticmethod
    def _normalize_incident_row(row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row)
        normalized.setdefault("incident_status", normalized.get("status"))
        normalized.setdefault("resolved_at", normalized.get("resolved_timestamp"))
        return normalized

    @staticmethod
    def _normalize_transition_row(row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row)
        try:
            normalized["details"] = json.loads(str(normalized.get("details", "{}")))
        except json.JSONDecodeError:
            normalized["details"] = {}
        return normalized

    def _normalize_target(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        target_type = str(payload.get("target_type", payload.get("type", ""))).strip().lower()
        if target_type not in MONITORING_TARGET_TYPES:
            raise ValueError("target_type must be http, tcp, or ssl")
        name = str(payload.get("name", "")).strip()
        address = str(payload.get("address", payload.get("url", payload.get("target", "")))).strip()
        if not name:
            raise ValueError("name is required")
        if not address:
            raise ValueError("address is required")
        expected_status = payload.get("expected_status")
        if expected_status in {"", None}:
            expected_status = 200 if target_type == "http" else None
        return {
            "name": name,
            "target_type": target_type,
            "address": address,
            "expected_status": int(expected_status) if expected_status is not None else None,
            "timeout_seconds": int(payload.get("timeout_seconds") or 5),
            "warning_days": int(payload.get("warning_days") or 30),
            "is_active": bool(payload.get("is_active", True)),
        }


def _safe_float(value: Any) -> float:
    """Safely convert a value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0