# Administrator Guide

## Dashboard Access

| URL                  | Purpose                       | Auth Required |
|----------------------|-------------------------------|---------------|
| `http://localhost:8000/` | Main dashboard            | Yes           |
| `http://localhost:8000/login` | Login page            | No            |
| `http://localhost:8000/admin` | Admin panel           | Yes (admin)   |
| `http://localhost:8000/api/docs` | Swagger API docs   | Yes           |

### Default Admin Credentials (Development)

| Field    | Value              |
|----------|--------------------|
| Email    | `admin@aegisnex.io`|
| Password | `admin`            |

**Important:** Change the default admin password immediately in production.

---

## User Management

### Roles

| Role       | Permissions                                              |
|------------|----------------------------------------------------------|
| `admin`    | Full access: manage users, settings, agents, tools       |
| `operator` | Monitor, view incidents, approve actions, run reports    |
| `viewer`   | Read-only: view dashboard, metrics, reports              |

### API Operations

| Method | Endpoint                   | Description                |
|--------|----------------------------|----------------------------|
| `POST` | `/api/auth/register`       | Register new user          |
| `POST` | `/api/auth/login`          | Authenticate, get JWT      |
| `GET`  | `/api/users`               | List users (admin only)    |
| `PUT`  | `/api/users/{id}`          | Update user role (admin)   |
| `DELETE` | `/api/users/{id}`        | Delete user (admin)        |

### Creating a User

```powershell
curl -X POST http://localhost:8000/api/auth/register `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer <admin-token>" `
  -d '{\"email\": \"ops@example.com\", \"password\": \"securepass123\", \"role\": \"operator\"}'
```

---

## Multi-Tenant Administration

### Tenant Hierarchy

```
Organization
  └── Team
       └── Project
            └── Monitoring Targets / Users / Incidents / Workflows
```

### API Operations

| Method | Endpoint                            | Description                   |
|--------|-------------------------------------|-------------------------------|
| `POST` | `/api/organizations`                | Create organization           |
| `GET`  | `/api/organizations`                | List organizations            |
| `PUT`  | `/api/organizations/{id}`           | Update organization           |
| `POST` | `/api/organizations/{id}/teams`     | Create team                   |
| `GET`  | `/api/teams`                        | List teams                    |
| `POST` | `/api/teams/{id}/projects`          | Create project                |
| `GET`  | `/api/projects`                     | List projects                 |
| `POST` | `/api/organizations/{id}/invite`    | Invite user to org            |
| `DELETE` | `/api/organizations/{id}/users/{userId}` | Remove user from org    |

### Inviting a User to an Organization

```powershell
curl -X POST http://localhost:8000/api/organizations/1/invite `
  -H "Authorization: Bearer <admin-token>" `
  -H "Content-Type: application/json" `
  -d '{\"email\": \"user@example.com\", \"role\": \"operator\"}'
```

---

## Monitoring Targets

### Supported Target Types

| Type        | Description                        | Check Interval (default) |
|-------------|------------------------------------|--------------------------|
| `http`      | HTTP/HTTPS endpoint check          | 60 seconds               |
| `https`     | HTTPS with certificate validation  | 60 seconds               |
| `tcp`       | TCP port connectivity              | 60 seconds               |
| `ping`      | ICMP ping                          | 120 seconds              |
| `dns`       | DNS resolution check               | 120 seconds              |

### Managing Targets

```powershell
# List all targets
curl http://localhost:8000/api/targets -H "Authorization: Bearer <token>"

# Create target
curl -X POST http://localhost:8000/api/targets `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/json" `
  -d '{\"name\": \"Production API\", \"url\": \"https://api.example.com/health\", \"target_type\": \"https\", \"interval_seconds\": 60}'

# Get target details with check history
curl http://localhost:8000/api/targets/1 -H "Authorization: Bearer <token>"

# Update target
curl -X PUT http://localhost:8000/api/targets/1 `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/json" `
  -d '{\"interval_seconds\": 30}'

# Delete target
curl -X DELETE http://localhost:8000/api/targets/1 -H "Authorization: Bearer <token>"
```

---

## Notification Channels

### Supported Channels

| Channel      | Configuration Fields                     |
|--------------|------------------------------------------|
| `slack`      | `webhook_url`                            |
| `email`      | `smtp_server`, `smtp_port`, `username`, `password`, `from_address`, `to_address` |
| `pagerduty`  | `routing_key`                            |
| `teams`      | `webhook_url`                            |
| `discord`    | `webhook_url`                            |
| `webhook`    | `url`, `headers`                         |

### Managing Channels

```powershell
# List channels
curl http://localhost:8000/api/notifications/channels -H "Authorization: Bearer <token>"

# Add Slack channel
curl -X POST http://localhost:8000/api/notifications/channels `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/json" `
  -d '{\"type\": \"slack\", \"name\": \"alerts\", \"config\": {\"webhook_url\": \"https://hooks.slack.com/services/...\"}}'

# Test channel
curl -X POST http://localhost:8000/api/notifications/channels/1/test `
  -H "Authorization: Bearer <token>"
```

---

## Incident Management

### Incident Statuses

| Status      | Description                             |
|-------------|-----------------------------------------|
| `open`      | Active incident, not yet acknowledged   |
| `acknowledged` | Being investigated                   |
| `in_progress` | Remediation in progress              |
| `resolved`  | Fixed, awaiting confirmation            |
| `closed`    | Closed after confirmation               |

### Managing Incidents

```powershell
# List open incidents
curl "http://localhost:8000/api/incidents?status=open" -H "Authorization: Bearer <token>"

# Get incident details
curl http://localhost:8000/api/incidents/INC-001 -H "Authorization: Bearer <token>"

# Resolve incident
curl -X PUT http://localhost:8000/api/incidents/INC-001 `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/json" `
  -d '{\"status\": \"resolved\", \"resolution\": \"Restarted container web-01\"}'
```

---

## Compliance Management

### Built-in Frameworks

| Framework    | Controls | Assessment Frequency |
|--------------|----------|----------------------|
| ISO 27001    | 114      | Monthly              |
| SOC 2        | 65       | Monthly              |
| NIST CSF     | 98       | Quarterly            |
| CIS Controls | 153      | Quarterly            |
| OWASP Top 10 | 10       | Weekly               |

### Running Compliance Assessments

```powershell
# Trigger assessment
curl -X POST "http://localhost:8000/api/compliance/assess?framework=iso_27001" `
  -H "Authorization: Bearer <token>"

# View latest assessment
curl http://localhost:8000/api/compliance/reports/latest?framework=iso_27001 `
  -H "Authorization: Bearer <token>"

# List all reports
curl http://localhost:8000/api/compliance/reports `
  -H "Authorization: Bearer <token>"
```

---

## AI & Agent Management

### Approving AI Actions

Pending approvals appear in the dashboard UI and via API:

```powershell
# List pending approvals
curl http://localhost:8000/api/approvals/pending -H "Authorization: Bearer <token>"

# Approve or deny
curl -X POST http://localhost:8000/api/approvals/1/approve `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/json" `
  -d '{\"notes\": \"Approved after verification\"}'

curl -X POST http://localhost:8000/api/approvals/1/deny `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/json" `
  -d '{\"reason\": \"Manual intervention required\"}'
```

### Managing Agents

```powershell
# List registered agents
curl http://localhost:8000/api/agents -H "Authorization: Bearer <token>"

# Get agent details
curl http://localhost:8000/api/agents/ops-supervisor-001 -H "Authorization: Bearer <token>"
```

---

## Audit Logging

All admin actions are logged to the `audit_logs` table:

```powershell
# View audit log
curl "http://localhost:8000/api/audit/logs?limit=50" -H "Authorization: Bearer <token>"
```

Audit entries record: `actor`, `action`, `resource_type`, `resource_id`, `details`, `ip_address`, `timestamp`.

---

## Security Settings

### JWT Configuration

Configure via `.env`:

| Variable | Description | Recommendation |
|----------|-------------|----------------|
| `AEGISNEX_JWT_ALGORITHM` | Signing algorithm | `RS256` for production |
| `AEGISNEX_ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL | `15` for production |
| `AEGISNEX_SECRET_KEY` | Signing secret | 64+ char random string |

### Rate Limiting

Rate limits are enforced per endpoint group. Defaults:

| Group          | Rate Limit (per IP) |
|----------------|---------------------|
| Auth endpoints | 10/min              |
| API endpoints  | 60/min              |
| AI queries     | 20/min              |
| WebSocket      | 100/min             |

Configure via `AEGISNEX_RATE_LIMITS` environment variable.

---

## Troubleshooting

### Common Issues

| Symptom                          | Likely Cause                         | Resolution                          |
|----------------------------------|--------------------------------------|-------------------------------------|
| Dashboard won't load             | Database not initialized             | Run `python -m src.scripts.init_db` |
| AI responses returning errors    | Missing API key for provider         | Set `OPENAI_API_KEY` or equivalent  |
| WebSocket disconnects            | Reverse proxy not configured for WS  | Add `Upgrade` / `Connection` headers|
| "Permission denied" errors       | User role lacks required permission  | Update user role via admin panel    |
| Docker tools return empty        | Docker daemon not running            | Start Docker Desktop or dockerd     |
| PostgreSQL connection failures   | Database URL misconfigured           | Check `AEGISNEX_DATABASE_URL`       |
| Scheduled tasks not firing       | Redis not configured or unreachable  | Start Redis, update `REDIS_URL`     |

### Logs

```powershell
# View application logs
Get-Content -Path .\logs\aegisnex.log -Tail 100

# Set debug level
$env:AEGISNEX_LOG_LEVEL = "DEBUG"
python -m uvicorn src.dashboard:app --reload --port 8000
```
