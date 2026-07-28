"""Auto-register existing agents into governance + seed demo data.

Called once on backend startup after GovernanceManager is initialized.
Idempotent — skips agents that are already registered.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import UTC, datetime, timedelta

from src.ai_governance import (
    AgentAction,
    AgentAnomaly,
    AgentPolicy,
    AIAgent,
    AnomalyStatus,
    GovernanceManager,
    RiskLevel,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _hours_ago(hours: float) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Domain agent definitions — mirrors src/agents/domain_agents.py
# ---------------------------------------------------------------------------

_ENTERPRISE_AGENTS: list[dict] = [
    {
        "agent_id": "planner",
        "name": "Planner",
        "agent_type": "planning",
        "description": "Breaks operator requests into executable plans with dependency ordering and confidence thresholds",
        "owner": "AegisNex AI Platform",
        "team": "intelligence",
        "department": "AI Platform",
        "purpose": "Plan multi-step agent work before any tool or model execution begins.",
        "provider": "openai",
        "model": "gpt-4o",
        "version": "2.3.0",
        "risk_level": RiskLevel.MEDIUM.value,
        "trust_score": 91.0,
        "daily_budget": 45.0,
        "monthly_budget": 1200.0,
        "average_cost": 0.018,
        "average_latency": 1180.0,
        "success_rate": 96.4,
        "permissions": json.dumps(["plan:create", "context:read", "task:delegate"]),
        "connected_tools": json.dumps(["rag_search", "tool_router", "policy_context"]),
        "policies": json.dumps(["global-registered-agent-default-allow"]),
        "approval_required": False,
        "allowed_tools": json.dumps(["rag_search", "tool_router", "policy_context"]),
        "allowed_resources": json.dumps(["/api/ai/plan", "/api/knowledge", "/api/governance"]),
        "max_actions_per_hour": 180,
    },
    {
        "agent_id": "knowledge",
        "name": "Knowledge",
        "agent_type": "knowledge",
        "description": "Retrieves memory, documentation, and incident patterns for grounded responses",
        "owner": "AegisNex AI Platform",
        "team": "intelligence",
        "department": "AI Platform",
        "purpose": "Provide retrieved context to planning, verification, and answer generation.",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "version": "1.8.2",
        "risk_level": RiskLevel.LOW.value,
        "trust_score": 94.0,
        "daily_budget": 18.0,
        "monthly_budget": 540.0,
        "average_cost": 0.004,
        "average_latency": 420.0,
        "success_rate": 98.1,
        "permissions": json.dumps(["knowledge:read", "memory:read", "learning:append"]),
        "connected_tools": json.dumps(["knowledge_base", "sqlite_memory", "embedding_search"]),
        "policies": json.dumps(
            ["knowledge-agent-no-mutations", "global-registered-agent-default-allow"]
        ),
        "approval_required": False,
        "allowed_tools": json.dumps(["knowledge_base", "sqlite_memory", "embedding_search"]),
        "allowed_resources": json.dumps(["/api/knowledge", "/api/search"]),
        "max_actions_per_hour": 240,
    },
    {
        "agent_id": "docker",
        "name": "Docker",
        "agent_type": "infrastructure",
        "description": "Inspects Docker containers, images, health status, and runtime drift",
        "owner": "Infrastructure Operations",
        "team": "operations",
        "department": "Infrastructure",
        "purpose": "Observe container state and provide safe remediation context.",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "version": "1.6.4",
        "risk_level": RiskLevel.MEDIUM.value,
        "trust_score": 88.0,
        "daily_budget": 22.0,
        "monthly_budget": 660.0,
        "average_cost": 0.006,
        "average_latency": 560.0,
        "success_rate": 95.2,
        "permissions": json.dumps(["containers:read", "images:read", "container:restart:request"]),
        "connected_tools": json.dumps(["docker_scan", "container_health", "restart_request"]),
        "policies": json.dumps(
            ["monitoring-query-allowed", "global-registered-agent-default-allow"]
        ),
        "approval_required": True,
        "allowed_tools": json.dumps(["docker_scan", "container_health", "restart_request"]),
        "allowed_resources": json.dumps(["/api/containers"]),
        "max_actions_per_hour": 120,
    },
    {
        "agent_id": "metrics",
        "name": "Metrics",
        "agent_type": "observability",
        "description": "Collects host, service, latency, and saturation metrics for operational decisions",
        "owner": "SRE",
        "team": "operations",
        "department": "Infrastructure",
        "purpose": "Maintain live operational telemetry for agents and dashboards.",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "version": "1.9.1",
        "risk_level": RiskLevel.LOW.value,
        "trust_score": 96.0,
        "daily_budget": 12.0,
        "monthly_budget": 360.0,
        "average_cost": 0.003,
        "average_latency": 260.0,
        "success_rate": 99.0,
        "permissions": json.dumps(["metrics:read", "targets:read", "health:read"]),
        "connected_tools": json.dumps(["system_metrics", "http_checks", "ssl_checks"]),
        "policies": json.dumps(
            ["monitoring-query-allowed", "global-registered-agent-default-allow"]
        ),
        "approval_required": False,
        "allowed_tools": json.dumps(["system_metrics", "http_checks", "ssl_checks"]),
        "allowed_resources": json.dumps(["/api/metrics", "/api/targets", "/api/health"]),
        "max_actions_per_hour": 360,
    },
    {
        "agent_id": "policy",
        "name": "Policy",
        "agent_type": "governance",
        "description": "Evaluates policy constraints and converts risky work into approval-gated requests",
        "owner": "Security Governance",
        "team": "security",
        "department": "Security",
        "purpose": "Enforce allow, deny, and approval decisions before execution.",
        "provider": "openai",
        "model": "gpt-4o",
        "version": "2.1.0",
        "risk_level": RiskLevel.HIGH.value,
        "trust_score": 89.0,
        "daily_budget": 30.0,
        "monthly_budget": 900.0,
        "average_cost": 0.014,
        "average_latency": 740.0,
        "success_rate": 97.3,
        "permissions": json.dumps(["policy:evaluate", "approval:create", "audit:write"]),
        "connected_tools": json.dumps(["policy_engine", "approval_queue", "audit_log"]),
        "policies": json.dumps(["global-registered-agent-default-allow"]),
        "approval_required": False,
        "allowed_tools": json.dumps(["policy_engine", "approval_queue", "audit_log"]),
        "allowed_resources": json.dumps(["/api/governance", "/api/approvals", "/api/audit"]),
        "max_actions_per_hour": 220,
    },
    {
        "agent_id": "risk",
        "name": "Risk",
        "agent_type": "risk",
        "description": "Scores proposed actions for blast radius, reversibility, confidence, and compliance exposure",
        "owner": "Security Governance",
        "team": "security",
        "department": "Security",
        "purpose": "Classify agent actions before policy enforcement and execution.",
        "provider": "openai",
        "model": "gpt-4o",
        "version": "2.0.5",
        "risk_level": RiskLevel.HIGH.value,
        "trust_score": 87.0,
        "daily_budget": 28.0,
        "monthly_budget": 840.0,
        "average_cost": 0.012,
        "average_latency": 690.0,
        "success_rate": 96.8,
        "permissions": json.dumps(["risk:score", "context:read", "audit:write"]),
        "connected_tools": json.dumps(["risk_engine", "policy_context", "audit_log"]),
        "policies": json.dumps(["global-registered-agent-default-allow"]),
        "approval_required": False,
        "allowed_tools": json.dumps(["risk_engine", "policy_context", "audit_log"]),
        "allowed_resources": json.dumps(["/api/governance", "/api/audit"]),
        "max_actions_per_hour": 200,
    },
    {
        "agent_id": "verifier",
        "name": "Verifier",
        "agent_type": "verification",
        "description": "Checks tool results against the objective and decides whether more work is required",
        "owner": "AegisNex AI Platform",
        "team": "intelligence",
        "department": "AI Platform",
        "purpose": "Validate agent outcomes and preserve loop termination guarantees.",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "version": "1.7.3",
        "risk_level": RiskLevel.MEDIUM.value,
        "trust_score": 93.0,
        "daily_budget": 20.0,
        "monthly_budget": 600.0,
        "average_cost": 0.005,
        "average_latency": 510.0,
        "success_rate": 97.9,
        "permissions": json.dumps(["tool_results:read", "verification:write", "confidence:score"]),
        "connected_tools": json.dumps(["result_verifier", "confidence_scorer", "evidence_builder"]),
        "policies": json.dumps(["global-registered-agent-default-allow"]),
        "approval_required": False,
        "allowed_tools": json.dumps(["result_verifier", "confidence_scorer", "evidence_builder"]),
        "allowed_resources": json.dumps(["/api/ai/verify", "/api/audit"]),
        "max_actions_per_hour": 180,
    },
    {
        "agent_id": "executor",
        "name": "Executor",
        "agent_type": "execution",
        "description": "Executes approved tool calls and records structured outcomes for verification",
        "owner": "AegisNex AI Platform",
        "team": "operations",
        "department": "AI Platform",
        "purpose": "Run approved tool calls while preserving audit and approval boundaries.",
        "provider": "openai",
        "model": "gpt-4o",
        "version": "2.2.1",
        "risk_level": RiskLevel.CRITICAL.value,
        "trust_score": 84.0,
        "daily_budget": 55.0,
        "monthly_budget": 1650.0,
        "average_cost": 0.021,
        "average_latency": 1320.0,
        "success_rate": 94.6,
        "permissions": json.dumps(["tool:execute", "approval:read", "audit:write"]),
        "connected_tools": json.dumps(["tool_executor", "approval_gate", "audit_log"]),
        "policies": json.dumps(["global-registered-agent-default-allow"]),
        "approval_required": True,
        "allowed_tools": json.dumps(["tool_executor", "approval_gate", "audit_log"]),
        "allowed_resources": json.dumps(["/api/ai/execute", "/api/approvals", "/api/audit"]),
        "max_actions_per_hour": 120,
    },
]

_DOMAIN_AGENTS: list[dict] = [
    {
        "agent_id": "supervisor-agent",
        "name": "Supervisor Agent",
        "agent_type": "orchestrator",
        "description": "Decomposes tasks, delegates to specialist agents, aggregates results",
        "owner": "platform",
        "team": "intelligence",
        "risk_level": RiskLevel.MEDIUM.value,
        "trust_score": 85.0,
        "allowed_tools": json.dumps(
            ["health", "metrics", "docker", "incident", "target", "audit", "report", "notification"]
        ),
        "allowed_resources": json.dumps(["*"]),
        "max_actions_per_hour": 200,
    },
    {
        "agent_id": "infrastructure-agent",
        "name": "Infrastructure Agent",
        "agent_type": "infrastructure",
        "description": "Assesses infrastructure capacity, service health, and resource posture",
        "owner": "platform",
        "team": "operations",
        "risk_level": RiskLevel.LOW.value,
        "trust_score": 90.0,
        "allowed_tools": json.dumps(["health"]),
        "allowed_resources": json.dumps(["/api/health", "/api/infrastructure"]),
        "max_actions_per_hour": 60,
    },
    {
        "agent_id": "docker-agent",
        "name": "Docker Agent",
        "agent_type": "infrastructure",
        "description": "Container inventory, Docker runtime inspection, and health monitoring",
        "owner": "platform",
        "team": "operations",
        "risk_level": RiskLevel.LOW.value,
        "trust_score": 88.0,
        "allowed_tools": json.dumps(["docker"]),
        "allowed_resources": json.dumps(["/api/containers"]),
        "max_actions_per_hour": 40,
    },
    {
        "agent_id": "monitoring-agent",
        "name": "Monitoring Agent",
        "agent_type": "operations",
        "description": "Collects monitoring targets, metrics, and health signals",
        "owner": "platform",
        "team": "operations",
        "risk_level": RiskLevel.LOW.value,
        "trust_score": 92.0,
        "allowed_tools": json.dumps(["metrics", "target"]),
        "allowed_resources": json.dumps(["/api/targets", "/api/metrics"]),
        "max_actions_per_hour": 100,
    },
    {
        "agent_id": "incident-agent",
        "name": "Incident Agent",
        "agent_type": "operations",
        "description": "Incident and notification triage, escalation, and resolution tracking",
        "owner": "platform",
        "team": "operations",
        "risk_level": RiskLevel.MEDIUM.value,
        "trust_score": 82.0,
        "allowed_tools": json.dumps(["incident", "notification"]),
        "allowed_resources": json.dumps(["/api/incidents", "/api/notifications"]),
        "max_actions_per_hour": 80,
    },
    {
        "agent_id": "reporting-agent",
        "name": "Reporting Agent",
        "agent_type": "general",
        "description": "Operational reporting, weekly/monthly summaries, and trend analysis",
        "owner": "platform",
        "team": "analytics",
        "risk_level": RiskLevel.LOW.value,
        "trust_score": 95.0,
        "allowed_tools": json.dumps(["report"]),
        "allowed_resources": json.dumps(["/api/reports"]),
        "max_actions_per_hour": 20,
    },
    {
        "agent_id": "knowledge-agent",
        "name": "Knowledge Agent",
        "agent_type": "general",
        "description": "Knowledge base search, memory retrieval, and learning consolidation",
        "owner": "platform",
        "team": "intelligence",
        "risk_level": RiskLevel.LOW.value,
        "trust_score": 90.0,
        "allowed_tools": json.dumps([]),
        "allowed_resources": json.dumps(["/api/knowledge"]),
        "max_actions_per_hour": 50,
    },
    {
        "agent_id": "compliance-agent",
        "name": "Compliance Agent",
        "agent_type": "compliance",
        "description": "Audit evidence collection, policy review, and regulatory compliance checks",
        "owner": "platform",
        "team": "security",
        "risk_level": RiskLevel.HIGH.value,
        "trust_score": 80.0,
        "allowed_tools": json.dumps(["audit"]),
        "allowed_resources": json.dumps(["/api/audit", "/api/compliance"]),
        "max_actions_per_hour": 30,
    },
    {
        "agent_id": "guardian-agent",
        "name": "Guardian Agent",
        "agent_type": "security",
        "description": "Autonomous guardian mode — monitors system health, auto-restarts failed services, enforces policy gates",
        "owner": "platform",
        "team": "security",
        "risk_level": RiskLevel.CRITICAL.value,
        "trust_score": 75.0,
        "allowed_tools": json.dumps(["health", "docker", "incident"]),
        "allowed_resources": json.dumps(["*"]),
        "max_actions_per_hour": 120,
    },
    {
        "agent_id": "self-healing-agent",
        "name": "Self-Healing Agent",
        "agent_type": "security",
        "description": "Policy-gated automatic remediation of detected issues — container restarts, config rollbacks",
        "owner": "platform",
        "team": "security",
        "risk_level": RiskLevel.CRITICAL.value,
        "trust_score": 70.0,
        "allowed_tools": json.dumps(["health", "docker"]),
        "allowed_resources": json.dumps(["/api/containers", "/api/infrastructure"]),
        "max_actions_per_hour": 30,
    },
    {
        "agent_id": "customer-support-agent",
        "name": "Customer Support Agent",
        "agent_type": "support",
        "description": "Handles support workflows such as customer messages, refunds, credits, and account updates",
        "owner": "support",
        "team": "customer-success",
        "risk_level": RiskLevel.HIGH.value,
        "trust_score": 78.0,
        "allowed_tools": json.dumps(["ticket", "email", "billing", "crm"]),
        "allowed_resources": json.dumps(["/api/customers", "/api/billing", "/api/support"]),
        "max_actions_per_hour": 80,
    },
    {
        "agent_id": "deployment-agent",
        "name": "Deployment Agent",
        "agent_type": "devops",
        "description": "Coordinates code deploys, rollbacks, release notes, and production change requests",
        "owner": "platform",
        "team": "engineering",
        "risk_level": RiskLevel.CRITICAL.value,
        "trust_score": 74.0,
        "allowed_tools": json.dumps(["github", "ci", "deploy", "incident"]),
        "allowed_resources": json.dumps(["/api/deployments", "/api/github", "/api/incidents"]),
        "max_actions_per_hour": 25,
    },
    {
        "agent_id": "finance-agent",
        "name": "Finance Agent",
        "agent_type": "finance",
        "description": "Reviews billing, invoices, credits, payment retries, and finance operations",
        "owner": "finance",
        "team": "finance",
        "risk_level": RiskLevel.HIGH.value,
        "trust_score": 76.0,
        "allowed_tools": json.dumps(["billing", "invoice", "payment"]),
        "allowed_resources": json.dumps(["/api/billing", "/api/invoices", "/api/payments"]),
        "max_actions_per_hour": 40,
    },
    {
        "agent_id": "data-ops-agent",
        "name": "Data Operations Agent",
        "agent_type": "data",
        "description": "Performs data quality checks, retention workflows, exports, and warehouse maintenance",
        "owner": "data",
        "team": "data-platform",
        "risk_level": RiskLevel.HIGH.value,
        "trust_score": 81.0,
        "allowed_tools": json.dumps(["warehouse", "export", "retention", "analytics"]),
        "allowed_resources": json.dumps(["/api/data", "/api/warehouse", "/api/exports"]),
        "max_actions_per_hour": 45,
    },
    {
        "agent_id": "integration-agent",
        "name": "Integration Agent",
        "agent_type": "integration",
        "description": "Calls third-party APIs, manages webhooks, and syncs external systems",
        "owner": "platform",
        "team": "integrations",
        "risk_level": RiskLevel.MEDIUM.value,
        "trust_score": 83.0,
        "allowed_tools": json.dumps(["webhook", "oauth", "external_api"]),
        "allowed_resources": json.dumps(["/api/integrations", "/api/webhooks"]),
        "max_actions_per_hour": 120,
    },
]


# ---------------------------------------------------------------------------
# Default governance policies
# ---------------------------------------------------------------------------

_DEFAULT_POLICIES: list[dict] = [
    {
        "name": "self-healing-approval-required",
        "description": "Self-healing agent actions require human approval before execution",
        "policy_type": "approval",
        "target_agents": json.dumps(["self-healing-agent"]),
        "conditions": json.dumps({"action_type": "remediation"}),
        "effect": "approve",
        "priority": 10,
    },
    {
        "name": "guardian-critical-approval",
        "description": "Guardian agent destructive actions require human approval",
        "policy_type": "approval",
        "target_agents": json.dumps(["guardian-agent"]),
        "conditions": json.dumps({"action_type": "restart"}),
        "effect": "approve",
        "priority": 11,
    },
    {
        "name": "prod-deploy-approval-required",
        "description": "Production deployments require human approval before execution",
        "policy_type": "approval",
        "target_agents": json.dumps(["deployment-agent"]),
        "conditions": json.dumps({"action_type": "deploy", "target_pattern": "prod|production"}),
        "effect": "approve",
        "priority": 12,
    },
    {
        "name": "prod-rollback-approval-required",
        "description": "Production rollbacks require human approval because they can disrupt customer traffic",
        "policy_type": "approval",
        "target_agents": json.dumps(["deployment-agent", "self-healing-agent"]),
        "conditions": json.dumps({"action_type": "rollback", "target_pattern": "prod|production"}),
        "effect": "approve",
        "priority": 13,
    },
    {
        "name": "block-direct-prod-db-write",
        "description": "No agent may write directly to production databases",
        "policy_type": "access_control",
        "target_agents": json.dumps(["*"]),
        "conditions": json.dumps(
            {"action_type": "write", "target_pattern": "prod.*db|production.*database"}
        ),
        "effect": "deny",
        "priority": 14,
    },
    {
        "name": "block-data-delete",
        "description": "Agents may not delete customer or warehouse data without a separate manual process",
        "policy_type": "access_control",
        "target_agents": json.dumps(
            ["data-ops-agent", "customer-support-agent", "integration-agent"]
        ),
        "conditions": json.dumps(
            {"action_type": "delete", "target_pattern": "customer|warehouse|dataset|pii"}
        ),
        "effect": "deny",
        "priority": 15,
    },
    {
        "name": "customer-refund-approval-required",
        "description": "Customer refunds require human approval before funds move",
        "policy_type": "approval",
        "target_agents": json.dumps(["customer-support-agent", "finance-agent"]),
        "conditions": json.dumps({"action_type": "refund"}),
        "effect": "approve",
        "priority": 16,
    },
    {
        "name": "block-large-credit-automation",
        "description": "Large account credits cannot be issued automatically by agents",
        "policy_type": "access_control",
        "target_agents": json.dumps(["customer-support-agent", "finance-agent"]),
        "conditions": json.dumps(
            {"action_type": "credit", "target_pattern": "large|enterprise|over-500"}
        ),
        "effect": "deny",
        "priority": 17,
    },
    {
        "name": "payment-retry-approval-required",
        "description": "Payment retries require review to avoid duplicate charges",
        "policy_type": "approval",
        "target_agents": json.dumps(["finance-agent"]),
        "conditions": json.dumps({"action_type": "payment_retry"}),
        "effect": "approve",
        "priority": 18,
    },
    {
        "name": "external-webhook-approval-required",
        "description": "Creating or updating outbound webhooks requires human approval",
        "policy_type": "approval",
        "target_agents": json.dumps(["integration-agent"]),
        "conditions": json.dumps({"action_type": "webhook_update"}),
        "effect": "approve",
        "priority": 19,
    },
    {
        "name": "block-secret-exfiltration",
        "description": "Agents may not send secrets or credentials to external systems",
        "policy_type": "access_control",
        "target_agents": json.dumps(["*"]),
        "conditions": json.dumps(
            {"action_type": "external_api", "target_pattern": "secret|credential|token|api_key"}
        ),
        "effect": "deny",
        "priority": 20,
    },
    {
        "name": "support-email-approval-for-legal",
        "description": "Customer-facing legal or termination messages require review before sending",
        "policy_type": "approval",
        "target_agents": json.dumps(["customer-support-agent"]),
        "conditions": json.dumps(
            {
                "action_type": "send_email",
                "target_pattern": "legal|termination|breach|refund-denial",
            }
        ),
        "effect": "approve",
        "priority": 21,
    },
    {
        "name": "compliance-audit-only-read",
        "description": "Compliance agent can only read audit logs, never write or delete",
        "policy_type": "access_control",
        "target_agents": json.dumps(["compliance-agent"]),
        "conditions": json.dumps({"action_type": "write"}),
        "effect": "deny",
        "priority": 22,
    },
    {
        "name": "knowledge-agent-no-mutations",
        "description": "Knowledge agent is read-only — no mutations to platform state",
        "policy_type": "access_control",
        "target_agents": json.dumps(["knowledge-agent"]),
        "conditions": json.dumps({"action_type": "mutation"}),
        "effect": "deny",
        "priority": 23,
    },
    {
        "name": "reporting-agent-read-only",
        "description": "Reporting agent is read-only — generates reports but cannot modify data",
        "policy_type": "access_control",
        "target_agents": json.dumps(["reporting-agent"]),
        "conditions": json.dumps({"action_type": "write"}),
        "effect": "deny",
        "priority": 24,
    },
    {
        "name": "data-export-approval-required",
        "description": "Bulk data exports require human review before files are generated",
        "policy_type": "approval",
        "target_agents": json.dumps(["data-ops-agent", "compliance-agent"]),
        "conditions": json.dumps(
            {"action_type": "export", "target_pattern": "bulk|customer|pii|audit"}
        ),
        "effect": "approve",
        "priority": 25,
    },
    {
        "name": "block-disable-monitoring",
        "description": "Agents may not disable monitoring or alerting controls",
        "policy_type": "access_control",
        "target_agents": json.dumps(["monitoring-agent", "self-healing-agent", "deployment-agent"]),
        "conditions": json.dumps({"action_type": "disable_monitoring"}),
        "effect": "deny",
        "priority": 26,
    },
    {
        "name": "incident-notification-allowed",
        "description": "Incident agents may send operational incident notifications",
        "policy_type": "access_control",
        "target_agents": json.dumps(["incident-agent"]),
        "conditions": json.dumps({"action_type": "notification"}),
        "effect": "allow",
        "priority": 100,
    },
    {
        "name": "monitoring-query-allowed",
        "description": "Monitoring and infrastructure agents may query health and metrics endpoints",
        "policy_type": "access_control",
        "target_agents": json.dumps(["monitoring-agent", "infrastructure-agent", "docker-agent"]),
        "conditions": json.dumps({"action_type": "query"}),
        "effect": "allow",
        "priority": 101,
    },
    {
        "name": "global-registered-agent-default-allow",
        "description": "Registered active agents are allowed when no deny or approval policy matches",
        "policy_type": "access_control",
        "target_agents": json.dumps(["*"]),
        "conditions": json.dumps({}),
        "effect": "allow",
        "priority": 1000,
    },
]


# ---------------------------------------------------------------------------
# Demo action history
# ---------------------------------------------------------------------------

_ACTION_TEMPLATES: list[dict] = [
    {
        "agent_id": "planner",
        "action_type": "plan",
        "action_summary": "Built a 5-step remediation plan for elevated API latency",
        "target_resource": "/api/ai/plan",
        "confidence": 0.94,
        "verdict": "allowed",
        "duration_ms": 1180,
        "cost": 0.019,
    },
    {
        "agent_id": "planner",
        "action_type": "delegation",
        "action_summary": "Routed evidence collection to Metrics, Docker, and Knowledge agents",
        "target_resource": "/api/governance",
        "confidence": 0.91,
        "verdict": "allowed",
        "duration_ms": 940,
        "cost": 0.016,
    },
    {
        "agent_id": "knowledge",
        "action_type": "query",
        "action_summary": "Retrieved prior incident notes for Postgres connection pool saturation",
        "target_resource": "/api/knowledge",
        "confidence": 0.97,
        "verdict": "allowed",
        "duration_ms": 410,
        "cost": 0.004,
    },
    {
        "agent_id": "knowledge",
        "action_type": "query",
        "action_summary": "Found runbook section for safe container restart checks",
        "target_resource": "/api/search",
        "confidence": 0.95,
        "verdict": "allowed",
        "duration_ms": 460,
        "cost": 0.004,
    },
    {
        "agent_id": "docker",
        "action_type": "query",
        "action_summary": "Inspected container health for api, worker, and postgres services",
        "target_resource": "/api/containers",
        "confidence": 0.90,
        "verdict": "allowed",
        "duration_ms": 575,
        "cost": 0.006,
    },
    {
        "agent_id": "docker",
        "action_type": "restart",
        "action_summary": "Requested restart for unhealthy worker container after policy evaluation",
        "target_resource": "/api/containers/worker/restart",
        "confidence": 0.83,
        "verdict": "pending_approval",
        "duration_ms": 830,
        "cost": 0.008,
    },
    {
        "agent_id": "metrics",
        "action_type": "query",
        "action_summary": "Collected p95 latency, CPU, memory, and error-rate metrics",
        "target_resource": "/api/metrics",
        "confidence": 0.99,
        "verdict": "allowed",
        "duration_ms": 255,
        "cost": 0.003,
    },
    {
        "agent_id": "metrics",
        "action_type": "query",
        "action_summary": "Verified all public targets were responding inside SLA",
        "target_resource": "/api/targets",
        "confidence": 0.98,
        "verdict": "allowed",
        "duration_ms": 285,
        "cost": 0.003,
    },
    {
        "agent_id": "policy",
        "action_type": "policy_evaluation",
        "action_summary": "Evaluated production restart request against approval policies",
        "target_resource": "/api/governance/policies",
        "confidence": 0.96,
        "verdict": "allowed",
        "duration_ms": 715,
        "cost": 0.013,
    },
    {
        "agent_id": "policy",
        "action_type": "approval_request",
        "action_summary": "Created human approval request for a critical execution path",
        "target_resource": "/api/approvals",
        "confidence": 0.94,
        "verdict": "allowed",
        "duration_ms": 760,
        "cost": 0.014,
    },
    {
        "agent_id": "risk",
        "action_type": "risk_assessment",
        "action_summary": "Scored container restart as high risk because it affected production workers",
        "target_resource": "/api/governance/risk",
        "confidence": 0.92,
        "verdict": "allowed",
        "duration_ms": 690,
        "cost": 0.012,
    },
    {
        "agent_id": "risk",
        "action_type": "risk_assessment",
        "action_summary": "Classified read-only metrics collection as low blast-radius",
        "target_resource": "/api/governance/risk",
        "confidence": 0.97,
        "verdict": "allowed",
        "duration_ms": 520,
        "cost": 0.009,
    },
    {
        "agent_id": "verifier",
        "action_type": "verification",
        "action_summary": "Validated that remediation evidence satisfied the operator objective",
        "target_resource": "/api/ai/verify",
        "confidence": 0.93,
        "verdict": "allowed",
        "duration_ms": 505,
        "cost": 0.005,
    },
    {
        "agent_id": "verifier",
        "action_type": "verification",
        "action_summary": "Rejected incomplete tool output and requested one additional metrics sample",
        "target_resource": "/api/ai/verify",
        "confidence": 0.72,
        "verdict": "allowed",
        "duration_ms": 535,
        "cost": 0.006,
    },
    {
        "agent_id": "executor",
        "action_type": "tool_execution",
        "action_summary": "Executed approved read-only diagnostics across metrics and container tools",
        "target_resource": "/api/ai/execute",
        "confidence": 0.90,
        "verdict": "allowed",
        "duration_ms": 1290,
        "cost": 0.021,
    },
    {
        "agent_id": "executor",
        "action_type": "tool_execution",
        "action_summary": "Paused destructive restart request pending human approval",
        "target_resource": "/api/approvals",
        "confidence": 0.89,
        "verdict": "pending_approval",
        "duration_ms": 610,
        "cost": 0.011,
    },
    {
        "agent_id": "monitoring-agent",
        "action_type": "query",
        "action_summary": "Collected CPU/memory metrics from all targets",
        "target_resource": "/api/metrics",
        "confidence": 0.92,
        "verdict": "allowed",
        "duration_ms": 145,
    },
    {
        "agent_id": "monitoring-agent",
        "action_type": "query",
        "action_summary": "Checked SSL certificate expiration for 3 endpoints",
        "target_resource": "/api/targets",
        "confidence": 0.95,
        "verdict": "allowed",
        "duration_ms": 89,
    },
    {
        "agent_id": "monitoring-agent",
        "action_type": "query",
        "action_summary": "DNS resolution check for api.aegisnex.io",
        "target_resource": "/api/targets",
        "confidence": 0.98,
        "verdict": "allowed",
        "duration_ms": 62,
    },
    {
        "agent_id": "docker-agent",
        "action_type": "query",
        "action_summary": "Scanned Docker containers — 12 running, 2 stopped",
        "target_resource": "/api/containers",
        "confidence": 0.88,
        "verdict": "allowed",
        "duration_ms": 234,
    },
    {
        "agent_id": "docker-agent",
        "action_type": "query",
        "action_summary": "Health check for postgres-primary container",
        "target_resource": "/api/containers",
        "confidence": 0.90,
        "verdict": "allowed",
        "duration_ms": 78,
    },
    {
        "agent_id": "incident-agent",
        "action_type": "query",
        "action_summary": "Retrieved 3 active incidents requiring attention",
        "target_resource": "/api/incidents",
        "confidence": 0.85,
        "verdict": "allowed",
        "duration_ms": 112,
    },
    {
        "agent_id": "incident-agent",
        "action_type": "notification",
        "action_summary": "Sent escalation notification for P1 incident INC-2024-001",
        "target_resource": "/api/notifications",
        "confidence": 0.78,
        "verdict": "allowed",
        "duration_ms": 340,
    },
    {
        "agent_id": "compliance-agent",
        "action_type": "query",
        "action_summary": "Retrieved audit logs for ISO 27001 evidence collection",
        "target_resource": "/api/audit",
        "confidence": 0.91,
        "verdict": "allowed",
        "duration_ms": 156,
    },
    {
        "agent_id": "compliance-agent",
        "action_type": "mutation",
        "action_summary": "Attempted to write compliance evidence — denied by policy",
        "target_resource": "/api/compliance",
        "confidence": 0.45,
        "verdict": "denied",
        "duration_ms": 22,
    },
    {
        "agent_id": "reporting-agent",
        "action_type": "query",
        "action_summary": "Generated weekly operations summary report",
        "target_resource": "/api/reports",
        "confidence": 0.94,
        "verdict": "allowed",
        "duration_ms": 890,
    },
    {
        "agent_id": "knowledge-agent",
        "action_type": "query",
        "action_summary": "Searched knowledge base for incident resolution patterns",
        "target_resource": "/api/knowledge",
        "confidence": 0.72,
        "verdict": "allowed",
        "duration_ms": 203,
    },
    {
        "agent_id": "knowledge-agent",
        "action_type": "query",
        "action_summary": "Retrieved memory entries for container failure correlations",
        "target_resource": "/api/knowledge",
        "confidence": 0.68,
        "verdict": "allowed",
        "duration_ms": 178,
    },
    {
        "agent_id": "infrastructure-agent",
        "action_type": "query",
        "action_summary": "System health check — CPU 34%, RAM 62%, Disk 45%",
        "target_resource": "/api/health",
        "confidence": 0.96,
        "verdict": "allowed",
        "duration_ms": 56,
    },
    {
        "agent_id": "supervisor-agent",
        "action_type": "delegation",
        "action_summary": "Decomposed task into 4 subtasks, delegated to specialist agents",
        "target_resource": "/api/governance",
        "confidence": 0.88,
        "verdict": "allowed",
        "duration_ms": 45,
    },
    {
        "agent_id": "guardian-agent",
        "action_type": "monitor",
        "action_summary": "Guardian health sweep — all services operational",
        "target_resource": "/api/health",
        "confidence": 0.93,
        "verdict": "allowed",
        "duration_ms": 123,
    },
    {
        "agent_id": "guardian-agent",
        "action_type": "restart",
        "action_summary": "Auto-restarted monitoring-engine after 3 consecutive failures",
        "target_resource": "/api/containers",
        "confidence": 0.82,
        "verdict": "pending_approval",
        "duration_ms": 2100,
    },
    {
        "agent_id": "self-healing-agent",
        "action_type": "remediation",
        "action_summary": "Rolled back config change after health check failure",
        "target_resource": "/api/infrastructure",
        "confidence": 0.74,
        "verdict": "pending_approval",
        "duration_ms": 3400,
    },
    {
        "agent_id": "self-healing-agent",
        "action_type": "query",
        "action_summary": "Pre-healing health check — all services healthy",
        "target_resource": "/api/health",
        "confidence": 0.89,
        "verdict": "allowed",
        "duration_ms": 67,
    },
    {
        "agent_id": "monitoring-agent",
        "action_type": "query",
        "action_summary": "HTTP endpoint check — 15/15 targets responding",
        "target_resource": "/api/targets",
        "confidence": 0.97,
        "verdict": "allowed",
        "duration_ms": 312,
    },
    {
        "agent_id": "incident-agent",
        "action_type": "query",
        "action_summary": "Auto-resolved stale incident INC-2024-005 (24h inactive)",
        "target_resource": "/api/incidents",
        "confidence": 0.80,
        "verdict": "allowed",
        "duration_ms": 89,
    },
    {
        "agent_id": "customer-support-agent",
        "action_type": "refund",
        "action_summary": "Requested refund for customer account CUST-1042",
        "target_resource": "/api/billing/refunds/customer",
        "confidence": 0.77,
        "verdict": "pending_approval",
        "duration_ms": 410,
    },
    {
        "agent_id": "customer-support-agent",
        "action_type": "send_email",
        "action_summary": "Drafted legal refund-denial email for enterprise customer",
        "target_resource": "/api/support/email/legal",
        "confidence": 0.71,
        "verdict": "pending_approval",
        "duration_ms": 360,
    },
    {
        "agent_id": "deployment-agent",
        "action_type": "deploy",
        "action_summary": "Requested production deploy for payments-api v2.8.1",
        "target_resource": "/api/deployments/production/payments-api",
        "confidence": 0.84,
        "verdict": "pending_approval",
        "duration_ms": 780,
    },
    {
        "agent_id": "deployment-agent",
        "action_type": "write",
        "action_summary": "Attempted direct production database migration",
        "target_resource": "/api/prod/db/payments",
        "confidence": 0.52,
        "verdict": "denied",
        "duration_ms": 95,
    },
    {
        "agent_id": "finance-agent",
        "action_type": "payment_retry",
        "action_summary": "Requested retry for failed invoice INV-8080",
        "target_resource": "/api/payments/retry",
        "confidence": 0.81,
        "verdict": "pending_approval",
        "duration_ms": 244,
    },
    {
        "agent_id": "data-ops-agent",
        "action_type": "delete",
        "action_summary": "Attempted deletion of stale customer PII dataset",
        "target_resource": "/api/data/customer/pii",
        "confidence": 0.49,
        "verdict": "denied",
        "duration_ms": 65,
    },
    {
        "agent_id": "data-ops-agent",
        "action_type": "export",
        "action_summary": "Requested bulk customer audit evidence export",
        "target_resource": "/api/exports/customer-audit-bulk",
        "confidence": 0.88,
        "verdict": "pending_approval",
        "duration_ms": 530,
    },
    {
        "agent_id": "integration-agent",
        "action_type": "external_api",
        "action_summary": "Attempted to send API token to external enrichment service",
        "target_resource": "/api/integrations/external/secret-token",
        "confidence": 0.38,
        "verdict": "denied",
        "duration_ms": 48,
    },
    {
        "agent_id": "integration-agent",
        "action_type": "webhook_update",
        "action_summary": "Requested webhook destination update for CRM sync",
        "target_resource": "/api/webhooks/crm-sync",
        "confidence": 0.86,
        "verdict": "pending_approval",
        "duration_ms": 205,
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def seed_governance(gov: GovernanceManager) -> dict[str, int]:
    """Seed the governance registry with existing agents, policies, and demo data.

    Returns counts of what was seeded.
    """
    counts = {"agents": 0, "policies": 0, "actions": 0, "anomalies": 0}

    agent_defs = _ENTERPRISE_AGENTS + _DOMAIN_AGENTS

    # 1. Register built-in and domain agents
    for agent_def in agent_defs:
        existing = gov.get_agent(agent_def["agent_id"])
        if existing is None:
            gov.register_agent(AIAgent(**agent_def))
            counts["agents"] += 1

    # 2. Create default policies (skip if name exists)
    for policy_def in _DEFAULT_POLICIES:
        existing = gov.get_policy(policy_def["name"])
        if existing is None:
            gov.create_policy(AgentPolicy(policy_id=0, **policy_def))
            counts["policies"] += 1

    # 3. Seed demo action history per action id, so new built-ins get history on existing databases.
    random.seed(42)  # Deterministic for consistent demo data
    enterprise_ids = {agent["agent_id"] for agent in _ENTERPRISE_AGENTS}
    for index, template in enumerate(_ACTION_TEMPLATES, start=1):
        action_prefix = "enterprise-act" if template["agent_id"] in enterprise_ids else "demo-act"
        action_id = f"{action_prefix}-{index:03d}"
        if gov.get_action(action_id) is None:
            hours_offset = random.uniform(0.5, 72)
            action = AgentAction(
                action_id=action_id,
                agent_id=template["agent_id"],
                action_type=template["action_type"],
                action_summary=template["action_summary"],
                target_resource=template["target_resource"],
                inputs=json.dumps({"trigger": "scheduled"}),
                outputs=json.dumps(
                    {"status": "ok", "cost": {"estimated_selected_usd": template.get("cost", 0.0)}}
                ),
                reasoning=f"Automated {template['action_type']} action by {template['agent_id']}",
                confidence_score=template["confidence"],
                policy_verdict=template["verdict"],
                status="success" if template["verdict"] != "denied" else "denied",
                duration_ms=template["duration_ms"],
            )
            action.created_at = _hours_ago(hours_offset)
            gov.record_action(action)
            counts["actions"] += 1

    # Update agent action counts from seeded and live actions.
    for agent_def in agent_defs:
        agent = gov.get_agent(agent_def["agent_id"])
        if agent:
            actions = gov.list_actions(agent_id=agent_def["agent_id"], limit=999)
            denied = sum(1 for a in actions if a.policy_verdict == "denied")
            avg_latency = (
                round(sum(a.duration_ms for a in actions) / len(actions), 1)
                if actions
                else agent.average_latency
            )
            success_rate = (
                round(sum(1 for a in actions if a.status == "success") / len(actions) * 100, 1)
                if actions
                else agent.success_rate
            )
            gov.update_agent(
                agent_def["agent_id"],
                total_actions=len(actions),
                total_denied=denied,
                average_latency=avg_latency,
                success_rate=success_rate,
                last_active_at=actions[0].created_at if actions else None,
            )

    # 4. Seed demo anomalies (only if no anomalies exist yet)
    existing_anomalies = gov.list_anomalies(limit=1)
    if not existing_anomalies:
        demo_anomalies = [
            {
                "agent_id": "compliance-agent",
                "anomaly_type": "policy_violation",
                "description": "Agent attempted write action on /api/compliance — denied by compliance-audit-only-read policy",
                "severity": RiskLevel.MEDIUM.value,
                "evidence": json.dumps(
                    {
                        "action_type": "write",
                        "target": "/api/compliance",
                        "policy": "compliance-audit-only-read",
                    }
                ),
                "status": AnomalyStatus.RESOLVED.value,
            },
            {
                "agent_id": "guardian-agent",
                "anomaly_type": "destructive_action",
                "description": "Agent executed container restart without prior approval — pending policy gate enforcement",
                "severity": RiskLevel.HIGH.value,
                "evidence": json.dumps(
                    {"action_type": "restart", "target": "monitoring-engine", "approved": False}
                ),
                "status": AnomalyStatus.OPEN.value,
            },
            {
                "agent_id": "self-healing-agent",
                "anomaly_type": "approval_bypass",
                "description": "Self-healing agent performed config rollback — requires human approval per policy",
                "severity": RiskLevel.CRITICAL.value,
                "evidence": json.dumps(
                    {"action_type": "remediation", "target": "config", "requires_approval": True}
                ),
                "status": AnomalyStatus.INVESTIGATING.value,
            },
        ]
        for anomaly_def in demo_anomalies:
            gov.record_anomaly(
                AgentAnomaly(
                    anomaly_id=0,
                    agent_id=anomaly_def["agent_id"],
                    anomaly_type=anomaly_def["anomaly_type"],
                    description=anomaly_def["description"],
                    severity=anomaly_def["severity"],
                    evidence=anomaly_def["evidence"],
                    status=anomaly_def["status"],
                    detected_at=_hours_ago(random.uniform(1, 48)),
                )
            )
            counts["anomalies"] += 1

    logger.info(
        "Governance seeded: %d agents, %d policies, %d actions, %d anomalies",
        counts["agents"],
        counts["policies"],
        counts["actions"],
        counts["anomalies"],
    )
    return counts
