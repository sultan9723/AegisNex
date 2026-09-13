"""Regression tests for the AI Workspace multi-intent planning/grounding bug.

Real E2E report: the prompt "Show me the current system health ... which
HTTP targets are healthy or unhealthy, list active incidents ..." - three
distinct live-data objectives (system health, HTTP target status, active
incidents) - collapsed into a single objective ("List active incidents"),
ran only the incident tool, and still reported 100% confidence. Separately,
the incident tool itself always returned 0 incidents regardless of real
incident state, because it read from a disposable, never-populated
IncidentManager instead of the real PlatformRepository.

These tests use different wording than the original report's sentence
throughout (per "do not create special-case logic for this exact
sentence") to prove the fix is a general mechanism, not a hardcoded match
on that one prompt.
"""

from __future__ import annotations

from pathlib import Path

from src.incidents import IncidentManager
from src.intelligence.nodes import (
    _match_intent_categories,
    goal_evaluator_node,
    parallel_supervisor_node,
    plan_node,
    verifier_node,
)
from src.intelligence.state import initial_state
from src.intelligence.tools import execute_tool
from src.platform_db import PlatformRepository


def make_repo(tmp_path: Path) -> PlatformRepository:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    repo.initialize()
    return repo


def create_real_incident(repo: PlatformRepository, tmp_path: Path, **overrides):
    """Creates a real incident through the same path the Guardian/monitor
    loop uses in production (IncidentManager.create_incident, which writes
    both the JSON history and, via storage_repository, the real DB row) -
    not a hand-inserted row."""
    im = IncidentManager(tmp_path / "incident_history.json", storage_repository=repo)
    defaults = dict(
        severity="high",
        service_name="kammand-website",
        incident_type="http_endpoint_failure",
        description="HTTP endpoint failed: connection refused",
        health_check_results=[{"status_code": 503, "error": "connection refused"}],
    )
    defaults.update(overrides)
    return im.create_incident(**defaults)


# ---------------------------------------------------------------------------
# 1. Intent-category detection supports multiple simultaneous intents
# ---------------------------------------------------------------------------


def test_match_intent_categories_detects_every_category_in_one_sentence():
    request = (
        "give me an overview of system health, tell me whether our monitoring "
        "targets are up, and list any active alerts"
    )
    categories = _match_intent_categories(request)
    assert set(categories) == {"health", "target", "incident"}


def test_match_intent_categories_single_topic_still_returns_one():
    assert _match_intent_categories("list active incidents") == ["incident"]


def test_match_intent_categories_no_keywords_returns_empty():
    assert _match_intent_categories("hello there") == []


# ---------------------------------------------------------------------------
# 2. plan_node: multi-intent requests run every required tool
# ---------------------------------------------------------------------------


def test_plan_node_multi_intent_prompt_unions_all_required_tools():
    """A three-part operational question must not collapse to one tool."""
    request = (
        "What is our overall infrastructure health right now, is every HTTP "
        "monitoring target reachable, and are there any active incidents?"
    )
    state = initial_state(request)

    result = plan_node(state)

    assert set(result["required_categories"]) == {"health", "target", "incident"}
    assert "health" in result["current_plan"]
    assert "target" in result["current_plan"]
    assert "incident" in result["current_plan"]
    # Objective describes every matched area, not just one.
    assert result["objective"].count(";") >= 1


def test_plan_node_single_intent_prompt_keeps_prior_single_tool_behavior():
    """Backward compatibility: a single-topic request still plans narrowly."""
    state = initial_state("list active incidents")

    result = plan_node(state)

    assert result["current_plan"] == ["incident"]
    assert result["objective"] == "List active incidents"
    assert result["required_categories"] == ["incident"]


def test_plan_node_separates_reference_material_from_live_evidence():
    """RAG/static-knowledge citations must never be pre-loaded into
    `evidence` - only real tool results belong there (populated later in
    verifier_node)."""
    state = initial_state("list active incidents")

    result = plan_node(state)

    assert result["evidence"] == []
    assert isinstance(result["reference_material"], list)


# ---------------------------------------------------------------------------
# 3 & 4. The incident tool reads real, current PlatformRepository data
# ---------------------------------------------------------------------------


def test_incident_tool_returns_real_incidents_not_always_zero(tmp_path: Path):
    repo = make_repo(tmp_path)
    create_real_incident(repo, tmp_path)

    result = execute_tool("incident", repo=repo, action="list")

    assert result["count"] == 1
    assert result["incidents"][0]["service_name"] == "kammand-website"


def test_incident_tool_list_with_no_incidents_returns_real_zero(tmp_path: Path):
    """0 is a valid, real answer when the repository genuinely has no
    incidents - the bug was that it was ALWAYS 0, never that 0 is wrong."""
    repo = make_repo(tmp_path)

    result = execute_tool("incident", repo=repo, action="list")

    assert result["count"] == 0
    assert result["incidents"] == []


def test_incident_tool_active_action_filters_to_active_and_acknowledged(tmp_path: Path):
    repo = make_repo(tmp_path)
    im = IncidentManager(tmp_path / "incident_history.json", storage_repository=repo)
    active = im.create_incident(
        severity="high", service_name="svc-a", incident_type="http_endpoint_failure",
        description="down",
    )
    resolved = im.create_incident(
        severity="low", service_name="svc-b", incident_type="http_endpoint_failure",
        description="down too",
    )
    im.update_incident(resolved.incident_id, status="resolved")

    result = execute_tool("incident", repo=repo, action="active")

    ids = {i["incident_id"] for i in result["incidents"]}
    assert active.incident_id in ids
    assert resolved.incident_id not in ids


def test_incident_tool_uses_the_same_repository_the_incidents_ui_reads(tmp_path: Path):
    """The real /api/incidents route reads via repo.list_incidents(); the
    tool must read from the exact same store, not a parallel one."""
    repo = make_repo(tmp_path)
    create_real_incident(repo, tmp_path)

    tool_result = execute_tool("incident", repo=repo, action="list")
    ui_result = repo.list_incidents()

    assert tool_result["count"] == len(ui_result)
    assert {i["incident_id"] for i in tool_result["incidents"]} == {
        i["incident_id"] for i in ui_result
    }


# ---------------------------------------------------------------------------
# 5 & 7. Confidence distinguishes tool success from objective coverage
# ---------------------------------------------------------------------------


def _state_with(required_categories, current_plan, tool_results) -> dict:
    state = initial_state("irrelevant for this test")
    state["required_categories"] = required_categories
    state["current_plan"] = current_plan
    state["tool_results"] = tool_results
    return state


def test_verifier_caps_confidence_when_two_of_three_objectives_never_ran():
    """Mirrors the real bug shape: 1 of 3 required categories covered, that
    1 tool succeeded. Tool success rate is 100%; confidence must not be."""
    state = _state_with(
        required_categories=["health", "target", "incident"],
        current_plan=["incident"],
        tool_results={"incident": {"status": "ok", "count": 0}},
    )

    result = verifier_node(state)

    assert result["tool_success_rate"] == 1.0
    assert result["objective_coverage"] == 1 / 3
    assert result["confidence"] == 1 / 3
    assert result["confidence"] < 1.0
    assert "health" not in result["covered_categories"]
    assert "target" not in result["covered_categories"]
    assert "incident" in result["covered_categories"]


def test_verifier_reaches_full_confidence_only_when_fully_covered():
    state = _state_with(
        required_categories=["incident"],
        current_plan=["incident"],
        tool_results={"incident": {"status": "ok", "count": 0}},
    )

    result = verifier_node(state)

    assert result["tool_success_rate"] == 1.0
    assert result["objective_coverage"] == 1.0
    assert result["confidence"] == 1.0


def test_verifier_records_zero_count_results_as_real_evidence():
    """A live query that legitimately found 0 items is observed evidence,
    not an absence of evidence - it must not be silently dropped."""
    state = _state_with(
        required_categories=["incident"],
        current_plan=["incident"],
        tool_results={"incident": {"status": "ok", "count": 0}},
    )

    result = verifier_node(state)

    assert any("0" in e and "incident" in e for e in result["evidence"])


def test_verifier_multi_tool_partial_failure_still_tracks_coverage_separately():
    """A tool that failed (not just one that never ran) should still surface
    as a coverage gap, distinct from the tool-execution-success ratio."""
    state = _state_with(
        required_categories=["health", "incident"],
        current_plan=["health", "incident"],
        tool_results={
            "health": {"status": "ok", "database": "ok"},
            "incident": {"status": "error", "error": "boom"},
        },
    )

    result = verifier_node(state)

    assert result["tool_success_rate"] == 0.5
    assert result["objective_coverage"] == 0.5
    assert "incident" not in result["covered_categories"]
    assert "health" in result["covered_categories"]


# ---------------------------------------------------------------------------
# 8. goal_evaluator surfaces uncovered objectives in the final answer
# ---------------------------------------------------------------------------


def test_goal_evaluator_reports_which_requested_areas_were_never_retrieved():
    state = _state_with(
        required_categories=["health", "target", "incident"],
        current_plan=["incident"],
        tool_results={"incident": {"status": "ok", "count": 0}},
    )
    state = verifier_node(state)

    result = goal_evaluator_node(state)

    assert "Objective Coverage" in result["final_answer"]
    assert "Not addressed" in result["final_answer"]
    assert "health" in result["final_answer"]
    assert "target" in result["final_answer"]
    assert "Partial" in result["final_answer"]


def test_goal_evaluator_full_coverage_reports_complete_status():
    state = _state_with(
        required_categories=["incident"],
        current_plan=["incident"],
        tool_results={"incident": {"status": "ok", "count": 0}},
    )
    state = verifier_node(state)

    result = goal_evaluator_node(state)

    assert "Complete" in result["final_answer"]
    assert "Not addressed" not in result["final_answer"]


# ---------------------------------------------------------------------------
# parallel_supervisor_node must receive and use the real repo.
#
# plan_node always populates `parallel_batches` (per matched category, or
# via its own "if not parallel_batches" fallback), and planner_router
# checks `parallel_batches` BEFORE `current_plan` - so parallel_supervisor,
# not tool_router/tool_executor, is the path almost every real plan
# actually takes. It previously called execute_tool(tool_name) with no repo
# argument at all (every other tool-calling node already receives repo from
# build_graph), so every repo-backed tool ran with repo=None here
# regardless of what repo the graph was built with - this was the actual,
# most severe cause of the live "Repository not available" failures.
# ---------------------------------------------------------------------------


def test_parallel_supervisor_node_passes_repo_to_tools(tmp_path: Path):
    repo = make_repo(tmp_path)
    create_real_incident(repo, tmp_path)

    state = initial_state("list active incidents")
    state = plan_node(state, repo=repo)
    assert state["parallel_batches"], "test assumes plan_node populates parallel_batches"

    result = parallel_supervisor_node(state, repo=repo)

    incident_result = result["tool_results"]["incident"]
    assert incident_result["status"] == "ok"
    assert incident_result["count"] == 1


def test_parallel_supervisor_node_without_repo_argument_defaults_to_none():
    """Regression guard for the exact prior bug shape: calling the node the
    old way (positional state only) must not silently succeed with fake
    data - it should visibly fail with 'Repository not available', proving
    repo really does flow through when supplied."""
    state = initial_state("list active incidents")
    state["parallel_batches"] = [["incident"]]
    state["current_plan"] = ["incident"]

    result = parallel_supervisor_node(state)

    assert result["tool_results"]["incident"]["status"] == "error"
    assert result["tool_results"]["incident"]["error"] == "Repository not available"


# ---------------------------------------------------------------------------
# 9. build_graph must not cache a graph that closes over a stale `repo`
#
# Found while re-running the fixed multi-intent flow live: build_graph()
# cached its compiled graph in a module-level global after the first call
# in the process, so every later call - regardless of the repo it passed -
# kept using whichever repo (including None) was current on that first
# build. In a long-running server this permanently broke target/incident
# tool execution with "Repository not available" even though a real repo
# was being passed on every request.
# ---------------------------------------------------------------------------


def test_build_graph_uses_the_repo_passed_on_each_call_not_a_cached_one(tmp_path: Path):
    from src.intelligence.graph import build_graph, reset_graph

    reset_graph()
    build_graph(repo=None)  # simulates an earlier call (e.g. at startup) with no repo

    repo = make_repo(tmp_path)
    create_real_incident(repo, tmp_path)

    graph = build_graph(repo=repo)
    from src.intelligence.state import initial_state as _initial_state

    state = _initial_state("list active incidents")
    result = graph.invoke(state)

    incident_result = result.get("tool_results", {}).get("incident", {})
    assert incident_result.get("status") == "ok"
    assert incident_result.get("count") == 1


def test_run_workflow_does_not_leak_repo_across_calls_with_different_repos(tmp_path: Path):
    from src.intelligence.graph import reset_graph, run_workflow

    reset_graph()
    run_workflow("list active incidents", repo=None)

    repo = make_repo(tmp_path)
    create_real_incident(repo, tmp_path)

    result = run_workflow("list active incidents", repo=repo)

    incident_result = result.get("tool_results", {}).get("incident", {})
    assert incident_result.get("status") == "ok"
    assert incident_result.get("error") != "Repository not available"
    assert incident_result.get("count") == 1
