# API Reference

Base URL: `http://<host>:<port>/api`

Authentication: JWT Bearer token (Authorization header or `aegisnex_session` cookie) or `X-API-Key` header.

---

## Public Health Endpoints

| Method | Path                 | Auth   | Description                        |
|--------|----------------------|--------|------------------------------------|
| GET    | `/api/health`        | No     | Basic health check                 |
| GET    | `/api/health/ready`  | No     | Readiness probe (checks DB)        |
| GET    | `/api/health/live`   | No     | Liveness probe                     |
| GET    | `/api/health/status` | Viewer | Detailed health status             |

**GET /api/health** → `{ "status": "ok", "timestamp": "...", "service": "aegisnex" }`

**GET /api/health/ready** → `{ "status": "ready" }` or `{ "status": "not_ready", "reason": "..." }`

**GET /api/health/status** → `{ "service": "aegisnex", "version": "1.0.0", "database": {...}, "docker": {...} }`

---

## Authentication

| Method | Path                | Auth    | Description                     |
|--------|---------------------|---------|----------------------------------|
| POST   | `/api/login`        | No      | Login with email/password        |
| GET    | `/api/auth/verify`  | Viewer  | Verify current token             |
| GET    | `/logout`           | Any     | Logout (clears session cookie)   |

**POST /api/login** → rate limited (5/min)
```
Request: { "username": "email", "password": "..." }
Response: { "access_token": "...", "token_type": "bearer", "refresh_token": "..." }
Sets aegisnex_session cookie.
```

**GET /api/auth/verify** → `{ "authenticated": true, "user": { "id", "email", "role", "is_superuser" } }`

---

## Dashboard

| Method | Path                               | Auth    | Description                           |
|--------|------------------------------------|---------|---------------------------------------|
| GET    | `/api/dashboard`                   | Viewer  | Full dashboard snapshot               |
| GET    | `/api/system-health`               | Viewer  | System health summary                 |
| GET    | `/api/system-info`                 | Viewer  | OS, hostname, uptime, Docker version  |
| GET    | `/api/metrics`                     | Viewer  | Current metrics (CPU, memory, etc.)   |
| GET    | `/api/metrics/history`             | Viewer  | Historical metrics (query: minutes)   |
| GET    | `/api/integrations`                | Viewer  | Integration status overview           |
| GET    | `/api/mcp`                         | Viewer  | MCP server tool list                  |

**GET /api/dashboard** → `{ "system": {...}, "containers": {...}, "incidents": {...}, "metrics": {...}, "notifications": {...}, "remediations": {...}, "http_monitoring": {...}, "ssl_monitoring": {...}, "tcp_monitoring": {...} }`

**GET /api/metrics/history?minutes=60** → `{ "history": [...], "count": N, "minutes": 60 }`

---

## Incidents

| Method | Path                                          | Auth      | Description                      |
|--------|-----------------------------------------------|-----------|----------------------------------|
| GET    | `/api/incidents`                               | Viewer    | List incidents (query: limit, offset) |
| GET    | `/api/incidents/{incident_id}`                 | Viewer    | Get incident detail + timeline    |
| POST   | `/api/incidents/{incident_id}/acknowledge`     | Operator  | Acknowledge incident             |
| POST   | `/api/incidents/{incident_id}/resolve`         | Operator  | Resolve incident with notes      |
| POST   | `/api/incidents/{incident_id}/reopen`          | Operator  | Reopen resolved incident         |
| DELETE | `/api/incidents/{incident_id}`                 | Admin     | Delete incident                  |

**GET /api/incidents?limit=100&offset=0** → `{ "active_incidents": [...], "resolved_incidents": [...], "incidents": [...], "active_count": N, "resolved_count": N }`

**GET /api/incidents/{id}** → `{ "incident": {...}, "timeline": [...] }`

---

## Containers

| Method | Path                                       | Auth      | Description                  |
|--------|--------------------------------------------|-----------|------------------------------|
| GET    | `/api/containers`                          | Viewer    | List all containers          |
| POST   | `/api/containers/{name}/start`             | Operator  | Start container              |
| POST   | `/api/containers/{name}/stop`              | Operator  | Stop container               |
| POST   | `/api/containers/{name}/restart`           | Operator  | Restart container            |
| GET    | `/api/containers/{name}/logs`              | Viewer    | Get container logs (query: tail) |

---

## Monitoring Targets

| Method | Path                                                | Auth      | Description                  |
|--------|-----------------------------------------------------|-----------|------------------------------|
| GET    | `/api/monitoring-targets`                           | Viewer    | List all targets             |
| POST   | `/api/monitoring-targets`                           | Operator  | Create target                |
| PUT    | `/api/monitoring-targets/{target_id}`               | Operator  | Update target                |
| DELETE | `/api/monitoring-targets/{target_id}`               | Operator  | Delete target                |
| POST   | `/api/monitoring-targets/{target_id}/run`           | Operator  | Run check on target          |
| GET    | `/api/monitoring-targets/{target_id}/history`       | Viewer    | Check history (limit 100)    |
| GET    | `/api/http-monitoring`                              | Viewer    | HTTP monitoring summary      |
| GET    | `/api/ssl-monitoring`                               | Viewer    | SSL monitoring summary       |
| GET    | `/api/tcp-monitoring`                               | Viewer    | TCP monitoring summary       |

**POST /api/monitoring-targets** →
```
Request: { "name": "...", "target_type": "http|tcp|ssl", "address": "...", ... }
```

---

## Notifications

| Method | Path                                                   | Auth      | Description                     |
|--------|--------------------------------------------------------|-----------|----------------------------------|
| GET    | `/api/notifications`                                   | Viewer    | Notification history            |
| GET    | `/api/notification-channels`                           | Viewer    | List channels                   |
| GET    | `/api/notification-channels/{channel_id}`              | Viewer    | Get channel detail              |
| POST   | `/api/notification-channels`                           | Operator  | Create channel                  |
| PUT    | `/api/notification-channels/{channel_id}`              | Operator  | Update channel                  |
| DELETE | `/api/notification-channels/{channel_id}`              | Operator  | Delete channel                  |
| POST   | `/api/notification-channels/test/{channel_type}`       | Operator  | Send test notification          |

---

## AI Intelligence

| Method | Path                              | Auth      | Description                     |
|--------|-----------------------------------|-----------|----------------------------------|
| POST   | `/api/ai/chat`                    | Viewer    | Full AI chat (plan→execute→verify)|
| POST   | `/api/ai/analyze`                 | Viewer    | Full analysis workflow          |
| POST   | `/api/ai/plan`                    | Viewer    | Planning phase only             |
| GET    | `/api/ai/history`                 | Viewer    | AI workflow history (query: limit, offset) |
| GET    | `/api/ai/tools`                   | Viewer    | List registered AI tools        |
| GET    | `/api/ai/workflows`               | Viewer    | Workflow graph definition       |
| GET    | `/api/ai/executions`              | Viewer    | AI execution history + stats    |
| GET    | `/api/ai/memory`                  | Viewer    | Query AI memory (query: type, q) |
| GET    | `/api/ai/timeline`                | Viewer    | Combined conversations + learnings |
| GET    | `/api/ai/policies`                | Viewer    | List AI policies                |
| GET    | `/api/ai/risk`                    | Viewer    | Risk assessment (query: tool)   |
| POST   | `/api/ai/approve`                 | Operator  | Approve pending action          |
| POST   | `/api/ai/reject`                  | Operator  | Reject pending action           |
| GET    | `/api/ai/pending-approvals`       | Viewer    | List pending approvals          |

**POST /api/ai/chat** →
```
Request: { "request": "check system health and containers" }
Response: { "answer": "...", "goal_achieved": bool, "confidence": 0.0, "steps": [...], "observations": [...], "corrections": [...], "errors": [...], "evidence": [...], "reasoning_summary": "...", "execution_duration_ms": 0.0, ... }
```

**POST /api/ai/plan** →
```
Request: { "request": "investigate high CPU" }
Response: { "objective": "...", "plan": {...}, "current_plan": [...], "parallel_batches": [...], "missing_info": [...] }
```

**GET /api/ai/memory?type=conversations&limit=10** → `{ "entries": [...], "count": N, "type": "conversations" }`

**GET /api/ai/memory?q=search+term** → `{ "entries": [...], "total": N, "query": "..." }`

---

## AI Runbooks

| Method | Path                     | Auth      | Description                  |
|--------|--------------------------|-----------|------------------------------|
| GET    | `/api/runbooks`          | Viewer    | List all runbooks            |
| POST   | `/api/runbooks/execute`  | Operator  | Execute a runbook            |

**POST /api/runbooks/execute** →
```
Request: { "runbook": "high-cpu" }
Response: { "runbook_name": "high-cpu", "status": "completed", "step_results": [...], "total_duration_ms": 0.0 }
```

---

## AI Workflows

| Method | Path                        | Auth      | Description                  |
|--------|-----------------------------|-----------|------------------------------|
| POST   | `/api/workflows/start`      | Operator  | Start a workflow by name     |
| GET    | `/api/workflows/history`    | Viewer    | Workflow execution history   |

---

## AI Timeline

| Method | Path                   | Auth      | Description                          |
|--------|------------------------|-----------|--------------------------------------|
| GET    | `/api/ai/timeline`     | Viewer    | Combined timeline (convos + learnings)|

---

## AI Policies

| Method | Path                   | Auth      | Description                  |
|--------|------------------------|-----------|------------------------------|
| GET    | `/api/ai/policies`     | Viewer    | List all AI policies         |

---

## AI Risk

| Method | Path              | Auth      | Description                         |
|--------|-------------------|-----------|-------------------------------------|
| GET    | `/api/ai/risk`    | Viewer    | Assess risk for a tool (?tool=name) |

---

## AI Approvals

| Method | Path                             | Auth      | Description                  |
|--------|----------------------------------|-----------|------------------------------|
| POST   | `/api/ai/approve`                | Operator  | Approve an action            |
| POST   | `/api/ai/reject`                 | Operator  | Reject an action             |
| GET    | `/api/ai/pending-approvals`      | Viewer    | List pending approvals       |
| POST   | `/api/approval/respond`          | Operator  | Unified approval response    |

**POST /api/ai/approve** → `Request: { "approval_id": "..." }` → `{ "status": "approved", ... }`

**POST /api/approval/respond** →
```
Request: { "approval_id": "...", "decision": "approve|reject" }
Response: { "status": "approved|rejected", "approval_id": "..." }
```

---

## AI Skills

| Method | Path                         | Auth      | Description                     |
|--------|------------------------------|-----------|----------------------------------|
| GET    | `/api/skills`                | Viewer    | List all AI skills              |
| POST   | `/api/skills/execute`        | Operator  | Execute a skill by ID           |
| POST   | `/api/skills/auto-select`    | Viewer    | Auto-select skills for a task   |
| POST   | `/api/skills/pipeline`       | Operator  | Execute a pipeline of skills    |

**POST /api/skills/execute** →
```
Request: { "skill_id": "builtin.system_analyzer", "context": {} }
```

---

## Multi-Agent

| Method | Path                        | Auth      | Description                          |
|--------|-----------------------------|-----------|--------------------------------------|
| GET    | `/api/agents`               | Viewer    | List registered agents               |
| POST   | `/api/agents/dispatch`      | Operator  | Dispatch task to agent               |
| POST   | `/api/agents/collaborate`   | Operator  | Multi-agent collaboration            |
| POST   | `/api/agents/fan-out`       | Operator  | Fan-out task to all agents           |
| GET    | `/api/agents/state`         | Viewer    | Get shared agent state               |

**POST /api/agents/dispatch** →
```
Request: { "task": "check system health", "agent_id": "ops-supervisor-001" }
```

**POST /api/agents/collaborate** →
```
Request: { "task": "audit security and compliance", "agent_ids": ["sec-supervisor-001", "comp-supervisor-001"] }
```

---

## Integrations / Marketplace

| Method | Path                     | Auth      | Description                  |
|--------|--------------------------|-----------|------------------------------|
| GET    | `/api/integrations`      | Viewer    | Integration status overview  |

---

## Knowledge Management

| Method | Path                                   | Auth      | Description                     |
|--------|----------------------------------------|-----------|----------------------------------|
| POST   | `/api/knowledge/upload`                | Operator  | Upload document for indexing     |
| POST   | `/api/knowledge/index-directory`       | Operator  | Index a directory of documents   |
| GET    | `/api/knowledge/search`                | Viewer    | Search knowledge base (q, limit) |
| GET    | `/api/knowledge/stats`                 | Viewer    | Knowledge base statistics        |
| DELETE | `/api/knowledge/remove`                | Operator  | Remove document by source        |

**POST /api/knowledge/upload** → multipart form with `file` field → `{ "status": "ok", "document": "name", "chunks_indexed": N }`

**GET /api/knowledge/search?q=cpu+usage&limit=10** → `{ "results": [...], "count": N }`

---

## Compliance

| Method | Path                                            | Auth      | Description                          |
|--------|-------------------------------------------------|-----------|--------------------------------------|
| GET    | `/api/compliance/frameworks`                    | Viewer    | List all frameworks                  |
| GET    | `/api/compliance/framework/{framework_id}`      | Viewer    | Get framework detail                 |
| POST   | `/api/compliance/check/{framework_id}`          | Operator  | Run compliance check                 |
| GET    | `/api/compliance/results/{framework_id}`        | Viewer    | Get check results                    |
| GET    | `/api/compliance/dashboard`                     | Viewer    | Compliance dashboard (query: framework_id) |
| GET    | `/api/compliance/report/{framework_id}`         | Viewer    | Generate compliance report (query: format) |

**GET /api/compliance/frameworks** → `{ "frameworks": [...], "count": N }`

**POST /api/compliance/check/{id}** → `{ "framework_id": "...", "checked": N, "results": [...], "summary": {...} }`

---

## Enterprise Search

| Method | Path                        | Auth      | Description                        |
|--------|-----------------------------|-----------|------------------------------------|
| GET    | `/api/search`               | Viewer    | Search across all domains (q, domain, limit) |
| GET    | `/api/search/domains`       | Viewer    | List search domains + counts       |
| POST   | `/api/search/reindex`       | Operator  | Rebuild search index               |
| GET    | `/api/search/stats`         | Viewer    | Search index statistics            |

**GET /api/search?q=incident+nginx&domain=incidents&limit=20** →
```
{
  "results": [{ "domain": "incidents", "id": "...", "title": "...",
                "snippet": "...", "url": "...", "score": 0.95, "metadata": {...} }],
  "total": 5, "domains": {"incidents": 5}, "query": "incident nginx", "duration_ms": 12.5
}
```

---

## Telemetry

| Method | Path                                  | Auth      | Description                         |
|--------|---------------------------------------|-----------|-------------------------------------|
| GET    | `/api/telemetry/api-stats`            | Viewer    | API latency stats (query: hours)    |
| GET    | `/api/telemetry/workflow-stats`       | Viewer    | Workflow execution stats            |
| GET    | `/api/telemetry/agent-stats`          | Viewer    | Agent execution stats               |
| GET    | `/api/telemetry/tool-failures`        | Viewer    | Tool failure stats                  |
| GET    | `/api/telemetry/approval-stats`       | Viewer    | Approval time stats                  |
| GET    | `/api/telemetry/dashboard`            | Viewer    | Telemetry dashboard summary         |

---

## Multi-Tenant

### Organizations

| Method | Path                       | Auth      | Description                    |
|--------|----------------------------|-----------|--------------------------------|
| GET    | `/api/orgs`                | Viewer    | List organizations             |
| POST   | `/api/orgs`                | Admin     | Create organization            |
| GET    | `/api/orgs/{org_id}`       | Viewer    | Get organization               |
| PUT    | `/api/orgs/{org_id}`       | Operator  | Update organization            |
| DELETE | `/api/orgs/{org_id}`       | Admin     | Deactivate organization        |
| GET    | `/api/orgs/{org_id}/stats` | Viewer    | Organization statistics        |
| GET    | `/api/orgs/{org_id}/users` | Viewer    | Users in organization          |

### Teams

| Method | Path                                   | Auth      | Description                    |
|--------|----------------------------------------|-----------|--------------------------------|
| GET    | `/api/orgs/{org_id}/teams`             | Viewer    | List teams in org              |
| POST   | `/api/orgs/{org_id}/teams`             | Operator  | Create team                    |

### Projects

| Method | Path                                     | Auth      | Description                    |
|--------|------------------------------------------|-----------|--------------------------------|
| GET    | `/api/orgs/{org_id}/projects`            | Viewer    | List projects (query: team_id) |
| POST   | `/api/orgs/{org_id}/projects`            | Operator  | Create project                 |

### User Assignment

| Method | Path                             | Auth   | Description                     |
|--------|----------------------------------|--------|----------------------------------|
| POST   | `/api/orgs/{org_id}/users`       | Admin  | Assign user to org with role    |

---

## User Management

| Method | Path                              | Auth      | Description                  |
|--------|-----------------------------------|-----------|------------------------------|
| GET    | `/api/users`                      | Admin     | List all users               |
| PUT    | `/api/users/{user_id}/role`       | Admin     | Update user role (query: role)|
| POST   | `/api/users/{user_id}/deactivate` | Admin     | Deactivate user              |

---

## API Keys

| Method | Path                         | Auth      | Description                  |
|--------|------------------------------|-----------|------------------------------|
| GET    | `/api/api-keys`              | Admin     | List API keys                |
| POST   | `/api/api-keys`              | Admin     | Create API key               |
| PUT    | `/api/api-keys/{key_id}`     | Admin     | Update API key               |
| DELETE | `/api/api-keys/{key_id}`     | Admin     | Delete API key               |

**POST /api/api-keys** →
```
Request: { "name": "ci-cd-key", "role": "operator" }
Response: { "name": "ci-cd-key", "api_key": "aeg_...", "key_prefix": "aeg_...", "role": "operator" }
```

---

## Settings

| Method | Path                | Auth      | Description                  |
|--------|---------------------|-----------|------------------------------|
| GET    | `/api/settings`     | Viewer    | Get all settings             |
| PUT    | `/api/settings`     | Operator  | Update settings              |

---

## Alert Rules

| Method | Path                              | Auth      | Description                  |
|--------|-----------------------------------|-----------|------------------------------|
| GET    | `/api/alert-rules`                | Viewer    | List alert rules             |
| POST   | `/api/alert-rules`                | Operator  | Create alert rule            |
| PUT    | `/api/alert-rules/{rule_id}`      | Operator  | Update alert rule            |
| DELETE | `/api/alert-rules/{rule_id}`      | Operator  | Delete alert rule            |

---

## Audit Logs

| Method | Path                    | Auth      | Description                       |
|--------|-------------------------|-----------|-----------------------------------|
| GET    | `/api/audit-logs`       | Viewer    | List audit logs (query: limit, offset) |

---

## Reports

| Method | Path                                          | Auth      | Description                     |
|--------|-----------------------------------------------|-----------|----------------------------------|
| GET    | `/api/reports`                                | Viewer    | Available report types          |
| GET    | `/api/reports/{report_type}/{report_format}`  | Viewer    | Download report (format: json/csv/pdf) |

---

## Prometheus Metrics

| Method | Path           | Auth                                 | Description              |
|--------|----------------|--------------------------------------|--------------------------|
| GET    | `/metrics`     | Bearer token or `AEGISNEX_METRICS_TOKEN` | Prometheus-formatted metrics |

---

## WebSocket Endpoints

| Path                          | Auth   | Description                          |
|-------------------------------|--------|--------------------------------------|
| `/ws/dashboard`               | JWT    | Real-time dashboard updates          |
| `/ws/incidents`               | JWT    | Incident stream                      |
| `/ws/containers`              | JWT    | Container status stream              |
| `/ws/targets`                 | JWT    | Monitoring target updates            |
| `/ws/containers/{name}/logs`  | JWT    | Container log stream                 |

All WebSocket connections authenticate via `aegisnex_session` cookie or `Authorization: Bearer <token>` header.
