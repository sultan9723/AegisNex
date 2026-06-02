import json
import os
from datetime import datetime, UTC

# Define clean constants for file layout context
DATA_DIR = os.path.expanduser("~/AegisNexus-Pipeline/data")
RECON_FILE = os.path.join(DATA_DIR, "recon_output.json")
AUDIT_FILE = os.path.join(DATA_DIR, "audit_output.json")
OUTPUT_MATRIX = os.path.join(DATA_DIR, "unified_threat_matrix.json")

def load_json_safely(filepath):
    """Safely loads data payloads without crashing the processing loop."""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[-] Error reading target dataset {filepath}: {e}")
        return None

def process_pipeline_state():
    print("[*] AegisNexus Ingestion: Consolidating active pipeline matrices...")
    
    recon_data = load_json_safely(RECON_FILE)
    audit_data = load_json_safely(AUDIT_FILE)
    
    # Establish standard target identifier fallbacks
    target = "unknown_asset"
    if recon_data and "target" in recon_data:
        target = recon_data["target"]
    elif audit_data and "target" in audit_data:
        target = audit_data["target"]

    # Extract foundational values from the telemetry frames
    open_ports = recon_data.get("telemetry_data", {}).get("detected_open_ports", 0) if recon_data else 0
    vulnerabilities = audit_data.get("matched_findings", []) if audit_data else []
    
    # Calculate an actionable Risk Severity Index (High/Medium/Low indicators)
    vuln_count = len(vulnerabilities)
    risk_score = "LOW"
    if vuln_count > 5 or open_ports > 10:
        risk_score = "CRITICAL"
    elif vuln_count > 2 or open_ports > 3:
        risk_score = "HIGH"
    elif vuln_count > 0:
        risk_score = "MEDIUM"

    # Construct the master unified data payload state (using timezone-aware UTC)
    threat_matrix = {
        "asset_target": target,
        "last_evaluation": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aggregated_risk_index": risk_score,
        "infrastructure_metrics": {
            "total_open_ports": open_ports,
            "port_scan_status": recon_data.get("engine_status", "UNKNOWN") if recon_data else "MISSING"
        },
        "application_vulnerabilities": {
            "total_findings": vuln_count,
            "findings_summary": vulnerabilities
        }
    }

    # Write the unified payload back down to shared disk state
    try:
        with open(OUTPUT_MATRIX, "w") as f:
            json.dump(threat_matrix, f, indent=2)
        print(f"[+] Success: Unified threat matrix compiled cleanly -> {OUTPUT_MATRIX}")
    except Exception as e:
        print(f"[-] Fatal error writing unified ledger state: {e}")

if __name__ == "__main__":
    process_pipeline_state()
