"""Slack notification provider."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

from src.notifications.base import NotificationProvider


class SlackProvider(NotificationProvider):
    name = "slack"

    def __init__(self, webhook_url: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.webhook_url = webhook_url

    def _send(self, message: str) -> None:
        payload = json.dumps({"text": message}).encode("utf-8")
        request = Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds):
            return
