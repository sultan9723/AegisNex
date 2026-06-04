"""System resource monitoring utilities for AgentX."""

from __future__ import annotations

import importlib
import logging
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
            ram_percent = float(psutil.virtual_memory().percent)
            disk_percent = float(psutil.disk_usage("/").percent)
            warnings = self._evaluate_thresholds(
                cpu_percent=cpu_percent,
                ram_percent=ram_percent,
                disk_percent=disk_percent,
            )
            payload = {
                "status": "warning" if warnings else "ok",
                "cpu_percent": cpu_percent,
                "ram_percent": ram_percent,
                "disk_percent": disk_percent,
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
