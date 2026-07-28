"""Built-in AI skills that don't require external plugins."""

from __future__ import annotations

from typing import Any

from src.plugins.base import PluginManifest, SkillPlugin


class SystemAnalyzerSkill(SkillPlugin):
    plugin_id = "builtin.system_analyzer"
    plugin_name = "System Analyzer"
    plugin_version = "1.0.0"
    plugin_description = "Analyzes system health metrics and provides recommendations"

    def __init__(self) -> None:
        manifest = PluginManifest(
            id=self.plugin_id,
            name=self.plugin_name,
            version=self.plugin_version,
            plugin_type="skill",
            description=self.plugin_description,
        )
        super().__init__(manifest)
        self._required_tools = ["health", "metrics"]
        self._expected_outputs = ["analysis_report"]

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        try:
            from src.intelligence.tools import execute_tool

            repo = context.get("repo")
            health = execute_tool("health", repo=repo)
            metrics = execute_tool("metrics", repo=repo)

            cpu = health.get("cpu_percent", 0)
            memory = health.get("memory_percent", 0)
            disk = health.get("disk_percent", 0)
            containers_running = health.get("containers_running", 0)
            containers_total = health.get("containers_total", 0)

            recommendations: list[str] = []
            if cpu > 80:
                recommendations.append(
                    "High CPU usage detected - consider scaling or investigating processes"
                )
            if memory > 80:
                recommendations.append(
                    "High memory usage detected - check for memory leaks or scale up"
                )
            if disk > 85:
                recommendations.append("Disk usage critical - clean up old logs or expand storage")
            if containers_total > 0 and containers_running < containers_total:
                recommendations.append(
                    f"Only {containers_running}/{containers_total} containers running - investigate stopped containers"
                )
            if health.get("docker_available") is False:
                recommendations.append("Docker daemon not reachable - check Docker service status")
            if health.get("database", {}).get("status") != "connected":
                recommendations.append("Database connection issue - verify database service")

            return {
                "status": "ok",
                "skill": self.plugin_name,
                "skill_id": self.manifest.id,
                "analysis_report": {
                    "health": health,
                    "metrics": metrics,
                    "recommendations": recommendations,
                    "summary": f"System CPU: {cpu}%, Memory: {memory}%, Disk: {disk}% - {len(recommendations)} recommendation(s)",
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "skill": self.plugin_name,
                "skill_id": self.manifest.id,
                "error": str(exc),
            }


class IncidentInvestigatorSkill(SkillPlugin):
    plugin_id = "builtin.incident_investigator"
    plugin_name = "Incident Investigator"
    plugin_version = "1.0.0"
    plugin_description = "Investigates incidents and finds root causes"

    def __init__(self) -> None:
        manifest = PluginManifest(
            id=self.plugin_id,
            name=self.plugin_name,
            version=self.plugin_version,
            plugin_type="skill",
            description=self.plugin_description,
        )
        super().__init__(manifest)
        self._required_tools = ["incident", "audit"]
        self._expected_outputs = ["investigation_report"]

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        try:
            from src.intelligence.tools import execute_tool

            repo = context.get("repo")
            incident_result = execute_tool("incident", repo=repo, action="list")
            audit_result = execute_tool("audit", repo=repo, limit=100)

            incidents = incident_result.get("incidents", [])
            audit_logs = audit_result.get("logs", [])

            active_incidents = [
                i
                for i in incidents
                if i.get("incident_status", i.get("status")) in {"active", "acknowledged"}
            ]
            root_causes: list[dict[str, Any]] = []
            for inc in active_incidents[:10]:
                service = inc.get("service_name", "unknown")
                related_logs = [log for log in audit_logs if service.lower() in str(log).lower()]
                root_causes.append(
                    {
                        "incident_id": inc.get("incident_id"),
                        "service": service,
                        "status": inc.get("incident_status", inc.get("status")),
                        "related_audit_entries": len(related_logs),
                        "timestamp": inc.get("timestamp"),
                    }
                )

            return {
                "status": "ok",
                "skill": self.plugin_name,
                "skill_id": self.manifest.id,
                "investigation_report": {
                    "total_incidents": len(incidents),
                    "active_incidents": len(active_incidents),
                    "audit_logs_reviewed": len(audit_logs),
                    "root_causes": root_causes,
                    "summary": f"Found {len(active_incidents)} active incident(s), reviewed {len(audit_logs)} audit log(s)",
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "skill": self.plugin_name,
                "skill_id": self.manifest.id,
                "error": str(exc),
            }


class ContainerManagerSkill(SkillPlugin):
    plugin_id = "builtin.container_manager"
    plugin_name = "Container Manager"
    plugin_version = "1.0.0"
    plugin_description = "Manages Docker containers"

    def __init__(self) -> None:
        manifest = PluginManifest(
            id=self.plugin_id,
            name=self.plugin_name,
            version=self.plugin_version,
            plugin_type="skill",
            description=self.plugin_description,
        )
        super().__init__(manifest)
        self._required_tools = ["docker"]
        self._expected_outputs = ["container_status", "actions_taken"]

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        try:
            from src.intelligence.tools import execute_tool

            repo = context.get("repo")
            docker_result = execute_tool("docker", repo=repo)

            containers = docker_result.get("containers", [])
            running = [c for c in containers if c.get("status") == "running"]
            stopped = [c for c in containers if c.get("status") == "stopped"]
            unhealthy = [
                c for c in containers if c.get("health_status") not in {"healthy", "none", None, ""}
            ]

            actions_taken: list[dict[str, str]] = []
            for c in unhealthy[:5]:
                actions_taken.append(
                    {
                        "container": c.get("name", "unknown"),
                        "issue": f"Unhealthy status: {c.get('health_status')}",
                        "recommended_action": "Restart container or investigate logs",
                    }
                )

            return {
                "status": "ok",
                "skill": self.plugin_name,
                "skill_id": self.manifest.id,
                "container_status": {
                    "total": len(containers),
                    "running": len(running),
                    "stopped": len(stopped),
                    "unhealthy": len(unhealthy),
                },
                "actions_taken": actions_taken,
                "containers": containers,
            }
        except Exception as exc:
            return {
                "status": "error",
                "skill": self.plugin_name,
                "skill_id": self.manifest.id,
                "error": str(exc),
            }


class ReportGeneratorSkill(SkillPlugin):
    plugin_id = "builtin.report_generator"
    plugin_name = "Report Generator"
    plugin_version = "1.0.0"
    plugin_description = "Generates operational reports"

    def __init__(self) -> None:
        manifest = PluginManifest(
            id=self.plugin_id,
            name=self.plugin_name,
            version=self.plugin_version,
            plugin_type="skill",
            description=self.plugin_description,
        )
        super().__init__(manifest)
        self._required_tools = ["report", "metrics", "incident"]
        self._expected_outputs = ["formatted_report"]

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        try:
            from src.intelligence.tools import execute_tool

            repo = context.get("repo")
            report_type = context.get("report_type", "weekly")
            report_result = execute_tool("report", repo=repo, report_type=report_type)
            metrics_result = execute_tool("metrics", repo=repo)
            incident_result = execute_tool("incident", repo=repo, action="list")

            report_data = report_result.get("report", {})
            incidents = incident_result.get("incidents", [])
            active_count = len(
                [
                    i
                    for i in incidents
                    if i.get("incident_status", i.get("status")) in {"active", "acknowledged"}
                ]
            )

            return {
                "status": "ok",
                "skill": self.plugin_name,
                "skill_id": self.manifest.id,
                "formatted_report": {
                    "report_type": report_type,
                    "report": report_data,
                    "metrics_summary": metrics_result.get("metrics", {}),
                    "incident_summary": {
                        "total": len(incidents),
                        "active": active_count,
                    },
                    "generated_at": __import__("datetime")
                    .datetime.now(__import__("datetime").timezone.utc)
                    .isoformat(),
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "skill": self.plugin_name,
                "skill_id": self.manifest.id,
                "error": str(exc),
            }


class SecurityAuditorSkill(SkillPlugin):
    plugin_id = "builtin.security_auditor"
    plugin_name = "Security Auditor"
    plugin_version = "1.0.0"
    plugin_description = "Audits system security"

    def __init__(self) -> None:
        manifest = PluginManifest(
            id=self.plugin_id,
            name=self.plugin_name,
            version=self.plugin_version,
            plugin_type="skill",
            description=self.plugin_description,
        )
        super().__init__(manifest)
        self._required_tools = ["audit", "target"]
        self._expected_outputs = ["security_audit_report"]

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        try:
            from src.intelligence.tools import execute_tool

            repo = context.get("repo")
            audit_result = execute_tool("audit", repo=repo, limit=200)
            target_result = execute_tool("target", repo=repo, action="list")

            audit_logs = audit_result.get("logs", [])
            targets = target_result.get("targets", [])

            failed_actions = [
                log
                for log in audit_logs
                if str(log.get("status", "")).lower() in {"error", "failed", "denied"}
            ]
            ssl_targets = [t for t in targets if str(t.get("target_type", "")).lower() == "ssl"]
            expired_ssl = [
                t for t in ssl_targets if t.get("latest_result", {}).get("status") != "ok"
            ]

            findings: list[dict[str, Any]] = []
            if failed_actions:
                findings.append(
                    {
                        "severity": "high",
                        "finding": f"Found {len(failed_actions)} failed/denied audit actions",
                        "details": [
                            log.get("action", str(log)[:80]) for log in failed_actions[:10]
                        ],
                    }
                )
            if expired_ssl:
                findings.append(
                    {
                        "severity": "medium",
                        "finding": f"{len(expired_ssl)} SSL certificate(s) with issues",
                        "details": [t.get("name", str(t)[:80]) for t in expired_ssl[:10]],
                    }
                )
            if not findings:
                findings.append(
                    {
                        "severity": "info",
                        "finding": "No critical security issues detected",
                        "details": [],
                    }
                )

            return {
                "status": "ok",
                "skill": self.plugin_name,
                "skill_id": self.manifest.id,
                "security_audit_report": {
                    "audit_logs_reviewed": len(audit_logs),
                    "monitoring_targets_reviewed": len(targets),
                    "findings": findings,
                    "summary": f"Reviewed {len(audit_logs)} audit log(s) and {len(targets)} target(s) - {len(findings)} finding(s)",
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "skill": self.plugin_name,
                "skill_id": self.manifest.id,
                "error": str(exc),
            }


def create_default_skills() -> list[SkillPlugin]:
    return [
        SystemAnalyzerSkill(),
        IncidentInvestigatorSkill(),
        ContainerManagerSkill(),
        ReportGeneratorSkill(),
        SecurityAuditorSkill(),
    ]
