# Phase 3 — Real Integrations Implementation

## Objective
Replace all placeholder/mock data in the Next.js frontend with real data from the AegisNex backend API. Every integration status, tool description, and report summary now originates from live backend checks.

## Changes Summary

### 1. Backend: Real Integration Health Checks
**File:** `src/dashboard.py` — `build_integrations_context()`

Replaced the static integration list with live health checks:

- **Grafana**
  - Probes `/api/health` on the configured Grafana URL (from `config.yaml` or defaults to `http://localhost:3000`).
  - Status reflects actual HTTP reachability:
    - `connected` — health endpoint returned 200
    - `configured` — `grafana/` directory exists but service unreachable
    - `not configured` — no provisioning directory found
  - Returns `url` for direct dashboard access when reachable.

- **Prometheus**
  - Queries `/api/v1/targets` on the configured Prometheus URL.
  - Status reflects actual API reachability:
    - `connected` — API returned `status: success`
    - `configured` — `grafana/prometheus/` directory exists but unreachable
    - `not configured` — no provisioning directory found
  - Returns `url` pointing to `/metrics` scrape endpoint.

- **Docker**
  - Invokes `DockerScanner.run({"include_all": True})` to get live container inventory.
  - Status reflects actual Docker socket connectivity:
    - `connected` — scanner returned `status: ok`
    - `disconnected` — scanner failed
  - Description includes real container counts (running/total).

- **MCP**
  - Instantiates `create_mcp_server()` and inspects registered tools.
  - Status reflects actual server state:
    - `available` — tools registered successfully
    - `unavailable` — server failed to initialize
  - Description includes real tool count.

- **SQLite**
  - Executes `repository.fetch_all("incidents", limit=1)` to verify DB connectivity.
  - Status reflects actual database state:
    - `connected` — query succeeded
    - `disconnected` — query failed

### 2. Backend: New REST API Endpoints
**File:** `src/dashboard.py` — inside `create_app()`

| Endpoint | Auth | Returns |
|----------|------|---------|
| `GET /api/integrations` | Required | `{ integrations: IntegrationRow[] }` |
| `GET /api/mcp` | Required | `{ mcp_tools: MCPToolDescription[], claude_config: string }` |
| `GET /api/reports` | Required | `{ reports: ReportSummary[] }` |

### 3. Frontend: API Client Types & Methods
**File:** `frontend/lib/api.ts`

Added typed fetch wrappers:

```typescript
export type IntegrationRow = {
  name: string;
  status: string;
  description: string;
  url?: string;
  reachable?: boolean;
};

export type IntegrationsResponse = {
  integrations: IntegrationRow[];
};

export type MCPToolDescription = {
  name: string;
  description: string;
  example: string;
};

export type MCPResponse = {
  mcp_tools: MCPToolDescription[];
  claude_config: string;
};

export function getIntegrations() {
  return fetchJson<IntegrationsResponse>("/api/integrations");
}

export function getMCPTools() {
  return fetchJson<MCPResponse>("/api/mcp");
}
```

### 4. Frontend: Integrations Page Rewrite
**File:** `frontend/app/integrations/page.tsx`

- Removed all `process.env.NEXT_PUBLIC_*` references.
- Fetches live integration data via `getIntegrations()`.
- Renders dynamic icon per integration name.
- Status badge reflects `reachable` boolean from backend.
- Shows "Open" button only when URL is present and service is reachable.
- Displays loading skeletons and error states.

### 5. Frontend: MCP Page Rewrite
**File:** `frontend/app/mcp/page.tsx`

- Removed hardcoded tool name array.
- Fetches live tool list via `getMCPTools()`.
- Displays real tool descriptions and example JSON payloads.
- Shows Claude Desktop config in formatted code block.
- Status badge reflects whether tools are registered.
- Displays loading skeletons and error states.

### 6. Frontend: Reports Page Rewrite
**File:** `frontend/app/reports/page.tsx`

- Fetches report summaries from `/api/reports`.
- Displays dynamic window labels from backend payload.
- Maintains download links for JSON/CSV/PDF formats.
- Displays loading skeletons and error states.

## Verification

- [x] `GET /api/integrations` returns real health-checked integration data.
- [x] `GET /api/mcp` returns real tool list from `src.mcp_server`.
- [x] `GET /api/reports` returns real report summary from backend.
- [x] Integrations page shows no hardcoded env-var statuses.
- [x] MCP page shows no hardcoded tool strings.
- [x] Reports page shows dynamic summaries from API.
- [x] All pages have loading/error state handling.

## Notes

- All backend checks are synchronous within the request context (fast I/O with 3-second timeouts).
- Docker/MCP checks use existing service instances (`app.state.services`).
- Grafana/Prometheus checks use `urllib.request` to avoid adding HTTP client dependencies.
- Frontend pages use `"use client"` directive for Next.js App Router compatibility.
- TypeScript types added to `frontend/lib/api.ts` ensure compile-time safety.