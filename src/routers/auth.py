"""Authentication routes for AegisNex dashboard."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from src.auth import AuthManager, parse_form_body
from src.enterprise_auth import (
    OIDCClient,
    OIDCConfigurationError,
    demo_auth_enabled,
    local_auth_enabled,
    new_oidc_nonce,
    new_oidc_state,
    sso_role_for_email,
)
from src.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["auth"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _user_agent(request: Request) -> str:
    return request.headers.get("User-Agent", "")


def _extract_refresh_jti(auth_manager: AuthManager, refresh_token: str) -> str:
    """Extract the JTI from a refresh token without verification."""
    import jwt as pyjwt

    try:
        payload = pyjwt.decode(
            refresh_token,
            auth_manager.jwt_secret,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
        return payload.get("jti", "")
    except pyjwt.PyJWTError:
        return ""


class LoginRequest(BaseModel):
    """Login request schema."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


def _set_auth_cookie(response: Response, token: str, ttl_seconds: int) -> None:
    """Set the authentication cookie."""
    secure = os.getenv("AEGISNEX_ENV", "development").strip().lower() not in {
        "development",
        "dev",
        "local",
        "test",
    }
    response.set_cookie(
        key="aegisnex_session",
        value=token,
        max_age=ttl_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def _set_refresh_cookie(response: Response, token: str, ttl_seconds: int) -> None:
    """Set the refresh token cookie."""
    secure = os.getenv("AEGISNEX_ENV", "development").strip().lower() not in {
        "development",
        "dev",
        "local",
        "test",
    }
    response.set_cookie(
        key="aegisnex_refresh",
        value=token,
        max_age=ttl_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def _set_oidc_cookie(response: Response, key: str, value: str) -> None:
    secure = os.getenv("AEGISNEX_ENV", "development").strip().lower() not in {
        "development",
        "dev",
        "local",
        "test",
    }
    response.set_cookie(
        key=key,
        value=value,
        max_age=600,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def _clear_oidc_cookies(response: Response) -> None:
    response.delete_cookie(key="aegisnex_oidc_state")
    response.delete_cookie(key="aegisnex_oidc_nonce")


def _clear_auth_cookies(response: Response) -> None:
    """Clear authentication cookies."""
    response.delete_cookie(key="aegisnex_session")
    response.delete_cookie(key="aegisnex_refresh")
    _clear_oidc_cookies(response)


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
    if not local_auth_enabled():
        raise HTTPException(status_code=404, detail="Password login is not enabled")
    form = await parse_form_body(request)
    email = form.get("username", "")
    auth_manager: AuthManager = request.app.state.auth_manager
    result = auth_manager.login(email, form.get("password", ""))
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user, access_token, refresh_token = result

    # Create session record
    refresh_jti = _extract_refresh_jti(auth_manager, refresh_token)
    if refresh_jti:
        import jwt as pyjwt

        try:
            payload = pyjwt.decode(
                refresh_token,
                auth_manager.jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            exp_ts = payload.get("exp", 0)
            expires_at = datetime.fromtimestamp(exp_ts, tz=UTC).isoformat().replace("+00:00", "Z")
            auth_manager.create_session_for_user(
                user_id=user.id,
                refresh_jti=refresh_jti,
                expires_at=expires_at,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )
        except Exception:
            logger.warning("Failed to create session for user %d", user.id)

    repo = getattr(request.app.state.services, "platform_repository", None)
    if repo is not None and hasattr(repo, "record_audit_log"):
        repo.record_audit_log(email, "login", "session", email, {})
    response = Response(
        content=json.dumps(
            {
                "access_token": access_token,
                "token_type": "bearer",
            }
        ),
        media_type="application/json",
    )
    _set_auth_cookie(response, access_token, auth_manager.token_ttl_seconds)
    _set_refresh_cookie(response, refresh_token, auth_manager.refresh_token_ttl_seconds)
    return response


@router.post("/api/auth/demo-login")
async def api_demo_login(request: Request) -> Any:
    """Demo login for development environment."""
    if not demo_auth_enabled():
        raise HTTPException(status_code=404, detail="Demo login is not enabled")
    import os as _os

    username = _os.getenv("AEGISNEX_DEMO_USERNAME", "admin")
    password = _os.getenv("AEGISNEX_DEMO_PASSWORD")
    if not password:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503, detail="Demo login is not configured. Set AEGISNEX_DEMO_PASSWORD."
        )
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
        content=json.dumps(
            {
                "access_token": access_token,
                "token_type": "bearer",
            }
        ),
        media_type="application/json",
    )
    _set_auth_cookie(response, access_token, auth_manager.token_ttl_seconds)
    _set_refresh_cookie(response, refresh_token, auth_manager.refresh_token_ttl_seconds)
    return response


@router.get("/api/auth/sso/config")
async def sso_config(request: Request) -> Any:
    """Return enterprise SSO availability without exposing provider secrets."""
    client = getattr(request.app.state, "oidc_client", None) or OIDCClient()
    provider_name = (
        os.getenv("AEGISNEX_SSO_PROVIDER_NAME", "Enterprise SSO").strip() or "Enterprise SSO"
    )
    return {
        "enabled": bool(client.is_enabled),
        "provider": provider_name,
        "local_auth_enabled": local_auth_enabled(),
        "demo_auth_enabled": demo_auth_enabled(),
        "password_login_enabled": local_auth_enabled(),
    }


@router.get("/api/auth/sso/login")
async def sso_login(request: Request) -> Any:
    """Start an OIDC authorization-code login."""
    client = getattr(request.app.state, "oidc_client", None) or OIDCClient()
    if not client.is_enabled:
        raise HTTPException(status_code=404, detail="Enterprise SSO is not configured")
    state = new_oidc_state()
    nonce = new_oidc_nonce()
    try:
        authorization_url = client.build_authorization_url(state=state, nonce=nonce)
    except OIDCConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    response = RedirectResponse(url=authorization_url, status_code=302)
    _set_oidc_cookie(response, "aegisnex_oidc_state", state)
    _set_oidc_cookie(response, "aegisnex_oidc_nonce", nonce)
    return response


@router.get("/api/auth/sso/callback")
async def sso_callback(request: Request) -> Any:
    """Complete OIDC login and create the AegisNex app session."""
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=401, detail=f"SSO login failed: {error}")
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    expected_state = request.cookies.get("aegisnex_oidc_state", "")
    nonce = request.cookies.get("aegisnex_oidc_nonce", "")
    if not code or not state or not expected_state or not nonce or state != expected_state:
        raise HTTPException(status_code=401, detail="Invalid SSO callback state")

    client = getattr(request.app.state, "oidc_client", None) or OIDCClient()
    try:
        profile = client.load_profile(code=code, nonce=nonce)
        auth_manager: AuthManager = request.app.state.auth_manager
        assigned_role = sso_role_for_email(profile.email, client.settings.default_role)
        user, access_token, refresh_token = auth_manager.external_login(
            provider=profile.issuer,
            subject=profile.subject,
            email=profile.email,
            display_name=profile.display_name,
            role=assigned_role,
            claims=profile.claims,
        )
    except (OIDCConfigurationError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    repo = getattr(request.app.state.services, "platform_repository", None)
    if repo is not None and hasattr(repo, "record_audit_log"):
        repo.record_audit_log(
            user.email, "sso_login", "session", user.email, {"provider": profile.issuer}
        )

    frontend_url = os.getenv("AEGISNEX_FRONTEND_URL", "/").strip() or "/"
    dashboard_url = "/dashboard" if frontend_url == "/" else f"{frontend_url.rstrip('/')}/dashboard"
    response = RedirectResponse(url=dashboard_url, status_code=302)
    _clear_oidc_cookies(response)
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
        content=json.dumps(
            {
                "access_token": new_access_token,
                "token_type": "bearer",
            }
        ),
        media_type="application/json",
    )
    _set_auth_cookie(response, new_access_token, auth_manager.token_ttl_seconds)
    _set_refresh_cookie(response, new_refresh_token, auth_manager.refresh_token_ttl_seconds)
    return response


# ---- Session Management ----


@router.get("/api/sessions")
async def list_sessions(request: Request) -> Any:
    """List active sessions for the current user."""
    from src.dashboard import require_auth

    auth_manager: AuthManager = request.app.state.auth_manager
    user = require_auth(request, auth_manager)
    sessions = auth_manager.list_sessions(user.id, active_only=True)
    return {
        "sessions": [
            {
                "id": s.id,
                "created_at": s.created_at,
                "last_used_at": s.last_used_at,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent[:64] if s.user_agent else "",
                "is_active": s.is_active,
            }
            for s in sessions
        ],
        "count": len(sessions),
    }


@router.delete("/api/sessions/{session_id}")
async def revoke_session(
    request: Request,
    session_id: int,
) -> Any:
    """Revoke a specific session."""
    from src.dashboard import require_auth

    auth_manager: AuthManager = request.app.state.auth_manager
    user = require_auth(request, auth_manager)
    # Ensure user owns this session or has admin
    sessions = auth_manager.list_sessions(user.id, active_only=False)
    owned = any(s.id == session_id for s in sessions)
    if not owned and user.role not in ("super_admin", "administrator"):
        raise HTTPException(status_code=403, detail="Cannot revoke another user's session")
    auth_manager.revoke_session(session_id)
    return {"status": "ok", "session_id": session_id}


@router.delete("/api/sessions")
async def revoke_all_sessions(request: Request) -> Any:
    """Revoke all sessions for the current user except the current one."""
    from src.dashboard import require_auth

    auth_manager: AuthManager = request.app.state.auth_manager
    user = require_auth(request, auth_manager)
    # Revoke all sessions
    count = auth_manager.revoke_all_sessions(user.id)
    return {"status": "ok", "revoked_count": count}
