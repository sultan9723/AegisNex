"""Persistent incident management for AegisNex operations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.notifications.base import NotificationProvider, NotificationResult


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class Incident:
    incident_id: str
    timestamp: str
    severity: str
    service_name: str
    incident_type: str
    description: str
    health_check_results: list[dict[str, Any]]
    remediation_attempted: bool
    remediation_successful: bool
    status: str
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None
    resolved_by: str | None = None
    resolved_timestamp: str | None = None
    resolution_notes: str | None = None
    proposed_remediation: dict[str, Any] | None = None
    remediation_proposed_by: str | None = None
    remediation_proposed_at: str | None = None
    remediation_approval_status: str | None = None
    remediation_plan_confidence: float | None = None
    remediation_history: list[dict[str, Any]] | None = None
    org_id: int | None = None
    org_name: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Incident:
        status = str(payload.get("incident_status", payload.get("status", "active")))
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
            status=status,
            acknowledged_by=payload.get("acknowledged_by"),
            acknowledged_at=payload.get("acknowledged_at"),
            resolved_by=payload.get("resolved_by"),
            resolved_timestamp=payload.get("resolved_at", payload.get("resolved_timestamp")),
            resolution_notes=payload.get("resolution_notes"),
            proposed_remediation=payload.get("proposed_remediation"),
            remediation_proposed_by=payload.get("remediation_proposed_by"),
            remediation_proposed_at=payload.get("remediation_proposed_at"),
            remediation_approval_status=payload.get("remediation_approval_status"),
            remediation_plan_confidence=payload.get("remediation_plan_confidence"),
            remediation_history=payload.get("remediation_history"),
            org_id=payload.get("org_id"),
            org_name=payload.get("org_name"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["incident_status"] = self.status
        payload["resolved_at"] = self.resolved_timestamp
        return payload

    @property
    def incident_status(self) -> str:
        return self.status

    @incident_status.setter
    def incident_status(self, value: str) -> None:
        self.status = value

    @property
    def resolved_at(self) -> str | None:
        return self.resolved_timestamp

    @resolved_at.setter
    def resolved_at(self, value: str | None) -> None:
        self.resolved_timestamp = value


class IncidentManager:
    def __init__(
        self,
        history_path: str | Path = "incident_history.json",
        notification_providers: list[NotificationProvider] | None = None,
        notification_history_path: str | Path = "notification_history.json",
        storage_repository: Any | None = None,
        broadcast_callback: Any | None = None,
    ) -> None:
        self.history_path = Path(history_path)
        self.notification_history_path = Path(notification_history_path)
        self.notification_providers = notification_providers or []
        self.storage_repository = storage_repository
        self.broadcast_callback = broadcast_callback
        self.incidents: list[Incident] = self._load_incidents()
        self.notification_events: list[dict[str, Any]] = self._load_notification_events()

    def create_incident(
        self,
        severity: str,
        service_name: str,
        incident_type: str,
        description: str,
        health_check_results: list[dict[str, Any]] | None = None,
    ) -> Incident:
        existing = self._find_active(service_name, incident_type)
        if existing:
            existing.severity = severity
            existing.description = description
            existing.health_check_results = health_check_results or []
            self._save_incidents()
            self._save_incident_to_storage(existing)
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
            acknowledged_by=None,
            acknowledged_at=None,
            resolved_by=None,
            resolved_timestamp=None,
            resolution_notes=None,
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
            "acknowledged_by",
            "acknowledged_at",
            "resolved_by",
            "resolved_timestamp",
            "resolution_notes",
            "proposed_remediation",
            "remediation_proposed_by",
            "remediation_proposed_at",
            "remediation_approval_status",
            "remediation_plan_confidence",
            "remediation_history",
            "org_id",
            "org_name",
        }
        for key, value in updates.items():
            if key in allowed_fields:
                setattr(incident, key, value)
        self._save_incidents()
        self._save_incident_to_storage(incident)
        return incident

    def acknowledge_incident(self, incident_id: str, actor: str = "system") -> Incident:
        incident = self._get_required(incident_id)
        previous_status = incident.status
        incident.status = "acknowledged"
        incident.acknowledged_by = actor
        incident.acknowledged_at = utc_timestamp()
        incident.resolved_by = None
        incident.resolved_timestamp = None
        self._save_incidents()
        self._save_incident_to_storage(incident)
        self._record_transition(
            incident, previous_status, incident.status, actor, {"reason": "acknowledged"}
        )
        return incident

    def resolve_incident(
        self,
        incident_id: str,
        actor: str = "system",
        resolution_notes: str | None = None,
    ) -> Incident:
        incident = self._get_required(incident_id)
        previous_status = incident.status
        incident.status = "resolved"
        incident.resolved_by = actor
        incident.resolved_timestamp = utc_timestamp()
        incident.resolution_notes = resolution_notes
        self._save_incidents()
        self._save_incident_to_storage(incident)
        self._record_transition(
            incident,
            previous_status,
            incident.status,
            actor,
            {"reason": "resolved", "resolution_notes": resolution_notes},
        )
        self._notify_resolved(incident)
        return incident

    def reopen_incident(self, incident_id: str, actor: str = "system") -> Incident:
        incident = self._get_required(incident_id)
        previous_status = incident.status
        incident.status = "active"
        incident.acknowledged_by = None
        incident.acknowledged_at = None
        incident.resolved_by = None
        incident.resolved_timestamp = None
        incident.resolution_notes = None
        self._save_incidents()
        self._save_incident_to_storage(incident)
        self._record_transition(
            incident, previous_status, incident.status, actor, {"reason": "reopened"}
        )
        return incident

    def propose_remediation(
        self,
        incident_id: str,
        proposed_by: str,
        remediation_plan: dict[str, Any],
        confidence: float = 0.0,
    ) -> Incident:
        incident = self._get_required(incident_id)
        if incident.remediation_history is None:
            incident.remediation_history = []
        if incident.proposed_remediation:
            incident.remediation_history.append(
                {
                    "plan": incident.proposed_remediation,
                    "proposed_by": incident.remediation_proposed_by,
                    "proposed_at": incident.remediation_proposed_at,
                    "approval_status": incident.remediation_approval_status,
                    "outcome": "superseded",
                }
            )
        incident.proposed_remediation = remediation_plan
        incident.remediation_proposed_by = proposed_by
        incident.remediation_proposed_at = utc_timestamp()
        incident.remediation_approval_status = "pending"
        incident.remediation_plan_confidence = confidence
        self._save_incidents()
        self._save_incident_to_storage(incident)
        self._record_transition(
            incident,
            incident.status,
            incident.status,
            proposed_by,
            {"reason": "remediation_proposed", "confidence": confidence},
        )
        if self.broadcast_callback:
            try:
                import asyncio

                asyncio.ensure_future(
                    self.broadcast_callback("remediation_proposed", incident.to_dict())
                )
            except Exception:
                pass
        return incident

    def approve_remediation(self, incident_id: str, actor: str = "system") -> Incident:
        incident = self._get_required(incident_id)
        if incident.remediation_approval_status != "pending":
            raise ValueError(
                f"Cannot approve remediation with status: {incident.remediation_approval_status}"
            )
        incident.remediation_approval_status = "approved"
        self._save_incidents()
        self._save_incident_to_storage(incident)
        self._record_transition(
            incident,
            incident.status,
            incident.status,
            actor,
            {"reason": "remediation_approved"},
        )
        if self.broadcast_callback:
            try:
                import asyncio

                asyncio.ensure_future(
                    self.broadcast_callback("remediation_approved", incident.to_dict())
                )
            except Exception:
                pass
        return incident

    def reject_remediation(
        self, incident_id: str, actor: str = "system", reason: str = ""
    ) -> Incident:
        incident = self._get_required(incident_id)
        if incident.remediation_approval_status != "pending":
            raise ValueError(
                f"Cannot reject remediation with status: {incident.remediation_approval_status}"
            )
        if incident.remediation_history is None:
            incident.remediation_history = []
        incident.remediation_history.append(
            {
                "plan": incident.proposed_remediation,
                "proposed_by": incident.remediation_proposed_by,
                "proposed_at": incident.remediation_proposed_at,
                "approval_status": "rejected",
                "rejected_by": actor,
                "rejected_at": utc_timestamp(),
                "rejection_reason": reason,
            }
        )
        incident.proposed_remediation = None
        incident.remediation_proposed_by = None
        incident.remediation_proposed_at = None
        incident.remediation_approval_status = "rejected"
        incident.remediation_plan_confidence = None
        self._save_incidents()
        self._save_incident_to_storage(incident)
        self._record_transition(
            incident,
            incident.status,
            incident.status,
            actor,
            {"reason": "remediation_rejected", "rejection_reason": reason},
        )
        if self.broadcast_callback:
            try:
                import asyncio

                asyncio.ensure_future(
                    self.broadcast_callback("remediation_rejected", incident.to_dict())
                )
            except Exception:
                pass
        return incident

    def mark_remediation_executed(
        self,
        incident_id: str,
        successful: bool,
        details: dict[str, Any] | None = None,
    ) -> Incident:
        incident = self._get_required(incident_id)
        incident.remediation_attempted = True
        incident.remediation_successful = successful
        if incident.remediation_history is None:
            incident.remediation_history = []
        incident.remediation_history.append(
            {
                "plan": incident.proposed_remediation,
                "proposed_by": incident.remediation_proposed_by,
                "proposed_at": incident.remediation_proposed_at,
                "approval_status": "executed",
                "executed_at": utc_timestamp(),
                "successful": successful,
                "details": details or {},
            }
        )
        incident.proposed_remediation = None
        incident.remediation_proposed_by = None
        incident.remediation_proposed_at = None
        incident.remediation_approval_status = "executed"
        incident.remediation_plan_confidence = None
        self._save_incidents()
        self._save_incident_to_storage(incident)
        if self.broadcast_callback:
            try:
                import asyncio

                asyncio.ensure_future(
                    self.broadcast_callback("remediation_executed", incident.to_dict())
                )
            except Exception:
                pass
        return incident

    def delete_incident(self, incident_id: str) -> None:
        incident = self._get_required(incident_id)
        self.incidents.remove(incident)
        self._save_incidents()
        if self.storage_repository and hasattr(self.storage_repository, "delete_incident"):
            self.storage_repository.delete_incident(incident_id)

    def resolve_service_incidents(
        self,
        service_name: str,
        actor: str = "system",
        resolution_notes: str | None = None,
    ) -> list[Incident]:
        resolved: list[Incident] = []
        for incident in self.get_active_incidents():
            if incident.service_name == service_name:
                resolved.append(
                    self.resolve_incident(
                        incident.incident_id,
                        actor=actor,
                        resolution_notes=resolution_notes,
                    )
                )
        return resolved

    def list_incidents(self) -> list[Incident]:
        return list(self.incidents)

    def get_active_incidents(self) -> list[Incident]:
        return [
            incident for incident in self.incidents if incident.status in {"active", "acknowledged"}
        ]

    def list_notification_events(self) -> list[dict[str, Any]]:
        return list(self.notification_events)

    def _find_active(self, service_name: str, incident_type: str) -> Incident | None:
        for incident in self.get_active_incidents():
            if incident.service_name == service_name and incident.incident_type == incident_type:
                return incident
        return None

    def _get_required(self, incident_id: str) -> Incident:
        for incident in self.incidents:
            if incident.incident_id == incident_id:
                return incident
        raise KeyError(f"Unknown incident: {incident_id}")

    def _record_transition(
        self,
        incident: Incident,
        from_status: str | None,
        to_status: str,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not self.storage_repository:
            return
        if hasattr(self.storage_repository, "record_incident_transition"):
            self.storage_repository.record_incident_transition(
                incident.incident_id,
                from_status,
                to_status,
                actor,
                details or {},
            )
        if hasattr(self.storage_repository, "record_audit_log"):
            self.storage_repository.record_audit_log(
                actor,
                f"incident.{to_status}",
                "incident",
                incident.incident_id,
                {
                    "service_name": incident.service_name,
                    "incident_type": incident.incident_type,
                    **(details or {}),
                },
            )

    def _load_incidents(self) -> list[Incident]:
        if not self.history_path.exists():
            return []
        try:
            payload = json.loads(self.history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        incidents: list[Incident] = []
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

    def _notify_created(self, incident: Incident) -> list[NotificationResult]:
        results = [
            provider.notify_incident_created(incident) for provider in self.notification_providers
        ]
        self._record_notification_results("incident_created", incident, results)
        if self.broadcast_callback:
            try:
                import asyncio

                asyncio.ensure_future(
                    self.broadcast_callback("incident_created", incident.to_dict())
                )
            except Exception:
                pass
        return results

    def _notify_resolved(self, incident: Incident) -> list[NotificationResult]:
        results = [
            provider.notify_incident_resolved(incident) for provider in self.notification_providers
        ]
        self._record_notification_results("incident_resolved", incident, results)
        if self.broadcast_callback:
            try:
                import asyncio

                asyncio.ensure_future(
                    self.broadcast_callback("incident_resolved", incident.to_dict())
                )
            except Exception:
                pass
        return results

    def _record_notification_results(
        self,
        event_type: str,
        incident: Incident,
        results: list[NotificationResult],
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

    def _load_notification_events(self) -> list[dict[str, Any]]:
        if not self.notification_history_path.exists():
            return []
        try:
            payload = json.loads(self.notification_history_path.read_text(encoding="utf-8"))
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
