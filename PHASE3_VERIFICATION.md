# Phase 3 — Real Integrations Verification

## Backend Verification

### Endpoint: GET /api/integrations
- [x] Requires authentication (401 without token)
- [x] Returns `{ integrations: [...] }`
- [x] Each integration has `name`, `status`, `description`, `url?`, `reachable?`
- [x] Grafana status reflects real health check (not hardcoded)
- [x] Prometheus status reflects real target health (not hardcoded)
- [x] Docker status reflects real scanner connectivity
- [x] Docker description includes live container count
- [x] MCP status reflects real tool registration
- [x] MCP description includes live tool count
- [x] SQLite status reflects real DB connectivity

### Endpoint: GET /api/mcp
- [x] Requires authentication (401 without token)
- [x] Returns `{ mcp_tools: [...], claude_config: string }`
- [x] Tool list comes from `src.mcp_server` (not hardcoded)
- [x] Each tool has `name`, `description`, `example`
- [x] Claude config is valid JSON string

### Endpoint: GET /api/reports
- [x] Requires authentication (401 without token)
- [x] Returns `{ reports: [...] }`
- [x] Report summaries come from backend (not hardcoded)

## Frontend Verification

### Integrations Page (`/integrations`)
- [x] No `process.env.NEXT_PUBLIC_GRAFANA_URL` references
- [x] No `process.env.NEXT_PUBLIC_PROMETHEUS_URL` references
- [x] Fetches data from `/api/integrations`
- [x] Shows loading skeletons while fetching
- [x] Shows error state on API failure
- [x] Status badge reflects backend `reachable` field
- [x] "Open" button appears only for reachable services with URLs
- [x] Icons are dynamic per integration name
- [x] Description comes from backend response

### MCP Page (`/mcp`)
- [x] No hardcoded tool name array
- [x] Fetches data from `/api/mcp`
- [x] Shows loading skeletons while fetching
- [x] Shows error state on API failure
- [x] Tool list matches backend response
- [x] Each tool shows real description and example
- [x] Claude config displayed in formatted code block
- [x] Status badge reflects tool availability

### Reports Page (`/reports`)
- [x] Fetches data from `/api/reports`
- [x] Shows loading skeletons while fetching
- [x] Shows error state on API failure
- [x] Report list comes from backend
- [x] Window labels come from backend payload
- [x] Download links preserved for all formats

## Test Results

### Backend Tests
```bash
pytest
```
- [ ] All existing tests pass
- [ ] No regressions introduced
- [ ] New endpoints return expected shapes

### Frontend Lint
```bash
npm run lint
```
- [ ] Zero TypeScript errors
- [ ] Zero ESLint errors
- [ ] No unused variables

### Frontend Build
```bash
npm run build
```
- [ ] Build completes successfully
- [ ] No compilation errors
- [ ] No missing type errors

## Mock Data Audit
- [x] No mock data in integrations page
- [x] No mock data in MCP page
- [x] No mock data in reports page
- [x] No placeholder cards in any page
- [x] No fake status badges
- [x] Every displayed status comes from backend API

## Completeness Check
- [x] Grafana availability detected via health endpoint
- [x] Prometheus scrape endpoint verified via targets API
- [x] MCP server connection tested via tool enumeration
- [x] Docker container inventory fetched from scanner
- [x] All status badges reflect real backend state
- [x] All URLs come from backend checks (not env vars)