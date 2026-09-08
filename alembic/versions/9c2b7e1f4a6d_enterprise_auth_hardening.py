"""enterprise_auth_hardening

Revision ID: 9c2b7e1f4a6d
Revises: 369f8483bf6d
Create Date: 2026-07-29 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c2b7e1f4a6d"
down_revision: Union[str, None] = "369f8483bf6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dialect() -> str:
    return op.get_bind().dialect.name


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _column_exists(table_name, column.name):
        return
    if _dialect() == "postgresql":
        nullable = "" if column.nullable else " NOT NULL"
        default = ""
        if column.server_default is not None:
            default_arg = column.server_default.arg
            default = f" DEFAULT {default_arg}" if isinstance(default_arg, str) else ""
        sql_type = column.type.compile(dialect=op.get_bind().dialect)
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column.name} {sql_type}{nullable}{default}")
    else:
        op.add_column(table_name, column)


def upgrade() -> None:
    """Add enterprise auth, tenant membership, and scoped API-key schema."""
    text_type = sa.Text()
    int_type = sa.Integer()

    if not _table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.Text(), nullable=False, unique=True),
            sa.Column("hashed_password", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_superuser", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_verified", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("role", sa.Text(), nullable=False, server_default="'read_only'"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=False, server_default="''"),
            sa.Column("last_login", sa.Text(), nullable=True),
            sa.Column("mfa_enabled", sa.Integer(), nullable=False, server_default="0"),
        )
    else:
        _add_column_if_missing("users", sa.Column("role", text_type, nullable=False, server_default="'read_only'"))
        _add_column_if_missing("users", sa.Column("display_name", text_type, nullable=False, server_default="''"))
        _add_column_if_missing("users", sa.Column("last_login", text_type, nullable=True))
        _add_column_if_missing("users", sa.Column("mfa_enabled", int_type, nullable=False, server_default="0"))

    if not _table_exists("external_identities"):
        op.create_table(
            "external_identities",
            sa.Column("provider", sa.Text(), nullable=False),
            sa.Column("subject", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("email", sa.Text(), nullable=False),
            sa.Column("claims_json", sa.Text(), nullable=False, server_default="'{}'"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("last_login", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("provider", "subject"),
        )
        op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"])
        op.create_index("ix_external_identities_email", "external_identities", ["email"])

    if not _table_exists("token_blacklist"):
        op.create_table(
            "token_blacklist",
            sa.Column("jti", sa.Text(), primary_key=True),
            sa.Column("expires_at", sa.Integer(), nullable=False),
            sa.Column("revoked_at", sa.Text(), nullable=False),
        )

    if not _table_exists("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.Text(), nullable=False, unique=True),
            sa.Column("key_hash", sa.Text(), nullable=False),
            sa.Column("key_prefix", sa.Text(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False, server_default="'read_only'"),
            sa.Column("scopes", sa.Text(), nullable=False, server_default="'[\"*\"]'"),
            sa.Column("org_id", sa.Integer(), nullable=True),
            sa.Column("expires_at", sa.Text(), nullable=True),
            sa.Column("revoked_at", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("last_used_at", sa.Text(), nullable=True),
            sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        )
    else:
        _add_column_if_missing("api_keys", sa.Column("scopes", text_type, nullable=False, server_default="'[\"*\"]'"))
        _add_column_if_missing("api_keys", sa.Column("org_id", int_type, nullable=True))
        _add_column_if_missing("api_keys", sa.Column("expires_at", text_type, nullable=True))
        _add_column_if_missing("api_keys", sa.Column("revoked_at", text_type, nullable=True))
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=False, if_not_exists=True)
    op.create_index("ix_api_keys_org_id", "api_keys", ["org_id"], unique=False, if_not_exists=True)

    if not _table_exists("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("slug", sa.Text(), nullable=False, unique=True),
            sa.Column("domain", sa.Text(), nullable=False, server_default="''"),
            sa.Column("settings", sa.Text(), nullable=False, server_default="'{}'"),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.Text(), nullable=False),
        )
    op.create_index("ix_organizations_domain", "organizations", ["domain"], unique=False, if_not_exists=True)

    if not _table_exists("teams"):
        op.create_table(
            "teams",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("org_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default="''"),
            sa.Column("settings", sa.Text(), nullable=False, server_default="'{}'"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("org_id", "slug", name="uq_teams_org_slug"),
        )

    if not _table_exists("projects"):
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("org_id", sa.Integer(), nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default="''"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("org_id", "team_id", "slug", name="uq_projects_org_team_slug"),
        )

    if not _table_exists("tenant_users"):
        op.create_table(
            "tenant_users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("org_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False, server_default="'read_only'"),
            sa.Column("permissions", sa.Text(), nullable=False, server_default="'{}'"),
            sa.UniqueConstraint("user_id", "org_id", name="uq_tenant_users_user_org"),
        )
    op.create_index("ix_tenant_users_user_id", "tenant_users", ["user_id"], unique=False, if_not_exists=True)
    op.create_index("ix_tenant_users_org_id", "tenant_users", ["org_id"], unique=False, if_not_exists=True)

    if not _table_exists("tenant_user_teams"):
        op.create_table(
            "tenant_user_teams",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("org_id", sa.Integer(), nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("user_id", "org_id", "team_id"),
        )

    if _table_exists("audit_logs"):
        _add_column_if_missing("audit_logs", sa.Column("before_state", text_type, nullable=True))
        _add_column_if_missing("audit_logs", sa.Column("after_state", text_type, nullable=True))
        _add_column_if_missing("audit_logs", sa.Column("execution_id", text_type, nullable=True))


def downgrade() -> None:
    """Drop enterprise auth additions.

    Column removals are intentionally conservative for SQLite compatibility.
    """
    op.drop_table("tenant_user_teams")
    op.drop_index("ix_tenant_users_org_id", table_name="tenant_users", if_exists=True)
    op.drop_index("ix_tenant_users_user_id", table_name="tenant_users", if_exists=True)
    op.drop_table("tenant_users")
    op.drop_table("projects")
    op.drop_table("teams")
    op.drop_index("ix_organizations_domain", table_name="organizations", if_exists=True)
    op.drop_table("organizations")
    op.drop_index("ix_external_identities_email", table_name="external_identities", if_exists=True)
    op.drop_index("ix_external_identities_user_id", table_name="external_identities", if_exists=True)
    op.drop_table("external_identities")
    op.drop_table("token_blacklist")
