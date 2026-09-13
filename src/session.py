"""Session management with refresh token rotation and family tracking."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.platform_db import PlatformRepository


def _utc_ts() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _epoch_ts(dt_str: str | None = None) -> int:
    if dt_str:
        try:
            return int(datetime.fromisoformat(dt_str.replace("Z", "+00:00")).timestamp())
        except (ValueError, TypeError):
            pass
    return int(time.time())


@dataclass
class SessionRecord:
    id: int
    user_id: int
    family_id: str
    refresh_jti: str
    expires_at: str
    created_at: str
    last_used_at: str | None
    ip_address: str
    user_agent: str
    is_active: bool
    metadata: dict[str, Any]


class SessionStore:
    """DB-backed session store with refresh token family tracking.

    Each refresh token belongs to a *family*.  When a token is rotated the
    old JWT is revoked and a new one issued within the same family.  If an
    *already-revoked* refresh token is ever presented we consider it a theft
    indicator (malicious actor copied the token) and revoke the **entire
    family** — invalidating all sessions that share that family.
    """

    def __init__(self, repo: PlatformRepository) -> None:
        self._repo = repo
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        with self._repo._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    family_id TEXT NOT NULL,
                    refresh_jti TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    ip_address TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_family_id ON sessions(family_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_refresh_jti ON sessions(refresh_jti);

                CREATE TABLE IF NOT EXISTS token_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    jti TEXT NOT NULL,
                    family_id TEXT NOT NULL,
                    session_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_token_audit_jti ON token_audit(jti);
                CREATE INDEX IF NOT EXISTS idx_token_audit_family_id ON token_audit(family_id);
            """)

    def _p(self) -> str:
        return self._repo.placeholder

    def _row_to_session(self, row: dict[str, Any]) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            user_id=row["user_id"],
            family_id=row["family_id"],
            refresh_jti=row["refresh_jti"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            last_used_at=row.get("last_used_at"),
            ip_address=row.get("ip_address", ""),
            user_agent=row.get("user_agent", ""),
            is_active=bool(row.get("is_active", 1)),
            metadata=json.loads(row.get("metadata", "{}")),
        )

    # ------------------------------------------------------------------
    # Create / Rotate
    # ------------------------------------------------------------------

    def _audit(self, jti: str, family_id: str, session_id: int, action: str) -> None:
        p = self._p()
        self._repo._execute(
            f"INSERT INTO token_audit (jti, family_id, session_id, action, created_at) VALUES ({p},{p},{p},{p},{p})",
            (jti, family_id, session_id, action, _utc_ts()),
        )

    def create_session(
        self,
        user_id: int,
        refresh_jti: str,
        expires_at: str,
        ip_address: str = "",
        user_agent: str = "",
        metadata: dict | None = None,
    ) -> SessionRecord:
        family_id = secrets.token_hex(16)
        p = self._p()
        now = _utc_ts()
        new_id = self._repo._execute(
            f"""INSERT INTO sessions
                (user_id, family_id, refresh_jti, expires_at, created_at,
                 last_used_at, ip_address, user_agent, is_active, metadata)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
            """,
            (
                user_id,
                family_id,
                refresh_jti,
                expires_at,
                now,
                now,
                ip_address,
                user_agent,
                1,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        rows = (
            self._repo._fetch_all(
                f"SELECT * FROM sessions WHERE id = {p}",
                (new_id,),
            )
            if new_id
            else self._repo._fetch_all(
                f"SELECT * FROM sessions WHERE refresh_jti = {p}",
                (refresh_jti,),
            )
        )
        if not rows:
            raise RuntimeError("Failed to create session")
        session = self._row_to_session(rows[0])
        self._audit(refresh_jti, family_id, session.id, "created")
        return session

    def rotate_refresh_token(
        self,
        old_jti: str,
        new_jti: str,
        new_expires_at: str,
    ) -> SessionRecord | None:
        """Rotate a refresh token within its family.

        Returns the updated session, or *None* if the old JTI is not found
        (or the session is inactive).  Callers **must** also revoke *old_jti*
        in the token blacklist after a successful rotation.
        """
        p = self._p()
        rows = self._repo._fetch_all(
            f"SELECT * FROM sessions WHERE refresh_jti = {p}",
            (old_jti,),
        )
        if not rows:
            return None
        session = self._row_to_session(rows[0])
        if not session.is_active:
            return None

        now = _utc_ts()
        self._repo._execute(
            f"""UPDATE sessions
                SET refresh_jti = {p}, expires_at = {p}, last_used_at = {p}
                WHERE id = {p} AND refresh_jti = {p}
            """,
            (new_jti, new_expires_at, now, session.id, old_jti),
        )
        self._audit(old_jti, session.family_id, session.id, "rotated")
        self._audit(new_jti, session.family_id, session.id, "issued")
        updated = self._repo._fetch_all(
            f"SELECT * FROM sessions WHERE id = {p}",
            (session.id,),
        )
        return self._row_to_session(updated[0]) if updated else None

    def detect_token_theft(self, old_jti: str) -> list[SessionRecord]:
        """Called when a *revoked* refresh token is presented.

        Finds the family_id from the token_audit trail (since the session's
        refresh_jti may have been rotated), then deactivates all sessions
        sharing that family.  Returns the list of deactivated sessions.
        """
        p = self._p()
        # Look up family_id from audit trail first
        audit_rows = self._repo._fetch_all(
            f"SELECT family_id FROM token_audit WHERE jti = {p}",
            (old_jti,),
        )
        family_id: str | None = None
        for row in audit_rows:
            family_id = row["family_id"]
            break

        # Fallback: check sessions table directly
        if family_id is None:
            session_rows = self._repo._fetch_all(
                f"SELECT family_id FROM sessions WHERE refresh_jti = {p}",
                (old_jti,),
            )
            if session_rows:
                family_id = session_rows[0]["family_id"]

        if family_id is None:
            return []

        self._repo._execute(
            f"UPDATE sessions SET is_active = 0 WHERE family_id = {p}",
            (family_id,),
        )
        stolen = self._repo._fetch_all(
            f"SELECT * FROM sessions WHERE family_id = {p}",
            (family_id,),
        )
        return [self._row_to_session(r) for r in stolen]

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_session_by_refresh_jti(self, jti: str) -> SessionRecord | None:
        p = self._p()
        rows = self._repo._fetch_all(
            f"SELECT * FROM sessions WHERE refresh_jti = {p}",
            (jti,),
        )
        return self._row_to_session(rows[0]) if rows else None

    def list_sessions_for_user(
        self,
        user_id: int,
        active_only: bool = True,
    ) -> list[SessionRecord]:
        p = self._p()
        if active_only:
            rows = self._repo._fetch_all(
                f"SELECT * FROM sessions WHERE user_id = {p} AND is_active = 1 ORDER BY last_used_at DESC",
                (user_id,),
            )
        else:
            rows = self._repo._fetch_all(
                f"SELECT * FROM sessions WHERE user_id = {p} ORDER BY last_used_at DESC",
                (user_id,),
            )
        return [self._row_to_session(r) for r in rows]

    # ------------------------------------------------------------------
    # Revocation
    # ------------------------------------------------------------------

    def revoke_session(self, session_id: int) -> bool:
        p = self._p()
        self._repo._execute(
            f"UPDATE sessions SET is_active = 0 WHERE id = {p}",
            (session_id,),
        )
        return True

    def revoke_all_user_sessions(self, user_id: int) -> int:
        p = self._p()
        self._repo._execute(
            f"UPDATE sessions SET is_active = 0 WHERE user_id = {p}",
            (user_id,),
        )
        rows = self._repo._fetch_all(
            f"SELECT COUNT(*) AS cnt FROM sessions WHERE user_id = {p} AND is_active = 0",
            (user_id,),
        )
        return rows[0]["cnt"] if rows else 0

    def revoke_session_by_refresh_jti(self, jti: str) -> bool:
        p = self._p()
        self._repo._execute(
            f"UPDATE sessions SET is_active = 0 WHERE refresh_jti = {p}",
            (jti,),
        )
        return True

    def cleanup_expired(self) -> int:
        p = self._p()
        now = _utc_ts()
        self._repo._execute(
            f"DELETE FROM sessions WHERE expires_at < {p}",
            (now,),
        )
        rows = self._repo._fetch_all("SELECT changes() AS cnt")
        return rows[0]["cnt"] if rows else 0
