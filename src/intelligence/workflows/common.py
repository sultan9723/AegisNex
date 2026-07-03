"""Common reusable workflow definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorkflowStep:
    name: str
    description: str
    tools: List[str] = field(default_factory=list)
    runbook: str = ""
    parallel: bool = False
    requires_approval: bool = False
    timeout_seconds: int = 60


@dataclass
class WorkflowDef:
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)
    steps: List[WorkflowStep] = field(default_factory=list)
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    risk_level: str = "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "steps": [
                {
                    "name": s.name,
                    "description": s.description,
                    "tools": s.tools,
                    "runbook": s.runbook,
                    "parallel": s.parallel,
                    "requires_approval": s.requires_approval,
                    "timeout_seconds": s.timeout_seconds,
                }
                for s in self.steps
            ],
            "category": self.category,
            "tags": self.tags,
            "risk_level": self.risk_level,
        }


class WorkflowLibrary:
    def __init__(self) -> None:
        self._workflows: Dict[str, WorkflowDef] = {}

    def register(self, wf: WorkflowDef) -> None:
        self._workflows[wf.name] = wf

    def get(self, name: str) -> Optional[WorkflowDef]:
        return self._workflows.get(name)

    def list(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        result = []
        for wf in self._workflows.values():
            if category and wf.category != category:
                continue
            result.append(wf.to_dict())
        return result

    def find_by_trigger(self, trigger: str) -> List[WorkflowDef]:
        t = trigger.lower()
        return [wf for wf in self._workflows.values() if any(t in tr.lower() for tr in wf.triggers)]

    def count(self) -> int:
        return len(self._workflows)


_GLOBAL_LIBRARY: Optional[WorkflowLibrary] = None


def get_workflow_library() -> WorkflowLibrary:
    global _GLOBAL_LIBRARY
    if _GLOBAL_LIBRARY is None:
        _GLOBAL_LIBRARY = WorkflowLibrary()
        register_default_workflows(_GLOBAL_LIBRARY)
    return _GLOBAL_LIBRARY


def register_default_workflows(lib: WorkflowLibrary) -> None:
    lib.register(WorkflowDef(
        name="website-down",
        description="Detect and remediate a website that is not responding",
        triggers=["website down", "site unreachable", "http 500", "website offline"],
        category="incidents",
        tags=["web", "http", "critical"],
        risk_level="high",
        steps=[
            WorkflowStep(name="check-http", description="Check HTTP endpoint status", tools=["target"]),
            WorkflowStep(name="check-containers", description="Check web server containers", tools=["docker"]),
            WorkflowStep(name="check-health", description="Check system health", tools=["health"], parallel=True),
            WorkflowStep(name="restart-service", description="Restart web service", runbook="restart-nginx", requires_approval=True),
            WorkflowStep(name="verify-recovery", description="Verify site is back online", tools=["target"]),
        ],
    ))

    lib.register(WorkflowDef(
        name="high-cpu",
        description="Investigate and resolve high CPU usage",
        triggers=["high cpu", "cpu spike", "cpu 100", "cpu overload"],
        category="performance",
        tags=["cpu", "performance"],
        risk_level="medium",
        steps=[
            WorkflowStep(name="collect-metrics", description="Collect CPU metrics", tools=["metrics"]),
            WorkflowStep(name="find-consumers", description="Identify top CPU consumers", tools=["docker"], parallel=True),
            WorkflowStep(name="check-health", description="Check system health", tools=["health"], parallel=True),
            WorkflowStep(name="remediate", description="Run CPU remediation", runbook="high-cpu", requires_approval=True),
            WorkflowStep(name="verify", description="Verify CPU normalized", tools=["metrics"]),
        ],
    ))

    lib.register(WorkflowDef(
        name="container-restart",
        description="Restart an unhealthy container and verify",
        triggers=["container crash", "container unhealthy", "container restart"],
        category="containers",
        tags=["docker", "containers"],
        risk_level="medium",
        steps=[
            WorkflowStep(name="inspect", description="Inspect container status", tools=["docker"]),
            WorkflowStep(name="restart", description="Restart the container", runbook="restart-nginx", requires_approval=True),
            WorkflowStep(name="verify-health", description="Verify container health", tools=["health", "docker"]),
        ],
    ))

    lib.register(WorkflowDef(
        name="ssl-expiry",
        description="Check SSL certificate expiry and notify",
        triggers=["ssl expir", "certificate expir", "tls expir"],
        category="security",
        tags=["ssl", "certificate", "security"],
        risk_level="low",
        steps=[
            WorkflowStep(name="check-ssl", description="Check SSL certificate status", tools=["target"]),
            WorkflowStep(name="notify", description="Send notification if expiring soon", tools=["notification"]),
        ],
    ))

    lib.register(WorkflowDef(
        name="database-offline",
        description="Investigate and restore database connectivity",
        triggers=["database down", "db offline", "database unreachable", "db connection"],
        category="incidents",
        tags=["database", "critical"],
        risk_level="high",
        steps=[
            WorkflowStep(name="check-health", description="Check database health", tools=["health"]),
            WorkflowStep(name="check-containers", description="Check database containers", tools=["docker"]),
            WorkflowStep(name="check-metrics", description="Check system metrics", tools=["metrics"], parallel=True),
            WorkflowStep(name="remediate", description="Restart database service", requires_approval=True),
            WorkflowStep(name="verify", description="Verify database is back online", tools=["health"]),
        ],
    ))

    lib.register(WorkflowDef(
        name="disk-full",
        description="Resolve disk space issues",
        triggers=["disk full", "disk space", "disk usage", "no space", "storage full"],
        category="storage",
        tags=["disk", "storage", "cleanup"],
        risk_level="medium",
        steps=[
            WorkflowStep(name="check-disk", description="Check disk usage", tools=["metrics"]),
            WorkflowStep(name="cleanup", description="Run disk cleanup", runbook="disk-full", requires_approval=True),
            WorkflowStep(name="verify", description="Verify disk space freed", tools=["metrics"]),
        ],
    ))

    lib.register(WorkflowDef(
        name="memory-leak",
        description="Investigate and resolve memory leaks",
        triggers=["memory leak", "high memory", "memory spike", "oom", "out of memory"],
        category="performance",
        tags=["memory", "performance"],
        risk_level="medium",
        steps=[
            WorkflowStep(name="collect-metrics", description="Collect memory metrics", tools=["metrics"]),
            WorkflowStep(name="find-consumers", description="Identify memory consumers", tools=["docker"]),
            WorkflowStep(name="check-health", description="Check system health", tools=["health"], parallel=True),
            WorkflowStep(name="restart-container", description="Restart memory-heavy container", requires_approval=True),
            WorkflowStep(name="verify", description="Verify memory usage normalized", tools=["metrics"]),
        ],
    ))
