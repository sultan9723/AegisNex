"""SQLite-backed dashboard authentication helpers with PyJWT, RBAC, and token blacklisting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import enum
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Any
from urllib.parse import parse_qs

import jwt as pyjwt


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Role(enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


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

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    @property
    def display_role(self) -> str:
        if self.is_superuser:
            return "Admin"
        return self.role.capitalize()


class AuthError(ValueError):
    """Raised when authentication input or credentials are invalid."""


class TokenBlacklist:
    """In-memory token blacklist with DB persistence for revocations."""

    def __init__(self, database_path: str | Path = "aegisnex_users.db") -> None:
        self.database_path = Path(database_path)
        self._cache: set[str] = set()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
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
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
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
                    role TEXT NOT NULL DEFAULT 'viewer',
                    created_at TEXT NOT NULL
                )
                """
            )
            # Add role column if migrating from old schema
            try:
                connection.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer'")
            except sqlite3.OperationalError:
                pass  # Column already exists

    def create_user(self, email: str, password: str, role: str = "viewer") -> User:
        normalized_email = normalize_email(email)
        if not normalized_email:
            raise AuthError("Email is required.")
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters.")
        if role not in ("admin", "operator", "viewer"):
            raise AuthError("Invalid role. Must be admin, operator, or viewer.")
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
                        1 if role == "admin" else 0,
                        role,
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

    def set_verified(self, user_id: int, verified: bool = True) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_verified = ? WHERE id = ?",
                (1 if verified else 0, user_id),
            )
            return cursor.rowcount > 0


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
        self.blacklist = TokenBlacklist(user_store.database_path)

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
    return User(
        id=int(row_dict["id"]),
        email=str(row_dict["email"]),
        hashed_password=str(row_dict["hashed_password"]),
        is_active=bool(row_dict["is_active"]),
        is_superuser=bool(row_dict["is_superuser"]),
        is_verified=bool(row_dict.get("is_verified", 0)),
        role=str(row_dict.get("role", "viewer")),
        created_at=str(row_dict["created_at"]),
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