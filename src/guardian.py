"""Autonomous Guardian mode for AgentX."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.health_checks import HealthCheck, HealthCheckResult
from src.incidents import IncidentManager
from src.notifications_compat import NotifierCompat
from src.orchestrator import SystemHealthChecker


class Guardian:
    def __init__(
        self,
        health_checker: SystemHealthChecker,
        docker_scanner: Any,
        notifier: NotifierCompat,
        restart_cooldown_seconds: int = 300,
        max_restart_attempts: int = 3,
        restart_history_path: str | Path = "restart_history.json",
        health_checks: list[HealthCheck] | None = None,
        incident_manager: IncidentManager | None = None,
        storage_repository: Any | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.health_checker = health_checker
        self.docker_scanner = docker_scanner
        self.notifier = notifier
        self.restart_cooldown_seconds = max(0, restart_cooldown_seconds)
        self.max_restart_attempts = max(1, max_restart_attempts)
        self.restart_history_path = Path(restart_history_path)
        self.health_checks = health_checks or []
        self.incident_manager = incident_manager
        self.storage_repository = storage_repository
        self.logger = logger or logging.getLogger("agentx.guardian")
        self.restart_history = self._load_restart_history()

    def run(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        docker_params = params.get("docker", {})
        docker_params.setdefault("include_all", getattr(self.docker_scanner, "include_all", True))

        health_report = self.health_checker.run({"docker": docker_params})
        actions: list[dict[str, Any]] = []

        docker_report = health_report.get("docker", {})
        containers = docker_report.get("containers", []) if isinstance(docker_report, dict) else []

        for container in containers:
            status = container.get("status")
            name = container.get("name")
            if not name:
                continue
            check_results = self._run_health_checks(container) if status == "running" else []
            unhealthy = status in {"stopped", "error"} or any(
                not result.healthy for result in check_results
            )
            if not unhealthy:
                self._reset_restart_history(name)
                self._resolve_service_incidents(name)
                continue

            serialized_results = [self._serialize_health_result(result) for result in check_results]
            incident = self._create_incident(
                service_name=name,
                status=str(status),
                health_check_results=serialized_results,
            )
            decision = self._restart_decision(name)
            if not decision["allowed"]:
                skipped = {
                    "status": "skipped",
                    "container": name,
                    "reason": decision["reason"],
                }
                if incident:
                    skipped["incident_id"] = incident.incident_id
                if check_results:
                    skipped["health_checks"] = serialized_results
                actions.append(skipped)
                continue
            if status == "running" and hasattr(self.docker_scanner, "restart_container"):
                action = self.docker_scanner.restart_container(name)
            else:
                action = self.docker_scanner.ensure_running(name)
            if check_results:
                action["health_checks"] = serialized_results
            if incident:
                action["incident_id"] = incident.incident_id
            if action.get("status") == "ok" and action.get("action") == "restarted":
                self._record_restart_attempt(name)
                timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
                message = f"Action: restarted\nContainer: {name}\nTimestamp: {timestamp}"
                action["alert"] = self.notifier.send_email_alert(message)
            self._update_incident_remediation(incident, action)
            self._record_remediation_action(name, incident, action)
            actions.append(action)

        return {"health": health_report, "actions": actions}

    def _run_health_checks(self, container: dict[str, Any]) -> list[HealthCheckResult]:
        results: list[HealthCheckResult] = []
        for health_check in self.health_checks:
            try:
                results.append(health_check.check(container))
            except Exception as exc:
                name = getattr(health_check, "name", health_check.__class__.__name__)
                self.logger.exception("Health check failed: %s", name)
                results.append(
                    HealthCheckResult(
                        name=name,
                        status="failed",
                        healthy=False,
                        message=str(exc),
                    )
                )
        return results

    @staticmethod
    def _serialize_health_result(result: HealthCheckResult) -> dict[str, Any]:
        return {
            "name": result.name,
            "status": result.status,
            "healthy": result.healthy,
            "message": result.message,
        }

    def _create_incident(
        self,
        service_name: str,
        status: str,
        health_check_results: list[dict[str, Any]],
    ) -> Any | None:
        if not self.incident_manager:
            return None
        incident_type = "health_check_failed" if health_check_results else "container_status"
        severity = "high" if health_check_results else "critical"
        if health_check_results:
            failed_checks = [
                result["name"] for result in health_check_results if not result["healthy"]
            ]
            description = f"Health check failure for {service_name}: " + ", ".join(failed_checks)
        else:
            description = f"Container {service_name} reported status {status}"
        return self.incident_manager.create_incident(
            severity=severity,
            service_name=service_name,
            incident_type=incident_type,
            description=description,
            health_check_results=health_check_results,
        )

    def _update_incident_remediation(self, incident: Any | None, action: dict[str, Any]) -> None:
        if not self.incident_manager or not incident:
            return
        successful = action.get("status") == "ok" and action.get("action") == "restarted"
        self.incident_manager.update_incident(
            incident.incident_id,
            remediation_attempted=True,
            remediation_successful=successful,
        )

    def _resolve_service_incidents(self, service_name: str) -> None:
        if not self.incident_manager:
            return
        self.incident_manager.resolve_service_incidents(service_name)

    def _record_remediation_action(
        self,
        service_name: str,
        incident: Any | None,
        action: dict[str, Any],
    ) -> None:
        if not self.storage_repository:
            return
        self.storage_repository.save_remediation_action(
            service_name=service_name,
            action=str(action.get("action", "restart")),
            successful=action.get("status") == "ok",
            incident_id=getattr(incident, "incident_id", None),
            details=action,
        )

    def _should_restart(self, container_name: str) -> bool:
        return self._restart_decision(container_name)["allowed"]

    def _restart_decision(self, container_name: str) -> dict[str, Any]:
        history = self.restart_history.get(container_name, {})
        attempts = int(history.get("attempts", 0))
        if attempts >= self.max_restart_attempts:
            return {"allowed": False, "reason": "max_restart_attempts"}

        if self.restart_cooldown_seconds <= 0:
            return {"allowed": True, "reason": "allowed"}

        last_restart_raw = history.get("last_restart")
        if not last_restart_raw:
            return {"allowed": True, "reason": "allowed"}
        last_restart = self._parse_timestamp(str(last_restart_raw))
        if not last_restart:
            return {"allowed": True, "reason": "allowed"}
        elapsed = datetime.now(UTC) - last_restart
        if elapsed.total_seconds() < self.restart_cooldown_seconds:
            return {"allowed": False, "reason": "restart_cooldown"}
        return {"allowed": True, "reason": "allowed"}

    def _record_restart_attempt(self, container_name: str) -> None:
        history = self.restart_history.get(container_name, {})
        attempts = int(history.get("attempts", 0)) + 1
        self.restart_history[container_name] = {
            "attempts": attempts,
            "last_restart": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        self._save_restart_history()

    def _reset_restart_history(self, container_name: str) -> None:
        if container_name not in self.restart_history:
            return
        del self.restart_history[container_name]
        self._save_restart_history()

    def _load_restart_history(self) -> dict[str, dict[str, Any]]:
        if not self.restart_history_path.exists():
            return {}
        try:
            payload = json.loads(self.restart_history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.warning("Failed to load restart history: %s", exc)
            return {}
        if not isinstance(payload, dict):
            return {}
        history: dict[str, dict[str, Any]] = {}
        for name, value in payload.items():
            if isinstance(name, str) and isinstance(value, dict):
                history[name] = value
        return history

    def _save_restart_history(self) -> None:
        try:
            self.restart_history_path.parent.mkdir(parents=True, exist_ok=True)
            self.restart_history_path.write_text(
                json.dumps(self.restart_history, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            self.logger.exception("Failed to save restart history: %s", exc)

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
