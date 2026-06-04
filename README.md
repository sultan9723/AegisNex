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

### 6) Run the dashboard
Install dashboard dependencies from `requirements.txt`, then start FastAPI with
Uvicorn:

```bash
uvicorn src.dashboard:create_app --factory --host 0.0.0.0 --port 8000
```

Dashboard routes:

- `/` - Operational overview with CPU, memory, disk, network, containers, and incident counts.
- `/containers` - Container status, Docker health, restart count, and last check timestamp.
- `/incidents` - Active and resolved incident history.
- `/actions` - Remediation action history from incidents and restart tracking.
- `/metrics` - Prometheus metrics endpoint.

## Prometheus Metrics
AegisNex exposes Prometheus metrics from the dashboard application at
`/metrics`.

Metric names:

- `aegisnex_system_cpu_usage_percent`
- `aegisnex_system_memory_usage_percent`
- `aegisnex_system_disk_usage_percent`
- `aegisnex_system_network_bytes_sent`
- `aegisnex_system_network_bytes_received`
- `aegisnex_containers_running`
- `aegisnex_containers_stopped`
- `aegisnex_containers_unhealthy`
- `aegisnex_incidents_active`
- `aegisnex_incidents_resolved`
- `aegisnex_incidents_total`
- `aegisnex_remediation_restart_attempts_total`
- `aegisnex_remediation_successful_restarts_total`
- `aegisnex_remediation_failed_restarts_total`
- `aegisnex_notifications_sent_total`
- `aegisnex_notifications_failed_total`

Prometheus scrape example:

```yaml
scrape_configs:
  - job_name: aegisnex
    scrape_interval: 15s
    static_configs:
      - targets:
          - localhost:8000
```

Grafana starter panels:

- CPU: `aegisnex_system_cpu_usage_percent`
- Memory: `aegisnex_system_memory_usage_percent`
- Disk: `aegisnex_system_disk_usage_percent`
- Active incidents: `aegisnex_incidents_active`
- Container health: `aegisnex_containers_unhealthy`
- Restart attempts: `aegisnex_remediation_restart_attempts_total`
- Notification failures: `aegisnex_notifications_failed_total`

## Grafana Dashboards
AegisNex includes Grafana provisioning, Prometheus datasource configuration,
Docker Compose support, and dashboard JSON exports under `grafana/`.

Start AegisNex metrics first:

```bash
uvicorn src.dashboard:create_app --factory --host 0.0.0.0 --port 8000
```

Then start Grafana and Prometheus:

```bash
cd grafana
docker compose up -d
```

Open Grafana at `http://localhost:3000` with `admin` / `admin`.

Dashboard documentation and screenshot placeholders are in
`docs/grafana/README.md`.

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

## Notification Providers
AegisNex can notify on incident creation and resolution through configured
providers in `config.yaml`.

Supported providers:

- Email
- Slack webhook
- Discord webhook

Each provider supports enable/disable, retry attempts, retry delay, timeout, and
custom message templates.

Example:

```yaml
notifications:
  email:
    enabled: true
    retry_attempts: 2
    retry_delay_seconds: 1
    timeout_seconds: 10
    host: smtp.gmail.com
    port: 587
    starttls: true
    username: ""
    password: ""
    sender: ""
    recipient: ops@example.com
    subject: AegisNex Incident
    message_template: "[{severity}] {service_name}: {description} ({incident_id})"
    resolution_template: "[RESOLVED] {service_name}: {description} ({incident_id})"
  slack:
    enabled: true
    webhook_url: https://hooks.slack.com/services/...
    retry_attempts: 2
    retry_delay_seconds: 1
    timeout_seconds: 10
  discord:
    enabled: false
    webhook_url: https://discord.com/api/webhooks/...
```

Secrets can also be supplied with environment variables such as
`NOTIFY_EMAIL_USERNAME`, `NOTIFY_EMAIL_PASSWORD`, `SLACK_WEBHOOK_URL`, and
`DISCORD_WEBHOOK_URL`.

## Suggestions & Improvements
- Add log rotation and alert rate limiting policies per container.
- Support additional notification targets (Slack, PagerDuty, Teams).
- Persist health history to a lightweight datastore for trend analysis.
- Integrate container-specific health checks (HTTP endpoints, exit codes).
