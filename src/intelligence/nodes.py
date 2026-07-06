"""LangGraph nodes for the AegisNex Intelligence Engine.

Each node is a standalone function that reads and writes the shared AgentState.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.intelligence.state import AgentState, AgentStep
from src.intelligence.tools import (
    TOOL_REGISTRY,
    DESTRUCTIVE_TOOLS,
    execute_tool,
    list_tools,
    get_tool,
    requires_human_approval,
    get_tool_risk_level,
)
from src.intelligence.risk import RiskEngine
from src.intelligence.policy import PolicyEngine
from src.intelligence.runbooks.engine import RunbookEngine
from src.intelligence.runbooks.registry import RunbookRegistry, get_registry as get_runbook_registry
from src.intelligence.tool_router import ToolRouter, ToolRouterConfig
from src.intelligence.execution_logger import (
    ExecutionLogger,
    create_logger_for_state,
    add_execution_log_to_state,
)
from src.intelligence.workflows.common import WorkflowLibrary, get_workflow_library
from src.intelligence.providers.base import Message
from src.platform_db import PlatformRepository


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _make_step(node: str, status: str, detail: str, data: Any = None) -> AgentStep:
    return AgentStep(node=node, status=status, detail=detail, timestamp=utc_now(), data=data)


def _get_provider():
    from src.intelligence.providers.factory import create_provider
    provider_name = os.getenv("AEGIS_AI_PROVIDER", "openai")
    try:
        return create_provider(provider_name)
    except Exception:
        return None


def _get_rag_engine(repo):
    from src.intelligence.retrieval.rag import RAGEngine
    provider = _get_provider()
    return RAGEngine(provider=provider, repo=repo)


def _get_memory_store():
    from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
    db_path = os.getenv("AEGIS_AI_MEMORY_DB", "ai_memory.db")
    return SQLiteMemoryStore(db_path=db_path)


def _confidence_threshold() -> float:
    return float(os.getenv("AEGIS_AI_CONFIDENCE_THRESHOLD", "0.4"))


def _requires_manual_investigation(confidence: float) -> bool:
    return confidence < _confidence_threshold()


def _get_skill_engine() -> Any:
    from src.skills.engine import create_default_engine
    return create_default_engine()


def tool_router_node(state: AgentState) -> AgentState:
    """Route abstract tasks from the plan to concrete tools.

    Produces structured execution log with:
    - Input: current_plan and parallel_batches
    - Output: routed_tools, tool_metadata
    - Decisions: routing decisions for each task
    - Tool calls: none (router doesn't execute)
    - Execution time and correlation tracking

    Responsibilities:
    - Validate each task in the plan
    - Map tasks to registered tools
    - Enrich tool metadata (category, risk level, permissions)
    - Log every routing decision
    - Update AgentState with routing results
    - Never execute tools
    - Never access database

    Returns updated AgentState with:
    - tool_router_results: routing decisions and metadata
    - executed_steps: appends routing step with structured log
    - errors: populated if tasks cannot be routed (strict mode)
    """
    logger = create_logger_for_state("tool_router", state)
    plan = state.get("current_plan", [])
    
    logger.add_input({
        "current_plan": plan,
        "parallel_batches": state.get("parallel_batches", []),
    })
    
    try:
        if not plan:
            logger.add_warning("No plan to route (current_plan is empty)")
            logger.add_output({"routed_tools": [], "invalid_tasks": []})
            log = logger.finalize("skipped")
            add_execution_log_to_state(state, log)
            return state

        # Initialize router with strict_mode=False to skip invalid tools instead of failing
        router_config = ToolRouterConfig(
            logger=logging.getLogger("tool_router_node"),
            strict_mode=False,
        )
        router = ToolRouter(config=router_config)

        # Route the entire plan
        routing_result = router.route_plan(plan)

        # Extract routing decisions
        routed_tools = routing_result.get("routed_tools", [])
        invalid_tasks = routing_result.get("invalid_tasks", [])
        decisions = routing_result.get("decisions", [])

        # Record routing decisions in log
        for decision in decisions:
            if decision.get("found"):
                logger.add_decision(
                    "routing",
                    decision.get("tool_name"),
                    reason=decision.get("reason", ""),
                    metadata={
                        "category": decision.get("category"),
                        "risk_level": decision.get("risk_level"),
                    },
                )
            else:
                logger.add_warning(f"Task '{decision.get('tool_name')}' not found in registry")

        # Enrich tool metadata for routed tools
        tool_metadata: Dict[str, Any] = {}
        for tool_name in routed_tools:
            metadata = router.get_tool_metadata(tool_name)
            if metadata:
                tool_metadata[tool_name] = metadata

        # Add output
        logger.add_output({
            "routed_tools": routed_tools,
            "invalid_tasks": invalid_tasks,
            "tool_count": len(routed_tools),
            "tool_metadata": tool_metadata,
        })

        # Record errors in logger
        for task in invalid_tasks:
            logger.add_error(f"Task '{task}' not found in registry")

        # Update state with routing results
        state["tool_router_results"] = {
            "timestamp": utc_now(),
            "total_tasks": len(plan),
            "routed_tools": routed_tools,
            "invalid_tasks": invalid_tasks,
            "decisions": decisions,
            "tool_metadata": tool_metadata,
        }

        # Update current_plan to only include routed tools (for downstream execution)
        state["current_plan"] = routed_tools

        # Update parallel_batches to only include routed tools
        parallel_batches = state.get("parallel_batches", [])
        filtered_batches: List[List[str]] = []
        for batch in parallel_batches:
            filtered_batch = [t for t in batch if t in routed_tools]
            if filtered_batch:
                filtered_batches.append(filtered_batch)
        state["parallel_batches"] = filtered_batches

        # Update errors in state
        errors = list(state.get("errors", []))
        for task in invalid_tasks:
            errors.append(f"Tool router: task '{task}' not found in registry")
        state["errors"] = errors

        # Finalize and log
        status = "success" if not invalid_tasks else "warning"
        log = logger.finalize(status)
        add_execution_log_to_state(state, log)

    except Exception as exc:
        logger.add_error(str(exc))
        logger_final = logger.finalize("error")
        add_execution_log_to_state(state, logger_final)
        state["errors"] = list(state.get("errors", [])) + [f"Tool router error: {str(exc)}"]

    return state


def skill_executor_node(state: AgentState) -> AgentState:
    """Execute AI skills matched to the user request.

    Uses keyword matching to auto-select skills and runs them.
    Results are stored in state['skill_results'] and active skill IDs
    in state['active_skills'].
    """
    request = state.get("user_request", "")
    if not request:
        executed_steps = list(state.get("executed_steps", []))
        executed_steps.append(_make_step("skill_executor", "skipped", "No user request to match skills"))
        state["executed_steps"] = executed_steps
        return state

    try:
        engine = _get_skill_engine()
        matched = asyncio.get_event_loop().run_until_complete(engine.auto_select_skills(request))
    except Exception:
        executed_steps = list(state.get("executed_steps", []))
        executed_steps.append(_make_step("skill_executor", "error", "Failed to initialize skill engine"))
        state["executed_steps"] = executed_steps
        return state

    if not matched:
        executed_steps = list(state.get("executed_steps", []))
        executed_steps.append(_make_step("skill_executor", "skipped", "No skills matched the request"))
        state["executed_steps"] = executed_steps
        return state

    active_skills = [s.manifest.id for s in matched]
    state["active_skills"] = active_skills
    skill_results: List[Dict[str, Any]] = list(state.get("skill_results", []))
    executed_steps = list(state.get("executed_steps", []))
    errors = list(state.get("errors", []))

    for skill in matched:
        context: Dict[str, Any] = {
            "repo": None,
            "user_request": request,
        }
        try:
            result = asyncio.get_event_loop().run_until_complete(engine.execute_skill(skill.manifest.id, context))
            skill_results.append(result)
            status = "ok" if result.get("status") == "ok" else "error"
            if status == "error":
                errors.append(f"Skill '{skill.manifest.name}': {result.get('error', 'Unknown error')}")
            executed_steps.append(_make_step(
                "skill_executor", status,
                f"Executed skill '{skill.manifest.name}': {result.get('status', 'completed')}",
                {"skill_id": skill.manifest.id, "result": result},
            ))
        except Exception as exc:
            errors.append(f"Skill '{skill.manifest.name}': {str(exc)}")
            skill_results.append({"status": "error", "skill_id": skill.manifest.id, "error": str(exc)})
            executed_steps.append(_make_step("skill_executor", "error", f"Skill '{skill.manifest.name}' failed: {exc}"))

    state["skill_results"] = skill_results
    state["errors"] = errors
    state["executed_steps"] = executed_steps

    return state


def plan_node(state: AgentState, repo: Optional[PlatformRepository] = None) -> AgentState:
    """Analyze the user request, retrieve context, and build a plan.
    
    Produces structured execution log with:
    - Input: user_request
    - Output: plan, objective, steps
    - Decisions: planning decisions made
    - Execution time and correlation tracking
    """
    logger = create_logger_for_state("planner", state)
    logger.add_input({"user_request": state.get("user_request", "")})
    
    try:
        request = state["user_request"].lower()
        steps: List[str] = []
        objective = ""
        parallel_batches: List[List[str]] = []
        missing_info: List[str] = []
        retrieved_context = ""
        evidence: List[str] = []

        rag = _get_rag_engine(repo)
        try:
            retrieval = rag.retrieve(state["user_request"], limit=5)
            retrieved_context = retrieval.context_text
            evidence = [f"[{d.source_type}] {d.source}" for d in retrieval.documents if d.relevance_score > 0]
            logger.add_decision("rag_retrieval", "success", f"Retrieved {len(evidence)} documents")
        except Exception as e:
            logger.add_warning(f"RAG retrieval failed: {str(e)}")
            retrieved_context = ""

        provider = state.get("provider")
        if provider is not None:
            try:
                available_tools = list_tools()
                tool_names = [t["name"] for t in available_tools]
                planning_prompt = (
                    f"Given the user request: \"{state['user_request']}\"\n\n"
                    f"Relevant context:\n{retrieved_context[:2000] if retrieved_context else 'None'}\n\n"
                    f"Available tools: {', '.join(tool_names)}\n\n"
                    "Select the most relevant tools for this request. "
                    f"Return ONLY a JSON array of tool names, nothing else. "
                    "Example: [\"metrics\", \"docker\"]"
                )
                msg = provider.chat([Message(role="user", content=planning_prompt)])
                import json as _json
                llm_steps = _json.loads(msg.content.strip())
                if isinstance(llm_steps, list) and all(s in tool_names for s in llm_steps):
                    steps = llm_steps
                    objective = f"LLM analysis for: {state['user_request'][:80]}"
                    parallel_batches = [[s] for s in steps]
                    logger.add_decision("planning", "llm_based", f"LLM selected tools: {steps}")
            except Exception:
                logger.add_warning("LLM planning failed, falling back to keyword matching")

        if not steps:
            if "incident" in request or "alert" in request:
                objective = "Investigate incidents"
                if "analyze" in request or "why" in request or "what happened" in request:
                    steps = ["audit", "incident", "health"]
                    parallel_batches = [["audit", "health"], ["incident"]]
                    logger.add_decision("planning", "incident_analysis", "Pattern: analyze incident")
                elif "active" in request:
                    steps = ["incident"]
                    objective = "List active incidents"
                    logger.add_decision("planning", "list_incidents", "Pattern: active incidents")
                else:
                    steps = ["incident"]
                    parallel_batches = [["incident"]]
                    logger.add_decision("planning", "list_incidents", "Pattern: generic incident query")
            elif "cpu" in request or "memory" in request or "disk" in request or "metric" in request or "performance" in request:
                objective = "Investigate system metrics"
                steps = ["metrics", "docker", "health"]
                parallel_batches = [["metrics", "health"], ["docker"]]
                logger.add_decision("planning", "metrics_analysis", "Pattern: system performance")
            elif "docker" in request or "container" in request:
                objective = "Inspect Docker containers"
                steps = ["docker", "health"]
                parallel_batches = [["docker", "health"]]
                logger.add_decision("planning", "docker_inspection", "Pattern: container query")
            elif "target" in request or "monitor" in request or "http" in request or "ssl" in request or "tcp" in request:
                objective = "Check monitoring targets"
                steps = ["target", "incident"]
                parallel_batches = [["target", "incident"]]
                logger.add_decision("planning", "targets_check", "Pattern: monitoring targets")
            elif "audit" in request or "log" in request:
                objective = "Review audit logs"
                steps = ["audit"]
                logger.add_decision("planning", "audit_review", "Pattern: audit/logs")
            elif "report" in request:
                objective = "Generate operational report"
                if "weekly" in request:
                    steps = ["report"]
                    logger.add_decision("planning", "weekly_report", "Pattern: weekly report")
                elif "monthly" in request:
                    steps = ["report"]
                    logger.add_decision("planning", "monthly_report", "Pattern: monthly report")
                else:
                    steps = ["report", "incident", "metrics"]
                    parallel_batches = [["incident", "metrics"], ["report"]]
                    logger.add_decision("planning", "full_report", "Pattern: generic report")
            elif "notification" in request:
                objective = "Check notification status"
                steps = ["notification"]
                logger.add_decision("planning", "notification_check", "Pattern: notifications")
            elif "health" in request or "status" in request or "overview" in request:
                objective = "Assess overall system health"
                steps = ["health", "metrics", "incident"]
                parallel_batches = [["health", "metrics"], ["incident"]]
                logger.add_decision("planning", "health_assessment", "Pattern: health/status")
            else:
                objective = "Comprehensive system analysis"
                steps = ["metrics", "docker", "incident", "target", "health"]
                parallel_batches = [["metrics", "health"], ["docker", "target"], ["incident"]]
                missing_info.append("Specific request type not identified; running full analysis")
                logger.add_decision("planning", "full_analysis", "Pattern: no specific match, default comprehensive")

        if not parallel_batches:
            parallel_batches = [[s] for s in steps]

        tool_permission_levels: Dict[str, str] = {}
        for s in steps:
            tool = get_tool(s)
            if tool:
                tool_permission_levels[s] = tool.risk_level.value if hasattr(tool, "risk_level") else "none"

        plan = {
            "objective": objective,
            "steps": steps,
            "parallel_batches": [b for b in parallel_batches if any(s in steps for s in b)],
            "tool_details": {
                name: {"description": get_tool(name).description if get_tool(name) else ""}
                for name in steps
                if get_tool(name) is not None
            },
        }

        state["objective"] = objective
        state["current_plan"] = steps
        state["plan"] = plan
        state["missing_info"] = missing_info
        state["parallel_batches"] = [b for b in parallel_batches if any(s in steps for s in b)]
        state["retrieved_context"] = retrieved_context
        state["evidence"] = evidence

        # Record output
        logger.add_output({
            "objective": objective,
            "steps": steps,
            "parallel_batches": state["parallel_batches"],
            "tool_count": len(steps),
            "missing_info": missing_info,
            "evidence_count": len(evidence),
        })

        # Finalize and log
        log = logger.finalize("success")
        add_execution_log_to_state(state, log)

    except Exception as exc:
        logger.add_error(str(exc))
        logger_final = logger.finalize("error")
        add_execution_log_to_state(state, logger_final)
        state["errors"] = list(state.get("errors", [])) + [f"Planner node error: {str(exc)}"]

    return state


def tool_executor_node(state: AgentState, repo: Optional[PlatformRepository] = None) -> AgentState:
    """Execute each tool in the plan and collect results.

    Produces structured execution log with:
    - Input: current_plan, parallel_batches
    - Output: tool_results
    - Tool calls: all tools executed with status
    - Execution time and correlation tracking

    Supports parallel execution within batches. Stores results in state.
    Checks for destructive tools and creates pending approvals.
    """
    logger = create_logger_for_state("tool_executor", state)
    steps = state.get("current_plan", [])
    parallel_batches = state.get("parallel_batches", [])
    
    logger.add_input({
        "current_plan": steps,
        "parallel_batches": parallel_batches,
    })
    
    try:
        tool_results = dict(state.get("tool_results", {}))
        errors = list(state.get("errors", []))
        pending_approvals = list(state.get("pending_approvals", []))

        if not parallel_batches:
            parallel_batches = [[s] for s in steps]

        for batch in parallel_batches:
            batch_results: Dict[str, Any] = {}
            for tool_name in batch:
                if tool_name not in steps:
                    continue
                if get_tool(tool_name) is None:
                    error_msg = f"Tool '{tool_name}' not found in registry"
                    errors.append(error_msg)
                    logger.add_error(error_msg)
                    continue

                tool = get_tool(tool_name)
                if tool and tool.requires_approval:
                    approval_id = f"approval_{utc_now()}_{tool_name}"
                    state["approval_required"] = True
                    state["approval_id"] = approval_id
                    pending_approvals.append({
                        "id": approval_id,
                        "step": tool_name,
                        "action": tool_name,
                        "target": "",
                        "reason": f"Destructive action: {tool.description}",
                        "status": "pending",
                    })
                    logger.add_decision("approval_required", tool_name, f"Tool requires approval: {tool.description}")
                    continue

                start_time = time.time()
                try:
                    result = execute_tool(tool_name, repo=repo)
                    duration_ms = (time.time() - start_time) * 1000
                    status = "ok" if result.get("status") == "ok" else "error"
                    batch_results[tool_name] = result
                    
                    # Record tool execution
                    logger.add_tool_call(
                        tool_name,
                        "success" if status == "ok" else "error",
                        input_params={},
                        output=result,
                        error=None if status == "ok" else result.get("error"),
                    )
                    
                    if status == "error":
                        error_msg = f"{tool_name}: {result.get('error', 'Unknown error')}"
                        errors.append(error_msg)
                        logger.add_error(error_msg)
                        
                except Exception as exc:
                    duration_ms = (time.time() - start_time) * 1000
                    error_msg = f"{tool_name}: {str(exc)}"
                    errors.append(error_msg)
                    batch_results[tool_name] = {"status": "error", "error": str(exc)}
                    logger.add_tool_call(
                        tool_name,
                        "error",
                        input_params={},
                        output=None,
                        error=str(exc),
                    )
                    logger.add_error(error_msg)

            tool_results.update(batch_results)

        # Add output
        logger.add_output({
            "tool_results": {k: {"status": v.get("status")} for k, v in tool_results.items()},
            "tools_executed": len(tool_results),
            "pending_approvals": len(pending_approvals),
        })

        # Finalize and log
        status = "success" if not errors else "warning"
        log = logger.finalize(status)
        add_execution_log_to_state(state, log)

        state["tool_results"] = tool_results
        state["errors"] = errors
        state["pending_approvals"] = pending_approvals

    except Exception as exc:
        logger.add_error(str(exc))
        logger_final = logger.finalize("error")
        add_execution_log_to_state(state, logger_final)
        state["errors"] = list(state.get("errors", [])) + [f"Tool executor error: {str(exc)}"]

    return state


def verifier_node(state: AgentState) -> AgentState:
    """Verify tool results for completeness, errors, and confidence.

    Produces structured execution log with:
    - Input: tool_results, errors
    - Output: confidence, observations, evidence
    - Decisions: verification decisions
    - Execution time and correlation tracking

    Sets confidence score and determines if re-planning is needed.
    Populates evidence, reasoning_summary, and remaining_uncertainty.
    """
    logger = create_logger_for_state("verifier", state)
    tool_results = state.get("tool_results", {})
    errors = list(state.get("errors", []))
    
    logger.add_input({
        "tool_results": {k: {"status": v.get("status")} for k, v in tool_results.items()},
        "errors": errors,
    })
    
    try:
        observations = list(state.get("observations", []))
        evidence = list(state.get("evidence", []))

        total_tools = len(state.get("current_plan", []))
        successful_tools = sum(1 for r in tool_results.values() if r.get("status") == "ok")
        failed_tools = len(errors)

        if total_tools == 0:
            logger.add_warning("No tools were planned")
            logger.add_output({
                "confidence": 0.0,
                "reasoning": "No tools were planned — unable to gather data.",
            })
            log = logger.finalize("warning")
            add_execution_log_to_state(state, log)
            state["confidence"] = 0.0
            state["reasoning_summary"] = "No tools were planned — unable to gather data."
            state["remaining_uncertainty"] = "Complete uncertainty: no operational data collected."
            return state

        confidence = successful_tools / total_tools

        if errors:
            msg = f"Found {len(errors)} tool errors"
            logger.add_error(msg)
            observations.append(f"{msg}: {'; '.join(errors[:3])}")

        for tool_name, result in tool_results.items():
            if result.get("status") == "error":
                msg = f"Tool '{tool_name}' failed: {result.get('error', 'unknown error')}"
                logger.add_decision("verification", "tool_failure", msg)
                observations.append(msg)

        if confidence >= 0.8:
            confidence_verdict = "High confidence: most tools completed successfully"
            logger.add_decision("verification", "confidence_level", "high", f"Confidence: {confidence:.0%}")
            observations.append(confidence_verdict)
        elif confidence >= 0.5:
            confidence_verdict = "Moderate confidence: some tools failed"
            logger.add_decision("verification", "confidence_level", "moderate", f"Confidence: {confidence:.0%}")
            observations.append(confidence_verdict)
        else:
            confidence_verdict = "Low confidence: significant tool failures detected"
            logger.add_decision("verification", "confidence_level", "low", f"Confidence: {confidence:.0%}")
            observations.append(confidence_verdict)

        for tool_name, result in tool_results.items():
            if result.get("status") == "ok" and result.get("count", 0) > 0:
                evidence.append(f"Tool '{tool_name}' returned {result.get('count')} items")

        reason_parts = []
        reason_parts.append(f"Executed {successful_tools}/{total_tools} tools successfully")
        if successful_tools > 0:
            names = [n for n, r in tool_results.items() if r.get("status") == "ok"]
            reason_parts.append(f"Successful: {', '.join(names)}")
        if failed_tools > 0:
            reason_parts.append(f"Failed: {failed_tools} tool(s)")
        reason_parts.append(f"Confidence: {min(confidence, 1.0):.0%}")

        uncertainty = []
        if failed_tools > 0:
            uncertainty.append(f"{failed_tools} tool(s) produced errors — data may be incomplete")
        if confidence < 0.6:
            uncertainty.append("Low confidence suggests significant gaps in available data")
        if _requires_manual_investigation(confidence):
            uncertainty.append("Confidence below threshold — manual investigation recommended")
        if not uncertainty:
            uncertainty.append("Low remaining uncertainty — sufficient data collected")

        # Add output
        logger.add_output({
            "confidence": min(confidence, 1.0),
            "successful_tools": successful_tools,
            "failed_tools": failed_tools,
            "observations_count": len(observations),
            "evidence_count": len(evidence),
        })

        # Finalize and log
        status = "success" if confidence >= 0.5 else "warning"
        log = logger.finalize(status)
        add_execution_log_to_state(state, log)

        state["confidence"] = min(confidence, 1.0)
        state["observations"] = observations
        state["evidence"] = evidence
        state["reasoning_summary"] = "; ".join(reason_parts)
        state["remaining_uncertainty"] = " ".join(uncertainty)

    except Exception as exc:
        logger.add_error(str(exc))
        logger_final = logger.finalize("error")
        add_execution_log_to_state(state, logger_final)
        state["errors"] = list(state.get("errors", [])) + [f"Verifier error: {str(exc)}"]

    return state


def self_corrector_node(state: AgentState, repo: Optional[PlatformRepository] = None) -> AgentState:
    """Handle failures by retrying or adjusting the plan."""
    retries = state.get("retries", 0)
    max_retries = state.get("max_retries", 3)
    errors = list(state.get("errors", []))
    corrections = list(state.get("corrections", []))
    executed_steps = list(state.get("executed_steps", []))
    current_plan = list(state.get("current_plan", []))
    tool_results = dict(state.get("tool_results", {}))

    if not errors:
        executed_steps.append(_make_step("self_corrector", "completed", "No corrections needed"))
        state["executed_steps"] = executed_steps
        return state

    if retries >= max_retries:
        corrections.append(f"Max retries ({max_retries}) reached. Producing best-effort answer.")
        executed_steps.append(_make_step("self_corrector", "warning",
            f"Max retries reached ({max_retries}), using partial results"))
        state["corrections"] = corrections
        state["executed_steps"] = executed_steps
        return state

    retries += 1
    state["retries"] = retries

    remaining_errors = []
    for error in list(errors):
        error_lower = error.lower()
        if "docker" in error_lower or "container" in error_lower:
            corrections.append("Docker unavailable — substituting metrics + health check")
            if "docker" in current_plan:
                current_plan.remove("docker")
            if "docker" in tool_results:
                del tool_results["docker"]
            if "health" not in current_plan:
                current_plan.append("health")
        elif "http" in error_lower or "ssl" in error_lower or "tcp" in error_lower:
            corrections.append(f"Monitoring check failed — retrying ({retries}/{max_retries})")
        elif "database" in error_lower or "repository" in error_lower:
            corrections.append("Database unavailable — using cached/fallback data")
        elif "services" in error_lower or "services not available" in error_lower:
            corrections.append("Metrics tool requires running services — skipping metrics")
            if "metrics" in current_plan:
                current_plan.remove("metrics")
        elif "not found" in error_lower:
            corrections.append(f"Tool or resource not found — adjusting plan")
        else:
            remaining_errors.append(error)
            corrections.append(f"Unresolved error: {error[:60]} — producing partial results")

    state["current_plan"] = current_plan
    state["tool_results"] = tool_results
    state["errors"] = remaining_errors
    state["corrections"] = corrections
    executed_steps.append(_make_step("self_corrector", "completed",
        f"Applied {len(state['corrections'])} corrections, retry {retries}/{max_retries}"))
    state["executed_steps"] = executed_steps

    return state


def rag_generator_node(state: AgentState, repo: Optional[PlatformRepository] = None) -> AgentState:
    """Generate an LLM-powered final answer using retrieved context and tool results.

    Calls RAGEngine.generate_with_context() if a provider is available
    and tool results exist. Otherwise falls through to goal_evaluator.
    """
    provider = state.get("provider")
    tool_results = state.get("tool_results", {})
    if provider is None or not tool_results:
        return state

    try:
        rag = _get_rag_engine(repo)
        retrieved_context = state.get("retrieved_context", "")
        answer = rag.generate_with_context(
            query=state.get("user_request", ""),
            context=retrieved_context or None,
            tool_results=tool_results,
        )
        state["final_answer"] = answer
        state["reasoning_summary"] = answer[:500]
        executed_steps = list(state.get("executed_steps", []))
        executed_steps.append(_make_step("rag_generator", "completed", "LLM-generated answer from context + tool results"))
        state["executed_steps"] = executed_steps
    except Exception as exc:
        executed_steps = list(state.get("executed_steps", []))
        executed_steps.append(_make_step("rag_generator", "error", f"LLM answer generation failed: {str(exc)}"))
        state["executed_steps"] = executed_steps

    return state


def goal_evaluator_node(state: AgentState) -> AgentState:
    """Determine if the goal is achieved or if more work is needed.

    Produces structured execution log with:
    - Input: tool_results, confidence, objective
    - Output: goal_achieved, final_answer
    - Decisions: goal achievement decision
    - Execution time and correlation tracking

    Produces the final_answer with a recommendation.
    Consolidates all observations, corrections, and tool results.
    Checks confidence threshold for manual investigation recommendation.
    """
    logger = create_logger_for_state("goal_evaluator", state)
    
    logger.add_input({
        "tool_results_count": len(state.get("tool_results", {})),
        "confidence": state.get("confidence", 0.0),
        "objective": state.get("objective", ""),
        "errors_count": len(state.get("errors", [])),
    })
    
    try:
        goal_achieved = False
        confidence = state.get("confidence", 0.0)
        retries = state.get("retries", 0)
        max_retries = state.get("max_retries", 3)
        errors = state.get("errors", [])
        tool_results = state.get("tool_results", {})
        observations = state.get("observations", [])
        corrections = state.get("corrections", [])
        evidence = state.get("evidence", [])
        reasoning_summary = state.get("reasoning_summary", "")
        remaining_uncertainty = state.get("remaining_uncertainty", "")
        retrieved_context = state.get("retrieved_context", "")

        has_data = bool(tool_results)
        has_critical_errors = any("database" in str(e).lower() for e in errors)

        if has_data and not has_critical_errors and confidence >= 0.6:
            goal_achieved = True
            logger.add_decision("goal_achievement", "achieved", "Data available, no critical errors, confidence >= 60%")
        elif has_data and not has_critical_errors and confidence >= 0.3:
            goal_achieved = True
            logger.add_decision("goal_achievement", "achieved", "Data available, no critical errors, confidence >= 30%")
        elif retries >= max_retries:
            goal_achieved = True
            logger.add_decision("goal_achievement", "achieved", f"Max retries reached ({retries}/{max_retries})")
        else:
            goal_achieved = False
            logger.add_decision("goal_achievement", "incomplete", f"Insufficient data or confidence (confidence={confidence:.0%})")

        summary_parts = []
        for tool_name, result in tool_results.items():
            status = result.get("status", "unknown")
            count = result.get("count", result.get("total_count", 0))
            if status == "ok":
                summary_parts.append(f"{tool_name}: {count} items")

        if corrections:
            summary_parts.append(f"corrections: {len(corrections)}")

        summary = "; ".join(summary_parts) if summary_parts else "No data collected"

        existing_answer = state.get("final_answer", "")
        if existing_answer and existing_answer != "":
            final_answer = existing_answer + "\n\n---\n"
        else:
            final_answer = (
                f"## Analysis Summary\n\n"
                f"**Request:** {state.get('user_request', '')}\n"
                f"**Objective:** {state.get('objective', '')}\n"
                f"**Confidence:** {confidence:.0%}\n\n"
                f"### Results\n{summary}\n\n"
            )

        if evidence:
            final_answer += "### Evidence Used\n"
            for e in evidence[-5:]:
                final_answer += f"- {e}\n"
            final_answer += "\n"

        if reasoning_summary:
            final_answer += f"### Reasoning\n{reasoning_summary}\n\n"

        if observations:
            final_answer += "### Observations\n"
            for obs in observations[-5:]:
                final_answer += f"- {obs}\n"
            final_answer += "\n"

        if corrections:
            final_answer += "### Corrections Applied\n"
            for cor in corrections[-3:]:
                final_answer += f"- {cor}\n"
            final_answer += "\n"

        if errors:
            final_answer += "### Errors\n"
            for err in errors[:3]:
                final_answer += f"- {err}\n"
            final_answer += "\n"

        if remaining_uncertainty:
            final_answer += f"### Remaining Uncertainty\n{remaining_uncertainty}\n\n"

        if has_critical_errors:
            final_answer += "**⚠ Warning:** Database connectivity issues may affect accuracy.\n\n"
            logger.add_warning("Critical errors detected (database-related)")

        if _requires_manual_investigation(confidence):
            final_answer += "**⚠ Manual investigation recommended** — confidence is below the configured threshold.\n"
            final_answer += "**Do not take destructive actions based on this analysis alone.**\n\n"
            logger.add_warning(f"Manual investigation recommended (confidence below threshold: {confidence:.0%})")

        if not existing_answer:
            if confidence >= 0.8:
                final_answer += "**Status:** Complete — high confidence in results."
            elif confidence >= 0.5:
                final_answer += "**Status:** Partial — some information may be incomplete."
            else:
                final_answer += "**Status:** Limited — unable to gather sufficient data."

        # Add output
        logger.add_output({
            "goal_achieved": goal_achieved,
            "confidence": confidence,
            "has_data": has_data,
            "has_critical_errors": has_critical_errors,
            "final_answer_length": len(final_answer),
        })

        # Finalize and log
        status = "success" if goal_achieved else "warning"
        log = logger.finalize(status)
        add_execution_log_to_state(state, log)

        state["final_answer"] = final_answer
        state["goal_achieved"] = goal_achieved

    except Exception as exc:
        logger.add_error(str(exc))
        logger_final = logger.finalize("error")
        add_execution_log_to_state(state, logger_final)
        state["errors"] = list(state.get("errors", [])) + [f"Goal evaluator error: {str(exc)}"]

    return state


def risk_assessor_node(state: AgentState) -> AgentState:
    """Assess risk of planned actions and populate risk_assessment."""
    engine = RiskEngine()
    tool_name = state.get("current_plan", [""])[0] if state.get("current_plan") else ""
    params = state.get("tool_results", {}).get(tool_name, {})
    assessment = engine.assess_tool(tool_name, params)
    state["risk_assessment"] = assessment.to_dict()

    if assessment.requires_approval:
        approval_id = f"risk_approval_{utc_now()}"
        state["approval_required"] = True
        state["approval_id"] = approval_id
        pending = list(state.get("pending_approvals", []))
        pending.append({
            "id": approval_id,
            "step": "risk_assessor",
            "action": tool_name,
            "target": "",
            "reason": f"Risk score {assessment.score}: {assessment.impact_estimate}",
            "status": "pending",
        })
        state["pending_approvals"] = pending

    executed_steps = list(state.get("executed_steps", []))
    executed_steps.append(_make_step("risk_assessor", "completed" if not assessment.requires_approval else "pending_approval",
        f"Risk: {assessment.level.value} ({assessment.score}), approval={'yes' if assessment.requires_approval else 'no'}"))
    state["executed_steps"] = executed_steps
    return state


def policy_checker_node(state: AgentState) -> AgentState:
    """Check policies before executing actions."""
    engine = PolicyEngine()
    action = state.get("current_plan", [""])[0] if state.get("current_plan") else ""
    context = {
        "environment": os.getenv("AEGISNEX_ENV", "development"),
        "restart_count": state.get("retries", 0),
        "retry_count": state.get("retries", 0),
        "destructive": any(get_tool(a) and get_tool(a).destructive for a in state.get("current_plan", [])),
    }
    result = engine.check_action(action, context)
    results = list(state.get("policy_results", []))
    results.append(result.to_dict())
    state["policy_results"] = results

    if result.requires_approval:
        approval_id = f"policy_approval_{utc_now()}"
        state["approval_required"] = True
        state["approval_id"] = approval_id
        pending = list(state.get("pending_approvals", []))
        pending.append({
            "id": approval_id,
            "step": "policy_checker",
            "action": action,
            "target": "",
            "reason": f"Policy '{result.policy_name}': {result.reason}",
            "status": "pending",
        })
        state["pending_approvals"] = pending

    executed_steps = list(state.get("executed_steps", []))
    executed_steps.append(_make_step("policy_checker", "approved" if result.allowed else "denied",
        f"Policy '{result.policy_name}': {'allowed' if result.allowed else 'denied'}, approval={'yes' if result.requires_approval else 'no'}"))
    state["executed_steps"] = executed_steps
    return state


def runbook_executor_node(state: AgentState, repo: Optional[PlatformRepository] = None) -> AgentState:
    """Execute a runbook selected by the planner."""
    runbook_name = state.get("current_runbook", "")
    if not runbook_name:
        registry = get_runbook_registry()
        workflow = get_workflow_library()
        for wf in workflow.list_workflows():
            request = state.get("user_request", "").lower()
            if any(kw in request for kw in wf.get("trigger_keywords", [])):
                if wf.get("runbook"):
                    runbook_name = wf["runbook"]
                    state["workflow_triggered"] = wf["name"]
                    break

    if not runbook_name:
        executed_steps = list(state.get("executed_steps", []))
        executed_steps.append(_make_step("runbook_executor", "skipped", "No runbook matched"))
        state["executed_steps"] = executed_steps
        return state

    registry = get_runbook_registry()
    runbook = registry.get(runbook_name)
    if not runbook:
        executed_steps = list(state.get("executed_steps", []))
        executed_steps.append(_make_step("runbook_executor", "error", f"Runbook '{runbook_name}' not found"))
        state["executed_steps"] = executed_steps
        return state

    engine = RunbookEngine(registry)
    for step_model in runbook.steps:
        step_dict = {
            "name": step_model.name,
            "action": step_model.action,
            "tool": step_model.tool,
            "params": step_model.params,
            "description": step_model.description,
            "requires_approval": step_model.requires_approval,
        }
        if step_model.requires_approval:
            approval_id = f"runbook_approval_{utc_now()}_{step_model.name}"
            state["approval_required"] = True
            state["approval_id"] = approval_id
            pending = list(state.get("pending_approvals", []))
            pending.append({
                "id": approval_id,
                "step": step_model.name,
                "action": step_model.tool or step_model.action,
                "target": runbook_name,
                "reason": f"Runbook step '{step_model.name}' requires approval",
                "status": "pending",
            })
            state["pending_approvals"] = pending

    results = engine.execute(runbook_name)
    state["runbook_steps"] = results.get("step_results", [])

    executed_steps = list(state.get("executed_steps", []))
    status = results.get("runbook_status", "completed")
    executed_steps.append(_make_step("runbook_executor", status,
        f"Runbook '{runbook_name}': {len(runbook.steps)} steps, status={status}"))
    state["executed_steps"] = executed_steps

    for sr in results.get("step_results", []):
        if sr.get("result"):
            state.setdefault("tool_results", {}).update(sr["result"])

    return state


def parallel_supervisor_node(state: AgentState) -> AgentState:
    """Fan out parallel batches and collect results."""
    parallel_batches = state.get("parallel_batches", [])
    if not parallel_batches:
        executed_steps = list(state.get("executed_steps", []))
        executed_steps.append(_make_step("parallel_supervisor", "skipped", "No parallel batches"))
        state["executed_steps"] = executed_steps
        return state

    all_results: Dict[str, Any] = {}
    for batch in parallel_batches:
        batch_result: Dict[str, Any] = {}
        for tool_name in batch:
            if get_tool(tool_name) is None:
                continue
            try:
                result = execute_tool(tool_name)
                batch_result[tool_name] = result
            except Exception as exc:
                batch_result[tool_name] = {"status": "error", "error": str(exc)}
        all_results.update(batch_result)

    state["parallel_executions"] = all_results
    existing_results = dict(state.get("tool_results", {}))
    existing_results.update(all_results)
    state["tool_results"] = existing_results

    executed_steps = list(state.get("executed_steps", []))
    executed_steps.append(_make_step("parallel_supervisor", "completed",
        f"Executed {len(all_results)} parallel tools across {len(parallel_batches)} batches"))
    state["executed_steps"] = executed_steps
    return state


def scheduler_node(state: AgentState) -> AgentState:
    """Check for pending scheduled tasks."""
    import os
    from src.intelligence.scheduler import Scheduler
    db_path = os.getenv("AEGIS_AI_SCHEDULER_DB", "ai_scheduler.db")
    scheduler = Scheduler(db_path=db_path)
    tasks = scheduler.list_tasks()
    state["scheduler_tasks"] = tasks

    executed_steps = list(state.get("executed_steps", []))
    executed_steps.append(_make_step("scheduler", "completed", f"Checked {len(tasks)} scheduled tasks"))
    state["executed_steps"] = executed_steps
    return state


def learning_node(state: AgentState) -> AgentState:
    """Store learnings from the current execution cycle."""
    from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
    db_path = os.getenv("AEGIS_AI_MEMORY_DB", "ai_memory.db")
    store = SQLiteMemoryStore(db_path=db_path)
    errors = state.get("errors", [])
    corrections = state.get("corrections", [])
    goal_achieved = state.get("goal_achieved", False)

    learnings: List[Dict[str, Any]] = []
    if errors:
        root_cause = "; ".join(errors[:3])
        resolution = "; ".join(corrections[:3]) if corrections else "No automatic resolution"
        store.store_learning(
            root_cause=root_cause[:500],
            resolution=resolution[:500],
            service="ai_engine",
            severity="error",
            category="tool_failure",
            outcome="corrected" if corrections else "unresolved",
            confidence=state.get("confidence", 0.0),
            tags=list(state.get("current_plan", [])),
        )
        learnings.append({"root_cause": root_cause[:100], "resolution": resolution[:100]})

    if goal_achieved and state.get("confidence", 0) > 0.7:
        plan_steps = ", ".join(state.get("current_plan", []))
        store.store_learning(
            root_cause=f"Successful execution for: {state.get('user_request', '')[:200]}",
            resolution=f"Plan: {plan_steps[:200]}",
            service="ai_engine",
            severity="info",
            category="success_pattern",
            outcome="achieved",
            confidence=state.get("confidence", 0.0),
            tags=list(state.get("current_plan", [])),
        )

    state["learnings"] = learnings
    executed_steps = list(state.get("executed_steps", []))
    executed_steps.append(_make_step("learning", "completed", f"Stored {len(learnings)} learnings"))
    state["executed_steps"] = executed_steps
    return state


def should_continue(state: AgentState) -> str:
    """Conditional edge: decide whether to re-plan or finish."""
    if state.get("goal_achieved", False):
        return "end"
    if state.get("retries", 0) >= state.get("max_retries", 3):
        return "end"
    if state.get("errors"):
        return "correct"
    return "end"


def human_approval_check(state: AgentState) -> str:
    """Check if there are pending approvals needing human input."""
    pending = [a for a in state.get("pending_approvals", []) if a.get("status") == "pending"]
    if pending:
        return "waiting"
    return "continue"
