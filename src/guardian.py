"""Autonomous Guardian mode for AgentX."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.orchestrator import SystemHealthChecker
from src.notifier import Notifier


class Guardian:
    def __init__(
        self,
        health_checker: SystemHealthChecker,
        docker_scanner: Any,
        notifier: Notifier,
        restart_cooldown_seconds: int = 300,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.health_checker = health_checker
        self.docker_scanner = docker_scanner
        self.notifier = notifier
        self.restart_cooldown_seconds = max(0, restart_cooldown_seconds)
        self._last_restart: Dict[str, datetime] = {}
        self.logger = logger or logging.getLogger("agentx.guardian")

    def run(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        docker_params = params.get("docker", {})
        docker_params.setdefault("include_all", True)

        health_report = self.health_checker.run({"docker": docker_params})
        actions: List[Dict[str, Any]] = []

        docker_report = health_report.get("docker", {})
        containers = docker_report.get("containers", []) if isinstance(docker_report, dict) else []

        for container in containers:
            status = container.get("status")
            name = container.get("name")
            if not name:
                continue
            if status in {"stopped", "error"}:
                if not self._should_restart(name):
                    actions.append(
                        {
                            "status": "skipped",
                            "container": name,
                            "reason": "restart_cooldown",
                        }
                    )
                    continue
                action = self.docker_scanner.ensure_running(name)
                if action.get("status") == "ok" and action.get("action") == "restarted":
                    self._last_restart[name] = datetime.now(timezone.utc)
                    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    message = (
                        f"Action: restarted\n"
                        f"Container: {name}\n"
                        f"Timestamp: {timestamp}"
                    )
                    action["alert"] = self.notifier.send_email_alert(message)
                actions.append(action)

        return {"health": health_report, "actions": actions}

    def _should_restart(self, container_name: str) -> bool:
        if self.restart_cooldown_seconds <= 0:
            return True
        last_restart = self._last_restart.get(container_name)
        if not last_restart:
            return True
        elapsed = datetime.now(timezone.utc) - last_restart
        return elapsed.total_seconds() >= self.restart_cooldown_seconds
