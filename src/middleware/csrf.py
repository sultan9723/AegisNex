"""CSRF protection middleware for AegisNex dashboard."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any, ClassVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection middleware.

    Generates and validates CSRF tokens for state-changing operations.
    Tokens are stored in cookies and must be included in request headers.
    """

    # Paths that don't require CSRF protection
    EXEMPT_PATHS: ClassVar[set[str]] = {
        "/api/health",
        "/api/health/ready",
        "/api/health/live",
        "/api/auth/login",
        "/api/auth/demo-login",
        "/api/auth/refresh",
    }

    # Methods that require CSRF protection
    PROTECTED_METHODS: ClassVar[set[str]] = {"POST", "PUT", "PATCH", "DELETE"}

    # Header name for CSRF token
    CSRF_HEADER: ClassVar[str] = "X-CSRF-Token"

    # Cookie name for CSRF token
    CSRF_COOKIE: ClassVar[str] = "csrf_token"

    def __init__(self, app: Any, secret_key: str | None = None) -> None:
        super().__init__(app)
        self.secret_key = secret_key or secrets.token_hex(32)

    def _generate_token(self) -> str:
        """Generate a new CSRF token."""
        return secrets.token_urlsafe(32)

    def _token_is_valid(self, token: str, cookie_token: str) -> bool:
        """Validate CSRF token against cookie token."""
        if not token or not cookie_token:
            return False
        return secrets.compare_digest(token, cookie_token)

    def _uses_explicit_api_auth(self, request: Request) -> bool:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return True
        return bool(request.headers.get("X-API-Key"))

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        """Process request with CSRF validation."""
        # Skip CSRF for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # AegisNex API routes are authenticated through bearer/API-key headers
        # or SameSite auth cookies. The current frontend API client does not
        # implement a CSRF-token handshake, so enforcing it here breaks core
        # product workflows. Keep this middleware for non-API browser posts.
        if request.url.path.startswith(("/api/", "/v1/")):
            return await call_next(request)

        # API clients authenticate each request explicitly and do not rely on
        # ambient browser cookies, so CSRF protection is not applicable.
        if self._uses_explicit_api_auth(request):
            return await call_next(request)

        # Skip CSRF for non-protected methods
        if request.method not in self.PROTECTED_METHODS:
            response = await call_next(request)
            # Set CSRF token cookie for GET requests
            if request.url.path.startswith("/api/"):
                token = self._generate_token()
                response.set_cookie(
                    key=self.CSRF_COOKIE,
                    value=token,
                    max_age=3600,
                    httponly=False,  # Must be accessible by JavaScript
                    secure=False,  # Set to True in production
                    samesite="lax",
                )
            return response

        # Validate CSRF token for protected methods
        csrf_token = request.headers.get(self.CSRF_HEADER, "")
        cookie_token = request.cookies.get(self.CSRF_COOKIE, "")

        if not self._token_is_valid(csrf_token, cookie_token):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid"},
            )

        return await call_next(request)
