"""Tests for NotifierCompat adapter that bridges old Notifier interface to new NotificationProvider system."""

from __future__ import annotations

from src.notifications.base import NotificationProvider, NotificationResult
from src.notifications_compat import NotifierCompat


class FakeProvider(NotificationProvider):
    name = "fake"

    def __init__(self, enabled: bool = True, should_fail: bool = False) -> None:
        super().__init__(enabled=enabled)
        self._should_fail = should_fail
        self.sent_messages: list[str] = []

    def _send(self, message: str) -> None:
        self.sent_messages.append(message)
        if self._should_fail:
            raise RuntimeError("send failed")


def test_notifier_compat_disabled_providers() -> None:
    notifier = NotifierCompat([])
    result = notifier.send_email_alert("hello")
    assert result["status"] == "disabled"


def test_notifier_compat_sends_via_provider() -> None:
    provider = FakeProvider(enabled=True)
    notifier = NotifierCompat([provider])
    result = notifier.send_email_alert("test message")
    assert result["status"] == "ok"
    assert provider.sent_messages == ["test message"]


def test_notifier_compat_handles_provider_failure() -> None:
    provider = FakeProvider(enabled=True, should_fail=True)
    notifier = NotifierCompat([provider])
    result = notifier.send_email_alert("test message")
    assert result["status"] == "error"


def test_notifier_compat_multiple_providers() -> None:
    p1 = FakeProvider(enabled=True)
    p2 = FakeProvider(enabled=True)
    notifier = NotifierCompat([p1, p2])
    result = notifier.send_email_alert("broadcast")
    assert p1.sent_messages == ["broadcast"]
    assert p2.sent_messages == ["broadcast"]
    assert isinstance(result, dict)


def test_notifier_compat_send_method() -> None:
    p1 = FakeProvider(enabled=True)
    notifier = NotifierCompat([p1])
    results = notifier.send("hello", providers=["fake"])
    assert len(results) == 1
    assert results[0]["provider"] == "fake"


def test_notifier_compat_send_filters_providers() -> None:
    p1 = FakeProvider(enabled=True)
    p1.name = "email"
    p2 = FakeProvider(enabled=True)
    p2.name = "slack"
    notifier = NotifierCompat([p1, p2])
    results = notifier.send("hello", providers=["email"])
    assert len(results) == 1
    assert p1.sent_messages == ["hello"]
    assert p2.sent_messages == []
