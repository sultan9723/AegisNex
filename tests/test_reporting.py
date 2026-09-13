from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from src.incidents import Incident
from src.reporting import OperationalReporter
from src.platform_db import PlatformRepository


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
    repository = PlatformRepository(str(db_path))
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


def test_weekly_report_counts_inserted_rows_with_future_clock_skew(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "aegisnex.db"
    PlatformRepository(str(db_path)).initialize()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO incidents (
                incident_id,
                timestamp,
                severity,
                service_name,
                incident_type,
                description,
                health_check_results,
                remediation_attempted,
                remediation_successful,
                status,
                resolved_timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "INC-FUTURE",
                "2026-06-04T13:00:00Z",
                "critical",
                "api",
                "container_status",
                "api stopped",
                "[]",
                1,
                1,
                "resolved",
                "2026-06-04T13:05:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO notifications (
                timestamp,
                event_type,
                incident_id,
                service_name,
                provider,
                status,
                attempts,
                message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-04T13:00:01Z",
                "incident_created",
                "INC-FUTURE",
                "api",
                "email",
                "ok",
                1,
                "",
            ),
        )
        connection.execute(
            """
            INSERT INTO remediation_actions (
                timestamp,
                service_name,
                action,
                successful,
                incident_id,
                details
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-04T13:00:02Z",
                "api",
                "restart",
                1,
                "INC-FUTURE",
                "{}",
            ),
        )

    report = OperationalReporter(db_path).weekly_report(now=NOW)

    assert report["summary"]["total_incidents"] == 1
    assert report["summary"]["resolved_incidents"] == 1
    assert report["summary"]["remediation_attempts"] == 1
    assert report["summary"]["notification_attempts"] == 1
    assert report["summary"]["average_recovery_seconds"] == 300.0


def test_monthly_report_counts_inserted_rows_using_incident_timestamp_column(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "aegisnex.db"
    PlatformRepository(str(db_path)).initialize()
    with sqlite3.connect(db_path) as connection:
        columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info(incidents)").fetchall()
        ]
        assert "timestamp" in columns
        for incident_id, timestamp in (
            ("INC-WEEKLY", "2026-06-03T12:00:00Z"),
            ("INC-MONTHLY", "2026-05-20T12:00:00Z"),
            ("INC-OLD", "2026-04-20T12:00:00Z"),
        ):
            connection.execute(
                """
                INSERT INTO incidents (
                    incident_id,
                    timestamp,
                    severity,
                    service_name,
                    incident_type,
                    description,
                    health_check_results,
                    remediation_attempted,
                    remediation_successful,
                    status,
                    resolved_timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    timestamp,
                    "high",
                    "api",
                    "health_check_failed",
                    "api failed",
                    "[]",
                    0,
                    0,
                    "active",
                    None,
                ),
            )

    reporter = OperationalReporter(db_path)

    assert reporter.weekly_report(now=NOW)["summary"]["total_incidents"] == 1
    assert reporter.monthly_report(now=NOW)["summary"]["total_incidents"] == 2
