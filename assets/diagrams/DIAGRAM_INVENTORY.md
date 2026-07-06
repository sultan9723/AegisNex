# Diagram Inventory

This document lists every diagram that should exist for the AegisNex project documentation. Diagrams are organized by audience and purpose.

---

## 1. System Architecture Overview

| Field | Value |
|---|---|
| **Filename** | `system-architecture-overview` |
| **Purpose** | High-level block diagram showing all layers: Frontend → Backend → Intelligence → Integrations → Compliance → Data Layer. Used in README and ARCHITECTURE.md. |
| **Sections Connected** | Frontend (Next.js), Backend (FastAPI), Intelligence (LangGraph), Integrations (11 providers), Compliance (5 frameworks), Data Layer (SQLite/PostgreSQL, RAG, Memory) |
| **Recommended Tool** | draw.io (can embed as SVG, easy to update with codebase changes) |

---

## 2. AI Workflow (LangGraph StateGraph)

| Field | Value |
|---|---|
| **Filename** | `ai-workflow-langgraph` |
| **Purpose** | Detailed node-and-edge diagram of the 12-node LangGraph StateGraph showing conditional routing, approval gates, and retry loops. Used in AI_ARCHITECTURE.md. |
| **Sections Connected** | Planner → Skill Executor → Tool Executor → Verifier → Self-Corrector → Goal Evaluator, plus Risk Assessor, Policy Checker, Runbook Executor, Parallel Supervisor, Scheduler, Learning |
| **Recommended Tool** | draw.io (precise control over conditional edge labels) |

---

## 3. RAG Pipeline

| Field | Value |
|---|---|
| **Filename** | `rag-pipeline` |
| **Purpose** | Flow diagram showing query → KnowledgeCollector (5 sources) → RetrievalResult → Context Injection → LLM → Answer. Used in AI_ARCHITECTURE.md. |
| **Sections Connected** | Query, KnowledgeCollector (incidents, audit logs, monitoring history, reports, runbooks), RAG Engine, LLM Provider |
| **Recommended Tool** | draw.io or Figma (simple flow, either works) |

---

## 4. Multi-Agent Collaboration

| Field | Value |
|---|---|
| **Filename** | `multi-agent-architecture` |
| **Purpose** | Diagram showing Agent Orchestrator dispatching to 4 domain supervisors (Operations, Security, Compliance, Infrastructure) with shared state and collaboration messaging. |
| **Sections Connected** | Agent Orchestrator, Operations Supervisor, Security Supervisor, Compliance Supervisor, Infrastructure Supervisor, Shared State |
| **Recommended Tool** | Figma (better for complex interconnected layouts) |

---

## 5. Data Flow Sequence

| Field | Value |
|---|---|
| **Filename** | `request-data-flow` |
| **Purpose** | Sequence diagram showing a user request flowing through HTTP/WS → Auth → Route Handler → Intelligence Engine → Tool Execution → Response. |
| **Sections Connected** | User, Browser, FastAPI, Auth Middleware, LangGraph Engine, Tools, Database |
| **Recommended Tool** | draw.io (sequence diagram template) |

---

## 6. Security Scanner Pipeline

| Field | Value |
|---|---|
| **Filename** | `scanner-pipeline` |
| **Purpose** | Flow showing GitHub CI → Docker Build → Network Recon (Nmap) → App Audit (Nuclei) → Telemetry Ingestion → Unified Threat Matrix. |
| **Sections Connected** | GitHub Actions, Docker Registry, network-recon module, app-audit module, orchestrator/ingest_telemetry.py, data/unified_threat_matrix.json |
| **Recommended Tool** | draw.io |

---

## 7. Database Schema (ER Diagram)

| Field | Value |
|---|---|
| **Filename** | `database-er-diagram` |
| **Purpose** | Entity-relationship diagram showing all 10+ platform tables (users, monitoring_targets, check_results, incidents, notifications, remediation_actions, incident_transitions, audit_logs, metrics_snapshots, reports) plus AI memory tables (6) with relationships and indexes. |
| **Sections Connected** | All database tables across platform DB and AI memory DB |
| **Recommended Tool** | draw.io (DB schema templates available) |

---

## 8. Multi-Tenant Hierarchy

| Field | Value |
|---|---|
| **Filename** | `multitenant-hierarchy` |
| **Purpose** | Tree diagram showing Organization → Team → Project hierarchy with associated entities (users, monitoring targets, incidents, workflows) and data isolation boundaries. |
| **Sections Connected** | Organizations, Teams, Projects, Users, Monitoring Targets, Incidents, Workflows |
| **Recommended Tool** | Figma (clean tree layouts) |

---

## 9. Deployment Architecture

| Field | Value |
|---|---|
| **Filename** | `deployment-architecture` |
| **Purpose** | Infrastructure diagram showing production deployment with PostgreSQL, Redis, reverse proxy (Nginx/Caddy), Docker containers, and optional Grafana/Prometheus stack. |
| **Sections Connected** | Nginx/Caddy, FastAPI app (multiple workers), PostgreSQL, Redis, Grafana, Prometheus, Docker daemon |
| **Recommended Tool** | draw.io (cloud architecture shapes) |

---

## 10. Tool Governance Flow

| Field | Value |
|---|---|
| **Filename** | `tool-governance-flow` |
| **Purpose** | Decision flowchart showing how a tool action passes through: Risk Assessment → Policy Check → Approval Gate (if needed) → Execution → Verification → Logging. |
| **Sections Connected** | Tool Executor, RiskEngine, PolicyEngine, Approval Gate, Tool Execution, Verifier, Audit Log |
| **Recommended Tool** | draw.io (flowchart template) |

---

## Summary

| # | Diagram | Tool | Priority |
|---|---------|------|----------|
| 1 | System Architecture Overview | draw.io | P0 — needed for README |
| 2 | AI Workflow (LangGraph) | draw.io | P0 — needed for AI docs |
| 3 | RAG Pipeline | Figma/draw.io | P1 |
| 4 | Multi-Agent Architecture | Figma | P1 |
| 5 | Data Flow Sequence | draw.io | P1 |
| 6 | Scanner Pipeline | draw.io | P2 |
| 7 | Database ER Diagram | draw.io | P2 |
| 8 | Multi-Tenant Hierarchy | Figma | P2 |
| 9 | Deployment Architecture | draw.io | P1 |
| 10 | Tool Governance Flow | draw.io | P2 |

**Priority Guide:**
- **P0**: Essential for the README and core documentation
- **P1**: Important for understanding key subsystems
- **P2**: Nice-to-have, deep-dive reference
