"""SQLite-backed dashboard authentication helpers with PyJWT, RBAC, and token blacklisting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import enum
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Any
from urllib.parse import parse_qs

_logger = logging.getLogger(__name__)

import jwt as pyjwt

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
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    def from_str(value: str) -> "Role":
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
    """In-memory token blacklist with DB persistence for revocations."""

    def __init__(self, database_path: str | Path = "aegisnex_users.db") -> None:
        self.database_path = Path(database_path)
        self._cache: set[str] = set()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        _logger.debug("TokenBlacklist opening connection to %s", self.database_path)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout=10000")
        except sqlite3.OperationalError:
            pass
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
            now = int(datetime.now(timezone.utc).timestamp())
            connection.execute("DELETE FROM token_blacklist WHERE expires_at < ?", (now,))
            rows = connection.execute(
                "SELECT jti FROM token_blacklist WHERE expires_at >= ?", (now,)
            ).fetchall()
            self._cache = {str(row["jti"]) for row in rows}

    def revoke(self, jti: str, expires_at: int) -> None:
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
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO token_blacklist (jti, expires_at, revoked_at) VALUES (?, ?, ?)",
                (f"user_revoke_{user_id}", 9999999999, utc_timestamp()),
            )
        self._cache.add(f"user_revoke_{user_id}")


class UserStore:
    """SQLite user repository with role support."""

    def __init__(self, database_path: str | Path = "aegisnex_users.db") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        _logger.debug("UserStore opening connection to %s", self.database_path)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout=10000")
        except sqlite3.OperationalError:
            pass
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
            existing = {str(row["name"]) for row in connection.execute("PRAGMA table_info(users)").fetchall()}
            if "role" not in existing:
                connection.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'read_only'")
            if "display_name" not in existing:
                connection.execute("ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
            if "last_login" not in existing:
                connection.execute("ALTER TABLE users ADD COLUMN last_login TEXT")
            if "mfa_enabled" not in existing:
                connection.execute("ALTER TABLE users ADD COLUMN mfa_enabled INTEGER NOT NULL DEFAULT 0")

    def create_user(self, email: str, password: str, role: str = "viewer") -> User:
        normalized_email = normalize_email(email)
        if not normalized_email:
            raise AuthError("Email is required.")
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters.")
        normalized_role = Role.from_str(role).value
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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ?",
                (normalize_email(email),),
            ).fetchone()
        return row_to_user(row)

    def get_user_by_id(self, user_id: int) -> User | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return row_to_user(row)

    def deactivate_user(self, user_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_active = 0 WHERE id = ?",
                (user_id,),
            )
            return cursor.rowcount > 0

    def update_password(self, user_id: int, new_password: str) -> bool:
        if len(new_password) < 8:
            raise AuthError("Password must be at least 8 characters.")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET hashed_password = ? WHERE id = ?",
                (hash_password(new_password), user_id),
            )
            return cursor.rowcount > 0

    def update_last_login(self, user_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (utc_timestamp(), user_id),
            )

    def update_display_name(self, user_id: int, display_name: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (display_name.strip()[:64], user_id),
            )
            return cursor.rowcount > 0

    def set_verified(self, user_id: int, verified: bool = True) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_verified = ? WHERE id = ?",
                (1 if verified else 0, user_id),
            )
            return cursor.rowcount > 0

    def seed_default_admin(self) -> None:
        admin = self.get_user_by_email("admin")
        if admin is not None:
            if verify_password("admin", admin.hashed_password):
                self.update_password(admin.id, "AegisNex!Demo2026")
            return
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (email, hashed_password, is_active, is_superuser, is_verified, role, created_at)
                VALUES (?, ?, 1, 1, 1, 'administrator', ?)
                """,
                ("admin", hash_password("AegisNex!Demo2026"), utc_timestamp()),
            )


class AuthManager:
    def __init__(
        self,
        user_store: UserStore | None = None,
        jwt_secret: str | None = None,
        token_ttl_seconds: int = 60 * 30,  # 30 minutes default
        refresh_token_ttl_seconds: int = 60 * 60 * 24 * 7,  # 7 days
    ) -> None:
        self.user_store = user_store or UserStore()
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
        self.token_ttl_seconds = int(
            os.getenv("AEGISNEX_TOKEN_TTL_SECONDS", str(token_ttl_seconds))
        )
        self.refresh_token_ttl_seconds = int(
            os.getenv("AEGISNEX_REFRESH_TOKEN_TTL_SECONDS", str(refresh_token_ttl_seconds))
        )
        self.blacklist = TokenBlacklist(self.user_store.database_path)

    def create_access_token(self, user: User) -> str:
        now = datetime.now(timezone.utc)
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
        now = datetime.now(timezone.utc)
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

    def logout(self, token: str | None) -> bool:
        """Revoke the given token."""
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
            return True
        except pyjwt.PyJWTError:
            return False

    def refresh_access_token(self, refresh_token: str) -> str | None:
        """Exchange a valid refresh token for a new access token."""
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
        if self.blacklist.is_revoked(jti):
            return None

        try:
            user_id = int(payload.get("sub", ""))
        except ValueError:
            return None

        user = self.user_store.get_user_by_id(user_id)
        if user is None or not user.is_active:
            return None

        # Revoke the old refresh token
        exp = payload.get("exp", 0)
        self.blacklist.revoke(jti, exp)

        return self.create_access_token(user)


def row_to_user(row: sqlite3.Row | None) -> User | None:
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
