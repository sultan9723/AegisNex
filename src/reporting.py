"""Operational reporting from persisted AegisNex SQLite history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import csv
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Literal

from src.storage import AegisNexRepository

ReportFormat = Literal["json", "csv", "pdf"]


@dataclass(frozen=True)
class ReportWindow:
    start: datetime
    end: datetime
    label: str

    def to_dict(self) -> dict[str, str]:
        return {
            "start": _format_timestamp(self.start),
            "end": _format_timestamp(self.end),
            "label": self.label,
        }


class OperationalReporter:
    """Builds human-readable operational reports from SQLite history."""

    def __init__(self, database_path: str | Path = "aegisnex.db") -> None:
        self.database_path = Path(database_path)
        AegisNexRepository(self.database_path)

    def weekly_report(self, now: datetime | None = None) -> dict[str, Any]:
        end = _normalize_datetime(now)
        window = ReportWindow(
            start=end - timedelta(days=7),
            end=end,
            label="Last 7 days",
        )
        return self._build_report("weekly", window)

    def monthly_report(self, now: datetime | None = None) -> dict[str, Any]:
        end = _normalize_datetime(now)
        window = ReportWindow(
            start=end - timedelta(days=30),
            end=end,
            label="Last 30 days",
        )
        return self._build_report("monthly", window)

    def service_health_report(
        self,
        service_name: str | None = None,
        days: int = 30,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        end = _normalize_datetime(now)
        window = ReportWindow(
            start=end - timedelta(days=days),
            end=end,
            label=f"Last {days} days",
        )
        services = self._service_health(window, service_name)
        return {
            "report_type": "service_health",
            "generated_at": _format_timestamp(end),
            "window": window.to_dict(),
            "service_name": service_name,
            "services": services,
        }

    def export_report(
        self,
        report: dict[str, Any],
        output_path: str | Path,
        report_format: ReportFormat | None = None,
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        selected_format = report_format or _format_from_path(path)
        if selected_format == "json":
            path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        elif selected_format == "csv":
            self._write_csv(report, path)
        elif selected_format == "pdf":
            path.write_bytes(_render_pdf(_report_lines(report)))
        else:
            raise ValueError(f"Unsupported report format: {selected_format}")
        return path

    def _build_report(self, report_type: str, window: ReportWindow) -> dict[str, Any]:
        return {
            "report_type": report_type,
            "generated_at": _format_timestamp(window.end),
            "window": window.to_dict(),
            "summary": {
                **self._incident_summary(window),
                **self._remediation_summary(window),
                **self._notification_summary(window),
            },
            "top_failing_services": self._top_failing_services(window),
            "trends": {
                "cpu": self._metric_trend(window, "cpu_percent"),
                "memory": self._metric_trend(window, "memory_percent"),
            },
        }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _incident_summary(self, window: ReportWindow) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_incidents,
                    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_incidents,
                    SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved_incidents
                FROM incidents
                WHERE timestamp >= ?
                """,
                _window_start_param(window),
            ).fetchone()
            recovery_rows = connection.execute(
                """
                SELECT timestamp, resolved_timestamp
                FROM incidents
                WHERE timestamp >= ?
                    AND resolved_timestamp IS NOT NULL
                """,
                _window_start_param(window),
            ).fetchall()

        recovery_seconds = [
            (_parse_timestamp(row["resolved_timestamp"]) - _parse_timestamp(row["timestamp"])).total_seconds()
            for row in recovery_rows
            if row["resolved_timestamp"]
        ]
        average_recovery_seconds = (
            sum(recovery_seconds) / len(recovery_seconds) if recovery_seconds else 0.0
        )
        return {
            "total_incidents": int(row["total_incidents"] or 0),
            "active_incidents": int(row["active_incidents"] or 0),
            "resolved_incidents": int(row["resolved_incidents"] or 0),
            "average_recovery_seconds": round(average_recovery_seconds, 2),
        }

    def _remediation_summary(self, window: ReportWindow) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN successful = 1 THEN 1 ELSE 0 END) AS successful
                FROM remediations
                WHERE timestamp >= ?
                """,
                _window_start_param(window),
            ).fetchone()
        total = int(row["total"] or 0)
        successful = int(row["successful"] or 0)
        return {
            "remediation_attempts": total,
            "successful_remediations": successful,
            "failed_remediations": total - successful,
            "auto_remediation_success_rate": _percentage(successful, total),
        }

    def _notification_summary(self, window: ReportWindow) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status IN ('ok', 'sent', 'success') THEN 1 ELSE 0 END) AS successful
                FROM notifications
                WHERE timestamp >= ?
                """,
                _window_start_param(window),
            ).fetchone()
        total = int(row["total"] or 0)
        successful = int(row["successful"] or 0)
        return {
            "notification_attempts": total,
            "successful_notifications": successful,
            "failed_notifications": total - successful,
            "notification_success_rate": _percentage(successful, total),
        }

    def _top_failing_services(
        self, window: ReportWindow, limit: int = 5
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT service_name, COUNT(*) AS incident_count
                FROM incidents
                WHERE timestamp >= ?
                GROUP BY service_name
                ORDER BY incident_count DESC, service_name ASC
                LIMIT ?
                """,
                (*_window_start_param(window), limit),
            ).fetchall()
        return [
            {
                "service_name": str(row["service_name"]),
                "incident_count": int(row["incident_count"]),
            }
            for row in rows
        ]

    def _metric_trend(self, window: ReportWindow, column: str) -> dict[str, float]:
        allowed_columns = {"cpu_percent", "memory_percent"}
        if column not in allowed_columns:
            raise ValueError(f"Unsupported metrics column: {column}")
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT
                    AVG({column}) AS average,
                    MIN({column}) AS minimum,
                    MAX({column}) AS maximum
                FROM metrics_snapshots
                WHERE timestamp >= ?
                """,
                _window_start_param(window),
            ).fetchone()
        return {
            "average": round(float(row["average"] or 0.0), 2),
            "minimum": round(float(row["minimum"] or 0.0), 2),
            "maximum": round(float(row["maximum"] or 0.0), 2),
        }

    def _service_health(
        self, window: ReportWindow, service_name: str | None = None
    ) -> list[dict[str, Any]]:
        filters = ["timestamp >= ?"]
        params: list[Any] = list(_window_start_param(window))
        if service_name:
            filters.append("service_name = ?")
            params.append(service_name)
        where_clause = " AND ".join(filters)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    service_name,
                    COUNT(*) AS total_incidents,
                    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_incidents,
                    SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved_incidents,
                    MAX(timestamp) AS last_incident_timestamp
                FROM incidents
                WHERE {where_clause}
                GROUP BY service_name
                ORDER BY total_incidents DESC, service_name ASC
                """,
                params,
            ).fetchall()
        return [
            {
                "service_name": str(row["service_name"]),
                "total_incidents": int(row["total_incidents"] or 0),
                "active_incidents": int(row["active_incidents"] or 0),
                "resolved_incidents": int(row["resolved_incidents"] or 0),
                "last_incident_timestamp": row["last_incident_timestamp"],
            }
            for row in rows
        ]

    def _write_csv(self, report: dict[str, Any], output_path: Path) -> None:
        with output_path.open("w", encoding="utf-8", newline="") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerow(["section", "metric", "value"])
            for line in _flatten_report(report):
                writer.writerow(line)


def _flatten_report(report: dict[str, Any]) -> Iterable[tuple[str, str, Any]]:
    yield ("metadata", "report_type", report.get("report_type", ""))
    yield ("metadata", "generated_at", report.get("generated_at", ""))
    window = report.get("window", {})
    if isinstance(window, dict):
        for key, value in window.items():
            yield ("window", key, value)
    summary = report.get("summary", {})
    if isinstance(summary, dict):
        for key, value in summary.items():
            yield ("summary", key, value)
    trends = report.get("trends", {})
    if isinstance(trends, dict):
        for metric_name, trend in trends.items():
            if isinstance(trend, dict):
                for key, value in trend.items():
                    yield (f"trend.{metric_name}", key, value)
    for item in report.get("top_failing_services", []):
        if isinstance(item, dict):
            yield (
                "top_failing_services",
                str(item.get("service_name", "")),
                item.get("incident_count", 0),
            )
    for item in report.get("services", []):
        if isinstance(item, dict):
            service = str(item.get("service_name", ""))
            for key, value in item.items():
                if key != "service_name":
                    yield (f"service.{service}", key, value)


def _report_lines(report: dict[str, Any]) -> list[str]:
    title = str(report.get("report_type", "operational")).replace("_", " ").title()
    lines = [f"AegisNex {title} Report"]
    for section, metric, value in _flatten_report(report):
        lines.append(f"{section} - {metric}: {value}")
    return lines


def _render_pdf(lines: list[str]) -> bytes:
    text_commands = ["BT", "/F1 11 Tf", "50 760 Td", "14 TL"]
    for index, line in enumerate(lines[:48]):
        if index:
            text_commands.append("T*")
        text_commands.append(f"({_escape_pdf_text(line[:100])}) Tj")
    text_commands.append("ET")
    stream = "\n".join(text_commands).encode("utf-8")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _format_from_path(path: Path) -> ReportFormat:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"json", "csv", "pdf"}:
        return suffix  # type: ignore[return-value]
    raise ValueError(f"Cannot infer report format from path: {path}")


def _normalize_datetime(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return _normalize_datetime(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _window_params(window: ReportWindow) -> tuple[str, str]:
    return (_format_timestamp(window.start), _format_timestamp(window.end))


def _window_start_param(window: ReportWindow) -> tuple[str]:
    return (_format_timestamp(window.start),)


def _percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)
