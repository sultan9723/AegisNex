"""System resource monitoring utilities for AgentX."""

from __future__ import annotations

import importlib
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import ThresholdConfig


class SystemResourceMonitor:
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        log_file: str = "logs/agentx.log",
        cpu_interval_seconds: float = 0.1,
        thresholds: ThresholdConfig | None = None,
    ) -> None:
        self.logger = logger or self._build_logger(log_file)
        self.cpu_interval_seconds = cpu_interval_seconds
        self.thresholds = thresholds or ThresholdConfig(
            cpu_percent=90,
            memory_percent=90,
            disk_percent=90,
        )

    def _build_logger(self, log_file: str) -> logging.Logger:
        logger = logging.getLogger("agentx.monitor")
        if logger.handlers:
            return logger

        logger.setLevel(logging.INFO)
        logger.propagate = False

        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s - %(message)s"
        )

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        return logger

    def _load_psutil(self) -> Any:
        return importlib.import_module("psutil")

    def run(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            params = params or {}
            psutil = self._load_psutil()
            interval = float(params.get("cpu_interval", self.cpu_interval_seconds))
            cpu_percent = float(psutil.cpu_percent(interval=interval))
            cpu_count = psutil.cpu_count() if hasattr(psutil, "cpu_count") else 1
            cpu_count = cpu_count or 1
            cpu_load = [round(x / cpu_count * 100, 1) for x in psutil.getloadavg()] if hasattr(psutil, "getloadavg") else None
            ram = psutil.virtual_memory()
            ram_percent = float(ram.percent)
            disk = psutil.disk_usage("/")
            disk_percent = float(disk.percent)
            disk_free = getattr(disk, "free", None)
            disk_total = getattr(disk, "total", None)
            disk_free_gb = round(disk_free / (1024**3), 2) if disk_free is not None else None
            disk_total_gb = round(disk_total / (1024**3), 2) if disk_total is not None else None
            net = psutil.net_io_counters() if hasattr(psutil, "net_io_counters") else None
            uptime_seconds = int(time.time() - psutil.boot_time()) if hasattr(psutil, "boot_time") else None
            process_count = len(psutil.pids()) if hasattr(psutil, "pids") else None
            net = psutil.net_io_counters()
            uptime_seconds = int(time.time() - psutil.boot_time())
            process_count = len(psutil.pids())
            temperature = None
            if hasattr(psutil, "sensors_temperatures"):
                try:
                    temps = psutil.sensors_temperatures()
                    if temps:
                        core = temps.get("coretemp") or temps.get("cpu-thermal") or temps.get("cpu_thermal") or []
                        if core:
                            temperature = round(core[0].current, 1)
                except Exception:
                    pass
            warnings = self._evaluate_thresholds(
                cpu_percent=cpu_percent,
                ram_percent=ram_percent,
                disk_percent=disk_percent,
            )
            payload = {
                "status": "warning" if warnings else "ok",
                "cpu_percent": cpu_percent,
                "cpu_load_1m": cpu_load[0] if cpu_load else None,
                "cpu_load_5m": cpu_load[1] if cpu_load else None,
                "cpu_load_15m": cpu_load[2] if cpu_load else None,
                "ram_percent": ram_percent,
                "ram_used_gb": round(ram.used / (1024**3), 2),
                "ram_total_gb": round(ram.total / (1024**3), 2),
                "disk_percent": disk_percent,
                "disk_free_gb": disk_free_gb,
                "disk_total_gb": disk_total_gb,
                "network_bytes_sent": getattr(net, "bytes_sent", 0) if net is not None else 0,
                "network_bytes_recv": getattr(net, "bytes_recv", 0) if net is not None else 0,
                "uptime_seconds": uptime_seconds,
                "process_count": process_count,
                "temperature_celsius": temperature,
                "warnings": warnings,
            }
            return payload
        except Exception as exc:
            self.logger.exception("SystemResourceMonitor failed: %s", exc)
            return {"status": "failed", "error": str(exc)}

    def _evaluate_thresholds(
        self,
        cpu_percent: float,
        ram_percent: float,
        disk_percent: float,
    ) -> list[str]:
        warnings: list[str] = []
        if cpu_percent >= self.thresholds.cpu_percent:
            warnings.append("cpu_threshold_exceeded")
        if ram_percent >= self.thresholds.memory_percent:
            warnings.append("memory_threshold_exceeded")
        if disk_percent >= self.thresholds.disk_percent:
            warnings.append("disk_threshold_exceeded")
        return warnings
