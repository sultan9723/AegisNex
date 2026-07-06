"""Production data models and repository for AegisNex.

Consolidated single-repository pattern. All data operations go through
PlatformRepository. AegisNexRepository (src/storage.py) is deprecated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Mapping
from urllib.parse import urlparse

from src.incidents import Incident, utc_timestamp

_logger = logging.getLogger(__name__)


# Settings keys — expanded for enterprise platform
SETTINGS_KEYS = frozenset({
    "session_timeout",
    "workspace_name",
    "email_notifications",
    "notification_frequency",
    "timezone",
    "theme",
    "accent_color",
    # SMTP
    "smtp_host",
    "smtp_port",
    "smtp_username",
    "smtp_password",
    "smtp_sender",
    "smtp_recipient",
    # Slack
    "slack_webhook_url",
    # Discord
    "discord_webhook_url",
    # Monitoring intervals
    "monitoring_default_interval_seconds",
    "monitoring_http_timeout",
    "monitoring_ssl_timeout",
    "monitoring_tcp_timeout",
    # Retention
    "retention_check_results_days",
    "retention_metrics_snapshots_days",
    "retention_audit_logs_days",
    # Thresholds
    "threshold_cpu_percent",
    "threshold_memory_percent",
    "threshold_disk_percent",
    # Prometheus
    "prometheus_enabled",
    "prometheus_port",
    # Grafana
    "grafana_url",
    "grafana_api_key",
    # General
    "log_level",
    "log_retention_days",
    "otel_enabled",
    "otel_endpoint",
})

MONITORING_TARGET_TYPES = {"http", "tcp", "ssl", "dns", "container"}
NOTIFICATION_CHANNEL_TYPES = {"email", "slack", "discord"}
ALERT_RULE_SEVERITIES = {"info", "low", "medium", "high", "critical"}

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
    "app_settings",
    "notification_channels",
    "api_keys",
    "alert_rules",
    "secrets",
    "invites",
    "password_resets",
    "approval_queue",
    "backup_records",
    "policies",
    "execution_history",
    "healing_actions",
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
    "app_settings": DatabaseModel(
        "app_settings",
        ("key", "value", "updated_at"),
    ),
    "notification_channels": DatabaseModel(
        "notification_channels",
        ("id", "name", "channel_type", "config", "is_active", "created_at", "updated_at"),
    ),
    "api_keys": DatabaseModel(
        "api_keys",
        ("id", "name", "key_hash", "key_prefix", "role", "is_active", "created_at", "last_used_at", "request_count"),
    ),
    "alert_rules": DatabaseModel(
        "alert_rules",
        ("id", "name", "description", "target_type", "condition", "threshold", "severity",
         "enabled", "created_at", "updated_at"),
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
        self._initialized = False

    def _sqlite_path(self) -> Path:
        parsed = urlparse(self.settings.url)
        if parsed.scheme == "sqlite":
            raw_path = parsed.path or ""
            if raw_path.startswith("//"):
                raw_path = raw_path[1:]
            elif os.name == "nt" and raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
                raw_path = raw_path.lstrip("/")
            elif raw_path.startswith("/"):
                raw_path = raw_path.lstrip("/")
            return Path(raw_path or "aegisnex.db")
        return Path(self.settings.url)

    def _connect(self) -> Any:
        if not getattr(self, '_initialized', False) and not getattr(self, '_initializing', False):
            self._initializing = True
            try:
                self.initialize()
            finally:
                self._initializing = False
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
                _logger.debug("Recreating stale SQLite connection")
                self._sqlite_conn = None
        path = self._sqlite_path()
        _logger.debug("Opening SQLite connection to %s", path)
        connection = sqlite3.connect(
            path,
            check_same_thread=False,
            timeout=30,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            _logger.warning("Could not enable WAL mode on %s (another connection may be active)", path)
        try:
            connection.execute("PRAGMA busy_timeout=30000")
        except sqlite3.OperationalError:
            pass
        try:
            connection.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            pass
        try:
            connection.execute("PRAGMA cache_size=-8000")
        except sqlite3.OperationalError:
            pass
        try:
            connection.execute("PRAGMA foreign_keys=ON")
        except sqlite3.OperationalError:
            pass
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
        except Exception as exc:
            _logger.debug("Error closing database connection: %s", exc)

    def close(self) -> None:
        """Close all database connections and pools."""
        _logger.debug("Closing all database connections")
        if self.backend == "postgresql":
            pool = getattr(self, "_pg_pool", None)
            if pool is not None:
                pool.close()
                self._pg_pool = None
        sqlite_conn = getattr(self, "_sqlite_conn", None)
        if sqlite_conn is not None:
            try:
                sqlite_conn.close()
                _logger.debug("Closed SQLite connection")
            except Exception as exc:
                _logger.debug("Error closing SQLite connection: %s", exc)
            self._sqlite_conn = None

    def initialize(self) -> None:
        if getattr(self, '_initialized', False):
            return
        retries = 3
        for attempt in range(retries):
            try:
                with self._connect() as connection:
                    for statement in self._schema_statements():
                        connection.execute(statement)
                    for statement in self._migration_statements(connection):
                        connection.execute(statement)
                    connection.commit()
                _logger.info("Database initialized successfully")
                self._initialized = True
                return
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc) and attempt < retries - 1:
                    wait = 0.5 * (2 ** attempt)
                    _logger.warning("Database locked during init (attempt %d/%d), retrying in %.1fs", attempt + 1, retries, wait)
                    time.sleep(wait)
                else:
                    raise

    def _tables_exist(self) -> bool:
        """Check whether the schema has already been created."""
        if self.backend == "postgresql":
            return False
        path = self._sqlite_path()
        if not path.exists():
            return False
        try:
            conn = sqlite3.connect(str(path))
            row = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
            conn.close()
            return row is not None and row[0] > 0
        except sqlite3.OperationalError:
            return False

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
                details {text} NOT NULL,
                before_state {text},
                after_state {text},
                execution_id {text}
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
            f"""
            CREATE TABLE IF NOT EXISTS app_settings (
                key {text} PRIMARY KEY,
                value {text} NOT NULL,
                updated_at {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS notification_channels (
                id {serial},
                name {text} NOT NULL UNIQUE,
                channel_type {text} NOT NULL,
                config {text} NOT NULL,
                is_active {bool_type} NOT NULL DEFAULT {true_default},
                created_at {text} NOT NULL,
                updated_at {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS api_keys (
                id {serial},
                name {text} NOT NULL UNIQUE,
                key_hash {text} NOT NULL,
                key_prefix {text} NOT NULL,
                role {text} NOT NULL DEFAULT 'viewer',
                is_active {bool_type} NOT NULL DEFAULT {true_default},
                created_at {text} NOT NULL,
                last_used_at {text},
                request_count {integer} NOT NULL DEFAULT 0
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS alert_rules (
                id {serial},
                name {text} NOT NULL UNIQUE,
                description {text} NOT NULL DEFAULT '',
                target_type {text} NOT NULL DEFAULT '',
                condition {text} NOT NULL DEFAULT 'above',
                threshold {real} NOT NULL DEFAULT 0.0,
                severity {text} NOT NULL DEFAULT 'medium',
                enabled {bool_type} NOT NULL DEFAULT {true_default},
                created_at {text} NOT NULL,
                updated_at {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS policies (
                id {serial},
                name {text} NOT NULL UNIQUE,
                description {text} NOT NULL DEFAULT '',
                action_pattern {text} NOT NULL DEFAULT '*',
                condition {text} NOT NULL DEFAULT 'always',
                effect {text} NOT NULL DEFAULT 'deny',
                priority {integer} NOT NULL DEFAULT 0,
                enabled {bool_type} NOT NULL DEFAULT {true_default},
                created_at {text} NOT NULL,
                updated_at {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS execution_history (
                id {serial},
                execution_id {text} NOT NULL UNIQUE,
                incident_id {text},
                trigger {text} NOT NULL DEFAULT '',
                status {text} NOT NULL DEFAULT 'running',
                data {text} NOT NULL DEFAULT '{{}}',
                started_at {text} NOT NULL,
                completed_at {text}
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS healing_actions (
                id {serial},
                action_id {text} NOT NULL UNIQUE,
                action {text} NOT NULL,
                target {text} NOT NULL DEFAULT '',
                status {text} NOT NULL DEFAULT 'running',
                policy_verdict {text},
                explanation {text} NOT NULL DEFAULT '{{}}',
                details {text} NOT NULL DEFAULT '{{}}',
                error {text},
                duration_ms {real},
                created_at {text} NOT NULL,
                completed_at {text}
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS secrets (
                id {serial},
                name {text} NOT NULL UNIQUE,
                encrypted_value {text} NOT NULL,
                category {text} NOT NULL DEFAULT 'generic',
                is_active {bool_type} NOT NULL DEFAULT {true_default},
                created_at {text} NOT NULL,
                updated_at {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS invites (
                id {serial},
                email {text} NOT NULL,
                token {text} NOT NULL UNIQUE,
                role {text} NOT NULL DEFAULT 'read_only',
                org_id {integer},
                invited_by {text} NOT NULL,
                expires_at {text} NOT NULL,
                accepted_at {text},
                created_at {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS password_resets (
                id {serial},
                user_id {integer} NOT NULL,
                token {text} NOT NULL UNIQUE,
                expires_at {text} NOT NULL,
                used_at {text},
                created_at {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS approval_queue (
                id {serial},
                approval_id {text} NOT NULL UNIQUE,
                request_type {text} NOT NULL,
                requester {text} NOT NULL,
                summary {text} NOT NULL,
                details {text} NOT NULL DEFAULT '{{}}',
                status {text} NOT NULL DEFAULT 'pending',
                reviewed_by {text},
                review_comment {text},
                reviewed_at {text},
                created_at {text} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS backup_records (
                id {serial},
                file_path {text} NOT NULL,
                file_size_bytes {integer} NOT NULL DEFAULT 0,
                label {text} NOT NULL DEFAULT '',
                tables_included {text} NOT NULL DEFAULT '[]',
                knowledge_included {bool_type} NOT NULL DEFAULT {false_default},
                created_by {text} NOT NULL DEFAULT 'system',
                created_at {text} NOT NULL
            )
            """,
        ]

    def _migration_statements(self, connection: Any) -> List[str]:
        columns = {
            "check_interval_seconds": "INTEGER",
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
        # Migrate audit_logs — add before_state, after_state, execution_id columns
        audit_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(audit_logs)").fetchall()}
        audit_migrations = []
        if "before_state" not in audit_columns:
            audit_migrations.append("ALTER TABLE audit_logs ADD COLUMN before_state TEXT")
        if "after_state" not in audit_columns:
            audit_migrations.append("ALTER TABLE audit_logs ADD COLUMN after_state TEXT")
        if "execution_id" not in audit_columns:
            audit_migrations.append("ALTER TABLE audit_logs ADD COLUMN execution_id TEXT")
        # Migrate legacy incident data
        updates = [
            "UPDATE incidents SET incident_status = status",
            "UPDATE incidents SET resolved_at = resolved_timestamp WHERE resolved_timestamp IS NOT NULL",
        ]
        return alter_statements + audit_migrations + updates

    @property
    def placeholder(self) -> str:
        return "%s" if self.backend == "postgresql" else "?"

    def _execute(self, sql: str, values: Iterable[Any] = ()) -> int | None:
        connection = self._connect()
        try:
            cursor = connection.execute(sql, tuple(values))
            if self.backend == "postgresql":
                connection.commit()
            else:
                connection.commit()
            return cursor.lastrowid if hasattr(cursor, "lastrowid") else None
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
            else:
                connection.commit()
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
        sql = f"SELECT * FROM [{table_name}]"
        params: list[Any] = []
        if limit > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
            if offset > 0:
                sql += " OFFSET ?"
                params.append(int(offset))
        return self._fetch_all(sql, params)

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
                    warning_days, is_active, check_interval_seconds, created_at, updated_at
                )
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                """,
                (
                    target["name"],
                    target["target_type"],
                    target["address"],
                    target.get("expected_status"),
                    target["timeout_seconds"],
                    target["warning_days"],
                    target["is_active"],
                    target.get("check_interval_seconds"),
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
                timeout_seconds = {p}, warning_days = {p}, is_active = {p},
                check_interval_seconds = {p}, updated_at = {p}
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
                target.get("check_interval_seconds"),
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
    # Notification channels
    # ========================================================================

    def list_notification_channels(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        if include_inactive:
            sql = "SELECT * FROM notification_channels ORDER BY name"
            return self._fetch_all(sql)
        return self._fetch_all(
            "SELECT * FROM notification_channels WHERE is_active = ? ORDER BY name",
            (1 if self.backend != "postgresql" else True,),
        )

    def get_notification_channel(self, channel_id: int) -> Dict[str, Any] | None:
        rows = self._fetch_all(
            "SELECT * FROM notification_channels WHERE id = ?",
            (channel_id,),
        )
        return rows[0] if rows else None

    def get_notification_channel_by_name(self, name: str) -> Dict[str, Any] | None:
        rows = self._fetch_all(
            "SELECT * FROM notification_channels WHERE name = ?",
            (name,),
        )
        return rows[0] if rows else None

    def create_notification_channel(
        self, payload: Mapping[str, Any], actor: str = "system"
    ) -> Dict[str, Any]:
        p = self.placeholder
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("name is required")
        channel_type = str(payload.get("channel_type", "")).strip().lower()
        if channel_type not in NOTIFICATION_CHANNEL_TYPES:
            raise ValueError(f"channel_type must be one of: {', '.join(sorted(NOTIFICATION_CHANNEL_TYPES))}")
        config = payload.get("config", {})
        if isinstance(config, dict):
            config = json.dumps(config, sort_keys=True)
        now = utc_timestamp()
        self._execute(
            f"""
            INSERT INTO notification_channels (name, channel_type, config, is_active, created_at, updated_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p})
            """,
            (name, channel_type, str(config), 1, now, now),
        )
        self.record_audit_log(actor, "create", "notification_channel", name, {"channel_type": channel_type})
        channel = self.get_notification_channel_by_name(name)
        if channel is None:
            raise RuntimeError("Failed to create notification channel")
        return channel

    def update_notification_channel(
        self, channel_id: int, payload: Mapping[str, Any], actor: str = "system"
    ) -> Dict[str, Any] | None:
        existing = self.get_notification_channel(channel_id)
        if existing is None:
            return None
        name = str(payload.get("name", existing["name"])).strip()
        channel_type = str(payload.get("channel_type", existing.get("channel_type", ""))).strip().lower()
        if channel_type not in NOTIFICATION_CHANNEL_TYPES and channel_type != existing.get("channel_type", ""):
            raise ValueError(f"channel_type must be one of: {', '.join(sorted(NOTIFICATION_CHANNEL_TYPES))}")
        config = payload.get("config")
        if config is not None:
            if isinstance(config, dict):
                config = json.dumps(config, sort_keys=True)
        else:
            config = existing.get("config", "{}")
        is_active = payload.get("is_active", existing.get("is_active", True))
        if isinstance(is_active, bool):
            is_active = 1 if is_active else 0
        is_active = int(is_active)
        now = utc_timestamp()
        p = self.placeholder
        self._execute(
            f"""
            UPDATE notification_channels
            SET name = {p}, channel_type = {p}, config = {p}, is_active = {p}, updated_at = {p}
            WHERE id = {p}
            """,
            (name, channel_type, str(config), is_active, now, channel_id),
        )
        self.record_audit_log(actor, "update", "notification_channel", name, {"channel_type": channel_type})
        return self.get_notification_channel(channel_id)

    def delete_notification_channel(self, channel_id: int, actor: str = "system") -> bool:
        existing = self.get_notification_channel(channel_id)
        if existing is None:
            return False
        name = existing["name"]
        p = self.placeholder
        self._execute("DELETE FROM notification_channels WHERE id = ?", (channel_id,))
        self.record_audit_log(actor, "delete", "notification_channel", name, {})
        return True

    # ========================================================================
    # API Keys
    # ========================================================================

    def list_api_keys(self) -> List[Dict[str, Any]]:
        return self._fetch_all("SELECT * FROM api_keys ORDER BY name")

    def get_api_key(self, key_id: int) -> Dict[str, Any] | None:
        rows = self._fetch_all(
            f"SELECT * FROM api_keys WHERE id = {self.placeholder}",
            (key_id,),
        )
        return rows[0] if rows else None

    def get_api_key_by_hash(self, key_hash: str) -> Dict[str, Any] | None:
        rows = self._fetch_all(
            f"SELECT * FROM api_keys WHERE key_hash = {self.placeholder}",
            (key_hash,),
        )
        return rows[0] if rows else None

    def create_api_key(self, name: str, key_hash: str, key_prefix: str, role: str = "viewer", actor: str = "system") -> Dict[str, Any]:
        now = utc_timestamp()
        p = self.placeholder
        new_id = self._execute(
            f"""
            INSERT INTO api_keys (name, key_hash, key_prefix, role, is_active, created_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p})
            """,
            (name, key_hash, key_prefix, role, 1, now),
        )
        self.record_audit_log(actor, "create", "api_key", name, {"role": role})
        if self.backend != "postgresql":
            key = self.get_api_key_by_hash(key_hash)
        else:
            key = self._fetch_all(f"SELECT * FROM api_keys WHERE id = {self.placeholder}", (new_id,))[0] if new_id else None
        if key is None:
            raise RuntimeError("Failed to create API key")
        return key

    def update_api_key(self, key_id: int, payload: Mapping[str, Any], actor: str = "system") -> Dict[str, Any] | None:
        existing = self.get_api_key(key_id)
        if existing is None:
            return None
        name = str(payload.get("name", existing["name"])).strip()
        role = str(payload.get("role", existing.get("role", "read_only")))
        from src.auth import Role as AuthRole
        normalized_role = AuthRole.from_str(role).value
        is_active = payload.get("is_active", existing.get("is_active", True))
        if isinstance(is_active, bool):
            is_active = 1 if is_active else 0
        p = self.placeholder
        self._execute(
            f"""
            UPDATE api_keys
            SET name = {p}, role = {p}, is_active = {p}
            WHERE id = {p}
            """,
            (name, normalized_role, int(is_active), key_id),
        )
        self.record_audit_log(actor, "update", "api_key", name, {})
        return self.get_api_key(key_id)

    def delete_api_key(self, key_id: int, actor: str = "system") -> bool:
        existing = self.get_api_key(key_id)
        if existing is None:
            return False
        name = existing["name"]
        self._execute(
            f"DELETE FROM api_keys WHERE id = {self.placeholder}",
            (key_id,),
        )
        self.record_audit_log(actor, "delete", "api_key", name, {})
        return True

    def record_api_key_usage(self, key_id: int) -> None:
        p = self.placeholder
        self._execute(
            f"""
            UPDATE api_keys
            SET last_used_at = {p}, request_count = request_count + 1
            WHERE id = {p}
            """,
            (utc_timestamp(), key_id),
        )

    # ========================================================================
    # Alert Rules
    # ========================================================================

    def list_alert_rules(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        if enabled_only:
            return self._fetch_all(
                f"SELECT * FROM alert_rules WHERE enabled = {self.placeholder} ORDER BY name",
                (1 if self.backend != "postgresql" else True,),
            )
        return self._fetch_all("SELECT * FROM alert_rules ORDER BY name")

    def get_alert_rule(self, rule_id: int) -> Dict[str, Any] | None:
        rows = self._fetch_all(
            f"SELECT * FROM alert_rules WHERE id = {self.placeholder}",
            (rule_id,),
        )
        return rows[0] if rows else None

    def get_alert_rule_by_name(self, name: str) -> Dict[str, Any] | None:
        rows = self._fetch_all(
            f"SELECT * FROM alert_rules WHERE name = {self.placeholder}",
            (name,),
        )
        return rows[0] if rows else None

    def create_alert_rule(self, payload: Mapping[str, Any], actor: str = "system") -> Dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("name is required")
        description = str(payload.get("description", "")).strip()
        target_type = str(payload.get("target_type", "")).strip().lower()
        condition = str(payload.get("condition", "above")).strip().lower()
        threshold = float(payload.get("threshold", 0.0))
        severity = str(payload.get("severity", "medium")).strip().lower()
        if severity not in ALERT_RULE_SEVERITIES:
            raise ValueError(f"severity must be one of: {', '.join(sorted(ALERT_RULE_SEVERITIES))}")
        enabled = bool(payload.get("enabled", True))
        now = utc_timestamp()
        p = self.placeholder
        new_id = self._execute(
            f"""
            INSERT INTO alert_rules (name, description, target_type, condition, threshold, severity, enabled, created_at, updated_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            """,
            (name, description, target_type, condition, threshold, severity, 1 if enabled else 0, now, now),
        )
        self.record_audit_log(actor, "create", "alert_rule", name, {"severity": severity, "condition": condition})
        rule = self.get_alert_rule(new_id) if new_id else None
        if rule is None:
            rule = self.get_alert_rule_by_name(name)
        if rule is None:
            raise RuntimeError("Failed to create alert rule")
        return rule

    def update_alert_rule(self, rule_id: int, payload: Mapping[str, Any], actor: str = "system") -> Dict[str, Any] | None:
        existing = self.get_alert_rule(rule_id)
        if existing is None:
            return None
        name = str(payload.get("name", existing["name"])).strip()
        description = str(payload.get("description", existing.get("description", ""))).strip()
        target_type = str(payload.get("target_type", existing.get("target_type", ""))).strip().lower()
        condition = str(payload.get("condition", existing.get("condition", "above"))).strip().lower()
        threshold = float(payload.get("threshold", existing.get("threshold", 0.0)))
        severity = str(payload.get("severity", existing.get("severity", "medium"))).strip().lower()
        if severity not in ALERT_RULE_SEVERITIES:
            raise ValueError(f"severity must be one of: {', '.join(sorted(ALERT_RULE_SEVERITIES))}")
        enabled = payload.get("enabled", existing.get("enabled", True))
        if isinstance(enabled, bool):
            enabled = 1 if enabled else 0
        now = utc_timestamp()
        p = self.placeholder
        self._execute(
            f"""
            UPDATE alert_rules
            SET name = {p}, description = {p}, target_type = {p}, condition = {p},
                threshold = {p}, severity = {p}, enabled = {p}, updated_at = {p}
            WHERE id = {p}
            """,
            (name, description, target_type, condition, threshold, severity, int(enabled), now, rule_id),
        )
        self.record_audit_log(actor, "update", "alert_rule", name, {"severity": severity})
        return self.get_alert_rule(rule_id)

    def delete_alert_rule(self, rule_id: int, actor: str = "system") -> bool:
        existing = self.get_alert_rule(rule_id)
        if existing is None:
            return False
        name = existing["name"]
        self._execute(
            f"DELETE FROM alert_rules WHERE id = {self.placeholder}",
            (rule_id,),
        )
        self.record_audit_log(actor, "delete", "alert_rule", name, {})
        return True

    # ========================================================================
    # Settings
    # ========================================================================

    def get_settings(self) -> Dict[str, str]:
        rows = self._fetch_all("SELECT key, value FROM app_settings")
        return {row["key"]: row["value"] for row in rows}

    def upsert_setting(self, key: str, value: str) -> None:
        if key not in SETTINGS_KEYS:
            raise ValueError(f"Unknown setting key: {key}")
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ({p}, {p}, {p})
            ON CONFLICT(key) DO UPDATE SET value = {p}, updated_at = {p}
            """,
            (key, value, utc_timestamp(), value, utc_timestamp()),
        )

    def update_settings(self, payload: Mapping[str, str]) -> Dict[str, str]:
        for key in payload:
            if key not in SETTINGS_KEYS:
                raise ValueError(f"Unknown setting key: {key}")
        for key, value in payload.items():
            self.upsert_setting(key, value)
        return self.get_settings()

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

    def delete_incident(self, incident_id: str) -> bool:
        p = self.placeholder
        self._execute(f"DELETE FROM incidents WHERE incident_id = {p}", (incident_id,))
        return True

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

    # ========================================================================
    # Policies
    # ========================================================================

    def list_policies(self) -> List[Dict[str, Any]]:
        try:
            return self._fetch_all("SELECT * FROM policies ORDER BY priority DESC")
        except Exception:
            return []

    def save_policy(self, policy: Mapping[str, Any]) -> None:
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO policies (name, description, action_pattern, condition, effect, priority, enabled, created_at, updated_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            ON CONFLICT(name) DO UPDATE SET
                description={p}, action_pattern={p}, condition={p}, effect={p},
                priority={p}, enabled={p}, updated_at={p}
            """,
            (
                policy["name"], policy.get("description", ""), policy.get("action_pattern", "*"),
                policy.get("condition", "always"), policy.get("effect", "deny"),
                int(policy.get("priority", 0)), bool(policy.get("enabled", True)),
                utc_timestamp(), utc_timestamp(),
                policy.get("description", ""), policy.get("action_pattern", "*"),
                policy.get("condition", "always"), policy.get("effect", "deny"),
                int(policy.get("priority", 0)), bool(policy.get("enabled", True)),
                utc_timestamp(),
            ),
        )

    def delete_policy(self, name: str) -> None:
        self._execute("DELETE FROM policies WHERE name = ?", (name,))

    # ========================================================================
    # Execution History
    # ========================================================================

    def save_execution_record(self, record: Mapping[str, Any]) -> None:
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO execution_history (execution_id, incident_id, trigger, status, data, started_at, completed_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
            ON CONFLICT(execution_id) DO UPDATE SET
                status={p}, data={p}, completed_at={p}
            """,
            (
                record.get("execution_id", ""),
                record.get("incident_id"),
                record.get("trigger", ""),
                record.get("status", "running"),
                json.dumps(record, default=str, sort_keys=True),
                record.get("started_at", utc_timestamp()),
                record.get("completed_at"),
                record.get("status", "running"),
                json.dumps(record, default=str, sort_keys=True),
                record.get("completed_at"),
            ),
        )

    def list_execution_history(self, limit: int = 50, status: str | None = None) -> List[Dict[str, Any]]:
        if status:
            rows = self._fetch_all(
                "SELECT * FROM execution_history WHERE status = ? ORDER BY started_at DESC LIMIT ?",
                (status, int(limit)),
            )
        else:
            rows = self._fetch_all(
                "SELECT * FROM execution_history ORDER BY started_at DESC LIMIT ?",
                (int(limit),),
            )
        for row in rows:
            try:
                row["data"] = json.loads(str(row.get("data", "{}")))
            except (json.JSONDecodeError, TypeError):
                row["data"] = {}
        return rows

    # ========================================================================
    # Healing Actions
    # ========================================================================

    def save_healing_action(self, action: Mapping[str, Any]) -> None:
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO healing_actions (action_id, action, target, status, policy_verdict, explanation, details, error, duration_ms, created_at, completed_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            ON CONFLICT(action_id) DO UPDATE SET
                status={p}, details={p}, error={p}, completed_at={p}
            """,
            (
                action.get("action_id", ""),
                action.get("action", ""),
                action.get("target", ""),
                action.get("status", "running"),
                action.get("policy", {}).get("verdict") if isinstance(action.get("policy"), dict) else None,
                json.dumps(action.get("explanation", {}), default=str, sort_keys=True),
                json.dumps(action.get("details", {}), default=str, sort_keys=True),
                action.get("error"),
                action.get("duration_ms"),
                utc_timestamp(),
                utc_timestamp() if action.get("status") in ("completed", "failed") else None,
                action.get("status", "running"),
                json.dumps(action.get("details", {}), default=str, sort_keys=True),
                action.get("error"),
                utc_timestamp() if action.get("status") in ("completed", "failed") else None,
            ),
        )

    def list_healing_actions(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._fetch_all(
            "SELECT * FROM healing_actions ORDER BY created_at DESC LIMIT ?",
            (int(limit),),
        )
        for row in rows:
            for field in ("explanation", "details"):
                try:
                    row[field] = json.loads(str(row.get(field, "{}")))
                except (json.JSONDecodeError, TypeError):
                    row[field] = {}
        return rows

    def record_audit_log(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Mapping[str, Any] | None = None,
        before_state: Mapping[str, Any] | str | None = None,
        after_state: Mapping[str, Any] | str | None = None,
        execution_id: str | None = None,
    ) -> None:
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO audit_logs (
                timestamp, actor, action, resource_type, resource_id, details,
                before_state, after_state, execution_id
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                utc_timestamp(),
                actor,
                action,
                resource_type,
                resource_id,
                json.dumps(dict(details or {}), sort_keys=True),
                json.dumps(dict(before_state)) if isinstance(before_state, Mapping) else before_state,
                json.dumps(dict(after_state)) if isinstance(after_state, Mapping) else after_state,
                execution_id,
            ),
        )

    def list_audit_logs(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List audit logs with optional pagination."""
        sql = "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?"
        params: list[Any] = [int(limit)]
        if offset > 0:
            sql += " OFFSET ?"
            params.append(int(offset))
        return self._fetch_all(sql, params)

    # ========================================================================
    # Enhanced audit log listing
    # ========================================================================

    def list_audit_logs_enhanced(
        self,
        limit: int = 100,
        offset: int = 0,
        actor_filter: str | None = None,
        action_filter: str | None = None,
        resource_type_filter: str | None = None,
        execution_id_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """List audit logs with optional filters."""
        conditions: list[str] = []
        params: list[Any] = []
        if actor_filter:
            conditions.append("actor = ?")
            params.append(actor_filter)
        if action_filter:
            conditions.append("action = ?")
            params.append(action_filter)
        if resource_type_filter:
            conditions.append("resource_type = ?")
            params.append(resource_type_filter)
        if execution_id_filter:
            conditions.append("execution_id = ?")
            params.append(execution_id_filter)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT * FROM audit_logs {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(int(limit))
        if offset > 0:
            sql += " OFFSET ?"
            params.append(int(offset))
        return self._fetch_all(sql, params)

    # ========================================================================
    # Secrets CRUD
    # ========================================================================

    def list_secrets(self) -> list[dict[str, Any]]:
        return self._fetch_all("SELECT id, name, category, is_active, created_at, updated_at FROM secrets ORDER BY name")

    def get_secret(self, name: str) -> str | None:
        rows = self._fetch_all(
            f"SELECT encrypted_value FROM secrets WHERE name = {self.placeholder} AND is_active = 1",
            (name,),
        )
        return rows[0]["encrypted_value"] if rows else None

    def upsert_secret(self, name: str, encrypted_value: str, category: str = "generic", actor: str = "system") -> dict[str, Any]:
        now = utc_timestamp()
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO secrets (name, encrypted_value, category, is_active, created_at, updated_at)
            VALUES ({p}, {p}, {p}, 1, {p}, {p})
            ON CONFLICT(name) DO UPDATE SET
                encrypted_value={p}, category={p}, updated_at={p}
            """,
            (name, encrypted_value, category, now, now, encrypted_value, category, now),
        )
        self.record_audit_log(actor, "upsert_secret", "secret", name, {"category": category})
        rows = self._fetch_all(f"SELECT id, name, category, is_active, created_at, updated_at FROM secrets WHERE name = {p}", (name,))
        return rows[0] if rows else {"name": name, "category": category}

    def delete_secret(self, name: str, actor: str = "system") -> bool:
        p = self.placeholder
        self._execute(f"UPDATE secrets SET is_active = 0, updated_at = {p} WHERE name = {p}", (utc_timestamp(), name))
        self.record_audit_log(actor, "delete_secret", "secret", name, {})
        return True

    def get_secret_metadata(self, name: str) -> dict[str, Any] | None:
        rows = self._fetch_all(
            "SELECT id, name, category, is_active, created_at, updated_at FROM secrets WHERE name = ?",
            (name,),
        )
        return rows[0] if rows else None

    # ========================================================================
    # Invites CRUD
    # ========================================================================

    def create_invite(self, email: str, token: str, role: str, invited_by: str, org_id: int | None = None, expires_in_hours: int = 48) -> dict[str, Any]:
        now = utc_timestamp()
        from datetime import datetime, timedelta, timezone
        expires = (datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)).isoformat().replace("+00:00", "Z")
        p = self.placeholder
        new_id = self._execute(
            f"""
            INSERT INTO invites (email, token, role, org_id, invited_by, expires_at, created_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
            """,
            (email, token, role, org_id, invited_by, expires, now),
        )
        self.record_audit_log(invited_by, "create_invite", "invite", email, {"role": role})
        if new_id:
            rows = self._fetch_all(f"SELECT * FROM invites WHERE id = {p}", (new_id,))
        else:
            rows = self._fetch_all(f"SELECT * FROM invites WHERE token = {p}", (token,))
        return rows[0] if rows else {"token": token, "email": email}

    def get_invite_by_token(self, token: str) -> dict[str, Any] | None:
        rows = self._fetch_all(
            "SELECT * FROM invites WHERE token = ? AND accepted_at IS NULL AND expires_at >= ?",
            (token, utc_timestamp()),
        )
        return rows[0] if rows else None

    def accept_invite(self, token: str) -> bool:
        p = self.placeholder
        self._execute(
            f"UPDATE invites SET accepted_at = {p} WHERE token = {p}",
            (utc_timestamp(), token),
        )
        return True

    def list_invites(self) -> list[dict[str, Any]]:
        return self._fetch_all("SELECT * FROM invites ORDER BY created_at DESC")

    # ========================================================================
    # Password Resets CRUD
    # ========================================================================

    def create_password_reset(self, user_id: int, token: str, expires_in_hours: int = 1) -> dict[str, Any]:
        now = utc_timestamp()
        from datetime import datetime, timedelta, timezone
        expires = (datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)).isoformat().replace("+00:00", "Z")
        p = self.placeholder
        new_id = self._execute(
            f"INSERT INTO password_resets (user_id, token, expires_at, created_at) VALUES ({p}, {p}, {p}, {p})",
            (user_id, token, expires, now),
        )
        rows = self._fetch_all(f"SELECT * FROM password_resets WHERE id = {p}", (new_id,)) if new_id else []
        return rows[0] if rows else {"token": token, "user_id": user_id}

    def get_password_reset_by_token(self, token: str) -> dict[str, Any] | None:
        rows = self._fetch_all(
            "SELECT * FROM password_resets WHERE token = ? AND used_at IS NULL AND expires_at >= ?",
            (token, utc_timestamp()),
        )
        return rows[0] if rows else None

    def use_password_reset(self, token: str) -> bool:
        p = self.placeholder
        self._execute(f"UPDATE password_resets SET used_at = {p} WHERE token = {p}", (utc_timestamp(), token))
        return True

    # ========================================================================
    # Approval Queue CRUD
    # ========================================================================

    def create_approval_request(
        self,
        approval_id: str,
        request_type: str,
        requester: str,
        summary: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_timestamp()
        p = self.placeholder
        self._execute(
            f"""
            INSERT INTO approval_queue (approval_id, request_type, requester, summary, details, status, created_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, 'pending', {p})
            """,
            (approval_id, request_type, requester, summary, json.dumps(dict(details or {}), sort_keys=True), now),
        )
        rows = self._fetch_all(f"SELECT * FROM approval_queue WHERE approval_id = {p}", (approval_id,))
        return rows[0] if rows else {"approval_id": approval_id}

    def list_approval_requests(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if status:
            return self._fetch_all(
                f"SELECT * FROM approval_queue WHERE status = {self.placeholder} ORDER BY created_at DESC LIMIT {int(limit)}",
                (status,),
            )
        return self._fetch_all(f"SELECT * FROM approval_queue ORDER BY created_at DESC LIMIT {int(limit)}")

    def get_approval_request(self, approval_id: str) -> dict[str, Any] | None:
        rows = self._fetch_all(
            f"SELECT * FROM approval_queue WHERE approval_id = {self.placeholder}",
            (approval_id,),
        )
        return rows[0] if rows else None

    def respond_approval(
        self,
        approval_id: str,
        decision: str,
        reviewed_by: str,
        comment: str = "",
    ) -> dict[str, Any] | None:
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        existing = self.get_approval_request(approval_id)
        if existing is None:
            return None
        if existing["status"] != "pending":
            return existing
        now = utc_timestamp()
        p = self.placeholder
        self._execute(
            f"""
            UPDATE approval_queue
            SET status = {p}, reviewed_by = {p}, review_comment = {p}, reviewed_at = {p}
            WHERE approval_id = {p}
            """,
            (decision, reviewed_by, comment, now, approval_id),
        )
        self.record_audit_log(reviewed_by, decision, "approval", approval_id, {"request_type": existing.get("request_type")})
        return self.get_approval_request(approval_id)

    # ========================================================================
    # Backup Records CRUD
    # ========================================================================

    def save_backup_record(
        self,
        file_path: str,
        file_size_bytes: int,
        label: str,
        tables_included: list[str],
        knowledge_included: bool,
        created_by: str = "system",
    ) -> dict[str, Any]:
        now = utc_timestamp()
        p = self.placeholder
        new_id = self._execute(
            f"""
            INSERT INTO backup_records (file_path, file_size_bytes, label, tables_included, knowledge_included, created_by, created_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
            """,
            (file_path, file_size_bytes, label, json.dumps(tables_included), 1 if knowledge_included else 0, created_by, now),
        )
        self.record_audit_log(created_by, "create_backup", "backup", label or file_path, {"size": file_size_bytes, "tables": tables_included})
        rows = self._fetch_all(f"SELECT * FROM backup_records WHERE id = {p}", (new_id,)) if new_id else []
        return rows[0] if rows else {"file_path": file_path, "label": label}

    def list_backup_records(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._fetch_all(f"SELECT * FROM backup_records ORDER BY created_at DESC LIMIT {int(limit)}")
        for row in rows:
            try:
                row["tables_included"] = json.loads(str(row.get("tables_included", "[]")))
            except (json.JSONDecodeError, TypeError):
                row["tables_included"] = []
        return rows

    # ========================================================================
    # Policy CRUD (enhanced)
    # ========================================================================

    def get_policy_by_name(self, name: str) -> dict[str, Any] | None:
        rows = self._fetch_all(
            f"SELECT * FROM policies WHERE name = {self.placeholder}",
            (name,),
        )
        return rows[0] if rows else None

    # ========================================================================
    # Health check
    # ========================================================================

    def health_check(self) -> Dict[str, Any]:
        """Check database connectivity and return status."""
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1")
            return {"status": "connected", "backend": self.backend}
        except Exception as exc:
            _logger.warning("Database health check failed: %s", exc)
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
            "check_interval_seconds": payload.get("check_interval_seconds"),
        }


def _safe_float(value: Any) -> float:
    """Safely convert a value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
