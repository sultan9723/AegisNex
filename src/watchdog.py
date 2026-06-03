"""Background watchdog for running Guardian checks."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import time
from pathlib import Path

from src.agent import AgentX
from src.docker_scanner import DockerScanner
from src.guardian import Guardian
from src.monitor import SystemResourceMonitor
from src.notifier import Notifier
from src.orchestrator import SystemHealthChecker


def setup_logging(log_path: Path) -> RotatingFileHandler:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    handler.setFormatter(formatter)
    return handler


def build_logger(name: str, handler: RotatingFileHandler) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        logger.addHandler(handler)
    return logger


def build_guardian(handler: RotatingFileHandler) -> Guardian:
    agent_logger = build_logger("agentx", handler)
    monitor_logger = build_logger("agentx.monitor", handler)
    docker_logger = build_logger("agentx.docker", handler)
    health_logger = build_logger("agentx.health", handler)
    notifier_logger = build_logger("agentx.notifier", handler)
    guardian_logger = build_logger("agentx.guardian", handler)

    agent = AgentX(logger=agent_logger)
    monitor = SystemResourceMonitor(logger=monitor_logger)
    docker_scanner = DockerScanner(logger=docker_logger)
    health_checker = SystemHealthChecker(
        monitor=monitor,
        docker_scanner=docker_scanner,
        logger=health_logger,
    )
    notifier = Notifier(logger=notifier_logger)
    guardian = Guardian(
        health_checker=health_checker,
        docker_scanner=docker_scanner,
        notifier=notifier,
        logger=guardian_logger,
    )

    agent.register_command("guardian", guardian)
    return guardian


def main() -> None:
    handler = setup_logging(Path("logs/agent.log"))
    watchdog_logger = build_logger("agentx.watchdog", handler)
    guardian = build_guardian(handler)

    watchdog_logger.info("Watchdog started")
    while True:
        try:
            guardian.run({})
            watchdog_logger.info("Guardian check completed")
        except Exception as exc:
            watchdog_logger.exception("Guardian check failed: %s", exc)
        time.sleep(300)


if __name__ == "__main__":
    main()
