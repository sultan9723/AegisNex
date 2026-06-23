"""Continuous monitoring engine backed by monitoring_targets."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Mapping

from src.http_monitor import HttpEndpointMonitor
from src.incidents import IncidentManager
from src.platform_db import PlatformRepository
from src.ssl_monitor import SslCertificateMonitor
from src.tcp_monitor import TcpTargetMonitor


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

    async def run_forever(self) -> None:
        while True:
            self.run_once()
            await asyncio.sleep(self.interval_seconds)

    def run_once(self) -> Dict[str, Any]:
        targets = self.platform_repository.list_monitoring_targets()
        results = []
        for target in targets:
            result = self._process_target(target, actor="system")
            results.append(result)
        return {"status": "ok", "checked": len(results), "results": results}

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

    def _run_target(self, target: Mapping[str, Any]) -> Dict[str, Any]:
        target_type = str(target.get("target_type", "")).lower()
        name = str(target.get("name", ""))
        address = str(target.get("address", ""))
        timeout = int(target.get("timeout_seconds") or 5)
        if target_type == "http":
            payload = HttpEndpointMonitor(
                {name: address},
                timeout_seconds=timeout,
                expected_status=int(target.get("expected_status") or 200),
            ).run({})
            result = dict(payload["checks"][0]) if payload["checks"] else {}
        elif target_type == "tcp":
            payload = TcpTargetMonitor({name: address}, timeout_seconds=timeout).run({})
            result = dict(payload["checks"][0]) if payload["checks"] else {}
        elif target_type == "ssl":
            payload = SslCertificateMonitor(
                {name: address},
                timeout_seconds=timeout,
                warning_days=int(target.get("warning_days") or 30),
            ).run({})
            result = dict(payload["checks"][0]) if payload["checks"] else {}
        else:
            result = {
                "name": name,
                "target_type": target_type,
                "status": "failed",
                "error": f"Unsupported target type: {target_type}",
            }
        result["target_type"] = target_type
        return result

    def _sync_incident(self, target: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        target_type = str(target.get("target_type", "")).lower()
        name = str(target.get("name", ""))
        incident_type = {
            "http": "http_endpoint_failure",
            "tcp": "tcp_target_unreachable",
            "ssl": "ssl_certificate_expiring",
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
        return f"Monitoring target {name} failed"
