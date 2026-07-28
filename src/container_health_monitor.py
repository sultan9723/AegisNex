"""Docker container health monitoring for AegisNex."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from src.failsafe import failsafe, safe_import
from src.incidents import IncidentManager, utc_timestamp


@dataclass(frozen=True)
class ContainerHealthCheck:
    name: str
    container_name: str
    timestamp: str
    status: str
    healthy: bool
    state: str
    exit_code: int | None
    restart_count: int
    error: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "container_name": self.container_name,
            "timestamp": self.timestamp,
            "status": self.status,
            "healthy": self.healthy,
            "state": self.state,
            "exit_code": self.exit_code,
            "restart_count": self.restart_count,
            "error": self.error,
        }


class ContainerHealthMonitor:
    """Check Docker container health status via the Docker SDK."""

    def __init__(
        self,
        targets: Mapping[str, str],
        timeout_seconds: int = 10,
        incident_manager: IncidentManager | None = None,
        storage_repository: Any | None = None,
        docker_client: Any | None = None,
    ) -> None:
        self.targets = dict(targets)
        self.timeout_seconds = timeout_seconds
        self.incident_manager = incident_manager
        self.storage_repository = storage_repository
        self._docker_client = docker_client

    def _get_client(self) -> Any:
        if self._docker_client is not None:
            return self._docker_client
        docker = safe_import("docker")
        if docker is None:
            raise RuntimeError("Docker SDK not available")
        return docker.from_env(timeout=self.timeout_seconds)

    @failsafe(fallback={"status": "error", "checks": [], "error": "Docker unavailable"})
    def run(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        targets = self._selected_targets(params)
        checks = [
            self._check_container(name, container_name) for name, container_name in targets.items()
        ]
        for check in checks:
            self._persist_check(check)
            self._sync_incident(check)

        healthy_count = len([c for c in checks if c.healthy])
        total = len(checks)
        availability = round((healthy_count / total) * 100, 2) if total else 100.0
        return {
            "status": "ok" if healthy_count == total else "warning",
            "timestamp": utc_timestamp(),
            "availability_percent": availability,
            "healthy_count": healthy_count,
            "total_count": total,
            "checks": [check.to_dict() for check in checks],
        }

    def _selected_targets(self, params: dict[str, Any]) -> dict[str, str]:
        target_name = str(params.get("target_name", "")).strip()
        if target_name:
            t = self.targets.get(target_name)
            return {target_name: t} if t else {}
        return dict(self.targets)

    def _check_container(self, name: str, container_name: str) -> ContainerHealthCheck:
        timestamp = utc_timestamp()
        started = perf_counter()
        try:
            client = self._get_client()
            container = client.containers.get(container_name)
            container.reload()
            state = container.status
            healthy = state == "running"
            exit_code = container.attrs.get("State", {}).get("ExitCode")
            restart_count = container.attrs.get("RestartCount", 0)
            health_status = container.attrs.get("State", {}).get("Health", {}).get("Status", "")
            if health_status and health_status != "healthy":
                healthy = False
                state = health_status
            latency_ms = round((perf_counter() - started) * 1000, 2)
            return ContainerHealthCheck(
                name=name,
                container_name=container_name,
                timestamp=timestamp,
                status="ok" if healthy else "failed",
                healthy=healthy,
                state=state,
                exit_code=exit_code,
                restart_count=restart_count,
                error="" if healthy else f"Container state: {state}",
            )
        except Exception as exc:
            latency_ms = round((perf_counter() - started) * 1000, 2)
            return ContainerHealthCheck(
                name=name,
                container_name=container_name,
                timestamp=timestamp,
                status="failed",
                healthy=False,
                state="unknown",
                exit_code=None,
                restart_count=0,
                error=str(exc),
            )

    def _persist_check(self, check: ContainerHealthCheck) -> None:
        if self.storage_repository is None:
            return
        self.storage_repository.save_check_result(
            {"name": check.name, "target_type": "container", "id": None},
            check.to_dict(),
        )

    def _sync_incident(self, check: ContainerHealthCheck) -> None:
        if self.incident_manager is None:
            return
        if check.healthy:
            self._resolve_container_incidents(check.name)
            return
        self.incident_manager.create_incident(
            severity="high",
            service_name=check.name,
            incident_type="container_health_failure",
            description=f"Container {check.container_name} is unhealthy: {check.error}",
            health_check_results=[check.to_dict()],
        )

    def _resolve_container_incidents(self, service_name: str) -> None:
        for inc in self.incident_manager.get_active_incidents():
            if inc.service_name == service_name and inc.incident_type == "container_health_failure":
                self.incident_manager.resolve_incident(inc.incident_id)
