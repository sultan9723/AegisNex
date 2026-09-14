"""FastAPI dashboard for AegisNex operational visibility."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import secrets
import socket
import time
import uuid
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncGenerator

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.responses import RedirectResponse as StarletteRedirect

from src.agents.orchestrator import AgentOrchestrator
from src.auth import AuthError, AuthManager, Role, User, parse_form_body
from src.config import Config
from src.docker_scanner import DockerScanner
from src.enterprise_auth import (
    OIDCClient,
    OIDCConfigurationError,
    demo_auth_enabled,
    is_production_environment,
    local_auth_enabled,
    new_oidc_nonce,
    new_oidc_state,
    seed_default_admin_enabled,
    sso_auto_create_orgs_enabled,
    sso_role_for_email,
    tenant_membership_required,
)
from src.guardian import Guardian
from src.incidents import Incident, IncidentManager
from src.logging_config import configure_logging, get_logger
from src.monitor import SystemResourceMonitor
from src.platform_db import PlatformRepository, load_database_settings

try:
    from fastapi import Request as FastAPIRequest
    from fastapi import WebSocket, WebSocketDisconnect
except ModuleNotFoundError:
    FastAPIRequest = Any
    WebSocket = Any
    WebSocketDisconnect = Exception


BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DEVELOPMENT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]
VIEWER_ROLES = ("super_admin", "administrator", "soc_analyst", "operator", "read_only", "auditor")
OPERATOR_ROLES = ("super_admin", "administrator", "soc_analyst", "operator")
ADMIN_ROLES = ("super_admin", "administrator")
AUDITOR_ROLES = ("super_admin", "administrator", "auditor")

REALTIME_EVENT_TYPES = {
    "metric_update",
    "incident_created",
    "incident_resolved",
    "remediation_executed",
    "container_status_changed",
}
DEFAULT_WEBSOCKET_POLL_INTERVAL_SECONDS = 5.0


# --- TLS Redirect Middleware ---


def force_https_redirect_enabled() -> bool:
    """Whether TLSRedirectMiddleware should actively redirect HTTP to HTTPS.

    Defaults to disabled. Managed platforms such as Back4app terminate TLS at
    their own edge/reverse proxy and forward requests to the container over
    plain HTTP; unconditionally redirecting in that case sends the browser
    back to the same public HTTPS URL, which the proxy again forwards as
    HTTP, producing an infinite redirect loop. Set
    ``AEGISNEX_FORCE_HTTPS_REDIRECT=true`` only for deployments that serve
    HTTPS directly (no TLS-terminating proxy in front of the app).
    """
    return os.getenv("AEGISNEX_FORCE_HTTPS_REDIRECT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class TLSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS, but only when explicitly enabled.

    See :func:`force_https_redirect_enabled` for why this is opt-in rather
    than automatic in production.
    """

    @staticmethod
    def _forwarded_proto_values(header_value: str | None) -> set[str]:
        if not header_value:
            return set()
        return {value.strip().lower() for value in header_value.split(",") if value.strip()}

    def _request_is_https(self, request: FastAPIRequest) -> bool:
        if request.url.scheme == "https":
            return True
        forwarded_proto = self._forwarded_proto_values(request.headers.get("x-forwarded-proto"))
        return "https" in forwarded_proto

    async def dispatch(self, request: FastAPIRequest, call_next: Any) -> Any:
        environment = os.getenv("AEGISNEX_ENV", "development").strip().lower()
        if environment not in {"development", "dev", "local", "test"} and force_https_redirect_enabled():
            if not self._request_is_https(request):
                url = request.url.replace(scheme="https")
                return StarletteRedirect(url=url, status_code=301)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: FastAPIRequest, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        environment = os.getenv("AEGISNEX_ENV", "development").strip().lower()
        if environment not in {"development", "dev", "local", "test"}:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' ws: wss:"
            )
        return response


class AuthModeMiddleware(BaseHTTPMiddleware):
    """Block disabled auth methods before endpoint-level login processing."""

    async def dispatch(self, request: FastAPIRequest, call_next: Any) -> Any:
        if request.method == "POST" and request.url.path in {"/api/login", "/api/auth/login"}:
            if not local_auth_enabled():
                return JSONResponse({"detail": "Password login is not enabled"}, status_code=404)
        if request.method == "POST" and request.url.path == "/api/auth/demo-login":
            if not demo_auth_enabled():
                return JSONResponse({"detail": "Demo login is not enabled"}, status_code=404)
        return await call_next(request)


# --- Rate Limiter ---

limiter = Limiter(key_func=get_remote_address)

# --- Auth Dependency Helpers ---

PUBLIC_API_PATHS = {
    "/api/health",
    "/api/health/ready",
    "/api/health/live",
    "/api/auth/login",
    "/api/auth/register",
}


def require_auth(request: FastAPIRequest, auth_manager: AuthManager) -> User:
    """Extract and validate the authenticated user from the request.

    Supports JWT via Authorization header/cookie or API key via X-API-Key header.
    """
    user, used_api_key = authenticate_request(request, auth_manager)
    if user is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Authentication required")
    if not used_api_key:
        enforce_tenant_membership(request, user)
    return user


def _websocket_token(websocket: Any, *, allow_query: bool = True) -> str | None:
    """Extract a websocket bearer token from cookie, header, or query string.

    ``allow_query`` controls whether the opaque token may be supplied as a query
    string parameter. Query-string tokens travel in URLs and can leak via logs,
    referrers, and browser history; only allow them where a legacy client (e.g.
    ``mission-control``) requires it. Dashboard-first websocket endpoints pass
    ``allow_query=False`` so they exclusively accept ``Authorization`` headers or
    cookies.
    """
    token = websocket.cookies.get("aegisnex_session")
    if token:
        return token
    auth_header = websocket.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    if not allow_query:
        return None
    query_token = websocket.query_params.get("token") or websocket.query_params.get("access_token")
    return query_token or None


def _query_int(request: Any, name: str, default: int | None = None) -> int | None:
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _query_int(request: Any, name: str, default: int | None = None) -> int | None:
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def require_role(*roles: str):
    """Dependency factory: require the authenticated user to have one of the specified roles."""

    def role_checker(request: FastAPIRequest) -> User:
        auth_manager: AuthManager = request.app.state.auth_manager
        user, used_api_key = authenticate_request(request, auth_manager)
        if user is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="Authentication required")
        if not used_api_key:
            enforce_tenant_membership(request, user)
        if not user.has_role(*roles):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.role}' not permitted. Required: {', '.join(roles)}",
            )
        return user

    return role_checker


def enforce_tenant_membership(request: FastAPIRequest, user: User) -> None:
    if not tenant_membership_required() or user.is_superuser or user.role == "super_admin":
        return
    tenant_manager = getattr(request.app.state, "tenant_manager", None)
    if tenant_manager is None:
        return
    try:
        tenants = tenant_manager.get_user_tenants(user.id)
    except Exception:
        tenants = []
    if not tenants:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="User is not assigned to an organization")


def require_api_scope(request: FastAPIRequest, *required_scopes: str) -> None:
    scopes = set(getattr(request.state, "api_key_scopes", []) or [])
    if not scopes:
        return
    if "*" in scopes:
        return
    if not any(scope in scopes for scope in required_scopes):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403, detail=f"API key scope required: {', '.join(required_scopes)}"
        )


def _extract_token(request: FastAPIRequest) -> str | None:
    """Extract JWT from Authorization header or cookie."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get("aegisnex_session")


def authenticate_request(
    request: FastAPIRequest, auth_manager: AuthManager
) -> tuple[User | None, bool]:
    """Authenticate via JWT or API key.

    Returns:
        (user, used_api_key) tuple.
    """
    user = require_auth_optional(request, auth_manager)
    if user is not None:
        return user, False
    api_key_user = _authenticate_api_key(request, auth_manager)
    if api_key_user is not None:
        return api_key_user, True
    return None, False


def require_auth_optional(request: FastAPIRequest, auth_manager: AuthManager) -> User | None:
    """Attempt authentication without raising on failure."""
    token = _extract_token(request)
    return auth_manager.get_user_from_token(token)


def _authenticate_api_key(request: FastAPIRequest, auth_manager: AuthManager) -> User | None:
    """Authenticate via X-API-Key header.

    Looks up the key hash, checks it's active, and returns a synthetic User.
    """
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer anx_"):
            api_key = auth_header[7:]
    if not api_key:
        return None
    from src.auth import hash_api_key

    key_hash = hash_api_key(api_key)
    services = getattr(request.app.state, "services", None)
    repo = getattr(services, "platform_repository", None) if services is not None else None
    if not repo:
        return None
    try:
        key_record = repo.get_api_key_by_hash(key_hash)
    except Exception:
        return None
    if key_record is None:
        return None
    if not key_record.get("is_active", False):
        return None
    if key_record.get("revoked_at"):
        return None
    expires_at = str(key_record.get("expires_at") or "")
    if expires_at:
        try:
            parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if parsed_expiry <= datetime.now(UTC):
                return None
        except ValueError:
            return None
    key_id = int(key_record["id"])
    with suppress(Exception):
        repo.record_api_key_usage(key_id)
    raw_scopes = key_record.get("scopes") or '["*"]'
    try:
        parsed_scopes = json.loads(raw_scopes) if isinstance(raw_scopes, str) else raw_scopes
    except json.JSONDecodeError:
        parsed_scopes = ["*"]
    if not isinstance(parsed_scopes, list):
        parsed_scopes = ["*"]
    request.state.api_key_id = key_id
    request.state.api_key_scopes = [str(scope) for scope in parsed_scopes]
    request.state.api_key_org_id = key_record.get("org_id")
    role = str(key_record.get("role", "read_only"))
    from src.auth import Role as AuthRole

    normalized = AuthRole.from_str(role).value
    return User(
        id=-key_id,
        email=f"api-key:{key_record.get('name', 'unknown')}",
        hashed_password="",
        is_active=True,
        is_superuser=(normalized in ("super_admin", "administrator")),
        is_verified=True,
        role=normalized,
        created_at=str(key_record.get("created_at", "")),
    )


def _set_auth_cookie(response: Any, token: str, max_age: int) -> None:
    """Set the auth cookie with secure defaults."""
    environment = os.getenv("AEGISNEX_ENV", "development").strip().lower()
    is_production = environment not in {"development", "dev", "local", "test"}
    response.set_cookie(
        "aegisnex_session",
        token,
        httponly=True,
        samesite="strict",
        secure=is_production,
        path="/",
        max_age=max_age,
    )


def _set_refresh_cookie(response: Any, token: str, max_age: int) -> None:
    environment = os.getenv("AEGISNEX_ENV", "development").strip().lower()
    is_production = environment not in {"development", "dev", "local", "test"}
    response.set_cookie(
        "aegisnex_refresh",
        token,
        httponly=True,
        samesite="strict",
        secure=is_production,
        path="/",
        max_age=max_age,
    )


def _clear_auth_cookies(response: Any) -> None:
    response.delete_cookie("aegisnex_session", path="/")
    response.delete_cookie("aegisnex_refresh", path="/")
    response.delete_cookie("aegisnex_oidc_state", path="/")
    response.delete_cookie("aegisnex_oidc_nonce", path="/")


def _set_short_lived_cookie(response: Any, key: str, value: str, max_age: int = 600) -> None:
    environment = os.getenv("AEGISNEX_ENV", "development").strip().lower()
    is_production = environment not in {"development", "dev", "local", "test"}
    response.set_cookie(
        key,
        value,
        httponly=True,
        samesite="strict",
        secure=is_production,
        path="/",
        max_age=max_age,
    )


@dataclass
class DashboardServices:
    monitor: SystemResourceMonitor
    docker_scanner: DockerScanner
    incident_manager: IncidentManager
    guardian: Guardian
    restart_history_path: Path
    http_monitor: Any | None = None
    ssl_monitor: Any | None = None
    tcp_monitor: Any | None = None
    platform_repository: Any | None = None
    monitoring_engine: Any | None = None
    autonomous_pipeline: Any | None = None
    self_healing_engine: Any | None = None
    execution_history: Any | None = None
    policy_engine: Any | None = None
    dashboard_cache: Any | None = None


def create_services(config_path: str | Path = "config.yaml") -> DashboardServices:
    from src.config import Config
    from src.docker_scanner import DockerScanner
    from src.guardian import Guardian
    from src.http_monitor import HttpEndpointMonitor
    from src.incidents import IncidentManager
    from src.monitor import SystemResourceMonitor
    from src.monitoring_engine import MonitoringEngine
    from src.notifications.factory import build_notification_providers
    from src.notifications_compat import NotifierCompat
    from src.orchestrator import SystemHealthChecker
    from src.ssl_monitor import SslCertificateMonitor
    from src.tcp_monitor import TcpTargetMonitor

    config = Config.load(config_path)
    notifier = NotifierCompat(build_notification_providers(config))
    monitor = SystemResourceMonitor(
        cpu_interval_seconds=config.monitoring.cpu_interval_seconds,
        thresholds=config.monitoring.thresholds,
    )
    docker_scanner = DockerScanner(
        include_all=config.docker.include_all,
        client_timeout_seconds=config.docker.client_timeout_seconds,
        restart_timeout_seconds=config.docker.restart_timeout_seconds,
    )
    platform_repository = PlatformRepository(
        config.storage.database_url or load_database_settings(config.storage.database_path)
    )
    incident_manager = IncidentManager(
        config.incidents.history_path,
        storage_repository=platform_repository,
    )
    health_checker = SystemHealthChecker(monitor=monitor, docker_scanner=docker_scanner)
    guardian = Guardian(
        health_checker=health_checker,
        docker_scanner=docker_scanner,
        notifier=notifier,
        restart_cooldown_seconds=config.guardian.restart_cooldown_seconds,
        max_restart_attempts=config.guardian.max_restart_attempts,
        restart_history_path=config.guardian.restart_history_path,
        incident_manager=incident_manager,
        storage_repository=platform_repository,
    )
    http_monitor = (
        HttpEndpointMonitor(
            endpoints=config.health_checks.http.endpoints,
            timeout_seconds=config.health_checks.http.timeout_seconds,
            expected_status=config.health_checks.http.expected_status,
            incident_manager=incident_manager,
            storage_repository=platform_repository,
        )
        if config.health_checks.http.enabled
        else None
    )
    ssl_monitor = (
        SslCertificateMonitor(
            targets=config.health_checks.ssl.targets,
            timeout_seconds=config.health_checks.ssl.timeout_seconds,
            warning_days=config.health_checks.ssl.warning_days,
            incident_manager=incident_manager,
            storage_repository=platform_repository,
        )
        if config.health_checks.ssl.enabled
        else None
    )
    tcp_monitor = (
        TcpTargetMonitor(
            targets=config.health_checks.tcp.targets,
            timeout_seconds=config.health_checks.tcp.timeout_seconds,
            incident_manager=incident_manager,
            storage_repository=platform_repository,
        )
        if config.health_checks.tcp.enabled
        else None
    )
    monitoring_engine = MonitoringEngine(
        platform_repository=platform_repository,
        incident_manager=incident_manager,
        interval_seconds=int(os.getenv("AEGISNEX_MONITOR_INTERVAL_SECONDS", "30")),
    )
    from src.autonomous import AutonomousPipeline
    from src.execution_history import ExecutionHistory
    from src.healing import SelfHealingEngine
    from src.policy_engine import AppPolicyEngine

    policy_engine = AppPolicyEngine(repository=platform_repository)
    execution_history = ExecutionHistory(
        history_path=Path(config.storage.database_path).parent / "execution_history.json",
        repository=platform_repository,
    )
    self_healing_engine = SelfHealingEngine(
        policy_engine=policy_engine,
        docker_scanner=docker_scanner,
        notifier=notifier,
        repository=platform_repository,
    )
    autonomous_pipeline = AutonomousPipeline(
        incident_manager=incident_manager,
        agent_registry=None,
        policy_engine=policy_engine,
        healing_engine=self_healing_engine,
        execution_history=execution_history,
        repository=platform_repository,
    )
    return DashboardServices(
        monitor=monitor,
        docker_scanner=docker_scanner,
        incident_manager=incident_manager,
        guardian=guardian,
        restart_history_path=Path(config.guardian.restart_history_path),
        http_monitor=http_monitor,
        ssl_monitor=ssl_monitor,
        tcp_monitor=tcp_monitor,
        platform_repository=platform_repository,
        monitoring_engine=monitoring_engine,
        autonomous_pipeline=autonomous_pipeline,
        self_healing_engine=self_healing_engine,
        execution_history=execution_history,
        policy_engine=policy_engine,
    )


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def is_local_environment() -> bool:
    environment = os.getenv("AEGISNEX_ENV", "development").strip().lower()
    return environment in {"development", "dev", "local", "test"}


def get_frontend_base_url(default: str = "/") -> str:
    configured = os.getenv("AEGISNEX_FRONTEND_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    if is_local_environment():
        return "http://localhost:3000"
    return default


def frontend_redirect_url(path: str) -> str:
    base = get_frontend_base_url("/")
    clean_path = path if path.startswith("/") else f"/{path}"
    if base == "/":
        return clean_path
    return f"{base}{clean_path}"


def get_cors_origins() -> list[str]:
    configured_origins = os.getenv("AEGISNEX_CORS_ORIGINS", "")
    if configured_origins.strip():
        return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
    if is_local_environment():
        return DEVELOPMENT_CORS_ORIGINS
    return []


def get_network_stats() -> dict[str, Any]:
    try:
        import psutil

        counters = psutil.net_io_counters()
        return {
            "bytes_sent": counters.bytes_sent,
            "bytes_recv": counters.bytes_recv,
            "packets_sent": counters.packets_sent,
            "packets_recv": counters.packets_recv,
            "status": "ok",
        }
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def load_restart_history(path: str | Path) -> dict[str, dict[str, Any]]:
    history_path = Path(path)
    if not history_path.exists():
        return {}
    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(name): value for name, value in payload.items() if isinstance(value, dict)}


def incident_to_dict(incident: Incident) -> dict[str, Any]:
    return incident.to_dict()


def build_container_rows(
    containers: list[dict[str, Any]],
    restart_history: dict[str, dict[str, Any]],
    last_check_timestamp: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for container in containers:
        name = str(container.get("name", "unknown"))
        history = restart_history.get(name, {})
        rows.append(
            {
                "name": name,
                "status": container.get("status", "unknown"),
                "health_status": container.get("health_status", "unknown"),
                "restart_count": int(history.get("attempts", 0)),
                "last_check_timestamp": last_check_timestamp,
                "image": container.get("image", "unknown"),
                "started_at": container.get("started_at"),
                "uptime_seconds": container.get("uptime_seconds"),
                "cpu_percent": container.get("cpu_percent"),
                "memory_usage_bytes": container.get("memory_usage_bytes"),
                "memory_limit_bytes": container.get("memory_limit_bytes"),
                "memory_percent": container.get("memory_percent"),
            }
        )
    return rows


def build_remediation_actions(
    incidents: list[Incident],
    restart_history: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for incident in incidents:
        if incident.remediation_attempted:
            actions.append(
                {
                    "timestamp": incident.timestamp,
                    "service_name": incident.service_name,
                    "action": "restart",
                    "successful": incident.remediation_successful,
                    "incident_id": incident.incident_id,
                    "source": "incident",
                }
            )
    for service_name, history in restart_history.items():
        if history.get("attempts"):
            actions.append(
                {
                    "timestamp": history.get("last_restart", ""),
                    "service_name": service_name,
                    "action": "restart",
                    "successful": None,
                    "incident_id": "",
                    "source": "restart_history",
                }
            )
    return sorted(actions, key=lambda item: str(item.get("timestamp", "")), reverse=True)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def storage_rows(services: DashboardServices, table_name: str) -> list[dict[str, Any]]:
    repository = services.platform_repository
    if repository is None:
        return []
    try:
        return list(repository.fetch_all(table_name))
    except Exception:
        return []


def collect_http_monitoring(services: DashboardServices) -> dict[str, Any]:
    return {
        "status": "disabled",
        "timestamp": utc_now(),
        "availability_percent": 100.0,
        "available_count": 0,
        "total_count": 0,
        "checks": [],
    }


def collect_ssl_monitoring(services: DashboardServices) -> dict[str, Any]:
    return {
        "status": "disabled",
        "timestamp": utc_now(),
        "warning_count": 0,
        "total_count": 0,
        "checks": [],
    }


def collect_tcp_monitoring(services: DashboardServices) -> dict[str, Any]:
    return {
        "status": "disabled",
        "timestamp": utc_now(),
        "availability_percent": 100.0,
        "reachable_count": 0,
        "total_count": 0,
        "checks": [],
    }


def build_monitoring_summary(repository: Any, target_type: str) -> dict[str, Any]:
    targets = [
        t
        for t in repository.list_monitoring_targets()
        if str(t.get("target_type", "")).lower() == target_type
    ]
    latest = [
        r
        for r in repository.latest_check_results()
        if str(r.get("target_type", "")).lower() == target_type
    ]
    details = [dict(r.get("details", {})) for r in latest]
    if not targets:
        base: dict[str, Any] = {
            "status": "disabled",
            "timestamp": utc_now(),
            "total_count": 0,
            "checks": [],
        }
        if target_type == "ssl":
            base["warning_count"] = 0
        elif target_type == "tcp":
            base.update({"availability_percent": 100.0, "reachable_count": 0})
        else:
            base.update({"availability_percent": 100.0, "available_count": 0})
        return base
    if target_type == "ssl":
        wc = len([c for c in details if c.get("status") != "ok"])
        s = "ok" if wc == 0 else "warning"
        return {
            "status": s,
            "timestamp": latest[0]["timestamp"] if latest else utc_now(),
            "warning_count": wc,
            "total_count": len(targets),
            "checks": details,
        }
    if target_type == "tcp":
        rc = len([c for c in details if c.get("reachable")])
        ap = round((rc / len(targets)) * 100, 2) if targets else 100.0
        s = "ok" if rc == len(targets) else "warning"
        return {
            "status": s,
            "timestamp": latest[0]["timestamp"] if latest else utc_now(),
            "availability_percent": ap,
            "reachable_count": rc,
            "total_count": len(targets),
            "checks": details,
        }
    ac = len([c for c in details if c.get("available")])
    ap = round((ac / len(targets)) * 100, 2) if targets else 100.0
    s = "ok" if ac == len(targets) else "warning"
    return {
        "status": s,
        "timestamp": latest[0]["timestamp"] if latest else utc_now(),
        "availability_percent": ap,
        "available_count": ac,
        "total_count": len(targets),
        "checks": details,
    }


def build_metric_trends(
    metric_rows: list[dict[str, Any]], metrics: dict[str, Any], now: datetime | None = None
) -> dict[str, dict[str, Any]]:
    current_time = now or datetime.now(UTC)
    window_start = current_time - timedelta(hours=24)
    recent_rows = [
        r
        for r in metric_rows
        if (parse_timestamp(r.get("timestamp")) or datetime.min.replace(tzinfo=UTC)) >= window_start
    ]
    recent_rows.sort(key=lambda r: str(r.get("timestamp", "")))
    if not recent_rows:
        label = current_time.strftime("%H:%M")
        return {
            "cpu": {"labels": [label], "values": [_safe_float(metrics.get("cpu_percent"))]},
            "memory": {"labels": [label], "values": [_safe_float(metrics.get("ram_percent"))]},
        }
    labels = [
        (parse_timestamp(r.get("timestamp")) or current_time).strftime("%H:%M") for r in recent_rows
    ]
    return {
        "cpu": {
            "labels": labels,
            "values": [_safe_float(r.get("cpu_percent")) for r in recent_rows],
        },
        "memory": {
            "labels": labels,
            "values": [_safe_float(r.get("memory_percent")) for r in recent_rows],
        },
    }


def build_hourly_event_trend(
    rows: list[dict[str, Any]], now: datetime | None = None
) -> dict[str, Any]:
    current_time = now or datetime.now(UTC)
    start_hour = (current_time - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
    buckets = {start_hour + timedelta(hours=i): 0 for i in range(24)}
    for row in rows:
        ts = parse_timestamp(row.get("timestamp"))
        if ts and ts.replace(minute=0, second=0, microsecond=0) in buckets:
            buckets[ts.replace(minute=0, second=0, microsecond=0)] += 1
    return {"labels": [b.strftime("%H:%M") for b in buckets], "values": list(buckets.values())}


def build_notification_statistics(rows: list[dict[str, Any]]) -> dict[str, int]:
    stats: dict[str, int] = {
        "email_count": 0,
        "slack_count": 0,
        "discord_count": 0,
        "failed_notifications": 0,
    }
    ok = {"ok", "sent", "success"}
    for row in rows:
        p = str(row.get("provider", "")).lower()
        if p == "email":
            stats["email_count"] += 1
        elif p == "slack":
            stats["slack_count"] += 1
        elif p == "discord":
            stats["discord_count"] += 1
        if str(row.get("status", "")).lower() not in ok:
            stats["failed_notifications"] += 1
    return stats


def build_recent_incidents(incidents: list[Incident], limit: int = 6) -> list[dict[str, Any]]:
    rows = [incident_to_dict(i) for i in incidents]
    rows.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return rows[:limit]


def _parse_health_check_results(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _incident_evidence(services: DashboardServices, incident: dict[str, Any]) -> dict[str, Any]:
    """Real, observed evidence for one incident - grounding for AI analysis.

    Contains nothing synthesized: every field is pulled directly from the
    incident record or its recorded status transitions.
    """
    incident_id = str(incident.get("incident_id", ""))
    repo = services.platform_repository
    timeline: list[dict[str, Any]] = []
    if repo is not None:
        try:
            timeline = repo.list_incident_transitions(incident_id)
        except Exception:
            timeline = []
    return {
        "incident_id": incident_id,
        "service_name": incident.get("service_name"),
        "incident_type": incident.get("incident_type"),
        "severity": incident.get("severity"),
        "status": incident.get("incident_status", incident.get("status")),
        "description": incident.get("description"),
        "created_at": incident.get("timestamp"),
        "acknowledged_by": incident.get("acknowledged_by"),
        "resolution_notes": incident.get("resolution_notes"),
        "health_check_results": _parse_health_check_results(incident.get("health_check_results")),
        "status_transitions": [
            {
                "from": t.get("from_status"),
                "to": t.get("to_status"),
                "actor": t.get("actor"),
                "timestamp": t.get("timestamp"),
            }
            for t in timeline
        ],
    }


def _similar_incidents_for(repo: Any, incident: dict[str, Any]) -> list[dict[str, Any]]:
    """Other real incidents of the same type, most recent first. Empty if none exist."""
    if repo is None:
        return []
    incident_id = str(incident.get("incident_id", ""))
    incident_type = incident.get("incident_type")
    service_name = incident.get("service_name")
    try:
        rows = repo.fetch_all("incidents")
    except Exception:
        return []
    candidates = [
        r
        for r in rows
        if str(r.get("incident_id")) != incident_id and r.get("incident_type") == incident_type
    ]
    candidates.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    results = []
    for row in candidates[:3]:
        relevance = 1.0 if row.get("service_name") == service_name else 0.6
        results.append(
            {
                "source": "incident_history",
                "content": f"{row.get('service_name')}: {row.get('description') or row.get('incident_type')} ({row.get('incident_status', row.get('status'))})",
                "relevance": relevance,
            }
        )
    return results


def _relevant_runbooks_for(incident: dict[str, Any]) -> list[dict[str, Any]]:
    """Runbooks whose name/category/tags match this incident's type or service.

    Reuses the existing runbook registry (src/intelligence/runbooks). Returns
    an empty list - not a fabricated one - when nothing matches or the
    registry has no runbooks loaded.
    """
    try:
        from src.intelligence.runbooks.registry import get_registry

        candidates = get_registry().list_all()
    except Exception:
        return []
    keywords = {
        str(incident.get("incident_type", "")).lower(),
        str(incident.get("service_name", "")).lower(),
    }
    keywords = {k for k in keywords if k}
    matches = []
    for rb in candidates:
        haystack = " ".join([rb.name, rb.category, *rb.tags]).lower()
        if any(kw in haystack for kw in keywords):
            matches.append({"source": "runbook", "title": rb.name, "content": rb.description})
    return matches[:3]


def _incident_audit_context(repo: Any, incident_id: str) -> list[dict[str, Any]]:
    if repo is None:
        return []
    try:
        rows = repo.fetch_all("audit_logs")
    except Exception:
        return []
    matched = [
        r
        for r in rows
        if str(r.get("resource_id")) == incident_id and r.get("resource_type") == "incident"
    ]
    matched.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return [
        {"content": f"{r.get('actor')} {r.get('action')}", "timestamp": r.get("timestamp", "")}
        for r in matched[:10]
    ]


def _evidence_confidence(evidence: dict[str, Any]) -> float:
    """Deterministic evidence-completeness heuristic, not a model-reported score.

    Deliberately conservative (capped at 0.9) since this never claims certainty.
    """
    score = 0.4
    if evidence.get("health_check_results"):
        score += 0.25
    if evidence.get("status_transitions"):
        score += 0.15
    if evidence.get("description"):
        score += 0.1
    return round(min(score, 0.9), 2)


def _load_incident(services: DashboardServices, incident_id: str) -> dict[str, Any] | None:
    repo = services.platform_repository
    incident = repo.get_incident(incident_id) if repo is not None else None
    if incident is None:
        for item in services.incident_manager.list_incidents():
            if item.incident_id == incident_id:
                incident = item.to_dict()
                break
    return incident


_READ_ONLY_DIAGNOSTIC_ACTIONS = {
    "collect_incident_context",
    "review_health_check_results",
    "review_incident_timeline",
    "prepare_evidence_packet",
}


def _execute_approved_diagnostics(
    services: DashboardServices,
    incident_id: str,
    approval_id: str,
    actor: str,
    requested_actions: list[str],
) -> dict[str, Any]:
    """Execute the approved diagnostics-only plan against one real incident."""
    incident = _load_incident(services, incident_id)
    if incident is None:
        raise ValueError("Incident not found")
    plan = incident.get("proposed_remediation") or {}
    if not isinstance(plan, dict) or not bool(plan.get("read_only", False)):
        raise ValueError("Only read-only diagnostic plans can be executed from this approval path")

    plan_actions = plan.get("actions") if isinstance(plan.get("actions"), list) else []
    action_names = [
        str(item.get("action", "")).strip()
        for item in plan_actions
        if isinstance(item, dict) and str(item.get("action", "")).strip()
    ]
    action_names = requested_actions or action_names
    if not action_names or any(
        action not in _READ_ONLY_DIAGNOSTIC_ACTIONS for action in action_names
    ):
        raise ValueError("Approval contains an unsupported diagnostic action")
    if "prepare_evidence_packet" not in action_names:
        raise ValueError("Diagnostic plan must include prepare_evidence_packet")

    evidence = _incident_evidence(services, incident)
    packet = {
        "title": f"Diagnostic evidence for {incident.get('service_name')}",
        "summary": "Approved read-only diagnostics collected from the incident record.",
        "incident_id": incident_id,
        "collected_at": utc_now(),
        "actions": action_names,
        "incident_context": evidence,
        "health_check_results": evidence.get("health_check_results", []),
        "timeline": evidence.get("status_transitions", []),
    }
    manager = services.incident_manager
    recorded = manager.record_diagnostic_evidence(
        incident_id,
        packet,
        actor=actor,
        incident_snapshot=incident,
        approval_id=approval_id,
    )
    return recorded.to_dict()


INCIDENT_AI_GOVERNANCE_AGENT_ID = "incident-ai"

_POLICY_TO_GOVERNANCE_VERDICT = {
    "safe": "allowed",
    "approval_required": "pending_approval",
    "forbidden": "denied",
}


def _normalize_approval_row(row: dict[str, Any]) -> dict[str, Any]:
    """approval_queue stores the reviewer note as review_comment; the
    frontend contract (ApprovalRequest.comment) expects `comment`."""
    normalized = dict(row)
    normalized.setdefault("comment", normalized.get("review_comment"))
    return normalized


def _ensure_incident_ai_agent_registered(
    gov: Any, provider_name: str, model: str, tenant_id: str
) -> None:
    """Idempotently register the real incident-AI agent identity in GovernanceManager.

    Not a fabricated persona: this is the actual code path (this file's
    /explain and /propose-remediation routes) reporting its own real,
    currently-configured provider/model. Skipped if already registered.
    """
    if gov.get_agent(INCIDENT_AI_GOVERNANCE_AGENT_ID, tenant_id=tenant_id) is not None:
        return
    from src.ai_governance import AIAgent

    gov.register_agent(
        AIAgent(
            agent_id=INCIDENT_AI_GOVERNANCE_AGENT_ID,
            name="Incident AI Assistant",
            agent_type="incident_analysis",
            description=(
                "Generates incident explanations and diagnostic/remediation proposals "
                "from real incident evidence via the configured AI provider "
                "(POST /api/incidents/{id}/explain, /propose-remediation)."
            ),
            owner="system",
            team="platform",
            provider=provider_name or "unknown",
            model=model or "unknown",
        ),
        tenant_id=tenant_id,
    )


def build_recent_remediations(
    storage_remediations: list[dict[str, Any]],
    fallback_actions: list[dict[str, Any]],
    limit: int = 6,
) -> list[dict[str, Any]]:
    rows = storage_remediations or fallback_actions
    normalized = [
        {
            "timestamp": row.get("timestamp", ""),
            "service_name": row.get("service_name", ""),
            "action": row.get("action", ""),
            "successful": _boolish(row.get("successful")),
        }
        for row in rows
    ]
    normalized.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return normalized[:limit]


def calculate_health_score(
    metrics: dict[str, Any], containers: list[dict[str, Any]], active_incident_count: int
) -> dict[str, Any]:
    cpu = _safe_float(metrics.get("cpu_percent"))
    memory = _safe_float(metrics.get("ram_percent"))
    unhealthy = len(
        [
            c
            for c in containers
            if c.get("status") != "running"
            or c.get("health_status") not in {"healthy", "none", None, ""}
        ]
    )
    penalty = (unhealthy / len(containers)) * 25 if containers else 0.0
    score = max(
        0,
        min(
            100,
            round(
                100.0
                - min(cpu, 100.0) * 0.25
                - min(memory, 100.0) * 0.25
                - penalty
                - min(active_incident_count * 5, 25)
            ),
        ),
    )
    if score >= 80:
        status, indicator = "healthy", "green"
    elif score >= 60:
        status, indicator = "degraded", "yellow"
    else:
        status, indicator = "critical", "red"
    return {"score": score, "status": status, "indicator": indicator}


def _safe_float(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _boolish(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    n = str(value).lower()
    if n in {"1", "true", "yes", "ok", "success"}:
        return True
    if n in {"0", "false", "no", "failed", "failure"}:
        return False
    return None


def collect_dashboard_context(
    services: DashboardServices, use_cache: bool = True
) -> dict[str, Any]:
    cache = getattr(services, "dashboard_cache", None)
    if use_cache and cache is not None:
        cached = cache.get_system_metrics()
        if cached is not None:
            return cached
    timestamp = utc_now()
    metrics = services.monitor.run({})
    docker_report = services.docker_scanner.run({"include_all": True})
    containers = docker_report.get("containers", []) if docker_report.get("status") == "ok" else []
    incidents = services.incident_manager.list_incidents()
    active = [i for i in incidents if i.status in {"active", "acknowledged"}]
    resolved = [i for i in incidents if i.status == "resolved"]
    restart_history = load_restart_history(services.restart_history_path)
    metric_rows = storage_rows(services, "metrics_snapshots")
    notification_rows = storage_rows(services, "notifications")
    remediation_rows = storage_rows(services, "remediations")
    actions = build_remediation_actions(incidents, restart_history)
    container_rows = build_container_rows(containers, restart_history, timestamp)
    result = {
        "timestamp": timestamp,
        "metrics": metrics,
        "network": get_network_stats(),
        "containers": container_rows,
        "running_containers": [c for c in containers if c.get("status") == "running"],
        "active_incidents": [incident_to_dict(i) for i in active],
        "resolved_incidents": [incident_to_dict(i) for i in resolved],
        "actions": actions,
        "health_score": calculate_health_score(metrics, container_rows, len(active)),
        "chart_data": {
            "metrics": build_metric_trends(metric_rows, metrics),
            "incidents": build_hourly_event_trend([incident_to_dict(i) for i in incidents]),
            "remediations": build_hourly_event_trend(remediation_rows or actions),
        },
        "recent_incidents": build_recent_incidents(incidents),
        "recent_remediations": build_recent_remediations(remediation_rows, actions),
        "notification_stats": build_notification_statistics(notification_rows),
        "notification_rows": sorted(
            notification_rows, key=lambda r: str(r.get("timestamp", "")), reverse=True
        ),
        "http_monitoring": collect_http_monitoring(services),
        "ssl_monitoring": collect_ssl_monitoring(services),
        "tcp_monitoring": collect_tcp_monitoring(services),
    }
    if cache is not None:
        cache.set_system_metrics(result)
    return result


def build_dashboard_api_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    incidents = context["active_incidents"] + context["resolved_incidents"]
    incidents.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return {
        "system": {
            "timestamp": context["timestamp"],
            "health_score": context["health_score"],
            "metrics": context["metrics"],
            "active_incident_count": len(context["active_incidents"]),
            "running_container_count": len(context["running_containers"]),
        },
        "containers": {
            "timestamp": context["timestamp"],
            "containers": context["containers"],
            "running_containers": context["running_containers"],
            "count": len(context["containers"]),
        },
        "incidents": {
            "active_incidents": context["active_incidents"],
            "resolved_incidents": context["resolved_incidents"],
            "recent_incidents": context["recent_incidents"],
            "incidents": incidents,
            "active_count": len(context["active_incidents"]),
            "resolved_count": len(context["resolved_incidents"]),
            "count": len(incidents),
        },
        "metrics": {
            "timestamp": context["timestamp"],
            "metrics": context["metrics"],
            "network": context["network"],
            "chart_data": context["chart_data"]["metrics"],
        },
        "notifications": {
            "notification_stats": context["notification_stats"],
            "notifications": context.get("notification_rows", [])[:25],
            "count": len(context.get("notification_rows", [])),
        },
        "remediations": {
            "actions": context["actions"],
            "recent_remediations": context["recent_remediations"],
            "count": len(context["actions"]),
        },
        "http_monitoring": context.get("http_monitoring", {"status": "disabled"}),
        "ssl_monitoring": context.get("ssl_monitoring", {"status": "disabled"}),
        "tcp_monitoring": context.get("tcp_monitoring", {"status": "disabled"}),
    }


def build_realtime_event(
    event_type: str, payload: dict[str, Any], timestamp: str | None = None
) -> dict[str, Any]:
    if event_type not in REALTIME_EVENT_TYPES:
        raise ValueError(f"Unsupported realtime event type: {event_type}")
    return {"type": event_type, "timestamp": timestamp or utc_now(), "payload": payload}


def build_realtime_events(
    current: dict[str, Any], previous: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    events = [
        build_realtime_event(
            "metric_update", build_dashboard_api_snapshot(current), current["timestamp"]
        )
    ]
    if previous is None:
        return events
    prev_incidents = {
        i["incident_id"]: i for i in previous["active_incidents"] + previous["resolved_incidents"]
    }
    for i in current["active_incidents"]:
        if i["incident_id"] not in prev_incidents:
            events.append(build_realtime_event("incident_created", i, current["timestamp"]))
    for i in current["resolved_incidents"]:
        if prev_incidents.get(i["incident_id"], {}).get("status") == "active":
            events.append(build_realtime_event("incident_resolved", i, current["timestamp"]))
    prev_actions = {_remediation_key(a) for a in previous["actions"]}
    for a in current["actions"]:
        if _remediation_key(a) not in prev_actions:
            events.append(build_realtime_event("remediation_executed", a, current["timestamp"]))
    prev_containers = {c["name"]: c for c in previous["containers"]}
    for c in current["containers"]:
        pc = prev_containers.get(c["name"])
        if pc is None or any(
            pc.get(f) != c.get(f) for f in ("status", "health_status", "restart_count")
        ):
            events.append(build_realtime_event("container_status_changed", c, current["timestamp"]))
    return events


def _remediation_key(action: dict[str, Any]) -> tuple:
    return (
        str(action.get("timestamp", "")),
        str(action.get("service_name", "")),
        str(action.get("action", "")),
        str(action.get("incident_id", "")),
        str(action.get("source", "")),
    )


async def run_dashboard_broadcaster(
    app: Any, interval_seconds: float = DEFAULT_WEBSOCKET_POLL_INTERVAL_SECONDS
) -> None:
    previous_context: dict[str, Any] | None = None
    manager = app.state.websocket_manager
    while True:
        try:
            if manager.connection_count:
                context = await asyncio.to_thread(collect_dashboard_context, app.state.services)
                events = build_realtime_events(context, previous_context)
                for event in events:
                    await manager.broadcast_with_backoff(event)
                # Broadcast container updates to /ws/containers channel
                if context.get("containers"):
                    await manager.broadcast_with_backoff(
                        {
                            "type": "container_list",
                            "timestamp": context["timestamp"],
                            "payload": {
                                "containers": context["containers"],
                                "count": len(context["containers"]),
                            },
                        },
                        channel="containers",
                    )
                # Broadcast target updates to /ws/targets channel
                repo = app.state.services.platform_repository
                if repo is not None:
                    targets = repo.list_monitoring_targets()
                    await manager.broadcast_with_backoff(
                        {
                            "type": "target_list",
                            "timestamp": context["timestamp"],
                            "payload": {"targets": targets, "count": len(targets)},
                        },
                        channel="targets",
                    )
                manager.reset_failures()
                previous_context = context
            else:
                previous_context = None
                manager.reset_failures()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).error("WebSocket broadcaster error: %s", exc, exc_info=True)
        await asyncio.sleep(interval_seconds)


def build_integrations_context(services: DashboardServices) -> dict[str, Any]:
    def check_grafana() -> dict[str, Any]:
        grafana_dir = BASE_DIR / "grafana"
        provisioned = grafana_dir.exists()
        health_url = None
        dashboard_url = None
        reachable = False
        try:
            import urllib.error
            import urllib.request

            config = getattr(services, "config", None)
            if (
                config
                and hasattr(config, "integrations")
                and hasattr(config.integrations, "grafana_url")
            ):
                health_url = f"{config.integrations.grafana_url.rstrip('/')}/api/health"
            if not health_url:
                grafana_url = os.getenv("AEGISNEX_GRAFANA_URL", "").strip().rstrip("/")
                if grafana_url:
                    health_url = f"{grafana_url}/api/health"
            if not health_url and provisioned and is_local_environment():
                health_url = "http://localhost:3000/api/health"
            if health_url:
                req = urllib.request.Request(health_url, method="GET")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        reachable = True
                dashboard_url = health_url.replace("/api/health", "")
        except Exception:
            reachable = False
        status = "connected" if reachable else ("configured" if provisioned else "not configured")
        return {
            "name": "Grafana",
            "status": status,
            "description": "Provisioned dashboards.",
            "url": dashboard_url,
            "reachable": reachable,
        }

    def check_prometheus() -> dict[str, Any]:
        prometheus_dir = BASE_DIR / "grafana" / "prometheus"
        reachable = False
        scrape_url = None
        try:
            import urllib.error
            import urllib.request

            config = getattr(services, "config", None)
            base = None
            if (
                config
                and hasattr(config, "integrations")
                and hasattr(config.integrations, "prometheus_url")
            ):
                base = config.integrations.prometheus_url.rstrip("/")
            if not base:
                base = os.getenv("AEGISNEX_PROMETHEUS_URL", "").strip().rstrip("/") or None
            if not base and prometheus_dir.exists() and is_local_environment():
                base = "http://localhost:9090"
            if base:
                targets_url = f"{base}/api/v1/targets"
                req = urllib.request.Request(targets_url, method="GET")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        reachable = data.get("status") == "success"
                scrape_url = f"{base}/metrics"
        except Exception:
            reachable = False
        status = (
            "connected"
            if reachable
            else ("configured" if prometheus_dir.exists() else "not configured")
        )
        return {
            "name": "Prometheus",
            "status": status,
            "description": "Metrics endpoint available.",
            "url": scrape_url,
            "reachable": reachable,
        }

    def check_docker() -> dict[str, Any]:
        scanner = getattr(services, "docker_scanner", None)
        reachable = False
        container_count = 0
        running_count = 0
        if scanner is not None:
            report = scanner.run({"include_all": True})
            if report.get("status") == "ok":
                reachable = True
                containers = report.get("containers", [])
                container_count = len(containers)
                running_count = sum(1 for c in containers if c.get("status") == "running")
        return {
            "name": "Docker",
            "status": "connected" if reachable else "disconnected",
            "description": f"Container runtime inventory ({running_count}/{container_count} running).",
            "reachable": reachable,
            "container_count": container_count,
            "running_count": running_count,
        }

    def check_mcp() -> dict[str, Any]:
        reachable = False
        tools_available = 0
        try:
            from src.mcp_server import create_mcp_server

            server = create_mcp_server()
            tools = getattr(server, "tools", None)
            if tools is not None:
                tools_available = len(tools)
                reachable = tools_available > 0
            else:
                list_fn = getattr(server, "list_tools", None)
                if callable(list_fn):
                    try:
                        import asyncio

                        result = asyncio.get_event_loop().run_until_complete(list_fn())
                        tools_available = len(result) if isinstance(result, list) else 0
                        reachable = tools_available > 0
                    except Exception:
                        reachable = False
        except Exception:
            reachable = False
        status = "available" if reachable else "unavailable"
        return {
            "name": "MCP",
            "status": status,
            "description": f"FastMCP server ({tools_available} tools).",
            "reachable": reachable,
            "tool_count": tools_available,
        }

    def check_sqlite() -> dict[str, Any]:
        repository = getattr(services, "platform_repository", None)
        reachable = False
        try:
            if repository is not None:
                _ = repository.fetch_all("incidents", limit=1)
                reachable = True
        except Exception:
            reachable = False
        status = "connected" if reachable else "disconnected"
        return {
            "name": "SQLite",
            "status": status,
            "description": "SQLite persistence.",
            "reachable": reachable,
        }

    return {
        "integrations": [
            check_grafana(),
            check_prometheus(),
            check_docker(),
            check_mcp(),
            check_sqlite(),
        ]
    }


def build_mcp_context() -> dict[str, Any]:
    return {
        "mcp_tools": [
            {
                "name": "get_system_health",
                "description": "Current system and Docker health report.",
                "example": '{"tool": "get_system_health"}',
            },
            {
                "name": "list_containers",
                "description": "List Docker containers.",
                "example": '{"tool": "list_containers", "include_all": true}',
            },
            {
                "name": "list_incidents",
                "description": "List incidents by status.",
                "example": '{"tool": "list_incidents", "status": "active"}',
            },
            {
                "name": "get_metrics",
                "description": "Current metrics snapshot.",
                "example": '{"tool": "get_metrics"}',
            },
            {
                "name": "get_http_monitoring",
                "description": "HTTP endpoint status.",
                "example": '{"tool": "get_http_monitoring"}',
            },
            {
                "name": "get_ssl_monitoring",
                "description": "SSL certificate status.",
                "example": '{"tool": "get_ssl_monitoring"}',
            },
            {
                "name": "get_tcp_monitoring",
                "description": "TCP target status.",
                "example": '{"tool": "get_tcp_monitoring"}',
            },
            {
                "name": "generate_report",
                "description": "Generate weekly or monthly report.",
                "example": '{"tool": "generate_report", "report_type": "weekly"}',
            },
            {
                "name": "restart_container",
                "description": "Restart a Docker container.",
                "example": '{"tool": "restart_container", "container_name": "api"}',
            },
        ],
        "claude_config": json.dumps(
            {
                "mcpServers": {
                    "aegisnex": {
                        "command": "python",
                        "args": ["-m", "src.mcp_server"],
                        "cwd": str(BASE_DIR),
                    }
                }
            },
            indent=2,
        ),
    }


def build_reports_context(services: DashboardServices) -> dict[str, Any]:
    return {
        "reports": [
            {
                "name": "Weekly report",
                "report_type": "weekly",
                "payload": {"window": {"label": "Last 7 days"}},
            },
            {
                "name": "Monthly report",
                "report_type": "monthly",
                "payload": {"window": {"label": "Last 30 days"}},
            },
        ]
    }


def build_notifications_context(services: DashboardServices) -> dict[str, Any]:
    rows = storage_rows(services, "notifications")
    rows = sorted(rows, key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return {"notification_stats": build_notification_statistics(rows), "notifications": rows[:25]}


async def save_metrics_snapshot_task(app: Any, interval_seconds: int = 60) -> None:
    """Periodically save system metrics snapshots to the database for chart history."""
    while True:
        try:
            repo = app.state.services.platform_repository
            if repo is not None and hasattr(repo, "save_metrics_snapshot"):
                monitor = app.state.services.monitor
                docker_scanner = app.state.services.docker_scanner
                metrics = monitor.run({})
                docker_report = docker_scanner.run({"include_all": True})
                containers = docker_report.get("containers", [])
                running = len([c for c in containers if c.get("status") == "running"])
                stopped = len([c for c in containers if c.get("status") == "stopped"])
                incident_mgr = app.state.services.incident_manager
                all_incidents = incident_mgr.list_incidents()
                active_incidents = len(
                    [i for i in all_incidents if i.status in {"active", "acknowledged"}]
                )
                resolved_incidents = len([i for i in all_incidents if i.status == "resolved"])
                repo.save_metrics_snapshot(
                    {
                        "aegisnex_system_cpu_usage_percent": float(metrics.get("cpu_percent", 0)),
                        "aegisnex_system_memory_usage_percent": float(
                            metrics.get("ram_percent", 0)
                        ),
                        "aegisnex_system_disk_usage_percent": float(metrics.get("disk_percent", 0)),
                        "aegisnex_system_network_bytes_sent": float(
                            metrics.get("network_bytes_sent", 0)
                        ),
                        "aegisnex_system_network_bytes_received": float(
                            metrics.get("network_bytes_recv", 0)
                        ),
                        "aegisnex_containers_running": float(running),
                        "aegisnex_containers_stopped": float(stopped),
                        "aegisnex_incidents_active": float(active_incidents),
                        "aegisnex_incidents_resolved": float(resolved_incidents),
                        "aegisnex_incidents_total": float(len(all_incidents)),
                    }
                )
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Metrics snapshot task failed")
        await asyncio.sleep(interval_seconds)


async def incident_broadcast_task(app: Any, event_type: str, payload: dict[str, Any]) -> None:
    """Broadcast an incident event to the incidents WebSocket channel."""
    try:
        manager = app.state.websocket_manager
        event = build_realtime_event(
            event_type.replace("incident_", "")
            if event_type.startswith("incident_")
            else event_type,
            payload,
        )
        await manager.broadcast(event, channel="incidents")
    except Exception:
        pass


def create_app(
    services: DashboardServices | None = None,
    auth_manager: AuthManager | None = None,
    telemetry_db_path: str | None = None,
) -> Any:
    try:
        from fastapi import FastAPI, HTTPException, Response
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import RedirectResponse
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Dashboard dependencies are missing. Install requirements.txt first."
        ) from exc

    @asynccontextmanager
    async def lifespan(fastapi_app: Any) -> Any:
        # Set broadcast callback on incident manager
        im = getattr(fastapi_app.state.services, "incident_manager", None)
        if im is not None:
            app_loop = asyncio.get_running_loop()

            def _incident_broadcast(event_type: str, payload: dict[str, Any]) -> None:
                asyncio.run_coroutine_threadsafe(
                    incident_broadcast_task(fastapi_app, event_type, payload),
                    app_loop,
                )

            im.broadcast_callback = _incident_broadcast

        fastapi_app.state.websocket_broadcast_task = asyncio.create_task(
            run_dashboard_broadcaster(
                fastapi_app, fastapi_app.state.websocket_poll_interval_seconds
            )
        )
        fastapi_app.state.metrics_snapshot_task = asyncio.create_task(
            save_metrics_snapshot_task(fastapi_app, 60)
        )
        fastapi_app.state.monitoring_engine_task = None
        if getattr(fastapi_app.state.services, "monitoring_engine", None) is not None:
            fastapi_app.state.monitoring_engine_task = asyncio.create_task(
                fastapi_app.state.services.monitoring_engine.run_forever()
            )
        from src.agents.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator(repo=fastapi_app.state.services.platform_repository)
        fastapi_app.state.agent_orchestrator = orchestrator

        # Start autonomous pipeline
        pipeline = getattr(fastapi_app.state.services, "autonomous_pipeline", None)
        if pipeline is not None:
            try:
                pipeline._agents = (
                    orchestrator.registry if hasattr(orchestrator, "registry") else None
                )
                asyncio.create_task(pipeline.start())
            except Exception:
                logger.exception("Failed to start autonomous pipeline")
        try:
            yield
        finally:
            for task_name in (
                "monitoring_engine_task",
                "websocket_broadcast_task",
                "metrics_snapshot_task",
            ):
                t = getattr(fastapi_app.state, task_name, None)
                if t is not None:
                    t.cancel()
                    with suppress(asyncio.CancelledError):
                        await t

    app = FastAPI(title="AegisNex Dashboard", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-CSRF-Token"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TLSRedirectMiddleware)
    from src.telemetry.collector import TelemetryCollector
    from src.telemetry.middleware import TelemetryMiddleware

    if not telemetry_db_path:
        data_dir = os.getenv("AEGISNEX_DATA_DIR", "").strip()
        telemetry_db_path = str(Path(data_dir) / "telemetry.db") if data_dir else "telemetry.db"
    telemetry_collector = TelemetryCollector(telemetry_db_path)
    app.add_middleware(TelemetryMiddleware, collector=telemetry_collector)
    app.add_middleware(AuthModeMiddleware)
    app.state.limiter = limiter
    app.add_exception_handler(429, _rate_limit_exceeded_handler)

    configure_logging()
    from src.opentelemetry import instrument_app

    instrument_app(app)

    logger = get_logger(__name__)
    logger.info("AegisNex dashboard starting")

    app.state.services = services or create_services()
    app.state.auth_manager = auth_manager or AuthManager()
    app.state.oidc_client = OIDCClient()
    if (
        is_production_environment()
        and not app.state.oidc_client.is_enabled
        and not local_auth_enabled()
    ):
        raise RuntimeError(
            "Production auth is not configured. Configure OIDC SSO or set "
            "AEGISNEX_LOCAL_AUTH_ENABLED=true for a controlled fallback."
        )
    if seed_default_admin_enabled():
        try:
            app.state.auth_manager.user_store.seed_default_admin()
        except AuthError as exc:
            logger.warning("Skipping default admin seed: %s", exc)
    from src.cache import DashboardCache

    app.state.dashboard_cache = DashboardCache()
    # collect_dashboard_context() reads the cache off `services`, not `app.state`
    # directly - wire it through so /api/dashboard's 10s TTL cache actually engages
    # instead of silently missing on every request.
    app.state.services.dashboard_cache = app.state.dashboard_cache
    app.state.telemetry_collector = telemetry_collector
    repo = app.state.services.platform_repository
    if repo is not None:
        repo.initialize()
    from src.multitenant.manager import TenantManager

    app.state.tenant_manager = TenantManager(repo) if repo is not None else None
    from src.websocket_manager import WebSocketManager

    app.state.websocket_manager = WebSocketManager()
    app.state.websocket_poll_interval_seconds = float(
        os.getenv("AEGISNEX_WS_POLL_INTERVAL_SECONDS", str(DEFAULT_WEBSOCKET_POLL_INTERVAL_SECONDS))
    )
    app.state.websocket_broadcast_task = None
    app.state.monitoring_engine_task = None
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ---- Helper functions ----
    def current_user(request: FastAPIRequest) -> Any:
        return app.state.auth_manager.get_user_from_token(_extract_token(request))

    def auth_context(request: FastAPIRequest, **extra: Any) -> dict[str, Any]:
        context: dict[str, Any] = {"request": request, "user": current_user(request)}
        context.update(extra)
        return context

    def protected_context(request: FastAPIRequest) -> dict[str, Any] | None:
        user = current_user(request)
        if user is None:
            return None
        context = collect_dashboard_context(app.state.services)
        context["request"] = request
        context["user"] = user
        return context

    def api_context_fn() -> dict[str, Any]:
        return collect_dashboard_context(app.state.services)

    def actor_from_request(request: FastAPIRequest) -> str:
        user = current_user(request)
        return getattr(user, "email", None) or "anonymous"

    def user_tenant_rows(user: User) -> list[dict[str, Any]]:
        tenant_manager = getattr(app.state, "tenant_manager", None)
        if tenant_manager is None or user.id <= 0:
            return []
        try:
            return [tenant.__dict__ for tenant in tenant_manager.get_user_tenants(user.id)]
        except Exception:
            return []

    def request_org_id(request: FastAPIRequest, user: User) -> int | None:
        api_org_id = getattr(request.state, "api_key_org_id", None)
        if api_org_id not in (None, ""):
            try:
                return int(api_org_id)
            except (TypeError, ValueError):
                return None
        rows = user_tenant_rows(user)
        if rows:
            try:
                return int(rows[0]["org_id"])
            except (KeyError, TypeError, ValueError):
                return None
        return None

    def require_workforce_agent_access(
        request: FastAPIRequest, agent: Any, user: User, write: bool = False
    ) -> None:
        from fastapi import HTTPException

        if user.is_superuser or user.role == "super_admin":
            return
        org_id = getattr(agent, "org_id", None)
        if org_id is None:
            if write:
                raise HTTPException(
                    status_code=403, detail="Unassigned workforce agent requires administrator"
                )
            return
        allowed_org = request_org_id(request, user)
        if allowed_org != int(org_id):
            raise HTTPException(
                status_code=403, detail="Workforce agent is outside your organization"
            )

    def maybe_assign_sso_org(user: User) -> None:
        if user.is_superuser or not sso_auto_create_orgs_enabled():
            return
        tenant_manager = getattr(app.state, "tenant_manager", None)
        if tenant_manager is None or user.id <= 0:
            return
        existing = tenant_manager.get_user_tenants(user.id)
        if existing:
            return
        domain = user.email.rsplit("@", 1)[-1] if "@" in user.email else ""
        if not domain:
            return
        org_name = domain.split(".", 1)[0].replace("-", " ").replace("_", " ").title() or domain
        org = tenant_manager.create_organization(org_name, domain=domain)
        tenant_manager.assign_user_to_org(user.id, org.id, role=user.role)

    def require_org_access(request: FastAPIRequest, org_id: int) -> None:
        api_key_org_id = getattr(request.state, "api_key_org_id", None)
        if api_key_org_id not in (None, ""):
            if int(api_key_org_id) != int(org_id):
                raise HTTPException(
                    status_code=403, detail="API key is not scoped to this organization"
                )
            return
        user = require_auth(request, app.state.auth_manager)
        if user.is_superuser or user.role == "super_admin":
            return
        tenant_manager = getattr(app.state, "tenant_manager", None)
        if tenant_manager is None or not tenant_manager.check_isolation(user.id, org_id):
            raise HTTPException(status_code=403, detail="Organization access denied")

    def run_monitoring_once() -> None:
        engine = getattr(app.state.services, "monitoring_engine", None)
        if engine is not None:
            with suppress(Exception):
                engine.run_once()

    def render_report_response(report_type: str, report_format: str) -> Any:
        from src.reporting import OperationalReporter

        repo = getattr(app.state.services, "platform_repository", None)
        database_path = (
            str(getattr(repo, "_sqlite_path", lambda: Path("aegisnex.db"))())
            if repo
            else "aegisnex.db"
        )
        reporter = OperationalReporter(database_path)
        report = reporter.weekly_report() if report_type == "weekly" else reporter.monthly_report()
        if report_format == "json":
            return Response(
                content=json.dumps(report, indent=2),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename={report_type}_report.json"},
            )
        if report_format == "csv":
            output_path = BASE_DIR / "reports" / f"{report_type}_report.csv"
            reporter.export_report(report, output_path, "csv")
            return Response(
                content=output_path.read_text(encoding="utf-8"),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={report_type}_report.csv"},
            )
        if report_format == "pdf":
            output_path = BASE_DIR / "reports" / f"{report_type}_report.pdf"
            reporter.export_report(report, output_path, "pdf")
            return Response(
                content=output_path.read_bytes(),
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={report_type}_report.pdf"},
            )
        return Response(content="Unsupported report format", status_code=400)

    # ---- WebSocket ----
    @app.websocket("/ws/dashboard")
    async def dashboard_websocket(websocket: WebSocket) -> None:
        token = _websocket_token(websocket, allow_query=False)
        if not token or app.state.auth_manager.get_user_from_token(token) is None:
            await websocket.close(code=4001, reason="Authentication required")
            return
        manager = app.state.websocket_manager
        await manager.connect(websocket, channel="dashboard")
        try:
            context = await asyncio.to_thread(collect_dashboard_context, app.state.services)
            await websocket.send_json(
                build_realtime_event(
                    "metric_update", build_dashboard_api_snapshot(context), context["timestamp"]
                )
            )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket, channel="dashboard")
        except Exception:
            manager.disconnect(websocket, channel="dashboard")
            raise

    @app.websocket("/ws/incidents")
    async def incidents_websocket(websocket: WebSocket) -> None:
        token = _websocket_token(websocket, allow_query=False)
        if not token or app.state.auth_manager.get_user_from_token(token) is None:
            await websocket.close(code=4001, reason="Authentication required")
            return
        manager = app.state.websocket_manager
        await manager.connect(websocket, channel="incidents")
        try:
            incidents = app.state.services.incident_manager.list_incidents()
            payload = [i.to_dict() for i in incidents]
            await websocket.send_json(
                {
                    "type": "incident_list",
                    "timestamp": utc_now(),
                    "payload": {"incidents": payload, "count": len(payload)},
                }
            )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket, channel="incidents")
        except Exception:
            manager.disconnect(websocket, channel="incidents")
            raise

    @app.websocket("/ws/containers")
    async def containers_websocket(websocket: WebSocket) -> None:
        token = _websocket_token(websocket, allow_query=False)
        if not token or app.state.auth_manager.get_user_from_token(token) is None:
            await websocket.close(code=4001, reason="Authentication required")
            return
        manager = app.state.websocket_manager
        await manager.connect(websocket, channel="containers")
        try:
            context = await asyncio.to_thread(collect_dashboard_context, app.state.services)
            await websocket.send_json(
                {
                    "type": "container_list",
                    "timestamp": utc_now(),
                    "payload": {
                        "containers": context["containers"],
                        "count": len(context["containers"]),
                    },
                }
            )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket, channel="containers")
        except Exception:
            manager.disconnect(websocket, channel="containers")
            raise

    @app.websocket("/ws/targets")
    async def targets_websocket(websocket: WebSocket) -> None:
        token = _websocket_token(websocket, allow_query=False)
        if not token or app.state.auth_manager.get_user_from_token(token) is None:
            await websocket.close(code=4001, reason="Authentication required")
            return
        manager = app.state.websocket_manager
        await manager.connect(websocket, channel="targets")
        try:
            repo = app.state.services.platform_repository
            targets = repo.list_monitoring_targets() if repo else []
            await websocket.send_json(
                {
                    "type": "target_list",
                    "timestamp": utc_now(),
                    "payload": {"targets": targets, "count": len(targets)},
                }
            )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket, channel="targets")
        except Exception:
            manager.disconnect(websocket, channel="targets")
            raise

    @app.websocket("/ws/containers/{name}/logs")
    async def container_logs_websocket(websocket: WebSocket, name: str) -> None:
        token = _websocket_token(websocket, allow_query=False)
        if not token or app.state.auth_manager.get_user_from_token(token) is None:
            await websocket.close(code=4001, reason="Authentication required")
            return
        await websocket.accept()
        try:
            scanner = app.state.services.docker_scanner
            import docker

            client = docker.from_env(timeout=5)
            container = client.containers.get(name)
            # Send recent logs first
            log_result = scanner.get_container_logs(name, tail=100)
            if log_result.get("status") == "ok":
                await websocket.send_json(
                    {"type": "logs_init", "container": name, "logs": log_result["logs"]}
                )
            # Stream live logs
            async for log_line in _stream_container_logs(container):
                try:
                    await websocket.send_json(
                        {"type": "log_line", "container": name, "line": log_line}
                    )
                except Exception:
                    break
        except docker.errors.NotFound:
            await websocket.send_json({"type": "error", "message": "Container not found"})
            await websocket.close()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    async def _stream_container_logs(container: Any) -> AsyncGenerator[str, None]:
        """Yield live log lines from a container."""
        try:
            logs_stream = container.logs(stream=True, follow=True, tail=0, timestamps=True)
            for log_chunk in logs_stream:
                if isinstance(log_chunk, bytes):
                    yield log_chunk.decode("utf-8", errors="replace").rstrip("\n")
                else:
                    yield str(log_chunk).rstrip("\n")
        except Exception:
            pass

    # ---- Public auth pages ----
    @app.get("/login")
    async def login_page() -> RedirectResponse:
        return RedirectResponse(url=frontend_redirect_url("/login"), status_code=302)

    @app.post("/api/login")
    @limiter.limit("5/minute")
    async def api_login(request: FastAPIRequest) -> Any:
        if not local_auth_enabled():
            raise HTTPException(status_code=404, detail="Password login is not enabled")
        form = await parse_form_body(request)
        email = form.get("username", "")
        result = app.state.auth_manager.login(email, form.get("password", ""))
        if result is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user, access_token, refresh_token = result

        # Create session record
        import jwt as pyjwt

        try:
            refresh_payload = pyjwt.decode(
                refresh_token,
                app.state.auth_manager.jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            refresh_jti = refresh_payload.get("jti", "")
            if refresh_jti:
                exp_ts = refresh_payload.get("exp", 0)
                from datetime import datetime

                expires_at = (
                    datetime.fromtimestamp(exp_ts, tz=UTC).isoformat().replace("+00:00", "Z")
                )
                ip = request.client.host if request.client else ""
                ua = request.headers.get("User-Agent", "")
                app.state.auth_manager.create_session_for_user(
                    user_id=user.id,
                    refresh_jti=refresh_jti,
                    expires_at=expires_at,
                    ip_address=ip,
                    user_agent=ua,
                )
        except Exception:
            pass

        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None and hasattr(repo, "record_audit_log"):
            repo.record_audit_log(email, "login", "session", email, {})
        response = Response(
            content=json.dumps(
                {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "refresh_token": refresh_token,
                }
            ),
            media_type="application/json",
        )
        _set_auth_cookie(response, access_token, app.state.auth_manager.token_ttl_seconds)
        _set_refresh_cookie(
            response, refresh_token, app.state.auth_manager.refresh_token_ttl_seconds
        )
        return response

    @app.post("/api/auth/demo-login")
    async def api_demo_login(request: FastAPIRequest) -> Any:
        if not demo_auth_enabled():
            raise HTTPException(status_code=404, detail="Demo login is not enabled")
        username = os.getenv("AEGISNEX_DEMO_USERNAME", "demo")
        password = os.getenv("AEGISNEX_DEMO_PASSWORD")
        if not password:
            raise HTTPException(
                status_code=503, detail="Demo login is not configured. Set AEGISNEX_DEMO_PASSWORD."
            )
        # Demo login always resolves to a dedicated, restricted read_only
        # account - never the real admin - regardless of AEGISNEX_DEMO_USERNAME.
        result = app.state.auth_manager.login(username, password)
        if result is None:
            with suppress(AuthError):
                app.state.auth_manager.user_store.seed_demo_user(username, password)
            result = app.state.auth_manager.login(username, password)
        if result is None:
            raise HTTPException(status_code=500, detail="Demo login is unavailable")
        user, access_token, refresh_token = result
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None and hasattr(repo, "record_audit_log"):
            repo.record_audit_log(username, "login", "session", username, {"mode": "demo"})
        # Ensure the demo account belongs to an organization so tenant-
        # membership enforcement (required by default in production) doesn't
        # lock a freshly seeded, non-superuser demo user out of every endpoint.
        tenant_manager = getattr(app.state, "tenant_manager", None)
        if tenant_manager is not None and tenant_membership_required() and not user.is_superuser:
            try:
                if not tenant_manager.get_user_tenants(user.id):
                    demo_org = tenant_manager.create_organization(
                        "Demo Workspace", domain="demo.aegisnex.local"
                    )
                    tenant_manager.assign_user_to_org(user.id, demo_org.id, role="read_only")
            except Exception:
                logger.warning("Failed to assign demo user to a demo organization", exc_info=True)
        response = Response(
            content=json.dumps(
                {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "refresh_token": refresh_token,
                }
            ),
            media_type="application/json",
        )
        _set_auth_cookie(response, access_token, app.state.auth_manager.token_ttl_seconds)
        _set_refresh_cookie(
            response, refresh_token, app.state.auth_manager.refresh_token_ttl_seconds
        )
        return response

    @app.get("/api/auth/sso/config")
    async def sso_config(request: FastAPIRequest) -> Any:
        client: OIDCClient = request.app.state.oidc_client
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

    @app.get("/api/auth/sso/login")
    async def sso_login(request: FastAPIRequest) -> Any:
        client: OIDCClient = request.app.state.oidc_client
        if not client.is_enabled:
            raise HTTPException(status_code=404, detail="Enterprise SSO is not configured")
        state = new_oidc_state()
        nonce = new_oidc_nonce()
        try:
            authorization_url = client.build_authorization_url(state=state, nonce=nonce)
        except OIDCConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        response = RedirectResponse(url=authorization_url, status_code=302)
        _set_short_lived_cookie(response, "aegisnex_oidc_state", state)
        _set_short_lived_cookie(response, "aegisnex_oidc_nonce", nonce)
        return response

    @app.get("/api/auth/sso/callback")
    async def sso_callback(request: FastAPIRequest) -> Any:
        error = request.query_params.get("error")
        if error:
            raise HTTPException(status_code=401, detail=f"SSO login failed: {error}")
        code = request.query_params.get("code", "")
        state = request.query_params.get("state", "")
        expected_state = request.cookies.get("aegisnex_oidc_state", "")
        nonce = request.cookies.get("aegisnex_oidc_nonce", "")
        if not code or not state or not expected_state or not nonce or state != expected_state:
            raise HTTPException(status_code=401, detail="Invalid SSO callback state")

        client: OIDCClient = request.app.state.oidc_client
        try:
            profile = client.load_profile(code=code, nonce=nonce)
            assigned_role = sso_role_for_email(profile.email, client.settings.default_role)
            user, access_token, refresh_token = app.state.auth_manager.external_login(
                provider=profile.issuer,
                subject=profile.subject,
                email=profile.email,
                display_name=profile.display_name,
                role=assigned_role,
                claims=profile.claims,
            )
            maybe_assign_sso_org(user)
        except (OIDCConfigurationError, AuthError, ValueError) as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None and hasattr(repo, "record_audit_log"):
            repo.record_audit_log(
                user.email, "sso_login", "session", user.email, {"provider": profile.issuer}
            )
        response = RedirectResponse(url=frontend_redirect_url("/dashboard"), status_code=302)
        _clear_auth_cookies(response)
        _set_auth_cookie(response, access_token, app.state.auth_manager.token_ttl_seconds)
        _set_refresh_cookie(
            response, refresh_token, app.state.auth_manager.refresh_token_ttl_seconds
        )
        return response

    @app.get("/api/auth/verify")
    async def auth_verify(request: FastAPIRequest) -> Any:
        auth_manager: AuthManager = request.app.state.auth_manager
        user = require_auth(request, auth_manager)
        return {
            "authenticated": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "is_superuser": user.is_superuser,
                "tenants": user_tenant_rows(user),
            },
        }

    @app.get("/logout")
    async def logout(request: FastAPIRequest) -> Any:
        token = _extract_token(request)
        user = app.state.auth_manager.get_user_from_token(token)
        app.state.auth_manager.logout(token)
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None and user is not None and hasattr(repo, "record_audit_log"):
            repo.record_audit_log(user.email, "logout", "session", user.email, {})
        response = RedirectResponse(url=frontend_redirect_url("/login"), status_code=302)
        _clear_auth_cookies(response)
        return response

    @app.post("/api/auth/refresh")
    async def auth_refresh(request: FastAPIRequest) -> Any:
        refresh_token = request.cookies.get("aegisnex_refresh") or request.headers.get(
            "x-refresh-token", ""
        )
        if not refresh_token:
            raise HTTPException(status_code=401, detail="Refresh token required")
        refreshed = app.state.auth_manager.refresh_session(refresh_token)
        if refreshed is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        access_token, next_refresh_token = refreshed
        response = Response(
            content=json.dumps(
                {
                    "access_token": access_token,
                    "token_type": "bearer",
                }
            ),
            media_type="application/json",
        )
        _set_auth_cookie(response, access_token, app.state.auth_manager.token_ttl_seconds)
        _set_refresh_cookie(
            response, next_refresh_token, app.state.auth_manager.refresh_token_ttl_seconds
        )
        return response

    # ---- Session Management ----
    @app.get("/api/sessions")
    async def list_sessions(request: FastAPIRequest) -> Any:
        auth_manager = request.app.state.auth_manager
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

    @app.delete("/api/sessions/{session_id}")
    async def revoke_session(request: FastAPIRequest, session_id: int) -> Any:
        from src.rbac import has_permission

        auth_manager = request.app.state.auth_manager
        user = require_auth(request, auth_manager)
        sessions = auth_manager.list_sessions(user.id, active_only=False)
        owned = any(s.id == session_id for s in sessions)
        if not owned and not has_permission(user.role, "session:revoke"):
            raise HTTPException(status_code=403, detail="Cannot revoke another user's session")
        auth_manager.revoke_session(session_id)
        return {"status": "ok", "session_id": session_id}

    @app.delete("/api/sessions")
    async def revoke_all_sessions(request: FastAPIRequest) -> Any:
        auth_manager = request.app.state.auth_manager
        user = require_auth(request, auth_manager)
        count = auth_manager.revoke_all_sessions(user.id)
        return {"status": "ok", "revoked_count": count}

    # ---- Protected template pages ----
    @app.get("/")
    def dashboard_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="dashboard.html", context=ctx, request=request)

    @app.get("/infrastructure")
    def infrastructure_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="infrastructure.html", context=ctx, request=request)

    @app.get("/containers")
    def containers_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="containers.html", context=ctx, request=request)

    @app.get("/incidents")
    def incidents_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="incidents.html", context=ctx, request=request)

    @app.get("/actions")
    def actions_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="actions.html", context=ctx, request=request)

    @app.get("/reports")
    def reports_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        ctx.update(build_reports_context(app.state.services))
        return templates.TemplateResponse(name="reports.html", context=ctx, request=request)

    @app.get("/reports/{report_type}/{report_format}")
    def download_report(request: FastAPIRequest, report_type: str, report_format: str) -> Any:
        user = current_user(request)
        if user is None:
            return RedirectResponse(url="/login", status_code=303)
        return render_report_response(report_type, report_format)

    @app.get("/notifications")
    def notifications_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        ctx.update(build_notifications_context(app.state.services))
        return templates.TemplateResponse(name="notifications.html", context=ctx, request=request)

    @app.get("/mcp")
    def mcp_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        ctx.update(build_mcp_context())
        return templates.TemplateResponse(name="mcp.html", context=ctx, request=request)

    @app.get("/integrations")
    def integrations_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        ctx.update(build_integrations_context(app.state.services))
        return templates.TemplateResponse(name="integrations.html", context=ctx, request=request)

    @app.get("/settings")
    def settings_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="settings.html", context=ctx, request=request)

    @app.get("/audit")
    def audit_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None:
            return RedirectResponse(url="/login", status_code=303)
        repo = getattr(app.state.services, "platform_repository", None)
        logs = repo.list_audit_logs(limit=100) if repo else []
        ctx["logs"] = logs
        return templates.TemplateResponse(name="audit.html", context=ctx, request=request)

    # ---- Authenticated API endpoints (Viewer: read-only) ----
    @app.get("/api/system-health")
    def api_system_health(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        ctx = api_context_fn()
        return {
            "timestamp": ctx["timestamp"],
            "health_score": ctx["health_score"],
            "metrics": ctx["metrics"],
            "active_incident_count": len(ctx["active_incidents"]),
            "running_container_count": len(ctx["running_containers"]),
        }

    @app.get("/api/containers")
    def api_containers(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        ctx = api_context_fn()
        return {
            "timestamp": ctx["timestamp"],
            "containers": ctx["containers"],
            "running_containers": ctx["running_containers"],
            "count": len(ctx["containers"]),
        }

    @app.get("/api/incidents")
    def api_incidents(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        limit = int(request.query_params.get("limit", 100))
        offset = int(request.query_params.get("offset", 0))
        org_id_param = request.query_params.get("org_id")
        org_id = None
        if org_id_param not in (None, ""):
            try:
                org_id = int(str(org_id_param))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Invalid org_id") from None
            require_org_access(request, org_id)
        limit = max(1, min(limit, 1000))
        repo = app.state.services.platform_repository
        if repo is None:
            ctx = api_context_fn()
            incidents = (
                [] if org_id is not None else ctx["active_incidents"] + ctx["resolved_incidents"]
            )
            incidents.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
            active = [
                i
                for i in incidents
                if i.get("incident_status", i.get("status")) in {"active", "acknowledged"}
            ]
            resolved = [
                i for i in incidents if i.get("incident_status", i.get("status")) == "resolved"
            ]
            return {
                "active_incidents": active,
                "resolved_incidents": resolved,
                "recent_incidents": incidents[:6],
                "incidents": incidents[:limit],
                "active_count": len(active),
                "resolved_count": len(resolved),
                "count": len(incidents),
                "limit": limit,
                "offset": offset,
            }
        all_incidents = repo.list_incidents(limit=limit, offset=offset, org_id=org_id)
        total_count = repo.count_incidents(org_id=org_id)
        active = [
            i for i in all_incidents if i.get("incident_status") in {"active", "acknowledged"}
        ]
        resolved = [i for i in all_incidents if i.get("incident_status") == "resolved"]
        active_count = repo.count_incidents(
            incident_status="active", org_id=org_id
        ) + repo.count_incidents(incident_status="acknowledged", org_id=org_id)
        resolved_count = repo.count_incidents(incident_status="resolved", org_id=org_id)
        return {
            "active_incidents": active,
            "resolved_incidents": resolved,
            "recent_incidents": all_incidents[:6],
            "incidents": all_incidents,
            "active_count": active_count,
            "resolved_count": resolved_count,
            "count": total_count,
            "total": total_count,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/incidents/{incident_id}")
    def api_incident_detail(incident_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        incident = repo.get_incident(incident_id) if repo is not None else None
        if incident is None:
            for item in app.state.services.incident_manager.list_incidents():
                if item.incident_id == incident_id:
                    incident = item.to_dict()
                    break
        if incident is None:
            return Response(content="Incident not found", status_code=404)
        timeline = repo.list_incident_transitions(incident_id) if repo is not None else []
        if not timeline:
            timeline = [
                {
                    "id": 0,
                    "incident_id": incident_id,
                    "timestamp": incident.get("timestamp"),
                    "from_status": None,
                    "to_status": incident.get("incident_status", incident.get("status", "active")),
                    "actor": "system",
                    "details": {"reason": "created"},
                }
            ]
        return {"incident": incident, "timeline": timeline, "count": len(timeline)}

    @app.post("/api/incidents/{incident_id}/client")
    async def api_assign_incident_client(incident_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        org_id_value = payload.get("org_id")
        org_id: int | None = None
        org_name: str | None = None
        if org_id_value not in (None, ""):
            try:
                org_id = int(org_id_value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Invalid org_id") from None
            require_org_access(request, org_id)
            mgr: TenantManager = request.app.state.tenant_manager
            try:
                org_name = mgr.get_organization(org_id).name
            except ValueError:
                return Response(content="Organization not found", status_code=404)
        existing = repo.get_incident(incident_id)
        if existing is None:
            return Response(content="Incident not found", status_code=404)
        updated = repo.assign_incident_org(incident_id, org_id, org_name)
        with suppress(KeyError):
            app.state.services.incident_manager.assign_client(incident_id, org_id, org_name)
        repo.record_audit_log(
            user.email,
            "assign_client",
            "incident",
            incident_id,
            {"org_id": org_id, "org_name": org_name},
        )
        return updated

    @app.post("/api/incidents/{incident_id}/explain")
    async def api_explain_incident(incident_id: str, request: FastAPIRequest) -> Any:
        # Read-only: generates analysis text only, never mutates the incident.
        require_role(*VIEWER_ROLES)(request)
        incident = _load_incident(app.state.services, incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")

        from src.intelligence.providers.base import Message
        from src.intelligence.providers.factory import create_provider, get_default_provider

        provider_name = get_default_provider()
        try:
            provider = create_provider()
        except Exception as exc:
            logger.warning(
                "incident.explain provider unavailable incident_id=%s provider=%s error_type=%s",
                incident_id,
                provider_name,
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    f"AI explanation unavailable: provider '{provider_name}' is not configured. "
                    f"Set AEGIS_AI_{provider_name.upper()}_API_KEY on the backend and retry."
                ),
            ) from exc

        evidence = _incident_evidence(app.state.services, incident)
        system_prompt = (
            "You are an infrastructure incident analyst for AegisNex. You are given real, "
            "observed evidence for exactly one incident and nothing else. Respond in exactly "
            "this structure:\n\n"
            "OBSERVED EVIDENCE:\n- Facts taken directly from the evidence provided. Add nothing "
            "that is not present in the evidence.\n\n"
            "POSSIBLE EXPLANATIONS (unconfirmed hypotheses):\n- Candidate causes consistent with "
            "the evidence, explicitly labeled as hypotheses, not confirmed findings.\n\n"
            "RECOMMENDATION:\n- One safe, non-destructive next diagnostic step.\n\n"
            "Never state a root cause as fact unless it is directly confirmed by the evidence. "
            "Never recommend a destructive or irreversible action."
        )
        try:
            response = provider.chat(
                [
                    Message(role="system", content=system_prompt),
                    Message(
                        role="user",
                        content=f"Incident evidence:\n{json.dumps(evidence, indent=2, default=str)}",
                    ),
                ]
            )
        except Exception:
            logger.exception(
                "incident.explain provider call failed incident_id=%s provider=%s",
                incident_id,
                provider_name,
            )
            raise HTTPException(
                status_code=502,
                detail=f"AI provider '{provider_name}' request failed. Check server logs for details.",
            ) from None

        repo = app.state.services.platform_repository
        confidence = _evidence_confidence(evidence)
        result = {
            "incident_id": incident_id,
            "analysis": response.content,
            "similar_incidents": _similar_incidents_for(repo, incident),
            "runbooks": _relevant_runbooks_for(incident),
            "audit_context": _incident_audit_context(repo, incident_id),
            "confidence": confidence,
            "timestamp": utc_now(),
        }
        logger.info(
            "incident.explain succeeded incident_id=%s provider=%s model=%s",
            incident_id,
            provider_name,
            getattr(provider.config, "model", ""),
        )

        # Record this real AI action in the governance action audit. Best-effort:
        # a governance bookkeeping failure must never break the actual response.
        try:
            gov = governance_manager()
            tenant = governance_tenant_id(request)
            model = getattr(provider.config, "model", "")
            _ensure_incident_ai_agent_registered(gov, provider_name, model, tenant)
            from src.ai_governance import AgentAction

            gov.record_action(
                AgentAction(
                    action_id=f"incident-explain-{incident_id}-{utc_now()}",
                    agent_id=INCIDENT_AI_GOVERNANCE_AGENT_ID,
                    action_type="incident_explain",
                    action_summary=f"Explained incident {incident_id}",
                    target_resource=f"incident:{incident_id}",
                    inputs=json.dumps({"incident_id": incident_id}),
                    outputs=json.dumps({"confidence": confidence}),
                    reasoning="Read-only incident analysis; no infrastructure mutation.",
                    confidence_score=confidence,
                    policy_verdict="allowed",
                    status="success",
                ),
                tenant_id=tenant,
            )
        except Exception:
            logger.exception(
                "incident.explain governance recording failed incident_id=%s", incident_id
            )

        return result

    @app.post("/api/incidents/{incident_id}/propose-remediation")
    async def api_propose_incident_remediation(incident_id: str, request: FastAPIRequest) -> Any:
        # Mutates incident state (records a pending proposal) - same access
        # tier as acknowledge/resolve/reopen, never VIEWER_ROLES/read_only.
        user = require_role(*OPERATOR_ROLES)(request)
        incident = _load_incident(app.state.services, incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")

        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None
        plan = payload.get("plan")
        if not isinstance(plan, dict):
            raise HTTPException(status_code=400, detail="plan (object) is required")
        actions = plan.get("actions")
        actions = actions if isinstance(actions, list) else []
        proposed_by = str(payload.get("proposed_by") or user.email or "operator")
        try:
            confidence = float(payload.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        # This endpoint never executes anything - it only classifies each
        # proposed action via the existing governance/policy engine and
        # records the plan as pending human approval.
        policy_engine = getattr(app.state.services, "policy_engine", None)
        context = {
            "incident_id": incident_id,
            "incident_type": incident.get("incident_type"),
            "service_name": incident.get("service_name"),
        }
        classified_actions = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_name = str(action.get("action", "")).strip()
            governance = {
                "verdict": "approval_required",
                "reason": "Policy engine unavailable; defaulting to human approval.",
                "risk_level": None,
            }
            if policy_engine is not None and action_name:
                try:
                    evaluation = policy_engine.evaluate(action_name, {**context, **action})
                    governance = {
                        "verdict": evaluation.verdict.value,
                        "reason": evaluation.reason,
                        "risk_level": evaluation.risk_level,
                    }
                except Exception:
                    logger.exception(
                        "incident.propose_remediation policy evaluation failed incident_id=%s action=%s",
                        incident_id,
                        action_name,
                    )
            classified_actions.append({**action, "governance": governance})

        # Best-effort AI rationale: the plan and its governance classification
        # are already complete and real without this. AI being unconfigured
        # or failing must not block a human-reviewable plan from being
        # proposed - it only means the rationale field stays empty.
        ai_rationale = None
        provider_name = None
        try:
            from src.intelligence.providers.base import Message
            from src.intelligence.providers.factory import create_provider, get_default_provider

            provider_name = get_default_provider()
            provider = create_provider()
            evidence = _incident_evidence(app.state.services, incident)
            prompt = (
                "Given this real incident evidence and this proposed read-only diagnostic plan, "
                "write a one or two sentence rationale for why these steps are reasonable given "
                "the evidence. Do not propose new actions. Do not claim a confirmed root cause."
            )
            response = provider.chat(
                [
                    Message(role="system", content=prompt),
                    Message(
                        role="user",
                        content=json.dumps(
                            {"evidence": evidence, "plan": {**plan, "actions": classified_actions}},
                            default=str,
                        ),
                    ),
                ]
            )
            ai_rationale = response.content
        except Exception as exc:
            logger.info(
                "incident.propose_remediation proceeding without AI rationale incident_id=%s provider=%s error_type=%s",
                incident_id,
                provider_name,
                type(exc).__name__,
            )

        enriched_plan = {**plan, "actions": classified_actions}
        if ai_rationale:
            enriched_plan["ai_rationale"] = ai_rationale

        try:
            updated = app.state.services.incident_manager.propose_remediation(
                incident_id,
                enriched_plan,
                proposed_by=proposed_by,
                confidence=confidence,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Incident not found") from None

        logger.info(
            "incident.propose_remediation succeeded incident_id=%s actions=%d proposed_by=%s ai_rationale=%s",
            incident_id,
            len(classified_actions),
            proposed_by,
            bool(ai_rationale),
        )
        message = "Diagnostic plan proposed and pending approval."
        if not ai_rationale:
            message += " (AI rationale unavailable; governance classification only.)"

        # Record each real, already-classified proposed action in the
        # governance action audit - one governance record per action
        # actually evaluated, using its real policy verdict. Best-effort:
        # a governance bookkeeping failure must never block the proposal.
        governance_action_ids: list[str] = []
        try:
            gov = governance_manager()
            tenant = governance_tenant_id(request)
            if not provider_name:
                from src.intelligence.providers.factory import (
                    get_default_provider as _get_default_provider,
                )

                provider_name = _get_default_provider()
            resolved_provider = provider_name
            model = (
                os.getenv(f"AEGIS_AI_{resolved_provider.upper()}_MODEL", "")
                if resolved_provider
                else ""
            )
            _ensure_incident_ai_agent_registered(gov, resolved_provider, model, tenant)
            from src.ai_governance import AgentAction

            for index, action in enumerate(classified_actions):
                governance_info = action.get("governance", {})
                gov_action_id = f"incident-remediation-{incident_id}-{utc_now()}-{index}"
                gov.record_action(
                    AgentAction(
                        action_id=gov_action_id,
                        agent_id=INCIDENT_AI_GOVERNANCE_AGENT_ID,
                        action_type="propose_remediation",
                        action_summary=str(action.get("action", "diagnostic_action")),
                        target_resource=f"incident:{incident_id}",
                        inputs=json.dumps(
                            {"action": action.get("action"), "target": action.get("target")}
                        ),
                        outputs=json.dumps({"governance": governance_info}),
                        reasoning=str(governance_info.get("reason", "")),
                        confidence_score=confidence,
                        policy_verdict=_POLICY_TO_GOVERNANCE_VERDICT.get(
                            governance_info.get("verdict"), "pending_approval"
                        ),
                        status="success",
                    ),
                    tenant_id=tenant,
                )
                governance_action_ids.append(gov_action_id)
        except Exception:
            logger.exception(
                "incident.propose_remediation governance recording failed incident_id=%s",
                incident_id,
            )

        # Queue this real, already-classified plan for a real human decision
        # via the existing Approvals page/API - this is the "real queue" the
        # UI already advertises. Best-effort: a queueing failure must not
        # undo the proposal that was already persisted above.
        try:
            repo = app.state.services.platform_repository
            if repo is not None:
                from uuid import uuid4

                new_approval_id = f"incident-remediation-{incident_id}-{uuid4().hex[:12]}"
                repo.create_approval_request(
                    new_approval_id,
                    "incident_diagnostic_remediation",
                    proposed_by,
                    f"Diagnostic/remediation plan for incident {incident_id} ({len(classified_actions)} action(s))",
                    {
                        "incident_id": incident_id,
                        "governance_action_ids": governance_action_ids,
                        "actions": [a.get("action") for a in classified_actions],
                        "read_only": bool(plan.get("read_only", True)),
                    },
                )
        except Exception:
            logger.exception(
                "incident.propose_remediation approval queueing failed incident_id=%s", incident_id
            )

        return {"incident": updated.to_dict(), "message": message}

    @app.get("/api/metrics")
    def api_metrics(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        ctx = api_context_fn()
        return {
            "timestamp": ctx["timestamp"],
            "metrics": ctx["metrics"],
            "network": ctx["network"],
            "chart_data": ctx["chart_data"]["metrics"],
        }

    @app.get("/api/metrics/history")
    def api_metrics_history(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        minutes = int(request.query_params.get("minutes", 60))
        minutes = max(1, min(minutes, 1440))
        repo = app.state.services.platform_repository
        if repo is None:
            return {"history": [], "count": 0}
        rows = repo.fetch_all("metrics_snapshots")
        from datetime import datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
        filtered = []
        for row in rows:
            ts = row.get("timestamp", "")
            try:
                parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if parsed >= cutoff:
                    filtered.append(row)
            except ValueError:
                continue
        return {"history": filtered, "count": len(filtered), "minutes": minutes}

    @app.get("/api/notifications")
    def api_notifications(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        ctx = api_context_fn()
        rows = storage_rows(app.state.services, "notifications")
        rows = sorted(rows, key=lambda r: str(r.get("timestamp", "")), reverse=True)
        return {
            "notification_stats": ctx["notification_stats"],
            "notifications": rows[:25],
            "count": len(rows),
        }

    @app.get("/api/remediations")
    def api_remediations(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        ctx = api_context_fn()
        return {
            "actions": ctx["actions"],
            "recent_remediations": ctx["recent_remediations"],
            "count": len(ctx["actions"]),
        }

    @app.get("/api/dashboard")
    def api_dashboard(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        return build_dashboard_api_snapshot(collect_dashboard_context(app.state.services))

    @app.get("/api/mcp")
    def api_mcp(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        return build_mcp_context()

    @app.get("/api/http-monitoring")
    def api_http_monitoring(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        monitor = getattr(app.state.services, "http_monitor", None)
        if monitor is not None:
            return monitor.run({})
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None:
            return build_monitoring_summary(repo, "http")
        return {
            "status": "disabled",
            "timestamp": utc_now(),
            "availability_percent": 100.0,
            "available_count": 0,
            "total_count": 0,
            "checks": [],
        }

    @app.get("/api/ssl-monitoring")
    def api_ssl_monitoring(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        monitor = getattr(app.state.services, "ssl_monitor", None)
        if monitor is not None:
            return monitor.run({})
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None:
            return build_monitoring_summary(repo, "ssl")
        return {
            "status": "disabled",
            "timestamp": utc_now(),
            "warning_count": 0,
            "total_count": 0,
            "checks": [],
        }

    @app.get("/api/tcp-monitoring")
    def api_tcp_monitoring(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        monitor = getattr(app.state.services, "tcp_monitor", None)
        if monitor is not None:
            return monitor.run({})
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None:
            return build_monitoring_summary(repo, "tcp")
        return {
            "status": "disabled",
            "timestamp": utc_now(),
            "availability_percent": 100.0,
            "reachable_count": 0,
            "total_count": 0,
            "checks": [],
        }

    @app.get("/api/audit-logs")
    def api_audit_logs(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"logs": [], "count": 0}
        limit = int(request.query_params.get("limit", 100))
        offset = int(request.query_params.get("offset", 0))
        limit = max(1, min(limit, 1000))
        logs = repo.list_audit_logs(limit=limit, offset=offset)
        total = repo.fetch_all("audit_logs", limit=0, offset=0)
        return {
            "logs": logs,
            "count": len(logs),
            "total": len(total),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/reports")
    def api_reports(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        return build_reports_context(app.state.services)

    @app.get("/api/reports/{report_type}/{report_format}")
    def api_download_report(report_type: str, report_format: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        return render_report_response(report_type, report_format)

    @app.get("/api/monitoring-targets")
    def api_monitoring_targets(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"targets": [], "count": 0}
        targets = repo.list_monitoring_targets(include_inactive=True)
        latest_results = repo.latest_check_results()
        latest_by_target = {
            str(r.get("target_id") or r.get("target_name")): r for r in latest_results
        }
        enriched = []
        for target in targets:
            key = str(target.get("id"))
            fallback_key = str(target.get("name"))
            result = latest_by_target.get(key) or latest_by_target.get(fallback_key)
            row = dict(target)
            row["latest_result"] = result.get("details") if result else None
            row["last_checked_at"] = result.get("timestamp") if result else None
            enriched.append(row)
        return {"targets": enriched, "count": len(enriched)}

    @app.get("/api/monitoring-targets/{target_id}/history")
    def api_monitoring_target_history(target_id: int, request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"history": [], "count": 0}
        rows = repo.check_history(target_id, limit=100)
        return {"history": rows, "count": len(rows)}

    @app.get("/api/integrations")
    def api_integrations(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        return build_integrations_context(app.state.services)

    @app.get("/api/integrations/catalog")
    def api_integrations_catalog(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        from src.integrations.marketplace import get_marketplace_catalog

        cat = get_marketplace_catalog()
        return {"catalog": cat, "count": len(cat)}

    @app.get("/api/integrations/installed")
    def api_integrations_installed(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        from src.integrations.marketplace import get_installed_integrations

        inst = get_installed_integrations()
        return {"integrations": inst, "count": len(inst)}

    @app.get("/api/integrations/status")
    def api_integrations_status(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        from src.integrations.status_center import build_integration_status_center

        return build_integration_status_center(app.state.services)

    @app.get("/api/platform/health")
    def api_platform_health(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        from src.integrations.status_center import (
            build_integration_status_center,
        )

        status = build_integration_status_center(app.state.services)
        return {
            "platform_health": status["platform_health"],
            "integrations": status["integrations"],
            "timestamp": utc_now(),
        }

    @app.post("/api/integrations/install")
    async def api_install_integration(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.integrations.marketplace import install_integration

        payload = await request.json()
        name = str(payload.get("name", "")).strip().lower()
        config = payload.get("config", {})
        if not name:
            return Response(content="Integration name is required", status_code=400)
        provider = install_integration(name, config)
        if provider is None:
            return Response(content=f"Unknown integration: {name}", status_code=404)
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous", "install", "integration", name, {}
            )
        return {"status": "ok", "name": name}

    @app.post("/api/integrations/{name}/uninstall")
    def api_uninstall_integration(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.integrations.marketplace import uninstall_integration

        removed = uninstall_integration(name)
        if not removed:
            return Response(content=f"Integration not found: {name}", status_code=404)
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous", "uninstall", "integration", name, {}
            )
        return {"status": "ok", "name": name}

    @app.put("/api/integrations/{name}")
    async def api_update_integration(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.integrations.marketplace import install_integration

        payload = await request.json()
        config = payload.get("config", {})
        provider = install_integration(name, config)
        if provider is None:
            return Response(content=f"Unknown integration: {name}", status_code=404)
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous", "update", "integration", name, {}
            )
        return {"status": "ok", "name": name}

    @app.post("/api/integrations/{name}/health")
    def api_integration_health(name: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        from src.integrations.base import get_integration
        from src.integrations.marketplace import get_installed_integrations

        installed = get_installed_integrations()
        config = None
        for inst in installed:
            if inst.get("integration_id") == name:
                config = {
                    "credentials": inst.get("credentials", {}),
                    "settings": inst.get("settings", {}),
                }
                break
        provider = get_integration(name, config or {})
        if provider is None:
            return Response(content=f"Unknown integration: {name}", status_code=404)
        try:
            import asyncio

            result = asyncio.run(provider.health_check())
            return {"status": "ok", "name": name, "health": result}
        except Exception as exc:
            return {"status": "error", "name": name, "error": str(exc)}

    @app.post("/api/integrations/{name}/test")
    def api_integration_test(name: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        from src.integrations.status_center import test_integration_connection

        return test_integration_connection(app.state.services, name)

    @app.get("/api/system-info")
    def api_system_info(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        docker_version = None
        try:
            import docker

            client = docker.from_env(timeout=5)
            docker_version = client.version().get("Version", "unknown")
        except Exception:
            docker_version = None
        uptime_seconds = None
        try:
            import psutil

            uptime_seconds = int(time.time() - psutil.boot_time())
        except Exception:
            uptime_seconds = None
        return {
            "os": f"{platform.system()} {platform.release()}",
            "hostname": socket.gethostname(),
            "uptime_seconds": uptime_seconds,
            "docker_version": docker_version,
        }

    @app.get("/api/settings")
    def api_get_settings(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"settings": {}}
        return {"settings": repo.get_settings()}

    # ---- Operator: incident actions ----
    @app.post("/api/incidents/{incident_id}/acknowledge")
    async def api_acknowledge_incident(incident_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        try:
            incident = app.state.services.incident_manager.acknowledge_incident(
                incident_id, actor=user.email
            )
        except KeyError:
            return Response(content="Incident not found", status_code=404)
        app.state.services.platform_repository.record_audit_log(
            user.email, "acknowledge", "incident", incident_id, {}
        )
        return incident.to_dict()

    @app.post("/api/incidents/{incident_id}/resolve")
    async def api_resolve_incident(incident_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        notes = None
        try:
            payload = await request.json()
            notes = str(payload.get("resolution_notes", "")).strip() or None
        except Exception:
            notes = None
        try:
            incident = app.state.services.incident_manager.resolve_incident(
                incident_id, actor=user.email, resolution_notes=notes
            )
        except KeyError:
            return Response(content="Incident not found", status_code=404)
        app.state.services.platform_repository.record_audit_log(
            user.email, "resolve", "incident", incident_id, {"resolution_notes": notes}
        )
        return incident.to_dict()

    @app.post("/api/incidents/{incident_id}/reopen")
    def api_reopen_incident(incident_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        try:
            incident = app.state.services.incident_manager.reopen_incident(
                incident_id, actor=user.email
            )
        except KeyError:
            return Response(content="Incident not found", status_code=404)
        app.state.services.platform_repository.record_audit_log(
            user.email, "reopen", "incident", incident_id, {}
        )
        return incident.to_dict()

    # ---- Operator: container actions ----
    @app.post("/api/containers/{name}/start")
    def api_container_start(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        mc_id = f"mc-docker-start-{uuid.uuid4().hex[:12]}"
        mc_exec = _start_mc_execution(
            request,
            mc_id,
            f"Start container: {name}",
            "docker_action",
            audit_links={"action": "container_start", "container": name},
        )
        if mc_exec is not None:
            _mc_complete_stage(mc_exec, "docker", status="running")
        start_ts = time.time()
        scanner = app.state.services.docker_scanner
        result = scanner.start_container(name)
        duration = (time.time() - start_ts) * 1000
        if result.get("status") == "error":
            if mc_exec is not None:
                _finish_mc_execution(
                    mc_exec,
                    status="failed",
                    error=result.get("message", "start failed"),
                    total_latency_ms=duration,
                )
            return Response(
                content=json.dumps(result), status_code=404, media_type="application/json"
            )
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous", "container_start", "container", name, {}
            )
        if mc_exec is not None:
            _mc_complete_stage(
                mc_exec,
                "docker",
                status="completed",
                latency_ms=duration,
                summary=f"Container {name} started",
            )
            _finish_mc_execution(
                mc_exec,
                status="completed",
                overall_result=f"Container {name} started successfully",
                total_latency_ms=duration,
            )
        return result

    @app.post("/api/containers/{name}/stop")
    def api_container_stop(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        mc_id = f"mc-docker-stop-{uuid.uuid4().hex[:12]}"
        mc_exec = _start_mc_execution(
            request,
            mc_id,
            f"Stop container: {name}",
            "docker_action",
            audit_links={"action": "container_stop", "container": name},
        )
        if mc_exec is not None:
            _mc_complete_stage(mc_exec, "docker", status="running")
        start_ts = time.time()
        scanner = app.state.services.docker_scanner
        result = scanner.stop_container(name)
        duration = (time.time() - start_ts) * 1000
        if result.get("status") == "error":
            if mc_exec is not None:
                _finish_mc_execution(
                    mc_exec,
                    status="failed",
                    error=result.get("message", "stop failed"),
                    total_latency_ms=duration,
                )
            return Response(
                content=json.dumps(result), status_code=404, media_type="application/json"
            )
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous", "container_stop", "container", name, {}
            )
        if mc_exec is not None:
            _mc_complete_stage(
                mc_exec,
                "docker",
                status="completed",
                latency_ms=duration,
                summary=f"Container {name} stopped",
            )
            _finish_mc_execution(
                mc_exec,
                status="completed",
                overall_result=f"Container {name} stopped successfully",
                total_latency_ms=duration,
            )
        return result

    @app.post("/api/containers/{name}/restart")
    def api_container_restart(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        mc_id = f"mc-docker-restart-{uuid.uuid4().hex[:12]}"
        mc_exec = _start_mc_execution(
            request,
            mc_id,
            f"Restart container: {name}",
            "docker_action",
            audit_links={"action": "container_restart", "container": name},
        )
        if mc_exec is not None:
            _mc_complete_stage(mc_exec, "docker", status="running")
        start_ts = time.time()
        scanner = app.state.services.docker_scanner
        result = scanner.restart_container(name)
        duration = (time.time() - start_ts) * 1000
        if result.get("status") == "error":
            if mc_exec is not None:
                _finish_mc_execution(
                    mc_exec,
                    status="failed",
                    error=result.get("message", "restart failed"),
                    total_latency_ms=duration,
                )
            return Response(
                content=json.dumps(result), status_code=404, media_type="application/json"
            )
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous", "container_restart", "container", name, {}
            )
        if mc_exec is not None:
            _mc_complete_stage(
                mc_exec,
                "docker",
                status="completed",
                latency_ms=duration,
                summary=f"Container {name} restarted",
            )
            _finish_mc_execution(
                mc_exec,
                status="completed",
                overall_result=f"Container {name} restarted successfully",
                total_latency_ms=duration,
            )
        return result

    @app.get("/api/containers/{name}/logs")
    def api_container_logs(name: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        tail = int(request.query_params.get("tail", 100))
        scanner = app.state.services.docker_scanner
        result = scanner.get_container_logs(name, tail=tail)
        if result.get("status") == "error":
            return Response(
                content=json.dumps(result), status_code=404, media_type="application/json"
            )
        return result

    @app.get("/api/containers/{name}/inspect")
    def api_container_inspect(name: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        try:
            import docker

            client = docker.from_env(timeout=5)
            container = client.containers.get(name)
            attrs = container.attrs
            return {"status": "ok", "container": name, "inspect": attrs}
        except docker.errors.NotFound:
            return Response(
                content=json.dumps({"status": "error", "message": "Container not found"}),
                status_code=404,
                media_type="application/json",
            )
        except docker.errors.DockerException as exc:
            get_logger(__name__).warning("Docker inspect error: %s", exc)
            return Response(
                content=json.dumps({"status": "error", "message": "Container inspection failed"}),
                status_code=503,
                media_type="application/json",
            )

    @app.get("/api/observability")
    def api_observability(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        from src.observability import get_tracker

        return get_tracker().get_summary()

    # ---- Operator: monitoring targets ----
    @app.post("/api/monitoring-targets")
    async def api_create_monitoring_target(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
            target = repo.create_monitoring_target(
                payload, actor=user.email if user else "anonymous"
            )
            run_monitoring_once()
            return target
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.put("/api/monitoring-targets/{target_id}")
    async def api_update_monitoring_target(target_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
            target = repo.update_monitoring_target(
                target_id, payload, actor=user.email if user else "anonymous"
            )
            if target is None:
                return Response(content="Monitoring target not found", status_code=404)
            run_monitoring_once()
            return target
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.delete("/api/monitoring-targets/{target_id}")
    def api_delete_monitoring_target(target_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        deleted = repo.delete_monitoring_target(
            target_id, actor=user.email if user else "anonymous"
        )
        if not deleted:
            return Response(content="Monitoring target not found", status_code=404)
        return {"status": "ok"}

    @app.post("/api/monitoring-targets/{target_id}/run")
    def api_run_monitoring_target(target_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        engine = getattr(app.state.services, "monitoring_engine", None)
        if engine is None:
            return Response(content="Monitoring engine unavailable", status_code=503)
        result = engine.run_target(target_id, actor=user.email if user else "anonymous")
        if result is None:
            return Response(content="Monitoring target not found", status_code=404)
        return result

    # ---- Operator: notification channels ----
    @app.get("/api/notification-channels")
    def api_list_notification_channels(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"channels": [], "count": 0}
        channels = repo.list_notification_channels()
        return {"channels": channels, "count": len(channels)}

    @app.get("/api/notification-channels/{channel_id}")
    def api_get_notification_channel(channel_id: int, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        channel = repo.get_notification_channel(channel_id)
        if channel is None:
            return Response(content="Notification channel not found", status_code=404)
        return channel

    @app.post("/api/notification-channels")
    async def api_create_notification_channel(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
            return repo.create_notification_channel(
                payload, actor=user.email if user else "anonymous"
            )
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.put("/api/notification-channels/{channel_id}")
    async def api_update_notification_channel(channel_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
            channel = repo.update_notification_channel(
                channel_id, payload, actor=user.email if user else "anonymous"
            )
            if channel is None:
                return Response(content="Notification channel not found", status_code=404)
            return channel
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.delete("/api/notification-channels/{channel_id}")
    def api_delete_notification_channel(channel_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        deleted = repo.delete_notification_channel(
            channel_id, actor=user.email if user else "anonymous"
        )
        if not deleted:
            return Response(content="Notification channel not found", status_code=404)
        return {"status": "ok"}

    @app.post("/api/notification-channels/test/{channel_type}")
    async def api_test_notification_channel(channel_type: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        channel_type = channel_type.lower()
        repo = app.state.services.platform_repository
        test_message = "This is a test notification from AegisNex."
        result = {"status": "error", "message": "Unsupported channel type or no channel configured"}
        if repo is not None:
            channels = repo.list_notification_channels()
            matches = [
                c for c in channels if str(c.get("channel_type", "")).lower() == channel_type
            ]
            if matches:
                config = matches[0].get("config", {})
                return await _send_test_notification(channel_type, config, test_message)
        try:
            config_obj = Config.load()
            if channel_type == "email" and config_obj.smtp.enabled:
                return await _send_test_notification(
                    "email",
                    {
                        "host": config_obj.smtp.host,
                        "port": config_obj.smtp.port,
                        "username": config_obj.smtp.username,
                        "password": config_obj.smtp.password,
                        "recipient": config_obj.smtp.recipient,
                        "sender": config_obj.smtp.username,
                    },
                    test_message,
                )
            if channel_type == "slack" and config_obj.notifications.slack.enabled:
                return await _send_test_notification(
                    "slack",
                    {"webhook_url": config_obj.notifications.slack.webhook_url},
                    test_message,
                )
            if channel_type == "discord" and config_obj.notifications.discord.enabled:
                return await _send_test_notification(
                    "discord",
                    {"webhook_url": config_obj.notifications.discord.webhook_url},
                    test_message,
                )
        except Exception:
            pass
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous",
                "test_notification",
                "notification_channel",
                channel_type,
                {},
            )
        return result

    async def _send_test_notification(
        channel_type: str, config: dict[str, Any], test_message: str
    ) -> Any:
        if channel_type == "email":
            try:
                from src.notifications.email import EmailProvider

                provider = EmailProvider(
                    smtp_host=str(config.get("host", "")),
                    smtp_port=int(config.get("port", 587)),
                    username=str(config.get("username", "")),
                    password=str(config.get("password", "")),
                    recipient=str(config.get("recipient", "")),
                    sender=str(config.get("sender", config.get("username", ""))),
                    subject="AegisNex Test Notification",
                    enabled=True,
                    retry_attempts=1,
                    timeout_seconds=10,
                )
                nr = provider._send_with_retries(test_message)
                return {"status": nr.status, "message": nr.message or "Test sent"}
            except Exception as exc:
                return {"status": "error", "message": str(exc)}
        elif channel_type in ("slack", "discord"):
            try:
                webhook_url = str(config.get("webhook_url", ""))
                if not webhook_url:
                    return {"status": "error", "message": "Webhook URL not configured"}
                import json as _json
                from urllib.request import Request as _Request
                from urllib.request import urlopen as _urlopen

                payload = _json.dumps(
                    {"text": test_message} if channel_type == "slack" else {"content": test_message}
                ).encode("utf-8")
                req = _Request(
                    webhook_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with _urlopen(req, timeout=10):
                    return {"status": "ok", "message": "Test sent"}
            except Exception as exc:
                return {"status": "error", "message": str(exc)}
        return {"status": "error", "message": "Unsupported channel type"}

    # ---- Operator: settings ----
    @app.put("/api/settings")
    async def api_update_settings(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
            settings = repo.update_settings(payload)
            repo.record_audit_log(
                user.email, "update", "settings", "all", {"keys": list(payload.keys())}
            )
            return {"settings": settings, "status": "ok"}
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    # ---- Admin: incident deletion ----
    @app.delete("/api/incidents/{incident_id}")
    def api_delete_incident(incident_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        deleted = repo.delete_incident(incident_id)
        if not deleted:
            try:
                app.state.services.incident_manager.delete_incident(incident_id)
            except KeyError:
                return Response(content="Incident not found", status_code=404)
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous", "delete", "incident", incident_id, {}
            )
        return {"status": "ok"}

    # ---- Admin: user management ----
    @app.get("/api/users")
    def api_list_users(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"users": [], "count": 0}
        rows = repo.fetch_all("users")
        sanitized = []
        for row in rows:
            sanitized.append(
                {
                    "id": row.get("id"),
                    "email": row.get("email"),
                    "role": row.get("role", "viewer"),
                    "is_active": bool(row.get("is_active", 0)),
                    "is_superuser": bool(row.get("is_superuser", 0)),
                    "is_verified": bool(row.get("is_verified", 0)),
                    "created_at": row.get("created_at"),
                }
            )
        return {"users": sanitized, "count": len(sanitized)}

    @app.put("/api/users/{user_id}/role")
    def api_update_user_role(user_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        from fastapi import HTTPException

        if user.role != Role.SUPER_ADMIN.value:
            raise HTTPException(status_code=403, detail="Only super_admin can change user roles")
        role = request.query_params.get("role", "")
        normalized_role = Role.from_str(role).value
        if role not in Role.valid_roles() and normalized_role not in Role.valid_roles():
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role. Must be one of: {', '.join(Role.valid_roles())}",
            )
        store = app.state.auth_manager.user_store
        try:
            with store._connect() as conn:
                conn.execute("UPDATE users SET role = ? WHERE id = ?", (normalized_role, user_id))
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to update user role") from None
        app.state.services.platform_repository.record_audit_log(
            user.email, "update_role", "user", str(user_id), {"role": normalized_role}
        )
        return {"status": "ok", "user_id": user_id, "role": normalized_role}

    @app.post("/api/users/{user_id}/deactivate")
    def api_deactivate_user(user_id: int, request: FastAPIRequest) -> Any:
        admin_user = require_role(*ADMIN_ROLES)(request)
        store = app.state.auth_manager.user_store
        target = store.get_user_by_id(user_id)
        if target is None:
            return Response(content="User not found", status_code=404)
        if target.is_superuser:
            return Response(content="Cannot deactivate superuser", status_code=400)
        store.deactivate_user(user_id)
        app.state.auth_manager.blacklist.revoke_all_for_user(user_id, app.state.auth_manager)
        app.state.services.platform_repository.record_audit_log(
            admin_user.email, "deactivate", "user", str(user_id), {}
        )
        return {"status": "ok"}

    # ---- Admin: API keys ----
    @app.get("/api/api-keys")
    def api_list_api_keys(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"keys": [], "count": 0}
        keys = repo.list_api_keys()
        sanitized = []
        for k in keys:
            raw_scopes = k.get("scopes") or '["*"]'
            try:
                scopes = json.loads(raw_scopes) if isinstance(raw_scopes, str) else raw_scopes
            except json.JSONDecodeError:
                scopes = ["*"]
            if not isinstance(scopes, list):
                scopes = ["*"]
            sanitized.append(
                {
                    "id": k.get("id"),
                    "name": k.get("name"),
                    "key_prefix": k.get("key_prefix"),
                    "role": k.get("role", "viewer"),
                    "scopes": scopes,
                    "org_id": k.get("org_id"),
                    "expires_at": k.get("expires_at"),
                    "revoked_at": k.get("revoked_at"),
                    "is_active": bool(k.get("is_active", False)),
                    "created_at": k.get("created_at"),
                    "last_used_at": k.get("last_used_at"),
                    "request_count": k.get("request_count", 0),
                }
            )
        return {"keys": sanitized, "count": len(sanitized)}

    @app.post("/api/api-keys")
    async def api_create_api_key(request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        name = str(payload.get("name", "")).strip()
        if not name:
            return Response(content="name is required", status_code=400)
        role = str(payload.get("role", "read_only")).strip().lower()
        normalized_role = Role.from_str(role).value
        if normalized_role == Role.SUPER_ADMIN.value and user.role != Role.SUPER_ADMIN.value:
            return Response(
                content="Only super_admin can create super_admin API keys", status_code=403
            )
        scopes = payload.get("scopes", ["commandmesh:chat"])
        if isinstance(scopes, str):
            scopes = [scope.strip() for scope in scopes.split(",") if scope.strip()]
        if not isinstance(scopes, list) or not scopes:
            scopes = ["commandmesh:chat"]
        normalized_scopes = [str(scope).strip() for scope in scopes if str(scope).strip()]
        if "*" in normalized_scopes and user.role != "super_admin":
            return Response(
                content="Only super_admin can create wildcard API keys", status_code=403
            )
        org_id_value = payload.get("org_id")
        org_id = int(org_id_value) if org_id_value not in (None, "") else None
        expires_at = str(payload.get("expires_at", "")).strip() or None
        from src.auth import generate_api_key

        full_key, key_hash, key_prefix = generate_api_key()
        repo.create_api_key(
            name,
            key_hash,
            key_prefix,
            normalized_role,
            actor=user.email,
            scopes=normalized_scopes,
            org_id=org_id,
            expires_at=expires_at,
        )
        return {
            "name": name,
            "api_key": full_key,
            "key_prefix": key_prefix,
            "role": normalized_role,
            "scopes": normalized_scopes,
            "org_id": org_id,
            "expires_at": expires_at,
        }

    @app.put("/api/api-keys/{key_id}")
    async def api_update_api_key(key_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        requested_scopes = payload.get("scopes")
        if requested_scopes is not None:
            parsed_scopes = requested_scopes
            if isinstance(parsed_scopes, str):
                parsed_scopes = [
                    scope.strip() for scope in parsed_scopes.split(",") if scope.strip()
                ]
            if isinstance(parsed_scopes, list) and "*" in [
                str(scope).strip() for scope in parsed_scopes
            ]:
                if user.role != "super_admin":
                    return Response(
                        content="Only super_admin can assign wildcard API key scope",
                        status_code=403,
                    )
        result = repo.update_api_key(key_id, payload, actor=user.email)
        if result is None:
            return Response(content="API key not found", status_code=404)
        return result

    @app.delete("/api/api-keys/{key_id}")
    def api_delete_api_key(key_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        deleted = repo.delete_api_key(key_id, actor=user.email)
        if not deleted:
            return Response(content="API key not found", status_code=404)
        return {"status": "ok"}

    # ---- Admin: alert rules ----
    @app.get("/api/alert-rules")
    def api_list_alert_rules(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"rules": [], "count": 0}
        rules = repo.list_alert_rules()
        return {"rules": rules, "count": len(rules)}

    @app.post("/api/alert-rules")
    async def api_create_alert_rule(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
            return repo.create_alert_rule(payload, actor=user.email)
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.put("/api/alert-rules/{rule_id}")
    async def api_update_alert_rule(rule_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
            rule = repo.update_alert_rule(rule_id, payload, actor=user.email)
            if rule is None:
                return Response(content="Alert rule not found", status_code=404)
            return rule
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.delete("/api/alert-rules/{rule_id}")
    def api_delete_alert_rule(rule_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        deleted = repo.delete_alert_rule(rule_id, actor=user.email)
        if not deleted:
            return Response(content="Alert rule not found", status_code=404)
        return {"status": "ok"}

    # ---- Enterprise: Invites ----
    @app.post("/api/invites")
    async def api_create_invite(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        email = str(payload.get("email", "")).strip().lower()
        role = str(payload.get("role", "read_only")).strip().lower()
        if not email:
            return Response(content="email is required", status_code=400)
        normalized_role = Role.from_str(role).value
        if normalized_role == Role.SUPER_ADMIN.value and user.role != Role.SUPER_ADMIN.value:
            return Response(
                content="Only super_admin can invite super_admin users", status_code=403
            )
        token = secrets.token_urlsafe(32)
        org_id = payload.get("org_id")
        invite = repo.create_invite(
            email=email, token=token, role=normalized_role, invited_by=user.email, org_id=org_id
        )
        return {"invite": invite, "invite_url": f"/accept-invite?token={token}"}

    @app.get("/api/invites")
    def api_list_invites(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"invites": [], "count": 0}
        invites = repo.list_invites()
        return {"invites": invites, "count": len(invites)}

    @app.post("/api/invites/accept")
    async def api_accept_invite(request: FastAPIRequest) -> Any:
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        token = str(payload.get("token", "")).strip()
        password = str(payload.get("password", "")).strip()
        if not token or not password:
            return Response(content="token and password are required", status_code=400)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        invite = repo.get_invite_by_token(token)
        if invite is None:
            return Response(content="Invalid or expired invite token", status_code=404)
        auth_mgr: AuthManager = request.app.state.auth_manager
        try:
            user, access_token, refresh_token = auth_mgr.register(invite["email"], password)
            from src.auth import Role

            normalized_role = Role.from_str(invite.get("role", "read_only")).value
            with auth_mgr.user_store._connect() as conn:
                conn.execute("UPDATE users SET role = ? WHERE id = ?", (normalized_role, user.id))
            repo.accept_invite(token)
            repo.record_audit_log(
                user.email, "accept_invite", "user", user.email, {"invited_role": normalized_role}
            )
            response = Response(
                content=json.dumps(
                    {
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "token_type": "bearer",
                    }
                ),
                media_type="application/json",
            )
            _set_auth_cookie(response, access_token, auth_mgr.token_ttl_seconds)
            return response
        except AuthError as exc:
            return Response(content=str(exc), status_code=400)

    # ---- Enterprise: Password Reset ----
    @app.post("/api/password-reset/request")
    async def api_request_password_reset(request: FastAPIRequest) -> Any:
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        email = str(payload.get("email", "")).strip().lower()
        if not email:
            return Response(content="email is required", status_code=400)
        auth_mgr: AuthManager = request.app.state.auth_manager
        user = auth_mgr.user_store.get_user_by_email(email)
        repo = app.state.services.platform_repository
        if user is None or repo is None:
            return {"status": "ok", "message": "If the email exists, a reset link has been sent"}
        token = secrets.token_urlsafe(32)
        repo.create_password_reset(user.id, token)
        repo.record_audit_log("system", "request_password_reset", "user", email, {})
        return {"status": "ok", "message": "If the email exists, a reset link has been sent"}

    @app.post("/api/password-reset/confirm")
    async def api_confirm_password_reset(request: FastAPIRequest) -> Any:
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        token = str(payload.get("token", "")).strip()
        new_password = str(payload.get("password", "")).strip()
        if not token or not new_password:
            return Response(content="token and password are required", status_code=400)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        reset = repo.get_password_reset_by_token(token)
        if reset is None:
            return Response(content="Invalid or expired reset token", status_code=404)
        auth_mgr: AuthManager = request.app.state.auth_manager
        try:
            auth_mgr.user_store.update_password(reset["user_id"], new_password)
        except AuthError as exc:
            return Response(content=str(exc), status_code=400)
        repo.use_password_reset(token)
        repo.record_audit_log("system", "confirm_password_reset", "user", str(reset["user_id"]), {})
        return {"status": "ok", "message": "Password has been reset successfully"}

    # ---- Enterprise: Secrets Management ----
    @app.get("/api/secrets")
    def api_list_secrets(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*OPERATOR_ROLES)(request)
        from src.secrets import SecretManager

        mgr = SecretManager(repo=app.state.services.platform_repository)
        secrets = mgr.list_secrets()
        return {"secrets": secrets, "count": len(secrets)}

    @app.post("/api/secrets")
    async def api_create_secret(request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        name = str(payload.get("name", "")).strip()
        value = str(payload.get("value", "")).strip()
        category = str(payload.get("category", "generic")).strip().lower()
        if not name or not value:
            return Response(content="name and value are required", status_code=400)
        from src.secrets import SecretManager

        mgr = SecretManager(repo=repo)
        result = mgr.store_secret(name, value, category, actor=user.email)
        return {"status": "ok", "secret": result}

    @app.delete("/api/secrets/{name}")
    def api_delete_secret(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        from src.secrets import SecretManager

        mgr = SecretManager(repo=repo)
        mgr.delete_secret(name, actor=user.email)
        return {"status": "ok"}

    @app.get("/api/secrets/{name}")
    def api_get_secret(name: str, request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        meta = repo.get_secret_metadata(name)
        if meta is None:
            return Response(content="Secret not found", status_code=404)
        return meta

    # ---- Enterprise: Enhanced Audit Logs ----
    @app.get("/api/audit-logs/filter")
    def api_audit_logs_filtered(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*AUDITOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"logs": [], "count": 0}
        limit = int(request.query_params.get("limit", 100))
        offset = int(request.query_params.get("offset", 0))
        actor = request.query_params.get("actor") or None
        action = request.query_params.get("action") or None
        resource_type = request.query_params.get("resource_type") or None
        execution_id = request.query_params.get("execution_id") or None
        limit = max(1, min(limit, 1000))
        logs = repo.list_audit_logs_enhanced(
            limit=limit,
            offset=offset,
            actor_filter=actor,
            action_filter=action,
            resource_type_filter=resource_type,
            execution_id_filter=execution_id,
        )
        return {"logs": logs, "count": len(logs), "limit": limit, "offset": offset}

    # ---- Enterprise: Approval Workflows ----
    @app.get("/api/approvals")
    def api_list_approvals(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"approvals": [], "count": 0}
        status = request.query_params.get("status") or None
        limit = int(request.query_params.get("limit", 50))
        approvals = [
            _normalize_approval_row(a)
            for a in repo.list_approval_requests(status=status, limit=limit)
        ]
        return {"approvals": approvals, "count": len(approvals)}

    @app.post("/api/approvals/{approval_id}/respond")
    async def api_respond_approval(approval_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            raise HTTPException(status_code=503, detail="Platform database unavailable")
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None
        decision = str(payload.get("decision", "")).strip().lower()
        if decision not in ("approved", "rejected"):
            raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")
        comment = str(payload.get("comment", "")).strip()

        existing = repo.get_approval_request(approval_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Approval request not found")
        if existing.get("status") != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Approval request already {existing.get('status')}; decisions are final.",
            )

        result = repo.respond_approval(
            approval_id, decision, reviewed_by=user.email, comment=comment
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Approval request not found")

        # Persist the human decision, synchronize linked governance/incident
        # state, and execute only the explicitly approved diagnostics-only
        # plan. A linkage failure must not undo the decision already persisted.
        try:
            details = result.get("details")
            if isinstance(details, str):
                details = json.loads(details) if details else {}
            details = details or {}
            governance_action_ids = details.get("governance_action_ids") or []
            if governance_action_ids:
                gov = governance_manager()
                tenant = governance_tenant_id(request)
                new_verdict = "allowed" if decision == "approved" else "denied"
                for gov_action_id in governance_action_ids:
                    gov.update_action(gov_action_id, tenant_id=tenant, policy_verdict=new_verdict)
            linked_incident_id = details.get("incident_id")
            if linked_incident_id:
                with suppress(KeyError):
                    app.state.services.incident_manager.record_remediation_decision(
                        linked_incident_id,
                        decision,
                        reviewed_by=user.email,
                    )
                if (
                    decision == "approved"
                    and result.get("request_type") == "incident_diagnostic_remediation"
                ):
                    _execute_approved_diagnostics(
                        app.state.services,
                        str(linked_incident_id),
                        approval_id,
                        user.email,
                        [str(action) for action in (details.get("actions") or [])],
                    )
        except Exception:
            logger.exception("approval.respond linkage sync failed approval_id=%s", approval_id)

        logger.info(
            "approval.respond succeeded approval_id=%s decision=%s reviewed_by=%s",
            approval_id,
            decision,
            user.email,
        )
        return _normalize_approval_row(result)

    # ---- Enterprise: Policy Management ----
    @app.post("/api/policies")
    async def api_create_policy(request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        name = str(payload.get("name", "")).strip()
        if not name:
            return Response(content="name is required", status_code=400)
        repo.save_policy(payload)
        repo.record_audit_log(user.email, "create_policy", "policy", name, payload)
        return {"status": "ok", "policy": repo.get_policy_by_name(name)}

    @app.put("/api/policies/{name}")
    async def api_update_policy(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        existing = repo.get_policy_by_name(name)
        if existing is None:
            return Response(content="Policy not found", status_code=404)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        merged = dict(existing)
        merged.update({k: v for k, v in payload.items() if v is not None})
        repo.save_policy(merged)
        repo.record_audit_log(user.email, "update_policy", "policy", name, payload)
        return {"status": "ok", "policy": repo.get_policy_by_name(name)}

    @app.delete("/api/policies/{name}")
    def api_delete_policy(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        existing = repo.get_policy_by_name(name)
        if existing is None:
            return Response(content="Policy not found", status_code=404)
        repo.delete_policy(name)
        repo.record_audit_log(user.email, "delete_policy", "policy", name, {})
        return {"status": "ok"}

    @app.get("/api/policies")
    def api_list_policies(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"policies": [], "count": 0}
        policies = repo.list_policies()
        return {"policies": policies, "count": len(policies)}

    # ---- Enterprise: System Administration ----
    @app.get("/api/admin/diagnostics")
    def api_admin_diagnostics(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        diagnostics: dict[str, Any] = {
            "timestamp": utc_now(),
            "database": repo.health_check() if repo else {"status": "unavailable"},
            "system": {},
            "queues": {},
            "workers": {},
            "storage": {},
        }
        try:
            import psutil

            diagnostics["system"] = {
                "cpu_percent": psutil.cpu_percent(interval=0.5),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage("/").percent,
                "uptime_seconds": int(time.time() - psutil.boot_time()),
            }
        except Exception:
            pass
        try:
            import docker

            client = docker.from_env(timeout=3)
            info = client.info()
            diagnostics["docker"] = {
                "containers_total": info.get("Containers", 0),
                "containers_running": info.get("ContainersRunning", 0),
                "containers_stopped": info.get("ContainersStopped", 0),
                "version": info.get("ServerVersion", "unknown"),
            }
        except Exception:
            diagnostics["docker"] = {"status": "unavailable"}
        if repo:
            try:
                tables = repo.table_names()
                diagnostics["storage"]["tables"] = sorted(tables)
                diagnostics["storage"]["table_count"] = len(tables)
            except Exception:
                pass
        return diagnostics

    @app.get("/api/admin/health")
    def api_admin_health(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        checks: dict[str, Any] = {
            "timestamp": utc_now(),
            "database": repo.health_check() if repo else {"status": "unavailable"},
        }
        try:
            import docker

            client = docker.from_env(timeout=3)
            checks["docker"] = {"status": "connected", "ping": client.ping()}
        except Exception:
            checks["docker"] = {"status": "disconnected"}
        try:
            import psutil

            checks["disk"] = {
                "status": "ok" if psutil.disk_usage("/").percent < 90 else "warning",
                "usage_percent": psutil.disk_usage("/").percent,
            }
            checks["memory"] = {
                "status": "ok" if psutil.virtual_memory().percent < 90 else "warning",
                "usage_percent": psutil.virtual_memory().percent,
            }
        except Exception:
            pass
        return checks

    # ---- Enterprise: Backup & Restore ----
    @app.post("/api/backup/export")
    async def api_backup_export(request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        tables = payload.get("tables")
        include_knowledge = bool(payload.get("include_knowledge", True))
        label = str(payload.get("label", "")).strip()
        from src.backup import BackupManager

        bm = BackupManager(repo=repo)
        result = bm.export_backup(tables=tables, include_knowledge=include_knowledge, label=label)
        if repo:
            repo.save_backup_record(
                file_path=result.get("file_path", ""),
                file_size_bytes=result.get("file_size_bytes", 0),
                label=label,
                tables_included=list(result.get("tables", {}).keys()),
                knowledge_included=include_knowledge,
                created_by=user.email,
            )
        return result

    @app.post("/api/backup/restore")
    async def api_backup_restore(request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        file_path = str(payload.get("file_path", "")).strip()
        if not file_path:
            return Response(content="file_path is required", status_code=400)
        tables = payload.get("tables")
        restore_knowledge = bool(payload.get("restore_knowledge", True))
        from src.backup import BackupManager

        bm = BackupManager(repo=repo)
        return bm.restore_backup(
            file_path, tables=tables, restore_knowledge=restore_knowledge, actor=user.email
        )

    @app.get("/api/backup/list")
    def api_backup_list(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        stored = repo.list_backup_records(limit=50) if repo else []
        from src.backup import BackupManager

        bm = BackupManager(repo=repo)
        files = bm.list_backups()
        return {
            "files": files,
            "records": stored,
            "file_count": len(files),
            "record_count": len(stored),
        }

    @app.delete("/api/backup/{file_path:path}")
    def api_backup_delete(file_path: str, request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        from src.backup import BackupManager

        bm = BackupManager(repo=repo)
        if not bm.delete_backup(file_path):
            return Response(content="Backup file not found", status_code=404)
        if repo:
            repo.record_audit_log(user.email, "delete_backup", "backup", file_path, {})
        return {"status": "ok"}

    # ---- Compliance API ----
    from src.compliance.engine import ComplianceEngine

    compliance_engine = ComplianceEngine(
        repo=getattr(app.state.services, "platform_repository", None)
    )
    app.state.compliance_engine = compliance_engine

    @app.get("/api/compliance/frameworks")
    def api_compliance_frameworks(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        engine: ComplianceEngine = request.app.state.compliance_engine
        return {"frameworks": engine.get_frameworks(), "count": len(engine.get_frameworks())}

    @app.get("/api/compliance/framework/{framework_id}")
    def api_compliance_framework(framework_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        engine: ComplianceEngine = request.app.state.compliance_engine
        fw = engine.get_framework(framework_id)
        if fw is None:
            return Response(content=f"Framework '{framework_id}' not found", status_code=404)
        return fw

    @app.post("/api/compliance/check/{framework_id}")
    def api_compliance_check(framework_id: str, request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        engine: ComplianceEngine = request.app.state.compliance_engine
        try:
            results = engine.run_check(framework_id)
            return {
                "framework_id": framework_id,
                "checked": len(results),
                "results": [engine._result_to_dict(r) for r in results],
                "summary": engine.get_summary(framework_id),
            }
        except ValueError as exc:
            return Response(content=str(exc), status_code=404)

    @app.get("/api/compliance/results/{framework_id}")
    def api_compliance_results(framework_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        engine: ComplianceEngine = request.app.state.compliance_engine
        results = engine.get_results(framework_id)
        return {
            "framework_id": framework_id,
            "results": results,
            "summary": engine.get_summary(framework_id),
            "count": len(results),
        }

    @app.get("/api/compliance/dashboard")
    def api_compliance_dashboard(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        engine: ComplianceEngine = request.app.state.compliance_engine
        fw_id = request.query_params.get("framework_id", "")
        return engine.get_dashboard(framework_id=fw_id)

    @app.get("/api/compliance/report/{framework_id}")
    def api_compliance_report(framework_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        from src.compliance.evidence import EvidenceCollector

        collector = EvidenceCollector(
            repo=getattr(request.app.state.services, "platform_repository", None)
        )
        report_format = request.query_params.get("format", "json")
        try:
            report = collector.generate_report(framework_id, format=report_format)
            media_type = {
                "json": "application/json",
                "html": "text/html",
                "markdown": "text/markdown",
            }.get(report_format, "application/json")
            return Response(
                content=report,
                media_type=media_type,
                headers={
                    "Content-Disposition": f"attachment; filename=compliance_{framework_id}.{report_format}"
                },
            )
        except ValueError as exc:
            return Response(content=str(exc), status_code=404)

    # ---- /metrics endpoint (protected) ----
    @app.get("/metrics")
    def metrics(request: FastAPIRequest) -> Any:
        metrics_token = os.getenv("AEGISNEX_METRICS_TOKEN", "")
        if metrics_token:
            auth_header = request.headers.get("Authorization", "")
            if not (auth_header == f"Bearer {metrics_token}" or _extract_token(request)):
                raise HTTPException(status_code=401, detail="Authentication required for /metrics")
        else:
            if not _extract_token(request):
                raise HTTPException(status_code=401, detail="Authentication required for /metrics")
        from src.prometheus_exporter import PrometheusExporter

        payload, content_type = PrometheusExporter(app.state.services).render()
        return Response(content=payload, media_type=content_type)

    # ---- AI Intelligence Engine ----
    _ai_pending_approvals: dict[str, dict[str, Any]] = {}

    # â”€â”€ Mission Control Integration Helpers â”€â”€

    def _mc_repo() -> Any:
        return getattr(app.state.services, "platform_repository", None)

    def _mc_user(request: FastAPIRequest) -> str:
        user = current_user(request)
        return getattr(user, "email", None) or "anonymous"

    def _mc_org(request: FastAPIRequest) -> str:
        user = current_user(request)
        tenant_manager = getattr(app.state, "tenant_manager", None)
        if user is not None and tenant_manager is not None and hasattr(user, "id") and user.id > 0:
            try:
                tenants = tenant_manager.get_user_tenants(user.id)
                if tenants:
                    return str(tenants[0].org_id)
            except Exception:
                pass
        api_key_org = getattr(request.state, "api_key_org_id", None)
        if api_key_org not in (None, ""):
            return str(api_key_org)
        return ""

    def _mc_agents(request: FastAPIRequest) -> list[str]:
        agents = []
        orch = getattr(app.state, "agent_orchestrator", None)
        if orch is not None:
            with suppress(Exception):
                agents = [a.get("name", a.get("id", "unknown")) for a in orch.list_agents()]
        return agents

    def _start_mc_execution(
        request: FastAPIRequest,
        execution_id: str,
        req_text: str,
        exec_type: str = "chat",
        audit_links: dict[str, str] | None = None,
    ) -> Any:
        from src.mission_control import create_execution

        repo = _mc_repo()
        if repo is None:
            return None
        try:
            return create_execution(
                repo=repo,
                execution_id=execution_id,
                request=req_text[:500],
                user=_mc_user(request),
                execution_type=exec_type,
                organization=_mc_org(request),
                agents=_mc_agents(request),
                audit_links=audit_links or {},
                metadata={"source_ip": request.client.host if request.client else ""},
            )
        except Exception as exc:
            get_logger(__name__).warning("MC create error: %s", exc)
            return None

    def _finish_mc_execution(
        execution: Any,
        status: str = "completed",
        error: str = "",
        overall_result: str = "",
        confidence: float = 0.0,
        total_latency_ms: float = 0.0,
        total_cost: float = 0.0,
    ) -> None:
        from src.mission_control import update_execution

        repo = _mc_repo()
        if repo is None or execution is None:
            return
        try:
            execution.current_status = status
            execution.error = error or execution.error
            execution.overall_result = overall_result or execution.overall_result
            execution.confidence = confidence or execution.confidence
            execution.total_latency_ms = total_latency_ms or execution.total_latency_ms
            execution.total_cost = total_cost or execution.total_cost
            update_execution(repo, execution)
            _broadcast_mc_update(repo)
        except Exception as exc:
            get_logger(__name__).warning("MC finish error: %s", exc)

    def _mc_complete_stage(
        execution: Any,
        stage_id: str,
        status: str = "completed",
        broadcast: bool = True,
        **kw: Any,
    ) -> None:
        from src.mission_control import complete_stage, update_execution

        repo = _mc_repo()
        if repo is None or execution is None:
            return
        try:
            complete_stage(execution, stage_id, status=status, **kw)
            update_execution(repo, execution)
            if broadcast:
                _broadcast_mc_update(repo)
        except Exception as exc:
            get_logger(__name__).warning("MC stage error: %s", exc)

    def _broadcast_mc_update(repo: Any) -> None:
        try:
            ws_mgr = getattr(app.state, "websocket_manager", None)
            if ws_mgr is not None:
                from src.mission_control import get_execution_stats

                stats = get_execution_stats(repo)
                asyncio.create_task(
                    ws_mgr.broadcast(
                        {"type": "execution_update", "stats": stats}, channel="mission_control"
                    )
                )
        except Exception:
            pass

    def _track_workforce_execution_in_mc(
        request: FastAPIRequest, agent: Any, execution: Any
    ) -> None:
        from src.ai_workforce import ExecutionResult
        from src.mission_control import create_execution

        repo = _mc_repo()
        if repo is None:
            return
        try:
            agent_label = str(getattr(agent, "name", "") or "").strip() or getattr(
                execution, "agent_id", ""
            )
            mc_exec = create_execution(
                repo=repo,
                execution_id=execution.execution_id,
                request=execution.task[:500],
                user=_mc_user(request),
                metadata={
                    "source": "ai_workforce_playground",
                    "workforce_execution_id": execution.execution_id,
                    "agent_id": execution.agent_id,
                    "agent_name": agent_label,
                    "workforce_status": execution.status,
                    **(execution.metadata or {}),
                },
                execution_type="agent_dispatch",
                organization=_mc_org(request),
                agents=[agent_label] if agent_label else [execution.agent_id],
                audit_links={
                    "workforce_execution": f"/api/workforce/agents/{execution.agent_id}/executions"
                },
            )
            mc_status = (
                "completed" if execution.status == ExecutionResult.SUCCESS.value else "failed"
            )
            stage_status = "completed" if mc_status == "completed" else "failed"
            _mc_complete_stage(
                mc_exec,
                "executor",
                status=stage_status,
                broadcast=False,
                latency_ms=execution.latency_ms,
                confidence=execution.confidence,
                model=getattr(agent, "model", ""),
                provider=getattr(agent, "provider", ""),
                estimated_cost=execution.cost,
                summary=(execution.response or execution.error or execution.task)[:300],
                connected_tools=execution.tools_used or [],
                inputs={
                    "task": execution.task,
                    "simulate": execution.metadata.get("mode") != "live",
                },
                outputs={"response": execution.response, "error": execution.error},
            )
            _finish_mc_execution(
                mc_exec,
                status=mc_status,
                error=execution.error,
                overall_result=execution.response,
                confidence=execution.confidence,
                total_latency_ms=execution.latency_ms,
                total_cost=execution.cost,
            )
        except Exception as exc:
            get_logger(__name__).warning("MC workforce tracking error: %s", exc, exc_info=True)

    WORKFORCE_GOVERNANCE_ACTION_TYPE = "workforce_playground_execution"

    def _ensure_workforce_agent_governance_registered(gov: Any, agent: Any, tenant_id: str) -> None:
        """Idempotently mirror a real Workforce agent's identity into GovernanceManager.

        Workforce (ai_workforce.py) and Governance (ai_governance.py) are
        separate registries backed by separate stores; nothing previously
        copied a Workforce agent into the governance agent registry, so its
        real executions had no governance/audit trail. Registered once, using
        the same agent_id, so the two systems can be correlated by ID -
        mirrors the existing _ensure_incident_ai_agent_registered pattern.
        """
        agent_id = getattr(agent, "agent_id", "")
        if not agent_id or gov.get_agent(agent_id, tenant_id=tenant_id) is not None:
            return
        from src.ai_governance import AIAgent

        gov.register_agent(
            AIAgent(
                agent_id=agent_id,
                name=getattr(agent, "name", "") or agent_id,
                agent_type=getattr(agent, "agent_type", "") or "general",
                description=getattr(agent, "description", ""),
                owner=getattr(agent, "owner", "") or "system",
                team=getattr(agent, "team", "") or "",
                provider=getattr(agent, "provider", "") or "unknown",
                model=getattr(agent, "model", "") or "unknown",
                daily_budget=getattr(agent, "daily_budget", 25.0),
                monthly_budget=getattr(agent, "monthly_budget", 750.0),
            ),
            tenant_id=tenant_id,
        )

    def _track_workforce_execution_in_governance(
        request: FastAPIRequest, agent: Any, execution: Any
    ) -> None:
        """Record a real Workforce Playground execution in Governance and Audit Logs.

        Best-effort and isolated per subsystem - a governance or audit
        failure must never break the actual playground response the operator
        is waiting on. The execution_id is reused as the deterministic
        governance action_id (UNIQUE(tenant_id, action_id) in agent_actions)
        and passed as record_audit_log's execution_id, so one execution can
        never create duplicate governance/audit rows and can always be
        correlated across Workforce/Mission Control/Governance/Audit by that
        one ID.
        """
        from src.ai_workforce import ExecutionResult

        agent_id = getattr(execution, "agent_id", "") or getattr(agent, "agent_id", "")
        tenant = governance_tenant_id(request)
        actor = _mc_user(request)
        is_success = execution.status == ExecutionResult.SUCCESS.value

        try:
            gov = governance_manager()
            with suppress(Exception):
                _ensure_workforce_agent_governance_registered(gov, agent, tenant)
            # likely a concurrent first-execution race; registration already exists or is in flight
            verdict, reason = gov.evaluate_policies(
                agent_id,
                WORKFORCE_GOVERNANCE_ACTION_TYPE,
                f"workforce_agent:{agent_id}",
                tenant_id=tenant,
            )
            from src.ai_governance import AgentAction

            gov.record_action(
                AgentAction(
                    action_id=f"workforce-{execution.execution_id}",
                    agent_id=agent_id,
                    action_type=WORKFORCE_GOVERNANCE_ACTION_TYPE,
                    action_summary=f"Playground execution for {getattr(agent, 'name', agent_id)}",
                    target_resource=f"workforce_agent:{agent_id}",
                    inputs=json.dumps(
                        {
                            "execution_id": execution.execution_id,
                            "simulate": execution.metadata.get("mode") != "live",
                        }
                    ),
                    outputs=json.dumps(
                        {
                            "status": execution.status,
                            "tools_used": execution.tools_used,
                        }
                    ),
                    reasoning=reason or "",
                    confidence_score=execution.confidence,
                    policy_verdict=verdict,
                    status="success" if is_success else "failed",
                    duration_ms=execution.latency_ms,
                ),
                tenant_id=tenant,
            )
        except Exception:
            get_logger(__name__).warning(
                "Workforce governance recording failed execution_id=%s",
                execution.execution_id,
                exc_info=True,
            )

        try:
            repo = app.state.services.platform_repository
            if repo is not None:
                # Only structural metadata - never the raw task prompt or the
                # raw LLM response, which may contain incident evidence or
                # other sensitive content that doesn't belong in audit logs.
                repo.record_audit_log(
                    actor=actor or "system",
                    action="workforce_playground_execution",
                    resource_type="workforce_agent",
                    resource_id=agent_id,
                    details={
                        "agent_name": getattr(agent, "name", ""),
                        "provider": getattr(agent, "provider", ""),
                        "model": getattr(agent, "model", ""),
                        "status": execution.status,
                        "latency_ms": execution.latency_ms,
                        "cost": execution.cost,
                        "confidence": execution.confidence,
                        "tools_used": execution.tools_used,
                    },
                    execution_id=execution.execution_id,
                )
        except Exception:
            get_logger(__name__).warning(
                "Workforce audit logging failed execution_id=%s",
                execution.execution_id,
                exc_info=True,
            )

    @app.post("/api/ai/chat")
    async def api_ai_chat(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        user_request = str(payload.get("request", "")).strip()
        if not user_request:
            return Response(content="request is required", status_code=400)
        mc_id = f"mc-chat-{uuid.uuid4().hex[:12]}"
        mc_exec = _start_mc_execution(request, mc_id, user_request, "chat")
        if mc_exec is not None:
            _mc_complete_stage(mc_exec, "planner", status="running")

        repo = getattr(app.state.services, "platform_repository", None)
        from src.intelligence.graph import run_chat
        from src.intelligence.history import save_workflow

        start_ts = time.time()
        try:
            result = run_chat(user_request, repo=repo)
        except Exception as exc:
            get_logger(__name__).warning("AI chat error: %s", exc)
            duration = (time.time() - start_ts) * 1000
            _finish_mc_execution(
                mc_exec, status="failed", error=str(exc), total_latency_ms=duration
            )
            return Response(
                content=json.dumps({"error": "AI chat processing failed"}),
                status_code=500,
                media_type="application/json",
            )

        duration = (time.time() - start_ts) * 1000
        confidence = result.get("confidence", 0.0)
        answer = result.get("answer", "")
        evidence = result.get("evidence", [])
        steps = result.get("steps", [])

        if mc_exec is not None:
            _mc_complete_stage(
                mc_exec,
                "planner",
                status="completed",
                latency_ms=duration * 0.3,
                confidence=confidence,
                summary=user_request[:200],
                outputs={"plan_steps": len(steps)},
            )
            _mc_complete_stage(mc_exec, "knowledge", status="completed", evidence=evidence)
            _mc_complete_stage(mc_exec, "verifier", status="completed", confidence=confidence)
            _mc_complete_stage(
                mc_exec,
                "executor",
                status="completed",
                latency_ms=duration * 0.7,
                summary=answer[:200],
            )
            _finish_mc_execution(
                mc_exec,
                status="completed",
                overall_result=answer,
                confidence=confidence,
                total_latency_ms=duration,
                total_cost=result.get("execution_duration_ms", 0) * 0.00001,
            )

        if repo is not None:
            try:
                save_workflow(
                    repo=repo,
                    request=user_request,
                    objective=answer[:100],
                    result_text=answer,
                    confidence=confidence,
                    goal_achieved=result.get("goal_achieved", False),
                    steps=steps,
                    observations=result.get("observations", []),
                    corrections=result.get("corrections", []),
                    errors=result.get("errors", []),
                    evidence=evidence,
                    reasoning_summary=result.get("reasoning_summary", ""),
                    remaining_uncertainty=result.get("remaining_uncertainty", ""),
                    provider_used=result.get("provider_used", ""),
                    model_used=result.get("model_used", ""),
                    execution_duration_ms=duration,
                    tools_used=[s.get("node", "") for s in steps if isinstance(s, dict)],
                    plan_text=answer[:200],
                )
            except Exception as exc:
                get_logger(__name__).warning("Failed to save AI history: %s", exc)
        return result

    @app.post("/api/ai/analyze")
    async def api_ai_analyze(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        user_request = str(payload.get("request", "")).strip()
        if not user_request:
            return Response(content="request is required", status_code=400)
        mc_id = f"mc-analyze-{uuid.uuid4().hex[:12]}"
        mc_exec = _start_mc_execution(request, mc_id, user_request, "analyze")
        repo = getattr(app.state.services, "platform_repository", None)
        from src.intelligence.graph import run_analyze
        from src.intelligence.history import save_workflow

        start_ts = time.time()
        try:
            result = run_analyze(user_request, repo=repo)
        except Exception as exc:
            get_logger(__name__).warning("AI analyze error: %s", exc)
            duration = (time.time() - start_ts) * 1000
            _finish_mc_execution(
                mc_exec, status="failed", error=str(exc), total_latency_ms=duration
            )
            return Response(
                content=json.dumps({"error": "AI analysis failed"}),
                status_code=500,
                media_type="application/json",
            )

        duration = (time.time() - start_ts) * 1000
        confidence = result.get("confidence", 0.0)
        final_answer = result.get("final_answer", "")

        if mc_exec is not None:
            _mc_complete_stage(
                mc_exec,
                "planner",
                status="completed",
                latency_ms=duration * 0.2,
                confidence=confidence,
                outputs={"plan": result.get("plan", {})},
            )
            _mc_complete_stage(mc_exec, "verifier", status="completed", confidence=confidence)
            _mc_complete_stage(
                mc_exec,
                "executor",
                status="completed",
                latency_ms=duration * 0.8,
                summary=final_answer[:300],
            )
            _finish_mc_execution(
                mc_exec,
                status="completed",
                overall_result=final_answer,
                confidence=confidence,
                total_latency_ms=duration,
            )

        if repo is not None:
            try:
                save_workflow(
                    repo=repo,
                    request=user_request,
                    objective=result.get("objective", "")[:100],
                    result_text=final_answer,
                    confidence=confidence,
                    goal_achieved=result.get("goal_achieved", False),
                    steps=result.get("executed_steps", []),
                    observations=result.get("observations", []),
                    corrections=result.get("corrections", []),
                    errors=result.get("errors", []),
                    evidence=result.get("evidence", []),
                    reasoning_summary=result.get("reasoning_summary", ""),
                    remaining_uncertainty=result.get("remaining_uncertainty", ""),
                    provider_used=result.get("provider_used", ""),
                    model_used=result.get("model_used", ""),
                    execution_duration_ms=duration,
                    tools_used=result.get("current_plan", []),
                    plan_text=json.dumps(result.get("plan", {})),
                )
            except Exception as exc:
                get_logger(__name__).warning("Failed to save AI history: %s", exc)
        return result

    @app.post("/api/ai/plan")
    async def api_ai_plan(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        user_request = str(payload.get("request", "")).strip()
        if not user_request:
            return Response(content="request is required", status_code=400)
        mc_id = f"mc-plan-{uuid.uuid4().hex[:12]}"
        mc_exec = _start_mc_execution(request, mc_id, user_request, "plan")
        repo = getattr(app.state.services, "platform_repository", None)
        from src.intelligence.graph import run_plan

        start_ts = time.time()
        try:
            result = run_plan(user_request, repo=repo)
        except Exception as exc:
            get_logger(__name__).warning("AI plan error: %s", exc)
            duration = (time.time() - start_ts) * 1000
            _finish_mc_execution(
                mc_exec, status="failed", error=str(exc), total_latency_ms=duration
            )
            return Response(
                content=json.dumps({"error": "AI planning failed"}),
                status_code=500,
                media_type="application/json",
            )

        duration = (time.time() - start_ts) * 1000
        plan = result.get("plan", {})
        plan_text = json.dumps(plan)[:500] if plan else ""

        if mc_exec is not None:
            _mc_complete_stage(
                mc_exec,
                "planner",
                status="completed",
                latency_ms=duration,
                summary=plan_text,
                outputs={
                    "plan": plan,
                    "current_plan": result.get("current_plan", []),
                    "objective": result.get("objective", ""),
                },
            )
            _mc_complete_stage(mc_exec, "verifier", status="completed")
            _finish_mc_execution(
                mc_exec, status="completed", overall_result=plan_text, total_latency_ms=duration
            )
        return result

    # â”€â”€ Mission Control Routes â”€â”€

    @app.get("/api/mission-control/executions")
    def api_mc_executions(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        repo = _mc_repo()
        if repo is None:
            return {"executions": [], "count": 0, "total": 0, "limit": 50, "offset": 0}
        limit = max(1, min(int(request.query_params.get("limit", 50)), 200))
        offset = max(0, int(request.query_params.get("offset", 0)))
        status = request.query_params.get("status") or None
        search = request.query_params.get("search") or None
        user = request.query_params.get("user") or None
        exec_type = request.query_params.get("execution_type") or None
        org = request.query_params.get("organization") or None
        days = _query_int(request, "days")
        from src.mission_control import count_executions, list_executions

        try:
            executions = list_executions(
                repo,
                limit=limit,
                offset=offset,
                status=status,
                search=search,
                user=user,
                execution_type=exec_type,
                organization=org,
                days=days,
            )
            total = count_executions(
                repo,
                status=status,
                search=search,
                user=user,
                execution_type=exec_type,
                organization=org,
                days=days,
            )
            return {
                "executions": [e.to_dict() for e in executions],
                "count": len(executions),
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        except Exception as exc:
            get_logger(__name__).warning("MC list error: %s", exc)
            return {
                "executions": [],
                "count": 0,
                "total": 0,
                "limit": limit,
                "offset": offset,
                "error": str(exc),
            }

    @app.get("/api/mission-control/executions/{execution_id}")
    def api_mc_execution_detail(execution_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        repo = _mc_repo()
        if repo is None:
            return Response(
                content=json.dumps({"error": "No database"}),
                status_code=503,
                media_type="application/json",
            )
        from src.mission_control import get_execution, get_execution_stats

        try:
            execution = get_execution(repo, execution_id)
            if execution is None:
                return Response(
                    content=json.dumps({"error": "Execution not found"}),
                    status_code=404,
                    media_type="application/json",
                )
            stats = get_execution_stats(repo)
            return {"execution": execution.to_dict(), "stats": stats}
        except Exception as exc:
            return Response(
                content=json.dumps({"error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    @app.get("/api/mission-control/executions/{execution_id}/export")
    def api_mc_export(execution_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        repo = _mc_repo()
        if repo is None:
            return Response(content="No database", status_code=503)
        from src.mission_control import get_execution

        try:
            execution = get_execution(repo, execution_id)
            if execution is None:
                return Response(
                    content=json.dumps({"error": "Not found"}),
                    status_code=404,
                    media_type="application/json",
                )
            return Response(
                content=json.dumps(execution.to_dict(), indent=2),
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=execution-{execution_id}.json"
                },
            )
        except Exception as exc:
            return Response(
                content=json.dumps({"error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    @app.get("/api/mission-control/executions/{execution_id}/replay")
    def api_mc_replay(execution_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        repo = _mc_repo()
        if repo is None:
            return Response(
                content=json.dumps({"error": "No database"}),
                status_code=503,
                media_type="application/json",
            )
        from src.mission_control import get_execution

        try:
            execution = get_execution(repo, execution_id)
            if execution is None:
                return Response(
                    content=json.dumps({"error": "Execution not found"}),
                    status_code=404,
                    media_type="application/json",
                )
            return execution.replay_data()
        except Exception as exc:
            return Response(
                content=json.dumps({"error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    @app.get("/api/mission-control/stats")
    def api_mc_stats(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        repo = _mc_repo()
        if repo is None:
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "running": 0,
                "queued": 0,
                "avg_latency": 0,
                "avg_cost": 0,
                "avg_confidence": 0,
                "total_cost": 0,
                "type_count": 0,
                "user_count": 0,
            }
        from src.mission_control import get_execution_stats

        try:
            return get_execution_stats(repo)
        except Exception as exc:
            get_logger(__name__).warning("MC stats error: %s", exc)
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "running": 0,
                "queued": 0,
                "avg_latency": 0,
                "avg_cost": 0,
                "avg_confidence": 0,
                "total_cost": 0,
                "type_count": 0,
                "user_count": 0,
            }

    @app.get("/api/mission-control/stats/types")
    def api_mc_stats_types(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        repo = _mc_repo()
        if repo is None:
            return []
        from src.mission_control import get_execution_type_stats

        try:
            return get_execution_type_stats(repo)
        except Exception as exc:
            get_logger(__name__).warning("MC type stats error: %s", exc)
            return []

    @app.get("/api/mission-control/history")
    def api_mc_history(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        repo = _mc_repo()
        if repo is None:
            return {"executions": [], "count": 0, "total": 0}
        limit = max(1, min(int(request.query_params.get("limit", 100)), 500))
        offset = max(0, int(request.query_params.get("offset", 0)))
        days = _query_int(request, "days", 30) or 30
        exec_type = request.query_params.get("execution_type") or None
        from src.mission_control import count_executions, list_executions

        try:
            executions = list_executions(
                repo, limit=limit, offset=offset, days=days, execution_type=exec_type
            )
            total = count_executions(repo, days=days, execution_type=exec_type)
            return {
                "executions": [e.to_dict() for e in executions],
                "count": len(executions),
                "total": total,
            }
        except Exception as exc:
            return {"executions": [], "count": 0, "total": 0, "error": str(exc)}

    @app.post("/api/mission-control/track")
    async def api_mc_track(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        execution_id = str(payload.get("execution_id", "")).strip()
        req_text = str(payload.get("request", "")).strip()
        exec_type = str(payload.get("execution_type", "chat")).strip()
        if not execution_id:
            import uuid

            execution_id = f"mc-{exec_type}-{uuid.uuid4().hex[:12]}"
        mc_exec = _start_mc_execution(
            request, execution_id, req_text, exec_type, audit_links=payload.get("audit_links")
        )
        if mc_exec is not None:
            _mc_complete_stage(mc_exec, "planner", status="completed", summary=req_text[:200])
            _finish_mc_execution(
                mc_exec, status="completed", overall_result=payload.get("result", "")
            )
            return {"status": "ok", "execution_id": execution_id}
        return Response(
            content=json.dumps({"error": "Tracking failed"}),
            status_code=500,
            media_type="application/json",
        )

    @app.websocket("/ws/mission-control")
    async def mission_control_websocket(websocket: WebSocket) -> None:
        token = _websocket_token(websocket)
        if not token or app.state.auth_manager.get_user_from_token(token) is None:
            with suppress(Exception):
                await websocket.close(code=4001, reason="Authentication required")
            return
        manager = getattr(app.state, "websocket_manager", None)
        if manager is not None:
            await manager.connect(websocket, channel="mission_control")
        try:
            repo = _mc_repo()
            if repo is not None:
                from src.mission_control import get_execution_stats

                stats = get_execution_stats(repo)
                with suppress(Exception):
                    await websocket.send_json({"type": "mc_stats_update", "stats": stats})
            while True:
                try:
                    data = await websocket.receive_text()
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        with suppress(Exception):
                            await websocket.send_json({"type": "pong"})
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        finally:
            if manager is not None:
                manager.disconnect(websocket, channel="mission_control")

    # â”€â”€ Integrate MC into knowledge search â”€â”€

    _original_knowledge_search = None

    @app.get("/api/knowledge/search")
    def api_knowledge_search(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        query = request.query_params.get("q", "").strip()
        limit = int(request.query_params.get("limit", 10))
        limit = max(1, min(limit, 100))
        mc_id = f"mc-kb-{uuid.uuid4().hex[:12]}"

        repo_store: tuple = _get_knowledge_services()
        _, _, _indexer, retriever = repo_store

        if not query:
            mc_exec = _start_mc_execution(request, mc_id, "", "knowledge_search")
            if mc_exec is not None:
                _finish_mc_execution(
                    mc_exec, status="completed", overall_result="No query provided"
                )
            return {"results": [], "count": 0}

        mc_exec = _start_mc_execution(
            request,
            mc_id,
            f"Search: {query[:200]}",
            "knowledge_search",
            audit_links={"type": "knowledge_search", "query": query[:200]},
        )
        start_ts = time.time()
        try:
            doc_types_str = request.query_params.get("doc_types", "")
            if doc_types_str:
                doc_types = [t.strip() for t in doc_types_str.split(",") if t.strip()]
                results = retriever.retrieve_with_filters(query, doc_types=doc_types, limit=limit)
            else:
                results = retriever.retrieve(query, limit=limit)
            duration = (time.time() - start_ts) * 1000
            if mc_exec is not None:
                _mc_complete_stage(
                    mc_exec,
                    "knowledge",
                    status="completed",
                    latency_ms=duration,
                    summary=f"Found {len(results)} results",
                )
                _finish_mc_execution(
                    mc_exec,
                    status="completed",
                    overall_result=f"Found {len(results)} results",
                    total_latency_ms=duration,
                    confidence=0.9 if results else 0.5,
                )
            return {"results": results, "count": len(results), "query": query}
        except Exception as exc:
            duration = (time.time() - start_ts) * 1000
            if mc_exec is not None:
                _finish_mc_execution(
                    mc_exec, status="failed", error=str(exc), total_latency_ms=duration
                )
            return Response(
                content=json.dumps({"error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    @app.get("/api/ai/history")
    def api_ai_history(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is None:
            return {"history": [], "count": 0}
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))
        limit = max(1, min(limit, 100))
        from src.intelligence.history import get_history_count, list_history

        try:
            rows = list_history(repo, limit=limit, offset=offset)
            total = get_history_count(repo)
            return {"history": rows, "count": len(rows), "total": total}
        except Exception as exc:
            return {"history": [], "count": 0, "error": str(exc)}

    @app.get("/api/ai/workflows")
    def api_ai_workflows(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.intelligence.graph import get_workflows

            return get_workflows()
        except Exception as exc:
            return {"error": str(exc)}

    @app.get("/api/ai/executions")
    def api_ai_executions(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is None:
            return {"executions": [], "count": 0, "stats": {}}
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))
        limit = max(1, min(limit, 100))
        try:
            from src.intelligence.history import get_history_count, get_history_stats, list_history

            rows = list_history(repo, limit=limit, offset=offset)
            total = get_history_count(repo)
            stats = get_history_stats(repo)
            return {"executions": rows, "count": len(rows), "total": total, "stats": stats}
        except Exception as exc:
            return {"executions": [], "count": 0, "stats": {}, "error": str(exc)}

    @app.get("/api/ai/memory")
    def api_ai_memory(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        query = request.query_params.get("query", "")
        memory_type = request.query_params.get("type", "all")
        limit = int(request.query_params.get("limit", 10))
        try:
            import os

            from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore

            db_path = os.getenv("AEGIS_AI_MEMORY_DB", "ai_memory.db")
            store = SQLiteMemoryStore(db_path=db_path)
            if not query:
                if memory_type == "conversations":
                    entries = store.get_recent_conversations(limit)
                elif memory_type == "incidents":
                    entries = store.get_recent_incidents(limit)
                elif memory_type == "recommendations":
                    entries = store.get_recent_recommendations(limit)
                elif memory_type == "remediations":
                    entries = store.get_recent_remediations(limit)
                else:
                    entries = store.get_recent_conversations(limit)
                return {"entries": entries, "count": len(entries), "type": memory_type}
            if memory_type == "all":
                result = store.search_all(query, limit)
            elif memory_type == "conversations":
                result = store.search_conversations(query, limit)
            elif memory_type == "incidents":
                result = store.search_incidents(query, limit)
            elif memory_type == "recommendations":
                result = store.search_recommendations(query, limit)
            elif memory_type == "remediations":
                result = store.search_remediations(query, limit)
            else:
                result = store.search_all(query, limit)
            return {
                "entries": result.entries,
                "count": result.count,
                "total": result.total,
                "type": memory_type,
                "query": query,
            }
        except Exception as exc:
            return {"entries": [], "count": 0, "error": str(exc)}

    @app.get("/api/ai/tools")
    def api_ai_tools(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.intelligence.tools import list_tool_definitions

            definitions = list_tool_definitions()
            return {"tools": definitions, "count": len(definitions)}
        except Exception as exc:
            return {"tools": [], "count": 0, "error": str(exc)}

    # ---- Skills API ----

    _skill_engine: Any = None

    def _get_skill_engine() -> Any:
        nonlocal _skill_engine
        if _skill_engine is None:
            from src.skills.engine import create_default_engine

            _skill_engine = create_default_engine()
        return _skill_engine

    @app.get("/api/skills")
    def api_list_skills(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            engine = _get_skill_engine()
            return {"skills": engine.registry.list(), "count": engine.registry.count()}
        except Exception as exc:
            return {"skills": [], "count": 0, "error": str(exc)}

    @app.post("/api/skills/execute")
    async def api_execute_skill(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        skill_id = str(payload.get("skill_id", "")).strip()
        if not skill_id:
            return Response(content="skill_id is required", status_code=400)
        try:
            engine = _get_skill_engine()
            context = payload.get("context", {})
            repo = getattr(app.state.services, "platform_repository", None)
            context["repo"] = repo
            return await engine.execute_skill(skill_id, context)
        except Exception as exc:
            return Response(
                content=json.dumps({"status": "error", "error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    @app.post("/api/skills/auto-select")
    async def api_auto_select_skills(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        task = str(payload.get("task", "")).strip()
        if not task:
            return Response(content="task is required", status_code=400)
        try:
            engine = _get_skill_engine()
            matched = await engine.auto_select_skills(task)
            return {"skills": [s.to_dict() for s in matched], "count": len(matched)}
        except Exception as exc:
            return {"skills": [], "count": 0, "error": str(exc)}

    @app.post("/api/skills/pipeline")
    async def api_execute_pipeline(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        skill_ids = payload.get("skill_ids", [])
        if not isinstance(skill_ids, list) or not skill_ids:
            return Response(content="skill_ids must be a non-empty list", status_code=400)
        try:
            engine = _get_skill_engine()
            context = payload.get("context", {})
            repo = getattr(app.state.services, "platform_repository", None)
            context["repo"] = repo
            results = await engine.execute_pipeline(skill_ids, context)
            return {"results": results, "count": len(results)}
        except Exception as exc:
            return Response(
                content=json.dumps({"status": "error", "error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    @app.post("/api/ai/approve")
    async def api_ai_approve(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        approval_id = str(payload.get("approval_id", "")).strip()
        if not approval_id:
            return Response(content="approval_id is required", status_code=400)
        app.state._ai_pending_approvals[approval_id] = {
            "status": "approved",
            "approved_at": utc_now(),
        }
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous", "approve", "ai_approval", approval_id, {}
            )
        mc_id = f"mc-gov-approve-{uuid.uuid4().hex[:12]}"
        mc_exec = _start_mc_execution(
            request,
            mc_id,
            f"Approval: {approval_id}",
            "governance_approval",
            audit_links={"approval_id": approval_id, "decision": "approved"},
        )
        if mc_exec is not None:
            _mc_complete_stage(
                mc_exec, "policy", status="completed", summary=f"Approved {approval_id}"
            )
            _finish_mc_execution(
                mc_exec,
                status="completed",
                overall_result=f"Approval {approval_id} granted",
                confidence=1.0,
            )
        return {"status": "approved", "approval_id": approval_id}

    @app.post("/api/ai/reject")
    async def api_ai_reject(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        approval_id = str(payload.get("approval_id", "")).strip()
        if not approval_id:
            return Response(content="approval_id is required", status_code=400)
        app.state._ai_pending_approvals[approval_id] = {
            "status": "rejected",
            "rejected_at": utc_now(),
        }
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous", "reject", "ai_approval", approval_id, {}
            )
        mc_id = f"mc-gov-reject-{uuid.uuid4().hex[:12]}"
        mc_exec = _start_mc_execution(
            request,
            mc_id,
            f"Rejection: {approval_id}",
            "governance_approval",
            audit_links={"approval_id": approval_id, "decision": "rejected"},
        )
        if mc_exec is not None:
            _mc_complete_stage(
                mc_exec, "policy", status="completed", summary=f"Rejected {approval_id}"
            )
            _finish_mc_execution(
                mc_exec,
                status="completed",
                overall_result=f"Approval {approval_id} denied",
                confidence=1.0,
            )
        return {"status": "rejected", "approval_id": approval_id}

    @app.get("/api/ai/pending-approvals")
    def api_ai_pending_approvals(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        pending = {
            k: v for k, v in app.state._ai_pending_approvals.items() if v.get("status") == "pending"
        }
        return {"approvals": pending, "count": len(pending)}

    # ---- Sprint 9: Runbooks, Workflows, Timeline, Risk, Policies ----
    @app.get("/api/runbooks")
    def api_list_runbooks(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.intelligence.runbooks.registry import get_registry

            registry = get_registry()
            return {
                "runbooks": [r.to_dict() for r in registry.list_all()],
                "count": registry.count(),
            }
        except Exception as exc:
            return {"runbooks": [], "count": 0, "error": str(exc)}

    @app.post("/api/runbooks/execute")
    async def api_execute_runbook(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        runbook_name = str(payload.get("runbook", "")).strip()
        if not runbook_name:
            return Response(content="runbook is required", status_code=400)
        try:
            from src.intelligence.runbooks.engine import RunbookEngine
            from src.intelligence.runbooks.registry import get_registry

            registry = get_registry()
            engine = RunbookEngine(registry)
            return engine.execute(runbook_name)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @app.post("/api/workflows/start")
    async def api_start_workflow(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        workflow_name = str(payload.get("workflow", "")).strip()
        if not workflow_name:
            return Response(content="workflow is required", status_code=400)
        try:
            from src.intelligence.graph import run_workflow

            repo = getattr(app.state.services, "platform_repository", None)
            result = run_workflow(workflow_name, repo=repo)
            return {
                "status": "completed",
                "confidence": result.get("confidence", 0.0),
                "goal_achieved": result.get("goal_achieved", False),
                "workflow_triggered": result.get("workflow_triggered", ""),
                "runbook": result.get("current_runbook", ""),
            }
        except Exception as exc:
            return Response(
                content=json.dumps({"error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    @app.get("/api/workflows/history")
    def api_workflow_history(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is None:
            return {"history": [], "count": 0}
        limit = int(request.query_params.get("limit", 20))
        try:
            from src.intelligence.history import list_history

            rows = list_history(repo, limit=limit)
            return {"history": rows, "count": len(rows)}
        except Exception as exc:
            return {"history": [], "count": 0, "error": str(exc)}

    @app.get("/api/ai/timeline")
    def api_ai_timeline(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            import os

            from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore

            db_path = os.getenv("AEGIS_AI_MEMORY_DB", "ai_memory.db")
            store = SQLiteMemoryStore(db_path=db_path)
            conversations = store.get_recent_conversations(limit=20)
            learnings = store.get_recent_learnings(limit=20)
            timeline = []
            for c in conversations:
                timeline.append(
                    {
                        "type": "conversation",
                        "timestamp": c.get("created_at", ""),
                        "summary": c.get("request", "")[:120],
                        "confidence": c.get("confidence", 0.0),
                        "goal_achieved": bool(c.get("goal_achieved", 0)),
                    }
                )
            for l in learnings:
                timeline.append(
                    {
                        "type": "learning",
                        "timestamp": l.get("created_at", ""),
                        "summary": l.get("root_cause", "")[:120],
                        "category": l.get("category", ""),
                        "severity": l.get("severity", "info"),
                    }
                )
            timeline.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
            return {"timeline": timeline[:50], "count": len(timeline[:50])}
        except Exception as exc:
            return {"timeline": [], "count": 0, "error": str(exc)}

    @app.get("/api/ai/policies")
    def api_ai_policies(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.intelligence.policy import PolicyEngine

            engine = PolicyEngine()
            return {"policies": engine.list_policies(), "count": len(engine.list_policies())}
        except Exception as exc:
            return {"policies": [], "count": 0, "error": str(exc)}

    @app.get("/api/ai/risk")
    def api_ai_risk(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        tool = request.query_params.get("tool", "")
        try:
            from src.intelligence.risk import RiskEngine

            engine = RiskEngine()
            if tool:
                assessment = engine.assess_tool(tool)
                return {"assessment": assessment.to_dict()}
            return {"message": "Specify ?tool=<name> for risk assessment"}
        except Exception as exc:
            return {"error": str(exc)}

    # ---- Knowledge Management ----

    def _get_knowledge_services() -> tuple:
        from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
        from src.intelligence.providers.factory import create_provider
        from src.intelligence.retrieval.chunker import SemanticChunker
        from src.intelligence.retrieval.embeddings import EmbeddingService
        from src.intelligence.retrieval.rag import RAGEngine
        from src.intelligence.retrieval.vector_store import SQLiteVectorStore
        from src.knowledge.indexer import KnowledgeIndexer
        from src.knowledge.retriever import KnowledgeRetriever

        mem_db = os.getenv("AEGIS_AI_MEMORY_DB", "ai_memory.db")
        store = SQLiteMemoryStore(db_path=mem_db)
        rag = RAGEngine()
        try:
            provider = create_provider()
            emb = EmbeddingService(provider)
        except Exception:
            emb = EmbeddingService()
        vec_db_path = (
            mem_db.replace(".db", "_vectors.db") if mem_db.endswith(".db") else mem_db + "_vectors"
        )
        vec_store = SQLiteVectorStore(vec_db_path)
        chunker = SemanticChunker(emb)
        indexer = KnowledgeIndexer(
            store=store, rag=rag, embedding_service=emb, vector_store=vec_store, chunker=chunker
        )
        retriever = KnowledgeRetriever(rag=rag, indexer=indexer)
        return store, rag, indexer, retriever

    @app.post("/api/knowledge/upload")
    async def api_knowledge_upload(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            form = await request.form()
            file = form.get("file")
            if file is None:
                return Response(content="No file provided", status_code=400)
            content_bytes = await file.read()
            filename = str(file.filename) if file.filename else "uploaded.md"
            filename = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)
            filename = filename.lstrip(".")
            temp_dir = BASE_DIR / "data" / "knowledge_uploads"
            temp_dir.mkdir(parents=True, exist_ok=True)
            dest = temp_dir / filename
            dest.write_bytes(content_bytes)
            _, _, indexer, _ = _get_knowledge_services()
            count = indexer.index_document(str(dest))
            return {
                "status": "ok",
                "document": filename,
                "chunks_indexed": count,
                "path": str(dest),
            }
        except Exception as exc:
            return Response(
                content=json.dumps({"error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    @app.post("/api/knowledge/index-directory")
    async def api_knowledge_index_directory(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        directory = str(payload.get("directory", "")).strip()
        if not directory:
            return Response(content="directory is required", status_code=400)
        if not os.path.isdir(directory):
            return Response(content=f"Directory not found: {directory}", status_code=404)
        _, _, indexer, _ = _get_knowledge_services()
        count = indexer.index_directory(directory)
        return {"status": "ok", "directory": directory, "total_chunks_indexed": count}

    @app.get("/api/knowledge/stats")
    def api_knowledge_stats(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        _, _, indexer, _ = _get_knowledge_services()
        stats = indexer.get_stats()
        return {"stats": stats}

    @app.delete("/api/knowledge/remove")
    def api_knowledge_remove(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        source = request.query_params.get("source", "").strip()
        if not source:
            return Response(content="source query parameter is required", status_code=400)
        _, _, indexer, _ = _get_knowledge_services()
        removed = indexer.remove_document(source)
        if not removed:
            return Response(content="Document not found", status_code=404)
        return {"status": "ok", "source": source}

    # ---- Approval ----

    @app.post("/api/approval/respond")
    async def api_approval_respond(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        approval_id = str(payload.get("approval_id", "")).strip()
        decision = str(payload.get("decision", "")).strip().lower()
        if not approval_id or decision not in ("approve", "reject"):
            return Response(
                content="approval_id and decision (approve/reject) are required", status_code=400
            )
        key = f"approval_{approval_id}"
        if key in app.state._ai_pending_approvals:
            app.state._ai_pending_approvals[key] = {"status": decision, "responded_at": utc_now()}
        status_text = "approved" if decision == "approve" else "rejected"
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(
                user.email if user else "anonymous", decision, "ai_approval", approval_id, {}
            )
        return {"status": status_text, "approval_id": approval_id}

    # ---- AI Governance / CommandMesh ----
    def governance_manager() -> Any:
        gov = getattr(app.state, "governance", None)
        if gov is None:
            from src.ai_governance import GovernanceManager

            gov = GovernanceManager("governance.db")
            app.state.governance = gov
        return gov

    def governance_tenant_id(request: FastAPIRequest) -> str:
        api_key_org_id = getattr(request.state, "api_key_org_id", None)
        if api_key_org_id not in (None, ""):
            return f"org:{api_key_org_id}"
        user = current_user(request)
        tenant_manager = getattr(app.state, "tenant_manager", None)
        if user is not None and tenant_manager is not None and user.id > 0:
            try:
                tenants = tenant_manager.get_user_tenants(user.id)
                if tenants:
                    return f"org:{tenants[0].org_id}"
            except Exception:
                pass
        return "default"

    @app.get("/api/governance/stats")
    def api_governance_stats(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        return governance_manager().get_agent_stats(tenant_id=governance_tenant_id(request))

    @app.get("/api/governance/agents")
    def api_governance_agents(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        gov = governance_manager()
        agents = [a.to_dict() for a in gov.list_agents(tenant_id=governance_tenant_id(request))]
        return {"agents": agents, "count": len(agents)}

    @app.get("/api/governance/agents/{agent_id}")
    def api_governance_agent(agent_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        agent = governance_manager().get_agent(agent_id, tenant_id=governance_tenant_id(request))
        if agent is None:
            return Response(
                content=json.dumps({"error": "Agent not found"}),
                status_code=404,
                media_type="application/json",
            )
        return agent.to_dict()

    @app.get("/api/governance/agents/{agent_id}/history")
    def api_governance_agent_history(agent_id: str, request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        limit = max(1, min(int(request.query_params.get("limit", 50)), 200))
        history = [
            a.to_dict()
            for a in governance_manager().get_agent_history(
                agent_id, limit=limit, tenant_id=governance_tenant_id(request)
            )
        ]
        return {"history": history, "count": len(history)}

    @app.get("/api/governance/agents/{agent_id}/policies")
    def api_governance_agent_policies(agent_id: str, request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        policies = [
            p.to_dict()
            for p in governance_manager().get_agent_policies(
                agent_id, tenant_id=governance_tenant_id(request)
            )
        ]
        return {"policies": policies, "count": len(policies)}

    @app.get("/api/governance/agents/{agent_id}/tools")
    def api_governance_agent_tools(agent_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        tools = governance_manager().get_agent_tools(
            agent_id, tenant_id=governance_tenant_id(request)
        )
        if tools is None:
            return Response(
                content=json.dumps({"error": "Agent not found"}),
                status_code=404,
                media_type="application/json",
            )
        return tools

    @app.get("/api/governance/agents/{agent_id}/metrics")
    def api_governance_agent_metrics(agent_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        metrics = governance_manager().get_agent_metrics(
            agent_id, tenant_id=governance_tenant_id(request)
        )
        if metrics is None:
            return Response(
                content=json.dumps({"error": "Agent not found"}),
                status_code=404,
                media_type="application/json",
            )
        return metrics

    @app.get("/api/governance/actions")
    def api_governance_actions(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        limit = max(1, min(int(request.query_params.get("limit", 100)), 500))
        offset = max(0, int(request.query_params.get("offset", 0)))
        actions = [
            a.to_dict()
            for a in governance_manager().list_actions(
                agent_id=request.query_params.get("agent_id"),
                action_type=request.query_params.get("action_type"),
                verdict=request.query_params.get("verdict"),
                limit=limit,
                offset=offset,
                tenant_id=governance_tenant_id(request),
            )
        ]
        return {"actions": actions, "count": len(actions)}

    @app.get("/api/governance/actions/stats")
    def api_governance_action_stats(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = max(1, min(int(request.query_params.get("hours", 24)), 24 * 30))
        return governance_manager().get_action_stats(
            agent_id=request.query_params.get("agent_id"),
            hours=hours,
            tenant_id=governance_tenant_id(request),
        )

    @app.get("/api/governance/policies")
    def api_governance_policies(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        policies = [
            p.to_dict()
            for p in governance_manager().list_policies(tenant_id=governance_tenant_id(request))
        ]
        return {"policies": policies, "count": len(policies)}

    @app.post("/api/governance/policies")
    async def api_governance_create_policy(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        from src.ai_governance import AgentPolicy

        policy = AgentPolicy(
            policy_id=0,
            name=str(payload.get("name", "")).strip(),
            description=str(payload.get("description", "")).strip(),
            policy_type=str(payload.get("policy_type", "access_control")).strip(),
            target_agents=json.dumps(payload.get("target_agents", [])),
            conditions=json.dumps(payload.get("conditions", {})),
            effect=str(payload.get("effect", "allow")).strip(),
            priority=int(payload.get("priority", 100)),
            enabled=bool(payload.get("enabled", True)),
        )
        if not policy.name:
            return Response(content="name is required", status_code=400)
        created = governance_manager().create_policy(
            policy, tenant_id=governance_tenant_id(request)
        )
        return created.to_dict()

    @app.post("/api/governance/evaluate")
    async def api_governance_evaluate(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        agent_id = str(payload.get("agent_id", ""))
        action_type = str(payload.get("action_type", ""))
        target = str(payload.get("target", ""))
        mc_id = f"mc-gov-eval-{uuid.uuid4().hex[:12]}"
        mc_exec = _start_mc_execution(
            request,
            mc_id,
            f"Policy eval: {action_type} on {target}",
            "policy_check",
            audit_links={"agent_id": agent_id, "action_type": action_type, "target": target},
        )
        if mc_exec is not None:
            _mc_complete_stage(mc_exec, "policy", status="running")
        start_ts = time.time()
        verdict, reason = governance_manager().evaluate_policies(
            agent_id,
            action_type,
            target,
            tenant_id=governance_tenant_id(request),
        )
        duration = (time.time() - start_ts) * 1000
        if mc_exec is not None:
            policy_decisions = [{"policy": action_type, "effect": verdict, "reason": reason}]
            _mc_complete_stage(
                mc_exec,
                "policy",
                status="completed",
                latency_ms=duration,
                summary=f"Verdict: {verdict}",
                policy_decisions=policy_decisions,
                outputs={"verdict": verdict, "reason": reason},
            )
            _finish_mc_execution(
                mc_exec,
                status="completed" if verdict == "allowed" else "completed",
                overall_result=f"Policy {verdict}: {reason}",
                total_latency_ms=duration,
            )
        return {"verdict": verdict, "reason": reason}

    @app.get("/api/governance/anomalies")
    def api_governance_anomalies(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        limit = max(1, min(int(request.query_params.get("limit", 100)), 500))
        anomalies = [
            a.to_dict()
            for a in governance_manager().list_anomalies(
                agent_id=request.query_params.get("agent_id"),
                limit=limit,
                tenant_id=governance_tenant_id(request),
            )
        ]
        return {"anomalies": anomalies, "count": len(anomalies)}

    @app.get("/api/governance/audit/verify")
    def api_governance_audit_verify(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        return governance_manager().verify_action_audit_chain(
            tenant_id=governance_tenant_id(request)
        )

    @app.get("/api/governance/audit/export.csv")
    def api_governance_audit_export(request: FastAPIRequest) -> Response:
        require_role(*VIEWER_ROLES)(request)
        csv_text = governance_manager().export_action_audit_csv(
            tenant_id=governance_tenant_id(request)
        )
        return Response(content=csv_text, media_type="text/csv")

    @app.get("/api/governance/costs/summary")
    def api_governance_cost_summary(request: FastAPIRequest) -> dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        actions = governance_manager().list_actions(
            limit=1000, tenant_id=governance_tenant_id(request)
        )
        by_model: dict[str, dict[str, Any]] = {}
        by_tier: dict[str, dict[str, Any]] = {}
        total_cost = 0.0
        for action in actions:
            data = action.to_dict().get("outputs", {})
            routing = data.get("routing", {}) if isinstance(data, dict) else {}
            cost = data.get("cost", {}) if isinstance(data, dict) else {}
            model = str(routing.get("selected_model", "unknown"))
            tier = str(routing.get("selected_tier", "unknown"))
            selected_cost = float(cost.get("estimated_selected_usd", 0.0) or 0.0)
            total_cost += selected_cost
            by_model.setdefault(model, {"calls": 0, "estimated_cost_usd": 0.0})
            by_model[model]["calls"] += 1
            by_model[model]["estimated_cost_usd"] += selected_cost
            by_tier.setdefault(tier, {"calls": 0, "estimated_cost_usd": 0.0})
            by_tier[tier]["calls"] += 1
            by_tier[tier]["estimated_cost_usd"] += selected_cost
        return {
            "total_calls": len(actions),
            "estimated_cost_usd": round(total_cost, 8),
            "by_model": by_model,
            "by_tier": by_tier,
        }

    @app.post("/v1/chat/completions")
    async def api_commandmesh_chat_completions(request: FastAPIRequest) -> Any:
        user = require_auth(request, app.state.auth_manager)
        require_api_scope(request, "commandmesh:chat", "ai:invoke")
        try:
            payload = await request.json()
        except Exception:
            return Response(
                content=json.dumps(
                    {"error": {"type": "invalid_request", "message": "Invalid JSON body"}}
                ),
                status_code=400,
                media_type="application/json",
            )
        if payload.get("stream"):
            return Response(
                content=json.dumps(
                    {
                        "error": {
                            "type": "unsupported_feature",
                            "message": "Streaming is not supported by this proxy",
                        }
                    }
                ),
                status_code=400,
                media_type="application/json",
            )

        agent_id = request.headers.get("X-Agent-ID", "commandmesh-proxy")
        messages = payload.get("messages", [])
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
        prompt_tokens = max(1, len(prompt_text.split()))
        from src.ai_governance import AgentAction
        from src.commandmesh_routing import decide_route, estimate_cost_usd

        requested_model = str(payload.get("model", "gpt-4o-mini"))
        route = decide_route(
            requested_provider="openai",
            requested_model=requested_model,
            prompt_text=prompt_text,
            prompt_tokens=prompt_tokens,
            has_tools=bool(payload.get("tools")),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
        tenant = governance_tenant_id(request)
        verdict, reason = governance_manager().evaluate_policies(
            agent_id, "chat_completion", "/v1/chat/completions", tenant_id=tenant
        )
        output_tokens = 256
        selected_cost = estimate_cost_usd(
            prompt_tokens,
            output_tokens,
            route.input_cost_per_million,
            route.output_cost_per_million,
        )
        requested_cost = estimate_cost_usd(
            prompt_tokens,
            output_tokens,
            route.requested_input_cost_per_million,
            route.requested_output_cost_per_million,
        )
        routing_payload = {
            "requested_model": route.requested_model,
            "selected_model": route.selected_model,
            "selected_tier": route.selected_tier,
            "selected_provider": route.selected_provider,
            "routing_disabled": route.routing_disabled,
            "reason": route.reason,
            "complexity": {
                "level": route.complexity.level,
                "score": route.complexity.score,
                "reasons": route.complexity.reasons,
            },
        }
        cost_payload = {
            "estimated_selected_usd": selected_cost,
            "estimated_requested_usd": requested_cost,
        }

        if verdict != "allowed":
            approval_id = ""
            status = "blocked"
            if verdict == "pending_approval":
                import secrets as _secrets

                approval_id = f"cmdmesh-{_secrets.token_hex(8)}"
                repo = app.state.services.platform_repository
                if repo is not None:
                    repo.create_approval_request(
                        approval_id,
                        "commandmesh_chat_completion",
                        user.email,
                        f"Approve CommandMesh request for {agent_id}",
                        {"agent_id": agent_id, "model": route.selected_model, "reason": reason},
                    )
            governance_manager().record_action(
                AgentAction(
                    action_id=f"cmdmesh-{utc_now()}-{agent_id}",
                    agent_id=agent_id,
                    action_type="chat_completion",
                    action_summary="CommandMesh chat completion request",
                    target_resource="/v1/chat/completions",
                    inputs=json.dumps({"model": requested_model, "prompt_tokens": prompt_tokens}),
                    outputs=json.dumps(
                        {
                            "routing": routing_payload,
                            "cost": cost_payload,
                            "approval_id": approval_id,
                        }
                    ),
                    policy_verdict=verdict,
                    status=status,
                ),
                tenant_id=tenant,
            )
            return Response(
                content=json.dumps(
                    {
                        "error": {
                            "type": verdict,
                            "message": reason or verdict,
                            "approval_id": approval_id,
                        }
                    }
                ),
                status_code=403,
                media_type="application/json",
            )

        factory = getattr(app.state, "commandmesh_provider_factory", None)
        if factory is None:
            from src.intelligence.providers.factory import LLMFactory

            def factory(provider_name="openai"):
                return LLMFactory.create(provider_name)

        provider = factory(route.selected_provider)
        from src.intelligence.providers.base import Message

        provider_messages = [
            Message(role=str(m.get("role", "user")), content=str(m.get("content", "")))
            for m in messages
            if isinstance(m, dict)
        ]
        if payload.get("tools"):
            result_message = provider.chat_with_tools(provider_messages, payload.get("tools", []))
        else:
            result_message = provider.chat(provider_messages)
        governance_manager().record_action(
            AgentAction(
                action_id=f"cmdmesh-{utc_now()}-{agent_id}",
                agent_id=agent_id,
                action_type="chat_completion",
                action_summary="CommandMesh chat completion request",
                target_resource="/v1/chat/completions",
                inputs=json.dumps({"model": requested_model, "prompt_tokens": prompt_tokens}),
                outputs=json.dumps({"routing": routing_payload, "cost": cost_payload}),
                policy_verdict=verdict,
                status="success",
            ),
            tenant_id=tenant,
        )
        return {
            "id": f"chatcmpl-{utc_now()}",
            "object": "chat.completion",
            "model": route.selected_model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": result_message.role, "content": result_message.content},
                    "finish_reason": "stop",
                }
            ],
            "commandmesh": {
                "policy_verdict": verdict,
                "routing": routing_payload,
                "cost": cost_payload,
            },
        }

    # ---- Enterprise Search ----
    @app.get("/api/search")
    def api_search(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        q = request.query_params.get("q", "").strip()
        domain = request.query_params.get("domain", "all").strip()
        limit = int(request.query_params.get("limit", 20))
        limit = max(1, min(limit, 100))
        try:
            import os as _os

            from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
            from src.search.engine import SearchEngine

            repo = app.state.services.platform_repository
            mem_db = _os.getenv("AEGIS_AI_MEMORY_DB", "ai_memory.db")
            store = SQLiteMemoryStore(db_path=mem_db)
            engine = SearchEngine(repo=repo, memory_store=store)
            results = engine.search(q, domain=domain, limit=limit)
            return {
                "results": [
                    {
                        "domain": r.domain,
                        "id": r.id,
                        "title": r.title,
                        "snippet": r.snippet,
                        "url": r.url,
                        "score": r.score,
                        "metadata": r.metadata,
                    }
                    for r in results.results
                ],
                "total": results.total,
                "domains": results.domains,
                "query": results.query,
                "duration_ms": results.duration_ms,
            }
        except Exception as exc:
            return {
                "results": [],
                "total": 0,
                "domains": {},
                "query": q,
                "duration_ms": 0,
                "error": str(exc),
            }

    @app.get("/api/search/domains")
    def api_search_domains(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.search.indexer import SearchIndexer

            repo = app.state.services.platform_repository
            indexer = SearchIndexer(repo)
            stats = indexer.get_index_stats()
            domains = {}
            for d, info in stats.get("domains", {}).items():
                domains[d] = info["doc_count"]
            return {"domains": domains, "total": sum(domains.values())}
        except Exception as exc:
            return {"domains": {}, "total": 0, "error": str(exc)}

    @app.post("/api/search/reindex")
    async def api_search_reindex(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        try:
            from src.search.indexer import SearchIndexer

            repo = app.state.services.platform_repository
            indexer = SearchIndexer(repo)
            domains = None
            try:
                body = await request.json()
                if isinstance(body, dict) and "domains" in body:
                    domains = body["domains"]
            except Exception:
                pass
            result = indexer.build_index(domains=domains)
            if repo is not None:
                repo.record_audit_log(
                    user.email if user else "anonymous",
                    "reindex",
                    "search",
                    ",".join(domains) if domains else "all",
                    {},
                )
            return {"status": "ok", "domains": result}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @app.get("/api/search/stats")
    def api_search_stats(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.search.indexer import SearchIndexer

            repo = app.state.services.platform_repository
            indexer = SearchIndexer(repo)
            return indexer.get_index_stats()
        except Exception as exc:
            return {"index_size": 0, "domains": {}, "last_indexed": None, "error": str(exc)}

    # ---- Multi-Agent Collaboration endpoints ----
    @app.get("/api/agents")
    def api_list_agents(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        orchestrator: AgentOrchestrator = request.app.state.agent_orchestrator
        agents = orchestrator.list_agents()
        return {"agents": agents, "count": len(agents)}

    @app.post("/api/agents/dispatch")
    async def api_dispatch_agent(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        task = str(payload.get("task", "")).strip()
        if not task:
            return Response(content="task is required", status_code=400)
        target = str(payload.get("agent_id", "")).strip()
        orchestrator: AgentOrchestrator = request.app.state.agent_orchestrator
        try:
            return await orchestrator.dispatch_task(task, target_agent=target)
        except Exception as exc:
            return Response(
                content=json.dumps({"error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    @app.post("/api/agents/collaborate")
    async def api_collaborate_agents(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        task = str(payload.get("task", "")).strip()
        if not task:
            return Response(content="task is required", status_code=400)
        agent_ids = payload.get("agent_ids", [])
        if not isinstance(agent_ids, list) or not agent_ids:
            return Response(content="agent_ids must be a non-empty list", status_code=400)
        orchestrator: AgentOrchestrator = request.app.state.agent_orchestrator
        try:
            return await orchestrator.collaborate(agent_ids, task)
        except Exception as exc:
            return Response(
                content=json.dumps({"error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    @app.get("/api/agents/state")
    def api_agent_state(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        orchestrator: AgentOrchestrator = request.app.state.agent_orchestrator
        state = orchestrator.get_shared_state()
        return {"state": state}

    @app.post("/api/agents/fan-out")
    async def api_fan_out_agents(request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        task = str(payload.get("task", "")).strip()
        if not task:
            return Response(content="task is required", status_code=400)
        orchestrator: AgentOrchestrator = request.app.state.agent_orchestrator
        try:
            results = await orchestrator.fan_out(task)
            return {
                "results": [
                    {
                        "agent_id": r.agent_id,
                        "success": r.success,
                        "summary": r.summary,
                        "duration_ms": r.duration_ms,
                    }
                    for r in results
                ],
                "count": len(results),
            }
        except Exception as exc:
            return Response(
                content=json.dumps({"error": str(exc)}),
                status_code=500,
                media_type="application/json",
            )

    # ---- Telemetry endpoints ----
    @app.get("/api/telemetry/api-stats")
    def api_telemetry_api_stats(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = int(request.query_params.get("hours", 24))
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_api_stats(hours=max(1, min(hours, 168)))

    @app.get("/api/telemetry/workflow-stats")
    def api_telemetry_workflow_stats(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = int(request.query_params.get("hours", 24))
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_workflow_stats(hours=max(1, min(hours, 168)))

    @app.get("/api/telemetry/agent-stats")
    def api_telemetry_agent_stats(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = int(request.query_params.get("hours", 24))
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_agent_stats(hours=max(1, min(hours, 168)))

    @app.get("/api/telemetry/tool-failures")
    def api_telemetry_tool_failures(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = int(request.query_params.get("hours", 24))
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_tool_failure_stats(hours=max(1, min(hours, 168)))

    @app.get("/api/telemetry/approval-stats")
    def api_telemetry_approval_stats(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = int(request.query_params.get("hours", 24))
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_approval_stats(hours=max(1, min(hours, 168)))

    # ---- Autonomous Operations ----

    @app.get("/api/autonomous/status")
    def api_autonomous_status(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        pipeline = getattr(request.app.state.services, "autonomous_pipeline", None)
        history = getattr(request.app.state.services, "execution_history", None)
        policy = getattr(request.app.state.services, "policy_engine", None)
        healing = getattr(request.app.state.services, "self_healing_engine", None)
        return {
            "pipeline_running": pipeline is not None,
            "total_executions": history.get_stats()["total_executions"] if history else 0,
            "success_rate": history.get_stats()["success_rate"] if history else 0.0,
            "safe_actions": policy.get_safe_actions() if policy else [],
            "approval_actions": policy.get_approval_actions() if policy else [],
            "forbidden_actions": policy.get_forbidden_actions() if policy else [],
            "recent_healing": healing.history[-5:] if healing and healing.history else [],
        }

    @app.get("/api/autonomous/executions")
    def api_autonomous_executions(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        history = getattr(request.app.state.services, "execution_history", None)
        status = request.query_params.get("status")
        if history:
            return {"executions": history.get_records(limit=50, status=status)}
        return {"executions": []}

    @app.get("/api/autonomous/executions/{execution_id}")
    def api_autonomous_execution_detail(execution_id: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        history = getattr(request.app.state.services, "execution_history", None)
        if history:
            record = history.get_record(execution_id)
            if record:
                return record.to_dict()
        return Response(
            content=json.dumps({"error": "Execution not found"}),
            status_code=404,
            media_type="application/json",
        )

    @app.get("/api/autonomous/pipeline")
    def api_autonomous_pipeline_results(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        pipeline = getattr(request.app.state.services, "autonomous_pipeline", None)
        if pipeline:
            return {"results": pipeline.get_results(limit=20)}
        return {"results": []}

    @app.get("/api/autonomous/policies")
    def api_autonomous_policies(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        policy = getattr(request.app.state.services, "policy_engine", None)
        if policy:
            return {
                "policies": policy.list_policies(),
                "safe": policy.get_safe_actions(),
                "approval": policy.get_approval_actions(),
                "forbidden": policy.get_forbidden_actions(),
            }
        return {"policies": [], "safe": [], "approval": [], "forbidden": []}

    @app.get("/api/autonomous/healing")
    def api_autonomous_healing(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        healing = getattr(request.app.state.services, "self_healing_engine", None)
        if healing:
            return {"actions": healing.history}
        return {"actions": []}

    @app.get("/api/telemetry/dashboard")
    def api_telemetry_dashboard(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_dashboard()

    # ---- Multi-Tenant endpoints ----
    @app.get("/api/orgs")
    def api_list_orgs(request: FastAPIRequest) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        mgr: TenantManager = request.app.state.tenant_manager
        api_key_org_id = getattr(request.state, "api_key_org_id", None)
        if api_key_org_id not in (None, ""):
            orgs = [mgr.get_organization(int(api_key_org_id))]
        elif user.is_superuser or user.role == "super_admin":
            orgs = mgr.list_organizations()
        else:
            tenant_ids = {tenant.org_id for tenant in mgr.get_user_tenants(user.id)}
            orgs = [org for org in mgr.list_organizations() if org.id in tenant_ids]
        return {"organizations": [o.__dict__ for o in orgs], "count": len(orgs)}

    @app.post("/api/orgs")
    async def api_create_org(request: FastAPIRequest) -> Any:
        require_role(*ADMIN_ROLES)(request)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        name = str(payload.get("name", "")).strip()
        if not name:
            return Response(content="name is required", status_code=400)
        mgr: TenantManager = request.app.state.tenant_manager
        try:
            org = mgr.create_organization(
                name=name,
                domain=str(payload.get("domain", "")).strip(),
                settings=payload.get("settings"),
            )
            return org.__dict__
        except ValueError as exc:
            return Response(content=str(exc), status_code=409)

    @app.get("/api/orgs/{org_id}")
    def api_get_org(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        require_org_access(request, org_id)
        mgr: TenantManager = request.app.state.tenant_manager
        try:
            org = mgr.get_organization(org_id)
            return org.__dict__
        except ValueError:
            return Response(content="Organization not found", status_code=404)

    @app.put("/api/orgs/{org_id}")
    async def api_update_org(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        require_org_access(request, org_id)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        mgr: TenantManager = request.app.state.tenant_manager
        try:
            org = mgr.update_organization(org_id, **payload)
            return org.__dict__
        except ValueError:
            return Response(content="Organization not found", status_code=404)

    @app.delete("/api/orgs/{org_id}")
    def api_deactivate_org(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*ADMIN_ROLES)(request)
        require_org_access(request, org_id)
        mgr: TenantManager = request.app.state.tenant_manager
        if not mgr.deactivate_organization(org_id):
            return Response(content="Organization not found", status_code=404)
        return {"status": "ok"}

    @app.get("/api/orgs/{org_id}/teams")
    def api_list_teams(org_id: int, request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        require_org_access(request, org_id)
        mgr: TenantManager = request.app.state.tenant_manager
        teams = mgr.list_teams(org_id)
        return {"teams": [t.__dict__ for t in teams], "count": len(teams)}

    @app.post("/api/orgs/{org_id}/teams")
    async def api_create_team(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        require_org_access(request, org_id)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        name = str(payload.get("name", "")).strip()
        if not name:
            return Response(content="name is required", status_code=400)
        mgr: TenantManager = request.app.state.tenant_manager
        try:
            team = mgr.create_team(
                org_id=org_id,
                name=name,
                description=str(payload.get("description", "")).strip(),
            )
            return team.__dict__
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.get("/api/orgs/{org_id}/projects")
    def api_list_projects(org_id: int, request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        require_org_access(request, org_id)
        team_id_param = request.query_params.get("team_id")
        team_id = int(team_id_param) if team_id_param else None
        mgr: TenantManager = request.app.state.tenant_manager
        projects = mgr.list_projects(org_id, team_id=team_id)
        return {"projects": [p.__dict__ for p in projects], "count": len(projects)}

    @app.post("/api/orgs/{org_id}/projects")
    async def api_create_project(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
        require_org_access(request, org_id)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        name = str(payload.get("name", "")).strip()
        team_id = int(payload.get("team_id", 0))
        if not name or not team_id:
            return Response(content="name and team_id are required", status_code=400)
        mgr: TenantManager = request.app.state.tenant_manager
        try:
            project = mgr.create_project(
                org_id=org_id,
                team_id=team_id,
                name=name,
                description=str(payload.get("description", "")).strip(),
            )
            return project.__dict__
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.post("/api/orgs/{org_id}/users")
    async def api_assign_user_to_org(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*ADMIN_ROLES)(request)
        require_org_access(request, org_id)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        user_id = int(payload.get("user_id", 0))
        role = str(payload.get("role", "viewer")).strip().lower()
        if not user_id:
            return Response(content="user_id is required", status_code=400)
        mgr: TenantManager = request.app.state.tenant_manager
        try:
            tu = mgr.assign_user_to_org(user_id=user_id, org_id=org_id, role=role)
            return {"user_id": tu.user_id, "org_id": tu.org_id, "role": tu.role}
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.get("/api/orgs/{org_id}/stats")
    def api_org_stats(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        require_org_access(request, org_id)
        mgr: TenantManager = request.app.state.tenant_manager
        try:
            return mgr.get_org_stats(org_id)
        except ValueError:
            return Response(content="Organization not found", status_code=404)

    @app.get("/api/orgs/{org_id}/users")
    def api_org_users(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        require_org_access(request, org_id)
        p = request.app.state.services.platform_repository
        if p is None:
            return {"users": [], "count": 0}
        placeholder = p.placeholder
        rows = p._fetch_all(
            f"SELECT u.id, u.email, tu.role FROM tenant_users tu JOIN users u ON u.id = tu.user_id WHERE tu.org_id = {placeholder}",
            (org_id,),
        )
        return {"users": rows, "count": len(rows)}

    # ---- AI Workforce ----
    @app.get("/api/workforce/stats")
    def api_workforce_stats(request: FastAPIRequest) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return {"error": "repository_unavailable"}
        manager = WorkforceManager(repo)
        if not (user.is_superuser or user.role == "super_admin"):
            return manager.get_workforce_stats(org_id=request_org_id(request, user))
        return manager.get_workforce_stats()

    @app.get("/api/workforce/agents")
    def api_workforce_list_agents(
        request: FastAPIRequest,
        lifecycle_status: str = "",
        agent_type: str = "",
        search: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return {"agents": [], "total": 0}
        manager = WorkforceManager(repo)
        agents = manager.list_agents(
            lifecycle_status=lifecycle_status or None,
            agent_type=agent_type or None,
            search=search or None,
            org_id=None
            if (user.is_superuser or user.role == "super_admin")
            else request_org_id(request, user),
            limit=min(limit, 500),
            offset=offset,
        )
        total = manager.count_agents(
            lifecycle_status=lifecycle_status or None,
            org_id=None
            if (user.is_superuser or user.role == "super_admin")
            else request_org_id(request, user),
        )
        return {"agents": [a.to_dict() for a in agents], "total": total}

    @app.post("/api/workforce/agents")
    async def api_workforce_create_agent(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceAgent, WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        body = await request.json()
        agent = WorkforceAgent.from_dict(body)
        if not agent.name:
            return JSONResponse({"error": "name is required"}, status_code=400)
        if not (user.is_superuser or user.role == "super_admin"):
            agent.org_id = request_org_id(request, user)
            if agent.org_id is None:
                return JSONResponse({"error": "organization_required"}, status_code=403)
        elif not agent.org_id:
            agent.org_id = request_org_id(request, user)
        agent = manager.register_agent(agent)
        return agent.to_dict()

    @app.get("/api/workforce/agents/{agent_id}")
    def api_workforce_get_agent(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user)
        return agent.to_dict()

    @app.put("/api/workforce/agents/{agent_id}")
    async def api_workforce_update_agent(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceAgent, WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        body = await request.json()
        existing = manager.get_agent(agent_id)
        if not existing:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, existing, user, write=True)
        agent = WorkforceAgent.from_dict({**existing.to_dict(), **body, "agent_id": agent_id})
        if not (user.is_superuser or user.role == "super_admin"):
            agent.org_id = existing.org_id
            agent.team_id = existing.team_id
        manager.update_agent(agent)
        return manager.get_agent(agent_id).to_dict()

    @app.delete("/api/workforce/agents/{agent_id}")
    def api_workforce_delete_agent(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user, write=True)
        if not manager.delete_agent(agent_id):
            return JSONResponse({"error": "not_found"}, status_code=404)
        return {"deleted": True}

    @app.post("/api/workforce/agents/{agent_id}/activate")
    def api_workforce_activate(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        existing = manager.get_agent(agent_id)
        if not existing:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, existing, user, write=True)
        agent = manager.activate_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "cannot_activate"}, status_code=400)
        return agent.to_dict()

    @app.post("/api/workforce/agents/{agent_id}/pause")
    def api_workforce_pause(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        existing = manager.get_agent(agent_id)
        if not existing:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, existing, user, write=True)
        agent = manager.pause_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "cannot_pause"}, status_code=400)
        return agent.to_dict()

    @app.post("/api/workforce/agents/{agent_id}/resume")
    def api_workforce_resume(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        existing = manager.get_agent(agent_id)
        if not existing:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, existing, user, write=True)
        agent = manager.resume_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "cannot_resume"}, status_code=400)
        return agent.to_dict()

    @app.post("/api/workforce/agents/{agent_id}/archive")
    def api_workforce_archive(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        existing = manager.get_agent(agent_id)
        if not existing:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, existing, user, write=True)
        agent = manager.archive_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "cannot_archive"}, status_code=400)
        return agent.to_dict()

    @app.post("/api/workforce/agents/{agent_id}/clone")
    async def api_workforce_clone(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        existing = manager.get_agent(agent_id)
        if not existing:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, existing, user, write=True)
        body = (
            await request.json()
            if request.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        new_name = body.get("name") if isinstance(body, dict) else None
        agent = manager.clone_agent(agent_id, new_name=new_name)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return agent.to_dict()

    @app.get("/api/workforce/agents/{agent_id}/versions")
    def api_workforce_list_versions(agent_id: str, request: FastAPIRequest) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return {"versions": []}
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return {"versions": [], "total": 0}
        require_workforce_agent_access(request, agent, user)
        versions = manager.list_agent_versions(agent_id)
        return {"versions": [v.to_dict() for v in versions], "total": len(versions)}

    @app.post("/api/workforce/agents/{agent_id}/versions")
    async def api_workforce_create_version(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "agent_not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user, write=True)
        body = (
            await request.json()
            if request.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        change_summary = (body or {}).get("change_summary", "")
        created_by = (body or {}).get("created_by", "")
        version = manager.create_agent_version(agent_id, change_summary, created_by)
        if not version:
            return JSONResponse({"error": "agent_not_found"}, status_code=404)
        return version.to_dict()

    @app.get("/api/workforce/agents/{agent_id}/versions/{version}")
    def api_workforce_get_version(agent_id: str, version: int, request: FastAPIRequest) -> Any:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user)
        snap = manager.get_agent_version(agent_id, version)
        if not snap:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return snap.to_dict()

    @app.post("/api/workforce/agents/{agent_id}/versions/{version}/restore")
    def api_workforce_restore_version(agent_id: str, version: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        existing = manager.get_agent(agent_id)
        if not existing:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, existing, user, write=True)
        agent = manager.restore_agent_version(agent_id, version)
        if not agent:
            return JSONResponse({"error": "cannot_restore"}, status_code=400)
        return agent.to_dict()

    @app.get("/api/workforce/agents/{agent_id}/prompts")
    def api_workforce_list_prompts(agent_id: str, request: FastAPIRequest) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return {"prompts": []}
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return {"prompts": [], "total": 0}
        require_workforce_agent_access(request, agent, user)
        prompts = manager.list_prompt_versions(agent_id=agent_id)
        return {"prompts": [p.to_dict() for p in prompts], "total": len(prompts)}

    @app.post("/api/workforce/agents/{agent_id}/prompts")
    async def api_workforce_save_prompt(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user, write=True)
        body = await request.json()
        prompt = manager.save_prompt_version(
            agent_id=agent_id,
            name=body.get("name", ""),
            content=body.get("content", ""),
            role=body.get("role", "system"),
            variables=body.get("variables"),
            description=body.get("description", ""),
        )
        return prompt.to_dict()

    @app.get("/api/workforce/agents/{agent_id}/tools")
    def api_workforce_list_tools(agent_id: str, request: FastAPIRequest) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return {"tools": []}
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return {"tools": [], "total": 0}
        require_workforce_agent_access(request, agent, user)
        tools = manager.get_tool_permissions(agent_id)
        return {"tools": [t.to_dict() for t in tools], "total": len(tools)}

    @app.put("/api/workforce/agents/{agent_id}/tools/{tool_name}")
    async def api_workforce_set_tool(agent_id: str, tool_name: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user, write=True)
        body = (
            await request.json()
            if request.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        allowed = (body or {}).get("allowed", True)
        config = (body or {}).get("config", {})
        perm = manager.set_tool_permission(agent_id, tool_name, bool(allowed), config)
        return perm.to_dict()

    @app.delete("/api/workforce/agents/{agent_id}/tools/{tool_name}")
    def api_workforce_delete_tool(agent_id: str, tool_name: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user, write=True)
        manager.delete_tool_permission(agent_id, tool_name)
        return {"deleted": True}

    @app.get("/api/workforce/agents/{agent_id}/knowledge")
    def api_workforce_list_knowledge(agent_id: str, request: FastAPIRequest) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return {"assignments": []}
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return {"assignments": [], "total": 0}
        require_workforce_agent_access(request, agent, user)
        assignments = manager.list_knowledge_assignments(agent_id)
        return {"assignments": [a.to_dict() for a in assignments], "total": len(assignments)}

    @app.post("/api/workforce/agents/{agent_id}/knowledge")
    async def api_workforce_assign_knowledge(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user, write=True)
        body = await request.json()
        ka = manager.assign_knowledge(
            agent_id=agent_id,
            knowledge_source_id=body.get("knowledge_source_id", ""),
            source_type=body.get("source_type", "collection"),
            access_level=body.get("access_level", "read_write"),
            priority=body.get("priority", 100),
        )
        return ka.to_dict()

    @app.delete("/api/workforce/agents/{agent_id}/knowledge/{source_id}")
    def api_workforce_remove_knowledge(
        agent_id: str, source_id: str, request: FastAPIRequest
    ) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user, write=True)
        manager.remove_knowledge_assignment(agent_id, source_id)
        return {"deleted": True}

    @app.get("/api/workforce/agents/{agent_id}/executions")
    def api_workforce_list_executions(
        agent_id: str,
        request: FastAPIRequest,
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return {"executions": [], "total": 0}
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return {"executions": [], "total": 0}
        require_workforce_agent_access(request, agent, user)
        execs = manager.list_executions(
            agent_id=agent_id, status=status or None, limit=min(limit, 500), offset=offset
        )
        return {"executions": [e.to_dict() for e in execs], "total": len(execs)}

    @app.get("/api/workforce/agents/{agent_id}/executions/stats")
    def api_workforce_execution_stats(agent_id: str, request: FastAPIRequest) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return {"total": 0}
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return {"total": 0}
        require_workforce_agent_access(request, agent, user)
        return manager.get_execution_stats(agent_id=agent_id)

    @app.get("/api/workforce/agents/{agent_id}/budget")
    def api_workforce_budget(agent_id: str, request: FastAPIRequest) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return {"error": "repository_unavailable"}
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return {"error": "not_found"}
        require_workforce_agent_access(request, agent, user)
        return manager.get_budget_usage(agent_id)

    @app.get("/api/workforce/agents/{agent_id}/health")
    def api_workforce_health_history(
        agent_id: str, request: FastAPIRequest, limit: int = 50
    ) -> dict[str, Any]:
        user = require_role(*VIEWER_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return {"records": []}
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return {"records": [], "latest": None}
        require_workforce_agent_access(request, agent, user)
        records = manager.get_health_history(agent_id, limit=min(limit, 200))
        latest = manager.get_latest_health(agent_id)
        return {
            "records": [r.to_dict() for r in records],
            "latest": latest.to_dict() if latest else None,
        }

    @app.post("/api/workforce/agents/{agent_id}/health")
    async def api_workforce_record_health(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user, write=True)
        body = (
            await request.json()
            if request.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        b = body or {}
        record = manager.record_health_check(
            agent_id=agent_id,
            status=b.get("status", "healthy"),
            check_type=b.get("check_type", "heartbeat"),
            metric_value=float(b.get("metric_value", 0.0)),
            details=b.get("details", {}),
        )
        return record.to_dict()

    @app.post("/api/workforce/agents/{agent_id}/playground")
    async def api_workforce_playground(agent_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceExecutionBlocked, WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        agent = manager.get_agent(agent_id)
        if not agent:
            return JSONResponse({"error": "not_found"}, status_code=404)
        require_workforce_agent_access(request, agent, user, write=True)
        body = await request.json()
        task = body.get("task", "")
        if not task:
            return JSONResponse({"error": "task is required"}, status_code=400)
        prompt_override = body.get("prompt_override")
        simulate = body.get("simulate", False)
        try:
            execution = manager.playground_execute(
                agent_id,
                task,
                prompt_override,
                bool(simulate),
                repo=repo,
            )
        except WorkforceExecutionBlocked as exc:
            return JSONResponse({"error": exc.reason, "details": exc.details}, status_code=409)
        _track_workforce_execution_in_mc(request, agent, execution)
        _track_workforce_execution_in_governance(request, agent, execution)
        return execution.to_dict()

    @app.post("/api/workforce/wizard")
    async def api_workforce_wizard(request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        from src.ai_workforce import WorkforceManager

        repo = app.state.services.platform_repository
        if repo is None:
            return JSONResponse({"error": "repository_unavailable"}, status_code=503)
        manager = WorkforceManager(repo)
        body = await request.json()
        if not body.get("name"):
            return JSONResponse({"error": "name is required"}, status_code=400)
        org_id = body.get("org_id")
        if not (user.is_superuser or user.role == "super_admin"):
            org_id = request_org_id(request, user)
            if org_id is None:
                return JSONResponse({"error": "organization_required"}, status_code=403)
        agent = manager.create_agent_wizard(
            name=body["name"],
            agent_type=body.get("agent_type", "general"),
            description=body.get("description", ""),
            provider=body.get("provider", "openai"),
            model=body.get("model", "gpt-4o-mini"),
            tools=body.get("tools"),
            permissions=body.get("permissions"),
            knowledge_sources=body.get("knowledge_sources"),
            daily_budget=float(body.get("daily_budget", 25.0)),
            monthly_budget=float(body.get("monthly_budget", 750.0)),
            owner=body.get("owner", ""),
            team=body.get("team", ""),
            org_id=int(org_id) if org_id not in (None, "") else None,
            team_id=int(body["team_id"]) if body.get("team_id") not in (None, "") else None,
            tags=body.get("tags"),
            system_prompt=body.get("system_prompt"),
        )
        return agent.to_dict()

    # ---- Public health endpoints ----
    @app.get("/api/health")
    def api_health() -> dict[str, Any]:
        return {"status": "ok", "timestamp": utc_now(), "service": "aegisnex"}

    @app.get("/api/health/ready")
    def api_health_ready() -> dict[str, Any]:
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None:
            db_status = repo.health_check()
            if db_status.get("status") != "connected":
                return {"status": "not_ready", "reason": "database_unavailable"}
        return {"status": "ready"}

    @app.get("/api/health/live")
    def api_health_live() -> dict[str, Any]:
        return {"status": "alive"}

    @app.get("/api/health/status")
    def api_health_status(request: FastAPIRequest) -> dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = getattr(app.state.services, "platform_repository", None)
        db_health = repo.health_check() if repo is not None else {"status": "unknown"}
        docker_ok = False
        try:
            import docker

            client = docker.from_env(timeout=3)
            docker_ok = bool(client.ping())
        except Exception:
            docker_ok = False
        return {
            "service": "aegisnex",
            "version": "1.0.0",
            "timestamp": utc_now(),
            "database": db_health,
            "docker": {"status": "connected" if docker_ok else "disconnected"},
        }

    return app


app = create_app()
