"""Email notifier for Guardian alerts."""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict, Optional


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
        self.logger = logger or logging.getLogger("agentx.notifier")

    def send_email_alert(self, message: str, subject: Optional[str] = None) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "message": "Email alerts disabled"}

        msg = MIMEText(message)
        msg["From"] = self.email_user
        msg["To"] = self.email_to
        msg["Subject"] = subject or self.subject

        try:
            with smtplib.SMTP(
                self.smtp_host,
                self.smtp_port,
                timeout=self.smtp_timeout_seconds,
            ) as server:
                if self.starttls:
                    server.starttls()
                server.login(self.email_user, self.email_pass)
                server.sendmail(self.email_user, [self.email_to], msg.as_string())
            return {"status": "ok", "recipient": self.email_to}
        except Exception as exc:
            self.logger.exception("Failed to send email alert: %s", exc)
            return {"status": "error", "message": "Failed to send email alert"}
