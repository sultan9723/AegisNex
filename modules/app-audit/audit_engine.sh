#!/bin/bash

# Configuration: Paths for the audit engine
TARGET_URL="https://stayfit.pk"
RAW_VULNS="/tmp/nuclei_raw.json"
JSON_OUTPUT="/data/audit_output.json"

echo "[*] AegisNexus [Module 2]: Initializing application threat discovery on: $TARGET_URL"

# Execute Nuclei scan
# Ensure you are not using the invalid -sn flag. Using -passive for light auditing.
nuclei -target "$TARGET_URL" -silent -jsonl -o "$RAW_VULNS"

# Data Processing: Validate findings and structure the telemetry
if [ -f "$RAW_VULNS" ] && [ -s "$RAW_VULNS" ]; then
    # Calculate count of lines
    TOTAL_VULNS=$(wc -l < "$RAW_VULNS")
    # Transform individual JSON lines into a valid structured JSON array
    MATCHED_FINDINGS=$(jq -s '.' "$RAW_VULNS")
else
    TOTAL_VULNS=0
    MATCHED_FINDINGS="[]"
    echo -e "\033[0;33m[!] Notice: No vulnerabilities identified or scan returned empty.\033[0m"
fi

# Final telemetry assembly
cat <<EOF > "$JSON_OUTPUT"
{
  "pipeline_module": "app-audit",
  "engine_status": "SUCCESS",
  "target": "$TARGET_URL",
  "execution_timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "telemetry_data": {
    "identified_vulnerabilities": $TOTAL_VULNS
  },
  "matched_findings": $MATCHED_FINDINGS
}
EOF

echo -e "\033[0;32m[+] AegisNexus [Module 2] Complete:\033[0m Telemetry array written to $JSON_OUTPUT"
