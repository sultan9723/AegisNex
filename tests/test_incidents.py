import json
from pathlib import Path

import pytest

from src.incidents import IncidentManager


def test_create_incident_persists_to_history(tmp_path: Path) -> None:
    history_path = tmp_path / "incident_history.json"
    manager = IncidentManager(history_path)

    incident = manager.create_incident(
        severity="high",
        service_name="api",
        incident_type="health_check_failed",
        description="api health check failed",
        health_check_results=[
            {"name": "http", "status": "503", "healthy": False, "message": "down"}
        ],
    )

    payload = json.loads(history_path.read_text(encoding="utf-8"))
    assert incident.incident_id
    assert incident.status == "active"
    assert payload[0]["service_name"] == "api"
    assert payload[0]["remediation_attempted"] is False
    assert payload[0]["resolved_timestamp"] is None


def test_create_incident_reuses_active_service_type_incident(tmp_path: Path) -> None:
    manager = IncidentManager(tmp_path / "incident_history.json")
    first = manager.create_incident(
        severity="high",
        service_name="api",
        incident_type="health_check_failed",
        description="first",
    )
    second = manager.create_incident(
        severity="critical",
        service_name="api",
        incident_type="health_check_failed",
        description="second",
    )

    assert first.incident_id == second.incident_id
    assert len(manager.list_incidents()) == 1
    assert manager.list_incidents()[0].severity == "critical"
    assert manager.list_incidents()[0].description == "second"


def test_update_and_resolve_incident(tmp_path: Path) -> None:
    manager = IncidentManager(tmp_path / "incident_history.json")
    incident = manager.create_incident(
        severity="critical",
        service_name="api",
        incident_type="container_status",
        description="api stopped",
    )

    updated = manager.update_incident(
        incident.incident_id,
        remediation_attempted=True,
        remediation_successful=True,
    )
    resolved = manager.resolve_incident(incident.incident_id)

    assert updated.remediation_attempted is True
    assert updated.remediation_successful is True
    assert resolved.status == "resolved"
    assert resolved.resolved_timestamp is not None
    assert manager.get_active_incidents() == []


def test_resolve_service_incidents_resolves_only_matching_service(tmp_path: Path) -> None:
    manager = IncidentManager(tmp_path / "incident_history.json")
    api = manager.create_incident("high", "api", "health_check_failed", "api failed")
    db = manager.create_incident("high", "db", "health_check_failed", "db failed")

    resolved = manager.resolve_service_incidents("api")

    assert [incident.incident_id for incident in resolved] == [api.incident_id]
    active_ids = [incident.incident_id for incident in manager.get_active_incidents()]
    assert active_ids == [db.incident_id]


def test_incident_manager_loads_existing_history(tmp_path: Path) -> None:
    history_path = tmp_path / "incident_history.json"
    history_path.write_text(
        json.dumps(
            [
                {
                    "incident_id": "INC-1",
                    "timestamp": "2026-06-04T00:00:00Z",
                    "severity": "high",
                    "service_name": "api",
                    "incident_type": "health_check_failed",
                    "description": "api failed",
                    "health_check_results": [],
                    "remediation_attempted": False,
                    "remediation_successful": False,
                    "status": "active",
                    "resolved_timestamp": None,
                }
            ]
        ),
        encoding="utf-8",
    )

    manager = IncidentManager(history_path)

    assert len(manager.list_incidents()) == 1
    assert manager.get_active_incidents()[0].incident_id == "INC-1"


def test_update_incident_rejects_unknown_id(tmp_path: Path) -> None:
    manager = IncidentManager(tmp_path / "incident_history.json")

    with pytest.raises(KeyError):
        manager.update_incident("missing", status="resolved")
