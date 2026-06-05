"""FastAPI dashboard for AegisNex operational visibility."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from typing import Any, Dict, List, Optional

from src.auth import AuthManager, parse_form_body
from src.config import Config
from src.docker_scanner import DockerScanner
from src.guardian import Guardian
from src.incidents import Incident, IncidentManager
from src.monitor import SystemResourceMonitor
from src.notifier import Notifier
from src.orchestrator import SystemHealthChecker
from src.prometheus_exporter import PrometheusExporter
from src.reporting import OperationalReporter
from src.storage import AegisNexRepository

try:
    from fastapi import Request as FastAPIRequest
except ModuleNotFoundError:
    FastAPIRequest = Any


BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


@dataclass
class DashboardServices:
    monitor: SystemResourceMonitor
    docker_scanner: DockerScanner
    incident_manager: IncidentManager
    guardian: Guardian
    restart_history_path: Path
    storage_repository: Any | None = None


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
    storage_repository = AegisNexRepository(config.storage.database_path)
    incident_manager = IncidentManager(
        config.incidents.history_path,
        storage_repository=storage_repository,
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
        storage_repository=storage_repository,
    )
    return DashboardServices(
        monitor=monitor,
        docker_scanner=docker_scanner,
        incident_manager=incident_manager,
        guardian=guardian,
        restart_history_path=Path(config.guardian.restart_history_path),
        storage_repository=storage_repository,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        rows.append(
            {
                "name": name,
                "status": container.get("status", "unknown"),
                "health_status": container.get("health_status", "unknown"),
                "restart_count": int(history.get("attempts", 0)),
                "last_check_timestamp": last_check_timestamp,
            }
        )
    return rows


def build_remediation_actions(
    incidents: List[Incident],
    restart_history: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
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
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def storage_rows(services: DashboardServices, table_name: str) -> List[Dict[str, Any]]:
    repository = services.storage_repository
    if repository is None:
        return []
    try:
        return list(repository.fetch_all(table_name))
    except Exception:
        return []


def build_metric_trends(
    metric_rows: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    now: datetime | None = None,
) -> Dict[str, Dict[str, Any]]:
    current_time = now or datetime.now(timezone.utc)
    window_start = current_time - timedelta(hours=24)
    recent_rows = [
        row
        for row in metric_rows
        if (parse_timestamp(row.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
        >= window_start
    ]
    recent_rows.sort(key=lambda row: str(row.get("timestamp", "")))
    if not recent_rows:
        label = current_time.strftime("%H:%M")
        return {
            "cpu": {
                "labels": [label],
                "values": [_safe_float(metrics.get("cpu_percent"))],
            },
            "memory": {
                "labels": [label],
                "values": [_safe_float(metrics.get("ram_percent"))],
            },
        }
    labels = [
        (parse_timestamp(row.get("timestamp")) or current_time).strftime("%H:%M")
        for row in recent_rows
    ]
    return {
        "cpu": {
            "labels": labels,
            "values": [_safe_float(row.get("cpu_percent")) for row in recent_rows],
        },
        "memory": {
            "labels": labels,
            "values": [_safe_float(row.get("memory_percent")) for row in recent_rows],
        },
    }


def build_hourly_event_trend(
    rows: List[Dict[str, Any]],
    now: datetime | None = None,
) -> Dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    start_hour = (current_time - timedelta(hours=23)).replace(
        minute=0, second=0, microsecond=0
    )
    buckets = {
        start_hour + timedelta(hours=index): 0
        for index in range(24)
    }
    for row in rows:
        timestamp = parse_timestamp(row.get("timestamp"))
        if timestamp is None:
            continue
        bucket = timestamp.replace(minute=0, second=0, microsecond=0)
        if bucket in buckets:
            buckets[bucket] += 1
    return {
        "labels": [bucket.strftime("%H:%M") for bucket in buckets],
        "values": list(buckets.values()),
    }


def build_notification_statistics(
    rows: List[Dict[str, Any]],
) -> Dict[str, int]:
    stats = {
        "email_count": 0,
        "slack_count": 0,
        "discord_count": 0,
        "failed_notifications": 0,
    }
    successful_statuses = {"ok", "sent", "success"}
    for row in rows:
        provider = str(row.get("provider", "")).lower()
        if provider == "email":
            stats["email_count"] += 1
        elif provider == "slack":
            stats["slack_count"] += 1
        elif provider == "discord":
            stats["discord_count"] += 1
        if str(row.get("status", "")).lower() not in successful_statuses:
            stats["failed_notifications"] += 1
    return stats


def build_recent_incidents(
    incidents: List[Incident],
    limit: int = 6,
) -> List[Dict[str, Any]]:
    rows = [incident_to_dict(incident) for incident in incidents]
    rows.sort(key=lambda row: str(row.get("timestamp", "")), reverse=True)
    return rows[:limit]


def build_recent_remediations(
    storage_remediations: List[Dict[str, Any]],
    fallback_actions: List[Dict[str, Any]],
    limit: int = 6,
) -> List[Dict[str, Any]]:
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
    normalized.sort(key=lambda row: str(row.get("timestamp", "")), reverse=True)
    return normalized[:limit]


def calculate_health_score(
    metrics: Dict[str, Any],
    containers: List[Dict[str, Any]],
    active_incident_count: int,
) -> Dict[str, Any]:
    cpu = _safe_float(metrics.get("cpu_percent"))
    memory = _safe_float(metrics.get("ram_percent"))
    unhealthy_containers = len(
        [
            container
            for container in containers
            if container.get("status") != "running"
            or container.get("health_status") not in {"healthy", "none", None, ""}
        ]
    )
    container_penalty = (
        (unhealthy_containers / len(containers)) * 25 if containers else 0.0
    )
    score = 100.0
    score -= min(cpu, 100.0) * 0.25
    score -= min(memory, 100.0) * 0.25
    score -= container_penalty
    score -= min(active_incident_count * 5, 25)
    score = max(0, min(100, round(score)))
    if score >= 80:
        status = "healthy"
        indicator = "green"
    elif score >= 60:
        status = "degraded"
        indicator = "yellow"
    else:
        status = "critical"
        indicator = "red"
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
    normalized = str(value).lower()
    if normalized in {"1", "true", "yes", "ok", "success"}:
        return True
    if normalized in {"0", "false", "no", "failed", "failure"}:
        return False
    return None


def collect_dashboard_context(services: DashboardServices) -> Dict[str, Any]:
    timestamp = utc_now()
    metrics = services.monitor.run({})
    docker_report = services.docker_scanner.run({"include_all": True})
    containers = docker_report.get("containers", []) if docker_report.get("status") == "ok" else []
    incidents = services.incident_manager.list_incidents()
    active_incidents = [incident for incident in incidents if incident.status == "active"]
    resolved_incidents = [
        incident for incident in incidents if incident.status == "resolved"
    ]
    restart_history = load_restart_history(services.restart_history_path)
    metric_rows = storage_rows(services, "metrics_snapshots")
    notification_rows = storage_rows(services, "notifications")
    remediation_rows = storage_rows(services, "remediations")
    actions = build_remediation_actions(incidents, restart_history)
    container_rows = build_container_rows(containers, restart_history, timestamp)
    return {
        "timestamp": timestamp,
        "metrics": metrics,
        "network": get_network_stats(),
        "containers": container_rows,
        "running_containers": [
            container for container in containers if container.get("status") == "running"
        ],
        "active_incidents": [incident_to_dict(incident) for incident in active_incidents],
        "resolved_incidents": [
            incident_to_dict(incident) for incident in resolved_incidents
        ],
        "actions": actions,
        "health_score": calculate_health_score(
            metrics,
            container_rows,
            len(active_incidents),
        ),
        "chart_data": {
            "metrics": build_metric_trends(metric_rows, metrics),
            "incidents": build_hourly_event_trend(
                [incident_to_dict(incident) for incident in incidents]
            ),
            "remediations": build_hourly_event_trend(remediation_rows or actions),
        },
        "recent_incidents": build_recent_incidents(incidents),
        "recent_remediations": build_recent_remediations(remediation_rows, actions),
        "notification_stats": build_notification_statistics(notification_rows),
    }


def build_integrations_context(services: DashboardServices) -> Dict[str, Any]:
    repository = services.storage_repository
    sqlite_status = "connected" if repository is not None else "unavailable"
    if repository is not None:
        try:
            repository.table_names()
        except Exception:
            sqlite_status = "degraded"
    try:
        docker_report = services.docker_scanner.run({"include_all": True})
        docker_status = "connected" if docker_report.get("status") == "ok" else "degraded"
    except Exception:
        docker_status = "degraded"
    return {
        "integrations": [
            {
                "name": "Grafana",
                "status": "configured" if (BASE_DIR / "grafana").exists() else "not configured",
                "description": "Provisioned dashboards for infrastructure, containers, incidents, and remediation.",
            },
            {
                "name": "Prometheus",
                "status": "connected",
                "description": "Metrics endpoint available at /metrics for scrape-based observability.",
            },
            {
                "name": "Docker",
                "status": docker_status,
                "description": "Container runtime inventory, health state, and safe restart operations.",
            },
            {
                "name": "MCP",
                "status": "available",
                "description": "FastMCP server exposes operational tools for AI assistants.",
            },
            {
                "name": "SQLite",
                "status": sqlite_status,
                "description": "SQLite persistence for incidents, notifications, remediations, and metrics.",
            },
        ]
    }


def build_mcp_context() -> Dict[str, Any]:
    return {
        "mcp_tools": [
            {
                "name": "get_system_health",
                "description": "Return the current system and Docker health report.",
                "example": '{"tool": "get_system_health"}',
            },
            {
                "name": "list_containers",
                "description": "List Docker containers, status, and health state.",
                "example": '{"tool": "list_containers", "include_all": true}',
            },
            {
                "name": "list_incidents",
                "description": "List all incidents or filter by active/resolved status.",
                "example": '{"tool": "list_incidents", "status": "active"}',
            },
            {
                "name": "get_metrics",
                "description": "Return current metrics and the latest persisted snapshot.",
                "example": '{"tool": "get_metrics"}',
            },
            {
                "name": "generate_report",
                "description": "Generate weekly, monthly, or service health reports.",
                "example": '{"tool": "generate_report", "report_type": "weekly"}',
            },
            {
                "name": "restart_container",
                "description": "Restart a Docker container by name.",
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


def build_reports_context(services: DashboardServices) -> Dict[str, Any]:
    database_path = getattr(services.storage_repository, "database_path", "aegisnex.db")
    reporter = OperationalReporter(database_path)
    try:
        weekly = reporter.weekly_report()
        monthly = reporter.monthly_report()
    except Exception:
        weekly = {"summary": {}, "report_type": "weekly"}
        monthly = {"summary": {}, "report_type": "monthly"}
    return {
        "reports": [
            {"name": "Weekly report", "report_type": "weekly", "payload": weekly},
            {"name": "Monthly report", "report_type": "monthly", "payload": monthly},
        ]
    }


def build_notifications_context(services: DashboardServices) -> Dict[str, Any]:
    rows = storage_rows(services, "notifications")
    rows = sorted(rows, key=lambda row: str(row.get("timestamp", "")), reverse=True)
    return {
        "notification_stats": build_notification_statistics(rows),
        "notifications": rows[:25],
    }


def create_app(
    services: Optional[DashboardServices] = None,
    auth_manager: AuthManager | None = None,
) -> Any:
    try:
        from fastapi import FastAPI, Response
        from fastapi.responses import RedirectResponse
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Dashboard dependencies are missing. Install requirements.txt first."
        ) from exc

    app = FastAPI(title="AegisNex Dashboard")
    app.state.services = services or create_services()
    app.state.auth_manager = auth_manager or AuthManager()
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def current_user(request: FastAPIRequest) -> Any:
        token = request.cookies.get("aegisnex_session")
        return app.state.auth_manager.get_user_from_token(token)

    def require_user(request: FastAPIRequest) -> Any:
        user = current_user(request)
        if user is None:
            return None
        return user

    def auth_context(request: FastAPIRequest, **extra: Any) -> Dict[str, Any]:
        context = {"request": request, "user": current_user(request)}
        context.update(extra)
        return context

    def protected_context(request: FastAPIRequest) -> Dict[str, Any] | None:
        user = require_user(request)
        if user is None:
            return None
        context = collect_dashboard_context(app.state.services)
        context["request"] = request
        context["user"] = user
        return context

    @app.get("/register")
    def register_page(request: FastAPIRequest) -> Any:
        return templates.TemplateResponse(
            name="register.html",
            context=auth_context(request),
            request=request,
        )

    @app.post("/register")
    async def register(request: FastAPIRequest) -> Any:
        form = await parse_form_body(request)
        try:
            user, token = app.state.auth_manager.register(
                form.get("email", ""),
                form.get("password", ""),
            )
        except ValueError as exc:
            return templates.TemplateResponse(
                name="register.html",
                context=auth_context(request, error=str(exc), email=form.get("email", "")),
                request=request,
                status_code=400,
            )
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            "aegisnex_session",
            token,
            httponly=True,
            samesite="lax",
            max_age=app.state.auth_manager.token_ttl_seconds,
        )
        return response

    @app.get("/login")
    def login_page(request: FastAPIRequest) -> Any:
        return templates.TemplateResponse(
            name="login.html",
            context=auth_context(request),
            request=request,
        )

    @app.post("/login")
    async def login(request: FastAPIRequest) -> Any:
        form = await parse_form_body(request)
        result = app.state.auth_manager.login(
            form.get("email", ""),
            form.get("password", ""),
        )
        if result is None:
            return templates.TemplateResponse(
                name="login.html",
                context=auth_context(
                    request,
                    error="Invalid email or password.",
                    email=form.get("email", ""),
                ),
                request=request,
                status_code=401,
            )
        user, token = result
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            "aegisnex_session",
            token,
            httponly=True,
            samesite="lax",
            max_age=app.state.auth_manager.token_ttl_seconds,
        )
        return response

    @app.get("/logout")
    def logout() -> Any:
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("aegisnex_session")
        return response

    @app.get("/")
    def dashboard(request: FastAPIRequest) -> Any:
        context = protected_context(request)
        if context is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(
            name="dashboard.html",
            context=context,
            request=request,
        )

    @app.get("/infrastructure")
    def infrastructure(request: FastAPIRequest) -> Any:
        context = protected_context(request)
        if context is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(
            name="infrastructure.html",
            context=context,
            request=request,
        )

    @app.get("/containers")
    def containers(request: FastAPIRequest) -> Any:
        context = protected_context(request)
        if context is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(
            name="containers.html",
            context=context,
            request=request,
        )

    @app.get("/incidents")
    def incidents(request: FastAPIRequest) -> Any:
        context = protected_context(request)
        if context is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(
            name="incidents.html",
            context=context,
            request=request,
        )

    @app.get("/actions")
    def actions(request: FastAPIRequest) -> Any:
        context = protected_context(request)
        if context is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(
            name="actions.html",
            context=context,
            request=request,
        )

    @app.get("/reports")
    def reports(request: FastAPIRequest) -> Any:
        context = protected_context(request)
        if context is None:
            return RedirectResponse(url="/login", status_code=303)
        context.update(build_reports_context(app.state.services))
        return templates.TemplateResponse(
            name="reports.html",
            context=context,
            request=request,
        )

    @app.get("/reports/{report_type}/{report_format}")
    def download_report(
        request: FastAPIRequest,
        report_type: str,
        report_format: str,
    ) -> Any:
        user = require_user(request)
        if user is None:
            return RedirectResponse(url="/login", status_code=303)
        database_path = getattr(app.state.services.storage_repository, "database_path", "aegisnex.db")
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

    @app.get("/notifications")
    def notifications(request: FastAPIRequest) -> Any:
        context = protected_context(request)
        if context is None:
            return RedirectResponse(url="/login", status_code=303)
        context.update(build_notifications_context(app.state.services))
        return templates.TemplateResponse(
            name="notifications.html",
            context=context,
            request=request,
        )

    @app.get("/mcp")
    def mcp(request: FastAPIRequest) -> Any:
        context = protected_context(request)
        if context is None:
            return RedirectResponse(url="/login", status_code=303)
        context.update(build_mcp_context())
        return templates.TemplateResponse(
            name="mcp.html",
            context=context,
            request=request,
        )

    @app.get("/integrations")
    def integrations(request: FastAPIRequest) -> Any:
        context = protected_context(request)
        if context is None:
            return RedirectResponse(url="/login", status_code=303)
        context.update(build_integrations_context(app.state.services))
        return templates.TemplateResponse(
            name="integrations.html",
            context=context,
            request=request,
        )

    @app.get("/settings")
    def settings(request: FastAPIRequest) -> Any:
        context = protected_context(request)
        if context is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(
            name="settings.html",
            context=context,
            request=request,
        )

    @app.get("/metrics")
    def metrics() -> Any:
        payload, content_type = PrometheusExporter(app.state.services).render()
        return Response(content=payload, media_type=content_type)

    return app


try:
    app = create_app()
except RuntimeError:
    app = None
