# AegisNex V3.0 Enterprise Architecture

## System Overview

AegisNex is an open-source, self-hosted infrastructure monitoring and intelligent operations platform. It combines real-time monitoring, AI-driven incident analysis, multi-agent collaboration, compliance auditing, and automated remediation into a single cohesive system. V3.0 introduces an enterprise-grade AI Intelligence Engine, multi-tenant support, plugin architecture, and four compliance frameworks.

---

## Architecture Principles

1. **Modular Layering** — Each layer has a single responsibility and communicates through well-defined interfaces.
2. **Agentic AI** — The LangGraph-based workflow engine autonomously plans, executes, verifies, and learns from operational tasks.
3. **Safety by Design** — Every destructive action passes through risk assessment, policy checks, and optional human approval gates.
4. **Multi-Tenant** — Organizations, teams, and projects are first-class citizens with data isolation.
5. **Plugin-Driven** — Integrations, tools, skills, and compliance frameworks are all pluggable via a registry.
6. **Observability** — Every API call, workflow execution, agent action, and tool failure is captured in telemetry.

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js / React)                   │
│  Dashboard · Containers · Incidents · AI Chat · Runbooks · Reports │
│  Admin · Compliance · Multi-Agent · Settings · WebSocket Streams   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ HTTP/WS
┌───────────────────────────▼─────────────────────────────────────────┐
│                    BACKEND (FastAPI Application)                     │
│                                                                     │
│  Middleware Stack:                                                   │
│  ┌─────────┐ ┌──────┐ ┌──────────┐ ┌───────────┐ ┌──────┐         │
│  │  Auth   │ │ TLS  │ │ Rate Lim │ │ Telemetry │ │ CORS │         │
│  │  JWT/PK │ │ Redir│ │  slowapi │ │ OpenTele  │ │      │         │
│  └─────────┘ └──────┘ └──────────┘ └───────────┘ └──────┘         │
│                                                                     │
│  Routes: API (200+) · Templates (Jinja2) · Static · WebSocket (5)  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                    INTELLIGENCE LAYER (LangGraph)                    │
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐             │
│  │ Planner  │───▶│ Tool Router   │───▶│ Tool Executor │             │
│  └─────┬────┘    └──────────────┘    └───────┬───────┘             │
│        │         ┌──────────────┐          ┌▼──────────────┐      │
│        ├────────▶│Runbook Exec. │──▶ Scheduler│ Reflection   │      │
│        │         └──────────────┘          └──────┬─────────┘      │
│        │         ┌────────────────┐               │                │
│        └────────▶│Parallel Superv.│──▶ Scheduler   ▼                │
│                  └────────────────┘            Verifier            │
│                                    ┌──────────────┬───────┐         │
│                                    │ Policy Checker│       │        │
│                                    └──────────────┬───────┘        │
│                                    ┌──────────────▼───────┐         │
│                                    │  Risk Assessor       │         │
│                                    └──────────────┬───────┘         │
│                                    ┌──────────────▼───────┐         │
│                                    │  Goal Evaluator      │         │
│                                    └──────────────┬───────┘         │
│                                                   │                 │
│                              goal_completed = False│                 │
│                              retries < 3           ▼                 │
│                                               Planner (loop)         │
│                                                   │                 │
│                                               Finish ─────────▶ END  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                       PLUGIN LAYER                                  │
│                                                                     │
│  ┌────────────┐  ┌───────────────┐  ┌────────────┐  ┌──────────┐  │
│  │ PluginReg. │  │ Integration   │  │ ToolPlugin │  │ Skill    │  │
│  │ (Registry) │  │ Plugin        │  │            │  │ Plugin   │  │
│  └────────────┘  └───────────────┘  └────────────┘  └──────────┘  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                     INTEGRATION LAYER (11 Providers)                 │
│                                                                     │
│  GitHub · GitLab · Jira · ServiceNow · Slack · Teams               │
│  PagerDuty · Discord · Kubernetes · Prometheus · Grafana           │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                     COMPLIANCE LAYER                                │
│                                                                     │
│  ┌───────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌─────────┐   │
│  │ ISO 27001 │  │ SOC 2  │  │  NIST  │  │  CIS   │  │  OWASP  │   │
│  └───────────┘  └────────┘  └────────┘  └────────┘  └─────────┘   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                     MULTI-AGENT LAYER                               │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                Agent Orchestrator                       │       │
│  │  ┌────────────┐ ┌──────────────┐ ┌──────────────┐ ┐     │       │
│  │  │Operations  │ │   Security   │ │  Compliance  │  │     │       │
│  │  │Supervisor  │ │  Supervisor  │ │  Supervisor  │  │     │       │
│  │  └────────────┘ └──────────────┘ └──────────────┘  │     │       │
│  │  ┌──────────────────┐                               │     │       │
│  │  │ Infrastructure   │                               │     │       │
│  │  │   Supervisor     │                               │     │       │
│  │  └──────────────────┘                               │     │       │
│  └─────────────────────────────────────────────────────────┘       │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                       DATA LAYER                                    │
│                                                                     │
│  ┌──────────┐  ┌─────┐  ┌──────────────┐  ┌──────────────┐        │
│  │  SQLite  │  │ RAG │  │ Knowledge    │  │ Memory Store │        │
│  │ /Postgres│  │     │  │ Base (9 tbl) │  │ (6 tables)   │        │
│  └──────────┘  └─────┘  └──────────────┘  └──────────────┘        │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐             │
│  │ Telemetry DB │  │ Scheduler DB  │  │ Search Index │             │
│  │ (5 tables)   │  │ (2 tables)    │  │ (12 domains) │             │
│  └──────────────┘  └───────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
User Request ──▶ HTTP / WebSocket ──▶ Auth Middleware ──▶ Route Handler
                                                              │
                    ┌─────────────────────────────────────────┘
                    ▼
           Intelligence Engine (LangGraph)
                    │
    ┌───────────────┼───────────────────────┐
    ▼               ▼                       ▼
 Planner      Skill Executor        Runbook Executor
    │               │                       │
    └───────┬───────┘                       │
            ▼                               │
     Tool Router ──▶ Tool Executor ──▶ Reflection ──▶ Verifier
            │                               │
            │                               ▼
            │                         Policy Checker ──▶ Risk Assessor
            │                                               │
            └───────────────────────────────▶ Goal Evaluator │
                                                    │        │
                         goal_completed == False    │        │
                         retries < 3                ▼        │
                                                 Planner (loop)
                                                    │
                                                 Finish ─────▶ Response (JSON)
```

---

## Plugin Architecture

The `PluginRegistry` (`src/plugins/registry.py`) is the central plugin manager.

| Plugin Type      | Base Class         | Purpose                              |
|------------------|--------------------|--------------------------------------|
| `TOOL`           | `ToolPlugin`       | Registers tools into the AI registry |
| `INTEGRATION`    | `IntegrationPlugin`| External service connectors          |
| `SKILL`          | `SkillPlugin`      | AI analysis capabilities             |
| `WORKFLOW`       | —                  | Custom workflow definitions          |
| `NOTIFICATION`   | —                  | Notification channel providers       |
| `COMPLIANCE`     | —                  | Compliance framework controls        |

Plugins declare a `PluginManifest` with id, name, version, type, dependencies, and config schema.

---

## Multi-Tenant Design

| Entity         | Table               | Hierarchy           |
|----------------|---------------------|---------------------|
| Organization   | `organizations`     | Top-level tenant    |
| Team           | `teams`             | Belongs to org      |
| Project        | `projects`          | Belongs to team     |
| TenantUser     | `tenant_users`      | User + org role     |
| TenantUserTeam | `tenant_user_teams` | User + org + team   |

Data isolation is enforced at the application layer. The `TenantManager` (`src/multitenant/manager.py`) manages all tenant CRUD.

---

## Security Model

| Layer           | Mechanism                                    |
|-----------------|----------------------------------------------|
| Authentication  | JWT (access + refresh tokens), API keys      |
| Authorization   | Role-based: `viewer`, `operator`, `admin`    |
| API Key Auth    | `X-API-Key` header with hashed key lookup    |
| Rate Limiting   | `slowapi` with per-route limits              |
| TLS Redirect    | Automatic HTTP→HTTPS in production           |
| Session         | HttpOnly, Secure, SameSite cookies           |
| Approval Gate   | Risk-based: destructive actions block at AI  |
| Audit Logging   | All mutations recorded in `audit_logs`       |
| Telemetry       | OpenTelemetry instrumentation                |

---

## Deployment Options

| Mode            | Method                                    |
|-----------------|-------------------------------------------|
| Development     | `python src/dashboard.py` (FastAPI dev)   |
| Production      | `gunicorn` + `uvicorn` workers            |
| Docker          | `Dockerfile` with multi-stage build       |
| Docker Compose  | `docker-compose up` with Grafana/Prom     |
| Kubernetes      | Manual deployment (helm chart planned)    |

Supports PostgreSQL for production (via `AEGISNEX_DATABASE_URL`) and SQLite for development/testing.
