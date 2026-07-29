"""Evidence collection for AegisNex compliance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.compliance.frameworks import BUILTIN_FRAMEWORKS, _utc_now


class EvidenceCollector:
    def __init__(self, repo: Any | None = None) -> None:
        self._repo = repo

    def collect_system_evidence(self, control_id: str) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "control_id": control_id,
            "type": "system",
            "collected_at": _utc_now(),
            "data": {},
        }
        if self._repo is not None:
            try:
                settings = self._repo.get_settings()
                evidence["data"]["settings"] = dict(settings)
            except Exception:
                evidence["data"]["settings"] = {}
            try:
                targets = self._repo.list_monitoring_targets(include_inactive=True)
                evidence["data"]["monitoring_targets"] = [
                    {
                        "id": t.get("id"),
                        "name": t.get("name"),
                        "type": t.get("target_type"),
                        "active": t.get("is_active"),
                    }
                    for t in targets
                ]
            except Exception:
                evidence["data"]["monitoring_targets"] = []
            try:
                audit_logs = self._repo.fetch_all("audit_logs", limit=10)
                evidence["data"]["recent_audit_events"] = len(audit_logs)
            except Exception:
                evidence["data"]["recent_audit_events"] = 0
        try:
            import platform as _platform

            evidence["data"]["host_info"] = {
                "system": _platform.system(),
                "release": _platform.release(),
                "python": _platform.python_version(),
            }
        except Exception:
            pass
        return evidence

    def collect_log_evidence(self, control_id: str, start: str, end: str) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "control_id": control_id,
            "type": "log",
            "collected_at": _utc_now(),
            "window": {"start": start, "end": end},
            "data": {},
        }
        if self._repo is not None:
            try:
                logs = self._repo.fetch_all("audit_logs")
                filtered = []
                for log in logs:
                    ts = str(log.get("timestamp", ""))
                    if start <= ts <= end:
                        filtered.append(log)
                evidence["data"]["audit_logs"] = filtered[:100]
                evidence["data"]["total_in_window"] = len(filtered)
            except Exception as exc:
                evidence["data"]["error"] = str(exc)
        return evidence

    def collect_policy_evidence(self, control_id: str) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "control_id": control_id,
            "type": "policy",
            "collected_at": _utc_now(),
            "data": {},
        }
        if self._repo is not None:
            try:
                settings = self._repo.get_settings()
                policy_keys = {
                    k: v
                    for k, v in settings.items()
                    if "policy" in k.lower() or "threshold" in k.lower() or "retention" in k.lower()
                }
                evidence["data"]["policy_settings"] = policy_keys
            except Exception as exc:
                evidence["data"]["error"] = str(exc)
        try:
            policy_dir = Path(__file__).resolve().parents[2] / "policies"
            if policy_dir.exists():
                policy_files = [
                    str(f.relative_to(policy_dir)) for f in policy_dir.iterdir() if f.is_file()
                ]
                evidence["data"]["policy_files"] = policy_files
        except Exception:
            pass
        return evidence

    def collect_access_control_evidence(self) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "type": "access_control",
            "collected_at": _utc_now(),
            "data": {},
        }
        if self._repo is not None:
            try:
                users = self._repo.fetch_all("users")
                evidence["data"]["users"] = [
                    {
                        "id": u.get("id"),
                        "email": u.get("email"),
                        "role": u.get("role", "viewer"),
                        "is_active": bool(u.get("is_active", False)),
                        "is_superuser": bool(u.get("is_superuser", False)),
                    }
                    for u in users
                ]
            except Exception:
                evidence["data"]["users"] = []
            try:
                api_keys = self._repo.list_api_keys()
                evidence["data"]["api_keys"] = [
                    {
                        "id": k.get("id"),
                        "name": k.get("name"),
                        "role": k.get("role", "viewer"),
                        "is_active": bool(k.get("is_active", False)),
                        "last_used_at": k.get("last_used_at"),
                    }
                    for k in api_keys
                ]
            except Exception:
                evidence["data"]["api_keys"] = []
            try:
                channels = self._repo.list_notification_channels()
                evidence["data"]["notification_channels"] = [
                    {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "type": c.get("channel_type"),
                        "active": bool(c.get("is_active", False)),
                    }
                    for c in channels
                ]
            except Exception:
                evidence["data"]["notification_channels"] = []
        return evidence

    def generate_report(self, framework_id: str, format: str = "json") -> str:
        fw = BUILTIN_FRAMEWORKS.get(framework_id)
        if fw is None:
            raise ValueError(f"Unknown framework: {framework_id}")
        report_data: dict[str, Any] = {
            "report_type": "compliance",
            "framework": {
                "id": fw.id,
                "name": fw.name,
                "version": fw.version,
                "description": fw.description,
                "level": fw.level,
                "total_controls": len(fw.controls),
            },
            "generated_at": _utc_now(),
            "controls": [],
        }
        for control in fw.controls:
            control_entry = {
                "id": control.id,
                "category": control.category,
                "title": control.title,
                "description": control.description,
                "required_evidence": control.required_evidence,
                "has_automated_check": control.automated_check is not None,
            }
            sys_evidence = self.collect_system_evidence(control.id)
            access_evidence = self.collect_access_control_evidence()
            control_entry["evidence"] = {
                "system": sys_evidence.get("data", {}),
                "access_control": access_evidence.get("data", {}),
            }
            report_data["controls"].append(control_entry)
        if format == "json":
            return json.dumps(report_data, indent=2, default=str, sort_keys=True)
        if format == "html":
            return self._render_html(report_data)
        if format == "markdown":
            return self._render_markdown(report_data)
        raise ValueError(f"Unsupported report format: {format}")

    def _render_html(self, report: dict[str, Any]) -> str:
        fw = report["framework"]
        controls_html = ""
        for ctrl in report["controls"]:
            controls_html += f"""
            <div class="control">
                <h3>{ctrl["id"]}: {ctrl["title"]}</h3>
                <p class="category">{ctrl["category"]}</p>
                <p>{ctrl["description"]}</p>
                <p><strong>Required Evidence:</strong> {", ".join(ctrl["required_evidence"]) if ctrl["required_evidence"] else "None"}</p>
                <p><strong>Automated Check:</strong> {ctrl["has_automated_check"]}</p>
            </div>
            """
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Compliance Report - {fw["name"]}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 1rem; }}
h1 {{ border-bottom: 2px solid #333; padding-bottom: 0.5rem; }}
.control {{ border: 1px solid #ddd; border-radius: 6px; padding: 1rem; margin-bottom: 1rem; }}
.category {{ color: #666; font-size: 0.9rem; }}
.footer {{ margin-top: 2rem; color: #999; font-size: 0.8rem; }}
</style>
</head>
<body>
<h1>Compliance Report: {fw["name"]} v{fw["version"]}</h1>
<p>{fw["description"]}</p>
<p><strong>Level:</strong> {fw["level"]} | <strong>Controls:</strong> {fw["total_controls"]}</p>
<p><strong>Generated:</strong> {report["generated_at"]}</p>
<hr>
{controls_html}
<div class="footer">AegisNex Compliance Report — {report["generated_at"]}</div>
</body>
</html>"""

    def _render_markdown(self, report: dict[str, Any]) -> str:
        fw = report["framework"]
        lines = [
            f"# Compliance Report: {fw['name']} v{fw['version']}",
            "",
            f"{fw['description']}",
            "",
            f"**Level:** {fw['level']} | **Controls:** {fw['total_controls']}",
            f"**Generated:** {report['generated_at']}",
            "",
            "---",
            "",
        ]
        for ctrl in report["controls"]:
            lines.append(f"## {ctrl['id']}: {ctrl['title']}")
            lines.append("")
            lines.append(f"**Category:** {ctrl['category']}")
            lines.append("")
            lines.append(f"{ctrl['description']}")
            lines.append("")
            if ctrl["required_evidence"]:
                lines.append(f"**Required Evidence:** {', '.join(ctrl['required_evidence'])}")
            lines.append(f"**Automated Check:** {'Yes' if ctrl['has_automated_check'] else 'No'}")
            lines.append("")
            lines.append("---")
            lines.append("")
        lines.append(f"*AegisNex Compliance Report — {report['generated_at']}*")
        return "\n".join(lines)
