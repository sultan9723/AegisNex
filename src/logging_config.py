"""Structured JSON logging with rotation for production AegisNex."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_entry.update(record.extra)
        return json.dumps(log_entry, default=str, sort_keys=True)


def configure_logging(
    log_dir: str | Path | None = None,
    log_level: str | None = None,
    log_retention_days: int = 30,
    json_format: bool = True,
) -> None:
    """Configure structured logging with rotation.

    Args:
        log_dir: Directory for log files. Defaults to BASE_DIR/logs.
        log_level: Logging level. Defaults to INFO.
        log_retention_days: Days to retain rotated logs.
        json_format: Use JSON format (True) or standard format.
    """
    if log_dir is None:
        log_dir = Path(__file__).resolve().parents[1] / "logs"
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    if log_level is None:
        log_level = os.getenv("AEGISNEX_LOG_LEVEL", "INFO").strip().upper()

    level = getattr(logging, log_level, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter: logging.Formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_dir / "aegisnex.log"),
        when="midnight",
        interval=1,
        backupCount=log_retention_days,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with structured logging support."""
    return logging.getLogger(name)
