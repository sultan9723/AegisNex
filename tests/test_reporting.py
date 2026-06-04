from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from src.incidents import Incident
from src.reporting import OperationalReporter
from src.storage import AegisNexRepository


NOW = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)


def make_incident(
    incident_id: str,
    service_name: str,
    timestamp: str,
    status: str = "active",
    resolved_timestamp: str | None = None,
) -> Incident:
    return Incident(
        incident_id=incident_id,
        timestamp=timestamp,
        severity="high",
        service_name=service_name,
        incident_type="health_check_failed",
        description=f"{service_name} health check failed",
        health_check_results=[{"name": "http", "healthy": False}],
        remediation_attempted=False,
        remediation_successful=False,
        status=status,
        resolved_timestamp=resolved_timestamp,
    )


def seed_history(db_path: Path) -> None:
    repository = AegisNexRepository(db_path)
    repository.save_incident(
        make_incident(
            "INC-1",
            "api",
            "2026-06-03T12:00:00Z",
            status="resolved",
            resolved_timestamp="2026-06-03T12:10:00Z",
        )
    )
    repository.save_incident(
        make_incident("INC-2", "api", "2026-06-04T10:00:00Z")
    )
    repository.save_incident(
        make_incident(
            "INC-3",
            "db",
            "2026-06-02T12:00:00Z",
            status="resolved",
            resolved_timestamp="2026-06-02T12:20:00Z",
        )
    )
    repository.save_incident(
        make_incident("INC-OLD", "worker", "2026-05-01T12:00:00Z")
    )
    repository.save_remediation_action(
        "api", "restart", True, "INC-1", timestamp="2026-06-03T12:01:00Z"
    )
    repository.save_remediation_action(
        "db", "restart", False, "INC-3", timestamp="2026-06-02T12:01:00Z"
    )
    repository.save_notification_event(
        {
            "timestamp": "2026-06-03T12:00:00Z",
            "event_type": "incident_created",
            "incident_id": "INC-1",
            "service_name": "api",
            "provider": "email",
            "status": "ok",
            "attempts": 1,
            "message": "",
        }
    )
    repository.save_notification_event(
        {
            "timestamp": "2026-06-02T12:00:00Z",
            "event_type": "incident_created",
            "incident_id": "INC-3",
            "service_name": "db",
            "provider": "slack",
            "status": "failed",
            "attempts": 2,
            "message": "timeout",
        }
    )
    repository.save_metrics_snapshot(
        {
            "aegisnex_system_cpu_usage_percent": 20,
            "aegisnex_system_memory_usage_percent": 40,
        },
        timestamp="2026-06-03T12:00:00Z",
    )
    repository.save_metrics_snapshot(
        {
            "aegisnex_system_cpu_usage_percent": 40,
            "aegisnex_system_memory_usage_percent": 60,
        },
        timestamp="2026-06-04T11:00:00Z",
    )


def test_weekly_report_calculates_operational_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "aegisnex.db"
    seed_history(db_path)

    report = OperationalReporter(db_path).weekly_report(now=NOW)

    assert report["report_type"] == "weekly"
    assert report["summary"]["total_incidents"] == 3
    assert report["summary"]["active_incidents"] == 1
    assert report["summary"]["resolved_incidents"] == 2
    assert report["summary"]["average_recovery_seconds"] == 900.0
    assert report["summary"]["auto_remediation_success_rate"] == 50.0
    assert report["summary"]["notification_success_rate"] == 50.0
    assert report["top_failing_services"][0] == {
        "service_name": "api",
        "incident_count": 2,
    }
    assert report["trends"]["cpu"] == {
        "average": 30.0,
        "minimum": 20.0,
        "maximum": 40.0,
    }
    assert report["trends"]["memory"]["average"] == 50.0


def test_monthly_report_uses_thirty_day_window(tmp_path: Path) -> None:
    db_path = tmp_path / "aegisnex.db"
    seed_history(db_path)

    report = OperationalReporter(db_path).monthly_report(now=NOW)

    assert report["window"]["label"] == "Last 30 days"
    assert report["summary"]["total_incidents"] == 3


def test_service_health_report_groups_incidents_by_service(tmp_path: Path) -> None:
    db_path = tmp_path / "aegisnex.db"
    seed_history(db_path)

    report = OperationalReporter(db_path).service_health_report(now=NOW)

    assert report["report_type"] == "service_health"
    assert report["services"][0]["service_name"] == "api"
    assert report["services"][0]["total_incidents"] == 2
    assert report["services"][0]["active_incidents"] == 1


def test_service_health_report_can_filter_to_one_service(tmp_path: Path) -> None:
    db_path = tmp_path / "aegisnex.db"
    seed_history(db_path)

    report = OperationalReporter(db_path).service_health_report(
        service_name="db", now=NOW
    )

    assert [service["service_name"] for service in report["services"]] == ["db"]


def test_report_exports_json_csv_and_pdf(tmp_path: Path) -> None:
    db_path = tmp_path / "aegisnex.db"
    seed_history(db_path)
    reporter = OperationalReporter(db_path)
    report = reporter.weekly_report(now=NOW)

    json_path = reporter.export_report(report, tmp_path / "weekly.json")
    csv_path = reporter.export_report(report, tmp_path / "weekly.csv")
    pdf_path = reporter.export_report(report, tmp_path / "weekly.pdf")

    assert json.loads(json_path.read_text(encoding="utf-8"))["report_type"] == "weekly"
    assert "summary,total_incidents,3" in csv_path.read_text(encoding="utf-8")
    assert pdf_path.read_bytes().startswith(b"%PDF-")


def test_empty_database_report_returns_zero_metrics(tmp_path: Path) -> None:
    report = OperationalReporter(tmp_path / "empty.db").weekly_report(now=NOW)

    assert report["summary"]["total_incidents"] == 0
    assert report["summary"]["auto_remediation_success_rate"] == 0.0
    assert report["trends"]["cpu"]["average"] == 0.0
