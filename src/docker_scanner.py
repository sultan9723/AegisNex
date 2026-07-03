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
        if not hasattr(self, "_docker_client") or self._docker_client is None:
            self._docker_client = docker.from_env(timeout=self.client_timeout_seconds)
        return self._docker_client

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
            payload: List[Dict[str, object]] = []
            for container in containers:
                container_stats = self._container_stats(container)
                started_at = container.attrs.get("State", {}).get("StartedAt") if hasattr(container, "attrs") else None
                uptime_seconds = None
                if started_at and container.status == "running":
                    try:
                        from datetime import datetime, timezone
                        parsed = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                        uptime_seconds = int((datetime.now(timezone.utc) - parsed).total_seconds())
                    except Exception:
                        pass
                payload.append({
                    "id": container.short_id,
                    "name": container.name,
                    "status": self._map_status(container.status),
                    "raw_status": container.status,
                    "health_status": self._health_status(container),
                    "image": container.image.tags[0] if container.image and container.image.tags else str(container.image.short_id) if container.image else "unknown",
                    "started_at": started_at,
                    "uptime_seconds": uptime_seconds,
                    "ports": self._ports(container),
                    "cpu_percent": container_stats.get("cpu_percent"),
                    "memory_usage_bytes": container_stats.get("memory_usage_bytes"),
                    "memory_limit_bytes": container_stats.get("memory_limit_bytes"),
                    "memory_percent": container_stats.get("memory_percent"),
                })

            return {"status": "ok", "containers": payload}
        except docker_errors.DockerException as exc:
            self.logger.exception("Docker daemon not running: %s", exc)
            return {"status": "error", "message": "Docker daemon not running"}
        except Exception as exc:
            self.logger.exception("Docker scan failed: %s", exc)
            return {"status": "error", "message": "Docker scan failed"}

    @staticmethod
    def _container_stats(container: Any) -> Dict[str, Any]:
        """Return CPU percent and memory stats for a single container."""
        result: Dict[str, Any] = {
            "cpu_percent": None,
            "memory_usage_bytes": None,
            "memory_limit_bytes": None,
            "memory_percent": None,
        }
        try:
            stats = container.stats(stream=False)
            if not stats:
                return result
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})
            cpu_usage = cpu_stats.get("cpu_usage", {})
            precpu_usage = precpu_stats.get("cpu_usage", {})
            cpu_delta = cpu_usage.get("total_usage", 0) - precpu_usage.get("total_usage", 0)
            system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)
            num_cpus = cpu_stats.get("online_cpus", 1) or 1
            if system_delta > 0 and cpu_delta > 0:
                result["cpu_percent"] = round((cpu_delta / system_delta) * num_cpus * 100.0, 2)
            mem_stats = stats.get("memory_stats", {})
            usage = mem_stats.get("usage")
            limit = mem_stats.get("limit")
            result["memory_usage_bytes"] = usage
            result["memory_limit_bytes"] = limit
            if usage is not None and limit and limit > 0:
                result["memory_percent"] = round((usage / limit) * 100.0, 2)
        except Exception:
            pass
        return result

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

    @staticmethod
    def _ports(container: Any) -> List[Dict[str, object]]:
        result: List[Dict[str, object]] = []
        raw_ports = getattr(container, "ports", {}) or {}
        for container_port, mappings in raw_ports.items():
            if mappings:
                for mapping in mappings:
                    result.append({
                        "container_port": container_port,
                        "host_port": mapping.get("HostPort"),
                        "host_ip": mapping.get("HostIp"),
                    })
            else:
                result.append({"container_port": container_port, "host_port": None, "host_ip": None})
        return result

    def start_container(self, container_name: str) -> Dict[str, Any]:
        try:
            client = self._client()
            container = client.containers.get(container_name)
            container.start()
            container.reload()
            return {"status": "ok", "container": container.name, "current_status": container.status}
        except docker_errors.NotFound:
            return {"status": "error", "message": "Container not found", "container": container_name}
        except docker_errors.DockerException as exc:
            return {"status": "error", "message": str(exc), "container": container_name}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "container": container_name}

    def stop_container(self, container_name: str) -> Dict[str, Any]:
        try:
            client = self._client()
            container = client.containers.get(container_name)
            container.stop(timeout=10)
            container.reload()
            return {"status": "ok", "container": container.name, "current_status": container.status}
        except docker_errors.NotFound:
            return {"status": "error", "message": "Container not found", "container": container_name}
        except docker_errors.DockerException as exc:
            return {"status": "error", "message": str(exc), "container": container_name}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "container": container_name}

    def get_container_logs(self, container_name: str, tail: int = 100) -> Dict[str, Any]:
        try:
            client = self._client()
            container = client.containers.get(container_name)
            logs = container.logs(tail=tail, timestamps=True)
            decoded = logs.decode("utf-8", errors="replace") if isinstance(logs, bytes) else str(logs)
            lines = decoded.splitlines()
            return {"status": "ok", "container": container_name, "logs": lines, "count": len(lines)}
        except docker_errors.NotFound:
            return {"status": "error", "message": "Container not found", "container": container_name}
        except docker_errors.DockerException as exc:
            return {"status": "error", "message": str(exc), "container": container_name}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "container": container_name}
