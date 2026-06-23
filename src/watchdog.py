"""Background watchdog for running Guardian checks."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import time
from pathlib import Path

from src.agent import AgentX
from src.config import Config
from src.docker_scanner import DockerScanner
from src.guardian import Guardian
from src.health_checks import DockerHealthCheck, HttpHealthCheck, TcpHealthCheck
from src.incidents import IncidentManager
from src.monitor import SystemResourceMonitor
from src.notifier import Notifier
from src.notifications.factory import build_notification_providers
from src.orchestrator import SystemHealthChecker
from src.platform_db import PlatformRepository, load_database_settings


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


def build_health_checks(config: Config, docker_scanner: DockerScanner) -> list[object]:
    health_checks: list[object] = []
    if config.health_checks.docker.enabled:
        health_checks.append(DockerHealthCheck(docker_scanner=docker_scanner))
    if config.health_checks.http.enabled:
        health_checks.append(
            HttpHealthCheck(
                endpoints=config.health_checks.http.endpoints,
                timeout_seconds=config.health_checks.http.timeout_seconds,
                expected_status=config.health_checks.http.expected_status,
            )
        )
    if config.health_checks.tcp.enabled:
        health_checks.append(
            TcpHealthCheck(
                targets=config.health_checks.tcp.targets,
                timeout_seconds=config.health_checks.tcp.timeout_seconds,
            )
        )
    return health_checks


def build_guardian(handler: RotatingFileHandler, config: Config) -> Guardian:
    agent_logger = build_logger("agentx", handler)
    monitor_logger = build_logger("agentx.monitor", handler)
    docker_logger = build_logger("agentx.docker", handler)
    health_logger = build_logger("agentx.health", handler)
    notifier_logger = build_logger("agentx.notifier", handler)
    guardian_logger = build_logger("agentx.guardian", handler)

    agent = AgentX(logger=agent_logger)
    monitor = SystemResourceMonitor(
        logger=monitor_logger,
        cpu_interval_seconds=config.monitoring.cpu_interval_seconds,
        thresholds=config.monitoring.thresholds,
    )
    docker_scanner = DockerScanner(
        logger=docker_logger,
        include_all=config.docker.include_all,
        client_timeout_seconds=config.docker.client_timeout_seconds,
        restart_timeout_seconds=config.docker.restart_timeout_seconds,
    )
    health_checker = SystemHealthChecker(
        monitor=monitor,
        docker_scanner=docker_scanner,
        logger=health_logger,
    )
    notifier = Notifier(
        enabled=config.smtp.enabled,
        smtp_host=config.smtp.host,
        smtp_port=config.smtp.port,
        smtp_timeout_seconds=config.smtp.timeout_seconds,
        starttls=config.smtp.starttls,
        email_user=config.smtp.username,
        email_pass=config.smtp.password,
        email_to=config.smtp.recipient,
        subject=config.smtp.subject,
        logger=notifier_logger,
    )
    platform_repository = PlatformRepository(
        config.storage.database_url
        or load_database_settings(config.storage.database_path)
    )
    guardian = Guardian(
        health_checker=health_checker,
        docker_scanner=docker_scanner,
        notifier=notifier,
        restart_cooldown_seconds=config.guardian.restart_cooldown_seconds,
        max_restart_attempts=config.guardian.max_restart_attempts,
        restart_history_path=config.guardian.restart_history_path,
        health_checks=build_health_checks(config, docker_scanner),
        incident_manager=IncidentManager(
            config.incidents.history_path,
            notification_providers=build_notification_providers(config),
            storage_repository=platform_repository,
        ),
        storage_repository=platform_repository,
        logger=guardian_logger,
    )

    agent.register_command("guardian", guardian)
    return guardian


def main() -> None:
    handler = setup_logging(Path("logs/agent.log"))
    watchdog_logger = build_logger("agentx.watchdog", handler)
    config = Config.load()
    guardian = build_guardian(handler, config)

    watchdog_logger.info("Watchdog started")
    while True:
        try:
            guardian.run({})
            watchdog_logger.info("Guardian check completed")
        except Exception as exc:
            watchdog_logger.exception("Guardian check failed: %s", exc)
        time.sleep(config.monitoring.watchdog_interval_seconds)


if __name__ == "__main__":
    main()