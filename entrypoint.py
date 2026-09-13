from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

from src.config import Config, ConfigError
from src.reporting import OperationalReporter, ReportFormat


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
    action_group.add_argument(
        "--weekly-report",
        action="store_true",
        help="Generate a weekly operational report from SQLite history",
    )
    action_group.add_argument(
        "--monthly-report",
        action="store_true",
        help="Generate a monthly operational report from SQLite history",
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
    parser.add_argument(
        "--report-format",
        choices=("json", "csv", "pdf"),
        default="json",
        help="Output format for weekly and monthly operational reports",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory for generated operational reports",
    )
    return parser.parse_args(argv)


def load_report(output_path: Path, logger: logging.Logger) -> int:
    if not output_path.exists():
        logger.error("Report file not found: %s", output_path)
        return 1

    data: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))
    print(json.dumps(data, indent=2))
    return 0


def build_health_checks(config: Config, docker_scanner: Any) -> list[Any]:
    from src.health_checks import DockerHealthCheck, HttpHealthCheck, TcpHealthCheck

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


def generate_operational_report(args: argparse.Namespace, config: Config) -> int:
    reporter = OperationalReporter(config.storage.database_path)
    report = (
        reporter.weekly_report()
        if args.weekly_report
        else reporter.monthly_report()
    )
    report_format: ReportFormat = args.report_format
    output_path = (
        Path(args.output_dir)
        / f"{report['report_type']}_operational_report.{report_format}"
    )
    written_path = reporter.export_report(report, output_path, report_format)
    print(f"Wrote {report['report_type']} operational report: {written_path}")
    print(json.dumps(report["summary"], indent=2))
    return 0


def run_scan(data_dir: str) -> int:
    from src.scanner import SecurityScanner

    scanner = SecurityScanner(data_dir=data_dir)
    scanner.run_scan()
    return 0


def print_latest_report(data_dir: str, logger: logging.Logger) -> int:
    from src.scanner import SecurityScanner

    scanner = SecurityScanner(data_dir=data_dir)
    return load_report(scanner.output_matrix, logger)


def run_monitor(config: Config) -> int:
    from src.agent import AgentX
    from src.monitor import SystemResourceMonitor

    agent = AgentX(logger=logging.getLogger("agentx"))
    monitor = SystemResourceMonitor(
        logger=logging.getLogger("agentx.monitor"),
        cpu_interval_seconds=config.monitoring.cpu_interval_seconds,
        thresholds=config.monitoring.thresholds,
    )
    agent.register_command("monitor", monitor)
    payload = agent.execute_task("monitor", {})
    print("System resource usage:")
    print(json.dumps(payload, indent=2))
    return 0


def build_docker_agent(config: Config) -> Any:
    from src.agent import AgentX
    from src.docker_scanner import DockerScanner
    from src.guardian import Guardian
    from src.incidents import IncidentManager
    from src.monitor import SystemResourceMonitor
    from src.notifications.factory import build_notification_providers
    from src.orchestrator import SystemHealthChecker
    from src.platform_db import PlatformRepository, load_database_settings

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
    notification_providers = build_notification_providers(config)
    storage_repository = PlatformRepository(
        config.storage.database_url or load_database_settings(config.storage.database_path)
    )
    from src.notifications_compat import NotifierCompat
    notifier = NotifierCompat(notification_providers)
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
            notification_providers=notification_providers,
            storage_repository=storage_repository,
        ),
        storage_repository=storage_repository,
        logger=logging.getLogger("agentx.guardian"),
    )
    agent.register_command("guardian", guardian)
    return agent


def run_docker_command(config: Config, command_name: str, heading: str) -> int:
    agent = build_docker_agent(config)
    payload = agent.execute_task(command_name, {})
    print(heading)
    print(json.dumps(payload, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    setup_logging(Path("logs"))
    logger = logging.getLogger("entrypoint")
    try:
        config = Config.load(args.config)
    except ConfigError as exc:
        logger.error("Configuration validation failed: %s", exc)
        return 1

    if args.weekly_report or args.monthly_report:
        return generate_operational_report(args, config)

    if args.scan:
        return run_scan(args.data_dir)

    if args.monitor:
        return run_monitor(config)

    if args.docker:
        return run_docker_command(config, "docker", "Docker containers:")

    if args.health:
        return run_docker_command(config, "health", "System health report:")

    if args.guardian:
        return run_docker_command(config, "guardian", "Guardian report:")

    return print_latest_report(args.data_dir, logger)


if __name__ == "__main__":
    raise SystemExit(main())
