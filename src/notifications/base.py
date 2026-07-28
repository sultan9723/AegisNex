"""Base notification provider primitives."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NotificationResult:
    provider: str
    status: str
    attempts: int
    message: str = ""


class NotificationProvider(ABC):
    name = "base"

    def __init__(
        self,
        enabled: bool = False,
        timeout_seconds: int = 10,
        retry_attempts: int = 1,
        retry_delay_seconds: float = 0,
        message_template: str | None = None,
        resolution_template: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = max(1, retry_attempts)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self.message_template = message_template or (
            "[{severity}] {service_name}: {description} ({incident_id})"
        )
        self.resolution_template = resolution_template or (
            "[RESOLVED] {service_name}: {description} ({incident_id})"
        )
        self.logger = logger or logging.getLogger(f"agentx.notifications.{self.name}")

    def notify_incident_created(self, incident: Any) -> NotificationResult:
        return self._send_with_retries(self.render_incident_message(incident))

    def notify_incident_resolved(self, incident: Any) -> NotificationResult:
        return self._send_with_retries(self.render_resolution_message(incident))

    def render_incident_message(self, incident: Any) -> str:
        return self._render_template(self.message_template, incident)

    def render_resolution_message(self, incident: Any) -> str:
        return self._render_template(self.resolution_template, incident)

    def _send_with_retries(self, message: str) -> NotificationResult:
        if not self.enabled:
            return NotificationResult(
                provider=self.name,
                status="disabled",
                attempts=0,
                message="Provider disabled",
            )

        last_error = ""
        for attempt in range(1, self.retry_attempts + 1):
            try:
                self._send(message)
                return NotificationResult(
                    provider=self.name,
                    status="ok",
                    attempts=attempt,
                )
            except Exception as exc:
                last_error = str(exc)
                self.logger.exception("Notification send failed: %s", self.name)
                if attempt < self.retry_attempts and self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds)
        return NotificationResult(
            provider=self.name,
            status="error",
            attempts=self.retry_attempts,
            message=last_error,
        )

    @abstractmethod
    def _send(self, message: str) -> None:
        """Send a rendered notification message."""

    def _render_template(self, template: str, incident: Any) -> str:
        values = self._incident_values(incident)
        values["severity"] = self.format_severity(str(values.get("severity", "")))
        return template.format(**values)

    @staticmethod
    def format_severity(severity: str) -> str:
        normalized = severity.strip().upper()
        if normalized == "CRITICAL":
            return "CRITICAL"
        if normalized == "HIGH":
            return "HIGH"
        if normalized == "MEDIUM":
            return "MEDIUM"
        if normalized == "LOW":
            return "LOW"
        return normalized or "UNKNOWN"

    @staticmethod
    def _incident_values(incident: Any) -> dict[str, Any]:
        if hasattr(incident, "to_dict"):
            values = incident.to_dict()
        elif isinstance(incident, Mapping):
            values = dict(incident)
        else:
            values = {}
        values.setdefault("incident_id", "")
        values.setdefault("severity", "")
        values.setdefault("service_name", "")
        values.setdefault("incident_type", "")
        values.setdefault("description", "")
        values.setdefault("status", "")
        values.setdefault("timestamp", "")
        values.setdefault("resolved_timestamp", "")
        return values
