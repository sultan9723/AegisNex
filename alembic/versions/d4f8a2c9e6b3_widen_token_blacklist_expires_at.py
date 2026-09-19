"""widen_token_blacklist_expires_at

Revision ID: d4f8a2c9e6b3
Revises: b81d4a7c2f11
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f8a2c9e6b3"
down_revision: Union[str, None] = "b81d4a7c2f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dialect() -> str:
    return op.get_bind().dialect.name


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Widen token_blacklist.expires_at to BIGINT on PostgreSQL.

    src.auth.TokenBlacklist.revoke_all_for_user stores 9999999999 (a
    "practically permanent" epoch sentinel) in expires_at when a user's
    tokens are revoked wholesale. That value overflows a 32-bit PostgreSQL
    INTEGER (max 2147483647), which is what the enterprise_auth_hardening
    migration originally created this column as. SQLite already stores it
    correctly regardless of declared width, so this is a no-op there.
    """
    if not _table_exists("token_blacklist"):
        return
    if _dialect() == "postgresql":
        op.execute("ALTER TABLE token_blacklist ALTER COLUMN expires_at TYPE BIGINT")


def downgrade() -> None:
    if _dialect() == "postgresql" and _table_exists("token_blacklist"):
        op.execute("ALTER TABLE token_blacklist ALTER COLUMN expires_at TYPE INTEGER")
