"""FastMCP server exposing AegisNex operational tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.config import Config
from src.incidents import IncidentManager
from src.monitor import SystemResourceMonitor
from src.orchestrator import SystemHealthChecker
from src.reporting import OperationalReporter
from src.storage import AegisNexRepository


try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    FastMCP = None  # type: ignore[assignment]


@dataclass
class AegisNexMCPServices:
    monitor: Any
    docker_scanner: Any
    health_checker: Any
    incident_manager: IncidentManager
    reporter: OperationalReporter
    storage_repository: Any | None = None


class AegisNexMCPTools:
    """Tool implementations shared by FastMCP and unit tests."""

    def __init__(self, services: AegisNexMCPServices) -> None:
        self.services = services

    def get_system_health(self) -> Dict[str, Any]:
        """Return the current system and Docker health report."""
        return dict(self.services.health_checker.run({}))

    def list_containers(self, include_all: bool = True) -> Dict[str, Any]:
        """List Docker containers known to AegisNex."""
        return dict(self.services.docker_scanner.run({"include_all": include_all}))

    def list_incidents(self, status: Optional[str] = None) -> Dict[str, Any]:
        """List incidents, optionally filtered by status."""
        incidents = [
            incident.to_dict()
            for incident in self.services.incident_manager.list_incidents()
        ]
        if status:
            incidents = [
                incident
                for incident in incidents
                if str(incident.get("status", "")).lower() == status.lower()
            ]
        return {"status": "ok", "incidents": incidents, "count": len(incidents)}

    def get_metrics(self) -> Dict[str, Any]:
        """Return current system metrics and latest persisted metrics snapshot."""
        current = dict(self.services.monitor.run({}))
        latest_snapshot: Dict[str, Any] | None = None
        repository = self.services.storage_repository
        if repository is not None:
            try:
                snapshots = repository.fetch_all("metrics_snapshots")
            except Exception:
                snapshots = []
            if snapshots:
                latest_snapshot = sorted(
                    snapshots,
                    key=lambda row: str(row.get("timestamp", "")),
                    reverse=True,
                )[0]
        return {
            "status": "ok",
            "current": current,
            "latest_snapshot": latest_snapshot,
        }

    def generate_report(
        self,
        report_type: str = "weekly",
        service_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a weekly, monthly, or service health operational report."""
        normalized = report_type.lower()
        if normalized == "weekly":
            return self.services.reporter.weekly_report()
        if normalized == "monthly":
            return self.services.reporter.monthly_report()
        if normalized in {"service", "service_health"}:
            return self.services.reporter.service_health_report(service_name=service_name)
        return {
            "status": "error",
            "message": "report_type must be weekly, monthly, or service_health",
        }

    def restart_container(self, container_name: str) -> Dict[str, Any]:
        """Restart a Docker container by name."""
        if not container_name.strip():
            return {"status": "error", "message": "container_name is required"}
        return dict(self.services.docker_scanner.restart_container(container_name))


class FastMCPUnavailable(RuntimeError):
    """Raised when the FastMCP dependency is unavailable."""


class FastMCPShim:
    """Small test fallback that mirrors the FastMCP tool decorator surface."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.tools: Dict[str, Callable[..., Any]] = {}

    def tool(self, name: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name or func.__name__] = func
            return func

        return decorator

    def run(self) -> None:
        raise FastMCPUnavailable("FastMCP is not installed. Install the 'mcp' package.")


def create_services(config_path: str | Path = "config.yaml") -> AegisNexMCPServices:
    from src.docker_scanner import DockerScanner

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
    health_checker = SystemHealthChecker(
        monitor=monitor,
        docker_scanner=docker_scanner,
    )
    repository = AegisNexRepository(config.storage.database_path)
    incident_manager = IncidentManager(
        config.incidents.history_path,
        storage_repository=repository,
    )
    reporter = OperationalReporter(config.storage.database_path)
    return AegisNexMCPServices(
        monitor=monitor,
        docker_scanner=docker_scanner,
        health_checker=health_checker,
        incident_manager=incident_manager,
        reporter=reporter,
        storage_repository=repository,
    )


def create_mcp_server(
    services: AegisNexMCPServices | None = None,
    config_path: str | Path = "config.yaml",
    allow_fallback: bool = False,
) -> Any:
    """Create and register the AegisNex FastMCP server."""
    server_cls = FastMCP
    if server_cls is None:
        if not allow_fallback:
            raise FastMCPUnavailable("FastMCP is not installed. Install the 'mcp' package.")
        server_cls = FastMCPShim

    mcp = server_cls("AegisNex")  # type: ignore[operator]
    tools = AegisNexMCPTools(services or create_services(config_path))

    @mcp.tool()
    def get_system_health() -> Dict[str, Any]:
        return tools.get_system_health()

    @mcp.tool()
    def list_containers(include_all: bool = True) -> Dict[str, Any]:
        return tools.list_containers(include_all=include_all)

    @mcp.tool()
    def list_incidents(status: Optional[str] = None) -> Dict[str, Any]:
        return tools.list_incidents(status=status)

    @mcp.tool()
    def get_metrics() -> Dict[str, Any]:
        return tools.get_metrics()

    @mcp.tool()
    def generate_report(
        report_type: str = "weekly",
        service_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        return tools.generate_report(report_type=report_type, service_name=service_name)

    @mcp.tool()
    def restart_container(container_name: str) -> Dict[str, Any]:
        return tools.restart_container(container_name=container_name)

    return mcp


def main() -> None:
    create_mcp_server().run()


if __name__ == "__main__":
    main()
