"""Tests for the Self-Healing Engine."""

from __future__ import annotations

import pytest

from src.event_bus import EventType, reset_bus
from src.healing import SelfHealingEngine

pytestmark = pytest.mark.asyncio


async def test_healing_engine_handles_container_down() -> None:
    reset_bus()
    engine = SelfHealingEngine()

    class FakeDocker:
        def restart_container(self, name: str) -> dict:
            return {"status": "ok", "action": "restarted", "container": name}

    engine._docker = FakeDocker()
    result = await engine.handle_event(EventType.CONTAINER_DOWN, {"name": "nginx"})

    assert result is not None
    assert result.action == "restart_container"
    assert result.target == "nginx"
    assert result.status == "completed"


async def test_healing_engine_skips_when_policy_blocks() -> None:
    reset_bus()

    class DenyPolicy:
        def evaluate(self, action: str, context: dict = None) -> object:
            from src.policy_engine import PolicyEvaluation, ActionVerdict
            return PolicyEvaluation(action=action, verdict=ActionVerdict.FORBIDDEN, reason="blocked")

    engine = SelfHealingEngine(policy_engine=DenyPolicy())  # type: ignore
    result = await engine.handle_event(EventType.CONTAINER_DOWN, {"name": "nginx"})

    assert result is not None
    assert result.status == "skipped"
    assert result.error is not None


async def test_healing_engine_retry_notification() -> None:
    reset_bus()
    engine = SelfHealingEngine()

    class FakeNotifier:
        def send_email_alert(self, message: str) -> dict:
            return {"status": "ok"}

        def send_slack_alert(self, message: str) -> dict:
            return {"status": "ok"}

        def send_discord_alert(self, message: str) -> dict:
            return {"status": "ok"}

    engine._notifier = FakeNotifier()
    result = await engine.handle_event(EventType.NOTIFICATION_FAILED, {"provider": "smtp", "message": "test", "error": "timeout", "attempt": 1})

    assert result is not None
    assert result.action == "retry_notification"
    assert result.target == "smtp"


async def test_healing_engine_rerun_health_check() -> None:
    reset_bus()
    engine = SelfHealingEngine()
    result = await engine.handle_event(EventType.TARGET_DOWN, {"name": "api-server", "target_type": "http"})

    assert result is not None
    assert result.action == "re_run_health_check"
    assert result.target == "api-server"


async def test_healing_engine_history() -> None:
    reset_bus()
    engine = SelfHealingEngine()

    class FakeDocker:
        def restart_container(self, name: str) -> dict:
            return {"status": "ok", "action": "restarted"}

    engine._docker = FakeDocker()
    await engine.handle_event(EventType.CONTAINER_DOWN, {"name": "web"})
    await engine.handle_event(EventType.TARGET_DOWN, {"name": "db", "target_type": "tcp"})

    assert len(engine.history) == 2


async def test_healing_engine_explanation_in_result() -> None:
    reset_bus()
    engine = SelfHealingEngine()

    class FakeDocker:
        def restart_container(self, name: str) -> dict:
            return {"status": "ok"}

    engine._docker = FakeDocker()
    result = await engine.handle_event(EventType.CONTAINER_DOWN, {"name": "redis"})

    assert result is not None
    assert result.explanation is not None
    assert result.explanation.action == "restart_container"
    assert len(result.explanation.evidence) > 0


async def test_healing_engine_unknown_event_returns_none() -> None:
    reset_bus()
    engine = SelfHealingEngine()
    result = await engine.handle_event(EventType.REPORT_GENERATED, {})
    assert result is None
