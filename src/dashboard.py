"""FastAPI dashboard for AegisNex operational visibility."""

from __future__ import annotations

import platform
import socket

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import asyncio
from pathlib import Path
import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse as StarletteRedirect

from src.auth import AuthManager, User, Role, AuthError, parse_form_body
from src.config import Config
from src.docker_scanner import DockerScanner
from src.guardian import Guardian
from src.http_monitor import HttpEndpointMonitor
from src.incidents import Incident, IncidentManager
from src.monitoring_engine import MonitoringEngine
from src.monitor import SystemResourceMonitor
from src.notifier import Notifier
from src.orchestrator import SystemHealthChecker
from src.prometheus_exporter import PrometheusExporter
from src.reporting import OperationalReporter
from src.ssl_monitor import SslCertificateMonitor
from src.tcp_monitor import TcpTargetMonitor
from src.platform_db import PlatformRepository, load_database_settings
from src.websocket_manager import WebSocketManager
from src.cache import DashboardCache
from src.logging_config import configure_logging, get_logger
from src.compliance.engine import ComplianceEngine
from src.compliance.evidence import EvidenceCollector
from src.opentelemetry import instrument_app
from src.intelligence.graph import run_chat, run_analyze, run_plan
from src.intelligence.history import save_workflow, list_history, get_history_count
from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
from src.knowledge.indexer import KnowledgeIndexer
from src.knowledge.retriever import KnowledgeRetriever
from src.knowledge.loader import load_document as _kd_load_document
from src.telemetry.collector import TelemetryCollector
from src.telemetry.middleware import TelemetryMiddleware
from src.multitenant.manager import TenantManager
from src.agents.orchestrator import AgentOrchestrator

try:
    from fastapi import Request as FastAPIRequest, WebSocket, WebSocketDisconnect
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

class TLSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS when running in production mode."""

    async def dispatch(self, request: FastAPIRequest, call_next: Any) -> Any:
        environment = os.getenv("AEGISNEX_ENV", "development").strip().lower()
        if environment not in {"development", "dev", "local", "test"}:
            if request.url.scheme != "https" and request.headers.get("x-forwarded-proto") != "https":
                url = request.url.replace(scheme="https")
                return StarletteRedirect(url=url, status_code=301)
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
    user, _ = authenticate_request(request, auth_manager)
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _websocket_token(websocket: Any) -> str | None:
    """Extract a websocket bearer token from cookie, header, or query string."""
    token = websocket.cookies.get("aegisnex_session")
    if token:
        return token
    auth_header = websocket.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    query_token = websocket.query_params.get("token") or websocket.query_params.get("access_token")
    return query_token or None


def require_role(*roles: str):
    """Dependency factory: require the authenticated user to have one of the specified roles."""
    def role_checker(request: FastAPIRequest) -> User:
        auth_manager: AuthManager = request.app.state.auth_manager
        user, _ = authenticate_request(request, auth_manager)
        if user is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Authentication required")
        if not user.has_role(*roles):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.role}' not permitted. Required: {', '.join(roles)}",
            )
        return user
    return role_checker


def _extract_token(request: FastAPIRequest) -> str | None:
    """Extract JWT from Authorization header or cookie."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get("aegisnex_session")


def authenticate_request(request: FastAPIRequest, auth_manager: AuthManager) -> tuple[User | None, bool]:
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
        return None
    from src.auth import hash_api_key
    key_hash = hash_api_key(api_key)
    repo = getattr(request.app.state, "services", None)
    if repo is None:
        repo = getattr(request.app.state.services, "platform_repository", None)
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
    key_id = int(key_record["id"])
    try:
        repo.record_api_key_usage(key_id)
    except Exception:
        pass
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


def create_services(config_path: str | Path = "config.yaml") -> DashboardServices:
    config = Config.load(config_path)
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
        config.storage.database_url
        or load_database_settings(config.storage.database_path)
    )
    incident_manager = IncidentManager(
        config.incidents.history_path,
        storage_repository=platform_repository,
    )
    health_checker = SystemHealthChecker(monitor=monitor, docker_scanner=docker_scanner)
    guardian = Guardian(
        health_checker=health_checker,
        docker_scanner=docker_scanner,
        notifier=Notifier(),
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
    from src.policy_engine import AppPolicyEngine
    from src.execution_history import ExecutionHistory
    from src.healing import SelfHealingEngine
    from src.autonomous import AutonomousPipeline
    policy_engine = AppPolicyEngine(repository=platform_repository)
    execution_history = ExecutionHistory(
        history_path=Path(config.storage.database_path).parent / "execution_history.json",
        repository=platform_repository,
    )
    self_healing_engine = SelfHealingEngine(
        policy_engine=policy_engine,
        docker_scanner=docker_scanner,
        notifier=Notifier(),
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
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_cors_origins() -> List[str]:
    configured_origins = os.getenv("AEGISNEX_CORS_ORIGINS", "")
    if configured_origins.strip():
        return [
            origin.strip()
            for origin in configured_origins.split(",")
            if origin.strip()
        ]
    environment = os.getenv("AEGISNEX_ENV", "development").strip().lower()
    if environment in {"development", "dev", "local", "test"}:
        return DEVELOPMENT_CORS_ORIGINS
    return []


def get_network_stats() -> Dict[str, Any]:
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


def load_restart_history(path: str | Path) -> Dict[str, Dict[str, Any]]:
    history_path = Path(path)
    if not history_path.exists():
        return {}
    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(name): value
        for name, value in payload.items()
        if isinstance(value, dict)
    }


def incident_to_dict(incident: Incident) -> Dict[str, Any]:
    return incident.to_dict()


def build_container_rows(
    containers: List[Dict[str, Any]],
    restart_history: Dict[str, Dict[str, Any]],
    last_check_timestamp: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for container in containers:
        name = str(container.get("name", "unknown"))
        history = restart_history.get(name, {})
        rows.append({
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
        })
    return rows


def build_remediation_actions(
    incidents: List[Incident],
    restart_history: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for incident in incidents:
        if incident.remediation_attempted:
            actions.append({
                "timestamp": incident.timestamp,
                "service_name": incident.service_name,
                "action": "restart",
                "successful": incident.remediation_successful,
                "incident_id": incident.incident_id,
                "source": "incident",
            })
    for service_name, history in restart_history.items():
        if history.get("attempts"):
            actions.append({
                "timestamp": history.get("last_restart", ""),
                "service_name": service_name,
                "action": "restart",
                "successful": None,
                "incident_id": "",
                "source": "restart_history",
            })
    return sorted(actions, key=lambda item: str(item.get("timestamp", "")), reverse=True)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def storage_rows(services: DashboardServices, table_name: str) -> List[Dict[str, Any]]:
    repository = services.platform_repository
    if repository is None:
        return []
    try:
        return list(repository.fetch_all(table_name))
    except Exception:
        return []


def collect_http_monitoring(services: DashboardServices) -> Dict[str, Any]:
    return {"status": "disabled", "timestamp": utc_now(), "availability_percent": 100.0, "available_count": 0, "total_count": 0, "checks": []}

def collect_ssl_monitoring(services: DashboardServices) -> Dict[str, Any]:
    return {"status": "disabled", "timestamp": utc_now(), "warning_count": 0, "total_count": 0, "checks": []}

def collect_tcp_monitoring(services: DashboardServices) -> Dict[str, Any]:
    return {"status": "disabled", "timestamp": utc_now(), "availability_percent": 100.0, "reachable_count": 0, "total_count": 0, "checks": []}


def build_monitoring_summary(repository: Any, target_type: str) -> Dict[str, Any]:
    targets = [t for t in repository.list_monitoring_targets() if str(t.get("target_type", "")).lower() == target_type]
    latest = [r for r in repository.latest_check_results() if str(r.get("target_type", "")).lower() == target_type]
    details = [dict(r.get("details", {})) for r in latest]
    if not targets:
        base: Dict[str, Any] = {"status": "disabled", "timestamp": utc_now(), "total_count": 0, "checks": []}
        if target_type == "ssl": base["warning_count"] = 0
        elif target_type == "tcp": base.update({"availability_percent": 100.0, "reachable_count": 0})
        else: base.update({"availability_percent": 100.0, "available_count": 0})
        return base
    if target_type == "ssl":
        wc = len([c for c in details if c.get("status") != "ok"])
        s = "ok" if wc == 0 else "warning"
        return {"status": s, "timestamp": latest[0]["timestamp"] if latest else utc_now(), "warning_count": wc, "total_count": len(targets), "checks": details}
    if target_type == "tcp":
        rc = len([c for c in details if c.get("reachable")])
        ap = round((rc / len(targets)) * 100, 2) if targets else 100.0
        s = "ok" if rc == len(targets) else "warning"
        return {"status": s, "timestamp": latest[0]["timestamp"] if latest else utc_now(), "availability_percent": ap, "reachable_count": rc, "total_count": len(targets), "checks": details}
    ac = len([c for c in details if c.get("available")])
    ap = round((ac / len(targets)) * 100, 2) if targets else 100.0
    s = "ok" if ac == len(targets) else "warning"
    return {"status": s, "timestamp": latest[0]["timestamp"] if latest else utc_now(), "availability_percent": ap, "available_count": ac, "total_count": len(targets), "checks": details}


def build_metric_trends(metric_rows: List[Dict[str, Any]], metrics: Dict[str, Any], now: datetime | None = None) -> Dict[str, Dict[str, Any]]:
    current_time = now or datetime.now(timezone.utc)
    window_start = current_time - timedelta(hours=24)
    recent_rows = [r for r in metric_rows if (parse_timestamp(r.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)) >= window_start]
    recent_rows.sort(key=lambda r: str(r.get("timestamp", "")))
    if not recent_rows:
        label = current_time.strftime("%H:%M")
        return {"cpu": {"labels": [label], "values": [_safe_float(metrics.get("cpu_percent"))]}, "memory": {"labels": [label], "values": [_safe_float(metrics.get("ram_percent"))]}}
    labels = [(parse_timestamp(r.get("timestamp")) or current_time).strftime("%H:%M") for r in recent_rows]
    return {"cpu": {"labels": labels, "values": [_safe_float(r.get("cpu_percent")) for r in recent_rows]}, "memory": {"labels": labels, "values": [_safe_float(r.get("memory_percent")) for r in recent_rows]}}


def build_hourly_event_trend(rows: List[Dict[str, Any]], now: datetime | None = None) -> Dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    start_hour = (current_time - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
    buckets = {start_hour + timedelta(hours=i): 0 for i in range(24)}
    for row in rows:
        ts = parse_timestamp(row.get("timestamp"))
        if ts and ts.replace(minute=0, second=0, microsecond=0) in buckets:
            buckets[ts.replace(minute=0, second=0, microsecond=0)] += 1
    return {"labels": [b.strftime("%H:%M") for b in buckets], "values": list(buckets.values())}


def build_notification_statistics(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    stats: Dict[str, int] = {"email_count": 0, "slack_count": 0, "discord_count": 0, "failed_notifications": 0}
    ok = {"ok", "sent", "success"}
    for row in rows:
        p = str(row.get("provider", "")).lower()
        if p == "email": stats["email_count"] += 1
        elif p == "slack": stats["slack_count"] += 1
        elif p == "discord": stats["discord_count"] += 1
        if str(row.get("status", "")).lower() not in ok:
            stats["failed_notifications"] += 1
    return stats


def build_recent_incidents(incidents: List[Incident], limit: int = 6) -> List[Dict[str, Any]]:
    rows = [incident_to_dict(i) for i in incidents]
    rows.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return rows[:limit]


def build_recent_remediations(storage_remediations: List[Dict[str, Any]], fallback_actions: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    rows = storage_remediations or fallback_actions
    normalized = [{"timestamp": row.get("timestamp", ""), "service_name": row.get("service_name", ""), "action": row.get("action", ""), "successful": _boolish(row.get("successful"))} for row in rows]
    normalized.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return normalized[:limit]


def calculate_health_score(metrics: Dict[str, Any], containers: List[Dict[str, Any]], active_incident_count: int) -> Dict[str, Any]:
    cpu = _safe_float(metrics.get("cpu_percent"))
    memory = _safe_float(metrics.get("ram_percent"))
    unhealthy = len([c for c in containers if c.get("status") != "running" or c.get("health_status") not in {"healthy", "none", None, ""}])
    penalty = (unhealthy / len(containers)) * 25 if containers else 0.0
    score = max(0, min(100, round(100.0 - min(cpu, 100.0) * 0.25 - min(memory, 100.0) * 0.25 - penalty - min(active_incident_count * 5, 25))))
    if score >= 80: status, indicator = "healthy", "green"
    elif score >= 60: status, indicator = "degraded", "yellow"
    else: status, indicator = "critical", "red"
    return {"score": score, "status": status, "indicator": indicator}


def _safe_float(value: Any) -> float:
    try: return round(float(value), 2)
    except (TypeError, ValueError): return 0.0


def _boolish(value: Any) -> bool | None:
    if value is None: return None
    if isinstance(value, bool): return value
    if isinstance(value, int): return bool(value)
    n = str(value).lower()
    if n in {"1", "true", "yes", "ok", "success"}: return True
    if n in {"0", "false", "no", "failed", "failure"}: return False
    return None


def collect_dashboard_context(services: DashboardServices, use_cache: bool = True) -> Dict[str, Any]:
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
        "chart_data": {"metrics": build_metric_trends(metric_rows, metrics), "incidents": build_hourly_event_trend([incident_to_dict(i) for i in incidents]), "remediations": build_hourly_event_trend(remediation_rows or actions)},
        "recent_incidents": build_recent_incidents(incidents),
        "recent_remediations": build_recent_remediations(remediation_rows, actions),
        "notification_stats": build_notification_statistics(notification_rows),
        "notification_rows": sorted(notification_rows, key=lambda r: str(r.get("timestamp", "")), reverse=True),
        "http_monitoring": collect_http_monitoring(services),
        "ssl_monitoring": collect_ssl_monitoring(services),
        "tcp_monitoring": collect_tcp_monitoring(services),
    }
    if cache is not None:
        cache.set_system_metrics(result)
    return result


def build_dashboard_api_snapshot(context: Dict[str, Any]) -> Dict[str, Any]:
    incidents = context["active_incidents"] + context["resolved_incidents"]
    incidents.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return {
        "system": {"timestamp": context["timestamp"], "health_score": context["health_score"], "metrics": context["metrics"], "active_incident_count": len(context["active_incidents"]), "running_container_count": len(context["running_containers"])},
        "containers": {"timestamp": context["timestamp"], "containers": context["containers"], "running_containers": context["running_containers"], "count": len(context["containers"])},
        "incidents": {"active_incidents": context["active_incidents"], "resolved_incidents": context["resolved_incidents"], "recent_incidents": context["recent_incidents"], "incidents": incidents, "active_count": len(context["active_incidents"]), "resolved_count": len(context["resolved_incidents"]), "count": len(incidents)},
        "metrics": {"timestamp": context["timestamp"], "metrics": context["metrics"], "network": context["network"], "chart_data": context["chart_data"]["metrics"]},
        "notifications": {"notification_stats": context["notification_stats"], "notifications": context.get("notification_rows", [])[:25], "count": len(context.get("notification_rows", []))},
        "remediations": {"actions": context["actions"], "recent_remediations": context["recent_remediations"], "count": len(context["actions"])},
        "http_monitoring": context.get("http_monitoring", {"status": "disabled"}),
        "ssl_monitoring": context.get("ssl_monitoring", {"status": "disabled"}),
        "tcp_monitoring": context.get("tcp_monitoring", {"status": "disabled"}),
    }


def build_realtime_event(event_type: str, payload: Dict[str, Any], timestamp: str | None = None) -> Dict[str, Any]:
    if event_type not in REALTIME_EVENT_TYPES:
        raise ValueError(f"Unsupported realtime event type: {event_type}")
    return {"type": event_type, "timestamp": timestamp or utc_now(), "payload": payload}


def build_realtime_events(current: Dict[str, Any], previous: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    events = [build_realtime_event("metric_update", build_dashboard_api_snapshot(current), current["timestamp"])]
    if previous is None:
        return events
    prev_incidents = {i["incident_id"]: i for i in previous["active_incidents"] + previous["resolved_incidents"]}
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
        if pc is None or any(pc.get(f) != c.get(f) for f in ("status", "health_status", "restart_count")):
            events.append(build_realtime_event("container_status_changed", c, current["timestamp"]))
    return events


def _remediation_key(action: Dict[str, Any]) -> tuple:
    return (str(action.get("timestamp", "")), str(action.get("service_name", "")), str(action.get("action", "")), str(action.get("incident_id", "")), str(action.get("source", "")))


async def run_dashboard_broadcaster(app: Any, interval_seconds: float = DEFAULT_WEBSOCKET_POLL_INTERVAL_SECONDS) -> None:
    previous_context: Dict[str, Any] | None = None
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
                    await manager.broadcast_with_backoff({
                        "type": "container_list",
                        "timestamp": context["timestamp"],
                        "payload": {"containers": context["containers"], "count": len(context["containers"])},
                    }, channel="containers")
                # Broadcast target updates to /ws/targets channel
                repo = app.state.services.platform_repository
                if repo is not None:
                    targets = repo.list_monitoring_targets()
                    await manager.broadcast_with_backoff({
                        "type": "target_list",
                        "timestamp": context["timestamp"],
                        "payload": {"targets": targets, "count": len(targets)},
                    }, channel="targets")
                manager.reset_failures()
                previous_context = context
            else:
                previous_context = None
                manager.reset_failures()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("WebSocket broadcaster error: %s", exc, exc_info=True)
        await asyncio.sleep(interval_seconds)


def build_integrations_context(services: DashboardServices) -> Dict[str, Any]:
    def check_grafana() -> Dict[str, Any]:
        grafana_dir = BASE_DIR / "grafana"
        provisioned = grafana_dir.exists()
        health_url = None
        dashboard_url = None
        reachable = False
        try:
            import urllib.request
            import urllib.error
            config = getattr(services, "config", None)
            if config and hasattr(config, "integrations") and hasattr(config.integrations, "grafana_url"):
                health_url = f"{config.integrations.grafana_url.rstrip('/')}/api/health"
            if not health_url and provisioned:
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
        return {"name": "Grafana", "status": status, "description": "Provisioned dashboards.", "url": dashboard_url, "reachable": reachable}

    def check_prometheus() -> Dict[str, Any]:
        prometheus_dir = BASE_DIR / "grafana" / "prometheus"
        reachable = False
        scrape_url = None
        try:
            import urllib.request
            import urllib.error
            config = getattr(services, "config", None)
            if config and hasattr(config, "integrations") and hasattr(config.integrations, "prometheus_url"):
                base = config.integrations.prometheus_url.rstrip("/")
            else:
                base = "http://localhost:9090"
            targets_url = f"{base}/api/v1/targets"
            req = urllib.request.Request(targets_url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    reachable = data.get("status") == "success"
            scrape_url = f"{base}/metrics"
        except Exception:
            reachable = False
        status = "connected" if reachable else ("configured" if prometheus_dir.exists() else "not configured")
        return {"name": "Prometheus", "status": status, "description": "Metrics endpoint available.", "url": scrape_url, "reachable": reachable}

    def check_docker() -> Dict[str, Any]:
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
        return {"name": "Docker", "status": "connected" if reachable else "disconnected", "description": f"Container runtime inventory ({running_count}/{container_count} running).", "reachable": reachable, "container_count": container_count, "running_count": running_count}

    def check_mcp() -> Dict[str, Any]:
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
        return {"name": "MCP", "status": status, "description": f"FastMCP server ({tools_available} tools).", "reachable": reachable, "tool_count": tools_available}

    def check_sqlite() -> Dict[str, Any]:
        repository = getattr(services, "platform_repository", None)
        reachable = False
        try:
            if repository is not None:
                _ = repository.fetch_all("incidents", limit=1)
                reachable = True
        except Exception:
            reachable = False
        status = "connected" if reachable else "disconnected"
        return {"name": "SQLite", "status": status, "description": "SQLite persistence.", "reachable": reachable}

    return {"integrations": [check_grafana(), check_prometheus(), check_docker(), check_mcp(), check_sqlite()]}


def build_mcp_context() -> Dict[str, Any]:
    return {"mcp_tools": [
        {"name": "get_system_health", "description": "Current system and Docker health report.", "example": '{"tool": "get_system_health"}'},
        {"name": "list_containers", "description": "List Docker containers.", "example": '{"tool": "list_containers", "include_all": true}'},
        {"name": "list_incidents", "description": "List incidents by status.", "example": '{"tool": "list_incidents", "status": "active"}'},
        {"name": "get_metrics", "description": "Current metrics snapshot.", "example": '{"tool": "get_metrics"}'},
        {"name": "get_http_monitoring", "description": "HTTP endpoint status.", "example": '{"tool": "get_http_monitoring"}'},
        {"name": "get_ssl_monitoring", "description": "SSL certificate status.", "example": '{"tool": "get_ssl_monitoring"}'},
        {"name": "get_tcp_monitoring", "description": "TCP target status.", "example": '{"tool": "get_tcp_monitoring"}'},
        {"name": "generate_report", "description": "Generate weekly or monthly report.", "example": '{"tool": "generate_report", "report_type": "weekly"}'},
        {"name": "restart_container", "description": "Restart a Docker container.", "example": '{"tool": "restart_container", "container_name": "api"}'},
    ], "claude_config": json.dumps({"mcpServers": {"aegisnex": {"command": "python", "args": ["-m", "src.mcp_server"], "cwd": str(BASE_DIR)}}}, indent=2)}


def build_reports_context(services: DashboardServices) -> Dict[str, Any]:
    return {
        "reports": [
            {"name": "Weekly report", "report_type": "weekly", "payload": {"window": {"label": "Last 7 days"}}},
            {"name": "Monthly report", "report_type": "monthly", "payload": {"window": {"label": "Last 30 days"}}},
        ]
    }


def build_notifications_context(services: DashboardServices) -> Dict[str, Any]:
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
                active_incidents = len([i for i in all_incidents if i.status in {"active", "acknowledged"}])
                resolved_incidents = len([i for i in all_incidents if i.status == "resolved"])
                repo.save_metrics_snapshot({
                    "aegisnex_system_cpu_usage_percent": float(metrics.get("cpu_percent", 0)),
                    "aegisnex_system_memory_usage_percent": float(metrics.get("ram_percent", 0)),
                    "aegisnex_system_disk_usage_percent": float(metrics.get("disk_percent", 0)),
                    "aegisnex_system_network_bytes_sent": float(metrics.get("network_bytes_sent", 0)),
                    "aegisnex_system_network_bytes_received": float(metrics.get("network_bytes_recv", 0)),
                    "aegisnex_containers_running": float(running),
                    "aegisnex_containers_stopped": float(stopped),
                    "aegisnex_incidents_active": float(active_incidents),
                    "aegisnex_incidents_resolved": float(resolved_incidents),
                    "aegisnex_incidents_total": float(len(all_incidents)),
                })
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Metrics snapshot task failed")
        await asyncio.sleep(interval_seconds)


async def incident_broadcast_task(app: Any, event_type: str, payload: Dict[str, Any]) -> None:
    """Broadcast an incident event to the incidents WebSocket channel."""
    try:
        manager = app.state.websocket_manager
        event = build_realtime_event(event_type.replace("incident_", "") if event_type.startswith("incident_") else event_type, payload)
        await manager.broadcast(event, channel="incidents")
    except Exception:
        pass


def create_app(services: Optional[DashboardServices] = None, auth_manager: AuthManager | None = None) -> Any:
    try:
        from fastapi import FastAPI, Response, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import RedirectResponse
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
    except ModuleNotFoundError as exc:
        raise RuntimeError("Dashboard dependencies are missing. Install requirements.txt first.") from exc

    @asynccontextmanager
    async def lifespan(fastapi_app: Any) -> Any:
        # Set broadcast callback on incident manager
        im = getattr(fastapi_app.state.services, "incident_manager", None)
        if im is not None:
            async def _incident_broadcast(event_type: str, payload: Dict[str, Any]) -> None:
                await incident_broadcast_task(fastapi_app, event_type, payload)
            im.broadcast_callback = _incident_broadcast

        fastapi_app.state.websocket_broadcast_task = asyncio.create_task(run_dashboard_broadcaster(fastapi_app, fastapi_app.state.websocket_poll_interval_seconds))
        fastapi_app.state.metrics_snapshot_task = asyncio.create_task(save_metrics_snapshot_task(fastapi_app, 60))
        fastapi_app.state.monitoring_engine_task = None
        if getattr(fastapi_app.state.services, "monitoring_engine", None) is not None:
            fastapi_app.state.monitoring_engine_task = asyncio.create_task(fastapi_app.state.services.monitoring_engine.run_forever())
        orchestrator = AgentOrchestrator(repo=fastapi_app.state.services.platform_repository)
        fastapi_app.state.agent_orchestrator = orchestrator

        # Start autonomous pipeline
        pipeline = getattr(fastapi_app.state.services, "autonomous_pipeline", None)
        if pipeline is not None:
            try:
                pipeline._agents = orchestrator.registry if hasattr(orchestrator, "registry") else None
                asyncio.create_task(pipeline.start())
            except Exception:
                logger.exception("Failed to start autonomous pipeline")
        try:
            yield
        finally:
            for task_name in ("monitoring_engine_task", "websocket_broadcast_task", "metrics_snapshot_task"):
                t = getattr(fastapi_app.state, task_name, None)
                if t is not None:
                    t.cancel()
                    try: await t
                    except asyncio.CancelledError: pass

    app = FastAPI(title="AegisNex Dashboard", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=get_cors_origins(), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(TLSRedirectMiddleware)
    app.add_middleware(TelemetryMiddleware)
    app.state.limiter = limiter
    app.add_exception_handler(429, _rate_limit_exceeded_handler)

    configure_logging()
    instrument_app(app)

    logger = get_logger(__name__)
    logger.info("AegisNex dashboard starting")

    app.state.services = services or create_services()
    app.state.auth_manager = auth_manager or AuthManager()
    app.state.auth_manager.user_store.seed_default_admin()
    app.state.dashboard_cache = DashboardCache()
    app.state.telemetry_collector = TelemetryCollector()
    repo = app.state.services.platform_repository
    app.state.tenant_manager = TenantManager(repo) if repo is not None else None
    app.state.websocket_manager = WebSocketManager()
    app.state.websocket_poll_interval_seconds = float(os.getenv("AEGISNEX_WS_POLL_INTERVAL_SECONDS", str(DEFAULT_WEBSOCKET_POLL_INTERVAL_SECONDS)))
    app.state.websocket_broadcast_task = None
    app.state.monitoring_engine_task = None
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ---- Helper functions ----
    def current_user(request: FastAPIRequest) -> Any:
        return app.state.auth_manager.get_user_from_token(_extract_token(request))

    def auth_context(request: FastAPIRequest, **extra: Any) -> Dict[str, Any]:
        context: Dict[str, Any] = {"request": request, "user": current_user(request)}
        context.update(extra)
        return context

    def protected_context(request: FastAPIRequest) -> Dict[str, Any] | None:
        user = current_user(request)
        if user is None:
            return None
        context = collect_dashboard_context(app.state.services)
        context["request"] = request
        context["user"] = user
        return context

    def api_context_fn() -> Dict[str, Any]:
        return collect_dashboard_context(app.state.services)

    def actor_from_request(request: FastAPIRequest) -> str:
        user = current_user(request)
        return getattr(user, "email", None) or "anonymous"

    def run_monitoring_once() -> None:
        engine = getattr(app.state.services, "monitoring_engine", None)
        if engine is not None:
            try: engine.run_once()
            except Exception: pass

    def render_report_response(report_type: str, report_format: str) -> Any:
        from src.reporting import OperationalReporter
        repo = getattr(app.state.services, "platform_repository", None)
        database_path = str(getattr(repo, "_sqlite_path", lambda: Path("aegisnex.db"))()) if repo else "aegisnex.db"
        reporter = OperationalReporter(database_path)
        report = reporter.weekly_report() if report_type == "weekly" else reporter.monthly_report()
        if report_format == "json":
            return Response(content=json.dumps(report, indent=2), media_type="application/json", headers={"Content-Disposition": f"attachment; filename={report_type}_report.json"})
        if report_format == "csv":
            output_path = BASE_DIR / "reports" / f"{report_type}_report.csv"
            reporter.export_report(report, output_path, "csv")
            return Response(content=output_path.read_text(encoding="utf-8"), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={report_type}_report.csv"})
        if report_format == "pdf":
            output_path = BASE_DIR / "reports" / f"{report_type}_report.pdf"
            reporter.export_report(report, output_path, "pdf")
            return Response(content=output_path.read_bytes(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={report_type}_report.pdf"})
        return Response(content="Unsupported report format", status_code=400)

    # ---- WebSocket ----
    @app.websocket("/ws/dashboard")
    async def dashboard_websocket(websocket: WebSocket) -> None:
        token = _websocket_token(websocket)
        if not token or app.state.auth_manager.get_user_from_token(token) is None:
            await websocket.close(code=4001, reason="Authentication required")
            return
        manager = app.state.websocket_manager
        await manager.connect(websocket, channel="dashboard")
        try:
            context = await asyncio.to_thread(collect_dashboard_context, app.state.services)
            await websocket.send_json(build_realtime_event("metric_update", build_dashboard_api_snapshot(context), context["timestamp"]))
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket, channel="dashboard")
        except Exception:
            manager.disconnect(websocket, channel="dashboard")
            raise

    @app.websocket("/ws/incidents")
    async def incidents_websocket(websocket: WebSocket) -> None:
        token = _websocket_token(websocket)
        if not token or app.state.auth_manager.get_user_from_token(token) is None:
            await websocket.close(code=4001, reason="Authentication required")
            return
        manager = app.state.websocket_manager
        await manager.connect(websocket, channel="incidents")
        try:
            incidents = app.state.services.incident_manager.list_incidents()
            payload = [i.to_dict() for i in incidents]
            await websocket.send_json({"type": "incident_list", "timestamp": utc_now(), "payload": {"incidents": payload, "count": len(payload)}})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket, channel="incidents")
        except Exception:
            manager.disconnect(websocket, channel="incidents")
            raise

    @app.websocket("/ws/containers")
    async def containers_websocket(websocket: WebSocket) -> None:
        token = _websocket_token(websocket)
        if not token or app.state.auth_manager.get_user_from_token(token) is None:
            await websocket.close(code=4001, reason="Authentication required")
            return
        manager = app.state.websocket_manager
        await manager.connect(websocket, channel="containers")
        try:
            context = await asyncio.to_thread(collect_dashboard_context, app.state.services)
            await websocket.send_json({"type": "container_list", "timestamp": utc_now(), "payload": {"containers": context["containers"], "count": len(context["containers"])}})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket, channel="containers")
        except Exception:
            manager.disconnect(websocket, channel="containers")
            raise

    @app.websocket("/ws/targets")
    async def targets_websocket(websocket: WebSocket) -> None:
        token = _websocket_token(websocket)
        if not token or app.state.auth_manager.get_user_from_token(token) is None:
            await websocket.close(code=4001, reason="Authentication required")
            return
        manager = app.state.websocket_manager
        await manager.connect(websocket, channel="targets")
        try:
            repo = app.state.services.platform_repository
            targets = repo.list_monitoring_targets() if repo else []
            await websocket.send_json({"type": "target_list", "timestamp": utc_now(), "payload": {"targets": targets, "count": len(targets)}})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket, channel="targets")
        except Exception:
            manager.disconnect(websocket, channel="targets")
            raise

    @app.websocket("/ws/containers/{name}/logs")
    async def container_logs_websocket(websocket: WebSocket, name: str) -> None:
        token = _websocket_token(websocket)
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
                await websocket.send_json({"type": "logs_init", "container": name, "logs": log_result["logs"]})
            # Stream live logs
            async for log_line in _stream_container_logs(container):
                try:
                    await websocket.send_json({"type": "log_line", "container": name, "line": log_line})
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
        return RedirectResponse(url="http://localhost:3000/login", status_code=302)

    @app.post("/api/login")
    @limiter.limit("5/minute")
    async def api_login(request: FastAPIRequest) -> Any:
        form = await parse_form_body(request)
        email = form.get("username", "")
        result = app.state.auth_manager.login(email, form.get("password", ""))
        if result is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user, access_token, refresh_token = result
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None:
            repo.record_audit_log(email, "login", "session", email, {})
        response = Response(
            content=json.dumps({
                "access_token": access_token,
                "token_type": "bearer",
                "refresh_token": refresh_token,
            }),
            media_type="application/json",
        )
        _set_auth_cookie(response, access_token, app.state.auth_manager.token_ttl_seconds)
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
            },
        }

    @app.get("/logout")
    async def logout(request: FastAPIRequest) -> Any:
        token = _extract_token(request)
        user = app.state.auth_manager.get_user_from_token(token)
        app.state.auth_manager.logout(token)
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None and user is not None:
            repo.record_audit_log(user.email, "logout", "session", user.email, {})
        response = RedirectResponse(url="http://localhost:3000/login", status_code=302)
        response.delete_cookie("aegisnex_session", path="/")
        return response

    # ---- Protected template pages ----
    @app.get("/")
    def dashboard_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="dashboard.html", context=ctx, request=request)

    @app.get("/infrastructure")
    def infrastructure_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="infrastructure.html", context=ctx, request=request)

    @app.get("/containers")
    def containers_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="containers.html", context=ctx, request=request)

    @app.get("/incidents")
    def incidents_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="incidents.html", context=ctx, request=request)

    @app.get("/actions")
    def actions_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="actions.html", context=ctx, request=request)

    @app.get("/reports")
    def reports_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        ctx.update(build_reports_context(app.state.services))
        return templates.TemplateResponse(name="reports.html", context=ctx, request=request)

    @app.get("/reports/{report_type}/{report_format}")
    def download_report(request: FastAPIRequest, report_type: str, report_format: str) -> Any:
        user = current_user(request)
        if user is None: return RedirectResponse(url="/login", status_code=303)
        return render_report_response(report_type, report_format)

    @app.get("/notifications")
    def notifications_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        ctx.update(build_notifications_context(app.state.services))
        return templates.TemplateResponse(name="notifications.html", context=ctx, request=request)

    @app.get("/mcp")
    def mcp_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        ctx.update(build_mcp_context())
        return templates.TemplateResponse(name="mcp.html", context=ctx, request=request)

    @app.get("/integrations")
    def integrations_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        ctx.update(build_integrations_context(app.state.services))
        return templates.TemplateResponse(name="integrations.html", context=ctx, request=request)

    @app.get("/settings")
    def settings_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(name="settings.html", context=ctx, request=request)

    @app.get("/audit")
    def audit_page(request: FastAPIRequest) -> Any:
        ctx = protected_context(request)
        if ctx is None: return RedirectResponse(url="/login", status_code=303)
        repo = getattr(app.state.services, "platform_repository", None)
        logs = repo.list_audit_logs(limit=100) if repo else []
        ctx["logs"] = logs
        return templates.TemplateResponse(name="audit.html", context=ctx, request=request)

    # ---- Authenticated API endpoints (Viewer: read-only) ----
    @app.get("/api/system-health")
    def api_system_health(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        ctx = api_context_fn()
        return {"timestamp": ctx["timestamp"], "health_score": ctx["health_score"], "metrics": ctx["metrics"], "active_incident_count": len(ctx["active_incidents"]), "running_container_count": len(ctx["running_containers"])}

    @app.get("/api/containers")
    def api_containers(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        ctx = api_context_fn()
        return {"timestamp": ctx["timestamp"], "containers": ctx["containers"], "running_containers": ctx["running_containers"], "count": len(ctx["containers"])}

    @app.get("/api/incidents")
    def api_incidents(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        limit = int(request.query_params.get("limit", 100))
        offset = int(request.query_params.get("offset", 0))
        limit = max(1, min(limit, 1000))
        repo = app.state.services.platform_repository
        if repo is None:
            ctx = api_context_fn()
            incidents = ctx["active_incidents"] + ctx["resolved_incidents"]
            incidents.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
            return {"active_incidents": ctx["active_incidents"], "resolved_incidents": ctx["resolved_incidents"], "recent_incidents": ctx["recent_incidents"], "incidents": incidents[:limit], "active_count": len(ctx["active_incidents"]), "resolved_count": len(ctx["resolved_incidents"]), "count": len(incidents), "limit": limit, "offset": offset}
        all_incidents = repo.list_incidents(limit=limit, offset=offset)
        total = repo.fetch_all("incidents", limit=0, offset=0)
        active = [i for i in all_incidents if i.get("incident_status") in {"active", "acknowledged"}]
        resolved = [i for i in all_incidents if i.get("incident_status") == "resolved"]
        return {"active_incidents": active, "resolved_incidents": resolved, "recent_incidents": all_incidents[:6], "incidents": all_incidents, "active_count": len(active), "resolved_count": len(resolved), "count": len(all_incidents), "total": len(total), "limit": limit, "offset": offset}

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
            timeline = [{"id": 0, "incident_id": incident_id, "timestamp": incident.get("timestamp"), "from_status": None, "to_status": incident.get("incident_status", incident.get("status", "active")), "actor": "system", "details": {"reason": "created"}}]
        return {"incident": incident, "timeline": timeline, "count": len(timeline)}

    @app.get("/api/metrics")
    def api_metrics(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        ctx = api_context_fn()
        return {"timestamp": ctx["timestamp"], "metrics": ctx["metrics"], "network": ctx["network"], "chart_data": ctx["chart_data"]["metrics"]}

    @app.get("/api/metrics/history")
    def api_metrics_history(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        minutes = int(request.query_params.get("minutes", 60))
        minutes = max(1, min(minutes, 1440))
        repo = app.state.services.platform_repository
        if repo is None:
            return {"history": [], "count": 0}
        rows = repo.fetch_all("metrics_snapshots")
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
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
    def api_notifications(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        ctx = api_context_fn()
        rows = storage_rows(app.state.services, "notifications")
        rows = sorted(rows, key=lambda r: str(r.get("timestamp", "")), reverse=True)
        return {"notification_stats": ctx["notification_stats"], "notifications": rows[:25], "count": len(rows)}

    @app.get("/api/remediations")
    def api_remediations(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        ctx = api_context_fn()
        return {"actions": ctx["actions"], "recent_remediations": ctx["recent_remediations"], "count": len(ctx["actions"])}

    @app.get("/api/dashboard")
    def api_dashboard(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        return build_dashboard_api_snapshot(collect_dashboard_context(app.state.services))

    @app.get("/api/mcp")
    def api_mcp(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        return build_mcp_context()

    @app.get("/api/http-monitoring")
    def api_http_monitoring(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        monitor = getattr(app.state.services, "http_monitor", None)
        if monitor is not None:
            return monitor.run({})
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None:
            return build_monitoring_summary(repo, "http")
        return {"status": "disabled", "timestamp": utc_now(), "availability_percent": 100.0, "available_count": 0, "total_count": 0, "checks": []}

    @app.get("/api/ssl-monitoring")
    def api_ssl_monitoring(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        monitor = getattr(app.state.services, "ssl_monitor", None)
        if monitor is not None:
            return monitor.run({})
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None:
            return build_monitoring_summary(repo, "ssl")
        return {"status": "disabled", "timestamp": utc_now(), "warning_count": 0, "total_count": 0, "checks": []}

    @app.get("/api/tcp-monitoring")
    def api_tcp_monitoring(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        monitor = getattr(app.state.services, "tcp_monitor", None)
        if monitor is not None:
            return monitor.run({})
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None:
            return build_monitoring_summary(repo, "tcp")
        return {"status": "disabled", "timestamp": utc_now(), "availability_percent": 100.0, "reachable_count": 0, "total_count": 0, "checks": []}

    @app.get("/api/audit-logs")
    def api_audit_logs(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None: return {"logs": [], "count": 0}
        limit = int(request.query_params.get("limit", 100))
        offset = int(request.query_params.get("offset", 0))
        limit = max(1, min(limit, 1000))
        logs = repo.list_audit_logs(limit=limit, offset=offset)
        total = repo.fetch_all("audit_logs", limit=0, offset=0)
        return {"logs": logs, "count": len(logs), "total": len(total), "limit": limit, "offset": offset}

    @app.get("/api/reports")
    def api_reports(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        return build_reports_context(app.state.services)

    @app.get("/api/reports/{report_type}/{report_format}")
    def api_download_report(report_type: str, report_format: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        return render_report_response(report_type, report_format)

    @app.get("/api/monitoring-targets")
    def api_monitoring_targets(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None: return {"targets": [], "count": 0}
        targets = repo.list_monitoring_targets(include_inactive=True)
        latest_results = repo.latest_check_results()
        latest_by_target = {str(r.get("target_id") or r.get("target_name")): r for r in latest_results}
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
    def api_monitoring_target_history(target_id: int, request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None: return {"history": [], "count": 0}
        rows = repo.check_history(target_id, limit=100)
        return {"history": rows, "count": len(rows)}

    @app.get("/api/integrations")
    def api_integrations(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        return build_integrations_context(app.state.services)

    @app.get("/api/integrations/catalog")
    def api_integrations_catalog(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        from src.integrations.marketplace import get_marketplace_catalog
        cat = get_marketplace_catalog()
        return {"catalog": cat, "count": len(cat)}

    @app.get("/api/integrations/installed")
    def api_integrations_installed(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        from src.integrations.marketplace import get_installed_integrations
        inst = get_installed_integrations()
        return {"integrations": inst, "count": len(inst)}

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
            repo.record_audit_log(user.email if user else "anonymous", "install", "integration", name, {})
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
            repo.record_audit_log(user.email if user else "anonymous", "uninstall", "integration", name, {})
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
            repo.record_audit_log(user.email if user else "anonymous", "update", "integration", name, {})
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
                config = {"credentials": inst.get("credentials", {}), "settings": inst.get("settings", {})}
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

    @app.get("/api/system-info")
    def api_system_info(request: FastAPIRequest) -> Dict[str, Any]:
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
    def api_get_settings(request: FastAPIRequest) -> Dict[str, Any]:
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
            incident = app.state.services.incident_manager.acknowledge_incident(incident_id, actor=user.email)
        except KeyError:
            return Response(content="Incident not found", status_code=404)
        app.state.services.platform_repository.record_audit_log(user.email, "acknowledge", "incident", incident_id, {})
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
            incident = app.state.services.incident_manager.resolve_incident(incident_id, actor=user.email, resolution_notes=notes)
        except KeyError:
            return Response(content="Incident not found", status_code=404)
        app.state.services.platform_repository.record_audit_log(user.email, "resolve", "incident", incident_id, {"resolution_notes": notes})
        return incident.to_dict()

    @app.post("/api/incidents/{incident_id}/reopen")
    def api_reopen_incident(incident_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        try:
            incident = app.state.services.incident_manager.reopen_incident(incident_id, actor=user.email)
        except KeyError:
            return Response(content="Incident not found", status_code=404)
        app.state.services.platform_repository.record_audit_log(user.email, "reopen", "incident", incident_id, {})
        return incident.to_dict()

    # ---- Operator: container actions ----
    @app.post("/api/containers/{name}/start")
    def api_container_start(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        scanner = app.state.services.docker_scanner
        result = scanner.start_container(name)
        if result.get("status") == "error":
            return Response(content=json.dumps(result), status_code=404, media_type="application/json")
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(user.email if user else "anonymous", "container_start", "container", name, {})
        return result

    @app.post("/api/containers/{name}/stop")
    def api_container_stop(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        scanner = app.state.services.docker_scanner
        result = scanner.stop_container(name)
        if result.get("status") == "error":
            return Response(content=json.dumps(result), status_code=404, media_type="application/json")
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(user.email if user else "anonymous", "container_stop", "container", name, {})
        return result

    @app.post("/api/containers/{name}/restart")
    def api_container_restart(name: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        scanner = app.state.services.docker_scanner
        result = scanner.restart_container(name)
        if result.get("status") == "error":
            return Response(content=json.dumps(result), status_code=404, media_type="application/json")
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(user.email if user else "anonymous", "container_restart", "container", name, {})
        return result

    @app.get("/api/containers/{name}/logs")
    def api_container_logs(name: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        tail = int(request.query_params.get("tail", 100))
        scanner = app.state.services.docker_scanner
        result = scanner.get_container_logs(name, tail=tail)
        if result.get("status") == "error":
            return Response(content=json.dumps(result), status_code=404, media_type="application/json")
        return result

    @app.get("/api/containers/{name}/inspect")
    def api_container_inspect(name: str, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        scanner = app.state.services.docker_scanner
        try:
            import docker
            client = docker.from_env(timeout=5)
            container = client.containers.get(name)
            attrs = container.attrs
            return {"status": "ok", "container": name, "inspect": attrs}
        except docker.errors.NotFound:
            return Response(content=json.dumps({"status": "error", "message": "Container not found"}), status_code=404, media_type="application/json")
        except docker.errors.DockerException as exc:
            return Response(content=json.dumps({"status": "error", "message": str(exc)}), status_code=503, media_type="application/json")

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
        if repo is None: return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
            target = repo.create_monitoring_target(payload, actor=user.email if user else "anonymous")
            run_monitoring_once()
            return target
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.put("/api/monitoring-targets/{target_id}")
    async def api_update_monitoring_target(target_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None: return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
            target = repo.update_monitoring_target(target_id, payload, actor=user.email if user else "anonymous")
            if target is None: return Response(content="Monitoring target not found", status_code=404)
            run_monitoring_once()
            return target
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    @app.delete("/api/monitoring-targets/{target_id}")
    def api_delete_monitoring_target(target_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None: return Response(content="Platform database unavailable", status_code=503)
        deleted = repo.delete_monitoring_target(target_id, actor=user.email if user else "anonymous")
        if not deleted: return Response(content="Monitoring target not found", status_code=404)
        return {"status": "ok"}

    @app.post("/api/monitoring-targets/{target_id}/run")
    def api_run_monitoring_target(target_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        engine = getattr(app.state.services, "monitoring_engine", None)
        if engine is None: return Response(content="Monitoring engine unavailable", status_code=503)
        result = engine.run_target(target_id, actor=user.email if user else "anonymous")
        if result is None: return Response(content="Monitoring target not found", status_code=404)
        return result

    # ---- Operator: notification channels ----
    @app.get("/api/notification-channels")
    def api_list_notification_channels(request: FastAPIRequest) -> Dict[str, Any]:
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
            channel = repo.create_notification_channel(payload, actor=user.email if user else "anonymous")
            return channel
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
            channel = repo.update_notification_channel(channel_id, payload, actor=user.email if user else "anonymous")
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
        deleted = repo.delete_notification_channel(channel_id, actor=user.email if user else "anonymous")
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
            matches = [c for c in channels if str(c.get("channel_type", "")).lower() == channel_type]
            if matches:
                config = matches[0].get("config", {})
                return await _send_test_notification(channel_type, config, test_message)
        try:
            config_obj = Config.load()
            if channel_type == "email" and config_obj.smtp.enabled:
                return await _send_test_notification("email", {
                    "host": config_obj.smtp.host,
                    "port": config_obj.smtp.port,
                    "username": config_obj.smtp.username,
                    "password": config_obj.smtp.password,
                    "recipient": config_obj.smtp.recipient,
                    "sender": config_obj.smtp.username,
                }, test_message)
            if channel_type == "slack" and config_obj.notifications.slack.enabled:
                return await _send_test_notification("slack", {"webhook_url": config_obj.notifications.slack.webhook_url}, test_message)
            if channel_type == "discord" and config_obj.notifications.discord.enabled:
                return await _send_test_notification("discord", {"webhook_url": config_obj.notifications.discord.webhook_url}, test_message)
        except Exception:
            pass
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(user.email if user else "anonymous", "test_notification", "notification_channel", channel_type, {})
        return result

    async def _send_test_notification(channel_type: str, config: Dict[str, Any], test_message: str) -> Any:
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
                from urllib.request import Request as _Request, urlopen as _urlopen
                payload = _json.dumps({"text": test_message} if channel_type == "slack" else {"content": test_message}).encode("utf-8")
                req = _Request(webhook_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
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
            repo.record_audit_log(user.email, "update", "settings", "all", {"keys": list(payload.keys())})
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
            repo.record_audit_log(user.email if user else "anonymous", "delete", "incident", incident_id, {})
        return {"status": "ok"}

    # ---- Admin: user management ----
    @app.get("/api/users")
    def api_list_users(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"users": [], "count": 0}
        rows = repo.fetch_all("users")
        sanitized = []
        for row in rows:
            sanitized.append({
                "id": row.get("id"),
                "email": row.get("email"),
                "role": row.get("role", "viewer"),
                "is_active": bool(row.get("is_active", 0)),
                "is_superuser": bool(row.get("is_superuser", 0)),
                "is_verified": bool(row.get("is_verified", 0)),
                "created_at": row.get("created_at"),
            })
        return {"users": sanitized, "count": len(sanitized)}

    @app.put("/api/users/{user_id}/role")
    def api_update_user_role(user_id: int, request: FastAPIRequest) -> Any:
        user = require_role(*ADMIN_ROLES)(request)
        from fastapi import HTTPException
        role = request.query_params.get("role", "")
        from src.auth import Role
        normalized_role = Role.from_str(role).value
        if role not in Role.valid_roles() and normalized_role not in Role.valid_roles():
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(Role.valid_roles())}")
        store = app.state.auth_manager.user_store
        try:
            from src.auth import _hashlib
            with store._connect() as conn:
                conn.execute("UPDATE users SET role = ? WHERE id = ?", (normalized_role, user_id))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        app.state.services.platform_repository.record_audit_log(user.email, "update_role", "user", str(user_id), {"role": normalized_role})
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
        app.state.services.platform_repository.record_audit_log(admin_user.email, "deactivate", "user", str(user_id), {})
        return {"status": "ok"}

    # ---- Admin: API keys ----
    @app.get("/api/api-keys")
    def api_list_api_keys(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"keys": [], "count": 0}
        keys = repo.list_api_keys()
        sanitized = []
        for k in keys:
            sanitized.append({
                "id": k.get("id"),
                "name": k.get("name"),
                "key_prefix": k.get("key_prefix"),
                "role": k.get("role", "viewer"),
                "is_active": bool(k.get("is_active", False)),
                "created_at": k.get("created_at"),
                "last_used_at": k.get("last_used_at"),
                "request_count": k.get("request_count", 0),
            })
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
        from src.auth import Role
        normalized_role = Role.from_str(role).value
        from src.auth import generate_api_key
        full_key, key_hash, key_prefix = generate_api_key()
        repo.create_api_key(name, key_hash, key_prefix, normalized_role, actor=user.email)
        return {"name": name, "api_key": full_key, "key_prefix": key_prefix, "role": normalized_role}

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
    def api_list_alert_rules(request: FastAPIRequest) -> Dict[str, Any]:
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
            rule = repo.create_alert_rule(payload, actor=user.email)
            return rule
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
        from src.auth import Role
        normalized_role = Role.from_str(role).value
        token = secrets.token_urlsafe(32)
        org_id = payload.get("org_id")
        invite = repo.create_invite(email=email, token=token, role=normalized_role, invited_by=user.email, org_id=org_id)
        return {"invite": invite, "invite_url": f"/accept-invite?token={token}"}

    @app.get("/api/invites")
    def api_list_invites(request: FastAPIRequest) -> Dict[str, Any]:
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
            repo.record_audit_log(user.email, "accept_invite", "user", user.email, {"invited_role": normalized_role})
            response = Response(
                content=json.dumps({"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}),
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
        return {"status": "ok", "message": "If the email exists, a reset link has been sent", "reset_token": token}

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
    def api_list_secrets(request: FastAPIRequest) -> Dict[str, Any]:
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
    def api_audit_logs_filtered(request: FastAPIRequest) -> Dict[str, Any]:
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
            limit=limit, offset=offset,
            actor_filter=actor, action_filter=action,
            resource_type_filter=resource_type, execution_id_filter=execution_id,
        )
        return {"logs": logs, "count": len(logs), "limit": limit, "offset": offset}

    # ---- Enterprise: Approval Workflows ----
    @app.get("/api/approvals")
    def api_list_approvals(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"approvals": [], "count": 0}
        status = request.query_params.get("status") or None
        limit = int(request.query_params.get("limit", 50))
        approvals = repo.list_approval_requests(status=status, limit=limit)
        return {"approvals": approvals, "count": len(approvals)}

    @app.post("/api/approvals/{approval_id}/respond")
    async def api_respond_approval(approval_id: str, request: FastAPIRequest) -> Any:
        user = require_role(*OPERATOR_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return Response(content="Platform database unavailable", status_code=503)
        try:
            payload = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)
        decision = str(payload.get("decision", "")).strip().lower()
        if decision not in ("approved", "rejected"):
            return Response(content="decision must be 'approved' or 'rejected'", status_code=400)
        comment = str(payload.get("comment", "")).strip()
        result = repo.respond_approval(approval_id, decision, reviewed_by=user.email, comment=comment)
        if result is None:
            return Response(content="Approval request not found", status_code=404)
        return result

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
    def api_list_policies(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = app.state.services.platform_repository
        if repo is None:
            return {"policies": [], "count": 0}
        policies = repo.list_policies()
        return {"policies": policies, "count": len(policies)}

    # ---- Enterprise: System Administration ----
    @app.get("/api/admin/diagnostics")
    def api_admin_diagnostics(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        diagnostics: Dict[str, Any] = {
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
    def api_admin_health(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        checks: Dict[str, Any] = {
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
        result = bm.restore_backup(file_path, tables=tables, restore_knowledge=restore_knowledge, actor=user.email)
        return result

    @app.get("/api/backup/list")
    def api_backup_list(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*ADMIN_ROLES)(request)
        repo = app.state.services.platform_repository
        stored = repo.list_backup_records(limit=50) if repo else []
        from src.backup import BackupManager
        bm = BackupManager(repo=repo)
        files = bm.list_backups()
        return {"files": files, "records": stored, "file_count": len(files), "record_count": len(stored)}

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
    compliance_engine = ComplianceEngine(repo=getattr(app.state.services, "platform_repository", None))
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
        engine: ComplianceEngine = request.app.state.compliance_engine
        collector = EvidenceCollector(repo=getattr(request.app.state.services, "platform_repository", None))
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
                headers={"Content-Disposition": f"attachment; filename=compliance_{framework_id}.{report_format}"},
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
        payload, content_type = PrometheusExporter(app.state.services).render()
        return Response(content=payload, media_type=content_type)

    # ---- AI Intelligence Engine ----
    _ai_pending_approvals: Dict[str, Dict[str, Any]] = {}

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
        repo = getattr(app.state.services, "platform_repository", None)
        try:
            result = run_chat(user_request, repo=repo)
        except Exception as exc:
            return Response(content=json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")
        if repo is not None:
            try:
                save_workflow(
                    repo=repo,
                    request=user_request,
                    objective=result.get("answer", "")[:100],
                    result_text=result.get("answer", ""),
                    confidence=result.get("confidence", 0.0),
                    goal_achieved=result.get("goal_achieved", False),
                    steps=result.get("steps", []),
                    observations=result.get("observations", []),
                    corrections=result.get("corrections", []),
                    errors=result.get("errors", []),
                    evidence=result.get("evidence", []),
                    reasoning_summary=result.get("reasoning_summary", ""),
                    remaining_uncertainty=result.get("remaining_uncertainty", ""),
                    provider_used=result.get("provider_used", ""),
                    model_used=result.get("model_used", ""),
                    execution_duration_ms=result.get("execution_duration_ms", 0.0),
                    tools_used=[s.get("node", "") for s in result.get("steps", []) if isinstance(s, dict)],
                    plan_text=result.get("answer", "")[:200],
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
        repo = getattr(app.state.services, "platform_repository", None)
        try:
            result = run_analyze(user_request, repo=repo)
        except Exception as exc:
            return Response(content=json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")
        if repo is not None:
            try:
                save_workflow(
                    repo=repo,
                    request=user_request,
                    objective=result.get("objective", "")[:100],
                    result_text=result.get("final_answer", ""),
                    confidence=result.get("confidence", 0.0),
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
                    execution_duration_ms=result.get("execution_duration_ms", 0.0),
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
        repo = getattr(app.state.services, "platform_repository", None)
        try:
            result = run_plan(user_request, repo=repo)
        except Exception as exc:
            return Response(content=json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")
        return result

    @app.get("/api/ai/history")
    def api_ai_history(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is None:
            return {"history": [], "count": 0}
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))
        limit = max(1, min(limit, 100))
        try:
            rows = list_history(repo, limit=limit, offset=offset)
            total = get_history_count(repo)
            return {"history": rows, "count": len(rows), "total": total}
        except Exception as exc:
            return {"history": [], "count": 0, "error": str(exc)}

    @app.get("/api/ai/workflows")
    def api_ai_workflows(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.intelligence.graph import get_workflows
            return get_workflows()
        except Exception as exc:
            return {"error": str(exc)}

    @app.get("/api/ai/executions")
    def api_ai_executions(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is None:
            return {"executions": [], "count": 0, "stats": {}}
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))
        limit = max(1, min(limit, 100))
        try:
            from src.intelligence.history import list_history, get_history_count, get_history_stats
            rows = list_history(repo, limit=limit, offset=offset)
            total = get_history_count(repo)
            stats = get_history_stats(repo)
            return {"executions": rows, "count": len(rows), "total": total, "stats": stats}
        except Exception as exc:
            return {"executions": [], "count": 0, "stats": {}, "error": str(exc)}

    @app.get("/api/ai/memory")
    def api_ai_memory(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        query = request.query_params.get("query", "")
        memory_type = request.query_params.get("type", "all")
        limit = int(request.query_params.get("limit", 10))
        try:
            from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
            import os
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
            return {"entries": result.entries, "count": result.count, "total": result.total, "type": memory_type, "query": query}
        except Exception as exc:
            return {"entries": [], "count": 0, "error": str(exc)}

    @app.get("/api/ai/tools")
    def api_ai_tools(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.intelligence.tools import list_tool_definitions, TOOL_REGISTRY
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
    def api_list_skills(request: FastAPIRequest) -> Dict[str, Any]:
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
            result = await engine.execute_skill(skill_id, context)
            return result
        except Exception as exc:
            return Response(content=json.dumps({"status": "error", "error": str(exc)}), status_code=500, media_type="application/json")

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
            return Response(content=json.dumps({"status": "error", "error": str(exc)}), status_code=500, media_type="application/json")

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
        app.state._ai_pending_approvals[approval_id] = {"status": "approved", "approved_at": utc_now()}
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(user.email if user else "anonymous", "approve", "ai_approval", approval_id, {})
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
        app.state._ai_pending_approvals[approval_id] = {"status": "rejected", "rejected_at": utc_now()}
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(user.email if user else "anonymous", "reject", "ai_approval", approval_id, {})
        return {"status": "rejected", "approval_id": approval_id}

    @app.get("/api/ai/pending-approvals")
    def api_ai_pending_approvals(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        pending = {k: v for k, v in app.state._ai_pending_approvals.items() if v.get("status") == "pending"}
        return {"approvals": pending, "count": len(pending)}

    # ---- Sprint 9: Runbooks, Workflows, Timeline, Risk, Policies ----
    @app.get("/api/runbooks")
    def api_list_runbooks(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.intelligence.runbooks.registry import get_registry
            registry = get_registry()
            return {"runbooks": [r.to_dict() for r in registry.list_all()], "count": registry.count()}
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
            from src.intelligence.runbooks.registry import get_registry
            from src.intelligence.runbooks.engine import RunbookEngine
            registry = get_registry()
            engine = RunbookEngine(registry)
            result = engine.execute(runbook_name)
            return result
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
            return {"status": "completed", "confidence": result.get("confidence", 0.0), "goal_achieved": result.get("goal_achieved", False), "workflow_triggered": result.get("workflow_triggered", ""), "runbook": result.get("current_runbook", "")}
        except Exception as exc:
            return Response(content=json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")

    @app.get("/api/workflows/history")
    def api_workflow_history(request: FastAPIRequest) -> Dict[str, Any]:
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
    def api_ai_timeline(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
            import os
            db_path = os.getenv("AEGIS_AI_MEMORY_DB", "ai_memory.db")
            store = SQLiteMemoryStore(db_path=db_path)
            conversations = store.get_recent_conversations(limit=20)
            learnings = store.get_recent_learnings(limit=20)
            timeline = []
            for c in conversations:
                timeline.append({"type": "conversation", "timestamp": c.get("created_at", ""), "summary": c.get("request", "")[:120], "confidence": c.get("confidence", 0.0), "goal_achieved": bool(c.get("goal_achieved", 0))})
            for l in learnings:
                timeline.append({"type": "learning", "timestamp": l.get("created_at", ""), "summary": l.get("root_cause", "")[:120], "category": l.get("category", ""), "severity": l.get("severity", "info")})
            timeline.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
            return {"timeline": timeline[:50], "count": len(timeline[:50])}
        except Exception as exc:
            return {"timeline": [], "count": 0, "error": str(exc)}

    @app.get("/api/ai/policies")
    def api_ai_policies(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.intelligence.policy import PolicyEngine
            engine = PolicyEngine()
            return {"policies": engine.list_policies(), "count": len(engine.list_policies())}
        except Exception as exc:
            return {"policies": [], "count": 0, "error": str(exc)}

    @app.get("/api/ai/risk")
    def api_ai_risk(request: FastAPIRequest) -> Dict[str, Any]:
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
        store = SQLiteMemoryStore(db_path=os.getenv("AEGIS_AI_MEMORY_DB", "ai_memory.db"))
        rag = RAGEngine()
        indexer = KnowledgeIndexer(store=store, rag=rag)
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
            temp_dir = BASE_DIR / "data" / "knowledge_uploads"
            temp_dir.mkdir(parents=True, exist_ok=True)
            dest = temp_dir / filename
            dest.write_bytes(content_bytes)
            _, _, indexer, _ = _get_knowledge_services()
            count = indexer.index_document(str(dest))
            return {"status": "ok", "document": filename, "chunks_indexed": count, "path": str(dest)}
        except Exception as exc:
            return Response(content=json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")

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

    @app.get("/api/knowledge/search")
    def api_knowledge_search(request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        query = request.query_params.get("q", "").strip()
        limit = int(request.query_params.get("limit", 10))
        limit = max(1, min(limit, 100))
        if not query:
            return {"results": [], "count": 0}
        _, _, indexer, retriever = _get_knowledge_services()
        doc_types_str = request.query_params.get("doc_types", "")
        if doc_types_str:
            doc_types = [t.strip() for t in doc_types_str.split(",") if t.strip()]
            results = retriever.retrieve_with_filters(query, doc_types=doc_types, limit=limit)
        else:
            results = retriever.retrieve(query, limit=limit)
        return {"results": results, "count": len(results), "query": query}

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
            return Response(content="approval_id and decision (approve/reject) are required", status_code=400)
        key = f"approval_{approval_id}"
        if key in app.state._ai_pending_approvals:
            app.state._ai_pending_approvals[key] = {"status": decision, "responded_at": utc_now()}
        status_text = "approved" if decision == "approve" else "rejected"
        repo = app.state.services.platform_repository
        if repo is not None:
            repo.record_audit_log(user.email if user else "anonymous", decision, "ai_approval", approval_id, {})
        return {"status": status_text, "approval_id": approval_id}

    # ---- Enterprise Search ----
    @app.get("/api/search")
    def api_search(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        q = request.query_params.get("q", "").strip()
        domain = request.query_params.get("domain", "all").strip()
        limit = int(request.query_params.get("limit", 20))
        limit = max(1, min(limit, 100))
        try:
            from src.search.engine import SearchEngine
            import os as _os
            from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
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
            return {"results": [], "total": 0, "domains": {}, "query": q, "duration_ms": 0, "error": str(exc)}

    @app.get("/api/search/domains")
    def api_search_domains(request: FastAPIRequest) -> Dict[str, Any]:
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
                repo.record_audit_log(user.email if user else "anonymous", "reindex", "search", ",".join(domains) if domains else "all", {})
            return {"status": "ok", "domains": result}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @app.get("/api/search/stats")
    def api_search_stats(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        try:
            from src.search.indexer import SearchIndexer
            repo = app.state.services.platform_repository
            indexer = SearchIndexer(repo)
            stats = indexer.get_index_stats()
            return stats
        except Exception as exc:
            return {"index_size": 0, "domains": {}, "last_indexed": None, "error": str(exc)}

    # ---- Multi-Agent Collaboration endpoints ----
    @app.get("/api/agents")
    def api_list_agents(request: FastAPIRequest) -> Dict[str, Any]:
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
            result = await orchestrator.dispatch_task(task, target_agent=target)
            return result
        except Exception as exc:
            return Response(content=json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")

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
            result = await orchestrator.collaborate(agent_ids, task)
            return result
        except Exception as exc:
            return Response(content=json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")

    @app.get("/api/agents/state")
    def api_agent_state(request: FastAPIRequest) -> Dict[str, Any]:
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
                    {"agent_id": r.agent_id, "success": r.success, "summary": r.summary,
                     "duration_ms": r.duration_ms}
                    for r in results
                ],
                "count": len(results),
            }
        except Exception as exc:
            return Response(content=json.dumps({"error": str(exc)}), status_code=500, media_type="application/json")

    # ---- Telemetry endpoints ----
    @app.get("/api/telemetry/api-stats")
    def api_telemetry_api_stats(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = int(request.query_params.get("hours", 24))
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_api_stats(hours=max(1, min(hours, 168)))

    @app.get("/api/telemetry/workflow-stats")
    def api_telemetry_workflow_stats(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = int(request.query_params.get("hours", 24))
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_workflow_stats(hours=max(1, min(hours, 168)))

    @app.get("/api/telemetry/agent-stats")
    def api_telemetry_agent_stats(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = int(request.query_params.get("hours", 24))
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_agent_stats(hours=max(1, min(hours, 168)))

    @app.get("/api/telemetry/tool-failures")
    def api_telemetry_tool_failures(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = int(request.query_params.get("hours", 24))
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_tool_failure_stats(hours=max(1, min(hours, 168)))

    @app.get("/api/telemetry/approval-stats")
    def api_telemetry_approval_stats(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        hours = int(request.query_params.get("hours", 24))
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_approval_stats(hours=max(1, min(hours, 168)))

    @app.get("/api/telemetry/dashboard")

    # ---- Autonomous Operations ----

    @app.get("/api/autonomous/status")
    def api_autonomous_status(request: FastAPIRequest) -> Dict[str, Any]:
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
    def api_autonomous_executions(request: FastAPIRequest) -> Dict[str, Any]:
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
        return Response(content=json.dumps({"error": "Execution not found"}), status_code=404, media_type="application/json")

    @app.get("/api/autonomous/pipeline")
    def api_autonomous_pipeline_results(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        pipeline = getattr(request.app.state.services, "autonomous_pipeline", None)
        if pipeline:
            return {"results": pipeline.get_results(limit=20)}
        return {"results": []}

    @app.get("/api/autonomous/policies")
    def api_autonomous_policies(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        policy = getattr(request.app.state.services, "policy_engine", None)
        if policy:
            return {"policies": policy.list_policies(), "safe": policy.get_safe_actions(), "approval": policy.get_approval_actions(), "forbidden": policy.get_forbidden_actions()}
        return {"policies": [], "safe": [], "approval": [], "forbidden": []}

    @app.get("/api/autonomous/healing")
    def api_autonomous_healing(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        healing = getattr(request.app.state.services, "self_healing_engine", None)
        if healing:
            return {"actions": healing.history}
        return {"actions": []}
    def api_telemetry_dashboard(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        collector: TelemetryCollector = request.app.state.telemetry_collector
        return collector.get_dashboard()

    # ---- Multi-Tenant endpoints ----
    @app.get("/api/orgs")
    def api_list_orgs(request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        mgr: TenantManager = request.app.state.tenant_manager
        orgs = mgr.list_organizations()
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
        mgr: TenantManager = request.app.state.tenant_manager
        try:
            org = mgr.get_organization(org_id)
            return org.__dict__
        except ValueError:
            return Response(content="Organization not found", status_code=404)

    @app.put("/api/orgs/{org_id}")
    async def api_update_org(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
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
        mgr: TenantManager = request.app.state.tenant_manager
        if not mgr.deactivate_organization(org_id):
            return Response(content="Organization not found", status_code=404)
        return {"status": "ok"}

    @app.get("/api/orgs/{org_id}/teams")
    def api_list_teams(org_id: int, request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        mgr: TenantManager = request.app.state.tenant_manager
        teams = mgr.list_teams(org_id)
        return {"teams": [t.__dict__ for t in teams], "count": len(teams)}

    @app.post("/api/orgs/{org_id}/teams")
    async def api_create_team(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
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
    def api_list_projects(org_id: int, request: FastAPIRequest) -> Dict[str, Any]:
        require_role(*VIEWER_ROLES)(request)
        team_id_param = request.query_params.get("team_id")
        team_id = int(team_id_param) if team_id_param else None
        mgr: TenantManager = request.app.state.tenant_manager
        projects = mgr.list_projects(org_id, team_id=team_id)
        return {"projects": [p.__dict__ for p in projects], "count": len(projects)}

    @app.post("/api/orgs/{org_id}/projects")
    async def api_create_project(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*OPERATOR_ROLES)(request)
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
        mgr: TenantManager = request.app.state.tenant_manager
        try:
            return mgr.get_org_stats(org_id)
        except ValueError:
            return Response(content="Organization not found", status_code=404)

    @app.get("/api/orgs/{org_id}/users")
    def api_org_users(org_id: int, request: FastAPIRequest) -> Any:
        require_role(*VIEWER_ROLES)(request)
        from src.multitenant.models import TenantUser
        p = request.app.state.services.platform_repository
        if p is None:
            return {"users": [], "count": 0}
        rows = p._fetch_all("SELECT u.id, u.email, tu.role FROM tenant_users tu JOIN users u ON u.id = tu.user_id WHERE tu.org_id = ?", (org_id,))
        return {"users": rows, "count": len(rows)}

    # ---- Public health endpoints ----
    @app.get("/api/health")
    def api_health() -> Dict[str, Any]:
        return {"status": "ok", "timestamp": utc_now(), "service": "aegisnex"}

    @app.get("/api/health/ready")
    def api_health_ready() -> Dict[str, Any]:
        repo = getattr(app.state.services, "platform_repository", None)
        if repo is not None:
            db_status = repo.health_check()
            if db_status.get("status") != "connected":
                return {"status": "not_ready", "reason": "database_unavailable"}
        return {"status": "ready"}

    @app.get("/api/health/live")
    def api_health_live() -> Dict[str, Any]:
        return {"status": "alive"}

    @app.get("/api/health/status")
    def api_health_status(request: FastAPIRequest) -> Dict[str, Any]:
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


try:
    app = create_app()
except (RuntimeError, AttributeError):
    app = None
