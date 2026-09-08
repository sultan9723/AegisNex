"""ai_workforce_tables

Revision ID: b81d4a7c2f11
Revises: 9c2b7e1f4a6d
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b81d4a7c2f11"
down_revision: Union[str, None] = "9c2b7e1f4a6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _columns(name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(name):
        return set()
    return {column["name"] for column in inspector.get_columns(name)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    int_pk = sa.Integer()

    if not _table_exists("workforce_agents"):
        op.create_table(
            "workforce_agents",
            sa.Column("id", int_pk, primary_key=True, autoincrement=True),
            sa.Column("agent_id", sa.Text(), nullable=False, unique=True),
            sa.Column("name", sa.Text(), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("agent_type", sa.Text(), nullable=False, server_default="general"),
            sa.Column("provider", sa.Text(), nullable=False, server_default="openai"),
            sa.Column("model", sa.Text(), nullable=False, server_default="gpt-4o-mini"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("lifecycle_status", sa.Text(), nullable=False, server_default="draft"),
            sa.Column("trust_score", sa.Float(), nullable=False, server_default="50.0"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("daily_budget", sa.Float(), nullable=False, server_default="25.0"),
            sa.Column("monthly_budget", sa.Float(), nullable=False, server_default="750.0"),
            sa.Column("total_cost", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("success_rate", sa.Float(), nullable=False, server_default="100.0"),
            sa.Column("average_latency_ms", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("total_executions", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("health_status", sa.Text(), nullable=False, server_default="unknown"),
            sa.Column("health_last_checked", sa.Text(), nullable=True),
            sa.Column("tools", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("permissions", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("owner", sa.Text(), nullable=False, server_default=""),
            sa.Column("team", sa.Text(), nullable=False, server_default=""),
            sa.Column("org_id", sa.Integer(), nullable=True),
            sa.Column("team_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.Column("last_active_at", sa.Text(), nullable=True),
        )
    else:
        _add_column_if_missing("workforce_agents", sa.Column("org_id", sa.Integer(), nullable=True))
        _add_column_if_missing("workforce_agents", sa.Column("team_id", sa.Integer(), nullable=True))

    op.create_index("ix_workforce_agents_org_id", "workforce_agents", ["org_id"], unique=False, if_not_exists=True)
    op.create_index("ix_workforce_agents_lifecycle", "workforce_agents", ["lifecycle_status"], unique=False, if_not_exists=True)

    if not _table_exists("workforce_agent_versions"):
        op.create_table(
            "workforce_agent_versions",
            sa.Column("id", int_pk, primary_key=True, autoincrement=True),
            sa.Column("agent_id", sa.Text(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("config_snapshot", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("prompt_ids", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("change_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("agent_id", "version", name="uq_workforce_agent_versions_agent_version"),
        )

    if not _table_exists("workforce_prompt_versions"):
        op.create_table(
            "workforce_prompt_versions",
            sa.Column("id", int_pk, primary_key=True, autoincrement=True),
            sa.Column("prompt_id", sa.Text(), nullable=False, unique=True),
            sa.Column("agent_id", sa.Text(), nullable=False, server_default=""),
            sa.Column("name", sa.Text(), nullable=False, server_default=""),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("role", sa.Text(), nullable=False, server_default="system"),
            sa.Column("variables", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("hash", sa.Text(), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.Text(), nullable=False),
        )

    if not _table_exists("workforce_tool_permissions"):
        op.create_table(
            "workforce_tool_permissions",
            sa.Column("id", int_pk, primary_key=True, autoincrement=True),
            sa.Column("agent_id", sa.Text(), nullable=False),
            sa.Column("tool_name", sa.Text(), nullable=False),
            sa.Column("allowed", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("config", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("agent_id", "tool_name", name="uq_workforce_tool_permissions_agent_tool"),
        )

    if not _table_exists("workforce_knowledge_assignments"):
        op.create_table(
            "workforce_knowledge_assignments",
            sa.Column("id", int_pk, primary_key=True, autoincrement=True),
            sa.Column("agent_id", sa.Text(), nullable=False),
            sa.Column("knowledge_source_id", sa.Text(), nullable=False),
            sa.Column("knowledge_source_type", sa.Text(), nullable=False, server_default="collection"),
            sa.Column("access_level", sa.Text(), nullable=False, server_default="read_write"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("agent_id", "knowledge_source_id", name="uq_workforce_knowledge_agent_source"),
        )

    if not _table_exists("workforce_executions"):
        op.create_table(
            "workforce_executions",
            sa.Column("id", int_pk, primary_key=True, autoincrement=True),
            sa.Column("execution_id", sa.Text(), nullable=False, unique=True),
            sa.Column("agent_id", sa.Text(), nullable=False),
            sa.Column("task", sa.Text(), nullable=False, server_default=""),
            sa.Column("response", sa.Text(), nullable=False, server_default=""),
            sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("cost", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("tools_used", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("status", sa.Text(), nullable=False, server_default="success"),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("prompt_version_id", sa.Text(), nullable=False, server_default=""),
            sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.Text(), nullable=False),
        )

    if not _table_exists("workforce_health_log"):
        op.create_table(
            "workforce_health_log",
            sa.Column("id", int_pk, primary_key=True, autoincrement=True),
            sa.Column("agent_id", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="healthy"),
            sa.Column("check_type", sa.Text(), nullable=False, server_default="heartbeat"),
            sa.Column("metric_value", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("details", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("checked_at", sa.Text(), nullable=False),
        )

    for table in (
        "workforce_agent_versions",
        "workforce_prompt_versions",
        "workforce_tool_permissions",
        "workforce_knowledge_assignments",
        "workforce_executions",
        "workforce_health_log",
    ):
        op.create_index(f"ix_{table}_agent_id", table, ["agent_id"], unique=False, if_not_exists=True)


def downgrade() -> None:
    for table in (
        "workforce_health_log",
        "workforce_executions",
        "workforce_knowledge_assignments",
        "workforce_tool_permissions",
        "workforce_prompt_versions",
        "workforce_agent_versions",
    ):
        op.drop_index(f"ix_{table}_agent_id", table_name=table, if_exists=True)
        op.drop_table(table)
    op.drop_index("ix_workforce_agents_lifecycle", table_name="workforce_agents", if_exists=True)
    op.drop_index("ix_workforce_agents_org_id", table_name="workforce_agents", if_exists=True)
    op.drop_table("workforce_agents")
