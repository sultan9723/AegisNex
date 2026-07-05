# Tool Reference

## Overview

The AegisNex tool system (`src/intelligence/tools.py`) provides a registry of callable tools used by the AI engine, agents, runbooks, and workflows. Each tool returns structured JSON and never calls another tool directly.

---

## Tool Model

### `ToolDef` (Definition)

| Field              | Type                     | Description                               |
|--------------------|--------------------------|-------------------------------------------|
| `name`             | `str`                    | Unique tool identifier                    |
| `description`      | `str`                    | Human-readable description                |
| `category`         | `str`                    | Grouping: monitoring, containers, etc.    |
| `parameters`       | `List[Dict]`             | JSON parameter schema                     |
| `permission_level` | `PermissionLevel`        | viewer, operator, admin                   |
| `access_mode`      | `AccessMode`             | read, write                               |
| `risk_level`       | `RiskLevel`              | none, low, medium, high, critical         |
| `requires_approval`| `bool`                   | Whether execution requires human approval |
| `destructive`      | `bool`                   | Whether tool modifies system state        |
| `fn`               | `Optional[ToolFn]`       | Implementation function                   |

### `Tool` (Runtime)

| Field | Type | Description |
|-------|------|-------------|
| Same as `ToolDef` plus `execute(**kwargs)` | — | Calls `fn` with kwargs, auto-injects `tool` name and `timestamp` |

---

## Registered Tools

### `metrics`
| Property          | Value                                      |
|-------------------|--------------------------------------------|
| **Category**      | `monitoring`                               |
| **Permission**    | `viewer` / `read`                          |
| **Risk Level**    | `none`                                     |
| **Requires Approval** | No                                     |

Retrieves current system metrics via `PrometheusExporter.collect()`.

**Returns:**
```json
{
  "metrics": { "cpu_percent": 45.2, "memory_percent": 67.1, ... },
  "count": 12,
  "status": "ok"
}
```

---

### `docker`
| Property          | Value                                      |
|-------------------|--------------------------------------------|
| **Category**      | `containers`                               |
| **Permission**    | `viewer` / `read`                          |
| **Risk Level**    | `none`                                     |
| **Requires Approval** | No                                     |

Lists all Docker containers via `DockerScanner.run()`.

**Returns:**
```json
{
  "containers": [
    {
      "id": "abc123",
      "name": "web-server",
      "status": "running",
      "health": "healthy",
      "cpu_percent": 12.3,
      "memory_percent": 34.5
    }
  ],
  "count": 5,
  "status": "ok"
}
```

---

### `incident`
| Property          | Value                                      |
|-------------------|--------------------------------------------|
| **Category**      | `incidents`                                |
| **Permission**    | `viewer` / `read`                          |
| **Risk Level**    | `none`                                     |
| **Requires Approval** | No                                     |

Queries incidents via `IncidentManager`.

**Parameters:**
| Parameter     | Type     | Description                      | Required |
|---------------|----------|----------------------------------|----------|
| `action`      | `string` | `list`, `get`, `active`          | No       |
| `incident_id` | `string` | Incident ID for `get` action     | No       |
| `status`      | `string` | Filter by status for `list`      | No       |

**Returns:**
```json
{
  "incidents": [{ "id": "INC-001", "title": "High CPU", "status": "open", ... }],
  "count": 3
}
```

---

### `target`
| Property          | Value                                      |
|-------------------|--------------------------------------------|
| **Category**      | `monitoring`                               |
| **Permission**    | `viewer` / `read`                          |
| **Risk Level**    | `none`                                     |
| **Requires Approval** | No                                     |

Lists monitoring targets with latest check results.

**Parameters:**
| Parameter    | Type      | Description                 | Required |
|--------------|-----------|-----------------------------|----------|
| `action`     | `string`  | `list`, `get`               | No       |
| `target_id`  | `integer` | Target ID for `get` action  | No       |
| `target_type`| `string`  | Filter by type for `list`   | No       |

**Returns:**
```json
{
  "targets": [
    {
      "id": 1,
      "name": "Production API",
      "target_type": "http",
      "latest_result": { "status_code": 200, "response_time_ms": 45 },
      "last_checked_at": "2025-01-15T10:30:00Z"
    }
  ],
  "count": 8
}
```

---

### `audit`
| Property          | Value                                      |
|-------------------|--------------------------------------------|
| **Category**      | `system`                                   |
| **Permission**    | `viewer` / `read`                          |
| **Risk Level**    | `none`                                     |
| **Requires Approval** | No                                     |

Retrieves recent audit log entries from the platform database.

**Parameters:**
| Parameter | Type      | Description                     | Required |
|-----------|-----------|----------------------------------|----------|
| `limit`   | `integer` | Number of log entries (max 100)  | No       |

**Returns:**
```json
{
  "logs": [
    {
      "id": 1,
      "action": "target.create",
      "actor": "admin@example.com",
      "timestamp": "2025-01-15T10:00:00Z"
    }
  ],
  "count": 50
}
```

---

### `report`
| Property          | Value                                      |
|-------------------|--------------------------------------------|
| **Category**      | `reports`                                  |
| **Permission**    | `viewer` / `read`                          |
| **Risk Level**    | `none`                                     |
| **Requires Approval** | No                                     |

Generates operational reports via `OperationalReporter`.

**Parameters:**
| Parameter    | Type     | Description              | Required |
|--------------|----------|--------------------------|----------|
| `report_type`| `string` | `weekly` or `monthly`    | No       |

**Returns:**
```json
{
  "report": { "summary": "...", "sections": [...] },
  "report_type": "weekly"
}
```

---

### `notification`
| Property          | Value                                      |
|-------------------|--------------------------------------------|
| **Category**      | `notifications`                            |
| **Permission**    | `viewer` / `read`                          |
| **Risk Level**    | `none`                                     |
| **Requires Approval** | No                                     |

Lists notification history and configured channels.

**Parameters:**
| Parameter | Type     | Description           | Required |
|-----------|----------|-----------------------|----------|
| `action`  | `string` | `list`                | No       |

**Returns:**
```json
{
  "notifications": [
    { "id": 1, "channel": "slack", "message": "...", "status": "sent" }
  ],
  "total_count": 150,
  "sent_count": 145,
  "failed_count": 5,
  "channels": ["slack", "email", "pagerduty"],
  "channel_count": 3
}
```

---

### `health`
| Property          | Value                                      |
|-------------------|--------------------------------------------|
| **Category**      | `system`                                   |
| **Permission**    | `viewer` / `read`                          |
| **Risk Level**    | `none`                                     |
| **Requires Approval** | No                                     |

Comprehensive system health check — database, Docker, CPU, memory, disk.

**Returns:**
```json
{
  "timestamp": "2025-01-15T10:30:00Z",
  "database": { "status": "ok", "size_mb": 156 },
  "cpu_percent": 32.1,
  "memory_percent": 55.0,
  "disk_percent": 42.3,
  "docker_available": true,
  "containers_running": 8,
  "containers_total": 10
}
```

---

## Registry API

### `get_tool(name: str) -> Optional[Tool]`

Retrieves a tool by name.

### `list_tools(category: Optional[str]) -> List[Dict]`

Lists all tools, optionally filtered by category.

### `list_tool_definitions() -> List[Dict]`

Returns governance definitions for all tools (permission, risk, approval).

### `execute_tool(name, repo, **kwargs) -> Dict`

Executes a tool by name. Returns `{"status": "error", "error": "..."}` for unknown tools.

### `is_destructive(name: str) -> bool`

Checks if a tool is marked destructive.

### `requires_human_approval(name: str) -> bool`

Checks if a tool requires human approval before execution.

### `get_tool_risk_level(name: str) -> str`

Returns the risk level string for a tool.

---

## Categories

| Category        | Tools                              |
|-----------------|------------------------------------|
| `monitoring`    | `metrics`, `target`                |
| `containers`    | `docker`                           |
| `incidents`     | `incident`                         |
| `system`        | `audit`, `health`                  |
| `reports`       | `report`                           |
| `notifications` | `notification`                     |

---

## Safety Model

| Enum            | Values                              |
|-----------------|-------------------------------------|
| `RiskLevel`     | `none`, `low`, `medium`, `high`, `critical` |
| `AccessMode`    | `read`, `write`                     |
| `PermissionLevel` | `viewer`, `operator`, `admin`     |

All currently registered tools are read-only (`READ`), `VIEWER`-level, and `NONE` risk. Destructive or high-risk tools (`DESTRUCTIVE_TOOLS`) can be added by registering them with `destructive=True`, `requires_approval=True`, and an appropriate `risk_level`.
