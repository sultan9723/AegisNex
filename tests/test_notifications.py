import json
from pathlib import Path

import pytest

from src.config import Config, ConfigError
from src.incidents import IncidentManager
from src.notifications.base import NotificationProvider
from src.notifications.discord import DiscordProvider
from src.notifications.email import EmailProvider
from src.notifications.factory import build_notification_providers
from src.notifications.slack import SlackProvider


class FakeProvider(NotificationProvider):
    name = "fake"

    def __init__(self, failures=0, **kwargs):
        super().__init__(**kwargs)
        self.failures = failures
        self.sent_messages = []

    def _send(self, message: str) -> None:
        self.sent_messages.append(message)
        if len(self.sent_messages) <= self.failures:
            raise RuntimeError("send failed")


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_calls = 0
        self.login_calls = []
        self.sendmail_calls = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.starttls_calls += 1

    def login(self, username, password):
        self.login_calls.append((username, password))

    def sendmail(self, sender, recipients, message):
        self.sendmail_calls.append((sender, recipients, message))


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def create_incident(tmp_path: Path):
    manager = IncidentManager(tmp_path / "incident_history.json")
    return manager.create_incident(
        severity="high",
        service_name="api",
        incident_type="health_check_failed",
        description="api failed",
    )


def test_notification_provider_formats_severity_and_templates(tmp_path: Path) -> None:
    incident = create_incident(tmp_path)
    provider = FakeProvider(
        enabled=True,
        message_template="{severity}:{service_name}:{description}",
        resolution_template="done:{service_name}:{incident_id}",
    )

    assert provider.render_incident_message(incident) == "HIGH:api:api failed"
    assert provider.render_resolution_message(incident).startswith("done:api:")


def test_notification_provider_retries_until_success(tmp_path: Path) -> None:
    incident = create_incident(tmp_path)
    provider = FakeProvider(enabled=True, failures=1, retry_attempts=2)

    result = provider.notify_incident_created(incident)

    assert result.status == "ok"
    assert result.attempts == 2
    assert len(provider.sent_messages) == 2


def test_notification_provider_returns_error_after_retry_exhaustion(tmp_path: Path) -> None:
    incident = create_incident(tmp_path)
    provider = FakeProvider(enabled=True, failures=3, retry_attempts=2)

    result = provider.notify_incident_created(incident)

    assert result.status == "error"
    assert result.attempts == 2
    assert result.message == "send failed"


def test_disabled_provider_does_not_send(tmp_path: Path) -> None:
    incident = create_incident(tmp_path)
    provider = FakeProvider(enabled=False)

    result = provider.notify_incident_created(incident)

    assert result.status == "disabled"
    assert result.attempts == 0
    assert provider.sent_messages == []


def test_email_provider_sends_smtp_message(monkeypatch, tmp_path: Path) -> None:
    FakeSMTP.instances = []
    monkeypatch.setattr("src.notifications.email.smtplib.SMTP", FakeSMTP)
    incident = create_incident(tmp_path)
    provider = EmailProvider(
        enabled=True,
        smtp_host="smtp.example.com",
        smtp_port=2525,
        timeout_seconds=4,
        username="sender@example.com",
        password="secret",
        sender="aegis@example.com",
        recipient="ops@example.com",
        subject="Incident",
        starttls=True,
    )

    result = provider.notify_incident_created(incident)

    smtp = FakeSMTP.instances[0]
    assert result.status == "ok"
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.example.com", 2525, 4)
    assert smtp.starttls_calls == 1
    assert smtp.login_calls == [("sender@example.com", "secret")]
    assert smtp.sendmail_calls[0][0] == "aegis@example.com"
    assert smtp.sendmail_calls[0][1] == ["ops@example.com"]
    assert "api failed" in smtp.sendmail_calls[0][2]


def test_slack_provider_posts_webhook_payload(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, json.loads(request.data.decode("utf-8")), timeout))
        return FakeResponse()

    monkeypatch.setattr("src.notifications.slack.urlopen", fake_urlopen)
    incident = create_incident(tmp_path)
    provider = SlackProvider(
        enabled=True,
        webhook_url="https://hooks.slack.test/example",
        timeout_seconds=3,
    )

    result = provider.notify_incident_created(incident)

    assert result.status == "ok"
    assert calls == [
        (
            "https://hooks.slack.test/example",
            {"text": "[HIGH] api: api failed (" + incident.incident_id + ")"},
            3,
        )
    ]


def test_discord_provider_posts_webhook_payload(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, json.loads(request.data.decode("utf-8")), timeout))
        return FakeResponse()

    monkeypatch.setattr("src.notifications.discord.urlopen", fake_urlopen)
    incident = create_incident(tmp_path)
    provider = DiscordProvider(
        enabled=True,
        webhook_url="https://discord.test/webhook",
        timeout_seconds=3,
    )

    result = provider.notify_incident_created(incident)

    assert result.status == "ok"
    assert calls[0][0] == "https://discord.test/webhook"
    assert calls[0][1]["content"].startswith("[HIGH] api: api failed")
    assert calls[0][2] == 3


def test_incident_manager_notifies_on_create_and_resolve(tmp_path: Path) -> None:
    provider = FakeProvider(enabled=True)
    manager = IncidentManager(
        tmp_path / "incident_history.json",
        notification_providers=[provider],
    )

    incident = manager.create_incident("high", "api", "health_check_failed", "api failed")
    manager.resolve_incident(incident.incident_id)

    assert len(provider.sent_messages) == 2
    assert provider.sent_messages[0].startswith("[HIGH] api")
    assert provider.sent_messages[1].startswith("[RESOLVED] api")


def test_incident_manager_does_not_notify_when_reusing_active_incident(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(enabled=True)
    manager = IncidentManager(
        tmp_path / "incident_history.json",
        notification_providers=[provider],
    )

    manager.create_incident("high", "api", "health_check_failed", "first")
    manager.create_incident("critical", "api", "health_check_failed", "second")

    assert len(provider.sent_messages) == 1


def test_build_notification_providers_from_config() -> None:
    config = Config.from_mapping(
        {
            "notifications": {
                "email": {
                    "enabled": True,
                    "host": "smtp.example.com",
                    "username": "sender",
                    "password": "secret",
                    "recipient": "ops@example.com",
                },
                "slack": {
                    "enabled": True,
                    "webhook_url": "https://hooks.slack.test/example",
                },
                "discord": {
                    "enabled": True,
                    "webhook_url": "https://discord.test/webhook",
                },
            }
        }
    )

    providers = build_notification_providers(config)

    assert [type(provider) for provider in providers] == [
        EmailProvider,
        SlackProvider,
        DiscordProvider,
    ]
    assert all(provider.enabled for provider in providers)


def test_config_rejects_enabled_slack_without_webhook() -> None:
    with pytest.raises(ConfigError):
        Config.from_mapping({"notifications": {"slack": {"enabled": True}}}).validate()
