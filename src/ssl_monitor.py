"""SSL certificate monitoring for AegisNex."""

from __future__ import annotations

import socket
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.incidents import IncidentManager, utc_timestamp

CERT_DATETIME_FORMAT = "%b %d %H:%M:%S %Y %Z"


@dataclass(frozen=True)
class SslCertificateCheck:
    name: str
    target: str
    host: str
    port: int
    timestamp: str
    status: str
    valid: bool
    issuer: str
    expires_at: str | None
    days_remaining: int | None
    warning_days: int
    error: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "host": self.host,
            "port": self.port,
            "timestamp": self.timestamp,
            "status": self.status,
            "valid": self.valid,
            "issuer": self.issuer,
            "expires_at": self.expires_at,
            "days_remaining": self.days_remaining,
            "warning_days": self.warning_days,
            "error": self.error,
        }


class SslCertificateMonitor:
    """Check SSL certificate expiry and issuer for configured targets."""

    def __init__(
        self,
        targets: Mapping[str, str],
        timeout_seconds: int = 5,
        warning_days: int = 30,
        incident_manager: IncidentManager | None = None,
        storage_repository: Any | None = None,
        certificate_fetcher: Any | None = None,
    ) -> None:
        self.targets = dict(targets)
        self.timeout_seconds = timeout_seconds
        self.warning_days = max(0, warning_days)
        self.incident_manager = incident_manager
        self.storage_repository = storage_repository
        self.certificate_fetcher = certificate_fetcher

    def run(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        targets = self._selected_targets(params)
        checks = [self._check_target(name, target) for name, target in targets.items()]
        for check in checks:
            self._persist_check(check)
            self._sync_incident(check)

        warning_count = len(
            [check for check in checks if check.status in {"warning", "expired", "failed"}]
        )
        return {
            "status": "ok" if warning_count == 0 else "warning",
            "timestamp": utc_timestamp(),
            "warning_count": warning_count,
            "total_count": len(checks),
            "checks": [check.to_dict() for check in checks],
        }

    def _selected_targets(self, params: dict[str, Any]) -> dict[str, str]:
        target_name = str(params.get("target_name", "")).strip()
        if target_name:
            target = self.targets.get(target_name)
            return {target_name: target} if target else {}
        return dict(self.targets)

    def _check_target(self, name: str, target: str) -> SslCertificateCheck:
        host, port = self._parse_target(target)
        timestamp = utc_timestamp()
        try:
            certificate = self._fetch_certificate(host, port)
            expires_at = self._parse_expires_at(str(certificate.get("notAfter", "")))
            days_remaining = (expires_at - datetime.now(UTC)).days
            issuer = self._parse_issuer(certificate.get("issuer", ()))
            if days_remaining < 0:
                status = "expired"
            elif days_remaining <= self.warning_days:
                status = "warning"
            else:
                status = "ok"
            return SslCertificateCheck(
                name=name,
                target=target,
                host=host,
                port=port,
                timestamp=timestamp,
                status=status,
                valid=status == "ok",
                issuer=issuer,
                expires_at=expires_at.isoformat().replace("+00:00", "Z"),
                days_remaining=days_remaining,
                warning_days=self.warning_days,
                error="",
            )
        except Exception as exc:
            return SslCertificateCheck(
                name=name,
                target=target,
                host=host,
                port=port,
                timestamp=timestamp,
                status="failed",
                valid=False,
                issuer="",
                expires_at=None,
                days_remaining=None,
                warning_days=self.warning_days,
                error=str(exc),
            )

    def _fetch_certificate(self, host: str, port: int) -> dict[str, Any]:
        if self.certificate_fetcher is not None:
            return dict(self.certificate_fetcher(host, port, self.timeout_seconds))

        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=self.timeout_seconds) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                return dict(tls_sock.getpeercert())

    @staticmethod
    def _parse_target(target: str) -> tuple[str, int]:
        if ":" not in target:
            return target, 443
        host, raw_port = target.rsplit(":", 1)
        return host, int(raw_port)

    @staticmethod
    def _parse_expires_at(value: str) -> datetime:
        return datetime.strptime(value, CERT_DATETIME_FORMAT).replace(tzinfo=UTC)

    @staticmethod
    def _parse_issuer(raw_issuer: Any) -> str:
        parts: list[str] = []
        for group in raw_issuer or ():
            for key, value in group:
                if key in {"commonName", "organizationName"}:
                    parts.append(str(value))
        return ", ".join(parts) if parts else "unknown"

    def _persist_check(self, check: SslCertificateCheck) -> None:
        if self.storage_repository is None:
            return
        self.storage_repository.save_ssl_check(check.to_dict())

    def _sync_incident(self, check: SslCertificateCheck) -> None:
        if self.incident_manager is None:
            return
        if check.status == "ok":
            self._resolve_ssl_incidents(check.name)
            return

        incident_type = (
            "ssl_certificate_check_failed"
            if check.status == "failed"
            else "ssl_certificate_expiring"
        )
        severity = "critical" if check.status in {"expired", "failed"} else "medium"
        if check.status == "failed":
            description = f"SSL certificate check failed for {check.name}: {check.error}"
        elif check.status == "expired":
            description = f"SSL certificate for {check.name} expired {-int(check.days_remaining or 0)} days ago"
        else:
            description = f"SSL certificate for {check.name} expires in {check.days_remaining} days"
        self.incident_manager.create_incident(
            severity=severity,
            service_name=check.name,
            incident_type=incident_type,
            description=description,
            health_check_results=[check.to_dict()],
        )

    def _resolve_ssl_incidents(self, service_name: str) -> None:
        for incident in self.incident_manager.get_active_incidents():
            if incident.service_name == service_name and incident.incident_type in {
                "ssl_certificate_expiring",
                "ssl_certificate_check_failed",
            }:
                self.incident_manager.resolve_incident(incident.incident_id)
