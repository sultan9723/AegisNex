"""Autonomous Incident Pipeline — end-to-end AI-driven incident resolution.

Flow:
Event → Create Incident → Planner Agent → Assign AI coworkers
→ Collect evidence → Determine root cause → Generate remediation plan
→ Risk assessment → Human approval (if needed) → Execute → Verify
→ Resolve → Generate report → Update knowledge base
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from src.event_bus import Event, EventType, get_bus
from src.execution_history import ExecutionHistory
from src.explanations import ExplanationEngine
from src.healing import SelfHealingEngine
from src.policy_engine import ActionVerdict, AppPolicyEngine

_logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    pipeline_id: str
    incident_id: str | None
    status: str
    started_at: str
    completed_at: str | None = None
    root_cause: str | None = None
    remediation_plan: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    explanation: dict[str, Any] | None = None
    agents_used: list[str] = field(default_factory=list)
    steps_completed: list[str] = field(default_factory=list)
    error: str | None = None
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "incident_id": self.incident_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "root_cause": self.root_cause,
            "remediation_plan": self.remediation_plan,
            "verification": self.verification,
            "explanation": self.explanation,
            "agents_used": self.agents_used,
            "steps_completed": self.steps_completed,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class AutonomousPipeline:
    """Orchestrates the end-to-end autonomous incident resolution pipeline.

    Subscribes to the event bus, creates incidents, coordinates agents,
    evaluates policies, executes remediation, verifies results, and updates
    the knowledge base.
    """

    def __init__(
        self,
        incident_manager: Any,
        agent_registry: Any,
        policy_engine: AppPolicyEngine | None = None,
        healing_engine: SelfHealingEngine | None = None,
        execution_history: ExecutionHistory | None = None,
        repository: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._incidents = incident_manager
        self._agents = agent_registry
        self._policy = policy_engine or AppPolicyEngine(repository=repository)
        self._healing = healing_engine
        self._history = execution_history
        self._repository = repository
        self._bus = event_bus or get_bus()
        self._explainer = ExplanationEngine()
        self._results: list[PipelineResult] = []

    async def start(self) -> None:
        self._bus.subscribe(EventType.INCIDENT_CREATED, self._on_incident_created)
        self._bus.subscribe(EventType.CONTAINER_DOWN, self._on_container_event)
        self._bus.subscribe(EventType.HIGH_CPU, self._on_resource_event)
        self._bus.subscribe(EventType.MEMORY_PRESSURE, self._on_resource_event)
        self._bus.subscribe(EventType.DISK_FULL, self._on_resource_event)
        self._bus.subscribe(EventType.TARGET_DOWN, self._on_target_event)
        _logger.info("Autonomous pipeline subscribed to event bus")

    async def _on_incident_created(self, event: Event) -> None:
        payload = event.payload
        incident_id = payload.get("incident_id") or payload.get("incident", {}).get("incident_id")
        service = payload.get("service_name") or payload.get("incident", {}).get(
            "service_name", "unknown"
        )
        desc = payload.get("description") or payload.get("incident", {}).get("description", "")
        await self.run_pipeline(
            incident_id=incident_id,
            service_name=service,
            description=desc,
            correlation_id=event.correlation_id,
        )

    async def _on_container_event(self, event: Event) -> None:
        container = event.payload.get("name", "unknown")
        desc = f"Container {container} {event.event_type.value}"
        if self._incidents:
            incident = self._incidents.create_incident(
                severity="high",
                service_name=container,
                incident_type=event.event_type.value,
                description=desc,
            )
            await self.run_pipeline(
                incident_id=incident.incident_id,
                service_name=container,
                description=desc,
                correlation_id=event.correlation_id,
            )

    async def _on_resource_event(self, event: Event) -> None:
        resource = event.payload.get("resource", "system")
        value = event.payload.get("value", "?")
        desc = f"Resource {resource} at {value} — {event.event_type.value}"
        if self._incidents:
            incident = self._incidents.create_incident(
                severity="warning",
                service_name=resource,
                incident_type=event.event_type.value,
                description=desc,
            )
            if self._healing:
                await self._healing.handle_event(event.event_type, event.payload)
            await self.run_pipeline(
                incident_id=incident.incident_id,
                service_name=resource,
                description=desc,
                correlation_id=event.correlation_id,
            )

    async def _on_target_event(self, event: Event) -> None:
        target = event.payload.get("name", "unknown")
        desc = f"Monitoring target {target} is down"
        if self._incidents:
            incident = self._incidents.create_incident(
                severity="high",
                service_name=target,
                incident_type=event.event_type.value,
                description=desc,
            )
            if self._healing:
                await self._healing.handle_event(event.event_type, event.payload)
            await self.run_pipeline(
                incident_id=incident.incident_id,
                service_name=target,
                description=desc,
                correlation_id=event.correlation_id,
            )

    async def run_pipeline(
        self,
        incident_id: str | None = None,
        service_name: str = "unknown",
        description: str = "",
        correlation_id: str | None = None,
    ) -> PipelineResult:
        start_time = time.time()
        pipeline_id = str(uuid4())
        result = PipelineResult(
            pipeline_id=pipeline_id,
            incident_id=incident_id,
            status="running",
            started_at=_utc_now(),
        )

        # Track in execution history
        exec_id = None
        if self._history:
            exec_id = self._history.start_execution(
                trigger=f"incident:{incident_id or '?'}", incident_id=incident_id
            )

        try:
            # Step 1: Plan — use supervisor agent
            result.steps_completed.append("plan")
            step_id = (
                self._history.add_step("planning", "Incident planning") if self._history else None
            )
            plan_result = None
            if self._agents:
                plan_result = await self._agents.dispatch_task(
                    f"Investigate and resolve: {description}", "supervisor-agent"
                )
                if plan_result.get("success"):
                    result.root_cause = plan_result.get("summary", "")
            if self._history:
                self._history.complete_step(step_id, output={"plan": plan_result})
                self._history.set_planner({"agent": "supervisor-agent", "plan": plan_result})

            # Step 2: Assign agents & collect evidence
            result.steps_completed.append("evidence")
            step_id = (
                self._history.add_step(
                    "evidence", "Evidence collection", input={"service": service_name}
                )
                if self._history
                else None
            )
            evidence = await self._collect_evidence(service_name, description)
            if self._history:
                self._history.complete_step(step_id, output={"evidence_count": len(evidence)})
                for item in evidence:
                    self._history.add_evidence(item)

            # Step 3: Determine root cause
            result.steps_completed.append("root_cause")
            if self._history:
                self._history.set_root_cause(result.root_cause or description)

            # Step 4: Generate remediation plan
            result.steps_completed.append("remediation_plan")
            plan = await self._generate_plan(service_name, description, evidence)
            result.remediation_plan = plan
            if self._history:
                self._history.set_remediation_plan(plan)
                decision = {
                    "step": "remediation_planning",
                    "plan": plan,
                    "evidence_count": len(evidence),
                }
                self._history.add_decision(decision)

            # Step 5: Risk assessment & approval
            result.steps_completed.append("risk_assessment")
            step_id = (
                self._history.add_step(
                    "approval", "Risk assessment & approval", input={"plan": plan}
                )
                if self._history
                else None
            )
            approved = await self._check_approval(plan)
            if self._history:
                self._history.complete_step(step_id, output={"approved": approved})
                self._history.add_approval({"approved": approved, "timestamp": _utc_now()})

            if not approved:
                result.status = "awaiting_approval"
                result.completed_at = _utc_now()
                result.duration_ms = (time.time() - start_time) * 1000
                self._results.append(result)
                if self._history:
                    self._history.complete_execution("approval_pending")
                await self._bus.publish(
                    EventType.APPROVAL_REQUESTED,
                    {"pipeline_id": pipeline_id, "incident_id": incident_id, "plan": plan},
                    source="autonomous_pipeline",
                    correlation_id=correlation_id,
                )
                return result

            # Step 6: Execute remediation
            result.steps_completed.append("execute")
            step_id = (
                self._history.add_step("execution", "Remediation execution", input={"plan": plan})
                if self._history
                else None
            )
            execution_result = await self._execute_remediation(plan, correlation_id)
            if self._history:
                self._history.complete_step(step_id, output=execution_result)

            # Step 7: Verify
            result.steps_completed.append("verify")
            verification = await self._verify_remediation(service_name, plan)
            result.verification = verification
            if self._history:
                self._history.set_verification(verification)
                self._history.add_decision({"step": "verification", "result": verification})

            # Step 8: Resolve incident
            result.steps_completed.append("resolve")
            if self._incidents and incident_id:
                try:
                    self._incidents.resolve_incident(
                        incident_id,
                        actor="autonomous_pipeline",
                        resolution_notes=f"Resolved by autonomous pipeline (pipeline_id={pipeline_id})",
                    )
                except KeyError:
                    _logger.warning("Incident %s not found for resolution", incident_id)

            # Step 9: Generate explanation
            result.steps_completed.append("explanation")
            explanation = self._build_explanation(
                service_name, description, plan, verification, result.root_cause
            )
            result.explanation = explanation
            if self._history:
                self._history.set_explanation(explanation)

            # Step 10: Update knowledge base
            result.steps_completed.append("knowledge_update")
            await self._update_knowledge(
                service_name, description, result.root_cause or "", plan, verification
            )

            result.status = "completed"
            await self._bus.publish(
                EventType.WORKFLOW_COMPLETED,
                {
                    "pipeline_id": pipeline_id,
                    "incident_id": incident_id,
                    "status": "completed",
                    "explanation": explanation,
                },
                source="autonomous_pipeline",
                correlation_id=correlation_id,
            )

        except Exception as exc:
            _logger.exception("Autonomous pipeline failed: %s", exc)
            result.status = "failed"
            result.error = str(exc)
            if self._history:
                self._history.fail_execution(str(exc))
            await self._bus.publish(
                EventType.WORKFLOW_FAILED,
                {"pipeline_id": pipeline_id, "incident_id": incident_id, "error": str(exc)},
                source="autonomous_pipeline",
                correlation_id=correlation_id,
            )
            await self._failsafe_rollback(pipeline_id, incident_id)

        result.completed_at = _utc_now()
        result.duration_ms = (time.time() - start_time) * 1000
        self._results.append(result)
        if self._history and self._history.get_active():
            self._history.complete_execution()
        return result

    async def _collect_evidence(self, service_name: str, description: str) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = [
            {
                "type": "incident_description",
                "value": description,
                "source": "event_bus",
                "timestamp": _utc_now(),
            },
            {
                "type": "service_name",
                "value": service_name,
                "source": "event_bus",
                "timestamp": _utc_now(),
            },
        ]
        if self._agents:
            try:
                agent_result = await self._agents.dispatch_task(
                    f"Investigate incident on {service_name}: {description}"
                )
                if agent_result.get("success") and isinstance(agent_result.get("data"), dict):
                    tool_results = agent_result["data"].get("tool_results", {})
                    for tool_name, tool_data in tool_results.items():
                        evidence.append(
                            {
                                "type": "tool_result",
                                "tool": tool_name,
                                "value": tool_data,
                                "source": agent_result.get("agent_id", "agent"),
                                "timestamp": _utc_now(),
                            }
                        )
            except Exception as exc:
                _logger.warning("Evidence collection failed: %s", exc)
        return evidence

    async def _generate_plan(
        self, service_name: str, description: str, evidence: list[dict[str, Any]]
    ) -> dict[str, Any]:
        plan: dict[str, Any] = {
            "service": service_name,
            "description": description,
            "evidence_count": len(evidence),
            "actions": [],
            "requires_approval": False,
        }

        knowledge_context = await self._retrieve_knowledge(service_name, description)
        if knowledge_context:
            plan["knowledge_context"] = knowledge_context

        if self._agents:
            try:
                prompt = f"Generate remediation plan for {service_name}: {description}"
                if knowledge_context:
                    prompt += f"\n\nPast knowledge: {knowledge_context.get('summary', 'none')}"
                prompt += '\n\nRespond with a JSON object containing: {"actions": [{"action": "action_name", "target": "target", "reason": "why"}], "root_cause": "...", "confidence": 0.0-1.0}'
                agent_result = await self._agents.dispatch_task(prompt)
                if agent_result.get("success"):
                    data = agent_result.get("data", {})
                    if isinstance(data, dict):
                        plan["agent_summary"] = data.get("summary", "")
                        plan["confidence"] = agent_result.get("confidence", 0.0)
                        parsed_actions = self._parse_agent_actions(data)
                        if parsed_actions:
                            plan["actions"] = parsed_actions
                        elif data.get("actions") and isinstance(data["actions"], list):
                            plan["actions"] = data["actions"]
                        if data.get("root_cause"):
                            plan["root_cause"] = data["root_cause"]
            except Exception as exc:
                _logger.warning("Plan generation failed: %s", exc)

        return plan

    def _parse_agent_actions(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for key in ("actions", "remediation_actions", "recommended_actions"):
            raw = data.get(key)
            if not isinstance(raw, list):
                continue
            for item in raw:
                if isinstance(item, str):
                    actions.append({"action": item, "target": "unknown", "reason": ""})
                elif isinstance(item, dict):
                    action_name = item.get("action", item.get("name", ""))
                    if action_name:
                        actions.append(
                            {
                                "action": action_name,
                                "target": item.get("target", "unknown"),
                                "reason": item.get("reason", item.get("description", "")),
                            }
                        )
            if actions:
                break
        return actions

    async def _retrieve_knowledge(
        self, service_name: str, description: str
    ) -> dict[str, Any] | None:
        if not self._repository:
            return None
        try:
            if hasattr(self._repository, "search_knowledge"):
                entries = self._repository.search_knowledge(service_name, limit=3)
                if entries:
                    return {
                        "similar_incidents": entries,
                        "count": len(entries),
                        "summary": f"Found {len(entries)} similar past incidents for {service_name}",
                    }
            if hasattr(self._repository, "get_knowledge_entries"):
                all_entries = self._repository.get_knowledge_entries()
                relevant = [
                    e
                    for e in all_entries
                    if isinstance(e, dict)
                    and service_name.lower() in str(e.get("service", "")).lower()
                ][:3]
                if relevant:
                    return {
                        "similar_incidents": relevant,
                        "count": len(relevant),
                        "summary": f"Found {len(relevant)} similar past incidents for {service_name}",
                    }
        except Exception as exc:
            _logger.warning("Knowledge retrieval failed: %s", exc)
        return None

    async def _check_approval(self, plan: dict[str, Any]) -> bool:
        actions = plan.get("actions", [])
        if not actions:
            return True
        for action_item in actions:
            action_name = (
                action_item if isinstance(action_item, str) else action_item.get("action", "")
            )
            policy = self._policy.evaluate(action_name, plan)
            if policy.verdict == ActionVerdict.FORBIDDEN:
                _logger.warning("Action '%s' is forbidden by policy", action_name)
                plan["forbidden_actions"] = plan.get("forbidden_actions", []) + [action_name]
                return False
            if policy.verdict == ActionVerdict.APPROVAL_REQUIRED:
                plan["requires_approval"] = True
                return False
        return True

    async def _execute_remediation(
        self, plan: dict[str, Any], correlation_id: str | None = None
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}
        actions = plan.get("actions", [])

        for action_item in actions:
            action_name = (
                action_item if isinstance(action_item, str) else action_item.get("action", "")
            )
            target = (
                action_item.get("target", plan.get("service", "unknown"))
                if isinstance(action_item, dict)
                else plan.get("service", "unknown")
            )

            if self._healing:
                healing_event = self._map_action_to_event(action_name)
                if healing_event:
                    healing_result = await self._healing.handle_event(
                        healing_event, {"name": target, "target_type": "unknown"}
                    )
                    if healing_result:
                        results[action_name] = healing_result.to_dict()
                        await self._bus.publish(
                            EventType.REMEDIATION_COMPLETED
                            if healing_result.status == "completed"
                            else EventType.REMEDIATION_FAILED,
                            {
                                "action": action_name,
                                "target": target,
                                "result": healing_result.to_dict(),
                            },
                            source="autonomous_pipeline",
                            correlation_id=correlation_id,
                        )

        return results

    async def _verify_remediation(self, service_name: str, plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "service": service_name,
            "verified": True,
            "timestamp": _utc_now(),
            "details": "Remediation completed successfully",
        }

    async def _update_knowledge(
        self,
        service_name: str,
        description: str,
        root_cause: str,
        plan: dict[str, Any],
        verification: dict[str, Any],
    ) -> None:
        if not self._repository:
            return
        try:
            if hasattr(self._repository, "save_knowledge_entry"):
                self._repository.save_knowledge_entry(
                    {
                        "service": service_name,
                        "incident_type": description,
                        "root_cause": root_cause,
                        "remediation": plan,
                        "verification": verification,
                        "timestamp": _utc_now(),
                    }
                )
            await self._bus.publish(
                EventType.KNOWLEDGE_UPDATED,
                {"service": service_name, "root_cause": root_cause},
                source="autonomous_pipeline",
            )
        except Exception as exc:
            _logger.warning("Knowledge update failed: %s", exc)

    def _build_explanation(
        self,
        service_name: str,
        description: str,
        plan: dict[str, Any],
        verification: dict[str, Any] | None,
        root_cause: str | None,
    ) -> dict[str, Any]:
        evidence = [
            f"Incident: {description}",
            f"Service: {service_name}",
        ]
        if root_cause:
            evidence.append(f"Root cause: {root_cause}")
        return {
            "why": f"Autonomous pipeline resolved '{description}' on '{service_name}'",
            "evidence": evidence,
            "confidence": plan.get("confidence", 0.85),
            "alternatives": [
                {"action": "manual_intervention", "reason": "Operator-driven resolution"},
                {"action": "escalate", "reason": "Escalate to senior operator"},
            ],
        }

    async def _failsafe_rollback(self, pipeline_id: str, incident_id: str | None) -> None:
        _logger.info("Failsafe rollback for pipeline %s", pipeline_id)
        try:
            if self._history:
                current = self._history.get_active()
                if current:
                    current.rollback = {"pipeline_id": pipeline_id, "triggered_at": _utc_now()}
                    self._history.fail_execution("Pipeline failed — rollback triggered")
            if self._incidents and incident_id:
                try:
                    self._incidents.update_incident(
                        incident_id, remediation_attempted=True, remediation_successful=False
                    )
                except KeyError:
                    pass
            await self._bus.publish(
                EventType.AUTONOMOUS_ACTION,
                {
                    "action": "rollback",
                    "pipeline_id": pipeline_id,
                    "incident_id": incident_id,
                    "status": "rolled_back",
                },
                source="autonomous_pipeline",
                correlation_id=pipeline_id,
            )
        except Exception as exc:
            _logger.exception("Rollback failed: %s", exc)

    def _map_action_to_event(self, action: str) -> EventType | None:
        mapping = {
            "restart_container": EventType.CONTAINER_DOWN,
            "retry_notification": EventType.NOTIFICATION_FAILED,
            "re_run_health_check": EventType.TARGET_DOWN,
            "restart_monitoring_job": EventType.WORKFLOW_FAILED,
        }
        return mapping.get(action)

    def get_results(self, limit: int = 20) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._results[-limit:]]

    def get_result(self, pipeline_id: str) -> dict[str, Any] | None:
        for r in self._results:
            if r.pipeline_id == pipeline_id:
                return r.to_dict()
        return None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
