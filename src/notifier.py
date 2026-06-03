"""Email notifier for Guardian alerts."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

EMAIL_USER_ENV = "EMAIL_USER"
EMAIL_PASS_ENV = "EMAIL_PASS"
EMAIL_TO_ENV = "EMAIL_TO"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


class Notifier:
    def __init__(
        self,
        email_user: Optional[str] = None,
        email_pass: Optional[str] = None,
        email_to: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.email_user = email_user or os.getenv(EMAIL_USER_ENV, "")
        self.email_pass = email_pass or os.getenv(EMAIL_PASS_ENV, "")
        self.email_to = email_to or os.getenv(EMAIL_TO_ENV, "")
        self.logger = logger or logging.getLogger("agentx.notifier")

    def send_email_alert(self, message: str, subject: str = "AgentX Alert") -> Dict[str, Any]:
        if not self.email_user or not self.email_pass or not self.email_to:
            return {"status": "disabled", "message": "Email credentials not configured"}

        msg = MIMEText(message)
        msg["From"] = self.email_user
        msg["To"] = self.email_to
        msg["Subject"] = subject

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(self.email_user, self.email_pass)
                server.sendmail(self.email_user, [self.email_to], msg.as_string())
            return {"status": "ok", "recipient": self.email_to}
        except Exception as exc:
            self.logger.exception("Failed to send email alert: %s", exc)
            return {"status": "error", "message": "Failed to send email alert"}
