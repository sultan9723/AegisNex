from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.incidents import IncidentManager
from src.ssl_monitor import CERT_DATETIME_FORMAT, SslCertificateMonitor
from src.storage import AegisNexRepository


def certificate(days_remaining: int, issuer: str = "Example CA") -> dict:
    expires_at = datetime.now(timezone.utc) + timedelta(days=days_remaining)
    return {
        "notAfter": expires_at.strftime(CERT_DATETIME_FORMAT),
        "issuer": ((("organizationName", issuer),), (("commonName", issuer),)),
    }


def test_ssl_monitor_reports_expiry_issuer_and_days_remaining(tmp_path: Path) -> None:
    repository = AegisNexRepository(tmp_path / "aegisnex.db")
    incident_manager = IncidentManager(
        tmp_path / "incident_history.json",
        storage_repository=repository,
    )
    monitor = SslCertificateMonitor(
        targets={"api": "example.com:443"},
        warning_days=30,
        incident_manager=incident_manager,
        storage_repository=repository,
        certificate_fetcher=lambda host, port, timeout: certificate(90),
    )

    result = monitor.run({})
    check = result["checks"][0]

    assert result["status"] == "ok"
    assert check["issuer"] == "Example CA, Example CA"
    assert 88 <= check["days_remaining"] <= 90
    assert check["expires_at"].endswith("Z")
    assert repository.fetch_all("ssl_checks")[0]["target_name"] == "api"


def test_ssl_monitor_generates_and_resolves_expiry_incidents(tmp_path: Path) -> None:
    repository = AegisNexRepository(tmp_path / "aegisnex.db")
    incident_manager = IncidentManager(
        tmp_path / "incident_history.json",
        storage_repository=repository,
    )
    certificates = [certificate(7), certificate(90)]
    monitor = SslCertificateMonitor(
        targets={"api": "example.com"},
        warning_days=30,
        incident_manager=incident_manager,
        storage_repository=repository,
        certificate_fetcher=lambda host, port, timeout: certificates.pop(0),
    )

    warning = monitor.run({})
    recovered = monitor.run({})

    incident = incident_manager.list_incidents()[0]
    assert warning["status"] == "warning"
    assert warning["checks"][0]["status"] == "warning"
    assert incident.incident_type == "ssl_certificate_expiring"
    assert recovered["status"] == "ok"
    assert incident.status == "resolved"


def test_ssl_monitor_generates_failure_incident(tmp_path: Path) -> None:
    incident_manager = IncidentManager(tmp_path / "incident_history.json")
    monitor = SslCertificateMonitor(
        targets={"api": "example.com:443"},
        incident_manager=incident_manager,
        certificate_fetcher=lambda host, port, timeout: (_ for _ in ()).throw(
            TimeoutError("timed out")
        ),
    )

    result = monitor.run({})
    incident = incident_manager.list_incidents()[0]

    assert result["status"] == "warning"
    assert result["checks"][0]["status"] == "failed"
    assert incident.severity == "critical"
    assert incident.incident_type == "ssl_certificate_check_failed"
