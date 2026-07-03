"""Agent registry and collaboration orchestration for Sprint D."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.agents.base import AgentMessage, AgentResult, BaseAgent
from src.agents.domain_agents import SupervisorAgent, build_default_agents
from src.agents.state import SharedAgentState
from src.intelligence.execution_logger import generate_execution_id, utc_now
from src.intelligence.state import initial_state


@dataclass
class CollaborationAggregation:
    """Aggregated view of a multi-agent execution."""

    success: bool
    summary: str
    confidence: float
    conflicts: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    data: Dict[str, Any]


class AgentRegistry:
    """Registry for collaborative agents with shared-state orchestration."""

    def __init__(self, repo: Any = None, shared_state: Optional[SharedAgentState] = None) -> None:
        self._repo = repo
        self._shared_state = shared_state or SharedAgentState()
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.agent_id] = agent

    def unregister(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        return [agent.to_dict() for agent in self._agents.values()]

    def register_defaults(self) -> None:
        for agent in build_default_agents():
            self.register(agent)

    def _runtime_state(self, task: str) -> Dict[str, Any]:
        state = initial_state(task)
        state.update(self._shared_state.get_all())
        state.setdefault("agent_collaboration", [])
        state.setdefault("shared_state", {})
        state["_correlation_id"] = state.get("_correlation_id") or generate_execution_id()
        state["_repo"] = self._repo
        state["execution_started_at"] = state.get("execution_started_at") or utc_now()
        return state

    def _enabled_agents(self, agent_ids: Sequence[str]) -> List[BaseAgent]:
        selected: List[BaseAgent] = []
        for agent_id in agent_ids:
            agent = self._agents.get(agent_id)
            if agent is not None and agent.config.enabled:
                selected.append(agent)
        return selected

    def _resolve_conflicts(self, results: Sequence[AgentResult]) -> List[Dict[str, Any]]:
        signal_index: Dict[str, Dict[str, Any]] = {}
        conflicts: List[Dict[str, Any]] = []

        for result in results:
            signal = result.data.get("primary_signal") if isinstance(result.data, dict) else None
            if not isinstance(signal, dict):
                continue
            signal_name = str(signal.get("signal", ""))
            if not signal_name:
                continue
            entry = {
                "agent_id": result.agent_id,
                "signal": signal_name,
                "value": signal.get("value"),
                "source": signal.get("source", ""),
                "confidence": float(result.data.get("confidence", 0.0)) if isinstance(result.data, dict) else 0.0,
            }
            existing = signal_index.get(signal_name)
            if existing is None:
                signal_index[signal_name] = entry
                continue
            if existing["value"] != entry["value"]:
                winner = entry if entry["confidence"] >= existing["confidence"] else existing
                conflicts.append({
                    "signal": signal_name,
                    "values": [existing["value"], entry["value"]],
                    "agents": [existing["agent_id"], entry["agent_id"]],
                    "resolved_by": winner["agent_id"],
                    "resolution": winner["value"],
                })
                signal_index[signal_name] = winner
            else:
                # Keep the stronger confidence for identical values.
                if entry["confidence"] > existing["confidence"]:
                    signal_index[signal_name] = entry

        return conflicts

    def _merge_tool_results(self, results: Sequence[AgentResult]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for result in results:
            data = result.data if isinstance(result.data, dict) else {}
            tool_results = data.get("tool_results", {})
            if not isinstance(tool_results, dict):
                continue
            for tool_name, tool_result in tool_results.items():
                if tool_name not in merged:
                    merged[tool_name] = tool_result
                    continue
                existing = merged[tool_name]
                if existing != tool_result:
                    existing_conf = float(existing.get("confidence", 0.0)) if isinstance(existing, dict) else 0.0
                    new_conf = float(data.get("confidence", 0.0))
                    if new_conf >= existing_conf:
                        merged[tool_name] = tool_result
        return merged

    def _aggregate(self, task: str, results: Sequence[AgentResult], conflicts: Sequence[Dict[str, Any]], duration_ms: float) -> CollaborationAggregation:
        successful = [result for result in results if result.success]
        confidences = [float(result.data.get("confidence", 0.0)) for result in results if isinstance(result.data, dict)]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        conflict_penalty = min(0.25, 0.05 * len(conflicts))
        confidence = max(0.0, min(0.99, avg_confidence - conflict_penalty + (0.05 if successful else 0.0)))
        summary_parts = [result.summary for result in results if result.summary]
        if conflicts:
            summary_parts.append(f"{len(conflicts)} conflict(s) resolved")
        summary = "; ".join(summary_parts) if summary_parts else f"No agent results for {task}"
        merged_tool_results = self._merge_tool_results(results)
        approvals: List[Dict[str, Any]] = []
        for result in results:
            data = result.data if isinstance(result.data, dict) else {}
            approvals.extend([p for p in data.get("pending_approvals", []) if isinstance(p, dict)])
        metrics = {
            "task": task,
            "agent_count": len(results),
            "success_count": len(successful),
            "conflict_count": len(conflicts),
            "duration_ms": round(duration_ms, 2),
            "average_confidence": round(avg_confidence, 3),
        }
        data = {
            "task": task,
            "agent_results": [
                {
                    "agent_id": result.agent_id,
                    "success": result.success,
                    "summary": result.summary,
                    "duration_ms": result.duration_ms,
                    "data": result.data,
                }
                for result in results
            ],
            "tool_results": merged_tool_results,
            "conflicts": list(conflicts),
            "pending_approvals": approvals,
            "execution_metrics": metrics,
        }
        success = bool(successful) and not approvals and confidence >= 0.45
        return CollaborationAggregation(success=success, summary=summary, confidence=confidence, conflicts=list(conflicts), metrics=metrics, data=data)

    def _subtask_for_agent(self, agent_id: str, task: str, plan: Dict[str, Any]) -> str:
        subtasks = plan.get("subtasks", {}) if isinstance(plan, dict) else {}
        if isinstance(subtasks, dict) and agent_id in subtasks:
            return str(subtasks[agent_id])
        return task

    async def _run_agents(self, agents: Sequence[BaseAgent], task: str, shared_state: Dict[str, Any], plan: Dict[str, Any]) -> List[AgentResult]:
        if not agents:
            return []

        group_results: List[AgentResult] = []
        for group in plan.get("parallel_groups", [list(agent.agent_id for agent in agents)]):
            group_agents = [agent for agent in agents if agent.agent_id in group]
            if not group_agents:
                continue
            jobs = []
            for agent in group_agents:
                subtask = self._subtask_for_agent(agent.agent_id, task, plan)
                jobs.append(agent.process(subtask, shared_state))
            batch = await asyncio.gather(*jobs, return_exceptions=True)
            for agent, item in zip(group_agents, batch):
                if isinstance(item, AgentResult):
                    group_results.append(item)
                else:
                    group_results.append(
                        AgentResult(
                            agent_id=agent.agent_id,
                            success=False,
                            summary=str(item),
                            data={"error": str(item), "confidence": 0.0, "tool_results": {}, "pending_approvals": []},
                            duration_ms=0.0,
                        )
                    )
        return group_results

    async def dispatch_task(self, task: str, target_agent: str = "") -> Dict[str, Any]:
        start = time.time()
        shared_state = self._runtime_state(task)

        if target_agent:
            agent = self.get(target_agent)
            if agent is None:
                return {"success": False, "error": f"Agent '{target_agent}' not found"}
            if not agent.config.enabled:
                return {"success": False, "error": f"Agent '{target_agent}' is disabled"}
            result = await agent.process(task, shared_state)
            aggregation = self._aggregate(task, [result], [], (time.time() - start) * 1000)
            self._update_shared_state(aggregation, result, task)
            return {
                "success": aggregation.success,
                "agent_id": agent.agent_id,
                "summary": aggregation.summary,
                "confidence": aggregation.confidence,
                "data": aggregation.data,
                "metrics": aggregation.metrics,
                "duration_ms": round((time.time() - start) * 1000, 2),
            }

        supervisor = self.get("supervisor-agent")
        if supervisor is None:
            return {"success": False, "error": "Supervisor agent is not registered"}

        plan_result = await supervisor.process(task, shared_state)
        plan = plan_result.data.get("collaboration_plan", {}) if isinstance(plan_result.data, dict) else {}
        selected_ids = plan.get("selected_agents", []) if isinstance(plan, dict) else []
        agents = self._enabled_agents(selected_ids)
        results = await self._run_agents(agents, task, shared_state, plan)
        conflicts = self._resolve_conflicts(results)
        aggregation = self._aggregate(task, results, conflicts, (time.time() - start) * 1000)
        supervisor_messages = await supervisor.collaborate([
            AgentMessage(
                source="registry",
                target=supervisor.agent_id,
                message_type="collaboration_request",
                payload={
                    "task": task,
                    "shared_state": shared_state,
                    "agent_results": [
                        {"source": result.agent_id, "payload": {"data": result.data, "summary": result.summary}}
                        for result in results
                    ],
                    "conflicts": conflicts,
                },
            )
        ])
        if supervisor_messages:
            aggregation.data["supervisor_summary"] = supervisor_messages[0].payload
        self._update_shared_state(aggregation, plan_result, task)
        return {
            "success": aggregation.success,
            "task": task,
            "selected_agents": selected_ids,
            "summary": aggregation.summary,
            "confidence": aggregation.confidence,
            "data": aggregation.data,
            "conflicts": conflicts,
            "metrics": aggregation.metrics,
            "duration_ms": round((time.time() - start) * 1000, 2),
        }

    async def fan_out(self, task: str) -> List[AgentResult]:
        shared_state = self._runtime_state(task)
        supervisor = self.get("supervisor-agent")
        if supervisor is not None:
            plan_result = await supervisor.process(task, shared_state)
            plan = plan_result.data.get("collaboration_plan", {}) if isinstance(plan_result.data, dict) else {}
            selected_ids = plan.get("selected_agents", []) if isinstance(plan, dict) else []
            agents = self._enabled_agents(selected_ids)
            return await self._run_agents(agents, task, shared_state, plan)
        agents = [agent for agent in self._agents.values() if agent.config.enabled]
        return await self._run_agents(agents, task, shared_state, {"parallel_groups": [[agent.agent_id for agent in agents]]})

    async def collaborate(self, agents: List[str], task: str) -> Dict[str, Any]:
        start = time.time()
        shared_state = self._runtime_state(task)
        selected_agents = self._enabled_agents(agents)
        if not selected_agents:
            return {"success": False, "error": "No valid agents specified"}

        results = await self._run_agents(selected_agents, task, shared_state, {"parallel_groups": [[agent.agent_id for agent in selected_agents]]})
        conflicts = self._resolve_conflicts(results)
        aggregation = self._aggregate(task, results, conflicts, (time.time() - start) * 1000)
        self._update_shared_state(aggregation, None, task)
        return {
            "success": aggregation.success,
            "task": task,
            "agents_involved": [agent.agent_id for agent in selected_agents],
            "message_count": len(results),
            "messages": [
                {
                    "source": result.agent_id,
                    "target": "registry",
                    "type": "agent_result",
                    "payload": {"summary": result.summary, "data": result.data, "success": result.success},
                }
                for result in results
            ],
            "confidence": aggregation.confidence,
            "conflicts": conflicts,
            "metrics": aggregation.metrics,
            "duration_ms": round((time.time() - start) * 1000, 2),
        }

    def _update_shared_state(self, aggregation: CollaborationAggregation, primary_result: Optional[AgentResult], task: str) -> None:
        trace = self._shared_state.get("agent_collaboration") or []
        trace = list(trace)
        if primary_result is not None:
            trace.append({
                "agent_id": primary_result.agent_id,
                "summary": primary_result.summary,
                "success": primary_result.success,
                "data": primary_result.data,
                "timestamp": utc_now(),
            })
        for result in aggregation.data.get("agent_results", []):
            if primary_result is not None and result.get("agent_id") == primary_result.agent_id:
                continue
            trace.append({
                "agent_id": result.get("agent_id", ""),
                "summary": result.get("summary", ""),
                "success": result.get("success", False),
                "data": result.get("data", {}),
                "timestamp": utc_now(),
            })

        merged_state = self._shared_state.get_all()
        merged_state.update({
            "agent_collaboration": trace,
            "tool_results": aggregation.data.get("tool_results", {}),
            "confidence": aggregation.confidence,
            "goal_achieved": aggregation.success,
            "goal_completed": aggregation.success,
            "final_answer": aggregation.summary,
            "errors": [],
            "pending_approvals": aggregation.data.get("pending_approvals", []),
            "approval_required": bool(aggregation.data.get("pending_approvals", [])),
            "execution_metrics": aggregation.metrics,
            "shared_state": {
                **merged_state.get("shared_state", {}),
                "last_task": task,
                "last_confidence": aggregation.confidence,
                "conflicts": aggregation.conflicts,
            },
        })
        for key, value in merged_state.items():
            self._shared_state.set(key, value, agent_id="registry")

    def get_shared_state(self) -> Dict[str, Any]:
        return self._shared_state.get_all()

    def update_shared_state(self, key: str, value: Any) -> None:
        self._shared_state.set(key, value, agent_id="registry")


def create_default_registry(repo: Any = None) -> AgentRegistry:
    registry = AgentRegistry(repo=repo)
    registry.register_defaults()
    return registry
