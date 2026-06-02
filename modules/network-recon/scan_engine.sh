#!/bin/bash
set -euo pipefail

TARGET_HOST="${1:-}"
OUTPUT_DATA_DIR="/data"
JSON_OUTPUT="$OUTPUT_DATA_DIR/recon_output.json"
XML_RAW="$OUTPUT_DATA_DIR/raw_recon.xml"

if [[ -z "$TARGET_HOST" ]]; then
    echo -e "\033[0;31m[!] Pipeline Execution Failure:\033[0m Target parameter is null."
    exit 1
fi

echo -e "\033[0;34m[*] AegisNexus [Module 1]:\033[0m Scanning infrastructure surface for: $TARGET_HOST"

# Execute optimized port enumeration and service fingerprinting
nmap -sV -F -oX "$XML_RAW" "$TARGET_HOST" > /dev/null

# Parse structural data using native tools to guarantee zero bloat
OPEN_PORTS=$(grep -c "<port " "$XML_RAW" || true)

# Transpile results into a clean telemetry JSON stream
cat <<EOF > "$JSON_OUTPUT"
{
  "pipeline_module": "network-recon",
  "engine_status": "SUCCESS",
  "target": "$TARGET_HOST",
  "execution_timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "telemetry_data": {
    "detected_open_ports": $OPEN_PORTS
  }
}
EOF

echo -e "\033[0;32m[+] AegisNexus [Module 1] Complete:\033[0m Telemetry array written to $JSON_OUTPUT"
