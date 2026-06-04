import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from src.guardian import Guardian
from src.incidents import IncidentManager


class FakeHealthChecker:
    def __init__(self, report):
        self.report = report
        self.calls = []

    def run(self, params):
        self.calls.append(params)
        return self.report


class FakeDockerScanner:
    include_all = True

    def __init__(self, actions=None):
        self.actions = actions or {}
        self.calls = []
        self.restart_calls = []

    def ensure_running(self, name):
        self.calls.append(name)
        return self.actions.get(
            name,
            {"status": "ok", "container": name, "action": "restarted"},
        )

    def restart_container(self, name):
        self.restart_calls.append(name)
        return self.actions.get(
            name,
            {"status": "ok", "container": name, "action": "restarted"},
        )


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send_email_alert(self, message):
        self.messages.append(message)
        return {"status": "ok", "recipient": "ops@example.com"}


class FakeHealthCheck:
    name = "fake"

    def __init__(self, healthy=True, status="ok"):
        self.healthy = healthy
        self.status = status
        self.calls = []

    def check(self, container):
        from src.health_checks import HealthCheckResult

        self.calls.append(container)
        return HealthCheckResult(
            name=self.name,
            status=self.status,
            healthy=self.healthy,
            message="" if self.healthy else "failed",
        )


def test_guardian_restarts_stopped_container_and_sends_alert(tmp_path: Path) -> None:
    health_report = {
        "docker": {
            "containers": [
                {"name": "api", "status": "stopped"},
                {"name": "worker", "status": "running"},
                {"status": "stopped"},
            ]
        }
    }
    docker_scanner = FakeDockerScanner()
    notifier = FakeNotifier()
    guardian = Guardian(
        health_checker=FakeHealthChecker(health_report),
        docker_scanner=docker_scanner,
        notifier=notifier,
        restart_cooldown_seconds=300,
        restart_history_path=tmp_path / "restart_history.json",
    )

    result = guardian.run({})

    assert docker_scanner.calls == ["api"]
    assert result["actions"] == [
        {
            "status": "ok",
            "container": "api",
            "action": "restarted",
            "alert": {"status": "ok", "recipient": "ops@example.com"},
        }
    ]
    assert "Container: api" in notifier.messages[0]
    assert guardian.restart_history["api"]["attempts"] == 1


def test_guardian_skips_container_inside_restart_cooldown(tmp_path: Path) -> None:
    health_report = {"docker": {"containers": [{"name": "api", "status": "error"}]}}
    docker_scanner = FakeDockerScanner()
    guardian = Guardian(
        health_checker=FakeHealthChecker(health_report),
        docker_scanner=docker_scanner,
        notifier=FakeNotifier(),
        restart_cooldown_seconds=300,
        restart_history_path=tmp_path / "restart_history.json",
    )
    guardian.restart_history["api"] = {
        "attempts": 1,
        "last_restart": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    result = guardian.run({})

    assert docker_scanner.calls == []
    assert result["actions"] == [
        {"status": "skipped", "container": "api", "reason": "restart_cooldown"}
    ]


def test_guardian_allows_restart_after_cooldown_elapsed(tmp_path: Path) -> None:
    health_report = {"docker": {"containers": [{"name": "api", "status": "stopped"}]}}
    docker_scanner = FakeDockerScanner()
    guardian = Guardian(
        health_checker=FakeHealthChecker(health_report),
        docker_scanner=docker_scanner,
        notifier=FakeNotifier(),
        restart_cooldown_seconds=300,
        restart_history_path=tmp_path / "restart_history.json",
    )
    guardian.restart_history["api"] = {
        "attempts": 1,
        "last_restart": (
            datetime.now(timezone.utc) - timedelta(seconds=301)
        ).isoformat().replace("+00:00", "Z"),
    }

    result = guardian.run({})

    assert docker_scanner.calls == ["api"]
    assert result["actions"][0]["action"] == "restarted"
    assert guardian.restart_history["api"]["attempts"] == 2


def test_guardian_handles_missing_or_invalid_docker_report(tmp_path: Path) -> None:
    guardian = Guardian(
        health_checker=FakeHealthChecker({"docker": "unavailable"}),
        docker_scanner=SimpleNamespace(include_all=True),
        notifier=FakeNotifier(),
        restart_history_path=tmp_path / "restart_history.json",
    )

    result = guardian.run({})

    assert result["actions"] == []


def test_guardian_persists_restart_history_across_instances(tmp_path: Path) -> None:
    history_path = tmp_path / "restart_history.json"
    health_report = {"docker": {"containers": [{"name": "api", "status": "stopped"}]}}

    first = Guardian(
        health_checker=FakeHealthChecker(health_report),
        docker_scanner=FakeDockerScanner(),
        notifier=FakeNotifier(),
        restart_cooldown_seconds=0,
        restart_history_path=history_path,
    )
    first.run({})

    second = Guardian(
        health_checker=FakeHealthChecker({"docker": {"containers": []}}),
        docker_scanner=FakeDockerScanner(),
        notifier=FakeNotifier(),
        restart_history_path=history_path,
    )

    assert second.restart_history["api"]["attempts"] == 1
    assert json.loads(history_path.read_text(encoding="utf-8"))["api"]["attempts"] == 1


def test_guardian_blocks_restart_after_max_attempts(tmp_path: Path) -> None:
    history_path = tmp_path / "restart_history.json"
    history_path.write_text(
        json.dumps(
            {
                "api": {
                    "attempts": 2,
                    "last_restart": (
                        datetime.now(timezone.utc) - timedelta(hours=1)
                    ).isoformat().replace("+00:00", "Z"),
                }
            }
        ),
        encoding="utf-8",
    )
    docker_scanner = FakeDockerScanner()
    guardian = Guardian(
        health_checker=FakeHealthChecker(
            {"docker": {"containers": [{"name": "api", "status": "stopped"}]}}
        ),
        docker_scanner=docker_scanner,
        notifier=FakeNotifier(),
        restart_cooldown_seconds=0,
        max_restart_attempts=2,
        restart_history_path=history_path,
    )

    result = guardian.run({})

    assert docker_scanner.calls == []
    assert result["actions"] == [
        {"status": "skipped", "container": "api", "reason": "max_restart_attempts"}
    ]


def test_guardian_resets_restart_history_after_healthy_state(tmp_path: Path) -> None:
    history_path = tmp_path / "restart_history.json"
    history_path.write_text(
        json.dumps(
            {
                "api": {
                    "attempts": 3,
                    "last_restart": datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            }
        ),
        encoding="utf-8",
    )
    guardian = Guardian(
        health_checker=FakeHealthChecker(
            {"docker": {"containers": [{"name": "api", "status": "running"}]}}
        ),
        docker_scanner=FakeDockerScanner(),
        notifier=FakeNotifier(),
        restart_history_path=history_path,
    )

    result = guardian.run({})

    assert result["actions"] == []
    assert guardian.restart_history == {}
    assert json.loads(history_path.read_text(encoding="utf-8")) == {}


def test_guardian_restarts_running_container_when_health_check_fails(tmp_path: Path) -> None:
    health_check = FakeHealthCheck(healthy=False, status="failed")
    docker_scanner = FakeDockerScanner()
    guardian = Guardian(
        health_checker=FakeHealthChecker(
            {"docker": {"containers": [{"name": "api", "status": "running"}]}}
        ),
        docker_scanner=docker_scanner,
        notifier=FakeNotifier(),
        restart_cooldown_seconds=0,
        restart_history_path=tmp_path / "restart_history.json",
        health_checks=[health_check],
    )

    result = guardian.run({})

    assert docker_scanner.calls == []
    assert docker_scanner.restart_calls == ["api"]
    assert result["actions"][0]["action"] == "restarted"
    assert result["actions"][0]["health_checks"] == [
        {"name": "fake", "status": "failed", "healthy": False, "message": "failed"}
    ]
    assert guardian.restart_history["api"]["attempts"] == 1


def test_guardian_resets_history_when_running_container_passes_health_checks(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "restart_history.json"
    history_path.write_text(
        json.dumps(
            {
                "api": {
                    "attempts": 2,
                    "last_restart": datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            }
        ),
        encoding="utf-8",
    )
    guardian = Guardian(
        health_checker=FakeHealthChecker(
            {"docker": {"containers": [{"name": "api", "status": "running"}]}}
        ),
        docker_scanner=FakeDockerScanner(),
        notifier=FakeNotifier(),
        restart_history_path=history_path,
        health_checks=[FakeHealthCheck(healthy=True, status="ok")],
    )

    result = guardian.run({})

    assert result["actions"] == []
    assert guardian.restart_history == {}


def test_guardian_creates_and_updates_incident_for_failed_health_check(
    tmp_path: Path,
) -> None:
    incident_manager = IncidentManager(tmp_path / "incident_history.json")
    guardian = Guardian(
        health_checker=FakeHealthChecker(
            {"docker": {"containers": [{"name": "api", "status": "running"}]}}
        ),
        docker_scanner=FakeDockerScanner(),
        notifier=FakeNotifier(),
        restart_cooldown_seconds=0,
        restart_history_path=tmp_path / "restart_history.json",
        health_checks=[FakeHealthCheck(healthy=False, status="failed")],
        incident_manager=incident_manager,
    )

    result = guardian.run({})
    incidents = incident_manager.list_incidents()

    assert len(incidents) == 1
    assert incidents[0].service_name == "api"
    assert incidents[0].incident_type == "health_check_failed"
    assert incidents[0].remediation_attempted is True
    assert incidents[0].remediation_successful is True
    assert result["actions"][0]["incident_id"] == incidents[0].incident_id


def test_guardian_resolves_incident_when_service_becomes_healthy(tmp_path: Path) -> None:
    incident_manager = IncidentManager(tmp_path / "incident_history.json")
    incident = incident_manager.create_incident(
        severity="high",
        service_name="api",
        incident_type="health_check_failed",
        description="api failed",
    )
    guardian = Guardian(
        health_checker=FakeHealthChecker(
            {"docker": {"containers": [{"name": "api", "status": "running"}]}}
        ),
        docker_scanner=FakeDockerScanner(),
        notifier=FakeNotifier(),
        restart_history_path=tmp_path / "restart_history.json",
        health_checks=[FakeHealthCheck(healthy=True, status="ok")],
        incident_manager=incident_manager,
    )

    guardian.run({})

    resolved = incident_manager.list_incidents()[0]
    assert resolved.incident_id == incident.incident_id
    assert resolved.status == "resolved"
    assert resolved.resolved_timestamp is not None
