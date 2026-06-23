from pathlib import Path

from src.incidents import IncidentManager
from src.monitoring_engine import MonitoringEngine
from src.platform_db import PlatformRepository


def test_monitoring_engine_persists_results_and_incident_transitions(tmp_path: Path) -> None:
    repository = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    incident_manager = IncidentManager(tmp_path / "incidents.json")
    target = repository.create_monitoring_target(
        {"name": "db", "target_type": "tcp", "address": "localhost:1"}
    )
    engine = MonitoringEngine(repository, incident_manager, interval_seconds=5)

    engine._run_target = lambda target: {  # type: ignore[method-assign]
        "name": target["name"],
        "target_type": "tcp",
        "timestamp": "2026-06-21T12:00:00Z",
        "status": "failed",
        "reachable": False,
        "latency_ms": 1.0,
        "error": "connection refused",
    }
    engine.run_once()

    assert repository.latest_check_results()[0]["details"]["reachable"] is False
    assert incident_manager.get_active_incidents()[0].incident_type == "tcp_target_unreachable"
    assert repository.list_audit_logs()

    engine._run_target = lambda target: {  # type: ignore[method-assign]
        "name": target["name"],
        "target_type": "tcp",
        "timestamp": "2026-06-21T12:01:00Z",
        "status": "ok",
        "reachable": True,
        "latency_ms": 1.0,
        "error": "",
    }
    engine.run_once()

    assert incident_manager.list_incidents()[0].status == "resolved"
    assert repository.get_monitoring_target(int(target["id"])) is not None
