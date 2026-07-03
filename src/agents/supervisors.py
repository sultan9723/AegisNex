"""Backward-compatible supervisor aliases for the collaborative agent layer."""

from __future__ import annotations

from src.agents.domain_agents import (
    ComplianceAgent,
    InfrastructureAgent,
    MonitoringAgent,
    SupervisorAgent,
)


class OperationsSupervisor(SupervisorAgent):
    """Compatibility alias for the legacy operations supervisor."""


class SecuritySupervisor(ComplianceAgent):
    """Compatibility alias for the legacy security supervisor."""


class ComplianceSupervisor(ComplianceAgent):
    """Compatibility alias for the legacy compliance supervisor."""


class InfrastructureSupervisor(InfrastructureAgent):
    """Compatibility alias for the legacy infrastructure supervisor."""
