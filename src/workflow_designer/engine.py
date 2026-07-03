"""Workflow execution engine."""

from __future__ import annotations

import copy
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.workflow_designer.models import (
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _evaluate_condition(expression: str, context: Dict[str, Any]) -> bool:
    """Safely evaluate a condition expression against context data."""
    if not expression:
        return True

    safe_globals: Dict[str, Any] = {
        "True": True,
        "False": False,
        "None": None,
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "float": float,
        "int": int,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "type": type,
    }
    safe_locals = dict(context)

    try:
        result = eval(expression, {"__builtins__": {}}, {**safe_globals, **safe_locals})  # nosec
        return bool(result)
    except Exception:
        return False


def _get_next_node(
    current_node_id: str,
    edges: List[WorkflowEdge],
    context: Dict[str, Any],
    nodes: List[WorkflowNode],
) -> Optional[WorkflowNode]:
    """Determine the next node based on edges and context."""
    outgoing = [e for e in edges if e.source == current_node_id]
    if not outgoing:
        return None

    current_node = next(
        (n for n in nodes if n.id == current_node_id), None
    )
    if current_node and current_node.type == WorkflowNodeType.CONDITION:
        for edge in outgoing:
            if _evaluate_condition(edge.condition, context):
                target = next(
                    (n for n in nodes if n.id == edge.target), None
                )
                context["_last_matched_condition"] = edge.condition
                return target
        return None

    target_id = outgoing[0].target
    return next((n for n in nodes if n.id == target_id), None)


class WorkflowEngine:
    """Executes a WorkflowDefinition node by node, producing a trace."""

    def execute(
        self,
        workflow: WorkflowDefinition,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        ctx: Dict[str, Any] = copy.deepcopy(context) if context else {}
        trace: List[Dict[str, Any]] = []
        overall_status = "completed"

        if not workflow.nodes or not workflow.edges:
            return {
                "status": "error",
                "error": "Workflow has no nodes or edges",
                "trace": [],
                "duration_ms": 0,
                "started_at": _utc_now(),
            }

        node_map = {n.id: n for n in workflow.nodes}
        trigger = next(
            (n for n in workflow.nodes if n.type == WorkflowNodeType.TRIGGER), None
        )
        if trigger is None:
            return {
                "status": "error",
                "error": "Workflow has no TRIGGER node",
                "trace": [],
                "duration_ms": 0,
                "started_at": _utc_now(),
            }

        current_node = trigger
        max_steps = len(workflow.nodes) * 2 + 10
        step_count = 0

        while current_node is not None and current_node.type != WorkflowNodeType.END:
            if step_count > max_steps:
                overall_status = "max_steps_exceeded"
                trace.append(
                    {
                        "node_id": current_node.id,
                        "node_label": current_node.label,
                        "node_type": current_node.type.value,
                        "status": "skipped",
                        "error": "Max steps exceeded",
                        "duration_ms": 0,
                    }
                )
                break

            step_count += 1
            node_start = time.time()
            step_entry: Dict[str, Any] = {
                "node_id": current_node.id,
                "node_label": current_node.label,
                "node_type": current_node.type.value,
            }

            try:
                result = self.execute_node(current_node, ctx)
                ctx.update(result.get("output", {}))
                ctx["_last_result"] = result
                step_entry["status"] = result.get("status", "completed")
                step_entry["output"] = result.get("output", {})
                if result.get("error"):
                    step_entry["error"] = result["error"]
                if result.get("pending"):
                    step_entry["pending"] = result["pending"]
            except Exception as exc:
                step_entry["status"] = "error"
                step_entry["error"] = f"{type(exc).__name__}: {exc}"
                step_entry["traceback"] = traceback.format_exc()
                overall_status = "error"

            step_entry["duration_ms"] = round((time.time() - node_start) * 1000, 2)
            step_entry["timestamp"] = _utc_now()
            trace.append(step_entry)

            if step_entry["status"] == "error" and current_node.type not in (
                WorkflowNodeType.CONDITION,
                WorkflowNodeType.END,
            ):
                overall_status = "error"
                break

            if current_node.type == WorkflowNodeType.APPROVAL:
                pending = step_entry.get("pending", {})
                if pending.get("status") == "pending":
                    overall_status = "pending_approval"
                    break

            current_node = _get_next_node(current_node.id, workflow.edges, ctx, workflow.nodes)

        total_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "status": overall_status,
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
            "trace": trace,
            "duration_ms": total_ms,
            "started_at": _utc_now(),
            "context": ctx,
        }

    def execute_node(
        self,
        node: WorkflowNode,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        if node.type == WorkflowNodeType.TRIGGER:
            return self._handle_trigger(node, context)
        elif node.type == WorkflowNodeType.AI_PLANNING:
            return self._handle_ai_planning(node, context)
        elif node.type == WorkflowNodeType.TOOL_EXECUTION:
            return self._handle_tool_execution(node, context)
        elif node.type == WorkflowNodeType.APPROVAL:
            return self._handle_approval(node, context)
        elif node.type == WorkflowNodeType.RUNBOOK:
            return self._handle_runbook(node, context)
        elif node.type == WorkflowNodeType.NOTIFICATION:
            return self._handle_notification(node, context)
        elif node.type == WorkflowNodeType.CONDITION:
            return self._handle_condition(node, context)
        elif node.type == WorkflowNodeType.END:
            return {"status": "completed", "output": {}}
        else:
            return {"status": "error", "error": f"Unknown node type: {node.type}"}

    def _handle_trigger(self, node: WorkflowNode, context: Dict[str, Any]) -> Dict[str, Any]:
        trigger_type = node.config.get("trigger_type", "manual")
        if trigger_type == "webhook":
            payload = node.config.get("payload", {})
            validated = True
            required_fields = node.config.get("required_fields", [])
            for field in required_fields:
                if field not in payload and field not in context.get("payload", {}):
                    validated = False
            context.setdefault("payload", {}).update(payload)
            return {
                "status": "completed" if validated else "error",
                "output": {"trigger_type": trigger_type, "validated": validated},
                "error": "" if validated else "Required fields missing",
            }
        elif trigger_type == "cron":
            schedule = node.config.get("schedule", "")
            return {
                "status": "completed",
                "output": {"trigger_type": trigger_type, "schedule": schedule},
            }
        elif trigger_type == "incident":
            incident_id = node.config.get("incident_id", "")
            severity = node.config.get("severity", "")
            context["incident_id"] = incident_id
            context["severity"] = severity
            return {
                "status": "completed",
                "output": {
                    "trigger_type": trigger_type,
                    "incident_id": incident_id,
                    "severity": severity,
                },
            }
        else:
            return {
                "status": "completed",
                "output": {"trigger_type": "manual", "triggered_at": _utc_now()},
            }

    def _handle_ai_planning(self, node: WorkflowNode, context: Dict[str, Any]) -> Dict[str, Any]:
        from src.intelligence.graph import run_plan, run_workflow

        user_request = (
            node.config.get("user_request")
            or context.get("user_request")
            or context.get("incident_id", "")
        )
        mode = node.config.get("mode", "plan")

        if mode == "workflow":
            result = run_workflow(user_request=user_request)
        else:
            result = run_plan(user_request=user_request)

        plan_data = result.get("plan") or result.get("current_plan") or result
        return {
            "status": "completed" if not result.get("errors") else "error",
            "output": {
                "plan": plan_data,
                "objective": result.get("objective", ""),
                "raw": result,
            },
            "error": "; ".join(result.get("errors", [])),
        }

    def _handle_tool_execution(self, node: WorkflowNode, context: Dict[str, Any]) -> Dict[str, Any]:
        from src.intelligence.tools import execute_tool

        tool_name = node.config.get("tool_name") or context.get("_tool_name", "")
        kwargs = dict(node.config.get("parameters", {}))
        kwargs.update(context.get("_tool_params", {}))
        result = execute_tool(name=tool_name, **kwargs)

        return {
            "status": result.get("status", "completed"),
            "output": result,
            "error": result.get("error", ""),
        }

    def _handle_approval(self, node: WorkflowNode, context: Dict[str, Any]) -> Dict[str, Any]:
        approval_id = node.config.get("approval_id", f"approval_{node.id}")
        approvers = node.config.get("approvers", [])
        timeout_minutes = node.config.get("timeout_minutes", 60)
        message = node.config.get("message", "Please approve this workflow step")

        pending = {
            "approval_id": approval_id,
            "status": "pending",
            "approvers": approvers,
            "timeout_minutes": timeout_minutes,
            "message": message,
            "created_at": _utc_now(),
        }
        context["_pending_approval"] = pending

        auto_approve = node.config.get("auto_approve", False)
        if auto_approve:
            pending["status"] = "approved"
            pending["approved_by"] = "auto"
            pending["approved_at"] = _utc_now()
            return {
                "status": "completed",
                "output": {"approval_id": approval_id, "approved": True, "auto": True},
            }

        approved = node.config.get("_approved", False)
        if approved:
            pending["status"] = "approved"
            pending["approved_by"] = node.config.get("_approved_by", "system")
            pending["approved_at"] = _utc_now()
            return {
                "status": "completed",
                "output": {"approval_id": approval_id, "approved": True},
            }

        return {
            "status": "pending",
            "output": {"approval_id": approval_id, "approved": False},
            "pending": pending,
        }

    def _handle_runbook(self, node: WorkflowNode, context: Dict[str, Any]) -> Dict[str, Any]:
        from src.intelligence.runbooks.engine import RunbookEngine
        from src.intelligence.runbooks.parser import RunbookParser

        runbook_source = node.config.get("runbook_source")
        if not runbook_source:
            return {"status": "error", "error": "No runbook_source specified"}

        if runbook_source.endswith(".yaml") or runbook_source.endswith(".yml"):
            try:
                path = node.config.get("base_path", ".")
                from pathlib import Path
                content = Path(path, runbook_source).read_text(encoding="utf-8")
                parser = RunbookParser()
                runbook = parser.parse(content)
            except Exception as exc:
                return {"status": "error", "error": f"Failed to parse runbook: {exc}"}
        else:
            parser = RunbookParser()
            runbook = parser.parse(runbook_source)

        engine = RunbookEngine()
        incident_id = context.get("incident_id")
        kwargs = dict(node.config.get("parameters", {}))
        result = engine.execute(runbook, incident_id=incident_id, **kwargs)

        return {
            "status": "completed" if result.status == "completed" else "error",
            "output": {
                "runbook_name": getattr(runbook, "name", ""),
                "status": result.status,
                "step_count": len(result.step_results),
                "results": [s.to_dict() if hasattr(s, "to_dict") else str(s) for s in result.step_results],
            },
            "error": "" if result.status == "completed" else result.status,
        }

    def _handle_notification(self, node: WorkflowNode, context: Dict[str, Any]) -> Dict[str, Any]:
        from src.notifications.base import NotificationResult
        from src.notifications.factory import build_notification_providers
        from src.config import Config

        channel = node.config.get("channel", "email")
        subject = node.config.get("subject", "AegisNex Workflow Notification")
        message_template = node.config.get("message", "")
        severity = context.get("severity", "info")
        incident_id = context.get("incident_id", "")

        message = message_template
        for key, value in context.items():
            if isinstance(value, (str, int, float, bool)):
                message = message.replace(f"{{{key}}}", str(value))
        message = message.replace("{severity}", severity)
        message = message.replace("{incident_id}", incident_id)

        try:
            config = Config() if hasattr(Config, "__init__") else Config
            providers = build_notification_providers(config)

            results: List[Dict[str, Any]] = []
            matched = False
            for provider in providers:
                provider_channel = getattr(provider, "channel", channel)
                if channel != "all" and provider_channel != channel and channel not in str(type(provider).__name__).lower():
                    continue
                if not getattr(provider, "enabled", True):
                    continue
                matched = True
                notification_result: NotificationResult = provider.send(
                    subject=subject,
                    message=message,
                    severity=severity,
                    incident_id=incident_id,
                )
                results.append(
                    {
                        "provider": type(provider).__name__,
                        "success": notification_result.success,
                        "error": notification_result.error or "",
                    }
                )

            if not matched:
                return {
                    "status": "completed",
                    "output": {"channel": channel, "sent": False, "note": "No matching provider found"},
                }

            all_ok = all(r["success"] for r in results)
            return {
                "status": "completed" if all_ok else "partial",
                "output": {"channel": channel, "results": results, "sent": all_ok},
                "error": "" if all_ok else "Some notification providers failed",
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": f"Notification failed: {exc}",
                "output": {"channel": channel, "sent": False},
            }

    def _handle_condition(self, node: WorkflowNode, context: Dict[str, Any]) -> Dict[str, Any]:
        expression = node.config.get("expression", "")
        if not expression:
            return {"status": "completed", "output": {"matched": True, "expression": ""}}
        result = _evaluate_condition(expression, context)
        return {
            "status": "completed",
            "output": {
                "expression": expression,
                "matched": result,
                "_matched_condition": expression if result else "",
            },
        }


def validate_workflow(definition: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a workflow definition dictionary.

    Returns (is_valid, list_of_error_messages).
    """
    errors: List[str] = []

    if not isinstance(definition, dict):
        return False, ["Definition must be a dictionary"]

    required_keys = ["id", "name", "nodes", "edges"]
    for key in required_keys:
        if key not in definition:
            errors.append(f"Missing required key: '{key}'")

    if errors:
        return False, errors

    if not definition.get("name"):
        errors.append("Workflow name must not be empty")

    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    if not isinstance(nodes, list):
        errors.append("'nodes' must be a list")
    if not isinstance(edges, list):
        errors.append("'edges' must be a list")

    if errors:
        return False, errors

    # Validate each node has required fields
    valid_types = {t.value for t in WorkflowNodeType}
    node_ids: set = set()
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{i}] must be a dictionary")
            continue
        if "id" not in node:
            errors.append(f"nodes[{i}] missing 'id'")
        else:
            nid = node["id"]
            if nid in node_ids:
                errors.append(f"Duplicate node id: '{nid}'")
            node_ids.add(nid)
        if "type" not in node:
            errors.append(f"nodes[{i}] missing 'type'")
        elif node.get("type") not in valid_types:
            errors.append(f"nodes[{i}] invalid type '{node.get('type')}'")

    # Validate edges reference valid nodes
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edges[{i}] must be a dictionary")
            continue
        eid = edge.get("id", f"edges[{i}]")
        source = edge.get("source", "")
        target = edge.get("target", "")
        if source and source not in node_ids:
            errors.append(f"Edge '{eid}' references unknown source node '{source}'")
        if target and target not in node_ids:
            errors.append(f"Edge '{eid}' references unknown target node '{target}'")

    # Must have exactly one TRIGGER
    trigger_count = sum(
        1 for n in nodes if isinstance(n, dict) and n.get("type") == "TRIGGER"
    )
    if trigger_count != 1:
        errors.append(f"Workflow must have exactly 1 TRIGGER node, found {trigger_count}")

    return (len(errors) == 0, errors)
