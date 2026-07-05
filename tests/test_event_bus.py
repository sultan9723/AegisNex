"""Tests for the Event Bus module."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.event_bus import EventType, EventBus, get_bus, reset_bus

pytestmark = pytest.mark.asyncio


async def _collector() -> List[Dict[str, Any]]:
    return []


async def test_event_bus_publish_and_subscribe() -> None:
    reset_bus()
    bus = get_bus()
    received: List[Any] = []

    async def handler(event: Any) -> None:
        received.append(event)

    bus.subscribe(EventType.CONTAINER_DOWN, handler)
    event = await bus.publish(EventType.CONTAINER_DOWN, {"name": "nginx"})

    assert len(received) == 1
    assert received[0].event_id == event.event_id
    assert received[0].event_type == EventType.CONTAINER_DOWN
    assert received[0].payload == {"name": "nginx"}
    assert received[0].source == "system"


async def test_event_bus_wildcard_subscriber() -> None:
    reset_bus()
    bus = get_bus()
    received: List[Any] = []

    async def wildcard(event: Any) -> None:
        received.append(event.event_type)

    bus.subscribe_all(wildcard)
    await bus.publish(EventType.HIGH_CPU, {"value": "95%"})
    await bus.publish(EventType.DISK_FULL, {"value": "98%"})

    assert len(received) == 2
    assert EventType.HIGH_CPU in received
    assert EventType.DISK_FULL in received


async def test_event_bus_unsubscribe() -> None:
    reset_bus()
    bus = get_bus()
    received: List[Any] = []

    async def handler(event: Any) -> None:
        received.append(event)

    bus.subscribe(EventType.CONTAINER_DOWN, handler)
    bus.unsubscribe(EventType.CONTAINER_DOWN, handler)
    await bus.publish(EventType.CONTAINER_DOWN, {"name": "test"})

    assert len(received) == 0


async def test_event_bus_error_isolation() -> None:
    reset_bus()
    bus = get_bus()
    received: List[Any] = []

    async def failing_handler(event: Any) -> None:
        raise ValueError("handler error")

    async def good_handler(event: Any) -> None:
        received.append(event)

    bus.subscribe(EventType.CONTAINER_DOWN, failing_handler)
    bus.subscribe(EventType.CONTAINER_DOWN, good_handler)
    await bus.publish(EventType.CONTAINER_DOWN, {"name": "test"})

    assert len(received) == 1


async def test_event_bus_correlation_id() -> None:
    reset_bus()
    bus = get_bus()
    received: List[Any] = []

    async def handler(event: Any) -> None:
        received.append(event)

    bus.subscribe(EventType.INCIDENT_CREATED, handler)
    await bus.publish(EventType.INCIDENT_CREATED, {"id": "inc-1"}, correlation_id="corr-123")

    assert received[0].correlation_id == "corr-123"


async def test_event_bus_multiple_subscribers_same_type() -> None:
    reset_bus()
    bus = get_bus()
    results: List[str] = []

    async def handler_a(event: Any) -> None:
        results.append("a")

    async def handler_b(event: Any) -> None:
        results.append("b")

    bus.subscribe(EventType.CONTAINER_DOWN, handler_a)
    bus.subscribe(EventType.CONTAINER_DOWN, handler_b)
    await bus.publish(EventType.CONTAINER_DOWN, {})

    assert len(results) == 2
    assert "a" in results
    assert "b" in results


async def test_event_bus_event_has_id() -> None:
    reset_bus()
    bus = get_bus()
    event = await bus.publish(EventType.CONTAINER_DOWN, {})

    assert event.event_id is not None
    assert len(event.event_id) > 0
    assert event.to_dict()["event_id"] == event.event_id
    assert event.to_dict()["event_type"] == "container_down"
