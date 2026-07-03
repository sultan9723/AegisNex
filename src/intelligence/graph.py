"""LangGraph construction for the AegisNex Intelligence Engine.

Builds the agentic workflow graph with Planning → Tool Router → Executor
→ Reflection → Verifier → Goal Evaluator → Finish. Supports retry loops
back to Planner when the goal is not completed and preserves workflow state.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END

from src.intelligence.state import AgentState, initial_state
from src.intelligence.nodes import (
    plan_node,
    skill_executor_node,
    tool_router_node,
    tool_executor_node,
    verifier_node,
    self_corrector_node,
    goal_evaluator_node,
    risk_assessor_node,
    policy_checker_node,
    runbook_executor_node,
    parallel_supervisor_node,
    scheduler_node,
    learning_node,
    human_approval_check,
)
from src.platform_db import PlatformRepository


_BUILT_GRAPH: Any = None


def _reflection_node(state: AgentState, repo: Optional[PlatformRepository] = None) -> AgentState:
    return self_corrector_node(state, repo=repo)


def _goal_evaluator_with_completion(state: AgentState) -> AgentState:
    updated_state = goal_evaluator_node(state)
    updated_state["goal_completed"] = updated_state.get("goal_achieved", False)
    return updated_state


def _goal_attempts(state: AgentState) -> int:
    return sum(1 for step in state.get("executed_steps", []) if step.get("node") == "goal_evaluator")


def _goal_router(state: AgentState) -> str:
    if state.get("goal_completed", False):
        return "finish"
    if _goal_attempts(state) >= state.get("max_retries", 3):
        return "finish"
    return "planner"


def _finish_node(state: AgentState) -> AgentState:
    updated_state = learning_node(state)
    updated_state["goal_completed"] = updated_state.get("goal_achieved", False)

    executed_steps = list(updated_state.get("executed_steps", []))
    executed_steps.append(
        {
            "node": "finish",
            "status": "completed",
            "detail": "Workflow finished",
            "timestamp": _utc_now(),
            "data": {
                "goal_completed": updated_state.get("goal_completed", False),
                "goal_achieved": updated_state.get("goal_achieved", False),
                "retry_count": updated_state.get("retries", 0),
            },
        }
    )
    updated_state["executed_steps"] = executed_steps
    return updated_state


def build_graph(repo: Optional[PlatformRepository] = None) -> StateGraph:
    """Build the LangGraph for the Intelligence Engine.

    Graph structure:
        START → planner → tool_router → tool_executor → reflection → verifier → goal_evaluator → finish → END
                          ↑                               │                    │
                          └─────────── loop back to planner if incomplete ◀────┘
        Pending approvals are preserved in state and the workflow terminates cleanly.
        Tool Router maps abstract tasks to registered tools without executing them.
    """
    global _BUILT_GRAPH

    if _BUILT_GRAPH is not None:
        return _BUILT_GRAPH

    graph = StateGraph(AgentState)

    graph.add_node("planner", lambda state: plan_node(state, repo=repo))
    graph.add_node("skill_executor", skill_executor_node)
    graph.add_node("tool_router", tool_router_node)
    graph.add_node("tool_executor", lambda state: tool_executor_node(state, repo=repo))
    graph.add_node("verifier", verifier_node)
    graph.add_node("reflection", lambda state: _reflection_node(state, repo=repo))
    graph.add_node("self_corrector", lambda state: _reflection_node(state, repo=repo))
    graph.add_node("goal_evaluator", _goal_evaluator_with_completion)
    graph.add_node("finish", _finish_node)
    graph.add_node("risk_assessor", risk_assessor_node)
    graph.add_node("policy_checker", policy_checker_node)
    graph.add_node("runbook_executor", lambda state: runbook_executor_node(state, repo=repo))
    graph.add_node("parallel_supervisor", parallel_supervisor_node)
    graph.add_node("scheduler", scheduler_node)

    graph.set_entry_point("planner")

    def planner_router(state: AgentState) -> str:
        if state.get("active_skills"):
            return "skills"
        if state.get("current_runbook") or state.get("workflow_triggered"):
            return "runbook"
        if state.get("parallel_batches"):
            return "parallel"
        if state.get("current_plan"):
            return "route"
        return "evaluate"

    graph.add_conditional_edges(
        "planner",
        planner_router,
        {
            "skills": "skill_executor",
            "runbook": "runbook_executor",
            "parallel": "parallel_supervisor",
            "route": "tool_router",
            "evaluate": "goal_evaluator",
        },
    )

    graph.add_edge("skill_executor", "tool_router")

    graph.add_edge("tool_router", "tool_executor")
    graph.add_edge("tool_executor", "reflection")

    graph.add_edge("reflection", "verifier")

    graph.add_edge("runbook_executor", "scheduler")
    graph.add_edge("parallel_supervisor", "scheduler")

    graph.add_edge("scheduler", "policy_checker")
    graph.add_edge("policy_checker", "risk_assessor")

    def risk_router(state: AgentState) -> str:
        if state.get("approval_required"):
            return "wait"
        return "verify"

    graph.add_conditional_edges(
        "risk_assessor",
        risk_router,
        {"verify": "verifier", "wait": "goal_evaluator"},
    )

    graph.add_edge("verifier", "goal_evaluator")

    graph.add_conditional_edges(
        "goal_evaluator",
        _goal_router,
        {"planner": "planner", "finish": "finish"},
    )

    graph.add_edge("finish", END)

    _BUILT_GRAPH = graph.compile()

    return _BUILT_GRAPH


def run_workflow(
    user_request: str,
    repo: Optional[PlatformRepository] = None,
) -> Dict[str, Any]:
    """Execute the full Intelligence Engine workflow for a user request.

    Records execution duration, persists to memory, and returns full state.
    """
    from src.intelligence.retrieval.rag import RAGEngine
    from src.intelligence.providers.factory import create_provider

    start_time = time.time()
    provider_name = os.getenv("AEGIS_AI_PROVIDER", "openai")
    model = os.getenv(f"AEGIS_AI_{provider_name.upper()}_MODEL", "")

    graph = build_graph(repo=repo)
    state = initial_state(user_request)
    state["execution_started_at"] = _utc_now()
    state["provider_used"] = provider_name
    state["model_used"] = model

    result = graph.invoke(state)

    duration_ms = (time.time() - start_time) * 1000
    result["execution_duration_ms"] = round(duration_ms, 2)

    # Persist to memory
    try:
        from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
        db_path = os.getenv("AEGIS_AI_MEMORY_DB", "ai_memory.db")
        memory = SQLiteMemoryStore(db_path=db_path)
        memory.store_conversation(
            request=user_request,
            response=result.get("final_answer", ""),
            confidence=result.get("confidence", 0.0),
            goal_achieved=result.get("goal_achieved", False),
            steps=[str(s) for s in result.get("executed_steps", [])],
            errors=result.get("errors", []),
            corrections=result.get("corrections", []),
            duration_ms=duration_ms,
            provider=provider_name,
            model=model,
        )
        # Store tool executions
        for tool_name, tool_result in result.get("tool_results", {}).items():
            memory.store_tool_execution(
                tool_name=tool_name,
                parameters={},
                result_status=tool_result.get("status", "unknown"),
                duration_ms=duration_ms / max(len(result.get("tool_results", {})), 1),
                error=tool_result.get("error", ""),
            )
    except Exception:
        pass

    return dict(result)


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_plan(
    user_request: str,
    repo: Optional[PlatformRepository] = None,
) -> Dict[str, Any]:
    """Execute only the planning phase and return the generated plan."""
    state = initial_state(user_request)
    planned = plan_node(state, repo=repo)
    return {
        "objective": planned.get("objective", ""),
        "plan": planned.get("plan", {}),
        "current_plan": planned.get("current_plan", []),
        "parallel_batches": planned.get("parallel_batches", []),
        "missing_info": planned.get("missing_info", []),
    }


def run_analyze(
    user_request: str,
    repo: Optional[PlatformRepository] = None,
) -> Dict[str, Any]:
    """Run full analysis workflow and return structured results."""
    return run_workflow(user_request, repo=repo)


def run_chat(
    user_request: str,
    repo: Optional[PlatformRepository] = None,
) -> Dict[str, Any]:
    """Run the full workflow and return a simplified chat response."""
    result = run_workflow(user_request, repo=repo)
    return {
        "answer": result.get("final_answer", ""),
        "goal_achieved": result.get("goal_achieved", False),
        "confidence": result.get("confidence", 0.0),
        "steps": result.get("executed_steps", []),
        "observations": result.get("observations", []),
        "corrections": result.get("corrections", []),
        "errors": result.get("errors", []),
        "evidence": result.get("evidence", []),
        "reasoning_summary": result.get("reasoning_summary", ""),
        "remaining_uncertainty": result.get("remaining_uncertainty", ""),
        "execution_duration_ms": result.get("execution_duration_ms", 0.0),
        "provider_used": result.get("provider_used", ""),
        "model_used": result.get("model_used", ""),
        "workflow": result.get("workflow_triggered", ""),
        "runbook": result.get("current_runbook", ""),
        "risk_score": result.get("risk_assessment", {}).get("score", 0.0),
        "risk_level": result.get("risk_assessment", {}).get("level", "none"),
        "policy_violations": [p.get("policy_name", "") for p in result.get("policy_results", []) if not p.get("allowed", True)],
        "scheduler_tasks": len(result.get("scheduler_tasks", [])),
        "learnings": len(result.get("learnings", [])),
    }


def reset_graph() -> None:
    """Reset the cached graph (useful for testing)."""
    global _BUILT_GRAPH
    _BUILT_GRAPH = None


def get_workflows() -> Dict[str, Any]:
    """Return workflow definitions for the AI dashboard."""
    return {
        "nodes": ["planner", "skill_executor", "tool_router", "tool_executor", "reflection", "verifier", "goal_evaluator", "finish", "risk_assessor", "policy_checker", "runbook_executor", "parallel_supervisor", "scheduler"],
        "edges": [
            {"from": "planner", "to": "skill_executor", "condition": "skills matched"},
            {"from": "planner", "to": "tool_router", "condition": "plan exists"},
            {"from": "planner", "to": "goal_evaluator", "condition": "empty plan"},
            {"from": "planner", "to": "runbook_executor", "condition": "runbook selected"},
            {"from": "planner", "to": "parallel_supervisor", "condition": "parallel batches"},
            {"from": "skill_executor", "to": "tool_router"},
            {"from": "tool_router", "to": "tool_executor"},
            {"from": "tool_executor", "to": "reflection"},
            {"from": "reflection", "to": "verifier"},
            {"from": "runbook_executor", "to": "scheduler"},
            {"from": "parallel_supervisor", "to": "scheduler"},
            {"from": "scheduler", "to": "policy_checker"},
            {"from": "policy_checker", "to": "risk_assessor"},
            {"from": "risk_assessor", "to": "verifier", "condition": "auto-approved"},
            {"from": "risk_assessor", "to": "goal_evaluator", "condition": "approval required"},
            {"from": "verifier", "to": "goal_evaluator", "condition": "verified"},
            {"from": "goal_evaluator", "to": "planner", "condition": "goal incomplete and retries < 3"},
            {"from": "goal_evaluator", "to": "finish", "condition": "goal completed or retries exhausted"},
            {"from": "finish", "to": "END"},
        ],
        "max_retries": 3,
    }
