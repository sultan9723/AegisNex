#!/bin/bash

# Configuration: Ensure paths are correctly mapped to your directory structure
DEPLOY_DIR="/home/sultan9723/AegisNexus-Pipeline/deploy"
# Change this line:
INGEST_SCRIPT="/home/sultan9723/AegisNexus-Pipeline/orchestrator/ingest_telemetry.py"

echo "===================================================="
echo "🛡️  AegisNexus Core Pipeline: Initiating Cycle 🛡️"
echo "===================================================="
echo "[*] Workspace Root: /home/sultan9723/AegisNexus-Pipeline"
echo "[*] Current Execution Time: $(date)"
echo "----------------------------------------------------"

# Step 1: Navigate to deploy context and perform a clean rebuild
echo "[*] Step 1: Building and spinning up secure engine containers (Forced Rebuild)..."
cd "$DEPLOY_DIR" || { echo "[-] Error: Could not change to $DEPLOY_DIR"; exit 1; }

# Perform a clean build and up sequence to ensure changes in audit_engine.sh are applied
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up --force-recreate -d

# Wait for services to finish (assuming they run as one-off tasks in the container)
echo "[*] Awaiting completion of scan modules..."
sudo docker compose wait app_audit network_recon

echo "----------------------------------------------------"
echo "[+] Step 2: Target scan modules finished execution safely."
echo "[*] Step 3: Triggering telemetry data ingestion engine..."

# Step 2: Automatically execute the standardized telemetry processing ledger
if [ -f "$INGEST_SCRIPT" ]; then
    python3 "$INGEST_SCRIPT"
else
    echo "[-] Critical Error: Ingestion file missing at $INGEST_SCRIPT"
    exit 1
fi

echo "===================================================="
echo "🚀 AegisNexus Pipeline Cycle Completed Successfully! 🚀"
echo "===================================================="

