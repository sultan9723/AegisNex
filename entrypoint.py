from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

from src.agent import AgentX
from src.config import Config, ConfigError
from src.docker_scanner import DockerScanner
from src.guardian import Guardian
from src.health_checks import DockerHealthCheck, HttpHealthCheck, TcpHealthCheck
from src.incidents import IncidentManager
from src.monitor import SystemResourceMonitor
from src.notifier import Notifier
from src.orchestrator import SystemHealthChecker
from src.scanner import SecurityScanner


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    formatter.converter = time.gmtime

    file_handler = logging.FileHandler(log_dir / "aegisnex.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AegisNex scanning entrypoint")
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--scan", action="store_true", help="Process scan telemetry and output a report"
    )
    action_group.add_argument(
        "--report", action="store_true", help="Print the latest unified threat matrix"
    )
    action_group.add_argument(
        "--monitor",
        action="store_true",
        help="Print current system resource usage",
    )
    action_group.add_argument(
        "--docker",
        action="store_true",
        help="List running Docker containers",
    )
    action_group.add_argument(
        "--health",
        action="store_true",
        help="Run system health checks",
    )
    action_group.add_argument(
        "--guardian",
        action="store_true",
        help="Run autonomous guardian mode",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing telemetry JSON files",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to AegisNex YAML configuration",
    )
    return parser.parse_args(argv)


def load_report(output_path: Path, logger: logging.Logger) -> int:
    if not output_path.exists():
        logger.error("Report file not found: %s", output_path)
        return 1

    data: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))
    print(json.dumps(data, indent=2))
    return 0


def build_health_checks(config: Config, docker_scanner: DockerScanner) -> list[Any]:
    health_checks: list[Any] = []
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


def main() -> int:
    args = parse_args()
    setup_logging(Path("logs"))
    logger = logging.getLogger("entrypoint")
    try:
        config = Config.load(args.config)
    except ConfigError as exc:
        logger.error("Configuration validation failed: %s", exc)
        return 1

    agent = AgentX(logger=logging.getLogger("agentx"))
    monitor = SystemResourceMonitor(
        logger=logging.getLogger("agentx.monitor"),
        cpu_interval_seconds=config.monitoring.cpu_interval_seconds,
        thresholds=config.monitoring.thresholds,
    )
    agent.register_command("monitor", monitor)
    docker_scanner = DockerScanner(
        logger=logging.getLogger("agentx.docker"),
        include_all=config.docker.include_all,
        client_timeout_seconds=config.docker.client_timeout_seconds,
        restart_timeout_seconds=config.docker.restart_timeout_seconds,
    )
    agent.register_command("docker", docker_scanner)
    health_checker = SystemHealthChecker(
        monitor=monitor,
        docker_scanner=docker_scanner,
        logger=logging.getLogger("agentx.health"),
    )
    agent.register_command("health", health_checker)
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
        logger=logging.getLogger("agentx.notifier"),
    )
    guardian = Guardian(
        health_checker=health_checker,
        docker_scanner=docker_scanner,
        notifier=notifier,
        restart_cooldown_seconds=config.guardian.restart_cooldown_seconds,
        max_restart_attempts=config.guardian.max_restart_attempts,
        restart_history_path=config.guardian.restart_history_path,
        health_checks=build_health_checks(config, docker_scanner),
        incident_manager=IncidentManager(config.incidents.history_path),
        logger=logging.getLogger("agentx.guardian"),
    )
    agent.register_command("guardian", guardian)

    scanner = SecurityScanner(data_dir=args.data_dir)
    if args.scan:
        scanner.run_scan()
        return 0

    if args.monitor:
        payload = agent.execute_task("monitor", {})
        print("System resource usage:")
        print(json.dumps(payload, indent=2))
        return 0

    if args.docker:
        payload = agent.execute_task("docker", {})
        print("Docker containers:")
        print(json.dumps(payload, indent=2))
        return 0

    if args.health:
        payload = agent.execute_task("health", {})
        print("System health report:")
        print(json.dumps(payload, indent=2))
        return 0

    if args.guardian:
        payload = agent.execute_task("guardian", {})
        print("Guardian report:")
        print(json.dumps(payload, indent=2))
        return 0

    return load_report(scanner.output_matrix, logger)


if __name__ == "__main__":
    raise SystemExit(main())
