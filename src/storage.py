"""SQLite persistence layer for AegisNex historical operational data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
from typing import Any, Dict, Iterable, Optional

from src.incidents import Incident, utc_timestamp


@dataclass(frozen=True)
class StorageConfig:
    database_path: Path


class AegisNexRepository:
    """Repository for durable operational history."""

    def __init__(self, database_path: str | Path = "aegisnex.db") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    incident_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    health_check_results TEXT NOT NULL,
                    remediation_attempted INTEGER NOT NULL,
                    remediation_successful INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    incident_status TEXT NOT NULL DEFAULT 'active',
                    acknowledged_by TEXT,
                    acknowledged_at TEXT,
                    resolved_by TEXT,
                    resolved_at TEXT,
                    resolved_timestamp TEXT,
                    resolution_notes TEXT
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    incident_id TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    message TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS remediations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    successful INTEGER NOT NULL,
                    incident_id TEXT,
                    details TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS metrics_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cpu_percent REAL NOT NULL,
                    memory_percent REAL NOT NULL,
                    disk_percent REAL NOT NULL,
                    network_bytes_sent REAL NOT NULL,
                    network_bytes_received REAL NOT NULL,
                    running_containers REAL NOT NULL,
                    stopped_containers REAL NOT NULL,
                    unhealthy_containers REAL NOT NULL,
                    active_incidents REAL NOT NULL,
                    resolved_incidents REAL NOT NULL,
                    total_incidents REAL NOT NULL,
                    restart_attempts REAL NOT NULL,
                    successful_restarts REAL NOT NULL,
                    failed_restarts REAL NOT NULL,
                    notifications_sent REAL NOT NULL,
                    notifications_failed REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS http_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    endpoint_name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    available INTEGER NOT NULL,
                    expected_status INTEGER NOT NULL,
                    status_code INTEGER,
                    latency_ms REAL,
                    error TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ssl_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    target_name TEXT NOT NULL,
                    target TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    valid INTEGER NOT NULL,
                    issuer TEXT NOT NULL,
                    expires_at TEXT,
                    days_remaining INTEGER,
                    warning_days INTEGER NOT NULL,
                    error TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tcp_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    target_name TEXT NOT NULL,
                    target TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    reachable INTEGER NOT NULL,
                    latency_ms REAL,
                    error TEXT NOT NULL
                );
                """
            )
            for statement in self._incident_migration_statements(connection):
                connection.execute(statement)

    def _incident_migration_statements(self, connection: sqlite3.Connection) -> list[str]:
        existing = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(incidents)").fetchall()
        }
        columns = {
            "incident_status": "TEXT NOT NULL DEFAULT 'active'",
            "acknowledged_by": "TEXT",
            "acknowledged_at": "TEXT",
            "resolved_by": "TEXT",
            "resolved_at": "TEXT",
            "resolution_notes": "TEXT",
        }
        statements = [
            f"ALTER TABLE incidents ADD COLUMN {name} {definition}"
            for name, definition in columns.items()
            if name not in existing
        ]
        statements.extend(
            [
                "UPDATE incidents SET incident_status = status",
                "UPDATE incidents SET resolved_at = resolved_timestamp WHERE resolved_timestamp IS NOT NULL",
            ]
        )
        return statements

    def save_incident(self, incident: Incident) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO incidents (
                    incident_id,
                    timestamp,
                    severity,
                    service_name,
                    incident_type,
                    description,
                    health_check_results,
                    remediation_attempted,
                    remediation_successful,
                    status,
                    incident_status,
                    acknowledged_by,
                    acknowledged_at,
                    resolved_by,
                    resolved_at,
                    resolved_timestamp,
                    resolution_notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    int(incident.remediation_attempted),
                    int(incident.remediation_successful),
                    incident.status,
                    getattr(incident, "incident_status", incident.status),
                    getattr(incident, "acknowledged_by", None),
                    getattr(incident, "acknowledged_at", None),
                    getattr(incident, "resolved_by", None),
                    getattr(incident, "resolved_at", incident.resolved_timestamp),
                    incident.resolved_timestamp,
                    getattr(incident, "resolution_notes", None),
                ),
            )

    def save_notification_event(self, event: Dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO notifications (
                    timestamp,
                    event_type,
                    incident_id,
                    service_name,
                    provider,
                    status,
                    attempts,
                    message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        incident_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO remediations (
                    timestamp,
                    service_name,
                    action,
                    successful,
                    incident_id,
                    details
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp or utc_timestamp(),
                    service_name,
                    action,
                    int(successful),
                    incident_id,
                    json.dumps(details or {}),
                ),
            )

    def save_metrics_snapshot(
        self,
        metrics: Dict[str, float],
        timestamp: Optional[str] = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO metrics_snapshots (
                    timestamp,
                    cpu_percent,
                    memory_percent,
                    disk_percent,
                    network_bytes_sent,
                    network_bytes_received,
                    running_containers,
                    stopped_containers,
                    unhealthy_containers,
                    active_incidents,
                    resolved_incidents,
                    total_incidents,
                    restart_attempts,
                    successful_restarts,
                    failed_restarts,
                    notifications_sent,
                    notifications_failed
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp or utc_timestamp(),
                    metrics.get("aegisnex_system_cpu_usage_percent", 0.0),
                    metrics.get("aegisnex_system_memory_usage_percent", 0.0),
                    metrics.get("aegisnex_system_disk_usage_percent", 0.0),
                    metrics.get("aegisnex_system_network_bytes_sent", 0.0),
                    metrics.get("aegisnex_system_network_bytes_received", 0.0),
                    metrics.get("aegisnex_containers_running", 0.0),
                    metrics.get("aegisnex_containers_stopped", 0.0),
                    metrics.get("aegisnex_containers_unhealthy", 0.0),
                    metrics.get("aegisnex_incidents_active", 0.0),
                    metrics.get("aegisnex_incidents_resolved", 0.0),
                    metrics.get("aegisnex_incidents_total", 0.0),
                    metrics.get("aegisnex_remediation_restart_attempts_total", 0.0),
                    metrics.get("aegisnex_remediation_successful_restarts_total", 0.0),
                    metrics.get("aegisnex_remediation_failed_restarts_total", 0.0),
                    metrics.get("aegisnex_notifications_sent_total", 0.0),
                    metrics.get("aegisnex_notifications_failed_total", 0.0),
                ),
            )

    def save_http_check(self, check: Dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO http_checks (
                    timestamp,
                    endpoint_name,
                    url,
                    status,
                    available,
                    expected_status,
                    status_code,
                    latency_ms,
                    error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(check.get("timestamp", utc_timestamp())),
                    str(check.get("name", check.get("endpoint_name", ""))),
                    str(check.get("url", "")),
                    str(check.get("status", "")),
                    int(bool(check.get("available", False))),
                    int(check.get("expected_status", 200)),
                    check.get("status_code"),
                    check.get("latency_ms"),
                    str(check.get("error", "")),
                ),
            )

    def save_ssl_check(self, check: Dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ssl_checks (
                    timestamp,
                    target_name,
                    target,
                    host,
                    port,
                    status,
                    valid,
                    issuer,
                    expires_at,
                    days_remaining,
                    warning_days,
                    error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(check.get("timestamp", utc_timestamp())),
                    str(check.get("name", check.get("target_name", ""))),
                    str(check.get("target", "")),
                    str(check.get("host", "")),
                    int(check.get("port", 443)),
                    str(check.get("status", "")),
                    int(bool(check.get("valid", False))),
                    str(check.get("issuer", "")),
                    check.get("expires_at"),
                    check.get("days_remaining"),
                    int(check.get("warning_days", 30)),
                    str(check.get("error", "")),
                ),
            )

    def save_tcp_check(self, check: Dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tcp_checks (
                    timestamp,
                    target_name,
                    target,
                    host,
                    port,
                    status,
                    reachable,
                    latency_ms,
                    error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(check.get("timestamp", utc_timestamp())),
                    str(check.get("name", check.get("target_name", ""))),
                    str(check.get("target", "")),
                    str(check.get("host", "")),
                    int(check.get("port", 0)),
                    str(check.get("status", "")),
                    int(bool(check.get("reachable", False))),
                    check.get("latency_ms"),
                    str(check.get("error", "")),
                ),
            )

    def fetch_all(self, table_name: str) -> list[Dict[str, Any]]:
        allowed = {
            "incidents",
            "notifications",
            "remediations",
            "metrics_snapshots",
            "http_checks",
            "ssl_checks",
            "tcp_checks",
        }
        if table_name not in allowed:
            raise ValueError(f"Unsupported table: {table_name}")
        with self._connect() as connection:
            rows = connection.execute(f"SELECT * FROM {table_name}").fetchall()
        return [dict(row) for row in rows]

    def table_names(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        return {str(row["name"]) for row in rows}
