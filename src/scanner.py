from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SecurityScanner:
    def __init__(self, data_dir: str | Path = "data", logger: logging.Logger | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.recon_file = self.data_dir / "recon_output.json"
        self.audit_file = self.data_dir / "audit_output.json"
        self.output_matrix = self.data_dir / "unified_threat_matrix.json"
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    def run_scan(self) -> dict[str, Any]:
        self.logger.info("Starting scan telemetry processing")
        recon_data = self._load_json_safely(self.recon_file)
        audit_data = self._load_json_safely(self.audit_file)
        threat_matrix = self.process_results(recon_data, audit_data)
        self._write_output(threat_matrix)
        return threat_matrix

    def process_results(
        self,
        recon_data: dict[str, Any] | None,
        audit_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        target = "unknown_asset"
        if recon_data and "target" in recon_data:
            target = str(recon_data["target"])
        elif audit_data and "target" in audit_data:
            target = str(audit_data["target"])

        open_ports = (
            recon_data.get("telemetry_data", {}).get("detected_open_ports", 0)
            if recon_data
            else 0
        )
        vulnerabilities = audit_data.get("matched_findings", []) if audit_data else []
        vuln_count = len(vulnerabilities) if isinstance(vulnerabilities, list) else 0

        risk_score = "LOW"
        if vuln_count > 5 or open_ports > 10:
            risk_score = "CRITICAL"
        elif vuln_count > 2 or open_ports > 3:
            risk_score = "HIGH"
        elif vuln_count > 0:
            risk_score = "MEDIUM"

        threat_matrix = {
            "asset_target": target,
            "last_evaluation": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "aggregated_risk_index": risk_score,
            "infrastructure_metrics": {
                "total_open_ports": open_ports,
                "port_scan_status": recon_data.get("engine_status", "UNKNOWN")
                if recon_data
                else "MISSING",
            },
            "application_vulnerabilities": {
                "total_findings": vuln_count,
                "findings_summary": vulnerabilities if isinstance(vulnerabilities, list) else [],
            },
        }

        self.logger.info(
            "Computed threat matrix for target=%s risk=%s", target, risk_score
        )
        return threat_matrix

    def _load_json_safely(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            self.logger.warning("Telemetry file missing: %s", path)
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.error("Failed to read telemetry file %s: %s", path, exc)
            return None

    def _write_output(self, threat_matrix: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_matrix.write_text(
            json.dumps(threat_matrix, indent=2), encoding="utf-8"
        )
        self.logger.info("Wrote unified threat matrix to %s", self.output_matrix)
