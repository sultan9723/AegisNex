"""Dashboard authentication helpers with PyJWT, RBAC, and token blacklisting.

UserStore and TokenBlacklist default to a local SQLite file (convenient for
local development and tests) but can be backed by a shared
src.platform_db.PlatformRepository instead - pass repository=<PlatformRepository>
to route persistence through that repository's configured backend (SQLite or
PostgreSQL/Neon in production). See src.session.SessionStore for the same
pattern applied to refresh-token sessions.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

_logger = logging.getLogger(__name__)

import contextlib

import jwt as pyjwt

from src.enterprise_auth import is_production_environment
from src.session import SessionStore

try:
    import hashlib as _hashlib
    import secrets as _secrets

    _HAVE_HASH = True
except ImportError:
    _HAVE_HASH = False


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (full_key, key_hash, key_prefix) where full_key is the key to give
        to the user, key_hash is the stored hash, and key_prefix is a
        human-readable prefix for identification.
    """
    raw = _secrets.token_hex(32)
    key_prefix = raw[:8]
    full_key = f"anx_{raw}"
    key_hash = _hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_hash, key_prefix


def hash_api_key(key: str) -> str:
    return _hashlib.sha256(key.encode()).hexdigest()


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Role(enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMINISTRATOR = "administrator"
    SOC_ANALYST = "soc_analyst"
    OPERATOR = "operator"
    READ_ONLY = "read_only"
    AUDITOR = "auditor"

    def level(self) -> int:
        return {
            "super_admin": 100,
            "administrator": 80,
            "soc_analyst": 60,
            "operator": 40,
            "read_only": 20,
            "auditor": 10,
        }[self.value]

    @staticmethod
    def from_str(value: str) -> Role:
        normalized = value.strip().lower()
        mapping = {
            "admin": Role.ADMINISTRATOR,
            "administrator": Role.ADMINISTRATOR,
            "super_admin": Role.SUPER_ADMIN,
            "superadmin": Role.SUPER_ADMIN,
            "soc_analyst": Role.SOC_ANALYST,
            "soc analyst": Role.SOC_ANALYST,
            "operator": Role.OPERATOR,
            "viewer": Role.READ_ONLY,
            "read_only": Role.READ_ONLY,
            "readonly": Role.READ_ONLY,
            "auditor": Role.AUDITOR,
        }
        return mapping.get(normalized, Role.READ_ONLY)

    @staticmethod
    def valid_roles() -> list[str]:
        return [r.value for r in Role]

    @staticmethod
    def requires_level(min_role: str) -> list[str]:
        """Return all roles that meet or exceed the given minimum role level."""
        min_level = Role.from_str(min_role).level()
        return [r.value for r in Role if r.level() >= min_level]


@dataclass(frozen=True)
class User:
    id: int
    email: str
    hashed_password: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    role: str
    created_at: str
    display_name: str = ""
    last_login: str | None = None
    mfa_enabled: bool = False

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    def has_minimum_role(self, min_role: str) -> bool:
        """Check if this user's role is at least the specified level."""
        try:
            return Role.from_str(self.role).level() >= Role.from_str(min_role).level()
        except ValueError:
            return False

    @property
    def display_role(self) -> str:
        return {
            "super_admin": "Super Admin",
            "administrator": "Administrator",
            "soc_analyst": "SOC Analyst",
            "operator": "Operator",
            "read_only": "Read Only",
            "auditor": "Auditor",
        }.get(self.role, self.role.capitalize())


class AuthError(ValueError):
    """Raised when authentication input or credentials are invalid."""


class TokenBlacklist:
    """In-memory token blacklist with DB persistence for revocations.

    Backed by a local SQLite file by default, or by a shared
    PlatformRepository (SQLite or PostgreSQL/Neon) when repository= is given.
    """

    def __init__(
        self,
        database_path: str | Path = "aegisnex_users.db",
        *,
        repository: Any | None = None,
    ) -> None:
        self._repo = repository
        self._cache: set[str] = set()
        if repository is not None:
            self.database_path = None
            self._initialize_repo()
        else:
            self.database_path = Path(database_path)
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        _logger.debug("TokenBlacklist opening connection to %s", self.database_path)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        with contextlib.suppress(sqlite3.OperationalError):
            connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS token_blacklist (
                    jti TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL,
                    revoked_at TEXT NOT NULL
                )
                """
            )
        # Warm the cache from DB
        with self._connect() as connection:
            now = int(datetime.now(UTC).timestamp())
            connection.execute("DELETE FROM token_blacklist WHERE expires_at < ?", (now,))
            rows = connection.execute(
                "SELECT jti FROM token_blacklist WHERE expires_at >= ?", (now,)
            ).fetchall()
            self._cache = {str(row["jti"]) for row in rows}

    def _initialize_repo(self) -> None:
        # token_blacklist is created by PlatformRepository's own schema
        # (src/platform_db.py _schema_statements); just warm the cache.
        p = self._repo.placeholder
        now = int(datetime.now(UTC).timestamp())
        self._repo._execute(f"DELETE FROM token_blacklist WHERE expires_at < {p}", (now,))
        rows = self._repo._fetch_all(
            f"SELECT jti FROM token_blacklist WHERE expires_at >= {p}", (now,)
        )
        self._cache = {str(row["jti"]) for row in rows}

    def revoke(self, jti: str, expires_at: int) -> None:
        if self._repo is not None:
            p = self._repo.placeholder
            existing = self._repo._fetch_all(
                f"SELECT jti FROM token_blacklist WHERE jti = {p}", (jti,)
            )
            if not existing:
                with contextlib.suppress(Exception):
                    self._repo._execute(
                        f"INSERT INTO token_blacklist (jti, expires_at, revoked_at) VALUES ({p}, {p}, {p})",
                        (jti, expires_at, utc_timestamp()),
                    )
            self._cache.add(jti)
            return
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO token_blacklist (jti, expires_at, revoked_at) VALUES (?, ?, ?)",
                (jti, expires_at, utc_timestamp()),
            )
        self._cache.add(jti)

    def is_revoked(self, jti: str) -> bool:
        return jti in self._cache

    def revoke_all_for_user(self, user_id: int, auth_manager: AuthManager) -> None:
        """Revoke all tokens for a user by adding a user-level revocation marker.
        This is called when a user is deactivated."""
        key = f"user_revoke_{user_id}"
        if self._repo is not None:
            p = self._repo.placeholder
            existing = self._repo._fetch_all(
                f"SELECT jti FROM token_blacklist WHERE jti = {p}", (key,)
            )
            if existing:
                self._repo._execute(
                    f"UPDATE token_blacklist SET expires_at = {p}, revoked_at = {p} WHERE jti = {p}",
                    (9999999999, utc_timestamp(), key),
                )
            else:
                self._repo._execute(
                    f"INSERT INTO token_blacklist (jti, expires_at, revoked_at) VALUES ({p}, {p}, {p})",
                    (key, 9999999999, utc_timestamp()),
                )
            self._cache.add(key)
            return
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO token_blacklist (jti, expires_at, revoked_at) VALUES (?, ?, ?)",
                (key, 9999999999, utc_timestamp()),
            )
        self._cache.add(key)


class UserStore:
    """User repository with role support.

    Backed by a local SQLite file by default (useful for local development
    and tests), or by a shared PlatformRepository (SQLite or
    PostgreSQL/Neon) when repository= is given - the intended mode for any
    deployment where users must survive a container restart.
    """

    def __init__(
        self,
        database_path: str | Path | None = "aegisnex_users.db",
        *,
        repository: Any | None = None,
    ) -> None:
        self._repo = repository
        if repository is not None:
            self.database_path = None
            self._initialize_repo()
        else:
            self.database_path = Path(database_path or "aegisnex_users.db")
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def _initialize_repo(self) -> None:
        # users / external_identities are created by PlatformRepository's own
        # schema (src/platform_db.py _schema_statements); just make sure it
        # has run so a fresh repository can be used immediately.
        self._repo.initialize()

    def _connect(self) -> sqlite3.Connection:
        _logger.debug("UserStore opening connection to %s", self.database_path)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        with contextlib.suppress(sqlite3.OperationalError):
            connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    hashed_password TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    is_superuser INTEGER NOT NULL DEFAULT 0,
                    is_verified INTEGER NOT NULL DEFAULT 0,
                    role TEXT NOT NULL DEFAULT 'read_only',
                    created_at TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    last_login TEXT,
                    mfa_enabled INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # Add columns if migrating from old schema
            existing = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "role" not in existing:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'read_only'"
                )
            if "display_name" not in existing:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''"
                )
            if "last_login" not in existing:
                connection.execute("ALTER TABLE users ADD COLUMN last_login TEXT")
            if "mfa_enabled" not in existing:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN mfa_enabled INTEGER NOT NULL DEFAULT 0"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS external_identities (
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    claims_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    last_login TEXT,
                    PRIMARY KEY (provider, subject),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            )

    def create_user(self, email: str, password: str, role: str = "viewer") -> User:
        normalized_email = normalize_email(email)
        if not normalized_email:
            raise AuthError("Email is required.")
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters.")
        normalized_role = Role.from_str(role).value
        if self._repo is not None:
            p = self._repo.placeholder
            if self._repo._fetch_all(
                f"SELECT id FROM users WHERE email = {p}", (normalized_email,)
            ):
                raise AuthError("User already exists.")
            try:
                self._repo._execute(
                    f"""
                    INSERT INTO users (
                        email, hashed_password, is_active, is_superuser, is_verified, role, created_at
                    )
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
                    """,
                    (
                        normalized_email,
                        hash_password(password),
                        True,
                        normalized_role in ("super_admin", "administrator"),
                        False,
                        normalized_role,
                        utc_timestamp(),
                    ),
                )
            except Exception as exc:
                raise AuthError("User already exists.") from exc
            user = self.get_user_by_email(normalized_email)
            if user is None:
                raise AuthError("Failed to create user.")
            return user
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO users (
                        email,
                        hashed_password,
                        is_active,
                        is_superuser,
                        is_verified,
                        role,
                        created_at
                    )
                    VALUES (?, ?, 1, ?, 0, ?, ?)
                    """,
                    (
                        normalized_email,
                        hash_password(password),
                        1 if normalized_role in ("super_admin", "administrator") else 0,
                        normalized_role,
                        utc_timestamp(),
                    ),
                )
                user_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise AuthError("User already exists.") from exc
        user = self.get_user_by_id(user_id)
        if user is None:
            raise AuthError("Failed to create user.")
        return user

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.get_user_by_email(email)
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def get_user_by_email(self, email: str) -> User | None:
        if self._repo is not None:
            p = self._repo.placeholder
            rows = self._repo._fetch_all(
                f"SELECT * FROM users WHERE email = {p}", (normalize_email(email),)
            )
            return row_to_user(rows[0]) if rows else None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ?",
                (normalize_email(email),),
            ).fetchone()
        return row_to_user(row)

    def get_user_by_id(self, user_id: int) -> User | None:
        if self._repo is not None:
            p = self._repo.placeholder
            rows = self._repo._fetch_all(f"SELECT * FROM users WHERE id = {p}", (user_id,))
            return row_to_user(rows[0]) if rows else None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return row_to_user(row)

    def deactivate_user(self, user_id: int) -> bool:
        if self._repo is not None:
            p = self._repo.placeholder
            self._repo._execute(f"UPDATE users SET is_active = {p} WHERE id = {p}", (False, user_id))
            return self.get_user_by_id(user_id) is not None
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_active = 0 WHERE id = ?",
                (user_id,),
            )
            return cursor.rowcount > 0

    def update_password(self, user_id: int, new_password: str) -> bool:
        if len(new_password) < 8:
            raise AuthError("Password must be at least 8 characters.")
        if self._repo is not None:
            p = self._repo.placeholder
            self._repo._execute(
                f"UPDATE users SET hashed_password = {p} WHERE id = {p}",
                (hash_password(new_password), user_id),
            )
            return self.get_user_by_id(user_id) is not None
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET hashed_password = ? WHERE id = ?",
                (hash_password(new_password), user_id),
            )
            return cursor.rowcount > 0

    def update_last_login(self, user_id: int) -> None:
        if self._repo is not None:
            p = self._repo.placeholder
            self._repo._execute(
                f"UPDATE users SET last_login = {p} WHERE id = {p}", (utc_timestamp(), user_id)
            )
            return
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (utc_timestamp(), user_id),
            )

    def update_role(self, user_id: int, role: str) -> bool:
        """Set a user's role directly (admin role-management, invite acceptance)."""
        normalized_role = Role.from_str(role).value
        if self._repo is not None:
            p = self._repo.placeholder
            self._repo._execute(
                f"UPDATE users SET role = {p} WHERE id = {p}", (normalized_role, user_id)
            )
            return self.get_user_by_id(user_id) is not None
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET role = ? WHERE id = ?",
                (normalized_role, user_id),
            )
            return cursor.rowcount > 0

    def update_display_name(self, user_id: int, display_name: str) -> bool:
        if self._repo is not None:
            p = self._repo.placeholder
            self._repo._execute(
                f"UPDATE users SET display_name = {p} WHERE id = {p}",
                (display_name.strip()[:64], user_id),
            )
            return self.get_user_by_id(user_id) is not None
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (display_name.strip()[:64], user_id),
            )
            return cursor.rowcount > 0

    def upsert_external_user(
        self,
        *,
        provider: str,
        subject: str,
        email: str,
        display_name: str = "",
        role: str = "read_only",
        claims: dict[str, Any] | None = None,
    ) -> User:
        normalized_email = normalize_email(email)
        normalized_role = Role.from_str(role).value
        now = utc_timestamp()
        claims_json = json.dumps(claims or {}, sort_keys=True)
        if self._repo is not None:
            user = self._upsert_external_user_repo(
                provider=provider,
                subject=subject,
                normalized_email=normalized_email,
                display_name=display_name,
                normalized_role=normalized_role,
                claims_json=claims_json,
                now=now,
            )
            if user is None:
                raise AuthError("Failed to provision SSO user.")
            return user
        with self._connect() as connection:
            identity = connection.execute(
                "SELECT user_id FROM external_identities WHERE provider = ? AND subject = ?",
                (provider, subject),
            ).fetchone()
            if identity is not None:
                user_id = int(identity["user_id"])
                connection.execute(
                    """
                    UPDATE users
                    SET email = ?, display_name = ?, is_verified = 1, role = ?, is_superuser = ?, last_login = ?
                    WHERE id = ?
                    """,
                    (
                        normalized_email,
                        display_name.strip()[:64],
                        normalized_role,
                        1 if normalized_role in ("super_admin", "administrator") else 0,
                        now,
                        user_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE external_identities
                    SET email = ?, claims_json = ?, last_login = ?
                    WHERE provider = ? AND subject = ?
                    """,
                    (normalized_email, claims_json, now, provider, subject),
                )
            else:
                existing = connection.execute(
                    "SELECT * FROM users WHERE email = ?",
                    (normalized_email,),
                ).fetchone()
                if existing is not None:
                    user_id = int(existing["id"])
                    connection.execute(
                        """
                        UPDATE users
                        SET display_name = CASE WHEN display_name = '' THEN ? ELSE display_name END,
                            role = ?,
                            is_superuser = ?,
                            is_verified = 1,
                            last_login = ?
                        WHERE id = ?
                        """,
                        (
                            display_name.strip()[:64],
                            normalized_role,
                            1 if normalized_role in ("super_admin", "administrator") else 0,
                            now,
                            user_id,
                        ),
                    )
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO users (
                            email,
                            hashed_password,
                            is_active,
                            is_superuser,
                            is_verified,
                            role,
                            display_name,
                            created_at,
                            last_login
                        )
                        VALUES (?, ?, 1, ?, 1, ?, ?, ?, ?)
                        """,
                        (
                            normalized_email,
                            hash_password(secrets.token_urlsafe(48)),
                            1 if normalized_role in ("super_admin", "administrator") else 0,
                            normalized_role,
                            display_name.strip()[:64],
                            now,
                            now,
                        ),
                    )
                    user_id = int(cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO external_identities (
                        provider, subject, user_id, email, claims_json, created_at, last_login
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (provider, subject, user_id, normalized_email, claims_json, now, now),
                )
        user = self.get_user_by_email(normalized_email)
        if user is None:
            raise AuthError("Failed to provision SSO user.")
        return user

    def _upsert_external_user_repo(
        self,
        *,
        provider: str,
        subject: str,
        normalized_email: str,
        display_name: str,
        normalized_role: str,
        claims_json: str,
        now: str,
    ) -> User | None:
        """PlatformRepository-backed twin of upsert_external_user's sqlite body.

        Each step commits independently (no single shared transaction) since
        PlatformRepository._execute/_fetch_all each own their connection -
        acceptable here as SSO provisioning races are rare and self-healing
        on the next login.
        """
        p = self._repo.placeholder
        is_superuser = normalized_role in ("super_admin", "administrator")
        identity_rows = self._repo._fetch_all(
            f"SELECT user_id FROM external_identities WHERE provider = {p} AND subject = {p}",
            (provider, subject),
        )
        if identity_rows:
            user_id = int(identity_rows[0]["user_id"])
            self._repo._execute(
                f"""
                UPDATE users
                SET email = {p}, display_name = {p}, is_verified = {p}, role = {p}, is_superuser = {p}, last_login = {p}
                WHERE id = {p}
                """,
                (normalized_email, display_name.strip()[:64], True, normalized_role, is_superuser, now, user_id),
            )
            self._repo._execute(
                f"""
                UPDATE external_identities
                SET email = {p}, claims_json = {p}, last_login = {p}
                WHERE provider = {p} AND subject = {p}
                """,
                (normalized_email, claims_json, now, provider, subject),
            )
            return self.get_user_by_email(normalized_email)

        existing_rows = self._repo._fetch_all(
            f"SELECT id FROM users WHERE email = {p}", (normalized_email,)
        )
        if existing_rows:
            user_id = int(existing_rows[0]["id"])
            self._repo._execute(
                f"""
                UPDATE users
                SET display_name = CASE WHEN display_name = '' THEN {p} ELSE display_name END,
                    role = {p},
                    is_superuser = {p},
                    is_verified = {p},
                    last_login = {p}
                WHERE id = {p}
                """,
                (display_name.strip()[:64], normalized_role, is_superuser, True, now, user_id),
            )
        else:
            self._repo._execute(
                f"""
                INSERT INTO users (
                    email, hashed_password, is_active, is_superuser, is_verified, role, display_name, created_at, last_login
                )
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                """,
                (
                    normalized_email,
                    hash_password(secrets.token_urlsafe(48)),
                    True,
                    is_superuser,
                    True,
                    normalized_role,
                    display_name.strip()[:64],
                    now,
                    now,
                ),
            )
            user_rows = self._repo._fetch_all(
                f"SELECT id FROM users WHERE email = {p}", (normalized_email,)
            )
            user_id = int(user_rows[0]["id"])
        self._repo._execute(
            f"""
            INSERT INTO external_identities (
                provider, subject, user_id, email, claims_json, created_at, last_login
            )
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
            """,
            (provider, subject, user_id, normalized_email, claims_json, now, now),
        )
        return self.get_user_by_email(normalized_email)

    def set_verified(self, user_id: int, verified: bool = True) -> bool:
        if self._repo is not None:
            p = self._repo.placeholder
            self._repo._execute(
                f"UPDATE users SET is_verified = {p} WHERE id = {p}", (verified, user_id)
            )
            return self.get_user_by_id(user_id) is not None
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_verified = ? WHERE id = ?",
                (1 if verified else 0, user_id),
            )
            return cursor.rowcount > 0

    def seed_default_admin(self, password: str | None = None) -> None:
        env_password = password or os.getenv("AEGISNEX_BOOTSTRAP_ADMIN_PASSWORD", "")
        if not env_password:
            raise AuthError(
                "AEGISNEX_BOOTSTRAP_ADMIN_PASSWORD environment variable is required to seed the default admin."
            )
        admin = self.get_user_by_email("admin")
        if admin is None:
            if self._repo is not None:
                p = self._repo.placeholder
                try:
                    self._repo._execute(
                        f"""
                        INSERT INTO users (email, hashed_password, is_active, is_superuser, is_verified, role, created_at)
                        VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
                        """,
                        ("admin", hash_password(env_password), True, True, True, "administrator", utc_timestamp()),
                    )
                except Exception:
                    # Another instance/worker seeded it concurrently; nothing
                    # left to do here.
                    pass
                return
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users (email, hashed_password, is_active, is_superuser, is_verified, role, created_at)
                    VALUES (?, ?, 1, 1, 1, 'administrator', ?)
                    """,
                    ("admin", hash_password(env_password), utc_timestamp()),
                )
            return
        # Upgrade the legacy known-insecure bootstrap password if it is still in use.
        # A real, operator-set password is never overwritten.
        if any(
            verify_password(legacy, admin.hashed_password)
            for legacy in ("admin", "AegisNex!Demo2026")
        ):
            self.update_password(admin.id, env_password)

    def seed_demo_user(self, username: str, password: str) -> None:
        """Create (or resync) a restricted, non-admin demo account.

        Unlike seed_default_admin, this never grants is_superuser or an
        elevated role: the demo identity is always read_only, regardless of
        how AEGISNEX_DEMO_USERNAME is configured, so demo login can never
        hand out admin, secrets, Docker, or mutation access.
        """
        if not password:
            raise AuthError(
                "AEGISNEX_DEMO_PASSWORD environment variable is required to seed the demo user."
            )
        existing = self.get_user_by_email(username)
        if existing is None:
            if self._repo is not None:
                p = self._repo.placeholder
                try:
                    self._repo._execute(
                        f"""
                        INSERT INTO users (email, hashed_password, is_active, is_superuser, is_verified, role, created_at)
                        VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
                        """,
                        (username, hash_password(password), True, False, True, "read_only", utc_timestamp()),
                    )
                    return
                except Exception:
                    # Two concurrent first-time demo-login requests can both
                    # see "no existing user" and both attempt this insert;
                    # the loser of that race isn't a real failure, just a
                    # concurrent winner - reconcile against what's there
                    # instead of raising.
                    existing = self.get_user_by_email(username)
                    if existing is None:
                        raise
            else:
                try:
                    with self._connect() as connection:
                        connection.execute(
                            """
                            INSERT INTO users (email, hashed_password, is_active, is_superuser, is_verified, role, created_at)
                            VALUES (?, ?, 1, 0, 1, 'read_only', ?)
                            """,
                            (username, hash_password(password), utc_timestamp()),
                        )
                    return
                except sqlite3.IntegrityError:
                    existing = self.get_user_by_email(username)
                    if existing is None:
                        raise
        # Internal automation account, not a real user's credential: keep it
        # in sync with the configured secret so rotating AEGISNEX_DEMO_PASSWORD
        # doesn't permanently lock demo login out.
        if not verify_password(password, existing.hashed_password):
            self.update_password(existing.id, password)


class AuthManager:
    def __init__(
        self,
        user_store: UserStore | None = None,
        jwt_secret: str | None = None,
        token_ttl_seconds: int = 60 * 30,  # 30 minutes default
        refresh_token_ttl_seconds: int = 60 * 60 * 24 * 7,  # 7 days
        session_store: SessionStore | None = None,
        repository: Any | None = None,
    ) -> None:
        """
        repository: an optional src.platform_db.PlatformRepository. When
        given (and user_store is not explicitly passed), user/token
        persistence is routed through it instead of a standalone local
        SQLite file - this is how production deployments get PostgreSQL/
        Neon-backed authentication automatically, since dashboard.py already
        constructs one PlatformRepository per process and can hand it here.
        """
        self.user_store = user_store or UserStore(repository=repository)
        # JWT secret MUST come from environment variable - no hardcoded fallback
        env_secret = os.getenv("AEGISNEX_JWT_SECRET")
        if jwt_secret:
            self.jwt_secret = jwt_secret
        elif env_secret:
            self.jwt_secret = env_secret
        else:
            raise RuntimeError(
                "AEGISNEX_JWT_SECRET environment variable is required. "
                "Set it to a random 256-bit key (e.g., openssl rand -hex 32)."
            )
        if is_production_environment() and len(self.jwt_secret.encode("utf-8")) < 32:
            raise RuntimeError(
                "AEGISNEX_JWT_SECRET must be at least 32 bytes in production. "
                "Generate one with: openssl rand -hex 32."
            )
        self.token_ttl_seconds = int(
            os.getenv("AEGISNEX_TOKEN_TTL_SECONDS", str(token_ttl_seconds))
        )
        self.refresh_token_ttl_seconds = int(
            os.getenv("AEGISNEX_REFRESH_TOKEN_TTL_SECONDS", str(refresh_token_ttl_seconds))
        )
        # Follow the user_store's own backend (sqlite file vs. shared
        # repository) so tokens and users are always revoked/looked-up
        # against the same store, regardless of how this AuthManager was
        # constructed.
        user_store_repo = getattr(self.user_store, "_repo", None)
        if user_store_repo is not None:
            self.blacklist = TokenBlacklist(repository=user_store_repo)
        else:
            self.blacklist = TokenBlacklist(self.user_store.database_path)
        self.session_store = session_store

    def create_access_token(self, user: User) -> str:
        now = datetime.now(UTC)
        jti = secrets.token_hex(16)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "is_superuser": user.is_superuser,
            "is_verified": user.is_verified,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.token_ttl_seconds)).timestamp()),
            "type": "access",
        }
        return pyjwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def create_refresh_token(self, user: User) -> str:
        now = datetime.now(UTC)
        jti = secrets.token_hex(16)
        payload = {
            "sub": str(user.id),
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.refresh_token_ttl_seconds)).timestamp()),
            "type": "refresh",
        }
        return pyjwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def get_user_from_token(self, token: str | None) -> User | None:
        if not token:
            return None
        try:
            payload = pyjwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["sub", "jti", "exp"]},
            )
        except pyjwt.PyJWTError:
            return None

        # Check token type - only access tokens can authenticate
        if payload.get("type") not in (None, "access"):
            return None

        jti = payload.get("jti", "")
        if self.blacklist.is_revoked(jti):
            return None

        # Check user-level revocation
        try:
            user_id = int(payload.get("sub", ""))
        except ValueError:
            return None

        if self.blacklist.is_revoked(f"user_revoke_{user_id}"):
            return None

        user = self.user_store.get_user_by_id(user_id)
        if user is None or not user.is_active:
            return None

        return user

    def register(self, email: str, password: str) -> tuple[User, str, str]:
        """Register a new user. Returns (user, access_token, refresh_token)."""
        user = self.user_store.create_user(email, password)
        return user, self.create_access_token(user), self.create_refresh_token(user)

    def login(self, email: str, password: str) -> tuple[User, str, str] | None:
        """Authenticate and return (user, access_token, refresh_token)."""
        user = self.user_store.authenticate(email, password)
        if user is None:
            return None
        self.user_store.update_last_login(user.id)
        refreshed = self.user_store.get_user_by_id(user.id)
        if refreshed is not None:
            user = refreshed
        return user, self.create_access_token(user), self.create_refresh_token(user)

    def external_login(
        self,
        *,
        provider: str,
        subject: str,
        email: str,
        display_name: str = "",
        role: str = "read_only",
        claims: dict[str, Any] | None = None,
    ) -> tuple[User, str, str]:
        """Provision or update an SSO user and return app session tokens."""
        user = self.user_store.upsert_external_user(
            provider=provider,
            subject=subject,
            email=email,
            display_name=display_name,
            role=role,
            claims=claims,
        )
        return user, self.create_access_token(user), self.create_refresh_token(user)

    def logout(self, token: str | None) -> bool:
        """Revoke the given token and deactivate all user sessions."""
        if not token:
            return False
        try:
            payload = pyjwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            jti = payload.get("jti", "")
            exp = payload.get("exp", 0)
            self.blacklist.revoke(jti, exp)

            # Revoke all sessions for this user on logout
            if self.session_store is not None:
                try:
                    user_id = int(payload.get("sub", "0"))
                    if user_id > 0:
                        self.session_store.revoke_all_user_sessions(user_id)
                except (ValueError, TypeError):
                    pass

            return True
        except pyjwt.PyJWTError:
            return False

    def refresh_access_token(self, refresh_token: str) -> tuple[str, str] | None:
        """Exchange a valid refresh token for a new access and refresh token pair.

        If a SessionStore is configured this method implements refresh token
        rotation with family tracking:
        - The old refresh JTI is revoked.
        - A new refresh JTI is issued within the same session family.
        - If the old JTI was *already* revoked (theft detection), the entire
          family is deactivated.
        """
        try:
            payload = pyjwt.decode(
                refresh_token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["sub", "jti", "exp"]},
            )
        except pyjwt.PyJWTError:
            return None

        if payload.get("type") != "refresh":
            return None

        jti = payload.get("jti", "")
        already_revoked = self.blacklist.is_revoked(jti)

        # Theft detection: if the token was already revoked, deactivate family
        if already_revoked and self.session_store is not None:
            self.session_store.detect_token_theft(jti)
            return None

        try:
            user_id = int(payload.get("sub", ""))
        except ValueError:
            return None

        user = self.user_store.get_user_by_id(user_id)
        if user is None or not user.is_active:
            return None

        # Verify session is still active (if session store is available)
        if self.session_store is not None:
            session = self.session_store.get_session_by_refresh_jti(jti)
            if session is None or not session.is_active:
                return None

        # Revoke the old refresh token
        exp = payload.get("exp", 0)
        self.blacklist.revoke(jti, exp)

        # Issue new tokens
        new_access = self.create_access_token(user)
        new_refresh = self.create_refresh_token(user)

        # Rotate session (update refresh JTI)
        if self.session_store is not None:
            new_payload = pyjwt.decode(
                new_refresh,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            new_jti = new_payload.get("jti", "")
            new_exp = new_payload.get("exp", 0)
            new_expires_at = (
                datetime.fromtimestamp(new_exp, tz=UTC).isoformat().replace("+00:00", "Z")
            )
            self.session_store.rotate_refresh_token(jti, new_jti, new_expires_at)

        return new_access, new_refresh

    def create_session_for_user(
        self,
        user_id: int,
        refresh_jti: str,
        expires_at: str,
        ip_address: str = "",
        user_agent: str = "",
        metadata: dict | None = None,
    ) -> any:
        """Create a session record for the user.  Requires session_store."""
        if self.session_store is None:
            return None
        return self.session_store.create_session(
            user_id=user_id,
            refresh_jti=refresh_jti,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata,
        )

    def list_sessions(self, user_id: int, active_only: bool = True) -> list:
        """List sessions for a user."""
        if self.session_store is None:
            return []
        return self.session_store.list_sessions_for_user(user_id, active_only=active_only)

    def revoke_session(self, session_id: int) -> bool:
        """Revoke a specific session by ID."""
        if self.session_store is None:
            return False
        return self.session_store.revoke_session(session_id)

    def revoke_all_sessions(self, user_id: int) -> int:
        """Revoke all sessions for a user.  Returns count revoked."""
        if self.session_store is None:
            return 0
        return self.session_store.revoke_all_user_sessions(user_id)

    def refresh_session(self, refresh_token: str) -> tuple[str, str] | None:
        """Compatibility wrapper for dashboard routes."""
        return self.refresh_access_token(refresh_token)


def row_to_user(row: Any | None) -> User | None:
    """Build a User from a sqlite3.Row or a plain dict (PlatformRepository
    rows are already dicts, from both its sqlite and postgres backends)."""
    if row is None:
        return None
    # Convert to dict for safe access with defaults
    row_dict = dict(row)
    normalized_role = Role.from_str(str(row_dict.get("role", "read_only"))).value
    return User(
        id=int(row_dict["id"]),
        email=str(row_dict["email"]),
        hashed_password=str(row_dict["hashed_password"]),
        is_active=bool(row_dict["is_active"]),
        is_superuser=bool(row_dict["is_superuser"]),
        is_verified=bool(row_dict.get("is_verified", 0)),
        role=normalized_role,
        created_at=str(row_dict["created_at"]),
        display_name=str(row_dict.get("display_name", "")),
        last_login=str(row_dict["last_login"]) if row_dict.get("last_login") else None,
        mfa_enabled=bool(row_dict.get("mfa_enabled", 0)),
    )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return "pbkdf2_sha256$120000$" + b64url_encode(salt) + "$" + b64url_encode(digest)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, encoded_salt, encoded_digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = b64url_decode(encoded_salt)
        expected = b64url_decode(encoded_digest)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


async def parse_form_body(request: Any) -> dict[str, str]:
    body = await request.body()
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def b64url_encode(value: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    import base64

    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
