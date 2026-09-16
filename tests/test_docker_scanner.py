from types import SimpleNamespace

import pytest
from docker import errors as docker_errors

from src.docker_scanner import DockerScanner, docker_scanner_enabled_from_env


class FakeContainer:
    def __init__(self, name="api", status="running", short_id="abc123", health_status="none"):
        self.name = name
        self.status = status
        self.short_id = short_id
        self.image = SimpleNamespace(tags=[f"{name}:latest"], short_id=short_id)
        self.attrs = {"State": {"Health": {"Status": health_status}, "StartedAt": "2026-06-04T12:00:00Z"}}
        self.reload_calls = 0
        self.restart_calls = []

    def reload(self):
        self.reload_calls += 1

    def restart(self, timeout=None):
        self.restart_calls.append(timeout)
        self.status = "running"


class FakeContainerCollection:
    def __init__(self, containers):
        self._containers = containers
        self.list_calls = []

    def get(self, name):
        if isinstance(self._containers, Exception):
            raise self._containers
        return self._containers[name]

    def list(self, all=False):
        self.list_calls.append(all)
        if isinstance(self._containers, Exception):
            raise self._containers
        return list(self._containers.values())


class FakeDockerClient:
    def __init__(self, containers, ping_error=None):
        self.containers = FakeContainerCollection(containers)
        self.ping_error = ping_error
        self.ping_calls = 0

    def ping(self):
        self.ping_calls += 1
        if self.ping_error:
            raise self.ping_error


def test_run_lists_containers_and_maps_statuses() -> None:
    containers = {
        "api": FakeContainer(name="api", status="running", short_id="a1", health_status="healthy"),
        "db": FakeContainer(name="db", status="exited", short_id="d1"),
        "job": FakeContainer(name="job", status="restarting", short_id="j1"),
    }
    client = FakeDockerClient(containers)
    scanner = DockerScanner(include_all=False)
    scanner._client = lambda: client

    result = scanner.run({"include_all": True})

    assert client.ping_calls == 1
    assert client.containers.list_calls == [True]
    for c in result["containers"]:
        assert c["id"] in ("a1", "d1", "j1")
        assert c["name"] in ("api", "db", "job")
        assert c["status"] in ("running", "stopped", "error")
        assert "raw_status" in c
        assert "health_status" in c
        assert "image" in c
        assert "started_at" in c
        assert "uptime_seconds" in c
        assert "ports" in c
        assert "cpu_percent" in c
        assert "memory_usage_bytes" in c
        assert "memory_limit_bytes" in c
        assert "memory_percent" in c


def test_run_returns_error_when_docker_daemon_unavailable() -> None:
    scanner = DockerScanner()
    scanner._client = lambda: FakeDockerClient(
        {},
        ping_error=docker_errors.DockerException("daemon unavailable"),
    )

    assert scanner.run() == {"status": "error", "message": "Docker daemon not running"}


def test_ensure_running_returns_already_running() -> None:
    container = FakeContainer(status="running")
    scanner = DockerScanner()
    scanner._client = lambda: FakeDockerClient({"api": container})

    result = scanner.ensure_running("api")

    assert result == {"status": "ok", "container": "api", "action": "already_running"}
    assert container.restart_calls == []


def test_ensure_running_restarts_stopped_container_with_timeout() -> None:
    container = FakeContainer(status="exited")
    scanner = DockerScanner(restart_timeout_seconds=7)
    scanner._client = lambda: FakeDockerClient({"api": container})

    result = scanner.ensure_running("api")

    assert container.restart_calls == [7]
    assert result == {
        "status": "ok",
        "container": "api",
        "action": "restarted",
        "current_status": "running",
    }


def test_ensure_running_handles_not_found() -> None:
    scanner = DockerScanner()
    scanner._client = lambda: SimpleNamespace(
        containers=SimpleNamespace(
            get=lambda name: (_ for _ in ()).throw(docker_errors.NotFound("missing"))
        )
    )

    assert scanner.ensure_running("missing") == {
        "status": "error",
        "message": "Container not found",
        "container": "missing",
    }


def test_ensure_running_handles_generic_restart_failure() -> None:
    container = FakeContainer(status="exited")
    container.restart = lambda timeout=None: (_ for _ in ()).throw(RuntimeError("boom"))
    scanner = DockerScanner()
    scanner._client = lambda: FakeDockerClient({"api": container})

    assert scanner.ensure_running("api") == {
        "status": "error",
        "message": "Failed to restart container",
        "container": "api",
    }


def test_get_health_status_reads_container_health() -> None:
    container = FakeContainer(status="running", health_status="unhealthy")
    scanner = DockerScanner()
    scanner._client = lambda: FakeDockerClient({"api": container})

    assert scanner.get_health_status("api") == "unhealthy"


def test_restart_container_restarts_running_container() -> None:
    container = FakeContainer(status="running")
    scanner = DockerScanner(restart_timeout_seconds=9)
    scanner._client = lambda: FakeDockerClient({"api": container})

    result = scanner.restart_container("api")

    assert container.restart_calls == [9]
    assert result == {
        "status": "ok",
        "container": "api",
        "action": "restarted",
        "current_status": "running",
    }


# --- AEGISNEX_DOCKER_SCANNER_ENABLED (cloud deployments without a Docker daemon) ---


def test_docker_scanner_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AEGISNEX_DOCKER_SCANNER_ENABLED", raising=False)
    assert docker_scanner_enabled_from_env() is True


@pytest.mark.parametrize("value", ["false", "False", "0", "no", "off"])
def test_docker_scanner_enabled_from_env_disabled_values(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AEGISNEX_DOCKER_SCANNER_ENABLED", value)
    assert docker_scanner_enabled_from_env() is False


@pytest.mark.parametrize("value", ["true", "True", "1", "yes", "anything-else"])
def test_docker_scanner_enabled_from_env_enabled_values(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AEGISNEX_DOCKER_SCANNER_ENABLED", value)
    assert docker_scanner_enabled_from_env() is True


def _fail_if_called() -> None:
    raise AssertionError("DockerScanner attempted a Docker daemon connection while disabled")


def test_disabled_scanner_never_attempts_client_connection() -> None:
    scanner = DockerScanner(enabled=False)
    scanner._client = lambda: _fail_if_called()

    assert scanner.run() == {"status": "disabled", "message": "Docker scanning is disabled", "containers": []}
    assert scanner.ensure_running("api") == {
        "status": "disabled",
        "message": "Docker scanning is disabled",
        "container": "api",
    }
    assert scanner.restart_container("api") == {
        "status": "disabled",
        "message": "Docker scanning is disabled",
        "container": "api",
    }
    assert scanner.start_container("api") == {
        "status": "disabled",
        "message": "Docker scanning is disabled",
        "container": "api",
    }
    assert scanner.stop_container("api") == {
        "status": "disabled",
        "message": "Docker scanning is disabled",
        "container": "api",
    }
    assert scanner.get_container_logs("api") == {
        "status": "disabled",
        "message": "Docker scanning is disabled",
        "container": "api",
        "logs": [],
        "count": 0,
    }
    # "none" (not a fake "healthy"/"unhealthy") so callers don't misreport status.
    assert scanner.get_health_status("api") == "none"


def test_disabled_scanner_logs_one_info_message() -> None:
    class RecordingLogger:
        def __init__(self) -> None:
            self.info_calls: list[str] = []

        def info(self, msg: str, *args: object) -> None:
            self.info_calls.append(msg % args if args else msg)

    logger = RecordingLogger()
    scanner = DockerScanner(logger=logger, enabled=False)

    scanner.run()
    scanner.run()
    scanner.ensure_running("api")

    assert len(logger.info_calls) == 1
    assert "disabled" in logger.info_calls[0].lower()


def test_scanner_enabled_by_default_reads_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AEGISNEX_DOCKER_SCANNER_ENABLED", raising=False)
    container = FakeContainer(status="running")
    scanner = DockerScanner()
    scanner._client = lambda: FakeDockerClient({"api": container})

    assert scanner.enabled is True
    result = scanner.run()
    assert result["status"] == "ok"
