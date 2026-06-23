"""HTTP endpoint monitoring for AegisNex."""

from __future__ import annotations

from dataclasses import dataclass
from http.client import HTTPResponse
from time import perf_counter
from typing import Any, Dict, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.incidents import IncidentManager, utc_timestamp


@dataclass(frozen=True)
class HttpEndpointCheck:
    name: str
    url: str
    timestamp: str
    status: str
    available: bool
    expected_status: int
    status_code: int | None
    latency_ms: float | None
    error: str
    availability_percent: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "timestamp": self.timestamp,
            "status": self.status,
            "available": self.available,
            "expected_status": self.expected_status,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "availability_percent": self.availability_percent,
        }


class HttpEndpointMonitor:
    """Check configured HTTP URLs and generate incidents for failures."""

    def __init__(
        self,
        endpoints: Mapping[str, str],
        timeout_seconds: int = 5,
        expected_status: int = 200,
        incident_manager: IncidentManager | None = None,
        storage_repository: Any | None = None,
        client: Any | None = None,
        availability_window: int = 100,
    ) -> None:
        self.endpoints = dict(endpoints)
        self.timeout_seconds = timeout_seconds
        self.expected_status = expected_status
        self.incident_manager = incident_manager
        self.storage_repository = storage_repository
        self.client = client
        self.availability_window = max(1, availability_window)

    def run(self, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        params = params or {}
        endpoints = self._selected_endpoints(params)
        checks = [self._check_endpoint(name, url) for name, url in endpoints.items()]
        for check in checks:
            self._persist_check(check)
            self._sync_incident(check)

        checks = [self._with_availability(check) for check in checks]
        available_count = len([check for check in checks if check.available])
        total = len(checks)
        availability = round((available_count / total) * 100, 2) if total else 100.0
        return {
            "status": "ok" if available_count == total else "warning",
            "timestamp": utc_timestamp(),
            "availability_percent": availability,
            "available_count": available_count,
            "total_count": total,
            "checks": [check.to_dict() for check in checks],
        }

    def _selected_endpoints(self, params: Dict[str, Any]) -> Dict[str, str]:
        endpoint_name = str(params.get("endpoint_name", "")).strip()
        if endpoint_name:
            endpoint = self.endpoints.get(endpoint_name)
            return {endpoint_name: endpoint} if endpoint else {}
        return dict(self.endpoints)

    def _check_endpoint(self, name: str, url: str) -> HttpEndpointCheck:
        started = perf_counter()
        timestamp = utc_timestamp()
        try:
            response = self._get(url)
            latency_ms = round((perf_counter() - started) * 1000, 2)
            status_code = int(response.status_code)
            available = 200 <= status_code <= 399
            return HttpEndpointCheck(
                name=name,
                url=url,
                timestamp=timestamp,
                status="ok" if available else "failed",
                available=available,
                expected_status=self.expected_status,
                status_code=status_code,
                latency_ms=latency_ms,
                error="" if available else f"HTTP status {status_code} outside healthy range 200-399",
                availability_percent=100.0 if available else 0.0,
            )
        except Exception as exc:
            latency_ms = round((perf_counter() - started) * 1000, 2)
            return HttpEndpointCheck(
                name=name,
                url=url,
                timestamp=timestamp,
                status="failed",
                available=False,
                expected_status=self.expected_status,
                status_code=None,
                latency_ms=latency_ms,
                error=str(exc),
                availability_percent=0.0,
            )

    def _get(self, url: str) -> Any:
        if self.client is not None:
            try:
                return self.client.get(
                    url,
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                    headers={"User-Agent": self._user_agent()},
                )
            except TypeError:
                return self.client.get(url, timeout=self.timeout_seconds)

        request = Request(url, headers={"User-Agent": self._user_agent()}, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return UrllibResponseAdapter(response)
        except HTTPError as exc:
            return UrllibErrorAdapter(exc)
        except URLError:
            raise

    @staticmethod
    def _user_agent() -> str:
        return "AegisNex-Monitor/1.0 (+https://aegisnex.local)"

    def _persist_check(self, check: HttpEndpointCheck) -> None:
        if self.storage_repository is None:
            return
        self.storage_repository.save_http_check(check.to_dict())

    def _sync_incident(self, check: HttpEndpointCheck) -> None:
        if self.incident_manager is None:
            return
        if check.available:
            self.incident_manager.resolve_service_incidents(check.name)
            return
        description = (
            f"HTTP endpoint {check.name} failed: "
            f"{check.error or 'unavailable'}"
        )
        self.incident_manager.create_incident(
            severity="high",
            service_name=check.name,
            incident_type="http_endpoint_failure",
            description=description,
            health_check_results=[check.to_dict()],
        )

    def _with_availability(self, check: HttpEndpointCheck) -> HttpEndpointCheck:
        availability = self._availability_for_endpoint(check.name)
        return HttpEndpointCheck(
            name=check.name,
            url=check.url,
            timestamp=check.timestamp,
            status=check.status,
            available=check.available,
            expected_status=check.expected_status,
            status_code=check.status_code,
            latency_ms=check.latency_ms,
            error=check.error,
            availability_percent=availability,
        )

    def _availability_for_endpoint(self, endpoint_name: str) -> float:
        if self.storage_repository is None:
            return 100.0
        try:
            rows = self.storage_repository.fetch_all("http_checks")
        except Exception:
            return 100.0
        endpoint_rows = [
            row
            for row in rows
            if str(row.get("endpoint_name", row.get("name", ""))) == endpoint_name
        ]
        endpoint_rows.sort(key=lambda row: str(row.get("timestamp", "")), reverse=True)
        recent_rows = endpoint_rows[: self.availability_window]
        if not recent_rows:
            return 100.0
        available = len([row for row in recent_rows if bool(row.get("available"))])
        return round((available / len(recent_rows)) * 100, 2)


class UrllibResponseAdapter:
    def __init__(self, response: HTTPResponse) -> None:
        self.status_code = int(response.status)


class UrllibErrorAdapter:
    def __init__(self, error: HTTPError) -> None:
        self.status_code = int(error.code)
