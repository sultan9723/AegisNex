"""Prometheus metrics exporter for AegisNex."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Dict, Mapping


PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@dataclass(frozen=True)
class MetricSnapshot:
    values: Dict[str, float]


class PrometheusExporter:
    def __init__(self, services: Any) -> None:
        self.services = services

    def collect(self, persist: bool = True) -> MetricSnapshot:
        metrics = self._collect_system_metrics()
        metrics.update(self._collect_container_metrics())
        metrics.update(self._collect_incident_metrics())
        metrics.update(self._collect_remediation_metrics())
        metrics.update(self._collect_notification_metrics())
        metrics.update(self._collect_target_metrics())
        metrics.update(self._collect_container_detail_metrics())
        if persist:
            storage_repository = getattr(self.services, "storage_repository", None)
            if storage_repository:
                storage_repository.save_metrics_snapshot(metrics)
        return MetricSnapshot(values=metrics)

    def render(self) -> tuple[bytes, str]:
        snapshot = self.collect()
        try:
            from prometheus_client import CollectorRegistry, Gauge, generate_latest
            from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST
        except ModuleNotFoundError:
            return self._render_text(snapshot.values), PROMETHEUS_CONTENT_TYPE

        registry = CollectorRegistry()
        for metric_name, value in snapshot.values.items():
            gauge = Gauge(
                metric_name,
                metric_name.replace("_", " "),
                registry=registry,
            )
            gauge.set(value)
        return generate_latest(registry), CONTENT_TYPE_LATEST

    def _collect_system_metrics(self) -> Dict[str, float]:
        monitor_payload = self.services.monitor.run({})
        network = self._network_stats()
        return {
            "aegisnex_system_cpu_usage_percent": _float_value(
                monitor_payload.get("cpu_percent")
            ),
            "aegisnex_system_memory_usage_percent": _float_value(
                monitor_payload.get("ram_percent")
            ),
            "aegisnex_system_disk_usage_percent": _float_value(
                monitor_payload.get("disk_percent")
            ),
            "aegisnex_system_network_bytes_sent": _float_value(
                network.get("bytes_sent")
            ),
            "aegisnex_system_network_bytes_received": _float_value(
                network.get("bytes_recv")
            ),
        }

    def _collect_container_metrics(self) -> Dict[str, float]:
        docker_payload = self.services.docker_scanner.run({"include_all": True})
        containers = (
            docker_payload.get("containers", [])
            if docker_payload.get("status") == "ok"
            else []
        )
        running = 0
        stopped = 0
        unhealthy = 0
        for container in containers:
            status = str(container.get("status", ""))
            health_status = str(container.get("health_status", ""))
            if status == "running":
                running += 1
            if status == "stopped":
                stopped += 1
            if status == "error" or health_status == "unhealthy":
                unhealthy += 1
        return {
            "aegisnex_containers_running": float(running),
            "aegisnex_containers_stopped": float(stopped),
            "aegisnex_containers_unhealthy": float(unhealthy),
        }

    def _collect_incident_metrics(self) -> Dict[str, float]:
        incidents = self.services.incident_manager.list_incidents()
        active = sum(1 for incident in incidents if incident.status == "active")
        resolved = sum(1 for incident in incidents if incident.status == "resolved")
        return {
            "aegisnex_incidents_active": float(active),
            "aegisnex_incidents_resolved": float(resolved),
            "aegisnex_incidents_total": float(len(incidents)),
        }

    def _collect_remediation_metrics(self) -> Dict[str, float]:
        restart_history = load_restart_history(self.services.restart_history_path)
        incidents = self.services.incident_manager.list_incidents()
        restart_attempts = sum(
            int(history.get("attempts", 0)) for history in restart_history.values()
        )
        successful = sum(
            1
            for incident in incidents
            if incident.remediation_attempted and incident.remediation_successful
        )
        failed = sum(
            1
            for incident in incidents
            if incident.remediation_attempted and not incident.remediation_successful
        )
        return {
            "aegisnex_remediation_restart_attempts_total": float(restart_attempts),
            "aegisnex_remediation_successful_restarts_total": float(successful),
            "aegisnex_remediation_failed_restarts_total": float(failed),
        }

    def _collect_notification_metrics(self) -> Dict[str, float]:
        events = self.services.incident_manager.list_notification_events()
        sent = sum(1 for event in events if event.get("status") == "ok")
        failed = sum(1 for event in events if event.get("status") == "error")
        return {
            "aegisnex_notifications_sent_total": float(sent),
            "aegisnex_notifications_failed_total": float(failed),
        }

    def _collect_target_metrics(self) -> Dict[str, float]:
        """Collect monitoring target health metrics."""
        repository = getattr(self.services, "platform_repository", None)
        if repository is None:
            return {}
        try:
            targets = repository.list_monitoring_targets()
        except Exception:
            return {}
        total = len(targets)
        active = sum(1 for t in targets if t.get("is_active", True))
        healthy = 0
        unhealthy = 0
        for t in targets:
            last_error = t.get("last_error")
            if not t.get("is_active", True):
                continue
            if last_error:
                unhealthy += 1
            else:
                healthy += 1
        return {
            "aegisnex_targets_total": float(total),
            "aegisnex_targets_active": float(active),
            "aegisnex_targets_healthy": float(healthy),
            "aegisnex_targets_unhealthy": float(unhealthy),
        }

    def _collect_container_detail_metrics(self) -> Dict[str, float]:
        """Collect per-container CPU/memory metrics."""
        docker_payload = self.services.docker_scanner.run({"include_all": True})
        containers = (
            docker_payload.get("containers", [])
            if docker_payload.get("status") == "ok"
            else []
        )
        total_cpu = 0.0
        total_mem = 0.0
        container_count = 0
        for container in containers:
            cpu = container.get("cpu_percent")
            mem = container.get("memory_percent")
            if cpu is not None:
                total_cpu += float(cpu)
            if mem is not None:
                total_mem += float(mem)
            container_count += 1
        return {
            "aegisnex_containers_total_cpu_percent": total_cpu,
            "aegisnex_containers_total_memory_percent": total_mem,
            "aegisnex_containers_with_metrics": float(container_count),
        }

    @staticmethod
    def _network_stats() -> Dict[str, Any]:
        try:
            import psutil

            counters = psutil.net_io_counters()
            return {
                "bytes_sent": counters.bytes_sent,
                "bytes_recv": counters.bytes_recv,
            }
        except Exception:
            return {"bytes_sent": 0, "bytes_recv": 0}

    @staticmethod
    def _render_text(values: Mapping[str, float]) -> bytes:
        lines: list[str] = []
        for metric_name, value in sorted(values.items()):
            lines.append(f"# HELP {metric_name} {metric_name.replace('_', ' ')}")
            lines.append(f"# TYPE {metric_name} gauge")
            lines.append(f"{metric_name} {value}")
        return ("\n".join(lines) + "\n").encode("utf-8")


def load_restart_history(path: str | Path) -> Dict[str, Dict[str, Any]]:
    history_path = Path(path)
    if not history_path.exists():
        return {}
    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(name): value
        for name, value in payload.items()
        if isinstance(value, dict)
    }


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
