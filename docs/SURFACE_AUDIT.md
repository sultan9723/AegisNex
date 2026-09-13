# AegisNex surface audit

Scope: active `src/` top-level modules and packages in this checkout. Evidence was gathered from Python import parsing across `tests/`, `entrypoint.py`, `src/`, and targeted `rg` checks against `frontend/`, `src/dashboard.py`, and `verify_v3.py`. Status values are:

- KEEP: load-bearing for the remediation, policy, incident, auth, monitoring, notification, or currently routed API/UI paths.
- DEFER: real surface with a caller or product route, but outside the core remediation/policy claim or under-tested relative to its scope.
- CUT: speculative or orphaned at the top level; no active entrypoint/frontend caller found in this audit.

| Module | Tested | Reachable from entrypoint.py or frontend | Status | Evidence / rationale |
| --- | --- | --- | --- | --- |
| `__init__.py` | No | No | KEEP | Package marker; no runtime behavior. |
| `agent.py` | Yes | Yes, via `entrypoint.py` and `watchdog.py` | KEEP | CLI/legacy agent commands still depend on it. |
| `agents/` | Yes | Yes, via dashboard multi-agent routes | DEFER | Real dashboard surface, but broader than the core remediation loop. |
| `ai_governance.py` | Yes | Yes, via dashboard governance routes | DEFER | Policy/governance surface is real and tested, but separate from Guardian safety gate. |
| `ai_workforce.py` | Yes | Yes, via dashboard workforce routes | DEFER | Product-facing AI workforce surface with tests; keep scoped until core trust metrics mature further. |
| `api_keys.py` | Indirect/partial | Yes, API key routes exist in dashboard/frontend | DEFER | Authentication support exists, but this module is not directly imported by dashboard routes in the current tree. |
| `auth.py` | Yes | Yes, via dashboard, routers, and platform services | KEEP | Core access control dependency. |
| `autonomous.py` | Yes | Yes, via dashboard autonomous pipeline route wiring | KEEP | Connects policy, execution history, explanations, and healing. |
| `backup.py` | Yes | Yes, via dashboard backup routes | DEFER | Operationally useful enterprise surface, not part of the remediation proof. |
| `cache.py` | No | Yes, via dashboard | DEFER | Runtime optimization with a dashboard caller but no direct tests. |
| `commandmesh_routing.py` | Yes | Yes, via dashboard CommandMesh proxy | DEFER | Tested and routed, but outside remediation/policy loop. |
| `compliance/` | No direct package tests | Yes, via dashboard compliance routes | DEFER | Real dashboard surface, under-tested as a package and outside the core loop. |
| `config.py` | Yes | Yes, via `entrypoint.py`, `watchdog.py`, dashboard, notification factory | KEEP | Shared configuration for core services. |
| `container_health_monitor.py` | No | No active caller found | CUT | Orphaned health-monitor variant; `monitoring_engine.py`, `guardian.py`, and dedicated monitors cover active paths. |
| `dashboard.py` | Yes | Yes, frontend/backend API entrypoint | KEEP | Main API/UI composition root. |
| `dns_monitor.py` | No direct tests | Yes, via `monitoring_engine.py` | DEFER | Used by monitoring engine, but lacks direct tests. |
| `docker_scanner.py` | Yes | Yes, via `entrypoint.py`, dashboard, watchdog, MCP, search | KEEP | Core remediation target scanner/executor. |
| `enterprise_auth.py` | Yes | Yes, via dashboard and auth router | KEEP | Production auth and SSO guardrails. |
| `event_bus.py` | Yes | Yes, via autonomous/healing runtime | KEEP | Core action/event plumbing. |
| `execution_history.py` | Yes | Yes, via autonomous pipeline and dashboard | KEEP | Audit trail for autonomous actions. |
| `explanations.py` | Yes | Yes, via autonomous/healing runtime | KEEP | Explains remediation decisions and actions. |
| `failsafe.py` | No direct tests | Yes, used by autonomous, healing, monitoring, notifier | KEEP | Guardrail wrapper used on active remediation/notification paths. |
| `governance_seed.py` | Yes | No direct entrypoint/frontend import | DEFER | Tested seed utility for demo/governance data, but not load-bearing at runtime. |
| `guardian.py` | Yes | Yes, via `entrypoint.py`, dashboard, watchdog | KEEP | Core remediation loop. |
| `healing.py` | Yes | Yes, via autonomous pipeline and dashboard | KEEP | Core self-healing action executor. |
| `health_checks.py` | Yes | Yes, via `entrypoint.py`, Guardian, watchdog | KEEP | Core health evaluation input. |
| `http_monitor.py` | Yes | Yes, via dashboard, MCP, monitoring engine | KEEP | Active monitor with tests and incident integration. |
| `incidents.py` | Yes | Yes, via `entrypoint.py`, dashboard, Guardian, monitors, MCP | KEEP | Core incident lifecycle. |
| `integrations/` | No direct package tests | Yes, via dashboard integrations/search | DEFER | Product surface is routed, but broad and under-tested. |
| `intelligence/` | Yes | Yes, via dashboard AI routes and dependent agents/search/workforce | KEEP | Contains policy/risk, tool execution, graph, runbooks, memory; central to AI governance claim. |
| `knowledge/` | No direct tests | Yes, via dashboard knowledge/RAG routes | DEFER | Real RAG surface, but no direct top-level tests and outside remediation proof. |
| `logging_config.py` | No direct tests | Yes, via dashboard and routers | KEEP | Shared runtime logging setup. |
| `mcp_server.py` | Yes | Yes, dashboard exposes MCP config/server creation | DEFER | Confirmed active tests and dashboard caller; not a cut candidate despite broad surface. |
| `middleware/` | Yes | No direct entrypoint/frontend import found | KEEP | Organization isolation middleware is exercised by enterprise IAM tests. |
| `mission_control.py` | Yes | Yes, via dashboard mission-control routes | DEFER | Real routed execution tracking surface; adjacent to workforce governance. |
| `monitor.py` | Yes | Yes, via `entrypoint.py`, dashboard, watchdog, MCP | KEEP | Core system health input. |
| `monitoring_engine.py` | Yes | Yes, via dashboard | KEEP | Coordinates HTTP/SSL/TCP/DNS monitoring and incident transitions. |
| `multitenant/` | No direct package tests | Yes, via dashboard, org isolation, mission control | DEFER | Important enterprise boundary, but under-tested as a package. |
| `notifications/` | Yes | Yes, via `entrypoint.py`, dashboard, incidents, watchdog | KEEP | Current notification provider stack. |
| `notifications_compat.py` | No | No active caller found | CUT | Compatibility shim has no active import in the current tree. |
| `notifier.py` | Yes | Yes, via `entrypoint.py`, dashboard, Guardian, watchdog | KEEP | Legacy/simple notifier still used by Guardian. |
| `observability.py` | No | Yes, via dashboard | DEFER | Dashboard caller exists, but no direct tests. |
| `opentelemetry.py` | No | Yes, via dashboard instrumentation hook | DEFER | Optional instrumentation surface with dashboard caller, no tests. |
| `orchestrator.py` | Yes | Yes, via `entrypoint.py`, dashboard, Guardian, MCP, watchdog | KEEP | Core health aggregation for remediation loop. |
| `platform_db.py` | Yes | Yes, via dashboard, MCP, monitoring, AI history/search | KEEP | Main persistence layer for enterprise/API/runtime data. |
| `plugins/` | No direct tests | No entrypoint/frontend caller; only used by `skills/` and `verify_v3.py` | CUT | Requested flag confirmed: no dashboard/entrypoint caller, and no direct tests. Keep only if skills remain a committed product surface. |
| `policy_engine.py` | Yes | Yes, via dashboard, autonomous, Guardian, healing | KEEP | Core trust gate. |
| `prometheus_exporter.py` | Yes | Yes, via dashboard and intelligence tools | DEFER | Useful ops surface, not central to remediation gating. |
| `rbac.py` | Yes | Yes, via dashboard and auth router | KEEP | Authorization enforcement. |
| `reporting.py` | Yes | Yes, via `entrypoint.py`, dashboard, MCP, intelligence tools | KEEP | Operational audit/reporting path. |
| `routers/` | No direct package tests | Not directly; individual routers are mounted through dashboard imports | DEFER | Routing split exists but is thin and under-tested as a package. |
| `scanner.py` | Yes | Yes, via `entrypoint.py` | KEEP | CLI security scan path. |
| `search/` | No direct package tests | Yes, via dashboard search routes | DEFER | Product route exists, but package lacks direct tests. |
| `secrets.py` | Yes | Yes, via dashboard secret routes | KEEP | Enterprise secret storage and encryption. |
| `session.py` | Yes | Yes, via auth runtime | KEEP | Session management for auth. |
| `skills/` | No direct package tests | Yes, via dashboard skills API and intelligence graph node | DEFER | Requested flag confirmed: has dashboard and AI graph callers, but no direct tests and depends on `plugins/`. Audit before expanding. |
| `ssl_monitor.py` | Yes | Yes, via dashboard, MCP, monitoring engine | KEEP | Active monitor with tests and incident integration. |
| `storage.py` | Yes | Yes, via `entrypoint.py` | KEEP | Core SQLite repository used by operations/tests. |
| `tcp_monitor.py` | Yes | Yes, via dashboard, MCP, monitoring engine | KEEP | Active monitor with tests and incident integration. |
| `telemetry/` | No direct package tests | Yes, via dashboard telemetry routes/middleware | DEFER | Product route exists, but package lacks direct tests. |
| `watchdog.py` | Yes | Runtime executable helper; no frontend caller | KEEP | Guardian service runner. |
| `websocket_manager.py` | No | Yes, via dashboard | DEFER | Dashboard live-update surface without direct tests. |
| `workflow_designer/` | No | No active entrypoint/frontend caller; only `verify_v3.py` and docs reference it | CUT | Requested flag confirmed: speculative relative to the core claim, no tests, no active product caller. |

## Focus areas requested

- `workflow_designer/`: recommend CUT. It has internal package imports and `verify_v3.py` coverage only; no test, dashboard import, entrypoint import, or frontend API path was found.
- `plugins/`: recommend CUT unless `skills/` is retained as a near-term product commitment. The package has no direct tests and no entrypoint/frontend caller; it exists mainly to support the skills implementation.
- `skills/`: recommend DEFER. It is reachable from dashboard `/api/skills` and the AI graph `skill_executor`, but has no direct tests and depends on the plugin surface.
- `mcp_server.py`: recommend DEFER, not CUT. It has a dedicated test module and a dashboard caller that creates server/config output.
