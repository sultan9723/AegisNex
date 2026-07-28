"""Agent base classes for the AegisNex Multi-Agent Collaboration module."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class AgentType(str, Enum):
    OPERATIONS = "operations"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    INFRASTRUCTURE = "infrastructure"
    GENERAL = "general"


@dataclass
class AgentConfig:
    agent_id: str
    name: str
    agent_type: AgentType
    description: str
    allowed_tools: list[str] = field(default_factory=list)
    supervisor_prompt: str = ""
    max_iterations: int = 5
    enabled: bool = True


@dataclass
class AgentMessage:
    source: str
    target: str
    message_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )


@dataclass
class AgentResult:
    agent_id: str
    success: bool
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


class BaseAgent(ABC):
    """Abstract base for all agents in the multi-agent collaboration system."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._message_log: list[AgentMessage] = []

    @abstractmethod
    async def process(self, task: str, shared_state: dict) -> AgentResult: ...

    @abstractmethod
    async def collaborate(self, messages: list[AgentMessage]) -> list[AgentMessage]: ...

    def log_message(self, msg: AgentMessage) -> None:
        self._message_log.append(msg)

    def get_message_log(self, limit: int = 50) -> list[AgentMessage]:
        return self._message_log[-limit:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.config.agent_id,
            "name": self.config.name,
            "agent_type": self.config.agent_type.value,
            "description": self.config.description,
            "allowed_tools": list(self.config.allowed_tools),
            "max_iterations": self.config.max_iterations,
            "enabled": self.config.enabled,
        }

    @property
    def agent_id(self) -> str:
        return self.config.agent_id
