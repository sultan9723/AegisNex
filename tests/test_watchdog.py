import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import Config
from src.guardian import Guardian
from src.health_checks import DockerHealthCheck
from src.notifications_compat import NotifierCompat
import src.watchdog as watchdog


def build_test_config() -> Config:
    return Config.from_mapping(
        {
            "monitoring": {
                "cpu_interval_seconds": 0.2,
                "watchdog_interval_seconds": 11,
                "thresholds": {
                    "cpu_percent": 80,
                    "memory_percent": 81,
                    "disk_percent": 82,
                },
            },
            "docker": {
                "include_all": False,
                "client_timeout_seconds": 5,
                "restart_timeout_seconds": 6,
            },
            "guardian": {
                "restart_cooldown_seconds": 123,
                "max_restart_attempts": 4,
                "restart_history_path": "custom_restart_history.json",
            },
            "incidents": {"history_path": "custom_incident_history.json"},
            "smtp": {
                "enabled": True,
                "host": "smtp.example.com",
                "port": 2525,
                "timeout_seconds": 4,
                "starttls": False,
                "username": "sender",
                "password": "secret",
                "recipient": "ops@example.com",
                "subject": "Watchdog Alert",
            },
        }
    )


def test_setup_logging_creates_rotating_handler(tmp_path: Path) -> None:
    handler = watchdog.setup_logging(tmp_path / "agent.log")

    assert handler.maxBytes == 1_000_000
    assert handler.backupCount == 5


def test_build_logger_reuses_existing_handlers() -> None:
    name = "tests.watchdog.logger"
    logger = logging.getLogger(name)
    logger.handlers.clear()
    handler = logging.NullHandler()

    first = watchdog.build_logger(name, handler)
    second = watchdog.build_logger(name, handler)

    assert first is second
    assert first.level == logging.INFO
    assert first.propagate is False
    assert first.handlers.count(handler) == 1


def test_build_guardian_wires_config_values(tmp_path: Path) -> None:
    handler = watchdog.setup_logging(tmp_path / "agent.log")
    guardian = watchdog.build_guardian(handler, build_test_config())

    assert isinstance(guardian, Guardian)
    assert guardian.restart_cooldown_seconds == 123
    assert guardian.max_restart_attempts == 4
    assert str(guardian.restart_history_path) == "custom_restart_history.json"
    assert str(guardian.incident_manager.history_path) == "custom_incident_history.json"
    assert guardian.docker_scanner.include_all is False
    assert guardian.docker_scanner.client_timeout_seconds == 5
    assert guardian.docker_scanner.restart_timeout_seconds == 6
    assert guardian.notifier is not None
    assert isinstance(guardian.notifier, NotifierCompat)
    assert guardian.health_checker.monitor.cpu_interval_seconds == 0.2
    assert guardian.health_checker.monitor.thresholds.cpu_percent == 80
    assert len(guardian.health_checks) == 1
    assert isinstance(guardian.health_checks[0], DockerHealthCheck)


def test_main_runs_guardian_once_and_sleeps_with_config_interval(monkeypatch) -> None:
    fake_guardian = SimpleNamespace(run=lambda params: {"actions": []})
    sleep_calls = []

    monkeypatch.setattr(watchdog.Config, "load", lambda: build_test_config())
    monkeypatch.setattr(watchdog, "setup_logging", lambda path: logging.NullHandler())
    monkeypatch.setattr(watchdog, "build_guardian", lambda handler, config: fake_guardian)
    monkeypatch.setattr(watchdog, "build_logger", lambda name, handler: logging.getLogger(name))

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(watchdog.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        watchdog.main()

    assert sleep_calls == [11]


def test_main_logs_guardian_failure_before_next_sleep(monkeypatch) -> None:
    class FailingGuardian:
        def run(self, params):
            raise RuntimeError("guardian failed")

    logger = SimpleNamespace(info=lambda *args: None, exception_calls=[])
    logger.exception = lambda *args: logger.exception_calls.append(args)

    monkeypatch.setattr(watchdog.Config, "load", lambda: build_test_config())
    monkeypatch.setattr(watchdog, "setup_logging", lambda path: logging.NullHandler())
    monkeypatch.setattr(watchdog, "build_guardian", lambda handler, config: FailingGuardian())
    monkeypatch.setattr(watchdog, "build_logger", lambda name, handler: logger)
    monkeypatch.setattr(
        watchdog.time,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    with pytest.raises(KeyboardInterrupt):
        watchdog.main()

    assert logger.exception_calls
