from pathlib import Path

from src.http_monitor import HttpEndpointMonitor
from src.incidents import IncidentManager
from src.storage import AegisNexRepository


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def get(self, url, timeout):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class HeaderAwareClient:
    def __init__(self) -> None:
        self.kwargs = {}

    def get(self, url, **kwargs):
        self.kwargs = kwargs
        return FakeResponse(302)


def test_http_monitor_records_latency_status_and_availability(tmp_path: Path) -> None:
    repository = AegisNexRepository(tmp_path / "aegisnex.db")
    incident_manager = IncidentManager(
        tmp_path / "incident_history.json",
        storage_repository=repository,
    )
    monitor = HttpEndpointMonitor(
        endpoints={"api": "http://example.test/health"},
        expected_status=200,
        incident_manager=incident_manager,
        storage_repository=repository,
        client=FakeClient([FakeResponse(200)]),
    )

    result = monitor.run({})

    assert result["status"] == "ok"
    assert result["availability_percent"] == 100.0
    assert result["checks"][0]["status_code"] == 200
    assert result["checks"][0]["latency_ms"] >= 0
    assert repository.fetch_all("http_checks")[0]["endpoint_name"] == "api"


def test_http_monitor_accepts_redirect_range_and_sends_user_agent() -> None:
    client = HeaderAwareClient()
    monitor = HttpEndpointMonitor(
        endpoints={"github": "https://github.com"},
        client=client,
    )

    result = monitor.run({})

    assert result["status"] == "ok"
    assert result["checks"][0]["status_code"] == 302
    assert result["checks"][0]["available"] is True
    assert client.kwargs["follow_redirects"] is True
    assert "AegisNex-Monitor" in client.kwargs["headers"]["User-Agent"]


def test_http_monitor_generates_and_resolves_incidents(tmp_path: Path) -> None:
    repository = AegisNexRepository(tmp_path / "aegisnex.db")
    incident_manager = IncidentManager(
        tmp_path / "incident_history.json",
        storage_repository=repository,
    )
    monitor = HttpEndpointMonitor(
        endpoints={"api": "http://example.test/health"},
        expected_status=200,
        incident_manager=incident_manager,
        storage_repository=repository,
        client=FakeClient([FakeResponse(500), FakeResponse(200)]),
    )

    failed = monitor.run({})
    recovered = monitor.run({})

    incidents = incident_manager.list_incidents()
    assert failed["status"] == "warning"
    assert failed["checks"][0]["available"] is False
    assert recovered["status"] == "ok"
    assert incidents[0].incident_type == "http_endpoint_failure"
    assert incidents[0].status == "resolved"
    assert recovered["checks"][0]["availability_percent"] == 50.0
