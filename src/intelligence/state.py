"""Shared LangGraph state for the AegisNex Intelligence Engine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AgentStep(TypedDict):
    node: str
    status: str
    detail: str
    timestamp: str
    data: Any


class PendingApproval(TypedDict):
    id: str
    step: str
    action: str
    target: str
    reason: str
    status: str


class AgentState(TypedDict):
    user_request: str
    objective: str
    current_plan: List[str]
    completed_steps: List[str]
    tool_results: Dict[str, Any]
    observations: List[str]
    confidence: float
    retries: int
    max_retries: int
    final_answer: str
    goal_achieved: bool
    goal_completed: bool
    plan: Dict[str, Any]
    executed_steps: List[AgentStep]
    pending_approvals: List[PendingApproval]
    errors: List[str]
    corrections: List[str]
    missing_info: List[str]
    parallel_batches: List[List[str]]
    retrieved_context: str
    evidence: List[str]
    reasoning_summary: str
    remaining_uncertainty: str
    provider_used: str
    model_used: str
    execution_started_at: str
    execution_duration_ms: float
    token_usage: int
    tool_permission_levels: Dict[str, str]
    approval_required: bool
    approval_id: str
    current_runbook: str
    runbook_steps: List[Dict[str, Any]]
    risk_assessment: Dict[str, Any]
    policy_results: List[Dict[str, Any]]
    workflow_triggered: str
    scheduler_tasks: List[Dict[str, Any]]
    learnings: List[Dict[str, Any]]
    parallel_executions: Dict[str, Any]
    approval_log: List[Dict[str, Any]]
    agent_type: str
    agent_collaboration: List[Dict[str, Any]]
    shared_state: Dict[str, Any]
    active_skills: List[str]
    skill_results: List[Dict[str, Any]]
    tool_router_results: Dict[str, Any]


def initial_state(user_request: str) -> AgentState:
    return {
        "user_request": user_request,
        "objective": "",
        "current_plan": [],
        "completed_steps": [],
        "tool_results": {},
        "observations": [],
        "confidence": 0.0,
        "retries": 0,
        "max_retries": 3,
        "final_answer": "",
        "goal_achieved": False,
        "goal_completed": False,
        "plan": {},
        "executed_steps": [],
        "pending_approvals": [],
        "errors": [],
        "corrections": [],
        "missing_info": [],
        "parallel_batches": [],
        "retrieved_context": "",
        "evidence": [],
        "reasoning_summary": "",
        "remaining_uncertainty": "",
        "provider_used": "",
        "model_used": "",
        "execution_started_at": "",
        "execution_duration_ms": 0.0,
        "token_usage": 0,
        "tool_permission_levels": {},
        "approval_required": False,
        "approval_id": "",
        "current_runbook": "",
        "runbook_steps": [],
        "risk_assessment": {},
        "policy_results": [],
        "workflow_triggered": "",
        "scheduler_tasks": [],
        "learnings": [],
        "parallel_executions": {},
        "approval_log": [],
        "agent_type": "",
        "agent_collaboration": [],
        "shared_state": {},
        "active_skills": [],
        "skill_results": [],
        "tool_router_results": {},
    }
