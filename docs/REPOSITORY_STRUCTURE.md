# Repository Structure

```
aegisnex/
├── src/                          # Python backend (40+ modules)
│   ├── dashboard.py              # FastAPI app (3558 lines, 200+ routes, 5 WebSockets)
│   ├── config.py                 # YAML/env configuration loader
│   ├── auth.py                   # JWT authentication (access + refresh tokens, API keys)
│   ├── agent.py                  # Command registry and dispatcher
│   ├── autonomous.py             # Autonomous agent mode
│   ├── monitor.py                # System resource monitor (CPU, memory, disk, network via psutil)
│   ├── monitoring_engine.py      # Continuous monitoring engine
│   ├── container_health_monitor.py # Docker container health tracking
│   ├── guardian.py               # Autonomous restart management with cooldown/max-attempt protection
│   ├── incidents.py              # Incident lifecycle management
│   ├── notifier.py               # Notification dispatcher
│   ├── healing.py                # Self-healing logic
│   ├── health_checks.py          # Health check framework (Docker, HTTP, SSL, TCP)
│   ├── http_monitor.py           # HTTP endpoint monitoring
│   ├── ssl_monitor.py            # SSL certificate monitoring
│   ├── tcp_monitor.py            # TCP port monitoring
│   ├── dns_monitor.py            # DNS resolution monitoring
│   ├── docker_scanner.py         # Docker container scanning
│   ├── scanner.py                # Security scanner
│   ├── reporting.py              # Operational reporting (weekly/monthly)
│   ├── cache.py                  # Dashboard caching
│   ├── event_bus.py              # Event bus
│   ├── failsafe.py               # Fail-safe decorators
│   ├── logging_config.py         # Logging configuration
│   ├── mcp_server.py             # MCP (Model Context Protocol) server
│   ├── observability.py          # Observability utilities
│   ├── opentelemetry.py          # OpenTelemetry instrumentation
│   ├── orchestrator.py           # System health orchestrator
│   ├── platform_db.py            # Platform database access (PlatformRepository)
│   ├── policy_engine.py          # Policy engine
│   ├── prometheus_exporter.py    # Prometheus metrics exporter
│   ├── secrets.py                # Secret management
│   ├── storage.py                # Data storage/repository
│   ├── watchdog.py               # Watchdog timer
│   ├── websocket_manager.py      # WebSocket manager
│   ├── explanations.py           # AI explanations
│   ├── execution_history.py      # Execution history
│   ├── backup.py                 # Database backup utilities
│   │
│   ├── intelligence/             # AI Intelligence Engine
│   │   ├── graph.py              # LangGraph StateGraph construction
│   │   ├── nodes.py              # 12 workflow nodes
│   │   ├── state.py              # AgentState TypedDict (30+ fields)
│   │   ├── tools.py              # Tool registry (518 lines)
│   │   ├── tool_router.py        # Tool router
│   │   ├── risk.py               # Risk engine (0-1 scoring)
│   │   ├── policy.py             # Policy engine (6 default policies)
│   │   ├── scheduler.py          # Task scheduler
│   │   ├── history.py            # Execution history
│   │   ├── execution_logger.py   # Execution logging
│   │   ├── providers/            # LLM provider factory (5 providers)
│   │   │   ├── factory.py        # Provider factory
│   │   │   ├── base.py           # Base provider class
│   │   │   ├── openai_provider.py
│   │   │   ├── ollama_provider.py
│   │   │   ├── gemini_provider.py
│   │   │   ├── anthropic_provider.py
│   │   │   └── azure_provider.py
│   │   ├── memory/               # SQLite memory store
│   │   │   ├── base.py           # Memory base
│   │   │   ├── sqlite_memory.py  # 6 tables
│   │   │   └── types.py          # Memory types
│   │   ├── retrieval/            # RAG engine
│   │   │   ├── base.py           # RAG base
│   │   │   ├── collector.py      # 5 collectors
│   │   │   └── rag.py            # RAG engine
│   │   └── runbooks/             # Runbook engine
│   │       ├── parser.py         # YAML/JSON parser
│   │       ├── registry.py       # Runbook registry
│   │       └── engine.py         # Execution engine
│   │
│   ├── agents/                   # Multi-agent system
│   │   ├── orchestrator.py       # Agent orchestrator
│   │   ├── supervisors.py        # 4 domain supervisors
│   │   ├── state.py              # Shared agent state
│   │   ├── registry.py           # Agent registry
│   │   ├── base.py               # Base agent class
│   │   └── domain_agents.py      # Domain-specific agents
│   │
│   ├── integrations/             # Integration marketplace
│   │   ├── base.py               # Integration base
│   │   ├── marketplace/          # Marketplace logic
│   │   └── providers/            # 11 integration providers
│   │       ├── github.py
│   │       ├── gitlab.py
│   │       ├── jira.py
│   │       ├── servicenow.py
│   │       ├── slack.py
│   │       ├── teams.py
│   │       ├── pagerduty.py
│   │       ├── discord_bot.py
│   │       ├── kubernetes.py
│   │       ├── prometheus_provider.py
│   │       └── grafana.py
│   │
│   ├── compliance/               # Compliance framework
│   │   ├── frameworks.py         # 5 framework definitions
│   │   ├── engine.py             # Assessment engine
│   │   └── evidence.py           # Evidence collection
│   │
│   ├── knowledge/                # Knowledge base
│   │   ├── loader.py             # Document loader
│   │   ├── indexer.py            # Document indexer
│   │   └── retriever.py          # Semantic retriever
│   │
│   ├── search/                   # Enterprise search
│   │   ├── engine.py             # Cross-domain search engine (12 domains)
│   │   └── indexer.py            # Search indexer
│   │
│   ├── skills/                   # AI skills
│   │   ├── registry.py           # Skill registry
│   │   ├── builtin.py            # 5 built-in skills
│   │   └── engine.py             # Skill execution engine
│   │
│   ├── telemetry/                # Telemetry collection
│   │   ├── collector.py          # Telemetry collector
│   │   └── middleware.py         # Request middleware
│   │
│   ├── multitenant/              # Multi-tenancy
│   │   ├── models.py             # Tenant models
│   │   ├── manager.py            # Tenant manager
│   │   └── isolation.py          # Data isolation
│   │
│   ├── plugins/                  # Plugin framework
│   │   ├── base.py               # Plugin base class
│   │   └── registry.py           # Plugin registry
│   │
│   ├── notifications/            # Notification providers
│   │   ├── base.py               # Base provider
│   │   ├── factory.py            # Channel factory
│   │   ├── email.py              # SMTP email
│   │   ├── slack.py              # Slack webhook
│   │   └── discord.py            # Discord webhook
│   │
│   └── workflow_designer/        # Visual workflow designer
│       ├── models.py             # Workflow models
│       ├── storage.py            # Workflow storage
│       ├── engine.py             # Workflow engine
│       └── examples.py           # Example workflows
│
├── frontend/                     # Next.js 14 dashboard
│   ├── app/                      # 13 app router routes
│   │   ├── page.tsx              # Dashboard (home)
│   │   ├── layout.tsx            # Root layout with AuthProvider, AppShell, Toaster
│   │   ├── globals.css           # Dark theme, utilities, animations
│   │   ├── ai/page.tsx           # AI operations
│   │   ├── audit/page.tsx        # Audit log viewer
│   │   ├── containers/page.tsx   # Container management
│   │   ├── incidents/page.tsx    # Incident management
│   │   ├── infrastructure/page.tsx # Infrastructure monitoring
│   │   ├── integrations/page.tsx # Integration marketplace
│   │   ├── login/page.tsx        # Login page
│   │   ├── mcp/page.tsx          # MCP tools
│   │   ├── notifications/page.tsx # Notifications
│   │   ├── reports/page.tsx      # Reports
│   │   ├── search/page.tsx       # Enterprise search
│   │   ├── settings/page.tsx     # Settings
│   │   └── targets/page.tsx      # Monitoring targets
│   ├── components/               # Shared components
│   │   ├── common/               # EmptyState, ErrorBoundary, LoadingState, etc.
│   │   ├── dashboard/            # DashboardPage, HealthScoreCard, MetricCard, TrendChart
│   │   ├── layout/               # AppShell, Sidebar, Header, CommandPalette, ActionDrawer
│   │   ├── pages/                # RouteScaffold
│   │   └── ui/                   # badge, button, card, dialog, sheet, table, input
│   └── lib/                      # Client libraries
│       ├── api.ts                # API client (931 lines, all REST endpoints)
│       ├── auth.tsx              # AuthProvider, useAuth hook, JWT handling
│       ├── format.ts             # Formatting utilities
│       ├── live-data.ts          # Live data hooks
│       ├── undo.ts               # Undo support
│       ├── useAction.ts          # Action hook
│       ├── utils.ts              # cn() utility
│       ├── workflow.ts           # Workflow utilities
│       └── ws.ts                 # WebSocket hook (auto-reconnect, exponential backoff)
│
├── modules/                      # Dockerized security scan modules
│   ├── app-audit/                # Nuclei vulnerability scanner
│   │   ├── Dockerfile            # Alpine + Bash + Nuclei
│   │   └── audit_engine.sh       # Scan script
│   └── network-recon/            # Nmap network scanner
│       ├── Dockerfile            # Alpine + Bash + Nmap
│       └── scan_engine.sh        # Scan script
│
├── grafana/                      # Grafana + Prometheus stack
│   ├── docker-compose.yml        # Services: Prometheus + Grafana
│   ├── prometheus/
│   │   └── prometheus.yml        # Scrape config (host.docker.internal:8000/metrics)
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── prometheus.yml    # Auto-provision datasource
│   │   └── dashboards/
│   │       └── aegisnex.yml      # Auto-provision dashboard config
│   └── dashboards/               # 4 JSON dashboard definitions
│       ├── infrastructure.json
│       ├── containers.json
│       ├── incidents.json
│       └── remediation.json
│
├── alembic/                      # Database migrations
│   ├── alembic.ini               # Alembic configuration
│   └── versions/
│       └── 369f8483bf6d_initial_schema.py  # Initial schema (10+ tables)
│
├── deploy/                       # Production deployment
│   └── docker-compose.yml        # network_recon + app_audit services
│
├── orchestrator/                 # Telemetry orchestration
│   └── ingest_telemetry.py       # Unified threat matrix consolidation
│
├── tests/                        # Python test suite (35+ files)
│   ├── test_agent.py
│   ├── test_auth.py
│   ├── test_autonomous.py
│   ├── test_config.py
│   ├── test_dashboard.py
│   ├── test_docker_scanner.py
│   ├── test_enterprise.py
│   ├── test_entrypoint.py
│   ├── test_event_bus.py
│   ├── test_execution_history.py
│   ├── test_execution_logging.py
│   ├── test_explanations.py
│   ├── test_grafana_assets.py
│   ├── test_guardian.py
│   ├── test_healing.py
│   ├── test_health_checks.py
│   ├── test_http_monitor.py
│   ├── test_incidents.py
│   ├── test_intelligence.py      # AI engine smoke tests
│   ├── test_mcp_server.py
│   ├── test_monitor.py
│   ├── test_monitoring_engine.py
│   ├── test_multi_agent_collaboration.py
│   ├── test_notifications.py
│   ├── test_notifier.py
│   ├── test_orchestrator.py
│   ├── test_phase_c3_integration.py
│   ├── test_platform_db.py
│   ├── test_policy_engine.py
│   ├── test_prometheus_exporter.py
│   ├── test_reporting.py
│   ├── test_scanner.py
│   ├── test_ssl_monitor.py
│   ├── test_storage.py
│   ├── test_tcp_monitor.py
│   ├── test_tool_router.py
│   ├── test_watchdog.py
│   ├── verify_sprint8.py         # Sprint 8 feature verification
│   ├── verify_sprint9.py         # Sprint 9 feature verification
│   └── verify_v3.py              # V3.0 Enterprise verification (16 parts)
│
├── docs/                         # Documentation (15+ files)
│   ├── ARCHITECTURE.md           # System architecture, data flow, security model
│   ├── AI_ARCHITECTURE.md        # AI engine architecture (LangGraph workflow)
│   ├── API_REFERENCE.md          # Complete API reference (200+ endpoints)
│   ├── DEPLOYMENT_GUIDE.md       # Production deployment, Docker, Kubernetes, scaling
│   ├── DEVELOPER_GUIDE.md        # Development setup, coding conventions, extending
│   ├── ADMIN_GUIDE.md            # User management, multi-tenant admin, troubleshooting
│   ├── DATABASE_SCHEMA.md        # Database tables, indexes, migrations
│   ├── ROADMAP.md                # Completed, in-progress, and planned features
│   ├── AGENT_REFERENCE.md        # Multi-agent system reference
│   ├── TOOL_REFERENCE.md         # AI tool registry reference
│   ├── WORKFLOW_REFERENCE.md     # Workflow designer reference
│   ├── AEGISNEX_TECHNICAL_SPECIFICATION.md  # Full technical spec
│   ├── REPOSITORY_STRUCTURE.md   # This file
│   ├── PHASE_C1_TOOL_ROUTER.md   # Phase C1 completion report
│   ├── PHASE_C2_COMPLETE.md      # Phase C2 completion report
│   ├── PHASE_C2_EXECUTION_LOGGING.md  # Execution logging design
│   ├── SPRINT_D_MULTI_AGENT.md   # Multi-agent design document
│   └── grafana/README.md         # Grafana setup instructions
│
├── scripts/                      # Utility scripts
│   └── check_imports.py          # Import verification
│
├── templates/                    # Jinja2 HTML templates (12)
├── static/                       # Static CSS (725 lines, dark theme)
├── data/                         # Runtime data (threat matrix, etc.)
├── logs/                         # Application logs
├── reports/                      # Generated operational reports
│
├── assets/                       # Media assets
│   ├── screenshots/              # Screenshots (placeholders)
│   ├── diagrams/                 # draw.io architecture diagrams
│   └── figma/                    # Figma design specifications
│
├── config.yaml                   # YAML configuration
├── .env.example                  # Environment template
├── .gitignore
├── .github/workflows/pipeline.yml # CI/CD (pytest on PR/push)
├── docker-compose.demo.yml       # Demo environment
├── requirements.txt              # Python dependencies (pinned)
├── local-requirements.txt        # Dev extras (Glances, pyinstrument, etc.)
├── skills-lock.json              # Agent skills lockfile
├── entrypoint.py                 # CLI entrypoint (291 lines, 7 actions)
├── run_pipeline.sh               # CI/CD pipeline script
├── CONTRIBUTING.md               # Contribution guidelines
├── SECURITY.md                   # Security policy
├── CHANGELOG.md                  # Release history
└── README.md                     # Project overview (this file)
```
