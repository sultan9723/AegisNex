"""Centralized typed event bus for AegisNex autonomous operations.

Every infrastructure event (container down, high CPU, target down, etc.)
is published here. Subscribers include the incident pipeline, self-healing
engine, WebSocket broadcaster, and execution history recorder.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

_logger = logging.getLogger(__name__)


class EventType(str, Enum):
    CONTAINER_DOWN = "container_down"
    CONTAINER_STOPPED = "container_stopped"
    CONTAINER_RESTARTED = "container_restarted"
    CONTAINER_HEALTHY = "container_healthy"
    HIGH_CPU = "high_cpu"
    MEMORY_PRESSURE = "memory_pressure"
    DISK_FULL = "disk_full"
    TARGET_DOWN = "target_down"
    TARGET_RECOVERED = "target_recovered"
    SSL_EXPIRING = "ssl_expiring"
    INCIDENT_CREATED = "incident_created"
    INCIDENT_RESOLVED = "incident_resolved"
    INCIDENT_ESCALATED = "incident_escalated"
    REMEDIATION_STARTED = "remediation_started"
    REMEDIATION_COMPLETED = "remediation_completed"
    REMEDIATION_FAILED = "remediation_failed"
    NOTIFICATION_FAILED = "notification_failed"
    NOTIFICATION_SENT = "notification_sent"
    REPORT_GENERATED = "report_generated"
    POLICY_VIOLATION = "policy_violation"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESPONDED = "approval_responded"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    AUTONOMOUS_ACTION = "autonomous_action"
    KNOWLEDGE_UPDATED = "knowledge_updated"


@dataclass
class Event:
    event_id: str
    event_type: EventType
    timestamp: str
    source: str
    payload: dict[str, Any]
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "source": self.source,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
        }


EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """In-process pub/sub event bus with async subscribers."""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._wildcard_subscribers: list[EventHandler] = []

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        self._wildcard_subscribers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        source: str = "system",
        correlation_id: str | None = None,
    ) -> Event:
        event = Event(
            event_id=str(uuid4()),
            event_type=event_type,
            timestamp=_utc_now(),
            source=source,
            payload=payload,
            correlation_id=correlation_id,
        )
        _logger.debug("Publishing event: %s [%s]", event_type.value, event.event_id)
        tasks = []
        for handler in self._wildcard_subscribers:
            tasks.append(self._safe_call(handler, event))
        for handler in self._subscribers.get(event_type, []):
            tasks.append(self._safe_call(handler, event))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return event

    async def _safe_call(self, handler: EventHandler, event: Event) -> None:
        try:
            await handler(event)
        except Exception:
            _logger.exception(
                "Event handler %s failed for %s",
                getattr(handler, "__name__", "?"),
                event.event_type.value,
            )


_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_bus() -> None:
    global _bus
    _bus = None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
