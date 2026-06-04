"""Pluggable health checks used by Guardian remediation."""

from __future__ import annotations

from dataclasses import dataclass
from http.client import HTTPException
import logging
import socket
from typing import Any, Mapping, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HealthCheckResult:
    name: str
    status: str
    healthy: bool
    message: str = ""


class HealthCheck(Protocol):
    name: str

    def check(self, container: Mapping[str, Any]) -> HealthCheckResult:
        """Return health status for a container payload."""


class DockerHealthCheck:
    name = "docker"

    def __init__(
        self,
        docker_scanner: Any | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.docker_scanner = docker_scanner
        self.logger = logger or logging.getLogger("agentx.healthcheck.docker")

    def check(self, container: Mapping[str, Any]) -> HealthCheckResult:
        container_name = str(container.get("name", ""))
        health_status = container.get("health_status")
        if health_status is None and self.docker_scanner and container_name:
            health_status = self.docker_scanner.get_health_status(container_name)

        if health_status in {None, "", "none"}:
            return HealthCheckResult(
                name=self.name,
                status="unknown",
                healthy=True,
                message="No Docker health check configured",
            )
        if health_status == "healthy":
            return HealthCheckResult(name=self.name, status="healthy", healthy=True)
        return HealthCheckResult(
            name=self.name,
            status=str(health_status),
            healthy=False,
            message=f"Docker health status is {health_status}",
        )


class HttpHealthCheck:
    name = "http"

    def __init__(
        self,
        endpoints: Mapping[str, str],
        timeout_seconds: int = 5,
        expected_status: int = 200,
        logger: logging.Logger | None = None,
    ) -> None:
        self.endpoints = dict(endpoints)
        self.timeout_seconds = timeout_seconds
        self.expected_status = expected_status
        self.logger = logger or logging.getLogger("agentx.healthcheck.http")

    def check(self, container: Mapping[str, Any]) -> HealthCheckResult:
        container_name = str(container.get("name", ""))
        endpoint = self.endpoints.get(container_name)
        if not endpoint:
            return HealthCheckResult(
                name=self.name,
                status="skipped",
                healthy=True,
                message="No HTTP endpoint configured",
            )

        try:
            request = Request(endpoint, method="GET")
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status_code = int(response.status)
        except (HTTPException, OSError, URLError) as exc:
            return HealthCheckResult(
                name=self.name,
                status="failed",
                healthy=False,
                message=str(exc),
            )

        healthy = status_code == self.expected_status
        return HealthCheckResult(
            name=self.name,
            status=str(status_code),
            healthy=healthy,
            message="" if healthy else f"Expected HTTP {self.expected_status}",
        )


class TcpHealthCheck:
    name = "tcp"

    def __init__(
        self,
        targets: Mapping[str, str],
        timeout_seconds: int = 5,
        logger: logging.Logger | None = None,
    ) -> None:
        self.targets = dict(targets)
        self.timeout_seconds = timeout_seconds
        self.logger = logger or logging.getLogger("agentx.healthcheck.tcp")

    def check(self, container: Mapping[str, Any]) -> HealthCheckResult:
        container_name = str(container.get("name", ""))
        target = self.targets.get(container_name)
        if not target:
            return HealthCheckResult(
                name=self.name,
                status="skipped",
                healthy=True,
                message="No TCP target configured",
            )
        host, port = self._parse_target(target)
        try:
            with socket.create_connection((host, port), timeout=self.timeout_seconds):
                return HealthCheckResult(name=self.name, status="open", healthy=True)
        except OSError as exc:
            return HealthCheckResult(
                name=self.name,
                status="closed",
                healthy=False,
                message=str(exc),
            )

    @staticmethod
    def _parse_target(target: str) -> tuple[str, int]:
        host, raw_port = target.rsplit(":", 1)
        return host, int(raw_port)
