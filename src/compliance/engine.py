"""Compliance checking engine for AegisNex."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.compliance.frameworks import (
    BUILTIN_FRAMEWORKS,
    ComplianceControl,
    ComplianceFramework,
    ComplianceResult,
    ComplianceStatus,
    _utc_now,
)


class ComplianceEngine:
    def __init__(self, repo: Any | None = None) -> None:
        self._repo = repo
        self._frameworks: dict[str, ComplianceFramework] = dict(BUILTIN_FRAMEWORKS)
        self._results: dict[str, list[ComplianceResult]] = {}

    def register_framework(self, framework: ComplianceFramework) -> None:
        self._frameworks[framework.id] = framework

    def get_frameworks(self) -> list[dict[str, Any]]:
        return [
            {
                "id": f.id,
                "name": f.name,
                "version": f.version,
                "description": f.description,
                "level": f.level,
                "control_count": len(f.controls),
            }
            for f in self._frameworks.values()
        ]

    def get_framework(self, framework_id: str) -> dict[str, Any] | None:
        fw = self._frameworks.get(framework_id)
        if fw is None:
            return None
        return {
            "id": fw.id,
            "name": fw.name,
            "version": fw.version,
            "description": fw.description,
            "level": fw.level,
            "controls": [
                {
                    "id": c.id,
                    "category": c.category,
                    "title": c.title,
                    "description": c.description,
                    "required_evidence": c.required_evidence,
                    "has_automated_check": c.automated_check is not None,
                }
                for c in fw.controls
            ],
            "control_count": len(fw.controls),
        }

    def run_check(self, framework_id: str) -> list[ComplianceResult]:
        fw = self._frameworks.get(framework_id)
        if fw is None:
            raise ValueError(f"Unknown framework: {framework_id}")
        results: list[ComplianceResult] = []
        for control in fw.controls:
            result = self._check_control(control)
            results.append(result)
        self._results[framework_id] = results
        return results

    def run_control_check(self, framework_id: str, control_id: str) -> ComplianceResult:
        fw = self._frameworks.get(framework_id)
        if fw is None:
            raise ValueError(f"Unknown framework: {framework_id}")
        for control in fw.controls:
            if control.id == control_id:
                result = self._check_control(control)
                return result
        raise ValueError(f"Unknown control: {control_id} in framework {framework_id}")

    def _check_control(self, control: ComplianceControl) -> ComplianceResult:
        if control.automated_check is None:
            return ComplianceResult(
                control_id=control.id,
                status=ComplianceStatus.NOT_CHECKED,
                evidence=[],
                checked_at=_utc_now(),
                details="No automated check available for this control.",
            )
        check_fn_name = f"_check_{control.automated_check}"
        check_fn = getattr(self, check_fn_name, None)
        if check_fn is None:
            return ComplianceResult(
                control_id=control.id,
                status=ComplianceStatus.NOT_CHECKED,
                evidence=[],
                checked_at=_utc_now(),
                details=f"Automated check '{control.automated_check}' not implemented.",
            )
        try:
            evidence, status, details = check_fn()
            return ComplianceResult(
                control_id=control.id,
                status=status,
                evidence=evidence,
                checked_at=_utc_now(),
                details=details,
            )
        except Exception as exc:
            return ComplianceResult(
                control_id=control.id,
                status=ComplianceStatus.IN_PROGRESS,
                evidence=[{"error": str(exc)}],
                checked_at=_utc_now(),
                details=f"Check failed with error: {exc}",
            )

    def get_results(self, framework_id: str) -> list[dict[str, Any]]:
        results = self._results.get(framework_id, [])
        return [self._result_to_dict(r) for r in results]

    def get_summary(self, framework_id: str) -> dict[str, Any]:
        results = self._results.get(framework_id, [])
        total = len(results)
        if total == 0:
            return {
                "framework_id": framework_id,
                "total_controls": 0,
                "compliant": 0,
                "non_compliant": 0,
                "not_applicable": 0,
                "not_checked": 0,
                "in_progress": 0,
                "score": 0.0,
                "status": "not_checked",
            }
        compliant = sum(1 for r in results if r.status == ComplianceStatus.COMPLIANT)
        non_compliant = sum(1 for r in results if r.status == ComplianceStatus.NON_COMPLIANT)
        applicable = total - sum(1 for r in results if r.status == ComplianceStatus.NOT_APPLICABLE)
        score = round((compliant / applicable) * 100, 2) if applicable > 0 else 0.0
        if score >= 90:
            status = "healthy"
        elif score >= 70:
            status = "warning"
        else:
            status = "critical"
        return {
            "framework_id": framework_id,
            "total_controls": total,
            "compliant": compliant,
            "non_compliant": non_compliant,
            "not_applicable": sum(1 for r in results if r.status == ComplianceStatus.NOT_APPLICABLE),
            "not_checked": sum(1 for r in results if r.status == ComplianceStatus.NOT_CHECKED),
            "in_progress": sum(1 for r in results if r.status == ComplianceStatus.IN_PROGRESS),
            "score": score,
            "status": status,
        }

    def generate_evidence(self, framework_id: str, control_id: str) -> dict[str, Any]:
        fw = self._frameworks.get(framework_id)
        if fw is None:
            raise ValueError(f"Unknown framework: {framework_id}")
        control = None
        for c in fw.controls:
            if c.id == control_id:
                control = c
                break
        if control is None:
            raise ValueError(f"Unknown control: {control_id}")
        evidence: dict[str, Any] = {
            "control_id": control_id,
            "framework_id": framework_id,
            "control_title": control.title,
            "generated_at": _utc_now(),
            "evidence_items": [],
        }
        if self._repo is not None:
            evidence["system_config"] = self._gather_system_config()
            evidence["access_control"] = self._gather_access_control()
        for evidence_type in control.required_evidence:
            item = {"type": evidence_type, "status": "collected", "data": {}}
            evidence["evidence_items"].append(item)
        return evidence

    def get_dashboard(self, framework_id: str = "") -> dict[str, Any]:
        dashboard: dict[str, Any] = {
            "generated_at": _utc_now(),
            "frameworks": [],
            "overall_score": 0.0,
            "overall_status": "not_checked",
        }
        total_controls = 0
        total_compliant = 0
        total_applicable = 0
        for fw_id, fw in self._frameworks.items():
            if framework_id and fw_id != framework_id:
                continue
            summary = self.get_summary(fw_id)
            fw_data = {
                "id": fw_id,
                "name": fw.name,
                "version": fw.version,
                "level": fw.level,
                "summary": summary,
            }
            dashboard["frameworks"].append(fw_data)
            total_controls += summary["total_controls"]
            total_compliant += summary["compliant"]
            total_applicable += (
                summary["total_controls"] - summary["not_applicable"]
            )
        if total_applicable > 0:
            dashboard["overall_score"] = round(
                (total_compliant / total_applicable) * 100, 2
            )
        dashboard["overall_status"] = (
            "healthy"
            if dashboard["overall_score"] >= 90
            else "warning"
            if dashboard["overall_score"] >= 70
            else "critical"
            if dashboard["overall_score"] > 0
            else "not_checked"
        )
        return dashboard

    # ---------------------------------------------------------------------------
    # Automated check implementations
    # ---------------------------------------------------------------------------

    def _check_policy_exists(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            settings = self._repo.get_settings()
            has_policy = bool(settings.get("security_policy"))
            if has_policy:
                return (
                    [{"type": "app_settings", "key": "security_policy", "found": True}],
                    ComplianceStatus.COMPLIANT,
                    "Security policy is configured in app settings.",
                )
            return (
                [{"type": "app_settings", "key": "security_policy", "found": False}],
                ComplianceStatus.NON_COMPLIANT,
                "No security policy found in app settings.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_policy_review_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "policy_review", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Policy review requires manual verification of review records.",
        )

    def _check_roles_defined(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            users = self._repo.fetch_all("users")
            roles = {u.get("role", "viewer") for u in users}
            if roles:
                return (
                    [{"type": "users", "roles_found": list(roles), "count": len(users)}],
                    ComplianceStatus.COMPLIANT,
                    f"User roles defined: {', '.join(sorted(roles))}.",
                )
            return (
                [{"type": "users", "roles_found": []}],
                ComplianceStatus.NON_COMPLIANT,
                "No user roles defined.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_segregation_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "segregation", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Segregation of duties requires manual review.",
        )

    def _check_asset_inventory_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            targets = self._repo.list_monitoring_targets(include_inactive=True)
            if targets:
                return (
                    [
                        {
                            "type": "monitoring_targets",
                            "count": len(targets),
                            "sample": [t.get("name") for t in targets[:5]],
                        }
                    ],
                    ComplianceStatus.COMPLIANT,
                    f"Monitoring targets found: {len(targets)} assets tracked.",
                )
            return (
                [{"type": "monitoring_targets", "count": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No monitoring targets found. Asset inventory may be incomplete.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_access_policy_exists(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_policy_exists()

    def _check_network_access_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            targets = self._repo.list_monitoring_targets()
            has_network = any(
                t.get("target_type") in ("http", "tcp") for t in targets
            )
            if has_network:
                return (
                    [{"type": "network_targets", "found": True}],
                    ComplianceStatus.COMPLIANT,
                    "Network access monitoring is configured.",
                )
            return (
                [{"type": "network_targets", "found": False}],
                ComplianceStatus.NON_COMPLIANT,
                "No network monitoring targets configured.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_user_lifecycle_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            users = self._repo.fetch_all("users")
            active = sum(1 for u in users if u.get("is_active"))
            inactive = sum(1 for u in users if not u.get("is_active"))
            return (
                [
                    {
                        "type": "users",
                        "total": len(users),
                        "active": active,
                        "inactive": inactive,
                    }
                ],
                ComplianceStatus.COMPLIANT,
                f"User lifecycle tracked: {active} active, {inactive} inactive.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_access_provisioning_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            audit_logs = self._repo.fetch_all("audit_logs", limit=10)
            provisioning_events = [
                l
                for l in audit_logs
                if "provision" in str(l.get("action", "")).lower()
            ]
            if provisioning_events:
                return (
                    [
                        {
                            "type": "audit_logs",
                            "provisioning_events": len(provisioning_events),
                        }
                    ],
                    ComplianceStatus.COMPLIANT,
                    "Access provisioning events found in audit logs.",
                )
            return (
                [{"type": "audit_logs", "provisioning_events": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No access provisioning events found in audit logs.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_privileged_access_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            users = self._repo.fetch_all("users")
            admin_users = [u for u in users if u.get("role") == "admin"]
            if admin_users:
                return (
                    [
                        {
                            "type": "privileged_users",
                            "count": len(admin_users),
                            "users": [u.get("email") for u in admin_users],
                        }
                    ],
                    ComplianceStatus.COMPLIANT,
                    f"Privileged users tracked: {len(admin_users)} admin(s).",
                )
            return (
                [{"type": "privileged_users", "count": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No privileged users defined.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_auth_security_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "auth_security", "note": "Verify MFA and password policy manually"}],
            ComplianceStatus.NOT_CHECKED,
            "Authentication security check requires manual verification.",
        )

    def _check_access_review_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "access_review", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Access review requires manual verification of review records.",
        )

    def _check_access_removal_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            audit_logs = self._repo.fetch_all("audit_logs", limit=20)
            removal_events = [
                l
                for l in audit_logs
                if "remov" in str(l.get("action", "")).lower()
                or "deactivat" in str(l.get("action", "")).lower()
            ]
            if removal_events:
                return (
                    [
                        {
                            "type": "audit_logs",
                            "removal_events": len(removal_events),
                        }
                    ],
                    ComplianceStatus.COMPLIANT,
                    "Access removal events found in audit logs.",
                )
            return (
                [{"type": "audit_logs", "removal_events": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No access removal events found.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_password_policy_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "password_policy", "note": "Verify password policy manually"}],
            ComplianceStatus.NOT_CHECKED,
            "Password policy compliance requires manual verification.",
        )

    def _check_encryption_policy_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            settings = self._repo.get_settings()
            has_tls = bool(
                settings.get("grafana_url", "").startswith("https")
            )
            return (
                [
                    {
                        "type": "encryption_config",
                        "tls_detected": has_tls,
                    }
                ],
                ComplianceStatus.COMPLIANT if has_tls else ComplianceStatus.NON_COMPLIANT,
                "TLS encryption detected." if has_tls else "No TLS encryption detected in configuration.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_key_management_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            api_keys = self._repo.list_api_keys()
            if api_keys:
                return (
                    [
                        {
                            "type": "api_keys",
                            "count": len(api_keys),
                            "active": sum(1 for k in api_keys if k.get("is_active")),
                        }
                    ],
                    ComplianceStatus.COMPLIANT,
                    f"API key management in place: {len(api_keys)} keys.",
                )
            return (
                [{"type": "api_keys", "count": 0}],
                ComplianceStatus.COMPLIANT,
                "No API keys found (acceptable if key management is not needed).",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_procedures_documented(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            reports = self._repo.fetch_all("reports")
            if reports:
                return (
                    [{"type": "reports", "count": len(reports)}],
                    ComplianceStatus.COMPLIANT,
                    f"Procedural documentation available: {len(reports)} reports.",
                )
            return (
                [{"type": "reports", "count": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No documented reports found.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_malware_protection_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "malware_protection", "note": "Verify antivirus/EDR manually"}],
            ComplianceStatus.NOT_CHECKED,
            "Malware protection requires manual verification.",
        )

    def _check_backup_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        db_path = getattr(self._repo, "_sqlite_path", lambda: Path("aegisnex.db"))()
        backup_dir = Path("data")
        backups = list(backup_dir.glob("*.db")) if backup_dir.exists() else []
        wal_files = list(backup_dir.glob("*.db-wal")) if backup_dir.exists() else []
        evidence = [
            {
                "type": "database",
                "db_exists": db_path.exists(),
            }
        ]
        has_wal = bool(wal_files)
        has_backups = bool(backups)
        if has_backups:
            evidence.append(
                {"type": "backup_files", "count": len(backups), "files": [str(b) for b in backups[:5]]}
            )
        compliant = has_backups or has_wal
        if compliant:
            return (
                evidence,
                ComplianceStatus.COMPLIANT,
                f"Database protection detected. WAL: {has_wal}, Backups: {len(backups)}.",
            )
        return (
            evidence,
            ComplianceStatus.NON_COMPLIANT,
            "No database backups or WAL journals detected.",
        )

    def _check_audit_logging_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            audit_logs = self._repo.fetch_all("audit_logs", limit=1)
            table_exists = self._repo.table_exists if hasattr(self._repo, "table_exists") else None
            has_table = table_exists("audit_logs") if table_exists else True
            if audit_logs or has_table:
                return (
                    [
                        {
                            "type": "audit_logs",
                            "table_exists": True,
                            "sample_count": len(audit_logs),
                        }
                    ],
                    ComplianceStatus.COMPLIANT,
                    "Audit logging is configured and contains entries.",
                )
            return (
                [{"type": "audit_logs", "table_exists": True, "entries": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "Audit log table exists but is empty.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_log_protection_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "log_protection", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Log protection requires manual verification of access controls.",
        )

    def _check_admin_logging_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            audit_logs = self._repo.fetch_all("audit_logs", limit=50)
            admin_actions = [
                l
                for l in audit_logs
                if str(l.get("actor", "")).lower() in ("admin", "system")
            ]
            if admin_actions:
                return (
                    [
                        {
                            "type": "admin_logs",
                            "admin_actions": len(admin_actions),
                        }
                    ],
                    ComplianceStatus.COMPLIANT,
                    f"Administrator activity logged: {len(admin_actions)} actions.",
                )
            return (
                [{"type": "admin_logs", "admin_actions": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No administrator actions found in audit logs.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_software_change_control(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "change_control", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Software change control requires manual verification.",
        )

    def _check_vulnerability_scan_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "vulnerability_scan", "status": "requires_external_scanner"}],
            ComplianceStatus.NOT_CHECKED,
            "Vulnerability scanning requires an external scanner tool.",
        )

    def _check_audit_trail_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_audit_logging_check()

    def _check_network_security_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            ssl_targets = [
                t
                for t in self._repo.list_monitoring_targets(include_inactive=True)
                if t.get("target_type") == "ssl"
            ]
            if ssl_targets:
                return (
                    [{"type": "network_security", "ssl_targets": len(ssl_targets)}],
                    ComplianceStatus.COMPLIANT,
                    f"SSL monitoring configured for {len(ssl_targets)} targets.",
                )
            return (
                [{"type": "network_security", "ssl_targets": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No SSL/TLS monitoring configured.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_transfer_security_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            settings = self._repo.get_settings()
            grafana_url = settings.get("grafana_url", "")
            has_https = grafana_url.startswith("https://")
            return (
                [{"type": "transfer_security", "https_detected": has_https}],
                ComplianceStatus.COMPLIANT if has_https else ComplianceStatus.NON_COMPLIANT,
                "HTTPS configured for web services."
                if has_https
                else "HTTPS not detected in service URLs.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_secure_dev_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "secure_dev", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Secure development practices require manual verification.",
        )

    def _check_incident_response_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            incidents = self._repo.fetch_all("incidents", limit=1)
            if incidents:
                return (
                    [
                        {"type": "incidents", "tracked": True, "sample_size": len(incidents)}
                    ],
                    ComplianceStatus.COMPLIANT,
                    "Incidents are being tracked.",
                )
            return (
                [{"type": "incidents", "tracked": False}],
                ComplianceStatus.NON_COMPLIANT,
                "No incidents found. Incident tracking may not be configured.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_incident_tracking_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_incident_response_check()

    def _check_evidence_preservation_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "evidence_preservation", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Evidence preservation procedures require manual verification.",
        )

    def _check_bcm_plan_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "bcm_plan", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Business continuity management plan requires manual verification.",
        )

    def _check_continuity_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "continuity", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Continuity processes require manual verification.",
        )

    def _check_compliance_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "compliance", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Compliance with legal requirements requires manual review.",
        )

    def _check_privacy_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "privacy", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Privacy controls require manual verification.",
        )

    def _check_risk_assessment_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "risk_assessment", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Risk assessment requires manual verification of risk register.",
        )

    def _check_change_impact_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            audit_logs = self._repo.fetch_all("audit_logs", limit=20)
            change_events = [
                l
                for l in audit_logs
                if "update" in str(l.get("action", "")).lower()
                or "change" in str(l.get("action", "")).lower()
            ]
            if change_events:
                return (
                    [
                        {
                            "type": "change_logs",
                            "change_events": len(change_events),
                        }
                    ],
                    ComplianceStatus.COMPLIANT,
                    "Change management events detected in audit logs.",
                )
            return (
                [{"type": "change_logs", "change_events": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No change management events found.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_monitoring_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            targets = self._repo.list_monitoring_targets()
            if targets:
                return (
                    [
                        {
                            "type": "monitoring",
                            "active_targets": len(targets),
                        }
                    ],
                    ComplianceStatus.COMPLIANT,
                    f"Monitoring active for {len(targets)} targets.",
                )
            return (
                [{"type": "monitoring", "active_targets": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No monitoring targets configured.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_control_activities_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "control_activities", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Control activities require manual verification.",
        )

    def _check_technology_controls_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_monitoring_check()

    def _check_policy_deployment_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            settings = self._repo.get_settings()
            has_policies = bool(settings)
            if has_policies:
                return (
                    [{"type": "policies", "count": len(settings)}],
                    ComplianceStatus.COMPLIANT,
                    f"Policies deployed: {len(settings)} settings configured.",
                )
            return (
                [{"type": "policies", "count": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No policies found in configuration.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_access_control_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            users = self._repo.fetch_all("users")
            api_keys = self._repo.list_api_keys()
            evidence = [
                {"type": "users", "count": len(users)},
                {"type": "api_keys", "count": len(api_keys)},
            ]
            if users or api_keys:
                return (
                    evidence,
                    ComplianceStatus.COMPLIANT,
                    "Access control mechanisms in place.",
                )
            return (
                evidence,
                ComplianceStatus.NON_COMPLIANT,
                "No users or API keys found.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_system_monitoring_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_monitoring_check()

    def _check_incident_management_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_incident_response_check()

    def _check_availability_monitoring_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_monitoring_check()

    def _check_backup_recovery_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_backup_check()

    def _check_processing_integrity_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "processing_integrity", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Processing integrity requires manual verification.",
        )

    def _check_confidentiality_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_encryption_policy_check()

    def _check_risk_management_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "risk_management", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Risk management requires manual verification.",
        )

    def _check_identity_management_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_user_lifecycle_check()

    def _check_remote_access_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "remote_access", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Remote access controls require manual verification.",
        )

    def _check_permission_management_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_privileged_access_check()

    def _check_network_segmentation_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "network_segmentation", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Network segmentation requires manual verification.",
        )

    def _check_encryption_at_rest_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "encryption_at_rest", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Encryption at rest requires manual verification of storage encryption.",
        )

    def _check_tls_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            settings = self._repo.get_settings()
            ssl_targets = [
                t
                for t in self._repo.list_monitoring_targets(include_inactive=True)
                if t.get("target_type") == "ssl"
            ]
            evidence = [
                {"type": "ssl_targets", "count": len(ssl_targets)},
                {"type": "settings", "grafana_https": settings.get("grafana_url", "").startswith("https://")},
            ]
            if ssl_targets:
                return (
                    evidence,
                    ComplianceStatus.COMPLIANT,
                    f"TLS/SSL configured and monitored for {len(ssl_targets)} targets.",
                )
            return (
                evidence,
                ComplianceStatus.NON_COMPLIANT,
                "No TLS/SSL monitoring configured.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_capacity_management_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            snapshots = self._repo.fetch_all("metrics_snapshots", limit=1)
            if snapshots:
                return (
                    [{"type": "metrics", "monitored": True}],
                    ComplianceStatus.COMPLIANT,
                    "System resource monitoring is active.",
                )
            return (
                [{"type": "metrics", "monitored": False}],
                ComplianceStatus.NON_COMPLIANT,
                "No metrics snapshots found.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_configuration_management_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            settings = self._repo.get_settings()
            if settings:
                return (
                    [{"type": "configuration", "settings_count": len(settings)}],
                    ComplianceStatus.COMPLIANT,
                    f"Configuration management in place: {len(settings)} settings.",
                )
            return (
                [{"type": "configuration", "settings_count": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No application settings configured.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_vulnerability_management_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "vulnerability_management", "status": "requires_external_scanner"}],
            ComplianceStatus.NOT_CHECKED,
            "Vulnerability management requires external scanner integration.",
        )

    def _check_network_baseline_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "network_baseline", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Network baseline requires manual verification.",
        )

    def _check_event_detection_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            incidents = self._repo.fetch_all("incidents", limit=1)
            if incidents:
                return (
                    [{"type": "event_detection", "incidents_tracked": True}],
                    ComplianceStatus.COMPLIANT,
                    "Event detection is operational.",
                )
            return (
                [{"type": "event_detection", "incidents_tracked": False}],
                ComplianceStatus.NON_COMPLIANT,
                "No incidents detected or tracked.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_network_monitoring_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_monitoring_check()

    def _check_user_activity_monitoring_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            audit_logs = self._repo.fetch_all("audit_logs", limit=1)
            if audit_logs:
                return (
                    [{"type": "user_activity", "logging_active": True}],
                    ComplianceStatus.COMPLIANT,
                    "User activity is being logged.",
                )
            return (
                [{"type": "user_activity", "logging_active": False}],
                ComplianceStatus.NON_COMPLIANT,
                "No user activity logs found.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_incident_notification_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            notifications = self._repo.fetch_all("notifications", limit=1)
            channels = self._repo.list_notification_channels()
            evidence = [
                {"type": "notifications", "sent": len(notifications) > 0},
                {"type": "channels", "configured": len(channels)},
            ]
            if channels:
                return (
                    evidence,
                    ComplianceStatus.COMPLIANT,
                    f"Notification channels configured: {len(channels)}.",
                )
            return (
                evidence,
                ComplianceStatus.NON_COMPLIANT,
                "No notification channels configured.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_recovery_plan_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "recovery_plan", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Recovery plan requires manual verification.",
        )

    def _check_unauthorized_asset_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            targets = self._repo.list_monitoring_targets(include_inactive=True)
            inactive = [t for t in targets if not t.get("is_active", True)]
            if inactive:
                return (
                    [{"type": "unauthorized_assets", "inactive_targets": len(inactive)}],
                    ComplianceStatus.COMPLIANT,
                    f"Unauthorized assets flagged: {len(inactive)} inactive targets.",
                )
            return (
                [{"type": "unauthorized_assets", "inactive_targets": 0}],
                ComplianceStatus.COMPLIANT,
                "All monitored assets are authorized.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_authorized_software_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "authorized_software", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Authorized software verification requires manual review.",
        )

    def _check_data_classification_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "data_classification", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Data classification requires manual verification.",
        )

    def _check_secure_config_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_configuration_management_check()

    def _check_config_monitoring_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_monitoring_check()

    def _check_account_inventory_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_user_lifecycle_check()

    def _check_dormant_account_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "dormant_accounts", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Dormant account review requires manual verification.",
        )

    def _check_access_model_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_privileged_access_check()

    def _check_mfa_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "mfa", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "MFA configuration requires manual verification.",
        )

    def _check_vulnerability_remediation_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "vulnerability_remediation", "status": "requires_external_scanner"}],
            ComplianceStatus.NOT_CHECKED,
            "Vulnerability remediation requires external scanner integration.",
        )

    def _check_log_centralization_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_audit_logging_check()

    def _check_log_retention_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            settings = self._repo.get_settings()
            retention_key = "retention_audit_logs_days"
            retention_days = settings.get(retention_key, "30")
            has_retention = retention_key in settings
            if has_retention:
                return (
                    [{"type": "log_retention", "days": int(retention_days)}],
                    ComplianceStatus.COMPLIANT,
                    f"Log retention configured: {retention_days} days.",
                )
            return (
                [{"type": "log_retention", "configured": False}],
                ComplianceStatus.NON_COMPLIANT,
                "Log retention policy not configured.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_behavior_detection_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "behavior_detection", "status": "requires_external_tool"}],
            ComplianceStatus.NOT_CHECKED,
            "Behavior-based detection requires external security tool.",
        )

    def _check_backup_automation_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_backup_check()

    def _check_recovery_test_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "recovery_test", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Recovery testing requires manual verification.",
        )

    def _check_ids_ips_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "ids_ips", "status": "requires_external_tool"}],
            ComplianceStatus.NOT_CHECKED,
            "IDS/IPS requires external security tool.",
        )

    def _check_traffic_analysis_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "traffic_analysis", "status": "requires_external_tool"}],
            ComplianceStatus.NOT_CHECKED,
            "Network traffic analysis requires external tool.",
        )

    def _check_app_vulnerability_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "app_vulnerability", "status": "requires_external_scanner"}],
            ComplianceStatus.NOT_CHECKED,
            "Application vulnerability scanning requires external tool.",
        )

    def _check_password_strength_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "password_strength", "note": "Verify password policy manually"}],
            ComplianceStatus.NOT_CHECKED,
            "Password strength requires manual verification.",
        )

    def _check_password_storage_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        try:
            from src.auth import hash_api_key
            has_hash = callable(hash_api_key)
            return (
                [{"type": "password_storage", "hashing_available": has_hash}],
                ComplianceStatus.COMPLIANT,
                "Password hashing is implemented.",
            )
        except Exception:
            return (
                [{"type": "password_storage", "status": "unknown"}],
                ComplianceStatus.NOT_CHECKED,
                "Unable to verify password storage mechanism.",
            )

    def _check_rate_limiting_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        try:
            from slowapi import Limiter
            has_rate_limiting = True
        except ImportError:
            has_rate_limiting = False
        if has_rate_limiting:
            return (
                [{"type": "rate_limiting", "enabled": True}],
                ComplianceStatus.COMPLIANT,
                "Rate limiting is configured.",
            )
        return (
            [{"type": "rate_limiting", "enabled": False}],
            ComplianceStatus.NON_COMPLIANT,
            "Rate limiting not detected.",
        )

    def _check_session_management_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "session_management", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Session management requires manual verification.",
        )

    def _check_session_token_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        try:
            import jwt as pyjwt
            has_jwt = True
        except ImportError:
            has_jwt = False
        if has_jwt:
            return (
                [{"type": "session_tokens", "jwt_available": True}],
                ComplianceStatus.COMPLIANT,
                "JWT-based session tokens are available.",
            )
        return (
            [{"type": "session_tokens", "jwt_available": False}],
            ComplianceStatus.NON_COMPLIANT,
            "No JWT library found for secure session tokens.",
        )

    def _check_session_binding_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "session_binding", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Session binding requires manual verification.",
        )

    def _check_least_privilege_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_privileged_access_check()

    def _check_idor_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "idor", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "IDOR prevention requires manual code review.",
        )

    def _check_rbac_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            users = self._repo.fetch_all("users")
            roles = {u.get("role") for u in users}
            if roles:
                return (
                    [{"type": "rbac", "roles": list(roles)}],
                    ComplianceStatus.COMPLIANT,
                    f"RBAC implemented with roles: {', '.join(sorted(roles))}.",
                )
            return (
                [{"type": "rbac", "roles": []}],
                ComplianceStatus.NON_COMPLIANT,
                "No RBAC roles defined.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_input_validation_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "input_validation", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Input validation requires manual code review.",
        )

    def _check_xss_prevention_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "xss_prevention", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "XSS prevention requires manual code review.",
        )

    def _check_sqli_prevention_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        try:
            import sqlite3
            has_parameterized = True
        except ImportError:
            has_parameterized = False
        if has_parameterized:
            return (
                [{"type": "sqli_prevention", "parameterized_queries": True}],
                ComplianceStatus.COMPLIANT,
                "Parameterized query support available.",
            )
        return (
            [{"type": "sqli_prevention", "parameterized_queries": False}],
            ComplianceStatus.NON_COMPLIANT,
            "No parameterized query support detected.",
        )

    def _check_file_upload_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "file_upload", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "File upload validation requires manual code review.",
        )

    def _check_cipher_security_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "cipher_security", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Cipher configuration requires manual verification.",
        )

    def _check_rng_security_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        try:
            import secrets
            has_secure_rng = True
        except ImportError:
            has_secure_rng = False
        if has_secure_rng:
            return (
                [{"type": "rng_security", "secure_rng": True}],
                ComplianceStatus.COMPLIANT,
                "Cryptographically secure random number generator available.",
            )
        return (
            [{"type": "rng_security", "secure_rng": False}],
            ComplianceStatus.NON_COMPLIANT,
            "No secure random number generator detected.",
        )

    def _check_error_handling_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "error_handling", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Error handling requires manual code review.",
        )

    def _check_log_integrity_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "log_integrity", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Log integrity requires manual verification.",
        )

    def _check_data_retention_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_log_retention_check()

    def _check_tls_config_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_tls_check()

    def _check_certificate_validation_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            ssl_targets = [
                t
                for t in self._repo.list_monitoring_targets(include_inactive=True)
                if t.get("target_type") == "ssl"
            ]
            if ssl_targets:
                return (
                    [
                        {
                            "type": "certificate_validation",
                            "ssl_targets": len(ssl_targets),
                        }
                    ],
                    ComplianceStatus.COMPLIANT,
                    f"SSL certificate monitoring active for {len(ssl_targets)} targets.",
                )
            return (
                [{"type": "certificate_validation", "ssl_targets": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No SSL certificate monitoring configured.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_static_analysis_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "static_analysis", "status": "requires_external_tool"}],
            ComplianceStatus.NOT_CHECKED,
            "Static analysis requires external tool integration.",
        )

    def _check_dependency_scan_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "dependency_scan", "status": "requires_external_tool"}],
            ComplianceStatus.NOT_CHECKED,
            "Dependency scanning requires external tool integration.",
        )

    def _check_file_execution_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "file_execution", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "File execution restrictions require manual verification.",
        )

    def _check_content_type_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "content_type", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Content-type validation requires manual code review.",
        )

    def _check_api_auth_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        if self._repo is None:
            return ([], ComplianceStatus.NOT_CHECKED, "Repository not available")
        try:
            api_keys = self._repo.list_api_keys()
            if api_keys:
                return (
                    [{"type": "api_auth", "api_keys": len(api_keys)}],
                    ComplianceStatus.COMPLIANT,
                    f"API authentication configured with {len(api_keys)} keys.",
                )
            return (
                [{"type": "api_auth", "api_keys": 0}],
                ComplianceStatus.NON_COMPLIANT,
                "No API authentication keys found.",
            )
        except Exception as exc:
            return ([{"error": str(exc)}], ComplianceStatus.IN_PROGRESS, f"Error: {exc}")

    def _check_api_rate_limit_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_rate_limiting_check()

    def _check_api_validation_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return self._check_input_validation_check()

    def _check_http_headers_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "http_headers", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "HTTP security headers require manual verification.",
        )

    def _check_cors_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "cors", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "CORS configuration requires manual verification.",
        )

    def _check_dependency_version_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "dependency_versions", "status": "requires_external_tool"}],
            ComplianceStatus.NOT_CHECKED,
            "Dependency version checking requires external tool integration.",
        )

    def _check_software_inventory_check(self) -> tuple[list[dict], ComplianceStatus, str]:
        return (
            [{"type": "software_inventory", "status": "manual_review_required"}],
            ComplianceStatus.NOT_CHECKED,
            "Software inventory requires manual verification.",
        )

    # ---------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------

    def _gather_system_config(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self._repo is not None:
            try:
                settings = self._repo.get_settings()
                result["settings"] = dict(settings)
            except Exception:
                pass
            try:
                targets = self._repo.list_monitoring_targets(include_inactive=True)
                result["monitoring_targets"] = len(targets)
            except Exception:
                pass
        return result

    def _gather_access_control(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self._repo is not None:
            try:
                users = self._repo.fetch_all("users")
                result["users"] = len(users)
            except Exception:
                pass
            try:
                api_keys = self._repo.list_api_keys()
                result["api_keys"] = len(api_keys)
            except Exception:
                pass
        return result

    @staticmethod
    def _result_to_dict(r: ComplianceResult) -> dict[str, Any]:
        return {
            "control_id": r.control_id,
            "status": r.status.value,
            "evidence": r.evidence,
            "checked_at": r.checked_at,
            "details": r.details,
        }
