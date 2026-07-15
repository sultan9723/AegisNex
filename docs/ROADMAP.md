# Roadmap

## Completed

### Core Platform
- [x] YAML + environment variable configuration system
- [x] System resource monitoring (CPU, memory, disk, network via psutil)
- [x] Docker container health tracking
- [x] HTTP/SSL/TCP/DNS endpoint monitoring
- [x] Monitoring engine with configurable intervals
- [x] Health check framework (Docker, HTTP, TCP)
- [x] Prometheus metrics exporter
- [x] 4 pre-built Grafana dashboards (infrastructure, containers, incidents, remediation)
- [x] OpenTelemetry instrumentation
- [x] CLI entrypoint with 7 actions

### Incident Management
- [x] Full incident lifecycle (open, acknowledge, resolve, reopen, close)
- [x] Incident transitions with audit trail
- [x] Guardian autonomous container restart
- [x] Restart persistence with cooldown and max attempts
- [x] Notification dispatcher (Email/SMTP, Slack, Discord)
- [x] PagerDuty, Microsoft Teams, generic Webhook support
- [x] Audit logging for all mutations

### AI Intelligence Engine
- [x] LangGraph StateGraph with 12 nodes
- [x] Multi-LLM provider factory (OpenAI, Anthropic, Ollama, Azure, Gemini)
- [x] Tool registry with governance (risk level, access mode, permission level)
- [x] RiskEngine (0-1 scoring with configurable auto-execute threshold)
- [x] PolicyEngine (6 default policies)
- [x] RAG pipeline (5 collectors: incidents, audit, monitoring, reports, runbooks)
- [x] SQLite memory store (6 tables)
- [x] Runbook engine (YAML/JSON parser, parallel steps, conditions, retries, approvals)
- [x] 5 built-in AI skills
- [x] Approval gates for destructive actions
- [x] Execution logging and history

### Multi-Agent System
- [x] Agent orchestrator
- [x] 4 domain supervisors (Operations, Security, Compliance, Infrastructure)
- [x] Shared agent state with collaboration messaging
- [x] Fan-out dispatch

### Dashboard & UI
- [x] Next.js 14 frontend with 13 route pages
- [x] Radix UI components + Recharts
- [x] Tailwind CSS dark theme (glass panels, grid, noise, glow)
- [x] Real-time WebSocket streams (5 endpoints)
- [x] Jinja2 template fallback UI
- [x] Full API client (931 lines, auto-reconnect WebSocket)

### Enterprise
- [x] Multi-tenancy (Organizations → Teams → Projects)
- [x] Application-layer data isolation
- [x] 5 compliance frameworks (ISO 27001, SOC 2, NIST, CIS, OWASP)
- [x] Integration marketplace (11 providers)
- [x] Enterprise search (12 domains)
- [x] Plugin system (6 types)
- [x] Knowledge management (upload, index, semantic search)
- [x] Workflow designer (storage and execution)
- [x] API key authentication

### Security
- [x] JWT authentication (access + refresh tokens)
- [x] Role-based access control (viewer, operator, admin)
- [x] Rate limiting (slowapi, per-route limits)
- [x] TLS redirect in production
- [x] Security scanner pipeline (Dockerized Nmap + Nuclei)
- [x] Unified threat matrix ingestion
- [x] GitHub Actions CI/CD pipeline

### Testing
- [x] 35+ test files covering all modules
- [x] pytest with pytest-asyncio
- [x] Coverage reporting
- [x] Sprint 8 verification (Memory, RAG, Tool Governance, Confidence, Approvals, APIs)
- [x] Sprint 9 verification (Risk, Policy, Scheduler, Runbooks)
- [x] V3.0 Enterprise verification (16 parts)

## In Progress

- [ ] Advanced RBAC with custom roles and permissions
- [ ] Helm chart for Kubernetes deployment
- [ ] AI learning refinement engine (self-improving from feedback)
- [ ] Better test coverage for enterprise modules

## Planned

- [ ] Custom plugin SDK with documentation and examples
- [ ] Terraform provider for infrastructure-as-code deployment
- [ ] ML-based anomaly detection for metrics
- [ ] SIEM integration (Splunk, Elastic)
- [ ] Real-time alert aggregation and deduplication
- [ ] Webhook-based event-driven triggers
- [ ] Performance benchmarks and optimization
