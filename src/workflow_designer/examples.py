"""Example workflow definitions for common AI Ops scenarios."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.workflow_designer.models import (
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _node(
    node_id: str,
    node_type: WorkflowNodeType,
    label: str,
    config: Dict[str, Any] = None,
    pos_x: float = 0.0,
    pos_y: float = 0.0,
) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        type=node_type,
        label=label,
        config=config or {},
        position={"x": pos_x, "y": pos_y},
    )


def _edge(
    edge_id: str,
    source: str,
    target: str,
    label: str = "",
    condition: str = "",
) -> WorkflowEdge:
    return WorkflowEdge(
        id=edge_id,
        source=source,
        target=target,
        label=label,
        condition=condition,
    )


def incident_response_workflow() -> WorkflowDefinition:
    """Trigger: incident created -> AI Planning -> Tool Execution -> Approval
    -> Runbook -> Notification -> End.
    """
    ts = _now()
    return WorkflowDefinition(
        id=_id("incident_response"),
        name="Incident Response Automation",
        description=(
            "Automated incident response: triages via AI planning, "
            "executes diagnostic tools, requests human approval, "
            "runs remediation runbooks, and notifies the team."
        ),
        version="1.0.0",
        nodes=[
            _node("trigger", WorkflowNodeType.TRIGGER, "Incident Created", {
                "trigger_type": "incident",
                "severity": "critical",
            }, 0, 0),
            _node("ai_plan", WorkflowNodeType.AI_PLANNING, "AI Triage & Plan", {
                "mode": "plan",
                "user_request": "Analyze incident {incident_id} and create remediation plan",
            }, 250, 0),
            _node("tool_exec", WorkflowNodeType.TOOL_EXECUTION, "Run Diagnostics", {
                "tool_name": "system_diagnostics",
                "parameters": {"incident_id": "{incident_id}"},
            }, 500, 0),
            _node("approval", WorkflowNodeType.APPROVAL, "Human Approval", {
                "approvers": ["oncall-engineer", "sre-lead"],
                "timeout_minutes": 30,
                "message": "Incident {incident_id} - approve remediation plan?",
            }, 750, 0),
            _node("runbook", WorkflowNodeType.RUNBOOK, "Remediation Runbook", {
                "runbook_source": "runbooks/incident_remediation.yaml",
                "parameters": {"incident_id": "{incident_id}"},
            }, 1000, 0),
            _node("notify", WorkflowNodeType.NOTIFICATION, "Notify Team", {
                "channel": "all",
                "subject": "Incident {incident_id} - Remediation Complete",
                "message": "Incident {incident_id} (severity: {severity}) has been "
                           "remediated. Runbook executed successfully.",
            }, 1250, 0),
            _node("end", WorkflowNodeType.END, "End", {}, 1500, 0),
        ],
        edges=[
            _edge("e1", "trigger", "ai_plan", "Incident raised"),
            _edge("e2", "ai_plan", "tool_exec", "Plan ready"),
            _edge("e3", "tool_exec", "approval", "Diagnostics complete"),
            _edge("e4", "approval", "runbook", "Approved"),
            _edge("e5", "runbook", "notify", "Remediation applied"),
            _edge("e6", "notify", "end", "Notified"),
        ],
        tags=["incident", "remediation", "critical", "automated"],
        created_at=ts,
        updated_at=ts,
        enabled=True,
    )


def scheduled_health_check() -> WorkflowDefinition:
    """Trigger: cron schedule -> AI Planning -> Tool Execution
    -> Notification (if issues) -> End.
    """
    ts = _now()
    return WorkflowDefinition(
        id=_id("scheduled_health_check"),
        name="Scheduled Health Check",
        description=(
            "Runs every 30 minutes: AI selects health checks, "
            "executes probes, and notifies if anomalies are detected."
        ),
        version="1.0.0",
        nodes=[
            _node("trigger", WorkflowNodeType.TRIGGER, "Cron Schedule", {
                "trigger_type": "cron",
                "schedule": "*/30 * * * *",
            }, 0, 0),
            _node("ai_plan", WorkflowNodeType.AI_PLANNING, "Select Health Checks", {
                "mode": "plan",
                "user_request": "Select health checks for system {system_name}",
            }, 250, 0),
            _node("tool_exec", WorkflowNodeType.TOOL_EXECUTION, "Run Health Probes", {
                "tool_name": "health_check",
                "parameters": {"targets": ["api", "database", "cache"]},
            }, 500, 0),
            _node("condition", WorkflowNodeType.CONDITION, "Issues Detected?", {
                "expression": "len(_last_result.get('output', {}).get('issues', [])) > 0",
            }, 750, -100),
            _node("notify_issues", WorkflowNodeType.NOTIFICATION, "Notify on Issues", {
                "channel": "slack",
                "subject": "Health Check - Issues Detected",
                "message": "Health check detected {issue_count} issue(s): {issue_summary}",
            }, 1000, -100),
            _node("end_issues", WorkflowNodeType.END, "End (with issues)", {}, 1250, -100),
            _node("end_ok", WorkflowNodeType.END, "End (healthy)", {}, 1000, 100),
        ],
        edges=[
            _edge("e1", "trigger", "ai_plan", "Scheduled"),
            _edge("e2", "ai_plan", "tool_exec", "Checks selected"),
            _edge("e3", "tool_exec", "condition", "Probes complete"),
            _edge("e4_yes", "condition", "notify_issues", "Issues found",
                  condition="len(_last_result.get('output', {}).get('issues', [])) > 0"),
            _edge("e4_no", "condition", "end_ok", "All healthy",
                  condition="len(_last_result.get('output', {}).get('issues', [])) == 0"),
            _edge("e5", "notify_issues", "end_issues", "Notified"),
        ],
        tags=["health-check", "monitoring", "scheduled"],
        created_at=ts,
        updated_at=ts,
        enabled=True,
    )


def deployment_pipeline() -> WorkflowDefinition:
    """Trigger: webhook -> AI Planning -> Approval -> Runbook -> Notification -> End."""
    ts = _now()
    return WorkflowDefinition(
        id=_id("deployment_pipeline"),
        name="Deployment Pipeline",
        description=(
            "Zero-touch deployment pipeline triggered by a webhook. "
            "AI validates the change, requests approval, runs the "
            "deployment runbook, and notifies the team."
        ),
        version="1.0.0",
        nodes=[
            _node("trigger", WorkflowNodeType.TRIGGER, "Webhook Received", {
                "trigger_type": "webhook",
                "required_fields": ["service", "version", "deploy_id"],
            }, 0, 0),
            _node("ai_plan", WorkflowNodeType.AI_PLANNING, "Validate & Plan", {
                "mode": "workflow",
                "user_request": "Validate deployment of {service} version {version} "
                               "and create deployment plan",
            }, 250, 0),
            _node("approval", WorkflowNodeType.APPROVAL, "Deploy Approval", {
                "approvers": ["release-manager", "tech-lead"],
                "timeout_minutes": 120,
                "message": "Deploy {service} version {version} to production? "
                          "(deploy_id: {deploy_id})",
            }, 500, 0),
            _node("runbook", WorkflowNodeType.RUNBOOK, "Execute Deployment", {
                "runbook_source": "runbooks/deployment.yaml",
                "parameters": {
                    "service": "{service}",
                    "version": "{version}",
                    "deploy_id": "{deploy_id}",
                },
            }, 750, 0),
            _node("condition", WorkflowNodeType.CONDITION, "Deploy Success?", {
                "expression": "_last_result.get('status') == 'completed'",
            }, 1000, -100),
            _node("notify_success", WorkflowNodeType.NOTIFICATION, "Notify Success", {
                "channel": "all",
                "subject": "Deployment Complete: {service} v{version}",
                "message": "Deployment {deploy_id} of {service} version {version} "
                          "completed successfully.",
            }, 1250, -100),
            _node("notify_failure", WorkflowNodeType.NOTIFICATION, "Notify Failure", {
                "channel": "all",
                "subject": "Deployment FAILED: {service} v{version}",
                "message": "Deployment {deploy_id} of {service} version {version} "
                          "FAILED. Immediate investigation required.",
            }, 1250, 100),
            _node("end", WorkflowNodeType.END, "End", {}, 1500, 0),
        ],
        edges=[
            _edge("e1", "trigger", "ai_plan", "Webhook payload parsed"),
            _edge("e2", "ai_plan", "approval", "Validation complete"),
            _edge("e3", "approval", "runbook", "Approved"),
            _edge("e4", "runbook", "condition", "Deployment executed"),
            _edge("e5_yes", "condition", "notify_success", "Success",
                  condition="_last_result.get('status') == 'completed'"),
            _edge("e5_no", "condition", "notify_failure", "Failed",
                  condition="_last_result.get('status') != 'completed'"),
            _edge("e6", "notify_success", "end", "Notified"),
            _edge("e7", "notify_failure", "end", "Notified"),
        ],
        tags=["deployment", "pipeline", "ci-cd", "automated"],
        created_at=ts,
        updated_at=ts,
        enabled=True,
    )


def _id(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:8]}"
