"""System health orchestration for AgentX."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class SystemHealthChecker:
    def __init__(
        self,
        monitor: Any,
        docker_scanner: Any,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.monitor = monitor
        self.docker_scanner = docker_scanner
        self.logger = logger or logging.getLogger("agentx.health")

    def run(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        monitor_params = params.get("monitor", {})
        docker_params = params.get("docker", {})

        hardware: Dict[str, Any]
        docker: Dict[str, Any]

        try:
            hardware = self.monitor.run(monitor_params)
        except Exception as exc:
            self.logger.exception("Monitor failed: %s", exc)
            hardware = {"status": "failed", "error": str(exc)}

        try:
            docker = self.docker_scanner.run(docker_params)
        except Exception as exc:
            self.logger.exception("Docker scan failed: %s", exc)
            docker = {"status": "failed", "error": str(exc)}

        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {"timestamp": timestamp, "hardware": hardware, "docker": docker}
