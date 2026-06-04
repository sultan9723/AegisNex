from src.orchestrator import SystemHealthChecker


class FakeComponent:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def run(self, params):
        self.calls.append(params)
        if self.error:
            raise self.error
        return self.result


def test_health_checker_aggregates_monitor_and_docker_results() -> None:
    monitor = FakeComponent({"status": "ok"})
    docker = FakeComponent({"status": "ok", "containers": []})
    checker = SystemHealthChecker(monitor=monitor, docker_scanner=docker)

    result = checker.run({"monitor": {"cpu_interval": 0}, "docker": {"include_all": True}})

    assert result["hardware"] == {"status": "ok"}
    assert result["docker"] == {"status": "ok", "containers": []}
    assert result["timestamp"].endswith("Z")
    assert monitor.calls == [{"cpu_interval": 0}]
    assert docker.calls == [{"include_all": True}]


def test_health_checker_converts_component_failures_to_failed_sections() -> None:
    checker = SystemHealthChecker(
        monitor=FakeComponent(error=RuntimeError("monitor failed")),
        docker_scanner=FakeComponent(error=RuntimeError("docker failed")),
    )

    result = checker.run({})

    assert result["hardware"] == {"status": "failed", "error": "monitor failed"}
    assert result["docker"] == {"status": "failed", "error": "docker failed"}
