"""Centralized configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Mapping


class ConfigError(ValueError):
    """Raised when configuration is missing, malformed, or unsafe."""


@dataclass(frozen=True)
class ThresholdConfig:
    cpu_percent: float
    memory_percent: float
    disk_percent: float


@dataclass(frozen=True)
class MonitoringConfig:
    cpu_interval_seconds: float
    watchdog_interval_seconds: int
    thresholds: ThresholdConfig


@dataclass(frozen=True)
class DockerConfig:
    include_all: bool
    client_timeout_seconds: int
    restart_timeout_seconds: int


@dataclass(frozen=True)
class GuardianConfig:
    restart_cooldown_seconds: int
    max_restart_attempts: int
    restart_history_path: str


@dataclass(frozen=True)
class DockerHealthCheckConfig:
    enabled: bool


@dataclass(frozen=True)
class HttpHealthCheckConfig:
    enabled: bool
    timeout_seconds: int
    expected_status: int
    endpoints: dict[str, str]


@dataclass(frozen=True)
class TcpHealthCheckConfig:
    enabled: bool
    timeout_seconds: int
    targets: dict[str, str]


@dataclass(frozen=True)
class HealthChecksConfig:
    docker: DockerHealthCheckConfig
    http: HttpHealthCheckConfig
    tcp: TcpHealthCheckConfig


@dataclass(frozen=True)
class IncidentConfig:
    history_path: str


@dataclass(frozen=True)
class NotificationProviderConfig:
    enabled: bool
    retry_attempts: int
    retry_delay_seconds: float
    timeout_seconds: int
    message_template: str
    resolution_template: str


@dataclass(frozen=True)
class EmailNotificationConfig(NotificationProviderConfig):
    host: str
    port: int
    starttls: bool
    username: str
    password: str
    sender: str
    recipient: str
    subject: str


@dataclass(frozen=True)
class WebhookNotificationConfig(NotificationProviderConfig):
    webhook_url: str


@dataclass(frozen=True)
class NotificationsConfig:
    email: EmailNotificationConfig
    slack: WebhookNotificationConfig
    discord: WebhookNotificationConfig


@dataclass(frozen=True)
class SMTPConfig:
    enabled: bool
    host: str
    port: int
    timeout_seconds: int
    starttls: bool
    username: str
    password: str
    recipient: str
    subject: str


@dataclass(frozen=True)
class Config:
    monitoring: MonitoringConfig
    docker: DockerConfig
    guardian: GuardianConfig
    incidents: IncidentConfig
    notifications: NotificationsConfig
    health_checks: HealthChecksConfig
    smtp: SMTPConfig

    @classmethod
    def load(
        cls,
        config_path: str | Path = "config.yaml",
        env_path: str | Path = ".env",
    ) -> "Config":
        load_env_file(env_path)
        path = Path(config_path)
        if not path.exists():
            raise ConfigError(f"Configuration file not found: {path}")

        raw = _parse_simple_yaml(path.read_text(encoding="utf-8"))

        if not isinstance(raw, Mapping):
            raise ConfigError("Configuration root must be a mapping.")

        config = cls.from_mapping(raw)
        config.validate()
        return config

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "Config":
        monitoring_raw = _section(raw, "monitoring")
        thresholds_raw = _section(monitoring_raw, "thresholds")
        docker_raw = _section(raw, "docker")
        guardian_raw = _section(raw, "guardian")
        incidents_raw = _section(raw, "incidents")
        notifications_raw = _section(raw, "notifications")
        notification_email_raw = _section(notifications_raw, "email")
        notification_slack_raw = _section(notifications_raw, "slack")
        notification_discord_raw = _section(notifications_raw, "discord")
        health_checks_raw = _section(raw, "health_checks")
        docker_health_raw = _section(health_checks_raw, "docker")
        http_health_raw = _section(health_checks_raw, "http")
        tcp_health_raw = _section(health_checks_raw, "tcp")
        smtp_raw = _section(raw, "smtp")

        smtp_username = _env_first(
            ("SMTP_USERNAME", "EMAIL_USER"),
            _str(smtp_raw, "username", ""),
        )
        smtp_password = _env_first(
            ("SMTP_PASSWORD", "EMAIL_PASS"),
            _str(smtp_raw, "password", ""),
        )
        smtp_recipient = _env_first(
            ("SMTP_RECIPIENT", "EMAIL_TO"),
            _str(smtp_raw, "recipient", ""),
        )
        smtp_enabled = _env_bool(
            "SMTP_ENABLED",
            _bool(smtp_raw, "enabled", False)
            or all((smtp_username, smtp_password, smtp_recipient)),
        )

        return cls(
            monitoring=MonitoringConfig(
                cpu_interval_seconds=_float(
                    monitoring_raw, "cpu_interval_seconds", 0.1
                ),
                watchdog_interval_seconds=_int(
                    monitoring_raw, "watchdog_interval_seconds", 300
                ),
                thresholds=ThresholdConfig(
                    cpu_percent=_float(thresholds_raw, "cpu_percent", 90),
                    memory_percent=_float(thresholds_raw, "memory_percent", 90),
                    disk_percent=_float(thresholds_raw, "disk_percent", 90),
                ),
            ),
            docker=DockerConfig(
                include_all=_bool(docker_raw, "include_all", True),
                client_timeout_seconds=_int(
                    docker_raw, "client_timeout_seconds", 10
                ),
                restart_timeout_seconds=_int(
                    docker_raw, "restart_timeout_seconds", 10
                ),
            ),
            guardian=GuardianConfig(
                restart_cooldown_seconds=_int(
                    guardian_raw, "restart_cooldown_seconds", 300
                ),
                max_restart_attempts=_int(guardian_raw, "max_restart_attempts", 3),
                restart_history_path=_str(
                    guardian_raw, "restart_history_path", "restart_history.json"
                ),
            ),
            incidents=IncidentConfig(
                history_path=_str(
                    incidents_raw, "history_path", "incident_history.json"
                )
            ),
            notifications=NotificationsConfig(
                email=EmailNotificationConfig(
                    **_notification_base(notification_email_raw),
                    host=_env_str(
                        "NOTIFY_EMAIL_HOST",
                        _str(notification_email_raw, "host", "smtp.gmail.com"),
                    ),
                    port=_env_int(
                        "NOTIFY_EMAIL_PORT", _int(notification_email_raw, "port", 587)
                    ),
                    starttls=_env_bool(
                        "NOTIFY_EMAIL_STARTTLS",
                        _bool(notification_email_raw, "starttls", True),
                    ),
                    username=_env_str(
                        "NOTIFY_EMAIL_USERNAME",
                        _str(notification_email_raw, "username", ""),
                    ),
                    password=_env_str(
                        "NOTIFY_EMAIL_PASSWORD",
                        _str(notification_email_raw, "password", ""),
                    ),
                    sender=_env_str(
                        "NOTIFY_EMAIL_SENDER",
                        _str(notification_email_raw, "sender", ""),
                    ),
                    recipient=_env_str(
                        "NOTIFY_EMAIL_RECIPIENT",
                        _str(notification_email_raw, "recipient", ""),
                    ),
                    subject=_env_str(
                        "NOTIFY_EMAIL_SUBJECT",
                        _str(notification_email_raw, "subject", "AegisNex Incident"),
                    ),
                ),
                slack=WebhookNotificationConfig(
                    **_notification_base(notification_slack_raw),
                    webhook_url=_env_str(
                        "SLACK_WEBHOOK_URL",
                        _str(notification_slack_raw, "webhook_url", ""),
                    ),
                ),
                discord=WebhookNotificationConfig(
                    **_notification_base(notification_discord_raw),
                    webhook_url=_env_str(
                        "DISCORD_WEBHOOK_URL",
                        _str(notification_discord_raw, "webhook_url", ""),
                    ),
                ),
            ),
            health_checks=HealthChecksConfig(
                docker=DockerHealthCheckConfig(
                    enabled=_bool(docker_health_raw, "enabled", True)
                ),
                http=HttpHealthCheckConfig(
                    enabled=_bool(http_health_raw, "enabled", False),
                    timeout_seconds=_int(http_health_raw, "timeout_seconds", 5),
                    expected_status=_int(http_health_raw, "expected_status", 200),
                    endpoints=_str_map(_section(http_health_raw, "endpoints")),
                ),
                tcp=TcpHealthCheckConfig(
                    enabled=_bool(tcp_health_raw, "enabled", False),
                    timeout_seconds=_int(tcp_health_raw, "timeout_seconds", 5),
                    targets=_str_map(_section(tcp_health_raw, "targets")),
                ),
            ),
            smtp=SMTPConfig(
                enabled=smtp_enabled,
                host=_env_str("SMTP_HOST", _str(smtp_raw, "host", "smtp.gmail.com")),
                port=_env_int("SMTP_PORT", _int(smtp_raw, "port", 587)),
                timeout_seconds=_env_int(
                    "SMTP_TIMEOUT_SECONDS",
                    _int(smtp_raw, "timeout_seconds", 10),
                ),
                starttls=_env_bool(
                    "SMTP_STARTTLS", _bool(smtp_raw, "starttls", True)
                ),
                username=smtp_username,
                password=smtp_password,
                recipient=smtp_recipient,
                subject=_env_str(
                    "SMTP_SUBJECT", _str(smtp_raw, "subject", "AegisNex Alert")
                ),
            ),
        )

    def validate(self) -> None:
        _require_positive(
            self.monitoring.cpu_interval_seconds, "monitoring.cpu_interval_seconds"
        )
        _require_positive_int(
            self.monitoring.watchdog_interval_seconds,
            "monitoring.watchdog_interval_seconds",
        )
        for name, value in (
            ("monitoring.thresholds.cpu_percent", self.monitoring.thresholds.cpu_percent),
            (
                "monitoring.thresholds.memory_percent",
                self.monitoring.thresholds.memory_percent,
            ),
            ("monitoring.thresholds.disk_percent", self.monitoring.thresholds.disk_percent),
        ):
            if value < 0 or value > 100:
                raise ConfigError(f"{name} must be between 0 and 100.")

        _require_positive_int(
            self.docker.client_timeout_seconds, "docker.client_timeout_seconds"
        )
        _require_positive_int(
            self.docker.restart_timeout_seconds, "docker.restart_timeout_seconds"
        )
        if self.guardian.restart_cooldown_seconds < 0:
            raise ConfigError("guardian.restart_cooldown_seconds cannot be negative.")
        _require_positive_int(
            self.guardian.max_restart_attempts, "guardian.max_restart_attempts"
        )
        if not self.guardian.restart_history_path.strip():
            raise ConfigError("guardian.restart_history_path cannot be empty.")
        if not self.incidents.history_path.strip():
            raise ConfigError("incidents.history_path cannot be empty.")
        self._validate_notifications()
        _require_positive_int(
            self.health_checks.http.timeout_seconds,
            "health_checks.http.timeout_seconds",
        )
        _require_positive_int(
            self.health_checks.tcp.timeout_seconds,
            "health_checks.tcp.timeout_seconds",
        )
        if (
            self.health_checks.http.expected_status < 100
            or self.health_checks.http.expected_status > 599
        ):
            raise ConfigError("health_checks.http.expected_status must be 100-599.")
        for name, endpoint in self.health_checks.http.endpoints.items():
            if not name.strip() or not endpoint.strip():
                raise ConfigError("health_checks.http.endpoints cannot contain empty values.")
        for name, target in self.health_checks.tcp.targets.items():
            if not name.strip() or not target.strip() or ":" not in target:
                raise ConfigError(
                    "health_checks.tcp.targets values must use host:port format."
                )
            try:
                int(target.rsplit(":", 1)[1])
            except ValueError as exc:
                raise ConfigError(
                    "health_checks.tcp.targets values must use numeric ports."
                ) from exc

        if not self.smtp.host.strip():
            raise ConfigError("smtp.host cannot be empty.")
        if self.smtp.port < 1 or self.smtp.port > 65535:
            raise ConfigError("smtp.port must be between 1 and 65535.")
        _require_positive_int(self.smtp.timeout_seconds, "smtp.timeout_seconds")
        if not self.smtp.subject.strip():
            raise ConfigError("smtp.subject cannot be empty.")
        if self.smtp.enabled:
            missing = [
                name
                for name, value in (
                    ("smtp.username", self.smtp.username),
                    ("smtp.password", self.smtp.password),
                    ("smtp.recipient", self.smtp.recipient),
                )
                if not value.strip()
            ]
            if missing:
                raise ConfigError(
                    "SMTP is enabled but required values are missing: "
                    + ", ".join(missing)
                )

    def _validate_notifications(self) -> None:
        for name, provider in (
            ("notifications.email", self.notifications.email),
            ("notifications.slack", self.notifications.slack),
            ("notifications.discord", self.notifications.discord),
        ):
            _require_positive_int(provider.retry_attempts, f"{name}.retry_attempts")
            if provider.retry_delay_seconds < 0:
                raise ConfigError(f"{name}.retry_delay_seconds cannot be negative.")
            _require_positive_int(provider.timeout_seconds, f"{name}.timeout_seconds")
            if not provider.message_template.strip():
                raise ConfigError(f"{name}.message_template cannot be empty.")
            if not provider.resolution_template.strip():
                raise ConfigError(f"{name}.resolution_template cannot be empty.")
        if self.notifications.email.enabled:
            missing = [
                field
                for field, value in (
                    ("host", self.notifications.email.host),
                    ("username", self.notifications.email.username),
                    ("password", self.notifications.email.password),
                    ("recipient", self.notifications.email.recipient),
                )
                if not str(value).strip()
            ]
            if missing:
                raise ConfigError(
                    "notifications.email enabled but missing: " + ", ".join(missing)
                )
            if self.notifications.email.port < 1 or self.notifications.email.port > 65535:
                raise ConfigError("notifications.email.port must be between 1 and 65535.")
        if self.notifications.slack.enabled and not self.notifications.slack.webhook_url.strip():
            raise ConfigError("notifications.slack.webhook_url cannot be empty when enabled.")
        if self.notifications.discord.enabled and not self.notifications.discord.webhook_url.strip():
            raise ConfigError("notifications.discord.webhook_url cannot be empty when enabled.")


def load_env_file(env_path: str | Path = ".env") -> None:
    path = Path(env_path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _parse_simple_yaml(content: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for line_number, line in enumerate(content.splitlines(), start=1):
        raw_line = line.split("#", 1)[0].rstrip()
        if not raw_line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 != 0:
            raise ConfigError(f"Invalid indentation at config line {line_number}.")
        stripped = raw_line.strip()
        if ":" not in stripped:
            raise ConfigError(f"Invalid config line {line_number}: missing ':'.")

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"Invalid config line {line_number}: empty key.")

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        raw_value = raw_value.strip()
        if not raw_value:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
            continue
        parent[key] = _parse_scalar(raw_value)

    return root


def _parse_scalar(value: str) -> Any:
    if value in {'""', "''"}:
        return ""
    if (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    ):
        return value[1:-1]

    normalized = value.lower()
    if normalized in {"true", "false"}:
        return normalized == "true"

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value


def _section(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"{key} must be a mapping.")
    return value


def _str_map(raw: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in raw.items()}


def _notification_base(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "enabled": _bool(raw, "enabled", False),
        "retry_attempts": _int(raw, "retry_attempts", 1),
        "retry_delay_seconds": _float(raw, "retry_delay_seconds", 0),
        "timeout_seconds": _int(raw, "timeout_seconds", 10),
        "message_template": _str(
            raw,
            "message_template",
            "[{severity}] {service_name}: {description} ({incident_id})",
        ),
        "resolution_template": _str(
            raw,
            "resolution_template",
            "[RESOLVED] {service_name}: {description} ({incident_id})",
        ),
    }


def _str(raw: Mapping[str, Any], key: str, default: str) -> str:
    value = raw.get(key, default)
    return str(value)


def _int(raw: Mapping[str, Any], key: str, default: int) -> int:
    value = raw.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{key} must be an integer.") from exc


def _float(raw: Mapping[str, Any], key: str, default: float) -> float:
    value = raw.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{key} must be a number.") from exc


def _bool(raw: Mapping[str, Any], key: str, default: bool) -> bool:
    return _parse_bool(raw.get(key, default), key)


def _env_str(key: str, default: str) -> str:
    return os.getenv(key, default)


def _env_first(keys: tuple[str, ...], default: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None:
            return value
    return default


def _env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer.") from exc


def _env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return _parse_bool(value, key)


def _parse_bool(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ConfigError(f"{key} must be a boolean.")


def _require_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero.")


def _require_positive_int(value: int, name: str) -> None:
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero.")
