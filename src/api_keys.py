"""API key authentication, rate-limiting, IP-restriction, and scope enforcement."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status

from src.auth import hash_api_key
from src.platform_db import PlatformRepository

_logger = logging.getLogger(__name__)


# ======================================================================
# In-memory rate-limiter (per-key sliding window)
# ======================================================================


class KeyRateLimiter:
    """Simple in-memory sliding-window rate limiter keyed by API key prefix."""

    def __init__(self, default_max_requests: int = 100, window_seconds: int = 60) -> None:
        self.default_max = default_max_requests
        self.window = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def check(self, key_prefix: str, max_requests: int | None = None) -> bool:
        now = time.monotonic()
        window_start = now - self.window
        bucket = self._buckets[key_prefix]
        # Prune stale entries
        cutoff = 0
        for i, ts in enumerate(bucket):
            if ts >= window_start:
                cutoff = i
                break
        else:
            cutoff = len(bucket)
        self._buckets[key_prefix] = bucket[cutoff:]

        limit = max_requests or self.default_max
        if len(self._buckets[key_prefix]) >= limit:
            return False
        self._buckets[key_prefix].append(now)
        return True


# Singleton
_rate_limiter = KeyRateLimiter()


# ======================================================================
# API Key authenticator
# ======================================================================


def authenticate_api_key(
    request: Request,
    repo: PlatformRepository,
) -> dict[str, Any] | None:
    """Extract and validate an API key from the ``Authorization`` header.

    Returns the API key record dict if valid, ``None`` otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer anx_"):
        return None

    raw_key = auth_header.split(None, 1)[-1].strip()
    key_hash = hash_api_key(raw_key)

    key_record = repo.get_api_key_by_hash(key_hash)
    if key_record is None:
        return None

    # Active check
    if not key_record.get("is_active", False):
        return None

    # Expiry check
    expires_at = key_record.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp < datetime.now(UTC):
                return None
        except (ValueError, TypeError):
            pass

    # Revocation check
    revoked_at = key_record.get("revoked_at")
    if revoked_at:
        return None

    return key_record


def enforce_api_key_scope(required_scope: str) -> Callable:
    """Factory for a dependency that checks API key scopes.

    Usage::

        @router.post("/ai/chat")
        async def ai_chat(
            request: Request,
            _=Depends(enforce_api_key_scope("ai:chat")),
        ):
            ...

    If the request is authenticated via API key (not session cookie), this
    dependency checks that the key's scopes include the required scope.
    Session-authenticated requests skip scope enforcement (covered by RBAC).
    """

    async def dependency(request: Request) -> None:
        # Only enforce for API-key-authenticated requests
        api_key = getattr(request.state, "api_key", None)
        if api_key is None:
            return

        scopes_raw = api_key.get("scopes", '["*"]')
        try:
            scopes = json.loads(scopes_raw) if isinstance(scopes_raw, str) else scopes_raw
        except (json.JSONDecodeError, TypeError):
            scopes = ["*"]

        if "*" in scopes:
            return

        if required_scope not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key does not have required scope: {required_scope}",
            )

    return dependency


def enforce_api_key_ip_restriction(request: Request, key_record: dict[str, Any]) -> None:
    """Check that the request IP is allowed by the API key's IP restriction."""
    allowed_ips_raw = key_record.get("allowed_ips", "")
    if not allowed_ips_raw:
        return

    try:
        allowed_ips = (
            json.loads(allowed_ips_raw) if isinstance(allowed_ips_raw, str) else allowed_ips_raw
        )
    except (json.JSONDecodeError, TypeError):
        return

    if not isinstance(allowed_ips, list) or not allowed_ips:
        return

    client_ip = request.client.host if request.client else ""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if client_ip not in allowed_ips:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key not allowed from this IP address",
        )


# ======================================================================
# FastAPI middleware to detect API key auth
# ======================================================================

import contextlib

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that detects API-key authentication.

    If the ``Authorization`` header starts with ``Bearer anx_``, it resolves
    the key, applies IP restriction and rate-limit checks, and sets
    ``request.state.api_key`` and ``request.state.user``.
    """

    def __init__(
        self,
        app: Any,
        repo_factory: Callable[[], PlatformRepository] | None = None,
    ) -> None:
        super().__init__(app)
        self._repo_factory = repo_factory

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Any:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer anx_"):
            repo = self._get_repo(request)
            if repo is not None:
                key_record = authenticate_api_key(request, repo)
                if key_record is not None:
                    # IP restriction
                    enforce_api_key_ip_restriction(request, key_record)

                    # Rate limit
                    key_prefix = key_record.get("key_prefix", "")
                    if not _rate_limiter.check(key_prefix):
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="API key rate limit exceeded",
                        )

                    # Record usage
                    with contextlib.suppress(Exception):
                        repo.record_api_key_usage(key_record["id"])

                    # Set on request state
                    request.state.api_key = key_record

        return await call_next(request)

    def _get_repo(self, request: Request) -> PlatformRepository | None:
        if self._repo_factory:
            return self._repo_factory()
        services = getattr(request.app.state, "services", None)
        if services is not None:
            return getattr(services, "platform_repository", None)
        return None
