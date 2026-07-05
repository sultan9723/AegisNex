"""Integration tests for Phase C3 graph wiring."""

from __future__ import annotations

from typing import Any, Dict

import src.intelligence.graph as graph_module
from src.intelligence.graph import build_graph, get_workflows, reset_graph, _goal_router
from src.intelligence.state import initial_state


def _append_step(state: Dict[str, Any], node: str, detail: str) -> None:
    executed_steps = list(state.get("executed_steps", []))
    executed_steps.append(
        {
            "node": node,
            "status": "completed",
            "detail": detail,
            "timestamp": "2026-07-01T00:00:00Z",
            "data": {},
        }
    )
    state["executed_steps"] = executed_steps


def test_workflow_topology_exposes_c3_path() -> None:
    workflow = get_workflows()

    assert "reflection" in workflow["nodes"]
    assert "finish" in workflow["nodes"]
    assert any(edge["from"] == "tool_executor" and edge["to"] == "reflection" for edge in workflow["edges"])
    assert any(edge["from"] == "reflection" and edge["to"] == "verifier" for edge in workflow["edges"])
    assert any(edge["from"] == "goal_evaluator" and edge["to"] == "planner" for edge in workflow["edges"])
    assert any(edge["from"] == "goal_evaluator" and edge["to"] == "finish" for edge in workflow["edges"])
    assert any(edge["from"] == "finish" and edge["to"] == "END" for edge in workflow["edges"])


def test_goal_router_uses_execution_history_for_retry_limit() -> None:
    state = initial_state("check the retry path")
    state["goal_completed"] = False
    state["max_retries"] = 3

    state["executed_steps"] = []
    assert _goal_router(state) == "planner"

    _append_step(state, "goal_evaluator", "first pass")
    assert _goal_router(state) == "planner"

    _append_step(state, "goal_evaluator", "second pass")
    assert _goal_router(state) == "planner"

    _append_step(state, "goal_evaluator", "third pass")
    assert _goal_router(state) == "finish"

    state["goal_completed"] = True
    assert _goal_router(state) == "finish"


def test_graph_loop_returns_to_planner_and_finishes(monkeypatch) -> None:
    reset_graph()

    def planner_stub(state, repo=None):
        state["retries"] = state.get("retries", 0) + 1
        state["current_plan"] = ["metrics"]
        state["parallel_batches"] = []
        _append_step(state, "planner", f"planner pass {state['retries']}")
        return state

    def tool_router_stub(state):
        _append_step(state, "tool_router", "routed plan")
        return state

    def tool_executor_stub(state, repo=None):
        state["tool_results"] = {"metrics": {"status": "ok", "count": 1}}
        _append_step(state, "tool_executor", "executed tools")
        return state

    def reflection_stub(state, repo=None):
        _append_step(state, "reflection", "reflected on execution")
        return state

    def verifier_stub(state):
        _append_step(state, "verifier", "verified state")
        return state

    def goal_evaluator_stub(state):
        state["goal_achieved"] = state.get("retries", 0) >= 2
        state["goal_completed"] = state["goal_achieved"]
        _append_step(state, "goal_evaluator", f"goal completed={state['goal_completed']}")
        return state

    def learning_stub(state):
        state["learnings"] = [{"note": "learning stored"}]
        _append_step(state, "learning", "persisted learnings")
        return state

    monkeypatch.setattr(graph_module, "plan_node", planner_stub)
    monkeypatch.setattr(graph_module, "tool_router_node", tool_router_stub)
    monkeypatch.setattr(graph_module, "tool_executor_node", tool_executor_stub)
    monkeypatch.setattr(graph_module, "self_corrector_node", reflection_stub)
    monkeypatch.setattr(graph_module, "verifier_node", verifier_stub)
    monkeypatch.setattr(graph_module, "goal_evaluator_node", goal_evaluator_stub)
    monkeypatch.setattr(graph_module, "learning_node", learning_stub)

    graph = build_graph(repo=None)
    result = graph.invoke(initial_state("check system health"))

    assert result["retries"] == 2
    assert result["goal_completed"] is True
    assert result["goal_achieved"] is True
    assert any(step["node"] == "reflection" for step in result["executed_steps"])
    assert any(step["node"] == "finish" for step in result["executed_steps"])
    assert result["executed_steps"][-1]["node"] == "finish"
    assert result["learnings"] == [{"note": "learning stored"}]
