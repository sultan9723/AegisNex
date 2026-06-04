import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

import entrypoint
from src.config import Config, ConfigError
from src.health_checks import DockerHealthCheck, HttpHealthCheck, TcpHealthCheck


def build_config() -> Config:
    return Config.from_mapping(
        {
            "monitoring": {
                "cpu_interval_seconds": 0.1,
                "watchdog_interval_seconds": 300,
                "thresholds": {
                    "cpu_percent": 90,
                    "memory_percent": 90,
                    "disk_percent": 90,
                },
            },
            "docker": {
                "include_all": True,
                "client_timeout_seconds": 10,
                "restart_timeout_seconds": 10,
            },
            "guardian": {"restart_cooldown_seconds": 300},
            "smtp": {"enabled": False},
        }
    )


class FakeAgent:
    def __init__(self, logger=None):
        self.commands = {}

    def register_command(self, name, instance):
        self.commands[name] = instance

    def execute_task(self, name, payload):
        return {"executed": name, "payload": payload}


class FakeScanner:
    run_scan_calls = 0
    output_matrix = Path("unused.json")

    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        FakeScanner.output_matrix = Path(data_dir) / "unified_threat_matrix.json"

    def run_scan(self):
        FakeScanner.run_scan_calls += 1
        return {"status": "ok"}


def patch_runtime(monkeypatch) -> None:
    monkeypatch.setattr(entrypoint, "setup_logging", lambda path: None)
    monkeypatch.setattr(entrypoint.Config, "load", lambda config_path: build_config())
    monkeypatch.setattr(entrypoint, "AgentX", FakeAgent)
    monkeypatch.setattr(entrypoint, "SystemResourceMonitor", lambda **kwargs: object())
    monkeypatch.setattr(entrypoint, "DockerScanner", lambda **kwargs: SimpleNamespace(include_all=True))
    monkeypatch.setattr(entrypoint, "SystemHealthChecker", lambda **kwargs: object())
    monkeypatch.setattr(entrypoint, "Notifier", lambda **kwargs: object())
    monkeypatch.setattr(entrypoint, "Guardian", lambda **kwargs: object())
    monkeypatch.setattr(entrypoint, "SecurityScanner", FakeScanner)


def test_parse_args_accepts_config_path() -> None:
    args = entrypoint.parse_args(["--monitor", "--config", "custom.yaml"])

    assert args.monitor is True
    assert args.config == "custom.yaml"


def test_load_report_prints_existing_report(tmp_path: Path, capsys) -> None:
    output = tmp_path / "report.json"
    output.write_text(json.dumps({"status": "ok"}), encoding="utf-8")

    result = entrypoint.load_report(output, logging.getLogger("tests.entrypoint"))

    assert result == 0
    assert '"status": "ok"' in capsys.readouterr().out


def test_load_report_returns_error_for_missing_report(tmp_path: Path) -> None:
    result = entrypoint.load_report(
        tmp_path / "missing.json", logging.getLogger("tests.entrypoint")
    )

    assert result == 1


@pytest.mark.parametrize(
    "flag, command_name, heading",
    [
        ("--monitor", "monitor", "System resource usage:"),
        ("--docker", "docker", "Docker containers:"),
        ("--health", "health", "System health report:"),
        ("--guardian", "guardian", "Guardian report:"),
    ],
)
def test_main_executes_agent_commands(monkeypatch, capsys, flag, command_name, heading) -> None:
    patch_runtime(monkeypatch)
    monkeypatch.setattr("sys.argv", ["entrypoint.py", flag])

    result = entrypoint.main()

    output = capsys.readouterr().out
    assert result == 0
    assert heading in output
    assert f'"executed": "{command_name}"' in output


def test_main_scan_runs_security_scanner(monkeypatch, tmp_path: Path) -> None:
    patch_runtime(monkeypatch)
    FakeScanner.run_scan_calls = 0
    monkeypatch.setattr(
        "sys.argv",
        ["entrypoint.py", "--scan", "--data-dir", str(tmp_path)],
    )

    assert entrypoint.main() == 0
    assert FakeScanner.run_scan_calls == 1


def test_main_report_loads_scanner_output(monkeypatch, tmp_path: Path, capsys) -> None:
    patch_runtime(monkeypatch)
    report = tmp_path / "unified_threat_matrix.json"
    report.write_text(json.dumps({"asset_target": "example.org"}), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["entrypoint.py", "--report", "--data-dir", str(tmp_path)],
    )

    assert entrypoint.main() == 0
    assert "example.org" in capsys.readouterr().out


def test_main_returns_error_when_config_validation_fails(monkeypatch) -> None:
    monkeypatch.setattr(entrypoint, "setup_logging", lambda path: None)
    monkeypatch.setattr(
        entrypoint.Config,
        "load",
        lambda config_path: (_ for _ in ()).throw(ConfigError("bad config")),
    )
    monkeypatch.setattr("sys.argv", ["entrypoint.py", "--monitor"])

    assert entrypoint.main() == 1


def test_build_health_checks_uses_enabled_config() -> None:
    config = Config.from_mapping(
        {
            "health_checks": {
                "docker": {"enabled": True},
                "http": {
                    "enabled": True,
                    "timeout_seconds": 2,
                    "expected_status": 204,
                    "endpoints": {"api": "http://localhost:8080/health"},
                },
                "tcp": {
                    "enabled": True,
                    "timeout_seconds": 3,
                    "targets": {"db": "localhost:5432"},
                },
            }
        }
    )
    checks = entrypoint.build_health_checks(config, SimpleNamespace())

    assert [type(check) for check in checks] == [
        DockerHealthCheck,
        HttpHealthCheck,
        TcpHealthCheck,
    ]
