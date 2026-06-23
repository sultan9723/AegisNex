"""TCP host and port monitoring for AegisNex."""

from __future__ import annotations

from dataclasses import dataclass
import socket
from time import perf_counter
from typing import Any, Dict, Mapping

from src.incidents import IncidentManager, utc_timestamp


@dataclass(frozen=True)
class TcpTargetCheck:
    name: str
    target: str
    host: str
    port: int
    timestamp: str
    status: str
    reachable: bool
    latency_ms: float | None
    error: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "host": self.host,
            "port": self.port,
            "timestamp": self.timestamp,
            "status": self.status,
            "reachable": self.reachable,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


class TcpTargetMonitor:
    """Check configured TCP host:port targets and raise incidents on failure."""

    def __init__(
        self,
        targets: Mapping[str, str],
        timeout_seconds: int = 5,
        incident_manager: IncidentManager | None = None,
        storage_repository: Any | None = None,
        connector: Any | None = None,
    ) -> None:
        self.targets = dict(targets)
        self.timeout_seconds = timeout_seconds
        self.incident_manager = incident_manager
        self.storage_repository = storage_repository
        self.connector = connector

    def run(self, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        params = params or {}
        targets = self._selected_targets(params)
        checks = [self._check_target(name, target) for name, target in targets.items()]
        for check in checks:
            self._persist_check(check)
            self._sync_incident(check)

        reachable_count = len([check for check in checks if check.reachable])
        total = len(checks)
        availability = round((reachable_count / total) * 100, 2) if total else 100.0
        return {
            "status": "ok" if reachable_count == total else "warning",
            "timestamp": utc_timestamp(),
            "availability_percent": availability,
            "reachable_count": reachable_count,
            "total_count": total,
            "checks": [check.to_dict() for check in checks],
        }

    def _selected_targets(self, params: Dict[str, Any]) -> Dict[str, str]:
        target_name = str(params.get("target_name", "")).strip()
        if target_name:
            target = self.targets.get(target_name)
            return {target_name: target} if target else {}
        return dict(self.targets)

    def _check_target(self, name: str, target: str) -> TcpTargetCheck:
        host, port = self._parse_target(target)
        timestamp = utc_timestamp()
        started = perf_counter()
        try:
            self._connect(host, port)
            latency_ms = round((perf_counter() - started) * 1000, 2)
            return TcpTargetCheck(
                name=name,
                target=target,
                host=host,
                port=port,
                timestamp=timestamp,
                status="ok",
                reachable=True,
                latency_ms=latency_ms,
                error="",
            )
        except Exception as exc:
            latency_ms = round((perf_counter() - started) * 1000, 2)
            return TcpTargetCheck(
                name=name,
                target=target,
                host=host,
                port=port,
                timestamp=timestamp,
                status="failed",
                reachable=False,
                latency_ms=latency_ms,
                error=str(exc),
            )

    def _connect(self, host: str, port: int) -> None:
        if self.connector is not None:
            self.connector(host, port, self.timeout_seconds)
            return
        with socket.create_connection((host, port), timeout=self.timeout_seconds):
            return

    @staticmethod
    def _parse_target(target: str) -> tuple[str, int]:
        host, raw_port = target.rsplit(":", 1)
        return host, int(raw_port)

    def _persist_check(self, check: TcpTargetCheck) -> None:
        if self.storage_repository is None:
            return
        self.storage_repository.save_tcp_check(check.to_dict())

    def _sync_incident(self, check: TcpTargetCheck) -> None:
        if self.incident_manager is None:
            return
        if check.reachable:
            self._resolve_tcp_incidents(check.name)
            return
        self.incident_manager.create_incident(
            severity="high",
            service_name=check.name,
            incident_type="tcp_target_unreachable",
            description=f"TCP target {check.name} is unreachable: {check.error}",
            health_check_results=[check.to_dict()],
        )

    def _resolve_tcp_incidents(self, service_name: str) -> None:
        for incident in self.incident_manager.get_active_incidents():
            if (
                incident.service_name == service_name
                and incident.incident_type == "tcp_target_unreachable"
            ):
                self.incident_manager.resolve_incident(incident.incident_id)
