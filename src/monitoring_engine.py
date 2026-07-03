"""Continuous monitoring engine backed by monitoring_targets."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Mapping

from src.http_monitor import HttpEndpointMonitor
from src.incidents import IncidentManager
from src.platform_db import PlatformRepository
from src.ssl_monitor import SslCertificateMonitor
from src.tcp_monitor import TcpTargetMonitor
from src.dns_monitor import DnsMonitor
from src.failsafe import failsafe, safe_import


class MonitoringEngine:
    def __init__(
        self,
        platform_repository: PlatformRepository,
        incident_manager: IncidentManager,
        interval_seconds: int = 30,
    ) -> None:
        self.platform_repository = platform_repository
        self.incident_manager = incident_manager
        self.interval_seconds = max(5, int(interval_seconds))
        self._monitor_cache: dict[str, Any] = {}
        self._last_check_time: dict[int, float] = {}

    async def run_forever(self) -> None:
        """Background loop with per-target interval scheduling.

        Runs every 5 seconds but only checks targets whose interval has elapsed.
        """
        while True:
            await asyncio.to_thread(self.run_scheduled)
            await asyncio.sleep(5)

    def run_scheduled(self) -> Dict[str, Any]:
        """Run checks respecting per-target check_interval_seconds."""
        targets = self.platform_repository.list_monitoring_targets()
        results = []
        now = time.time()
        for target in targets:
            if not target.get("is_active", True):
                continue
            interval = self._target_interval(target)
            target_id = int(target.get("id", 0))
            last_check = self._last_check_time.get(target_id, 0.0)
            if now - last_check < interval:
                continue
            result = self._process_target(target, actor="system")
            self._last_check_time[target_id] = now
            results.append(result)
        self._check_system_metrics()
        return {"status": "ok", "checked": len(results), "results": results}

    def run_once(self) -> Dict[str, Any]:
        """Run a full check of all active targets immediately, bypassing per-target intervals."""
        targets = self.platform_repository.list_monitoring_targets()
        results = []
        now = time.time()
        for target in targets:
            if not target.get("is_active", True):
                continue
            result = self._process_target(target, actor="system")
            target_id = int(target.get("id", 0))
            self._last_check_time[target_id] = now
            results.append(result)
        self._check_system_metrics()
        return {"status": "ok", "checked": len(results), "results": results}

    def _target_interval(self, target: Mapping[str, Any]) -> float:
        per_target = target.get("check_interval_seconds")
        if per_target is not None:
            try:
                return max(5.0, float(per_target))
            except (TypeError, ValueError):
                pass
        return float(self.interval_seconds)

    def _check_system_metrics(self) -> None:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent
            self._sync_system_incident("high_cpu", cpu > 90, "high", f"CPU usage at {cpu:.1f}% exceeds 90% threshold")
            self._sync_system_incident("high_memory", mem > 90, "high", f"Memory usage at {mem:.1f}% exceeds 90% threshold")
            self._sync_system_incident("high_disk", disk > 90, "high", f"Disk usage at {disk:.1f}% exceeds 90% threshold")
        except Exception:
            pass

    def _sync_system_incident(self, incident_type: str, is_breached: bool, severity: str, description: str) -> None:
        active = [i for i in self.incident_manager.get_active_incidents() if i.incident_type == incident_type and i.service_name == "system"]
        if is_breached and not active:
            self.incident_manager.create_incident(severity=severity, service_name="system", incident_type=incident_type, description=description)
        elif not is_breached and active:
            for incident in active:
                self.incident_manager.resolve_incident(incident.incident_id, actor="system", resolution_notes="System metric recovered.")

    def run_target(self, target_id: int, actor: str = "system") -> Dict[str, Any] | None:
        target = self.platform_repository.get_monitoring_target(target_id)
        if target is None:
            return None
        return self._process_target(target, actor=actor)

    def _process_target(self, target: Mapping[str, Any], actor: str) -> Dict[str, Any]:
        result = self._run_target(target)
        self.platform_repository.save_check_result(target, result)
        self._sync_incident(target, result)
        self.platform_repository.record_audit_log(
            actor,
            "check.executed",
            "monitoring_target",
            str(target.get("id", target.get("name", ""))),
            {"status": result.get("status"), "target_type": target.get("target_type")},
        )
        return result

    def _get_or_create_monitor(self, target_type: str, name: str, address: str, target: Mapping[str, Any]) -> Any:
        cache_key = f"{target_type}:{name}:{address}"
        if cache_key in self._monitor_cache:
            return self._monitor_cache[cache_key]
        timeout = int(target.get("timeout_seconds") or 5)
        if target_type == "http":
            monitor = HttpEndpointMonitor(
                {name: address},
                timeout_seconds=timeout,
                expected_status=int(target.get("expected_status") or 200),
                incident_manager=self.incident_manager,
                storage_repository=self.platform_repository,
            )
        elif target_type == "tcp":
            monitor = TcpTargetMonitor(
                {name: address},
                timeout_seconds=timeout,
                incident_manager=self.incident_manager,
                storage_repository=self.platform_repository,
            )
        elif target_type == "ssl":
            monitor = SslCertificateMonitor(
                {name: address},
                timeout_seconds=timeout,
                warning_days=int(target.get("warning_days") or 30),
                incident_manager=self.incident_manager,
                storage_repository=self.platform_repository,
            )
        elif target_type == "dns":
            monitor = DnsMonitor(
                {name: address},
                timeout_seconds=timeout,
                incident_manager=self.incident_manager,
                storage_repository=self.platform_repository,
            )
        elif target_type == "container":
            ContainerHealthMonitor = safe_import("src.container_health_monitor", "ContainerHealthMonitor")
            if ContainerHealthMonitor is not None:
                monitor = ContainerHealthMonitor(
                    {name: address},
                    timeout_seconds=timeout,
                    incident_manager=self.incident_manager,
                    storage_repository=self.platform_repository,
                )
            else:
                return None
        else:
            return None
        self._monitor_cache[cache_key] = monitor
        return monitor

    def _run_target(self, target: Mapping[str, Any]) -> Dict[str, Any]:
        target_type = str(target.get("target_type", "")).lower()
        name = str(target.get("name", ""))
        address = str(target.get("address", ""))
        monitor = self._get_or_create_monitor(target_type, name, address, target)
        if monitor is None:
            return {
                "name": name,
                "target_type": target_type,
                "status": "failed",
                "error": f"Unsupported target type: {target_type}",
            }
        payload = monitor.run({})
        if target_type == "http":
            result = dict(payload["checks"][0]) if payload.get("checks") else {}
        elif target_type == "tcp":
            result = dict(payload["checks"][0]) if payload.get("checks") else {}
        elif target_type == "ssl":
            result = dict(payload["checks"][0]) if payload.get("checks") else {}
        elif target_type == "dns":
            result = dict(payload["checks"][0]) if payload.get("checks") else {}
        elif target_type == "container":
            result = dict(payload["checks"][0]) if payload.get("checks") else {}
        else:
            result = {}
        result["target_type"] = target_type
        return result

    def _sync_incident(self, target: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        target_type = str(target.get("target_type", "")).lower()
        name = str(target.get("name", ""))
        incident_type = {
            "http": "http_endpoint_failure",
            "tcp": "tcp_target_unreachable",
            "ssl": "ssl_certificate_expiring",
            "dns": "dns_resolution_failure",
            "container": "container_health_failure",
        }.get(target_type, "monitoring_check_failed")
        failure = self._is_failure(target_type, result)
        active = [
            incident
            for incident in self.incident_manager.get_active_incidents()
            if incident.service_name == name and incident.incident_type == incident_type
        ]
        if failure and not active:
            incident = self.incident_manager.create_incident(
                severity=self._severity(target_type, result),
                service_name=name,
                incident_type=incident_type,
                description=self._description(target_type, name, result),
                health_check_results=[dict(result)],
            )
            self.platform_repository.record_incident_transition(
                incident.incident_id,
                None,
                "active",
                "system",
                {"reason": "check_failed", "target_type": target_type},
            )
            self.platform_repository.record_audit_log(
                "system",
                "incident.created",
                "incident",
                incident.incident_id,
                {"service_name": name, "incident_type": incident_type},
            )
        elif not failure and active:
            for incident in active:
                self.incident_manager.resolve_incident(
                    incident.incident_id,
                    actor="system",
                    resolution_notes="Recovered automatically after a successful check.",
                )

    @staticmethod
    def _is_failure(target_type: str, result: Mapping[str, Any]) -> bool:
        if target_type == "http":
            return not bool(result.get("available"))
        if target_type == "tcp":
            return not bool(result.get("reachable"))
        if target_type == "ssl":
            return str(result.get("status")) != "ok"
        if target_type == "dns":
            return not bool(result.get("resolvable"))
        if target_type == "container":
            return str(result.get("status")) != "ok"
        return str(result.get("status")) != "ok"

    @staticmethod
    def _severity(target_type: str, result: Mapping[str, Any]) -> str:
        if target_type == "ssl" and str(result.get("status")) == "warning":
            return "medium"
        return "high"

    @staticmethod
    def _description(target_type: str, name: str, result: Mapping[str, Any]) -> str:
        if target_type == "http":
            return f"HTTP target {name} failed: {result.get('error') or result.get('status_code')}"
        if target_type == "tcp":
            return f"TCP target {name} is unreachable: {result.get('error')}"
        if target_type == "ssl":
            if result.get("days_remaining") is not None:
                return f"SSL certificate for {name} expires in {result.get('days_remaining')} days"
            return f"SSL certificate check failed for {name}: {result.get('error')}"
        if target_type == "dns":
            return f"DNS resolution failed for {name}: {result.get('error')}"
        if target_type == "container":
            return f"Container health check failed for {name}: {result.get('error')}"
        return f"Monitoring target {name} failed"
