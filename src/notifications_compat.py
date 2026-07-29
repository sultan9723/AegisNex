"""Compatibility adapter bridging the old Notifier interface with the new NotificationProvider system."""

from __future__ import annotations

import logging
from typing import Any

from src.notifications.base import NotificationProvider

_logger = logging.getLogger(__name__)


class NotifierCompat:
    """Adapter that exposes the old Notifier.send_email_alert() interface
    backed by the new NotificationProvider list."""

    def __init__(self, providers: list[NotificationProvider] | None = None) -> None:
        self._providers = providers or []

    def send_email_alert(self, message: str, subject: str | None = None) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for provider in self._providers:
            try:
                result = provider._send_with_retries(message)
                results.append(
                    {
                        "status": result.status,
                        "provider": result.provider,
                        "attempts": result.attempts,
                        "message": result.message,
                    }
                )
            except Exception as exc:
                _logger.exception("NotifierCompat send failed for %s", provider.name)
                results.append(
                    {
                        "status": "error",
                        "provider": getattr(provider, "name", "unknown"),
                        "message": str(exc),
                    }
                )
        if not results:
            return {"status": "disabled", "message": "No notification providers configured"}
        return results[0] if len(results) == 1 else {"status": "ok", "results": results}

    def send_slack_alert(self, message: str, channel: str | None = None) -> dict[str, Any]:
        for provider in self._providers:
            if getattr(provider, "name", "") == "slack":
                result = provider._send_with_retries(message)
                return {"status": result.status, "provider": result.provider}
        return {"status": "disabled", "message": "Slack provider not configured"}

    def send_discord_alert(self, message: str, username: str | None = None) -> dict[str, Any]:
        for provider in self._providers:
            if getattr(provider, "name", "") == "discord":
                result = provider._send_with_retries(message)
                return {"status": result.status, "provider": result.provider}
        return {"status": "disabled", "message": "Discord provider not configured"}

    def send(
        self,
        message: str,
        providers: list[str] | None = None,
        subject: str | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for provider in self._providers:
            if providers and getattr(provider, "name", "") not in providers:
                continue
            result = provider._send_with_retries(message)
            results.append(
                {
                    "status": result.status,
                    "provider": result.provider,
                    "attempts": result.attempts,
                }
            )
        return results
