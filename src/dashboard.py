"""FastAPI dashboard for AegisNex operational visibility."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import asyncio
from pathlib import Path
import json
import os
from typing import Any, Dict, List, Optional

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse as StarletteRedirect

from src.auth import AuthManager, User, Role, parse_form_body
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

try:
    from fastapi import Request as FastAPIRequest
except ModuleNotFoundError:
    FastAPIRequest = Any


BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DEVELOPMENT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]
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
    """Extract and validate the authenticated user from the request."""
    token = _extract_token(request)
    user = auth_manager.get_user_from_token(token)
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_role(*roles: str):
    """Dependency factory: require the authenticated user to have one of the specified roles."""
    def role_checker(request: FastAPIRequest) -> User:
        auth_manager: AuthManager = request.app.state.auth_manager
        user = require_auth(request, auth_manager)
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
                context = collect_dashboard_context(app.state.services)
                events = build_realtime_events(context, previous_context)
                for event in events:
                    await manager.broadcast_with_backoff(event)
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


def create_app(services: Optional[DashboardServices] = None, auth_manager: AuthManager | None = None) -> Any:
    try:
        from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import RedirectResponse
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
    except ModuleNotFoundError as exc:
        raise RuntimeError("Dashboard dependencies are missing. Install requirements.txt first.") from exc

    @asynccontextmanager
    async def lifespan(fastapi_app: Any) -> Any:
        fastapi_app.state.websocket_broadcast_task = asyncio.create_task(run_dashboard_broadcaster(fastapi_app, fastapi_app.state.websocket_poll_interval_seconds))
        fastapi_app.state.monitoring_engine_task = None
        if getattr(fastapi_app.state.services, "monitoring_engine", None) is not None:
            fastapi_app.state.monitoring_engine_task = asyncio.create_task(fastapi_app.state.services.monitoring_engine.run_forever())
        try:
            yield
        finally:
            for task_name in ("monitoring_engine_task", "websocket_broadcast_task"):
                t = getattr(fastapi_app.state, task_name, None)
                if t is not None:
                    t.cancel()
                    try: await t
                    except asyncio.CancelledError: pass

    app = FastAPI(title="AegisNex Dashboard", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=get_cors_origins(), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(TLSRedirectMiddleware)
    app.state.limiter = limiter
    app.add_exception_handler(429, _rate_limit_exceeded_handler)

    app.state.services = services or create_services()
    app.state.auth_manager = auth_manager or AuthManager()
    app.state.dashboard_cache = DashboardCache()
    app.state.websocket_manager = WebSocketManager(cache=app.state.dashboard_cache)
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
        manager = app.state.websocket_manager
        await manager.connect(websocket)
        try:
            context = collect_dashboard_context(app.state.services)
            await websocket.send_json(build_realtime_event("metric_update", build_dashboard_api_snapshot(context), context["timestamp"]))
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception:
            manager.disconnect(websocket)
            raise

    # ---- Public auth pages ----
    @app.get("/login")
    def login_page(request: FastAPIRequest) -> Any:
        return templates.TemplateResponse(name="login.html", context=auth_context(request), request=request)

    @app.post("/login")
    @limiter.limit("5/minute")
    async def login(request: FastAPIRequest) -> Any:
        form = await parse_form_body(request)
        result = app.state.auth_manager.login(form.get("email", ""), form.get("password", ""))
        if result is None:
            return templates.TemplateResponse(name="login.html", context=auth_context(request, error="Invalid email or password.", email=form.get("email", "")), request=request, status_code=401)
        user, access_token, refresh_token = result
        response = RedirectResponse(url="/", status_code=303)
        _set_auth_cookie(response, access_token, app.state.auth_manager.token_ttl_seconds)
        return response

    @app.get("/register")
    def register_page(request: FastAPIRequest) -> Any:
        return templates.TemplateResponse(name="register.html", context=auth_context(request), request=request)

    @app.post("/register")
    @limiter.limit("3/hour")
    async def register(request: FastAPIRequest) -> Any:
        form = await parse_form_body(request)
        try:
            user, access_token, refresh_token = app.state.auth_manager.register(form.get("email", ""), form.get("password", ""))
        except ValueError as exc:
            return templates.TemplateResponse(name="register.html", context=auth_context(request, error=str(exc), email=form.get("email", "")), request=request, status_code=400)
        response = RedirectResponse(url="/", status_code=303)
        _set_auth_cookie(response, access_token, app.state.auth_manager.token_ttl_seconds)
        return response

    @app.get("/logout")
    async def logout(request: FastAPIRequest) -> Any:
        token = _extract_token(request)
        app.state.auth_manager.logout(token)
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("aegisnex_session")
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

    # ---- Authenticated API endpoints ----
    @app.get("/api/system-health")
    def api_system_health(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        ctx = api_context_fn()
        return {"timestamp": ctx["timestamp"], "health_score": ctx["health_score"], "metrics": ctx["metrics"], "active_incident_count": len(ctx["active_incidents"]), "running_container_count": len(ctx["running_containers"])}

    @app.get("/api/containers")
    def api_containers(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        ctx = api_context_fn()
        return {"timestamp": ctx["timestamp"], "containers": ctx["containers"], "running_containers": ctx["running_containers"], "count": len(ctx["containers"])}

    @app.get("/api/incidents")
    def api_incidents(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
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
        require_auth(request, app.state.auth_manager)
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

    @app.post("/api/incidents/{incident_id}/acknowledge")
    async def api_acknowledge_incident(incident_id: str, request: FastAPIRequest) -> Any:
        user = require_auth(request, app.state.auth_manager)
        try:
            incident = app.state.services.incident_manager.acknowledge_incident(incident_id, actor=user.email)
        except KeyError:
            return Response(content="Incident not found", status_code=404)
        return incident.to_dict()

    @app.post("/api/incidents/{incident_id}/resolve")
    async def api_resolve_incident(incident_id: str, request: FastAPIRequest) -> Any:
        user = require_auth(request, app.state.auth_manager)
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
        return incident.to_dict()

    @app.get("/api/metrics")
    def api_metrics(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        ctx = api_context_fn()
        return {"timestamp": ctx["timestamp"], "metrics": ctx["metrics"], "network": ctx["network"], "chart_data": ctx["chart_data"]["metrics"]}

    @app.get("/api/notifications")
    def api_notifications(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        ctx = api_context_fn()
        rows = storage_rows(app.state.services, "notifications")
        rows = sorted(rows, key=lambda r: str(r.get("timestamp", "")), reverse=True)
        return {"notification_stats": ctx["notification_stats"], "notifications": rows[:25], "count": len(rows)}

    @app.get("/api/remediations")
    def api_remediations(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        ctx = api_context_fn()
        return {"actions": ctx["actions"], "recent_remediations": ctx["recent_remediations"], "count": len(ctx["actions"])}

    @app.get("/api/monitoring-targets")
    def api_monitoring_targets(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
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

    @app.post("/api/monitoring-targets")
    async def api_create_monitoring_target(request: FastAPIRequest) -> Any:
        require_auth(request, app.state.auth_manager)
        user = current_user(request)
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
        require_auth(request, app.state.auth_manager)
        user = current_user(request)
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
        require_auth(request, app.state.auth_manager)
        user = current_user(request)
        repo = app.state.services.platform_repository
        if repo is None: return Response(content="Platform database unavailable", status_code=503)
        deleted = repo.delete_monitoring_target(target_id, actor=user.email if user else "anonymous")
        if not deleted: return Response(content="Monitoring target not found", status_code=404)
        return {"status": "ok"}

    @app.post("/api/monitoring-targets/{target_id}/run")
    def api_run_monitoring_target(target_id: int, request: FastAPIRequest) -> Any:
        require_auth(request, app.state.auth_manager)
        user = current_user(request)
        engine = getattr(app.state.services, "monitoring_engine", None)
        if engine is None: return Response(content="Monitoring engine unavailable", status_code=503)
        result = engine.run_target(target_id, actor=user.email if user else "anonymous")
        if result is None: return Response(content="Monitoring target not found", status_code=404)
        return result

    @app.get("/api/monitoring-targets/{target_id}/history")
    def api_monitoring_target_history(target_id: int, request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        repo = app.state.services.platform_repository
        if repo is None: return {"history": [], "count": 0}
        rows = repo.check_history(target_id, limit=100)
        return {"history": rows, "count": len(rows)}

    @app.get("/api/integrations")
    def api_integrations(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        return build_integrations_context(app.state.services)

    @app.get("/api/mcp")
    def api_mcp(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        return build_mcp_context()

    @app.get("/api/http-monitoring")
    def api_http_monitoring(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        return {"status": "disabled", "timestamp": utc_now(), "availability_percent": 100.0, "available_count": 0, "total_count": 0, "checks": []}

    @app.get("/api/ssl-monitoring")
    def api_ssl_monitoring(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        return {"status": "disabled", "timestamp": utc_now(), "warning_count": 0, "total_count": 0, "checks": []}

    @app.get("/api/tcp-monitoring")
    def api_tcp_monitoring(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
        return {"status": "disabled", "timestamp": utc_now(), "availability_percent": 100.0, "reachable_count": 0, "total_count": 0, "checks": []}

    @app.get("/api/audit-logs")
    def api_audit_logs(request: FastAPIRequest) -> Dict[str, Any]:
        require_auth(request, app.state.auth_manager)
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
        require_auth(request, app.state.auth_manager)
        return build_reports_context(app.state.services)

    @app.get("/api/reports/{report_type}/{report_format}")
    def api_download_report(report_type: str, report_format: str, request: FastAPIRequest) -> Any:
        require_auth(request, app.state.auth_manager)
        return render_report_response(report_type, report_format)

    # ---- /metrics endpoint (protected) ----
    @app.get("/metrics")
    def metrics(request: FastAPIRequest) -> Any:
        metrics_token = os.getenv("AEGISNEX_METRICS_TOKEN", "")
        if metrics_token:
            auth_header = request.headers.get("Authorization", "")
            if not (auth_header == f"Bearer {metrics_token}" or _extract_token(request)):
                raise HTTPException(status_code=401, detail="Authentication required for /metrics")
        elif os.getenv("AEGISNEX_ENV", "development").strip().lower() not in {"development", "dev", "local", "test"}:
            raise HTTPException(status_code=401, detail="Authentication required for /metrics")
        payload, content_type = PrometheusExporter(app.state.services).render()
        return Response(content=payload, media_type=content_type)

    # ---- Public health endpoints ----
    @app.get("/api/health")
    def api_health() -> Dict[str, Any]:
        return {"status": "ok", "timestamp": utc_now(), "database": "unknown"}

    return app


try:
    app = create_app()
except (RuntimeError, AttributeError):
    app = None
