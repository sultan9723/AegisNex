# Changelog

All notable changes to AegisNex are documented here.

## 3.0.0 (2026-06-15)

### Added
- **AI Intelligence Engine**: LangGraph StateGraph with 12 nodes (planner, tool executor, verifier, self-corrector, goal evaluator, risk assessor, policy checker, runbook executor, parallel supervisor, scheduler, learning, skill executor)
- **Multi-LLM Support**: OpenAI, Anthropic, Ollama, Azure OpenAI, Gemini via provider factory
- **Tool Governance**: Per-tool risk scoring, policy engine with 6 default policies, approval gates
- **RAG Pipeline**: Context retrieval from incidents, audit logs, monitoring history, reports, runbooks
- **Memory Store**: 6 AI-specific SQLite tables for conversations, incidents, recommendations, learnings
- **Runbook Engine**: YAML/JSON parser with parallel steps, conditions, retries, approvals
- **5 Built-in AI Skills**: system_analyzer, incident_investigator, container_manager, report_generator, security_auditor
- **Multi-Agent System**: Agent orchestrator with 4 domain supervisors (Operations, Security, Compliance, Infrastructure)
- **Multi-Tenancy**: Organizations → Teams → Projects with application-layer data isolation
- **5 Compliance Frameworks**: ISO 27001 (114 controls), SOC 2 (65), NIST CSF (98), CIS Controls (153), OWASP Top 10
- **Integration Marketplace**: 11 providers (GitHub, GitLab, Jira, ServiceNow, Slack, Teams, PagerDuty, Discord, Kubernetes, Prometheus, Grafana)
- **Enterprise Search**: Cross-domain search across 12 data domains
- **Plugin System**: 6 plugin types (Tool, Integration, Skill, Workflow, Notification, Compliance)
- **Knowledge Management**: Document upload, directory indexing, semantic search
- **Workflow Designer**: Visual workflow builder with storage and execution engine
- **Next.js 14 Dashboard**: 13 route pages with Radix UI, Recharts, Tailwind CSS dark theme
- **5 WebSocket Endpoints**: Real-time dashboard, incidents, containers, targets, container logs
- **Prometheus Exporter**: `/metrics` endpoint with 4 pre-built Grafana dashboards
- **Incident Lifecycle**: Open → Acknowledged → In Progress → Resolved → Closed with full transition audit
- **Notification Channels**: Email (SMTP), Slack, Discord, PagerDuty, Teams, generic Webhook
- **Security Scanner Pipeline**: Dockerized Nmap + Nuclei with telemetry ingestion

### Changed
- Migrated backend to FastAPI with Uvicorn (from earlier Flask prototype)
- Replaced ad-hoc monitoring with `MonitoringEngine` orchestration
- Consolidated configuration into YAML + environment variables

### Fixed
- Container restart loop protection in Guardian (cooldown + max attempts)
- Incident transition state validation
- WebSocket reconnection with exponential backoff

## 2.1.0 (2025-12-01)

### Added
- Guardian auto-restart module
- Prometheus client integration
- Docker health monitoring
- CLI entrypoint with scan/report/monitor actions

### Fixed
- Database connection pooling
- Memory leak in long-running monitors

## 2.0.0 (2025-09-15)

### Added
- FastAPI backend with JWT authentication
- Monitoring engine with HTTP/SSL/TCP/DNS checks
- Incident management system
- Email notification support
- Jinja2 dashboard templates
- SQLite database with Alembic migrations

## 1.0.0 (2025-06-01)

### Added
- Initial release
- Basic system monitoring
- Docker container scanning
- Report generation
- YAML configuration
