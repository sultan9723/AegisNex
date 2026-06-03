"""Docker container scanning utilities for AgentX."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import docker
from docker import errors as docker_errors


class DockerScanner:
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger("agentx.docker")

    def ensure_running(self, container_name: str) -> Dict[str, Any]:
        try:
            client = docker.from_env()
            container = client.containers.get(container_name)
            container.reload()
            status = container.status
            if status == "running":
                return {
                    "status": "ok",
                    "container": container.name,
                    "action": "already_running",
                }

            container.restart()
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
            include_all = bool(params.get("include_all", False))
            client = docker.from_env()
            client.ping()

            containers = client.containers.list(all=include_all)
            payload: List[Dict[str, str]] = [
                {
                    "id": container.short_id,
                    "name": container.name,
                    "status": self._map_status(container.status),
                    "raw_status": container.status,
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

    @staticmethod
    def _map_status(raw_status: str) -> str:
        if raw_status in {"exited", "dead", "created", "paused"}:
            return "stopped"
        if raw_status in {"removing", "restarting"}:
            return "error"
        return raw_status
