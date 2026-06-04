from types import SimpleNamespace
from urllib.error import URLError

from src.health_checks import DockerHealthCheck, HttpHealthCheck, TcpHealthCheck


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_docker_health_check_uses_container_health_status() -> None:
    result = DockerHealthCheck().check({"name": "api", "health_status": "unhealthy"})

    assert result.name == "docker"
    assert result.healthy is False
    assert result.status == "unhealthy"


def test_docker_health_check_treats_missing_health_as_healthy_unknown() -> None:
    result = DockerHealthCheck().check({"name": "api", "health_status": "none"})

    assert result.healthy is True
    assert result.status == "unknown"


def test_docker_health_check_can_query_scanner() -> None:
    scanner = SimpleNamespace(get_health_status=lambda name: "healthy")

    result = DockerHealthCheck(docker_scanner=scanner).check({"name": "api"})

    assert result.healthy is True
    assert result.status == "healthy"


def test_http_health_check_success(monkeypatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return FakeResponse(200)

    monkeypatch.setattr("src.health_checks.urlopen", fake_urlopen)
    check = HttpHealthCheck({"api": "http://localhost/health"}, timeout_seconds=2)

    result = check.check({"name": "api"})

    assert result.healthy is True
    assert result.status == "200"
    assert calls == [("http://localhost/health", 2)]


def test_http_health_check_failure_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.health_checks.urlopen",
        lambda request, timeout: FakeResponse(503),
    )

    result = HttpHealthCheck({"api": "http://localhost/health"}).check({"name": "api"})

    assert result.healthy is False
    assert result.status == "503"


def test_http_health_check_connection_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.health_checks.urlopen",
        lambda request, timeout: (_ for _ in ()).throw(URLError("down")),
    )

    result = HttpHealthCheck({"api": "http://localhost/health"}).check({"name": "api"})

    assert result.healthy is False
    assert result.status == "failed"


def test_http_health_check_skips_unconfigured_container() -> None:
    result = HttpHealthCheck({}).check({"name": "api"})

    assert result.healthy is True
    assert result.status == "skipped"


def test_tcp_health_check_success(monkeypatch) -> None:
    calls = []

    def fake_create_connection(address, timeout):
        calls.append((address, timeout))
        return FakeSocket()

    monkeypatch.setattr("src.health_checks.socket.create_connection", fake_create_connection)
    result = TcpHealthCheck({"api": "localhost:8080"}, timeout_seconds=3).check(
        {"name": "api"}
    )

    assert result.healthy is True
    assert result.status == "open"
    assert calls == [(("localhost", 8080), 3)]


def test_tcp_health_check_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.health_checks.socket.create_connection",
        lambda address, timeout: (_ for _ in ()).throw(OSError("refused")),
    )

    result = TcpHealthCheck({"api": "localhost:8080"}).check({"name": "api"})

    assert result.healthy is False
    assert result.status == "closed"


def test_tcp_health_check_skips_unconfigured_container() -> None:
    result = TcpHealthCheck({}).check({"name": "api"})

    assert result.healthy is True
    assert result.status == "skipped"
