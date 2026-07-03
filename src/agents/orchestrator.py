"""Multi-agent orchestrator for the AegisNex collaboration system."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.agents.base import BaseAgent
from src.agents.registry import AgentRegistry, create_default_registry
from src.agents.state import SharedAgentState


class AgentOrchestrator:
    """Orchestrates multiple agents for task dispatch, fan-out, and collaboration."""

    def __init__(self, repo: Any = None, shared_state: Optional[SharedAgentState] = None, autoload_defaults: bool = True) -> None:
        self._shared_state = shared_state or SharedAgentState()
        self._registry = AgentRegistry(repo=repo, shared_state=self._shared_state)
        if autoload_defaults:
            self._registry.register_defaults()

    def register_agent(self, agent: BaseAgent) -> None:
        self._registry.register(agent)

    def unregister_agent(self, agent_id: str) -> None:
        self._registry.unregister(agent_id)

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        return self._registry.get(agent_id)

    def list_agents(self) -> list[Dict[str, Any]]:
        return self._registry.list_agents()

    async def dispatch_task(self, task: str, target_agent: str = "") -> Dict[str, Any]:
        return await self._registry.dispatch_task(task, target_agent=target_agent)

    async def fan_out(self, task: str) -> List[AgentResult]:
        return await self._registry.fan_out(task)

    async def collaborate(self, agents: List[str], task: str) -> Dict[str, Any]:
        return await self._registry.collaborate(agents, task)

    def get_shared_state(self) -> Dict[str, Any]:
        return self._registry.get_shared_state()

    def update_shared_state(self, key: str, value: Any) -> None:
        self._registry.update_shared_state(key, value)
