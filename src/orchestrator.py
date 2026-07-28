"""System health orchestration for AgentX."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any


class SystemHealthChecker:
    def __init__(
        self,
        monitor: Any,
        docker_scanner: Any,
        logger: logging.Logger | None = None,
    ) -> None:
        self.monitor = monitor
        self.docker_scanner = docker_scanner
        self.logger = logger or logging.getLogger("agentx.health")

    def run(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        monitor_params = params.get("monitor", {})
        docker_params = params.get("docker", {})

        hardware: dict[str, Any]
        docker: dict[str, Any]

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

        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return {"timestamp": timestamp, "hardware": hardware, "docker": docker}
