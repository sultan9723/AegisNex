"""initial_schema

Revision ID: 369f8483bf6d
Revises: 
Create Date: 2026-06-23 00:36:47.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '369f8483bf6d'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_superuser INTEGER NOT NULL DEFAULT 0,
    is_verified INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
)
"""

CREATE_MONITORING_TARGETS = """
CREATE TABLE IF NOT EXISTS monitoring_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    target_type TEXT NOT NULL,
    address TEXT NOT NULL,
    expected_status INTEGER,
    timeout_seconds INTEGER NOT NULL DEFAULT 5,
    warning_days INTEGER NOT NULL DEFAULT 30,
    is_active INTEGER NOT NULL DEFAULT 1,
    last_error TEXT,
    last_status_code INTEGER,
    last_response_time_ms REAL,
    last_successful_check_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    incident_status TEXT,
    acknowledged_by TEXT,
    acknowledged_at TEXT,
    resolved_by TEXT,
    resolved_at TEXT,
    resolution_notes TEXT
)
"""

CREATE_CHECK_RESULTS = """
CREATE TABLE IF NOT EXISTS check_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER,
    target_name TEXT NOT NULL,
    target_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms REAL,
    details TEXT NOT NULL
)
"""

CREATE_INCIDENTS = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    severity TEXT NOT NULL,
    service_name TEXT NOT NULL,
    incident_type TEXT NOT NULL,
    description TEXT NOT NULL,
    health_check_results TEXT NOT NULL,
    remediation_attempted INTEGER NOT NULL DEFAULT 0,
    remediation_successful INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    incident_status TEXT NOT NULL DEFAULT 'active',
    acknowledged_by TEXT,
    acknowledged_at TEXT,
    resolved_by TEXT,
    resolved_at TEXT,
    resolved_timestamp TEXT,
    resolution_notes TEXT
)
"""

CREATE_NOTIFICATIONS = """
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
)
"""

CREATE_REMEDIATION_ACTIONS = """
CREATE TABLE IF NOT EXISTS remediation_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    service_name TEXT NOT NULL,
    action TEXT NOT NULL,
    successful INTEGER NOT NULL,
    incident_id TEXT,
    details TEXT NOT NULL
)
"""

CREATE_INCIDENT_TRANSITIONS = """
CREATE TABLE IF NOT EXISTS incident_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    details TEXT NOT NULL
)
"""

CREATE_AUDIT_LOGS = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    details TEXT NOT NULL
)
"""

CREATE_METRICS_SNAPSHOTS = """
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
)
"""

CREATE_REPORTS = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    report_type TEXT NOT NULL,
    status TEXT NOT NULL,
    path TEXT NOT NULL,
    summary TEXT NOT NULL
)
"""

INDEX_CHECK_RESULTS_TARGET_ID = "CREATE INDEX IF NOT EXISTS ix_check_results_target_id ON check_results (target_id)"
INDEX_CHECK_RESULTS_TIMESTAMP = "CREATE INDEX IF NOT EXISTS ix_check_results_timestamp ON check_results (timestamp)"
INDEX_INCIDENTS_TIMESTAMP = "CREATE INDEX IF NOT EXISTS ix_incidents_timestamp ON incidents (timestamp)"
INDEX_INCIDENTS_STATUS = "CREATE INDEX IF NOT EXISTS ix_incidents_incident_status ON incidents (incident_status)"
INDEX_METRICS_TIMESTAMP = "CREATE INDEX IF NOT EXISTS ix_metrics_snapshots_timestamp ON metrics_snapshots (timestamp)"
INDEX_AUDIT_LOGS_TIMESTAMP = "CREATE INDEX IF NOT EXISTS ix_audit_logs_timestamp ON audit_logs (timestamp)"

MIGRATE_INCIDENTS_STATUS = "UPDATE incidents SET incident_status = status WHERE incident_status IS NULL"
MIGRATE_INCIDENTS_RESOLVED = "UPDATE incidents SET resolved_at = resolved_timestamp WHERE resolved_timestamp IS NOT NULL"


def upgrade() -> None:
    """Create the initial AegisNex schema with indexes."""
    op.execute(CREATE_USERS)
    op.execute(CREATE_MONITORING_TARGETS)
    op.execute(CREATE_CHECK_RESULTS)
    op.execute(CREATE_INCIDENTS)
    op.execute(CREATE_NOTIFICATIONS)
    op.execute(CREATE_REMEDIATION_ACTIONS)
    op.execute(CREATE_INCIDENT_TRANSITIONS)
    op.execute(CREATE_AUDIT_LOGS)
    op.execute(CREATE_METRICS_SNAPSHOTS)
    op.execute(CREATE_REPORTS)

    # Indexes for common queries
    op.execute(INDEX_CHECK_RESULTS_TARGET_ID)
    op.execute(INDEX_CHECK_RESULTS_TIMESTAMP)
    op.execute(INDEX_INCIDENTS_TIMESTAMP)
    op.execute(INDEX_INCIDENTS_STATUS)
    op.execute(INDEX_METRICS_TIMESTAMP)
    op.execute(INDEX_AUDIT_LOGS_TIMESTAMP)

    # Backfill legacy incident data if needed
    op.execute(MIGRATE_INCIDENTS_STATUS)
    op.execute(MIGRATE_INCIDENTS_RESOLVED)


def downgrade() -> None:
    """Drop all tables created in upgrade."""
    op.execute("DROP TABLE IF EXISTS reports")
    op.execute("DROP TABLE IF EXISTS metrics_snapshots")
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS incident_transitions")
    op.execute("DROP TABLE IF EXISTS remediation_actions")
    op.execute("DROP TABLE IF EXISTS notifications")
    op.execute("DROP TABLE IF EXISTS incidents")
    op.execute("DROP TABLE IF EXISTS check_results")
    op.execute("DROP TABLE IF EXISTS monitoring_targets")
    op.execute("DROP TABLE IF EXISTS users")