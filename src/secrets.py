"""Secret Management — Fernet-encrypted credentials at rest."""

from __future__ import annotations

import json
import os
import base64
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SecretManager:
    """Manages encrypted secrets using Fernet symmetric encryption.

    The encryption key is derived from an environment variable (AEGISNEX_SECRET_KEY)
    using PBKDF2. Each secret value is encrypted before storage and decrypted on read.
    """

    def __init__(self, repo: Any | None = None) -> None:
        self._repo = repo
        self._fernet: Fernet | None = None

    def _get_key(self) -> bytes:
        secret_key = os.getenv("AEGISNEX_SECRET_KEY")
        if not secret_key:
            raise RuntimeError(
                "AEGISNEX_SECRET_KEY environment variable is required for secret management. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(secret_key) < 16:
            raise RuntimeError(
                "AEGISNEX_SECRET_KEY must be at least 16 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        try:
            return base64.urlsafe_b64decode(secret_key)
        except Exception:
            salt = b"aegisnex-key-salt"
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=600_000,
            )
            derived = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
            return derived

    def _get_fernet(self) -> Fernet:
        if self._fernet is None:
            key = self._get_key()
            self._fernet = Fernet(key)
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string. Returns a base64-encoded cipher string."""
        f = self._get_fernet()
        return f.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a cipher string back to plaintext."""
        f = self._get_fernet()
        return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")

    def store_secret(self, name: str, value: str, category: str = "generic", actor: str = "system") -> dict[str, Any]:
        """Encrypt and store a secret in the database."""
        encrypted = self.encrypt(value)
        if self._repo is not None and hasattr(self._repo, "upsert_secret"):
            return self._repo.upsert_secret(name, encrypted, category, actor=actor)
        return {"name": name, "encrypted": encrypted, "category": category}

    def retrieve_secret(self, name: str) -> str | None:
        """Retrieve and decrypt a secret from the database."""
        if self._repo is not None and hasattr(self._repo, "get_secret"):
            encrypted = self._repo.get_secret(name)
            if encrypted is None:
                return None
            return self.decrypt(encrypted)
        return None

    def list_secrets(self) -> list[dict[str, Any]]:
        """List all stored secrets (without exposing decrypted values)."""
        if self._repo is not None and hasattr(self._repo, "list_secrets"):
            return self._repo.list_secrets()
        return []

    def delete_secret(self, name: str, actor: str = "system") -> bool:
        """Delete a secret from storage."""
        if self._repo is not None and hasattr(self._repo, "delete_secret"):
            return self._repo.delete_secret(name, actor=actor)
        return False
