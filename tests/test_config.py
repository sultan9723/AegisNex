from pathlib import Path

import pytest

from src.config import Config, ConfigError


def test_config_loads_yaml_and_env_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SMTP_ENABLED", raising=False)
    monkeypatch.delenv("EMAIL_USER", raising=False)
    monkeypatch.delenv("EMAIL_PASS", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
monitoring:
  cpu_interval_seconds: 0.2
  watchdog_interval_seconds: 60
  thresholds:
    cpu_percent: 80
    memory_percent: 85
    disk_percent: 90
docker:
  include_all: false
  client_timeout_seconds: 5
  restart_timeout_seconds: 7
guardian:
  restart_cooldown_seconds: 120
smtp:
  enabled: false
  host: smtp.example.com
  port: 2525
  timeout_seconds: 4
  starttls: false
  username: yaml-user
  password: yaml-pass
  recipient: yaml@example.com
  subject: YAML Alert
""".strip(),
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "SMTP_ENABLED=true",
                "EMAIL_USER=env-user",
                "EMAIL_PASS=env-pass",
                "EMAIL_TO=env@example.com",
            ]
        ),
        encoding="utf-8",
    )

    config = Config.load(config_path=config_path, env_path=env_path)

    assert config.monitoring.cpu_interval_seconds == 0.2
    assert config.docker.include_all is False
    assert config.guardian.restart_cooldown_seconds == 120
    assert config.guardian.max_restart_attempts == 3
    assert config.guardian.restart_history_path == "restart_history.json"
    assert config.incidents.history_path == "incident_history.json"
    assert config.smtp.enabled is True
    assert config.smtp.username == "env-user"
    assert config.smtp.password == "env-pass"
    assert config.smtp.recipient == "env@example.com"


def test_config_validation_rejects_invalid_threshold(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
monitoring:
  thresholds:
    cpu_percent: 101
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        Config.load(config_path=config_path, env_path=tmp_path / ".env")


def test_config_loads_health_check_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SMTP_ENABLED", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
health_checks:
  docker:
    enabled: true
  http:
    enabled: true
    timeout_seconds: 4
    expected_status: 204
    endpoints:
      api: http://localhost:8080/health
  tcp:
    enabled: true
    timeout_seconds: 3
    targets:
      db: localhost:5432
""".strip(),
        encoding="utf-8",
    )

    config = Config.load(config_path=config_path, env_path=tmp_path / ".env")

    assert config.health_checks.docker.enabled is True
    assert config.health_checks.http.enabled is True
    assert config.health_checks.http.timeout_seconds == 4
    assert config.health_checks.http.expected_status == 204
    assert config.health_checks.http.endpoints == {
        "api": "http://localhost:8080/health"
    }
    assert config.health_checks.tcp.enabled is True
    assert config.health_checks.tcp.timeout_seconds == 3
    assert config.health_checks.tcp.targets == {"db": "localhost:5432"}


def test_config_rejects_invalid_tcp_target(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
health_checks:
  tcp:
    enabled: true
    targets:
      db: localhost:not-a-port
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        Config.load(config_path=config_path, env_path=tmp_path / ".env")
