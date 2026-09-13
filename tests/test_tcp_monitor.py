from pathlib import Path

from src.incidents import IncidentManager
from src.platform_db import PlatformRepository
from src.tcp_monitor import TcpTargetMonitor


def test_tcp_monitor_records_reachable_target(tmp_path: Path) -> None:
    repository = PlatformRepository(str(tmp_path / "aegisnex.db"))
    incident_manager = IncidentManager(
        tmp_path / "incident_history.json",
        storage_repository=repository,
    )
    monitor = TcpTargetMonitor(
        targets={"db": "localhost:5432"},
        incident_manager=incident_manager,
        storage_repository=repository,
        connector=lambda host, port, timeout: None,
    )

    result = monitor.run({})
    check = result["checks"][0]

    assert result["status"] == "ok"
    assert result["availability_percent"] == 100.0
    assert check["host"] == "localhost"
    assert check["port"] == 5432
    assert check["reachable"] is True
    results = repository.fetch_all("check_results")
    tcp_results = [r for r in results if r.get("target_type") == "tcp"]
    assert tcp_results[0]["target_name"] == "db"


def test_tcp_monitor_generates_and_resolves_incidents(tmp_path: Path) -> None:
    incident_manager = IncidentManager(tmp_path / "incident_history.json")
    outcomes = [ConnectionError("connection refused"), None]

    def connector(host, port, timeout):
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome

    monitor = TcpTargetMonitor(
        targets={"db": "localhost:5432"},
        incident_manager=incident_manager,
        connector=connector,
    )

    failed = monitor.run({})
    recovered = monitor.run({})
    incident = incident_manager.list_incidents()[0]

    assert failed["status"] == "warning"
    assert failed["checks"][0]["reachable"] is False
    assert incident.incident_type == "tcp_target_unreachable"
    assert recovered["status"] == "ok"
    assert incident.status == "resolved"


def test_tcp_monitor_filters_target_name() -> None:
    seen: list[tuple[str, int]] = []
    monitor = TcpTargetMonitor(
        targets={"db": "localhost:5432", "cache": "localhost:6379"},
        connector=lambda host, port, timeout: seen.append((host, port)),
    )

    result = monitor.run({"target_name": "cache"})

    assert result["total_count"] == 1
    assert result["checks"][0]["name"] == "cache"
    assert seen == [("localhost", 6379)]
