"""initial_schema

Revision ID: 369f8483bf6d
Revises:
Create Date: 2026-06-23 00:36:47.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "369f8483bf6d"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    if context.is_offline_mode():
        return False
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _create_table_if_missing(table_name: str, *columns: sa.Column) -> None:
    if _table_exists(table_name):
        return
    op.create_table(table_name, *columns)


def _integer_pk() -> sa.Column:
    return sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True)


def upgrade() -> None:
    """Create the initial AegisNex schema with indexes."""
    _create_table_if_missing(
        "users",
        _integer_pk(),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    _create_table_if_missing(
        "monitoring_targets",
        _integer_pk(),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("expected_status", sa.Integer(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("warning_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_response_time_ms", sa.Float(), nullable=True),
        sa.Column("last_successful_check_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("incident_status", sa.Text(), nullable=True),
        sa.Column("acknowledged_by", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.Text(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
    )
    _create_table_if_missing(
        "check_results",
        _integer_pk(),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("target_name", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("details", sa.Text(), nullable=False),
    )
    _create_table_if_missing(
        "incidents",
        sa.Column("incident_id", sa.Text(), primary_key=True),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("service_name", sa.Text(), nullable=False),
        sa.Column("incident_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("health_check_results", sa.Text(), nullable=False),
        sa.Column("remediation_attempted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("remediation_successful", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("incident_status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("acknowledged_by", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.Text(), nullable=True),
        sa.Column("resolved_timestamp", sa.Text(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
    )
    _create_table_if_missing(
        "notifications",
        _integer_pk(),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("incident_id", sa.Text(), nullable=False),
        sa.Column("service_name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
    )
    _create_table_if_missing(
        "remediation_actions",
        _integer_pk(),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("service_name", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("successful", sa.Boolean(), nullable=False),
        sa.Column("incident_id", sa.Text(), nullable=True),
        sa.Column("details", sa.Text(), nullable=False),
    )
    _create_table_if_missing(
        "incident_transitions",
        _integer_pk(),
        sa.Column("incident_id", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
    )
    _create_table_if_missing(
        "audit_logs",
        _integer_pk(),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
    )
    _create_table_if_missing(
        "metrics_snapshots",
        _integer_pk(),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("cpu_percent", sa.Float(), nullable=False),
        sa.Column("memory_percent", sa.Float(), nullable=False),
        sa.Column("disk_percent", sa.Float(), nullable=False),
        sa.Column("network_bytes_sent", sa.Float(), nullable=False),
        sa.Column("network_bytes_received", sa.Float(), nullable=False),
        sa.Column("running_containers", sa.Float(), nullable=False),
        sa.Column("stopped_containers", sa.Float(), nullable=False),
        sa.Column("unhealthy_containers", sa.Float(), nullable=False),
        sa.Column("active_incidents", sa.Float(), nullable=False),
        sa.Column("resolved_incidents", sa.Float(), nullable=False),
        sa.Column("total_incidents", sa.Float(), nullable=False),
        sa.Column("restart_attempts", sa.Float(), nullable=False),
        sa.Column("successful_restarts", sa.Float(), nullable=False),
        sa.Column("failed_restarts", sa.Float(), nullable=False),
        sa.Column("notifications_sent", sa.Float(), nullable=False),
        sa.Column("notifications_failed", sa.Float(), nullable=False),
    )
    _create_table_if_missing(
        "reports",
        _integer_pk(),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("report_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
    )

    op.create_index(
        "ix_check_results_target_id",
        "check_results",
        ["target_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_check_results_timestamp",
        "check_results",
        ["timestamp"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_incidents_timestamp",
        "incidents",
        ["timestamp"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_incidents_incident_status",
        "incidents",
        ["incident_status"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_metrics_snapshots_timestamp",
        "metrics_snapshots",
        ["timestamp"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_audit_logs_timestamp",
        "audit_logs",
        ["timestamp"],
        if_not_exists=True,
    )

    # Backfill legacy incident data if needed.
    op.execute("UPDATE incidents SET incident_status = status WHERE incident_status IS NULL")
    op.execute(
        "UPDATE incidents SET resolved_at = resolved_timestamp "
        "WHERE resolved_timestamp IS NOT NULL"
    )


def downgrade() -> None:
    """Drop all tables created in upgrade."""
    op.drop_table("reports", if_exists=True)
    op.drop_table("metrics_snapshots", if_exists=True)
    op.drop_table("audit_logs", if_exists=True)
    op.drop_table("incident_transitions", if_exists=True)
    op.drop_table("remediation_actions", if_exists=True)
    op.drop_table("notifications", if_exists=True)
    op.drop_table("incidents", if_exists=True)
    op.drop_table("check_results", if_exists=True)
    op.drop_table("monitoring_targets", if_exists=True)
    op.drop_table("users", if_exists=True)
