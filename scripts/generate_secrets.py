"""Generate secure random values for AegisNex's required secrets.

Prints KEY=value lines to stdout only - nothing is written to disk and
nothing is committed. Paste the output into your .env (or your Azure
Container Apps secrets) yourself.

Usage:
    python scripts/generate_secrets.py
"""

from __future__ import annotations

import secrets
import sys

from cryptography.fernet import Fernet


def generate_jwt_secret() -> str:
    """256-bit hex secret for HS256 JWT signing (AEGISNEX_JWT_SECRET)."""
    return secrets.token_hex(32)


def generate_demo_password() -> str:
    """High-entropy password for the server-side-only demo account (AEGISNEX_DEMO_PASSWORD)."""
    return secrets.token_urlsafe(24)


def generate_secret_key() -> str:
    """Valid Fernet key for secrets-at-rest encryption (AEGISNEX_SECRET_KEY)."""
    return Fernet.generate_key().decode("ascii")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("# Generated secrets - copy into your .env or Azure Container Apps secrets.")
    print("# These are printed once and never saved or committed. Treat them as sensitive.")
    print(f"AEGISNEX_JWT_SECRET={generate_jwt_secret()}")
    print(f"AEGISNEX_DEMO_PASSWORD={generate_demo_password()}")
    print(f"AEGISNEX_SECRET_KEY={generate_secret_key()}")


if __name__ == "__main__":
    main()
