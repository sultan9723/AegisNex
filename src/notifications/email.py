"""Email notification provider."""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import Optional

from src.notifications.base import NotificationProvider


class EmailProvider(NotificationProvider):
    name = "email"

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        recipient: str,
        sender: Optional[str] = None,
        subject: str = "AegisNex Incident",
        starttls: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.recipient = recipient
        self.sender = sender or username
        self.subject = subject
        self.starttls = starttls

    def _send(self, message: str) -> None:
        msg = MIMEText(message)
        msg["From"] = self.sender
        msg["To"] = self.recipient
        msg["Subject"] = self.subject
        with smtplib.SMTP(
            self.smtp_host,
            self.smtp_port,
            timeout=self.timeout_seconds,
        ) as server:
            if self.starttls:
                server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.sender, [self.recipient], msg.as_string())
