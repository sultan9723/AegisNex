"""SQLite-backed dashboard authentication helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Any
from urllib.parse import parse_qs


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class User:
    id: int
    email: str
    hashed_password: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    created_at: str


class AuthError(ValueError):
    """Raised when authentication input or credentials are invalid."""


class UserStore:
    """SQLite user repository with a FastAPI Users-compatible data shape."""

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
                    is_verified INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )

    def create_user(self, email: str, password: str) -> User:
        normalized_email = normalize_email(email)
        if not normalized_email:
            raise AuthError("Email is required.")
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters.")
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
                        created_at
                    )
                    VALUES (?, ?, 1, 0, 1, ?)
                    """,
                    (normalized_email, hash_password(password), utc_timestamp()),
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


class AuthManager:
    def __init__(
        self,
        user_store: UserStore | None = None,
        jwt_secret: str | None = None,
        token_ttl_seconds: int = 60 * 60 * 8,
    ) -> None:
        self.user_store = user_store or UserStore()
        self.jwt_secret = jwt_secret or os.getenv(
            "AEGISNEX_JWT_SECRET",
            "change-this-development-secret",
        )
        self.token_ttl_seconds = token_ttl_seconds

    def create_access_token(self, user: User) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.token_ttl_seconds)).timestamp()),
        }
        return encode_jwt(payload, self.jwt_secret)

    def get_user_from_token(self, token: str | None) -> User | None:
        if not token:
            return None
        payload = decode_jwt(token, self.jwt_secret)
        if payload is None:
            return None
        try:
            user_id = int(payload.get("sub", ""))
        except ValueError:
            return None
        return self.user_store.get_user_by_id(user_id)

    def register(self, email: str, password: str) -> tuple[User, str]:
        user = self.user_store.create_user(email, password)
        return user, self.create_access_token(user)

    def login(self, email: str, password: str) -> tuple[User, str] | None:
        user = self.user_store.authenticate(email, password)
        if user is None:
            return None
        return user, self.create_access_token(user)


def row_to_user(row: sqlite3.Row | None) -> User | None:
    if row is None:
        return None
    return User(
        id=int(row["id"]),
        email=str(row["email"]),
        hashed_password=str(row["hashed_password"]),
        is_active=bool(row["is_active"]),
        is_superuser=bool(row["is_superuser"]),
        is_verified=bool(row["is_verified"]),
        created_at=str(row["created_at"]),
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


def encode_jwt(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        b64url_json(header) + "." + b64url_json(payload)
    ).encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return signing_input.decode("ascii") + "." + b64url_encode(signature)


def decode_jwt(token: str, secret: str) -> dict[str, Any] | None:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".", 2)
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(b64url_decode(encoded_signature), expected_signature):
            return None
        header = json.loads(b64url_decode(encoded_header).decode("utf-8"))
        if header.get("alg") != "HS256":
            return None
        payload = json.loads(b64url_decode(encoded_payload).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return payload
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


async def parse_form_body(request: Any) -> dict[str, str]:
    body = await request.body()
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def b64url_json(payload: dict[str, Any]) -> str:
    return b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
