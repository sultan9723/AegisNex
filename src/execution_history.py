"""Permanent execution timeline for autonomous operations.

Records every step of the autonomous pipeline: planner decisions, agent
assignments, tool calls, evidence collected, approvals, verification, and
remediation actions. Provides query and export capabilities.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

_logger = logging.getLogger(__name__)


class ExecutionStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    APPROVAL_PENDING = "approval_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


@dataclass
class ExecutionStep:
    step_id: str
    step_type: str
    name: str
    status: str
    started_at: str
    completed_at: str | None = None
    agent: str | None = None
    tool: str | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ExecutionRecord:
    execution_id: str
    incident_id: str | None
    trigger: str
    status: str
    started_at: str
    completed_at: str | None = None
    steps: list[ExecutionStep] = field(default_factory=list)
    planner: dict[str, Any] | None = None
    agents: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    root_cause: str | None = None
    remediation_plan: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    explanation: dict[str, Any] | None = None
    error: str | None = None
    rollback: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "incident_id": self.incident_id,
            "trigger": self.trigger,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "steps": [s.to_dict() for s in self.steps],
            "planner": self.planner,
            "agents": self.agents,
            "evidence": self.evidence,
            "decisions": self.decisions,
            "approvals": self.approvals,
            "root_cause": self.root_cause,
            "remediation_plan": self.remediation_plan,
            "verification": self.verification,
            "explanation": self.explanation,
            "error": self.error,
            "rollback": self.rollback,
        }


class ExecutionHistory:
    """Persistent timeline of all autonomous operations."""

    def __init__(
        self,
        history_path: str | Path = "execution_history.json",
        repository: Any = None,
    ) -> None:
        self.history_path = Path(history_path)
        self._repository = repository
        self._records: list[ExecutionRecord] = []
        self._active: ExecutionRecord | None = None
        self._load()

    # ---- Lifecycle ----

    def start_execution(
        self,
        trigger: str,
        incident_id: str | None = None,
    ) -> str:
        record = ExecutionRecord(
            execution_id=str(uuid4()),
            incident_id=incident_id,
            trigger=trigger,
            status=ExecutionStatus.RUNNING,
            started_at=_utc_now(),
        )
        self._records.append(record)
        self._active = record
        self._save()
        return record.execution_id

    def complete_execution(self, status: str = ExecutionStatus.COMPLETED) -> None:
        if self._active:
            self._active.status = status
            self._active.completed_at = _utc_now()
            self._persist()
            self._active = None
            self._save()

    def fail_execution(self, error: str) -> None:
        if self._active:
            self._active.status = ExecutionStatus.FAILED
            self._active.error = error
            self._active.completed_at = _utc_now()
            self._persist()
            self._active = None
            self._save()

    # ---- Steps ----

    def add_step(
        self,
        step_type: str,
        name: str,
        input: dict[str, Any] | None = None,
    ) -> str:
        step = ExecutionStep(
            step_id=str(uuid4()),
            step_type=step_type,
            name=name,
            status=ExecutionStatus.RUNNING,
            started_at=_utc_now(),
            input=input,
        )
        if self._active:
            self._active.steps.append(step)
            self._save()
        return step.step_id

    def complete_step(
        self,
        step_id: str,
        output: dict[str, Any] | None = None,
        agent: str | None = None,
        tool: str | None = None,
    ) -> None:
        if not self._active:
            return
        for step in self._active.steps:
            if step.step_id == step_id:
                step.status = ExecutionStatus.COMPLETED
                step.completed_at = _utc_now()
                step.output = output
                step.agent = agent
                step.tool = tool
                if step.started_at:
                    started = _parse_iso(step.started_at)
                    completed = _parse_iso(step.completed_at)
                    if started and completed:
                        step.duration_ms = (completed - started).total_seconds() * 1000
                break
        self._save()

    def fail_step(self, step_id: str, error: str) -> None:
        if not self._active:
            return
        for step in self._active.steps:
            if step.step_id == step_id:
                step.status = ExecutionStatus.FAILED
                step.error = error
                step.completed_at = _utc_now()
                break
        self._save()

    # ---- Metadata ----

    def set_planner(self, planner_data: dict[str, Any]) -> None:
        if self._active:
            self._active.planner = planner_data
            self._save()

    def add_agent(self, agent_data: dict[str, Any]) -> None:
        if self._active:
            self._active.agents.append(agent_data)
            self._save()

    def add_evidence(self, evidence: dict[str, Any]) -> None:
        if self._active:
            self._active.evidence.append(evidence)
            self._save()

    def add_decision(self, decision: dict[str, Any]) -> None:
        if self._active:
            self._active.decisions.append(decision)
            self._save()

    def add_approval(self, approval: dict[str, Any]) -> None:
        if self._active:
            self._active.approvals.append(approval)
            self._save()

    def set_root_cause(self, root_cause: str) -> None:
        if self._active:
            self._active.root_cause = root_cause
            self._save()

    def set_remediation_plan(self, plan: dict[str, Any]) -> None:
        if self._active:
            self._active.remediation_plan = plan
            self._save()

    def set_verification(self, verification: dict[str, Any]) -> None:
        if self._active:
            self._active.verification = verification
            self._save()

    def set_explanation(self, explanation: dict[str, Any]) -> None:
        if self._active:
            self._active.explanation = explanation
            self._save()

    def set_rollback(self, rollback: dict[str, Any]) -> None:
        if self._active:
            self._active.rollback = rollback
            self._save()

    def set_remediation_plan_from_dict(self, plan: dict[str, Any] | None) -> None:
        self.set_remediation_plan(plan)

    def set_verification_from_dict(self, verification: dict[str, Any] | None) -> None:
        self.set_verification(verification)

    # ---- Query ----

    def get_active(self) -> ExecutionRecord | None:
        return self._active

    def get_record(self, execution_id: str) -> ExecutionRecord | None:
        for record in self._records:
            if record.execution_id == execution_id:
                return record
        return None

    def get_records(
        self,
        limit: int = 50,
        status: str | None = None,
        incident_id: str | None = None,
    ) -> list[dict[str, Any]]:
        results = list(self._records)
        if status:
            results = [r for r in results if r.status == status]
        if incident_id:
            results = [r for r in results if r.incident_id == incident_id]
        results.sort(key=lambda r: r.started_at, reverse=True)
        return [r.to_dict() for r in results[:limit]]

    def get_stats(self) -> dict[str, Any]:
        total = len(self._records)
        completed = sum(1 for r in self._records if r.status == ExecutionStatus.COMPLETED)
        failed = sum(1 for r in self._records if r.status == ExecutionStatus.FAILED)
        pending = sum(1 for r in self._records if r.status == ExecutionStatus.RUNNING)
        return {
            "total_executions": total,
            "completed": completed,
            "failed": failed,
            "running": pending,
            "success_rate": round(completed / total * 100, 1) if total > 0 else 0.0,
        }

    # ---- Persistence ----

    def _persist(self) -> None:
        if not self._active or not self._repository:
            return
        try:
            if hasattr(self._repository, "save_execution_record"):
                self._repository.save_execution_record(self._active.to_dict())
            if hasattr(self._repository, "record_audit_log"):
                self._repository.record_audit_log(
                    "system",
                    "execution",
                    "autonomous",
                    self._active.execution_id,
                    {"trigger": self._active.trigger, "status": self._active.status},
                )
        except Exception:
            _logger.exception("Failed to persist execution record")

    def _load(self) -> None:
        if not self.history_path.exists():
            return
        try:
            data = json.loads(self.history_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    self._records.append(_record_from_dict(item))
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning("Failed to load execution history: %s", exc)

    def _save(self) -> None:
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            self.history_path.write_text(
                json.dumps([r.to_dict() for r in self._records], indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            _logger.exception("Failed to save execution history: %s", exc)


def _record_from_dict(data: dict[str, Any]) -> ExecutionRecord:
    steps = []
    for s in data.get("steps", []):
        steps.append(
            ExecutionStep(**{k: v for k, v in s.items() if k in ExecutionStep.__dataclass_fields__})
        )
    allowed = set(ExecutionRecord.__dataclass_fields__)
    kwargs = {k: v for k, v in data.items() if k in allowed}
    kwargs["steps"] = steps
    return ExecutionRecord(**kwargs)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
