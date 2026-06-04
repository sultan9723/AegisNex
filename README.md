# AegisNex Guardian

**Autonomous container health monitoring and self-healing for production Docker environments.**

## The Problem
Modern workloads often rely on multiple Docker containers running continuously. Manual checks and ad-hoc restarts are slow, error-prone, and easy to miss during outages. When a container fails silently, downstream services degrade and recovery time increases. Infrastructure teams need automated monitoring and rapid remediation to keep services healthy.

## The Solution
AegisNex is an autonomous "Guardian" agent that follows a Sense-Analyze-Act loop:

- **Sense:** Collects system resource metrics and Docker container status.
- **Analyze:** Aggregates health signals into a unified report.
- **Act:** Automatically attempts safe remediation (container restart) and alerts via email.

## Key Features
- **Self-healing:** Automatically restarts containers that are stopped or unhealthy.
- **Email alerting:** Sends actionable alerts with timestamps and remediation details.
- **Daemonized watchdog:** Runs continuously in the background with rotating logs.
- **Modular design:** Clean registry-driven architecture for plugging in new capabilities.

## Architecture
Core components are organized for clarity and extensibility:

- `src/` - Modular agent capabilities (monitoring, Docker scanning, orchestration, guardian).
- `entrypoint.py` - CLI entrypoint for running individual features.
- `src/watchdog.py` - Background loop for continuous guardian checks.
- `logs/` - Runtime logs (e.g., `logs/agent.log`, `logs/agentx.log`).

## Installation & Usage

### 1) Clone the repository
```bash
git clone https://github.com/sultan9723/AegisNex.git
cd AegisNex
```

### 2) Create a virtual environment (optional)
```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

### 3) Install dependencies
```bash
pip install -r requirements.txt
```

### 4) Configure email alerts
Create a `.env` file (or set environment variables) with your email configuration:

```bash
EMAIL_USER=youraddress@gmail.com
EMAIL_PASS=your_app_password
EMAIL_TO=recipient@example.com
```

> Gmail requires an App Password (enable 2-Step Verification, then create an App Password).

### 5) Run Guardian modes
Run an on-demand health report:
```bash
python entrypoint.py --health
```

Run the autonomous guardian:
```bash
python entrypoint.py --guardian
```

Run background watchdog (continuous):
```bash
python -m src.watchdog
```

## Best Practices
- Use environment variables for secrets (never hardcode credentials).
- Keep logs under version control exclusion (already handled in `.gitignore`).
- Run watchdog in a service manager or scheduler for production reliability.

## Incident Management
AegisNex persists operational incidents to `incident_history.json` through
`src/incidents.py`.

Guardian creates or reuses an active incident when a container is stopped, in an
error state, or fails a configured health check. When remediation is attempted,
the incident is updated with remediation outcome fields. When the service is
observed healthy again, active incidents for that service are resolved.

Incident records contain:

- `incident_id`
- `timestamp`
- `severity`
- `service_name`
- `incident_type`
- `description`
- `health_check_results`
- `remediation_attempted`
- `remediation_successful`
- `status`
- `resolved_timestamp`

Example:

```json
{
  "incident_id": "8c2d7d25-6a64-4e13-9f2f-3212c2db1b20",
  "timestamp": "2026-06-04T12:00:00Z",
  "severity": "high",
  "service_name": "api",
  "incident_type": "health_check_failed",
  "description": "Health check failure for api: http",
  "health_check_results": [
    {
      "name": "http",
      "status": "503",
      "healthy": false,
      "message": "Expected HTTP 200"
    }
  ],
  "remediation_attempted": true,
  "remediation_successful": true,
  "status": "active",
  "resolved_timestamp": null
}
```

## Suggestions & Improvements
- Add log rotation and alert rate limiting policies per container.
- Support additional notification targets (Slack, PagerDuty, Teams).
- Persist health history to a lightweight datastore for trend analysis.
- Integrate container-specific health checks (HTTP endpoints, exit codes).
