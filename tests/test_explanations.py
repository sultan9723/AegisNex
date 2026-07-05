"""Tests for the AI Explanation Generator."""

from __future__ import annotations

from src.explanations import ExplanationEngine


def test_explain_restart() -> None:
    engine = ExplanationEngine()
    explanation = engine.explain_restart(
        service_name="nginx",
        reason="container_crashed",
        health_data={"health_checks": [{"name": "http_check", "healthy": False, "message": "Connection refused"}]},
    )
    assert explanation.action == "restart_container"
    assert "unhealthy" in explanation.why.lower()
    assert len(explanation.evidence) > 0
    assert explanation.confidence > 0
    assert len(explanation.alternatives) > 0
    assert explanation.risk_level == "low"


def test_explain_notification_retry() -> None:
    engine = ExplanationEngine()
    explanation = engine.explain_notification_retry("slack", "timeout", attempt=2)
    assert explanation.action == "retry_notification"
    assert "slack" in explanation.why
    assert explanation.confidence == 0.7
    assert explanation.risk_level == "none"


def test_explain_health_check_rerun() -> None:
    engine = ExplanationEngine()
    explanation = engine.explain_health_check_rerun("api-server", "http")
    assert explanation.action == "re_run_health_check"
    assert "api-server" in explanation.why
    assert explanation.confidence == 0.9


def test_explain_monitoring_job_restart() -> None:
    engine = ExplanationEngine()
    explanation = engine.explain_monitoring_job_restart("cpu_monitor", "process crashed")
    assert explanation.action == "restart_monitoring_job"
    assert "cpu_monitor" in explanation.why
    assert explanation.confidence == 0.8


def test_explain_verification() -> None:
    engine = ExplanationEngine()
    explanation = engine.explain_verification("restart_container", True, "Container is healthy")
    assert explanation.action == "verify_restart_container"
    assert explanation.confidence == 0.95


def test_explain_remediation() -> None:
    engine = ExplanationEngine()
    explanation = engine.explain_remediation(
        action="restart_container",
        incident_type="container_down",
        service_name="redis",
        evidence=["Container unhealthy", "Health check failed"],
        confidence=0.9,
        alternatives=["manual_inspection"],
        risk_level="low",
    )
    assert explanation.action == "restart_container"
    assert "redis" in explanation.why
    assert "container_down" in explanation.why
    assert len(explanation.evidence) == 2
    assert explanation.confidence == 0.9
    assert explanation.risk_level == "low"


def test_explanation_to_dict() -> None:
    engine = ExplanationEngine()
    explanation = engine.explain_restart("test", "reason", {})
    d = explanation.to_dict()
    assert isinstance(d, dict)
    assert d["action"] == "restart_container"
    assert "why" in d
    assert "evidence" in d
    assert "confidence" in d
    assert "alternatives" in d
