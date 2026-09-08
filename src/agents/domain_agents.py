"""Specialized collaborative agents for Sprint D.

These agents build on the existing backend services and tool registry without
re-implementing Sprint C LangGraph nodes or duplicating backend APIs.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.agents.base import AgentConfig, AgentMessage, AgentResult, AgentType, BaseAgent
from src.intelligence.execution_logger import ExecutionLogger
from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
from src.intelligence.tools import execute_tool, is_destructive, requires_human_approval


@dataclass(frozen=True)
class AgentDomainSpec:
    agent_id: str
    name: str
    agent_type: AgentType
    description: str
    keywords: Sequence[str]
    owned_tools: Sequence[str]


class CollaborativeDomainAgent(BaseAgent):
    """Base class for domain agents that use existing backend services only."""

    domain_name: str = "general"
    keywords: Sequence[str] = ()
    owned_tools: Sequence[str] = ()

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    def supports(self, task: str) -> bool:
        task_lower = task.lower()
        return any(keyword in task_lower for keyword in self.keywords)

    def _repo(self, shared_state: dict) -> Any:
        return shared_state.get("_repo")

    def _correlation_id(self, shared_state: dict) -> str:
        return str(shared_state.get("_correlation_id", ""))

    def _memory_store(self) -> SQLiteMemoryStore:
        db_path = os.getenv("AEGIS_AI_MEMORY_DB", "aegisnex.db")
        return SQLiteMemoryStore(db_path=db_path)

    def _tool_kwargs(self, tool_name: str, task: str) -> dict[str, Any]:
        task_lower = task.lower()
        if tool_name == "incident":
            if "active" in task_lower:
                return {"action": "active"}
            return {"action": "list"}
        if tool_name == "report":
            if "monthly" in task_lower:
                return {"report_type": "monthly"}
            return {"report_type": "weekly"}
        if tool_name == "audit":
            return {"limit": 50}
        if tool_name == "notification":
            return {"action": "list"}
        if tool_name == "target":
            return {"action": "list"}
        return {}

    def _score_confidence(
        self, successful: int, total: int, pending_approvals: int = 0, conflicts: int = 0
    ) -> float:
        if total <= 0:
            return 0.15
        base = successful / total
        penalty = min(0.2, pending_approvals * 0.05) + min(0.3, conflicts * 0.1)
        return max(0.05, min(0.98, base - penalty + 0.1))

    def _summarize(self, tool_results: dict[str, dict[str, Any]]) -> str:
        if not tool_results:
            return f"{self.config.name}: no applicable tools were executed"
        parts: list[str] = []
        for tool_name, result in tool_results.items():
            status = result.get("status", "unknown")
            if tool_name == "metrics":
                parts.append(f"metrics={result.get('count', 0)}")
            elif tool_name == "docker":
                parts.append(f"containers={result.get('count', 0)}")
            elif tool_name == "incident":
                parts.append(f"incidents={result.get('count', 0)}")
            elif tool_name == "report":
                parts.append(f"report={result.get('report_type', 'unknown')}")
            elif tool_name == "audit":
                parts.append(f"audit_logs={result.get('count', 0)}")
            elif tool_name == "notification":
                parts.append(f"notifications={result.get('total_count', 0)}")
            elif tool_name == "health":
                parts.append(f"health={status}")
            else:
                parts.append(f"{tool_name}={status}")
        return f"{self.config.name}: " + "; ".join(parts)

    def _primary_signal(self, tool_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        if not tool_results:
            return {"status": "skipped", "detail": "No tools executed"}
        if "health" in tool_results:
            result = tool_results["health"]
            healthy = not result.get("status") == "error" and result.get("cpu_percent") is not None
            return {
                "signal": "system_health",
                "value": "healthy" if healthy else "degraded",
                "source": "health",
            }
        if "metrics" in tool_results:
            result = tool_results["metrics"]
            return {
                "signal": "system_health",
                "value": "observed" if result.get("count", 0) > 0 else "unknown",
                "source": "metrics",
            }
        if "docker" in tool_results:
            result = tool_results["docker"]
            return {
                "signal": "container_state",
                "value": "active" if result.get("count", 0) > 0 else "empty",
                "source": "docker",
            }
        if "incident" in tool_results:
            result = tool_results["incident"]
            return {
                "signal": "incident_state",
                "value": "active" if result.get("count", 0) > 0 else "clear",
                "source": "incident",
            }
        return {"signal": "summary", "value": "collected", "source": next(iter(tool_results))}

    async def process(self, task: str, shared_state: dict) -> AgentResult:
        start = time.time()
        correlation_id = self._correlation_id(shared_state)
        logger = ExecutionLogger(self.agent_id, correlation_id=correlation_id or None)
        logger.add_input(
            {
                "task": task,
                "shared_keys": sorted(k for k in shared_state if not str(k).startswith("_"))[:25],
            }
        )

        repo = self._repo(shared_state)
        tool_results: dict[str, dict[str, Any]] = {}
        pending_approvals: list[dict[str, Any]] = []
        selected_tools = [
            tool for tool in self.owned_tools if self.supports(task) or tool in task.lower()
        ]

        if not selected_tools and self.supports(task):
            selected_tools = list(self.owned_tools[:1])

        if not selected_tools:
            logger.add_warning("Task is outside domain scope")
            log = logger.finalize("skipped")
            return AgentResult(
                agent_id=self.agent_id,
                success=False,
                summary=f"{self.config.name}: task outside domain scope",
                data={
                    "domain": self.domain_name,
                    "confidence": 0.0,
                    "tool_results": {},
                    "pending_approvals": [],
                    "conflicts": [],
                    "execution_log": log.to_dict(),
                    "execution_trace": log.to_agent_step(),
                    "metrics": {
                        "duration_ms": round((time.time() - start) * 1000, 2),
                        "tool_count": 0,
                    },
                },
                duration_ms=round((time.time() - start) * 1000, 2),
            )

        for tool_name in selected_tools:
            if is_destructive(tool_name) or requires_human_approval(tool_name):
                approval = {
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "reason": f"{tool_name} requires human approval",
                    "status": "pending",
                }
                pending_approvals.append(approval)
                logger.add_decision(
                    "approval", "required", approval["reason"], {"tool_name": tool_name}
                )
                continue

            tool_kwargs = self._tool_kwargs(tool_name, task)
            result = execute_tool(tool_name, repo=repo, **tool_kwargs)
            tool_results[tool_name] = result
            logger.add_tool_call(
                tool_name, result.get("status", "ok"), input_params=tool_kwargs, output=result
            )

        successful = sum(
            1 for result in tool_results.values() if result.get("status", "ok") == "ok"
        )
        signal = self._primary_signal(tool_results)
        confidence = self._score_confidence(
            successful, max(len(selected_tools), 1), len(pending_approvals)
        )
        summary = self._summarize(tool_results)

        logger.add_context("domain", self.domain_name)
        logger.add_context("selected_tools", list(selected_tools))
        logger.add_output(
            {
                "tool_count": len(tool_results),
                "pending_approvals": len(pending_approvals),
                "confidence": confidence,
                "primary_signal": signal,
            }
        )
        log = logger.finalize("success" if confidence >= 0.5 else "warning")

        metrics = {
            "tool_count": len(tool_results),
            "pending_approvals": len(pending_approvals),
            "duration_ms": round(log.duration_ms, 2),
            "correlation_id": log.correlation_id,
        }

        return AgentResult(
            agent_id=self.agent_id,
            success=confidence >= 0.5 and not pending_approvals,
            summary=summary,
            data={
                "domain": self.domain_name,
                "task": task,
                "tool_results": tool_results,
                "pending_approvals": pending_approvals,
                "confidence": confidence,
                "primary_signal": signal,
                "execution_log": log.to_dict(),
                "execution_trace": log.to_agent_step(),
                "metrics": metrics,
            },
            duration_ms=round(log.duration_ms, 2),
        )

    async def collaborate(self, messages: list[AgentMessage]) -> list[AgentMessage]:
        responses: list[AgentMessage] = []
        for message in messages:
            task = str(message.payload.get("task", message.payload.get("subtask", "")))
            result = await self.process(task, message.payload.get("shared_state", {}))
            responses.append(
                AgentMessage(
                    source=self.agent_id,
                    target=message.source,
                    message_type="agent_result",
                    payload={
                        "agent_id": self.agent_id,
                        "summary": result.summary,
                        "success": result.success,
                        "data": result.data,
                    },
                )
            )
        return responses


class SupervisorAgent(BaseAgent):
    """Supervisor that delegates work across domain agents via shared state only."""

    def __init__(self) -> None:
        config = AgentConfig(
            agent_id="supervisor-agent",
            name="Supervisor Agent",
            agent_type=AgentType.GENERAL,
            description="Delegates tasks, coordinates parallel execution, and resolves conflicts",
            allowed_tools=[],
            supervisor_prompt=(
                "You are the Supervisor Agent. Decompose the task into domain-specific subtasks, "
                "delegate to specialized agents, and aggregate their results without direct peer-to-peer communication."
            ),
        )
        super().__init__(config)

    def _plan(self, task: str, shared_state: dict) -> dict[str, Any]:
        task_lower = task.lower()
        selected_agents: list[str] = []
        subtasks: dict[str, str] = {}

        def add(agent_id: str, subtask: str) -> None:
            if agent_id not in selected_agents:
                selected_agents.append(agent_id)
            subtasks[agent_id] = subtask

        if any(word in task_lower for word in ("docker", "container", "image")):
            add("docker-agent", f"Inspect container state for: {task}")
        if any(
            word in task_lower for word in ("health", "metric", "target", "monitor", "performance")
        ):
            add("monitoring-agent", f"Assess monitoring signals for: {task}")
        if any(word in task_lower for word in ("incident", "alert", "outage", "failure")):
            add("incident-agent", f"Review incidents and notifications for: {task}")
        if any(word in task_lower for word in ("report", "weekly", "monthly", "summary")):
            add("reporting-agent", f"Generate report context for: {task}")
        if any(word in task_lower for word in ("audit", "compliance", "policy", "evidence")):
            add("compliance-agent", f"Review compliance evidence for: {task}")
        if any(
            word in task_lower for word in ("knowledge", "history", "learn", "previous", "context")
        ):
            add("knowledge-agent", f"Search knowledge base for: {task}")
        if any(
            word in task_lower
            for word in ("infra", "infrastructure", "capacity", "resource", "scale")
        ):
            add("infrastructure-agent", f"Assess infrastructure capacity for: {task}")

        if not selected_agents:
            add("monitoring-agent", f"Assess general platform health for: {task}")
            add("knowledge-agent", f"Retrieve prior context for: {task}")

        parallel_groups: list[list[str]] = []
        if len(selected_agents) <= 2:
            parallel_groups = [selected_agents]
        else:
            parallel_groups = [selected_agents[:2], selected_agents[2:]]

        estimated_confidence = min(0.95, 0.35 + 0.1 * len(selected_agents))
        if shared_state.get("agent_collaboration"):
            estimated_confidence = min(0.98, estimated_confidence + 0.05)

        return {
            "selected_agents": selected_agents,
            "parallel_groups": [group for group in parallel_groups if group],
            "subtasks": subtasks,
            "estimated_confidence": estimated_confidence,
            "needs_approval": False,
            "reason": f"Selected {len(selected_agents)} specialist agent(s) for task decomposition",
        }

    async def process(self, task: str, shared_state: dict) -> AgentResult:
        start = time.time()
        logger = ExecutionLogger(
            self.agent_id, correlation_id=str(shared_state.get("_correlation_id", "")) or None
        )
        logger.add_input(
            {
                "task": task,
                "collaboration_history": len(shared_state.get("agent_collaboration", [])),
            }
        )
        plan = self._plan(task, shared_state)
        logger.add_decision(
            "delegation", "planned", plan["reason"], {"selected_agents": plan["selected_agents"]}
        )
        logger.add_output(plan)
        log = logger.finalize("success")
        summary = f"Supervisor planned {len(plan['selected_agents'])} agent(s)"
        return AgentResult(
            agent_id=self.agent_id,
            success=True,
            summary=summary,
            data={
                "collaboration_plan": plan,
                "execution_log": log.to_dict(),
                "execution_trace": log.to_agent_step(),
                "metrics": {
                    "duration_ms": round(log.duration_ms, 2),
                    "selected_agents": len(plan["selected_agents"]),
                },
            },
            duration_ms=round((time.time() - start) * 1000, 2),
        )

    async def collaborate(self, messages: list[AgentMessage]) -> list[AgentMessage]:
        responses: list[AgentMessage] = []
        for message in messages:
            shared_state = message.payload.get("shared_state", {})
            result_messages = message.payload.get("agent_results", [])
            selected = [m.get("source", "") for m in result_messages if m.get("source")]
            confidence_scores = [
                float(m.get("payload", {}).get("data", {}).get("confidence", 0.0))
                for m in result_messages
            ]
            conflicts = message.payload.get("conflicts", [])
            consensus = max(confidence_scores) if confidence_scores else 0.0
            if conflicts:
                consensus = max(0.0, consensus - 0.1 * len(conflicts))
            payload = {
                "task": message.payload.get("task", ""),
                "selected_agents": selected,
                "conflicts": conflicts,
                "confidence": consensus,
                "shared_state": shared_state,
            }
            responses.append(
                AgentMessage(
                    source=self.agent_id,
                    target=message.source,
                    message_type="supervisor_summary",
                    payload=payload,
                )
            )
        return responses


class InfrastructureAgent(CollaborativeDomainAgent):
    def __init__(self) -> None:
        super().__init__(
            AgentConfig(
                agent_id="infrastructure-agent",
                name="Infrastructure Agent",
                agent_type=AgentType.INFRASTRUCTURE,
                description="Infrastructure capacity, service health, and resource posture",
                allowed_tools=["health"],
                supervisor_prompt="Assess infrastructure readiness using existing health services.",
            )
        )
        self.domain_name = "infrastructure"
        self.keywords = ("infra", "infrastructure", "capacity", "resource", "scale", "reliability")
        self.owned_tools = ("health",)


class DockerAgent(CollaborativeDomainAgent):
    def __init__(self) -> None:
        super().__init__(
            AgentConfig(
                agent_id="docker-agent",
                name="Docker Agent",
                agent_type=AgentType.INFRASTRUCTURE,
                description="Container inventory and Docker runtime inspection",
                allowed_tools=["docker"],
                supervisor_prompt="Inspect container state and summarize Docker posture.",
            )
        )
        self.domain_name = "docker"
        self.keywords = ("docker", "container", "image", "compose")
        self.owned_tools = ("docker",)


class MonitoringAgent(CollaborativeDomainAgent):
    def __init__(self) -> None:
        super().__init__(
            AgentConfig(
                agent_id="monitoring-agent",
                name="Monitoring Agent",
                agent_type=AgentType.OPERATIONS,
                description="Monitoring targets, metrics, and health signals",
                allowed_tools=["metrics", "target"],
                supervisor_prompt="Inspect telemetry and target checks without mutating system state.",
            )
        )
        self.domain_name = "monitoring"
        self.keywords = (
            "monitor",
            "metrics",
            "metric",
            "health",
            "target",
            "performance",
            "cpu",
            "memory",
            "disk",
        )
        self.owned_tools = ("metrics", "target")


class IncidentAgent(CollaborativeDomainAgent):
    def __init__(self) -> None:
        super().__init__(
            AgentConfig(
                agent_id="incident-agent",
                name="Incident Agent",
                agent_type=AgentType.OPERATIONS,
                description="Incident and notification triage",
                allowed_tools=["incident", "notification"],
                supervisor_prompt="Review incidents and notification history for operational incidents.",
            )
        )
        self.domain_name = "incident"
        self.keywords = ("incident", "alert", "outage", "failure", "notification")
        self.owned_tools = ("incident", "notification")


class ReportingAgent(CollaborativeDomainAgent):
    def __init__(self) -> None:
        super().__init__(
            AgentConfig(
                agent_id="reporting-agent",
                name="Reporting Agent",
                agent_type=AgentType.GENERAL,
                description="Operational reporting and summaries",
                allowed_tools=["report"],
                supervisor_prompt="Generate existing operational reports and summarize them.",
            )
        )
        self.domain_name = "reporting"
        self.keywords = ("report", "weekly", "monthly", "summary")
        self.owned_tools = ("report",)


class KnowledgeAgent(CollaborativeDomainAgent):
    def __init__(self) -> None:
        super().__init__(
            AgentConfig(
                agent_id="knowledge-agent",
                name="Knowledge Agent",
                agent_type=AgentType.GENERAL,
                description="Knowledge base and memory search",
                allowed_tools=[],
                supervisor_prompt="Retrieve prior learnings and relevant memory entries.",
            )
        )
        self.domain_name = "knowledge"
        self.keywords = (
            "knowledge",
            "history",
            "learn",
            "learning",
            "previous",
            "context",
            "memory",
        )
        self.owned_tools = ()

    async def process(self, task: str, shared_state: dict) -> AgentResult:
        start = time.time()
        logger = ExecutionLogger(
            self.agent_id, correlation_id=str(shared_state.get("_correlation_id", "")) or None
        )
        logger.add_input({"task": task})
        store = self._memory_store()
        query = task.strip()
        knowledge_hits = store.search_knowledge(query, limit=5)
        learning_hits = store.search_learnings(query, limit=5)
        conversation_hits = store.search_conversations(query, limit=5)
        combined = {
            "knowledge": knowledge_hits.entries,
            "learnings": learning_hits.entries,
            "conversations": conversation_hits.entries,
        }
        logger.add_output(
            {
                "knowledge_hits": len(knowledge_hits.entries),
                "learning_hits": len(learning_hits.entries),
            }
        )
        log = logger.finalize("success")
        confidence = 0.4 + 0.1 * min(5, len(knowledge_hits.entries) + len(learning_hits.entries))
        summary = f"Knowledge Agent found {len(knowledge_hits.entries)} knowledge hit(s)"
        return AgentResult(
            agent_id=self.agent_id,
            success=True,
            summary=summary,
            data={
                "domain": self.domain_name,
                "task": task,
                "tool_results": combined,
                "pending_approvals": [],
                "confidence": min(0.95, confidence),
                "primary_signal": {
                    "signal": "knowledge_hits",
                    "value": len(knowledge_hits.entries),
                    "source": "memory",
                },
                "execution_log": log.to_dict(),
                "execution_trace": log.to_agent_step(),
                "metrics": {
                    "duration_ms": round(log.duration_ms, 2),
                    "query_hits": len(knowledge_hits.entries),
                },
            },
            duration_ms=round((time.time() - start) * 1000, 2),
        )

    async def collaborate(self, messages: list[AgentMessage]) -> list[AgentMessage]:
        responses: list[AgentMessage] = []
        for message in messages:
            result = await self.process(
                str(message.payload.get("task", "")), message.payload.get("shared_state", {})
            )
            responses.append(
                AgentMessage(
                    source=self.agent_id,
                    target=message.source,
                    message_type="knowledge_summary",
                    payload={"summary": result.summary, "data": result.data},
                )
            )
        return responses


class ComplianceAgent(CollaborativeDomainAgent):
    def __init__(self) -> None:
        super().__init__(
            AgentConfig(
                agent_id="compliance-agent",
                name="Compliance Agent",
                agent_type=AgentType.COMPLIANCE,
                description="Audit evidence and policy review",
                allowed_tools=["audit"],
                supervisor_prompt="Review audit evidence and compliance posture using existing services.",
            )
        )
        self.domain_name = "compliance"
        self.keywords = ("compliance", "audit", "policy", "evidence", "control", "regulation")
        self.owned_tools = ("audit",)


def build_default_agents() -> list[BaseAgent]:
    """Create the full Sprint D collaborative agent set."""
    return [
        SupervisorAgent(),
        InfrastructureAgent(),
        DockerAgent(),
        MonitoringAgent(),
        IncidentAgent(),
        ReportingAgent(),
        KnowledgeAgent(),
        ComplianceAgent(),
    ]
