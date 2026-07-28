"""Runbook execution engine — runs runbook steps against tool registry."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.intelligence.runbooks.parser import RunbookDef, RunbookStep
from src.intelligence.tools import get_tool


@dataclass
class StepResult:
    step_name: str
    status: str
    duration_ms: float = 0.0
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class RunbookResult:
    runbook_name: str
    status: str
    step_results: list[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    error: str = ""
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "runbook_name": self.runbook_name,
            "status": self.status,
            "step_results": [s.to_dict() for s in self.step_results],
            "total_duration_ms": self.total_duration_ms,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class RunbookEngine:
    def __init__(self, repo: Any = None) -> None:
        self._repo = repo

    def _utc_now(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def execute(
        self,
        runbook: RunbookDef,
        incident_id: str | None = None,
        **kwargs: Any,
    ) -> RunbookResult:
        started_at = self._utc_now()
        start_time = time.time()
        step_results: list[StepResult] = []
        overall_status = "completed"

        steps_to_run: list[RunbookStep] = list(runbook.steps)

        # Handle parallel step groups
        if runbook.parallel_steps:
            for group in runbook.parallel_steps:
                group_names = set(group)
                group_steps = [s for s in steps_to_run if s.name in group_names]
                remaining = [s for s in steps_to_run if s.name not in group_names]

                parallel_results = []
                for step in group_steps:
                    step_start = time.time()
                    result = self._execute_step(step, incident_id=incident_id, **kwargs)
                    step_result = StepResult(
                        step_name=step.name,
                        status=result.get("status", "error")
                        if isinstance(result, dict)
                        else "error",
                        duration_ms=(time.time() - step_start) * 1000,
                        result=result if isinstance(result, dict) else {},
                        error=result.get("error", "") if isinstance(result, dict) else str(result),
                    )
                    step_result.duration_ms = (time.time() - step_start) * 1000
                    parallel_results.append(step_result)

                step_results.extend(parallel_results)
                steps_to_run = remaining

        # Execute remaining steps sequentially
        for step in steps_to_run:
            if step.name in {sr.step_name for sr in step_results}:
                continue

            if step.condition:
                if not self._evaluate_condition(step.condition, step_results):
                    step_results.append(
                        StepResult(step_name=step.name, status="skipped", error="Condition not met")
                    )
                    continue

            if step.requires_approval:
                step_results.append(
                    StepResult(
                        step_name=step.name,
                        status="pending_approval",
                        error="Awaiting human approval",
                    )
                )
                overall_status = "pending_approval"
                continue

            step_start = time.time()
            try:
                result = self._execute_step(step, incident_id=incident_id, **kwargs)
                elapsed = (time.time() - step_start) * 1000
                status = "ok" if result.get("status") == "ok" else "error"
                step_results.append(
                    StepResult(
                        step_name=step.name, status=status, duration_ms=elapsed, result=result
                    )
                )

                if status == "error" and step.on_failure == "stop":
                    overall_status = "failed"
                    break
                if status == "error" and step.on_failure == "continue":
                    continue
            except Exception as exc:
                elapsed = (time.time() - step_start) * 1000
                step_results.append(
                    StepResult(
                        step_name=step.name, status="error", duration_ms=elapsed, error=str(exc)
                    )
                )
                if step.on_failure == "stop":
                    overall_status = "failed"
                    break

        for sr in step_results:
            if sr.status == "error":
                overall_status = "completed_with_errors"
                break

        total_duration = (time.time() - start_time) * 1000
        return RunbookResult(
            runbook_name=runbook.name,
            status=overall_status,
            step_results=step_results,
            total_duration_ms=round(total_duration, 2),
            started_at=started_at,
            completed_at=self._utc_now(),
        )

    def _execute_step(self, step: RunbookStep, **kwargs: Any) -> dict[str, Any]:
        if step.action == "tool" and step.tool:
            tool = get_tool(step.tool)
            if tool is None:
                return {"status": "error", "error": f"Tool '{step.tool}' not found"}
            params = dict(step.params)
            params["repo"] = self._repo
            params.update(kwargs)
            return tool.execute(**params)

        if step.action == "wait":
            duration = int(step.params.get("seconds", 5))
            time.sleep(duration)
            return {"status": "ok", "waited_seconds": duration}

        if step.action == "notify":
            return {
                "status": "ok",
                "message": f"Notification: {step.params.get('message', step.description)}",
            }

        if step.action == "resolve_incident":
            inc_id = kwargs.get("incident_id") or step.params.get("incident_id", "")
            if inc_id and self._repo is not None:
                from src.incidents import IncidentManager

                im = IncidentManager("", storage_repository=self._repo)
                im.resolve_incident(
                    inc_id, "runbook", step.params.get("resolution_notes", "Resolved by runbook")
                )
                return {"status": "ok", "incident_id": inc_id, "resolved": True}
            return {
                "status": "ok",
                "incident_id": inc_id or "unknown",
                "resolved": False,
                "note": "No repo available",
            }

        if step.action == "create_incident":
            if self._repo is not None:
                from src.incidents import IncidentManager

                im = IncidentManager("", storage_repository=self._repo)
                inc = im.create_incident(
                    severity=step.params.get("severity", "medium"),
                    service_name=step.params.get("service", "unknown"),
                    incident_type=step.params.get("type", "automated"),
                    description=step.params.get("description", ""),
                )
                return {"status": "ok", "incident": inc.to_dict() if inc else {"id": "unknown"}}
            return {"status": "error", "error": "No repo available"}

        return {"status": "error", "error": f"Unknown action: {step.action}"}

    def _evaluate_condition(self, condition: str, results: list[StepResult]) -> bool:
        cond = condition.strip().lower()
        if cond.startswith("step:"):
            parts = cond.split(":")
            if len(parts) >= 3:
                step_name = parts[1]
                expected = parts[2]
                for r in results:
                    if r.step_name == step_name:
                        return r.status == expected
        return True
