"""FastAPI dashboard for AegisNex operational visibility."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any, Dict, List, Optional

from src.config import Config
from src.docker_scanner import DockerScanner
from src.guardian import Guardian
from src.incidents import Incident, IncidentManager
from src.monitor import SystemResourceMonitor
from src.notifier import Notifier
from src.orchestrator import SystemHealthChecker
from src.prometheus_exporter import PrometheusExporter

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
    incident_manager = IncidentManager(config.incidents.history_path)
    health_checker = SystemHealthChecker(monitor=monitor, docker_scanner=docker_scanner)
    guardian = Guardian(
        health_checker=health_checker,
        docker_scanner=docker_scanner,
        notifier=Notifier(),
        restart_cooldown_seconds=config.guardian.restart_cooldown_seconds,
        max_restart_attempts=config.guardian.max_restart_attempts,
        restart_history_path=config.guardian.restart_history_path,
        incident_manager=incident_manager,
    )
    return DashboardServices(
        monitor=monitor,
        docker_scanner=docker_scanner,
        incident_manager=incident_manager,
        guardian=guardian,
        restart_history_path=Path(config.guardian.restart_history_path),
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
    return {
        "timestamp": timestamp,
        "metrics": metrics,
        "network": get_network_stats(),
        "containers": build_container_rows(containers, restart_history, timestamp),
        "running_containers": [
            container for container in containers if container.get("status") == "running"
        ],
        "active_incidents": [incident_to_dict(incident) for incident in active_incidents],
        "resolved_incidents": [
            incident_to_dict(incident) for incident in resolved_incidents
        ],
        "actions": build_remediation_actions(incidents, restart_history),
    }


def create_app(services: Optional[DashboardServices] = None) -> Any:
    try:
        from fastapi import FastAPI, Response
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Dashboard dependencies are missing. Install requirements.txt first."
        ) from exc

    app = FastAPI(title="AegisNex Dashboard")
    app.state.services = services or create_services()
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def dashboard(request: FastAPIRequest) -> Any:
        context = collect_dashboard_context(app.state.services)
        context["request"] = request
        return templates.TemplateResponse(
            name="dashboard.html",
            context=context,
            request=request,
        )

    @app.get("/containers")
    def containers(request: FastAPIRequest) -> Any:
        context = collect_dashboard_context(app.state.services)
        context["request"] = request
        return templates.TemplateResponse(
            name="containers.html",
            context=context,
            request=request,
        )

    @app.get("/incidents")
    def incidents(request: FastAPIRequest) -> Any:
        context = collect_dashboard_context(app.state.services)
        context["request"] = request
        return templates.TemplateResponse(
            name="incidents.html",
            context=context,
            request=request,
        )

    @app.get("/actions")
    def actions(request: FastAPIRequest) -> Any:
        context = collect_dashboard_context(app.state.services)
        context["request"] = request
        return templates.TemplateResponse(
            name="actions.html",
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
