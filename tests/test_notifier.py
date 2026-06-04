from src.notifier import Notifier


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


class FailingSMTP(FakeSMTP):
    def login(self, username, password):
        raise RuntimeError("smtp login failed")


def test_send_email_alert_disabled() -> None:
    notifier = Notifier(enabled=False)

    assert notifier.send_email_alert("message") == {
        "status": "disabled",
        "message": "Email alerts disabled",
    }


def test_send_email_alert_success(monkeypatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setattr("src.notifier.smtplib.SMTP", FakeSMTP)
    notifier = Notifier(
        enabled=True,
        smtp_host="smtp.example.com",
        smtp_port=2525,
        smtp_timeout_seconds=3,
        starttls=True,
        email_user="sender@example.com",
        email_pass="secret",
        email_to="ops@example.com",
        subject="Default Subject",
    )

    result = notifier.send_email_alert("hello", subject="Override Subject")

    smtp = FakeSMTP.instances[0]
    assert result == {"status": "ok", "recipient": "ops@example.com"}
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.example.com", 2525, 3)
    assert smtp.starttls_calls == 1
    assert smtp.login_calls == [("sender@example.com", "secret")]
    assert smtp.sendmail_calls[0][0] == "sender@example.com"
    assert smtp.sendmail_calls[0][1] == ["ops@example.com"]
    assert "Override Subject" in smtp.sendmail_calls[0][2]


def test_send_email_alert_can_skip_starttls(monkeypatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setattr("src.notifier.smtplib.SMTP", FakeSMTP)
    notifier = Notifier(
        enabled=True,
        starttls=False,
        email_user="sender@example.com",
        email_pass="secret",
        email_to="ops@example.com",
    )

    notifier.send_email_alert("hello")

    assert FakeSMTP.instances[0].starttls_calls == 0


def test_send_email_alert_returns_error_on_smtp_failure(monkeypatch) -> None:
    monkeypatch.setattr("src.notifier.smtplib.SMTP", FailingSMTP)
    notifier = Notifier(
        enabled=True,
        email_user="sender@example.com",
        email_pass="secret",
        email_to="ops@example.com",
    )

    assert notifier.send_email_alert("hello") == {
        "status": "error",
        "message": "Failed to send email alert",
    }
