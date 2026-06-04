"""Persistent incident management for AegisNex operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.notifications.base import NotificationProvider, NotificationResult


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class Incident:
    incident_id: str
    timestamp: str
    severity: str
    service_name: str
    incident_type: str
    description: str
    health_check_results: List[Dict[str, Any]]
    remediation_attempted: bool
    remediation_successful: bool
    status: str
    resolved_timestamp: Optional[str]

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Incident":
        return cls(
            incident_id=str(payload["incident_id"]),
            timestamp=str(payload["timestamp"]),
            severity=str(payload["severity"]),
            service_name=str(payload["service_name"]),
            incident_type=str(payload["incident_type"]),
            description=str(payload["description"]),
            health_check_results=list(payload.get("health_check_results", [])),
            remediation_attempted=bool(payload.get("remediation_attempted", False)),
            remediation_successful=bool(payload.get("remediation_successful", False)),
            status=str(payload.get("status", "active")),
            resolved_timestamp=payload.get("resolved_timestamp"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IncidentManager:
    def __init__(
        self,
        history_path: str | Path = "incident_history.json",
        notification_providers: Optional[List[NotificationProvider]] = None,
        notification_history_path: str | Path = "notification_history.json",
        storage_repository: Any | None = None,
    ) -> None:
        self.history_path = Path(history_path)
        self.notification_history_path = Path(notification_history_path)
        self.notification_providers = notification_providers or []
        self.storage_repository = storage_repository
        self.incidents: List[Incident] = self._load_incidents()
        self.notification_events: List[Dict[str, Any]] = self._load_notification_events()

    def create_incident(
        self,
        severity: str,
        service_name: str,
        incident_type: str,
        description: str,
        health_check_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Incident:
        existing = self._find_active(service_name, incident_type)
        if existing:
            existing.severity = severity
            existing.description = description
            existing.health_check_results = health_check_results or []
            self._save_incidents()
            return existing

        incident = Incident(
            incident_id=str(uuid4()),
            timestamp=utc_timestamp(),
            severity=severity,
            service_name=service_name,
            incident_type=incident_type,
            description=description,
            health_check_results=health_check_results or [],
            remediation_attempted=False,
            remediation_successful=False,
            status="active",
            resolved_timestamp=None,
        )
        self.incidents.append(incident)
        self._save_incidents()
        self._save_incident_to_storage(incident)
        self._notify_created(incident)
        return incident

    def update_incident(self, incident_id: str, **updates: Any) -> Incident:
        incident = self._get_required(incident_id)
        allowed_fields = {
            "severity",
            "description",
            "health_check_results",
            "remediation_attempted",
            "remediation_successful",
            "status",
            "resolved_timestamp",
        }
        for key, value in updates.items():
            if key in allowed_fields:
                setattr(incident, key, value)
        self._save_incidents()
        self._save_incident_to_storage(incident)
        return incident

    def resolve_incident(self, incident_id: str) -> Incident:
        incident = self._get_required(incident_id)
        incident.status = "resolved"
        incident.resolved_timestamp = utc_timestamp()
        self._save_incidents()
        self._save_incident_to_storage(incident)
        self._notify_resolved(incident)
        return incident

    def resolve_service_incidents(self, service_name: str) -> List[Incident]:
        resolved: List[Incident] = []
        for incident in self.get_active_incidents():
            if incident.service_name == service_name:
                incident.status = "resolved"
                incident.resolved_timestamp = utc_timestamp()
                resolved.append(incident)
        if resolved:
            self._save_incidents()
            for incident in resolved:
                self._save_incident_to_storage(incident)
                self._notify_resolved(incident)
        return resolved

    def list_incidents(self) -> List[Incident]:
        return list(self.incidents)

    def get_active_incidents(self) -> List[Incident]:
        return [incident for incident in self.incidents if incident.status == "active"]

    def list_notification_events(self) -> List[Dict[str, Any]]:
        return list(self.notification_events)

    def _find_active(self, service_name: str, incident_type: str) -> Optional[Incident]:
        for incident in self.get_active_incidents():
            if (
                incident.service_name == service_name
                and incident.incident_type == incident_type
            ):
                return incident
        return None

    def _get_required(self, incident_id: str) -> Incident:
        for incident in self.incidents:
            if incident.incident_id == incident_id:
                return incident
        raise KeyError(f"Unknown incident: {incident_id}")

    def _load_incidents(self) -> List[Incident]:
        if not self.history_path.exists():
            return []
        try:
            payload = json.loads(self.history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        incidents: List[Incident] = []
        for item in payload:
            if isinstance(item, dict):
                try:
                    incidents.append(Incident.from_dict(item))
                except KeyError:
                    continue
        return incidents

    def _save_incidents(self) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(
            json.dumps(
                [incident.to_dict() for incident in self.incidents],
                indent=2,
            ),
            encoding="utf-8",
        )

    def _save_incident_to_storage(self, incident: Incident) -> None:
        if self.storage_repository:
            self.storage_repository.save_incident(incident)

    def _notify_created(self, incident: Incident) -> List[NotificationResult]:
        results = [
            provider.notify_incident_created(incident)
            for provider in self.notification_providers
        ]
        self._record_notification_results("incident_created", incident, results)
        return results

    def _notify_resolved(self, incident: Incident) -> List[NotificationResult]:
        results = [
            provider.notify_incident_resolved(incident)
            for provider in self.notification_providers
        ]
        self._record_notification_results("incident_resolved", incident, results)
        return results

    def _record_notification_results(
        self,
        event_type: str,
        incident: Incident,
        results: List[NotificationResult],
    ) -> None:
        if not results:
            return
        for result in results:
            event = {
                "timestamp": utc_timestamp(),
                "event_type": event_type,
                "incident_id": incident.incident_id,
                "service_name": incident.service_name,
                "provider": result.provider,
                "status": result.status,
                "attempts": result.attempts,
                "message": result.message,
            }
            self.notification_events.append(event)
            if self.storage_repository:
                self.storage_repository.save_notification_event(event)
        self._save_notification_events()

    def _load_notification_events(self) -> List[Dict[str, Any]]:
        if not self.notification_history_path.exists():
            return []
        try:
            payload = json.loads(
                self.notification_history_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        return [event for event in payload if isinstance(event, dict)]

    def _save_notification_events(self) -> None:
        self.notification_history_path.parent.mkdir(parents=True, exist_ok=True)
        self.notification_history_path.write_text(
            json.dumps(self.notification_events, indent=2),
            encoding="utf-8",
        )
