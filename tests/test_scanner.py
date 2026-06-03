import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scanner import SecurityScanner


def test_run_scan_writes_output(tmp_path: Path) -> None:
    recon_payload = {
        "pipeline_module": "network-recon",
        "engine_status": "SUCCESS",
        "target": "example.org",
        "telemetry_data": {"detected_open_ports": 4},
    }
    audit_payload = {
        "pipeline_module": "app-audit",
        "engine_status": "SUCCESS",
        "target": "example.org",
        "matched_findings": [
            {"id": "TEST-1", "severity": "medium"},
        ],
    }

    (tmp_path / "recon_output.json").write_text(
        json.dumps(recon_payload), encoding="utf-8"
    )
    (tmp_path / "audit_output.json").write_text(
        json.dumps(audit_payload), encoding="utf-8"
    )

    scanner = SecurityScanner(data_dir=tmp_path)
    result = scanner.run_scan()

    assert result["aggregated_risk_index"] == "HIGH"
    assert result["asset_target"] == "example.org"
    output_path = tmp_path / "unified_threat_matrix.json"
    assert output_path.exists()
