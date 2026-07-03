"""AegisNex Multi-Agent Collaboration module."""

from src.agents.base import (
    AgentConfig,
    AgentMessage,
    AgentResult,
    AgentType,
    BaseAgent,
)
from src.agents.orchestrator import AgentOrchestrator
from src.agents.registry import AgentRegistry, create_default_registry
from src.agents.state import SharedAgentState
from src.agents.domain_agents import (
    ComplianceAgent,
    DockerAgent,
    InfrastructureAgent,
    IncidentAgent,
    KnowledgeAgent,
    MonitoringAgent,
    ReportingAgent,
    SupervisorAgent,
)

# Backward-compatible supervisor aliases.
from src.agents.supervisors import (
    ComplianceSupervisor,
    InfrastructureSupervisor,
    OperationsSupervisor,
    SecuritySupervisor,
)

__all__ = [
    "AgentConfig",
    "AgentMessage",
    "AgentResult",
    "AgentType",
    "AgentRegistry",
    "AgentOrchestrator",
    "BaseAgent",
    "ComplianceAgent",
    "ComplianceSupervisor",
    "DockerAgent",
    "InfrastructureAgent",
    "InfrastructureSupervisor",
    "IncidentAgent",
    "KnowledgeAgent",
    "MonitoringAgent",
    "OperationsSupervisor",
    "ReportingAgent",
    "SecuritySupervisor",
    "SharedAgentState",
    "SupervisorAgent",
    "create_default_registry",
]
