"""Centralized tool registry for the AegisNex Intelligence Engine.

All tools return structured JSON. No tool calls another tool directly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from src.platform_db import PlatformRepository


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


ToolFn = Callable[..., dict[str, Any]]


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AccessMode(str, Enum):
    READ = "read"
    WRITE = "write"


class PermissionLevel(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


@dataclass
class ToolDef:
    name: str
    description: str
    category: str
    parameters: list[dict[str, Any]] = field(default_factory=list)
    permission_level: PermissionLevel = PermissionLevel.VIEWER
    access_mode: AccessMode = AccessMode.READ
    risk_level: RiskLevel = RiskLevel.NONE
    requires_approval: bool = False
    destructive: bool = False
    fn: ToolFn | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.parameters,
            "permission_level": self.permission_level.value,
            "access_mode": self.access_mode.value,
            "risk_level": self.risk_level.value,
            "requires_approval": self.requires_approval,
            "destructive": self.destructive,
        }


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        category: str,
        fn: ToolFn,
        destructive: bool = False,
        requires_approval: bool = False,
        permission_level: PermissionLevel = PermissionLevel.VIEWER,
        access_mode: AccessMode = AccessMode.READ,
        risk_level: RiskLevel = RiskLevel.NONE,
        parameters: list[dict[str, Any]] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.category = category
        self.fn = fn
        self.destructive = destructive
        self.requires_approval = requires_approval
        self.permission_level = permission_level
        self.access_mode = access_mode
        self.risk_level = risk_level
        self.parameters = parameters or []

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        result = self.fn(**kwargs)
        result.setdefault("tool", self.name)
        result.setdefault("timestamp", utc_now())
        result.setdefault("status", "ok")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.parameters,
            "permission_level": self.permission_level.value,
            "access_mode": self.access_mode.value,
            "risk_level": self.risk_level.value,
            "requires_approval": self.requires_approval,
            "destructive": self.destructive,
        }


# ---- Tool implementations ----


def _metrics_tool(repo: PlatformRepository | None = None, **kwargs: Any) -> dict[str, Any]:
    try:
        from src.prometheus_exporter import PrometheusExporter

        services = getattr(repo, "_services", None) if repo else None
        if services is not None:
            exporter = PrometheusExporter(services)
            snapshot = exporter.collect(persist=False)
            return {"metrics": snapshot.values, "count": len(snapshot.values)}
        return {"status": "error", "error": "Services not available", "metrics": {}}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "metrics": {}}


def _docker_tool(repo: PlatformRepository | None = None, **kwargs: Any) -> dict[str, Any]:
    try:
        from src.docker_scanner import DockerScanner

        scanner = DockerScanner()
        report = scanner.run({"include_all": True})
        return {
            "status": report.get("status", "ok"),
            "containers": report.get("containers", []),
            "count": len(report.get("containers", [])),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc), "containers": [], "count": 0}


def _incident_tool(
    repo: PlatformRepository | None = None,
    action: str = "list",
    incident_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        from src.incidents import IncidentManager

        im = IncidentManager("", storage_repository=repo)
        if action == "list":
            incidents = im.list_incidents()
            status_filter = kwargs.get("status")
            if status_filter:
                incidents = [i for i in incidents if i.status == status_filter]
            return {
                "incidents": [i.to_dict() for i in incidents],
                "count": len(incidents),
            }
        if action == "get" and incident_id:
            incident = im.get_incident(incident_id)
            if incident:
                return {"incident": incident.to_dict()}
            return {"status": "error", "error": "Incident not found"}
        if action == "active":
            active = im.get_active_incidents()
            return {
                "incidents": [i.to_dict() for i in active],
                "count": len(active),
            }
        return {"status": "error", "error": f"Unknown action: {action}"}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "incidents": [], "count": 0}


def _target_tool(
    repo: PlatformRepository | None = None,
    action: str = "list",
    target_id: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        if repo is None:
            return {"status": "error", "error": "Repository not available"}
        if action == "list":
            target_type = kwargs.get("target_type")
            targets = repo.list_monitoring_targets(include_inactive=True)
            if target_type:
                targets = [t for t in targets if t.get("target_type") == target_type]
            latest = repo.latest_check_results()
            latest_by_target = {str(r.get("target_id")): r for r in latest}
            enriched = []
            for t in targets:
                row = dict(t)
                result = latest_by_target.get(str(t.get("id")))
                row["latest_result"] = result.get("details") if result else None
                row["last_checked_at"] = result.get("timestamp") if result else None
                enriched.append(row)
            return {"targets": enriched, "count": len(enriched)}
        if action == "get" and target_id is not None:
            target = repo.get_monitoring_target(target_id)
            if target:
                history = repo.check_history(target_id, limit=10)
                return {"target": target, "history": history}
            return {"status": "error", "error": "Target not found"}
        return {"status": "error", "error": f"Unknown action: {action}"}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "targets": [], "count": 0}


def _audit_tool(
    repo: PlatformRepository | None = None,
    action: str = "list",
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        if repo is None:
            return {"status": "error", "error": "Repository not available"}
        limit = int(kwargs.get("limit", 50))
        logs = repo.list_audit_logs(limit=limit)
        return {"logs": logs, "count": len(logs)}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "logs": [], "count": 0}


def _report_tool(
    repo: PlatformRepository | None = None,
    report_type: str = "weekly",
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        from src.reporting import OperationalReporter

        database_path = (
            str(getattr(repo, "_sqlite_path", lambda: "aegisnex.db")()) if repo else "aegisnex.db"
        )
        reporter = OperationalReporter(database_path)
        if report_type == "weekly":
            report = reporter.weekly_report()
        elif report_type == "monthly":
            report = reporter.monthly_report()
        else:
            return {"status": "error", "error": f"Unknown report type: {report_type}"}
        return {"report": report, "report_type": report_type}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "report": {}}


def _notification_tool(
    repo: PlatformRepository | None = None,
    action: str = "list",
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        if repo is None:
            return {"status": "error", "error": "Repository not available"}
        rows = repo.fetch_all("notifications")
        rows = sorted(rows, key=lambda r: str(r.get("timestamp", "")), reverse=True)
        ok = {"ok", "sent", "success"}
        sent = sum(1 for r in rows if str(r.get("status", "")).lower() in ok)
        failed = sum(1 for r in rows if str(r.get("status", "")).lower() not in ok)
        channels = repo.list_notification_channels()
        return {
            "notifications": rows[:50],
            "total_count": len(rows),
            "sent_count": sent,
            "failed_count": failed,
            "channels": channels,
            "channel_count": len(channels),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc), "notifications": [], "total_count": 0}


def _health_tool(
    repo: PlatformRepository | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        result: dict[str, Any] = {"timestamp": utc_now()}
        if repo is not None:
            result["database"] = repo.health_check()
        try:
            import psutil

            result["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            result["memory_percent"] = psutil.virtual_memory().percent
            result["disk_percent"] = psutil.disk_usage("/").percent
        except Exception:
            pass
        try:
            import docker

            client = docker.from_env(timeout=3)
            result["docker_available"] = bool(client.ping())
        except Exception:
            result["docker_available"] = False
        try:
            from src.docker_scanner import DockerScanner

            scanner = DockerScanner()
            report = scanner.run({"include_all": True})
            containers = report.get("containers", [])
            running = sum(1 for c in containers if c.get("status") == "running")
            result["containers_running"] = running
            result["containers_total"] = len(containers)
        except Exception:
            pass
        return result
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ---- Tool Definitions for Registration & Governance ----

TOOL_DEFINITIONS: list[ToolDef] = [
    ToolDef(
        name="metrics",
        description="Retrieve current system metrics (CPU, memory, disk, network, containers, incidents)",
        category="monitoring",
        parameters=[
            {
                "name": "repo",
                "type": "object",
                "description": "Platform repository",
                "required": False,
            }
        ],
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    ToolDef(
        name="docker",
        description="List all Docker containers with status, health, CPU, memory",
        category="containers",
        parameters=[
            {
                "name": "repo",
                "type": "object",
                "description": "Platform repository",
                "required": False,
            }
        ],
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    ToolDef(
        name="incident",
        description="Query incidents: list all, filter by status, get by ID",
        category="incidents",
        parameters=[
            {
                "name": "action",
                "type": "string",
                "description": "list, get, active",
                "required": False,
            },
            {
                "name": "incident_id",
                "type": "string",
                "description": "Incident ID for get action",
                "required": False,
            },
        ],
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    ToolDef(
        name="target",
        description="List monitoring targets with latest check results",
        category="monitoring",
        parameters=[
            {"name": "action", "type": "string", "description": "list, get", "required": False},
            {
                "name": "target_id",
                "type": "integer",
                "description": "Target ID for get action",
                "required": False,
            },
        ],
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    ToolDef(
        name="audit",
        description="Retrieve recent audit log entries",
        category="system",
        parameters=[
            {
                "name": "limit",
                "type": "integer",
                "description": "Number of log entries",
                "required": False,
            }
        ],
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    ToolDef(
        name="report",
        description="Generate weekly or monthly operational reports",
        category="reports",
        parameters=[
            {
                "name": "report_type",
                "type": "string",
                "description": "weekly or monthly",
                "required": False,
            }
        ],
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    ToolDef(
        name="notification",
        description="List notification history and configured channels",
        category="notifications",
        parameters=[{"name": "action", "type": "string", "description": "list", "required": False}],
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    ToolDef(
        name="health",
        description="Comprehensive system health: database, Docker, CPU, memory, disk",
        category="system",
        parameters=[
            {
                "name": "repo",
                "type": "object",
                "description": "Platform repository",
                "required": False,
            }
        ],
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
]


# ---- Registry ----

TOOL_REGISTRY: dict[str, Tool] = {
    "metrics": Tool(
        "metrics",
        "Retrieve current system metrics (CPU, memory, disk, network, containers, incidents)",
        "monitoring",
        _metrics_tool,
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    "docker": Tool(
        "docker",
        "List all Docker containers with status, health, CPU, memory",
        "containers",
        _docker_tool,
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    "incident": Tool(
        "incident",
        "Query incidents: list all, filter by status, get by ID",
        "incidents",
        _incident_tool,
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    "target": Tool(
        "target",
        "List monitoring targets with latest check results",
        "monitoring",
        _target_tool,
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    "audit": Tool(
        "audit",
        "Retrieve recent audit log entries",
        "system",
        _audit_tool,
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    "report": Tool(
        "report",
        "Generate weekly or monthly operational reports",
        "reports",
        _report_tool,
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    "notification": Tool(
        "notification",
        "List notification history and configured channels",
        "notifications",
        _notification_tool,
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
    "health": Tool(
        "health",
        "Comprehensive system health: database, Docker, CPU, memory, disk",
        "system",
        _health_tool,
        permission_level=PermissionLevel.VIEWER,
        access_mode=AccessMode.READ,
        risk_level=RiskLevel.NONE,
    ),
}

DESTRUCTIVE_TOOLS: dict[str, Tool] = {}


def get_tool(name: str) -> Tool | None:
    return TOOL_REGISTRY.get(name)


def list_tools(category: str | None = None) -> list[dict[str, Any]]:
    tools = []
    for name, tool in TOOL_REGISTRY.items():
        if category and tool.category != category:
            continue
        tools.append(tool.to_dict())
    return tools


def list_tool_definitions() -> list[dict[str, Any]]:
    return [td.to_dict() for td in TOOL_DEFINITIONS]


def execute_tool(
    name: str, repo: PlatformRepository | None = None, **kwargs: Any
) -> dict[str, Any]:
    tool = get_tool(name)
    if tool is None:
        return {"status": "error", "error": f"Unknown tool: {name}", "tool": name}
    kwargs["repo"] = repo
    return tool.execute(**kwargs)


def is_destructive(name: str) -> bool:
    tool = get_tool(name)
    return tool is not None and tool.destructive


def requires_human_approval(name: str) -> bool:
    tool = get_tool(name)
    return tool is not None and tool.requires_approval


def get_tool_risk_level(name: str) -> str:
    tool = get_tool(name)
    return tool.risk_level.value if tool else "unknown"
