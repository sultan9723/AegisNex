"""Multi-provider notification dispatcher for AegisNex.

Supports SMTP email, Slack webhook, Discord webhook, and generic webhook.
"""

from __future__ import annotations

import json
import logging
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.failsafe import failsafe


class Notifier:
    def __init__(
        self,
        enabled: bool = False,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
        smtp_timeout_seconds: int = 10,
        starttls: bool = True,
        email_user: str = "",
        email_pass: str = "",
        email_to: str = "",
        subject: str = "AegisNex Alert",
        slack_webhook_url: str = "",
        discord_webhook_url: str = "",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.enabled = enabled
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_timeout_seconds = smtp_timeout_seconds
        self.starttls = starttls
        self.email_user = email_user
        self.email_pass = email_pass
        self.email_to = email_to
        self.subject = subject
        self.slack_webhook_url = slack_webhook_url
        self.discord_webhook_url = discord_webhook_url
        self.logger = logger or logging.getLogger("agentx.notifier")

    @failsafe(fallback={"status": "error", "message": "Email sending failed"})
    def send_email_alert(self, message: str, subject: Optional[str] = None) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "message": "Email alerts disabled"}
        if not self.email_user or not self.email_pass or not self.email_to:
            return {"status": "error", "message": "Email notifier is enabled but credentials are missing"}
        msg = MIMEText(message)
        msg["From"] = self.email_user
        msg["To"] = self.email_to
        msg["Subject"] = subject or self.subject
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.smtp_timeout_seconds) as server:
            if self.starttls:
                server.starttls()
            server.login(self.email_user, self.email_pass)
            server.sendmail(self.email_user, [self.email_to], msg.as_string())
        return {"status": "ok", "recipient": self.email_to, "provider": "smtp"}

    @failsafe(fallback={"status": "error", "message": "Slack webhook failed"})
    def send_slack_alert(self, message: str, channel: str | None = None) -> Dict[str, Any]:
        if not self.slack_webhook_url:
            return {"status": "disabled", "message": "Slack webhook URL not configured"}
        payload = {"text": message}
        if channel:
            payload["channel"] = channel
        data = json.dumps(payload).encode("utf-8")
        req = Request(self.slack_webhook_url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=self.smtp_timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
        return {"status": "ok", "provider": "slack", "response": body}

    @failsafe(fallback={"status": "error", "message": "Discord webhook failed"})
    def send_discord_alert(self, message: str, username: str | None = None) -> Dict[str, Any]:
        if not self.discord_webhook_url:
            return {"status": "disabled", "message": "Discord webhook URL not configured"}
        payload: Dict[str, Any] = {"content": message}
        if username:
            payload["username"] = username
        data = json.dumps(payload).encode("utf-8")
        req = Request(self.discord_webhook_url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=self.smtp_timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
        return {"status": "ok", "provider": "discord", "response": body}

    @failsafe(fallback={"status": "error", "message": "Webhook failed"})
    def send_webhook(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=self.smtp_timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
        return {"status": "ok", "provider": "webhook", "response": body}

    def send(
        self,
        message: str,
        providers: list[str] | None = None,
        subject: str | None = None,
    ) -> list[Dict[str, Any]]:
        """Dispatch a message to all configured (or specified) providers."""
        results: list[Dict[str, Any]] = []
        if providers is None:
            providers = ["smtp", "slack", "discord"]
        for provider in providers:
            if provider == "smtp":
                results.append(self.send_email_alert(message, subject=subject))
            elif provider == "slack":
                results.append(self.send_slack_alert(message))
            elif provider == "discord":
                results.append(self.send_discord_alert(message))
        return results
