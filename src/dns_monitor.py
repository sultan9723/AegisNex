"""DNS resolution monitoring for AegisNex."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Dict, Mapping

from src.incidents import IncidentManager, utc_timestamp


@dataclass(frozen=True)
class DnsResolutionCheck:
    name: str
    hostname: str
    timestamp: str
    status: str
    resolvable: bool
    resolved_addresses: list[str]
    latency_ms: float | None
    error: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "hostname": self.hostname,
            "timestamp": self.timestamp,
            "status": self.status,
            "resolvable": self.resolvable,
            "resolved_addresses": self.resolved_addresses,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


class DnsMonitor:
    """Check DNS resolution for configured hostnames."""

    def __init__(
        self,
        targets: Mapping[str, str],
        timeout_seconds: int = 5,
        resolver: Any | None = None,
        incident_manager: IncidentManager | None = None,
        storage_repository: Any | None = None,
    ) -> None:
        self.targets = dict(targets)
        self.timeout_seconds = timeout_seconds
        self.resolver = resolver
        self.incident_manager = incident_manager
        self.storage_repository = storage_repository

    def run(self, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        params = params or {}
        targets = self._selected_targets(params)
        checks = [self._check_target(name, hostname) for name, hostname in targets.items()]
        for check in checks:
            self._persist_check(check)
            self._sync_incident(check)

        resolvable_count = len([c for c in checks if c.resolvable])
        total = len(checks)
        availability = round((resolvable_count / total) * 100, 2) if total else 100.0
        return {
            "status": "ok" if resolvable_count == total else "warning",
            "timestamp": utc_timestamp(),
            "availability_percent": availability,
            "resolvable_count": resolvable_count,
            "total_count": total,
            "checks": [check.to_dict() for check in checks],
        }

    def _selected_targets(self, params: Dict[str, Any]) -> Dict[str, str]:
        target_name = str(params.get("target_name", "")).strip()
        if target_name:
            t = self.targets.get(target_name)
            return {target_name: t} if t else {}
        return dict(self.targets)

    def _check_target(self, name: str, hostname: str) -> DnsResolutionCheck:
        timestamp = utc_timestamp()
        started = perf_counter()
        try:
            addresses = self._resolve(hostname)
            latency_ms = round((perf_counter() - started) * 1000, 2)
            return DnsResolutionCheck(
                name=name,
                hostname=hostname,
                timestamp=timestamp,
                status="ok",
                resolvable=True,
                resolved_addresses=addresses,
                latency_ms=latency_ms,
                error="",
            )
        except Exception as exc:
            latency_ms = round((perf_counter() - started) * 1000, 2)
            return DnsResolutionCheck(
                name=name,
                hostname=hostname,
                timestamp=timestamp,
                status="failed",
                resolvable=False,
                resolved_addresses=[],
                latency_ms=latency_ms,
                error=str(exc),
            )

    def _resolve(self, hostname: str) -> list[str]:
        import socket
        if self.resolver is not None:
            return self.resolver(hostname, self.timeout_seconds)
        return [str(r[4][0]) for r in socket.getaddrinfo(hostname, 80, family=socket.AF_INET, type=socket.SOCK_STREAM)]

    def _persist_check(self, check: DnsResolutionCheck) -> None:
        if self.storage_repository is None:
            return
        self.storage_repository.save_check_result(
            {"name": check.name, "target_type": "dns", "id": None},
            check.to_dict(),
        )

    def _sync_incident(self, check: DnsResolutionCheck) -> None:
        if self.incident_manager is None:
            return
        if check.resolvable:
            self._resolve_dns_incidents(check.name)
            return
        self.incident_manager.create_incident(
            severity="high",
            service_name=check.name,
            incident_type="dns_resolution_failure",
            description=f"DNS resolution failed for {check.name}: {check.error}",
            health_check_results=[check.to_dict()],
        )

    def _resolve_dns_incidents(self, service_name: str) -> None:
        for inc in self.incident_manager.get_active_incidents():
            if inc.service_name == service_name and inc.incident_type == "dns_resolution_failure":
                self.incident_manager.resolve_incident(inc.incident_id)
