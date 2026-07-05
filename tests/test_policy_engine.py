"""Tests for the Policy Engine module."""

from __future__ import annotations

from src.policy_engine import AppPolicyEngine, ActionVerdict


def test_policy_engine_safe_action() -> None:
    engine = AppPolicyEngine()
    result = engine.evaluate("restart_container")
    assert result.verdict == ActionVerdict.SAFE


def test_policy_engine_approval_required_action() -> None:
    engine = AppPolicyEngine()
    result = engine.evaluate("delete_container")
    assert result.verdict == ActionVerdict.APPROVAL_REQUIRED


def test_policy_engine_forbidden_action() -> None:
    engine = AppPolicyEngine()
    result = engine.evaluate("delete_database")
    assert result.verdict == ActionVerdict.FORBIDDEN


def test_policy_engine_unknown_action_default_safe() -> None:
    engine = AppPolicyEngine()
    result = engine.evaluate("list_containers")
    assert result.verdict in (ActionVerdict.SAFE, ActionVerdict.APPROVAL_REQUIRED)


def test_policy_engine_evaluate_returns_reason() -> None:
    engine = AppPolicyEngine()
    result = engine.evaluate("restart_container")
    assert len(result.reason) > 0
    assert result.to_dict()["verdict"] == "safe"


def test_policy_engine_forbidden_action_reason() -> None:
    engine = AppPolicyEngine()
    result = engine.evaluate("delete_database")
    assert "forbidden" in result.reason.lower()
    assert result.to_dict()["verdict"] == "forbidden"


def test_policy_engine_list_safe_actions() -> None:
    engine = AppPolicyEngine()
    safe = engine.get_safe_actions()
    assert "restart_container" in safe
    assert "retry_notification" in safe


def test_policy_engine_list_approval_actions() -> None:
    engine = AppPolicyEngine()
    approval = engine.get_approval_actions()
    assert "delete_container" in approval
    assert "stop_container" in approval


def test_policy_engine_list_forbidden_actions() -> None:
    engine = AppPolicyEngine()
    forbidden = engine.get_forbidden_actions()
    assert "delete_database" in forbidden
    assert "format_disk" in forbidden


def test_policy_engine_risk_score_in_result() -> None:
    engine = AppPolicyEngine()
    result = engine.evaluate("delete_database")
    assert result.risk_score > 0.5
    assert result.risk_level is not None


def test_policy_engine_to_dict() -> None:
    engine = AppPolicyEngine()
    result = engine.evaluate("restart_container")
    d = result.to_dict()
    assert isinstance(d, dict)
    assert d["action"] == "restart_container"
