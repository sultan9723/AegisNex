import json
from pathlib import Path

from src.guardian import Guardian
from src.incidents import IncidentManager
from src.policy_engine import AppPolicyEngine


class SequenceHealthChecker:
    def __init__(self, reports: list[dict]):
        self.reports = list(reports)

    def run(self, params):
        if len(self.reports) == 1:
            return self.reports[0]
        return self.reports.pop(0)


class RecordingDockerScanner:
    include_all = True

    def __init__(self):
        self.ensure_calls: list[str] = []
        self.restart_calls: list[str] = []

    def ensure_running(self, name: str) -> dict:
        self.ensure_calls.append(name)
        return {"status": "ok", "container": name, "action": "restarted"}

    def restart_container(self, name: str) -> dict:
        self.restart_calls.append(name)
        return {"status": "ok", "container": name, "action": "restarted"}


class RecordingNotifier:
    def __init__(self):
        self.messages: list[str] = []

    def send_email_alert(self, message: str) -> dict:
        self.messages.append(message)
        return {"status": "ok", "recipient": "ops@example.com"}


def _report(container: dict) -> dict:
    return {"docker": {"containers": [container]}}


def _guardian(
    tmp_path: Path,
    health_checker: SequenceHealthChecker,
    docker_scanner: RecordingDockerScanner,
    notifier: RecordingNotifier,
    incident_manager: IncidentManager,
    max_restart_attempts: int = 3,
) -> Guardian:
    return Guardian(
        health_checker=health_checker,
        docker_scanner=docker_scanner,
        notifier=notifier,
        restart_cooldown_seconds=0,
        max_restart_attempts=max_restart_attempts,
        restart_history_path=tmp_path / "restart_history.json",
        incident_manager=incident_manager,
        policy_engine=AppPolicyEngine(),
    )


def test_guardian_remediation_loop_restarts_logs_notifies_and_resolves(
    tmp_path: Path,
) -> None:
    incidents = IncidentManager(tmp_path / "incident_history.json")
    docker = RecordingDockerScanner()
    notifier = RecordingNotifier()
    guardian = _guardian(
        tmp_path,
        SequenceHealthChecker(
            [
                _report({"name": "api", "status": "stopped"}),
                _report({"name": "api", "status": "running"}),
            ]
        ),
        docker,
        notifier,
        incidents,
    )

    first = guardian.run({})

    assert docker.ensure_calls == ["api"]
    assert first["actions"][0]["action"] == "restarted"
    assert notifier.messages
    assert guardian.restart_history["api"]["attempts"] == 1
    created = incidents.list_incidents()[0]
    assert created.service_name == "api"
    assert created.remediation_attempted is True
    assert created.remediation_successful is True

    second = guardian.run({})

    assert second["actions"] == []
    resolved = incidents.list_incidents()[0]
    assert resolved.status == "resolved"
    assert resolved.resolved_timestamp is not None


def test_guardian_remediation_loop_skips_after_max_restart_attempts(
    tmp_path: Path,
) -> None:
    incidents = IncidentManager(tmp_path / "incident_history.json")
    docker = RecordingDockerScanner()
    guardian = _guardian(
        tmp_path,
        SequenceHealthChecker([_report({"name": "api", "status": "stopped"})]),
        docker,
        RecordingNotifier(),
        incidents,
        max_restart_attempts=2,
    )

    first = guardian.run({})
    second = guardian.run({})
    third = guardian.run({})

    assert first["actions"][0]["action"] == "restarted"
    assert second["actions"][0]["action"] == "restarted"
    assert docker.ensure_calls == ["api", "api"]
    assert third["actions"][0]["status"] == "skipped"
    assert third["actions"][0]["reason"] == "max_restart_attempts"
    assert json.loads((tmp_path / "restart_history.json").read_text())["api"][
        "attempts"
    ] == 2


def test_guardian_remediation_loop_requires_approval_for_critical_container(
    tmp_path: Path,
) -> None:
    incidents = IncidentManager(tmp_path / "incident_history.json")
    docker = RecordingDockerScanner()
    guardian = _guardian(
        tmp_path,
        SequenceHealthChecker(
            [
                _report(
                    {
                        "name": "payments",
                        "status": "stopped",
                        "labels": {"criticality": "critical"},
                    }
                )
            ]
        ),
        docker,
        RecordingNotifier(),
        incidents,
    )

    result = guardian.run({})

    assert docker.ensure_calls == []
    assert result["actions"][0]["status"] == "skipped"
    assert result["actions"][0]["reason"] == "approval_required"
    assert result["actions"][0]["policy"]["verdict"] == "approval_required"
