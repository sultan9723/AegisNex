"""Docker container scanning utilities for AgentX."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import docker
from docker import errors as docker_errors


class DockerScanner:
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        include_all: bool = True,
        client_timeout_seconds: int = 10,
        restart_timeout_seconds: int = 10,
    ) -> None:
        self.logger = logger or logging.getLogger("agentx.docker")
        self.include_all = include_all
        self.client_timeout_seconds = client_timeout_seconds
        self.restart_timeout_seconds = restart_timeout_seconds

    def _client(self) -> Any:
        return docker.from_env(timeout=self.client_timeout_seconds)

    def ensure_running(self, container_name: str) -> Dict[str, Any]:
        try:
            client = self._client()
            container = client.containers.get(container_name)
            container.reload()
            status = container.status
            if status == "running":
                return {
                    "status": "ok",
                    "container": container.name,
                    "action": "already_running",
                }

            container.restart(timeout=self.restart_timeout_seconds)
            container.reload()
            return {
                "status": "ok",
                "container": container.name,
                "action": "restarted",
                "current_status": container.status,
            }
        except docker_errors.NotFound:
            self.logger.exception("Container not found: %s", container_name)
            return {
                "status": "error",
                "message": "Container not found",
                "container": container_name,
            }
        except docker_errors.DockerException as exc:
            self.logger.exception("Docker daemon not running: %s", exc)
            return {
                "status": "error",
                "message": "Docker daemon not running",
                "container": container_name,
            }
        except Exception as exc:
            self.logger.exception("Failed to restart container: %s", exc)
            return {
                "status": "error",
                "message": "Failed to restart container",
                "container": container_name,
            }

    def run(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            params = params or {}
            include_all = bool(params.get("include_all", self.include_all))
            client = self._client()
            client.ping()

            containers = client.containers.list(all=include_all)
            payload: List[Dict[str, str]] = [
                {
                    "id": container.short_id,
                    "name": container.name,
                    "status": self._map_status(container.status),
                    "raw_status": container.status,
                    "health_status": self._health_status(container),
                }
                for container in containers
            ]

            return {"status": "ok", "containers": payload}
        except docker_errors.DockerException as exc:
            self.logger.exception("Docker daemon not running: %s", exc)
            return {"status": "error", "message": "Docker daemon not running"}
        except Exception as exc:
            self.logger.exception("Docker scan failed: %s", exc)
            return {"status": "error", "message": "Docker scan failed"}

    def get_health_status(self, container_name: str) -> str:
        try:
            client = self._client()
            container = client.containers.get(container_name)
            container.reload()
            return self._health_status(container)
        except docker_errors.DockerException as exc:
            self.logger.exception("Docker health lookup failed: %s", exc)
            return "unknown"

    def restart_container(self, container_name: str) -> Dict[str, Any]:
        try:
            client = self._client()
            container = client.containers.get(container_name)
            container.restart(timeout=self.restart_timeout_seconds)
            container.reload()
            return {
                "status": "ok",
                "container": container.name,
                "action": "restarted",
                "current_status": container.status,
            }
        except docker_errors.NotFound:
            self.logger.exception("Container not found: %s", container_name)
            return {
                "status": "error",
                "message": "Container not found",
                "container": container_name,
            }
        except docker_errors.DockerException as exc:
            self.logger.exception("Docker daemon not running: %s", exc)
            return {
                "status": "error",
                "message": "Docker daemon not running",
                "container": container_name,
            }
        except Exception as exc:
            self.logger.exception("Failed to restart container: %s", exc)
            return {
                "status": "error",
                "message": "Failed to restart container",
                "container": container_name,
            }

    @staticmethod
    def _map_status(raw_status: str) -> str:
        if raw_status in {"exited", "dead", "created", "paused"}:
            return "stopped"
        if raw_status in {"removing", "restarting"}:
            return "error"
        return raw_status

    @staticmethod
    def _health_status(container: Any) -> str:
        state = getattr(container, "attrs", {}).get("State", {})
        health = state.get("Health", {})
        return str(health.get("Status", "none"))
