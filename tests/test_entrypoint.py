import json
import logging
import importlib
from pathlib import Path
from types import SimpleNamespace
import builtins

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


class FakeOperationalReporter:
    exported = None

    def __init__(self, database_path):
        self.database_path = database_path

    def weekly_report(self):
        return {
            "report_type": "weekly",
            "summary": {"total_incidents": 1},
        }

    def monthly_report(self):
        return {
            "report_type": "monthly",
            "summary": {"total_incidents": 2},
        }

    def export_report(self, report, output_path, report_format):
        FakeOperationalReporter.exported = (report, output_path, report_format)
        return output_path


def patch_runtime(monkeypatch) -> None:
    monkeypatch.setattr(entrypoint, "setup_logging", lambda path: None)
    monkeypatch.setattr(entrypoint.Config, "load", lambda config_path: build_config())
    monkeypatch.setattr(entrypoint, "OperationalReporter", FakeOperationalReporter)
    monkeypatch.setattr(
        entrypoint,
        "run_monitor",
        lambda config: _print_fake_command("monitor", "System resource usage:"),
    )
    monkeypatch.setattr(
        entrypoint,
        "run_docker_command",
        lambda config, command_name, heading: _print_fake_command(command_name, heading),
    )
    monkeypatch.setattr(entrypoint, "run_scan", _fake_run_scan)
    monkeypatch.setattr(entrypoint, "print_latest_report", _fake_print_latest_report)


def _print_fake_command(command_name: str, heading: str) -> int:
    print(heading)
    print(json.dumps({"executed": command_name, "payload": {}}, indent=2))
    return 0


def _fake_run_scan(data_dir: str) -> int:
    FakeScanner(data_dir).run_scan()
    return 0


def _fake_print_latest_report(data_dir: str, logger: logging.Logger) -> int:
    return entrypoint.load_report(
        Path(data_dir) / "unified_threat_matrix.json",
        logger,
    )


def test_parse_args_accepts_config_path() -> None:
    args = entrypoint.parse_args(["--monitor", "--config", "custom.yaml"])

    assert args.monitor is True
    assert args.config == "custom.yaml"


def test_parse_args_accepts_operational_report_options() -> None:
    args = entrypoint.parse_args(
        [
            "--weekly-report",
            "--report-format",
            "csv",
            "--output-dir",
            "out",
        ]
    )

    assert args.weekly_report is True
    assert args.report_format == "csv"
    assert args.output_dir == "out"


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


def test_main_generates_operational_report(monkeypatch, tmp_path: Path, capsys) -> None:
    patch_runtime(monkeypatch)
    FakeOperationalReporter.exported = None
    monkeypatch.setattr(
        "sys.argv",
        [
            "entrypoint.py",
            "--weekly-report",
            "--report-format",
            "pdf",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert entrypoint.main() == 0
    output = capsys.readouterr().out
    assert "Wrote weekly operational report" in output
    assert '"total_incidents": 1' in output
    assert FakeOperationalReporter.exported[2] == "pdf"


def test_operational_report_does_not_import_docker(monkeypatch, tmp_path: Path) -> None:
    patch_runtime(monkeypatch)
    original_import = builtins.__import__

    def fail_on_docker_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"docker", "src.docker_scanner"}:
            raise ModuleNotFoundError("No module named 'docker'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_on_docker_import)
    monkeypatch.setattr(
        "sys.argv",
        [
            "entrypoint.py",
            "--weekly-report",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert entrypoint.main() == 0


def test_entrypoint_import_does_not_require_docker(monkeypatch) -> None:
    original_import = builtins.__import__

    def fail_on_docker_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"docker", "src.docker_scanner"}:
            raise ModuleNotFoundError("No module named 'docker'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_on_docker_import)

    reloaded_entrypoint = importlib.reload(entrypoint)

    assert reloaded_entrypoint.parse_args(["--weekly-report"]).weekly_report is True


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
