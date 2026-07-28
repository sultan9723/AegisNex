"""Authentication routes for AegisNex dashboard."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from src.auth import AuthManager, parse_form_body
from src.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    """Login request schema."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


def _set_auth_cookie(response: Response, token: str, ttl_seconds: int) -> None:
    """Set the authentication cookie."""
    response.set_cookie(
        key="aegisnex_session",
        value=token,
        max_age=ttl_seconds,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
    )


def _set_refresh_cookie(response: Response, token: str, ttl_seconds: int) -> None:
    """Set the refresh token cookie."""
    response.set_cookie(
        key="aegisnex_refresh",
        value=token,
        max_age=ttl_seconds,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear authentication cookies."""
    response.delete_cookie(key="aegisnex_session")
    response.delete_cookie(key="aegisnex_refresh")


@router.get("/login")
async def login_page() -> RedirectResponse:
    """Redirect to frontend login page."""
    frontend_url = os.getenv("AEGISNEX_FRONTEND_URL", "").strip()
    if not frontend_url:
        environment = os.getenv("AEGISNEX_ENV", "development").strip().lower()
        if environment in {"development", "dev", "local", "test"}:
            frontend_url = "http://localhost:3000"
        else:
            frontend_url = "/"
    return RedirectResponse(url=f"{frontend_url}/login", status_code=302)


@router.post("/api/login")
async def api_login(request: Request) -> Any:
    """Authenticate user with username/password."""

    # Rate limiting is handled by the app's limiter
    form = await parse_form_body(request)
    email = form.get("username", "")
    auth_manager: AuthManager = request.app.state.auth_manager
    result = auth_manager.login(email, form.get("password", ""))
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _user, access_token, refresh_token = result
    repo = getattr(request.app.state.services, "platform_repository", None)
    if repo is not None:
        repo.record_audit_log(email, "login", "session", email, {})
    response = Response(
        content=json.dumps({
            "access_token": access_token,
            "token_type": "bearer",
        }),
        media_type="application/json",
    )
    _set_auth_cookie(response, access_token, auth_manager.token_ttl_seconds)
    _set_refresh_cookie(response, refresh_token, auth_manager.refresh_token_ttl_seconds)
    return response


@router.post("/api/auth/demo-login")
async def api_demo_login(request: Request) -> Any:
    """Demo login for development environment."""
    environment = os.getenv("AEGISNEX_ENV", "development").strip().lower()
    if environment not in {"development", "dev", "local", "test"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Demo login is not available in production")
    import os as _os
    username = _os.getenv("AEGISNEX_DEMO_USERNAME", "admin")
    password = _os.getenv("AEGISNEX_DEMO_PASSWORD")
    if not password:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Demo login is not configured. Set AEGISNEX_DEMO_PASSWORD.")
    auth_manager: AuthManager = request.app.state.auth_manager
    result = auth_manager.login(username, password)
    if result is None:
        auth_manager.user_store.seed_default_admin()
        result = auth_manager.login(username, password)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Demo login is unavailable")
    _user, access_token, refresh_token = result
    repo = getattr(request.app.state.services, "platform_repository", None)
    if repo is not None and hasattr(repo, "record_audit_log"):
        repo.record_audit_log(username, "login", "session", username, {"mode": "demo"})
    response = Response(
        content=json.dumps({
            "access_token": access_token,
            "token_type": "bearer",
        }),
        media_type="application/json",
    )
    _set_auth_cookie(response, access_token, auth_manager.token_ttl_seconds)
    _set_refresh_cookie(response, refresh_token, auth_manager.refresh_token_ttl_seconds)
    return response


@router.get("/api/auth/verify")
async def auth_verify(request: Request) -> Any:
    """Verify current authentication status."""
    from src.dashboard import require_auth
    auth_manager: AuthManager = request.app.state.auth_manager
    user = require_auth(request, auth_manager)
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "is_superuser": user.is_superuser,
        },
    }


@router.get("/logout")
async def logout(request: Request) -> Any:
    """Logout current user."""
    from src.dashboard import _extract_token
    auth_manager: AuthManager = request.app.state.auth_manager
    token = _extract_token(request)
    user = auth_manager.get_user_from_token(token)
    auth_manager.logout(token)
    repo = getattr(request.app.state.services, "platform_repository", None)
    if repo is not None and user is not None and hasattr(repo, "record_audit_log"):
        repo.record_audit_log(user.email, "logout", "session", user.email, {})
    response = RedirectResponse(url="/login", status_code=302)
    _clear_auth_cookies(response)
    return response


@router.post("/api/logout")
async def api_logout(request: Request) -> Any:
    """API logout endpoint."""
    from src.dashboard import _extract_token
    auth_manager: AuthManager = request.app.state.auth_manager
    token = _extract_token(request)
    user = auth_manager.get_user_from_token(token)
    auth_manager.logout(token)
    repo = getattr(request.app.state.services, "platform_repository", None)
    if repo is not None and user is not None and hasattr(repo, "record_audit_log"):
        repo.record_audit_log(user.email, "logout", "session", user.email, {})
    response = Response(content=json.dumps({"status": "ok"}), media_type="application/json")
    _clear_auth_cookies(response)
    return response


@router.post("/api/auth/refresh")
async def api_refresh_token(request: Request) -> Any:
    """Refresh access token using refresh token."""
    auth_manager: AuthManager = request.app.state.auth_manager
    refresh_token = request.cookies.get("aegisnex_refresh")
    if not refresh_token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="No refresh token")
    result = auth_manager.refresh_access_token(refresh_token)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    new_access_token, new_refresh_token = result
    response = Response(
        content=json.dumps({
            "access_token": new_access_token,
            "token_type": "bearer",
        }),
        media_type="application/json",
    )
    _set_auth_cookie(response, new_access_token, auth_manager.token_ttl_seconds)
    _set_refresh_cookie(response, new_refresh_token, auth_manager.refresh_token_ttl_seconds)
    return response
