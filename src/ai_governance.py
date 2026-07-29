"""AI Agent Governance — registry, action audit, policy enforcement, anomaly detection.

This module provides the core governance layer for AI agents operating within
AegisNex. It answers the questions every organization deploying AI must answer:
  - What agents exist? Who owns them?
  - What actions did each agent take, and why?
  - Are agents operating within their assigned policies?
  - Are there anomalous patterns indicating compromised or misbehaving agents?
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AgentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    DECOMMISSIONED = "decommissioned"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVE = "approve"


class AnomalyStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class ActionVerdict(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    PENDING_APPROVAL = "pending_approval"
    ANOMALOUS = "anomalous"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AIAgent:
    agent_id: str
    name: str
    agent_type: str
    description: str
    owner: str
    team: str
    department: str = ""
    purpose: str = ""
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    version: str = "1.0.0"
    status: str = AgentStatus.ACTIVE.value
    risk_level: str = RiskLevel.MEDIUM.value
    trust_score: float = 50.0
    daily_budget: float = 25.0
    monthly_budget: float = 750.0
    average_cost: float = 0.0
    average_latency: float = 0.0
    success_rate: float = 100.0
    permissions: str = "[]"
    connected_tools: str = "[]"
    policies: str = "[]"
    approval_required: bool = False
    allowed_tools: str = "[]"
    allowed_resources: str = "[]"
    max_actions_per_hour: int = 100
    total_actions: int = 0
    total_denied: int = 0
    total_anomalies: int = 0
    created_at: str = ""
    updated_at: str = ""
    last_active_at: str | None = None
    tenant_id: str = "default"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = self.agent_id
        d["department"] = self.department or self.team
        d["purpose"] = self.purpose or self.description
        d["execution_count"] = self.total_actions
        d["last_execution"] = self.last_active_at
        d["allowed_tools"] = (
            json.loads(self.allowed_tools)
            if isinstance(self.allowed_tools, str)
            else self.allowed_tools
        )
        d["allowed_resources"] = (
            json.loads(self.allowed_resources)
            if isinstance(self.allowed_resources, str)
            else self.allowed_resources
        )
        d["permissions"] = (
            json.loads(self.permissions) if isinstance(self.permissions, str) else self.permissions
        )
        d["connected_tools"] = (
            json.loads(self.connected_tools)
            if isinstance(self.connected_tools, str)
            else self.connected_tools
        )
        d["policies"] = (
            json.loads(self.policies) if isinstance(self.policies, str) else self.policies
        )
        d["approval_required"] = bool(self.approval_required)
        return d


@dataclass
class AgentAction:
    action_id: str
    agent_id: str
    action_type: str
    action_summary: str
    target_resource: str
    inputs: str = "{}"
    outputs: str = "{}"
    reasoning: str = ""
    confidence_score: float = 0.0
    policy_verdict: str = ActionVerdict.ALLOWED.value
    status: str = "success"
    duration_ms: float = 0.0
    created_at: str = ""
    tenant_id: str = "default"
    previous_hash: str = ""
    entry_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["inputs"] = json.loads(self.inputs) if isinstance(self.inputs, str) else self.inputs
        d["outputs"] = json.loads(self.outputs) if isinstance(self.outputs, str) else self.outputs
        return d


@dataclass
class AgentPolicy:
    policy_id: int
    name: str
    description: str
    policy_type: str
    target_agents: str = "[]"
    conditions: str = "{}"
    effect: str = PolicyEffect.ALLOW.value
    priority: int = 100
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    tenant_id: str = "default"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["target_agents"] = (
            json.loads(self.target_agents)
            if isinstance(self.target_agents, str)
            else self.target_agents
        )
        d["conditions"] = (
            json.loads(self.conditions) if isinstance(self.conditions, str) else self.conditions
        )
        d["enabled"] = bool(self.enabled)
        return d


@dataclass
class AgentAnomaly:
    anomaly_id: int
    agent_id: str
    anomaly_type: str
    description: str
    severity: str
    evidence: str = "{}"
    status: str = AnomalyStatus.OPEN.value
    detected_at: str = ""
    resolved_at: str | None = None
    resolved_by: str | None = None
    tenant_id: str = "default"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = (
            json.loads(self.evidence) if isinstance(self.evidence, str) else self.evidence
        )
        return d


# ---------------------------------------------------------------------------
# Governance Manager
# ---------------------------------------------------------------------------


class GovernanceManager:
    """Manages AI agent governance: registry, audit, policies, anomalies."""

    def __init__(self, database_path: str | Path = "aegisnex.db") -> None:
        self.database_path = Path(database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout=10000")
        except sqlite3.OperationalError:
            pass
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS ai_agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    agent_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    agent_type TEXT NOT NULL DEFAULT 'general',
                    description TEXT NOT NULL DEFAULT '',
                    owner TEXT NOT NULL DEFAULT 'system',
                    team TEXT NOT NULL DEFAULT 'platform',
                    department TEXT NOT NULL DEFAULT '',
                    purpose TEXT NOT NULL DEFAULT '',
                    provider TEXT NOT NULL DEFAULT 'openai',
                    model TEXT NOT NULL DEFAULT 'gpt-4o-mini',
                    version TEXT NOT NULL DEFAULT '1.0.0',
                    status TEXT NOT NULL DEFAULT 'active',
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    trust_score REAL NOT NULL DEFAULT 50.0,
                    daily_budget REAL NOT NULL DEFAULT 25.0,
                    monthly_budget REAL NOT NULL DEFAULT 750.0,
                    average_cost REAL NOT NULL DEFAULT 0.0,
                    average_latency REAL NOT NULL DEFAULT 0.0,
                    success_rate REAL NOT NULL DEFAULT 100.0,
                    permissions TEXT NOT NULL DEFAULT '[]',
                    connected_tools TEXT NOT NULL DEFAULT '[]',
                    policies TEXT NOT NULL DEFAULT '[]',
                    approval_required INTEGER NOT NULL DEFAULT 0,
                    allowed_tools TEXT NOT NULL DEFAULT '[]',
                    allowed_resources TEXT NOT NULL DEFAULT '[]',
                    max_actions_per_hour INTEGER NOT NULL DEFAULT 100,
                    total_actions INTEGER NOT NULL DEFAULT 0,
                    total_denied INTEGER NOT NULL DEFAULT 0,
                    total_anomalies INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_active_at TEXT,
                    UNIQUE (tenant_id, agent_id)
                );

                CREATE TABLE IF NOT EXISTS agent_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    action_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_summary TEXT NOT NULL,
                    target_resource TEXT NOT NULL DEFAULT '',
                    inputs TEXT NOT NULL DEFAULT '{}',
                    outputs TEXT NOT NULL DEFAULT '{}',
                    reasoning TEXT NOT NULL DEFAULT '',
                    confidence_score REAL NOT NULL DEFAULT 0.0,
                    policy_verdict TEXT NOT NULL DEFAULT 'allowed',
                    status TEXT NOT NULL DEFAULT 'success',
                    duration_ms REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL DEFAULT '',
                    entry_hash TEXT NOT NULL DEFAULT '',
                    UNIQUE (tenant_id, action_id)
                );

                CREATE TABLE IF NOT EXISTS agent_policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    policy_type TEXT NOT NULL DEFAULT 'access_control',
                    target_agents TEXT NOT NULL DEFAULT '[]',
                    conditions TEXT NOT NULL DEFAULT '{}',
                    effect TEXT NOT NULL DEFAULT 'allow',
                    priority INTEGER NOT NULL DEFAULT 100,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (tenant_id, name)
                );

                CREATE TABLE IF NOT EXISTS agent_anomalies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    agent_id TEXT NOT NULL,
                    anomaly_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'medium',
                    evidence TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'open',
                    detected_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolved_by TEXT
                );
            """)
            self._migrate_tenant_columns(connection)

    def _migrate_tenant_columns(self, connection: sqlite3.Connection) -> None:
        for table in ("ai_agents", "agent_actions", "agent_policies", "agent_anomalies"):
            columns = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "tenant_id" not in columns:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'"
                )
        self._rebuild_legacy_unique_tables(connection)
        self._migrate_agent_registry_columns(connection)
        self._migrate_action_hash_columns(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_agents_tenant ON ai_agents (tenant_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_actions_tenant ON agent_actions (tenant_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_actions_hash_chain ON agent_actions (tenant_id, id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_policies_tenant ON agent_policies (tenant_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_anomalies_tenant ON agent_anomalies (tenant_id)"
        )

    def _migrate_agent_registry_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(ai_agents)").fetchall()
        }
        registry_columns = {
            "department": "TEXT NOT NULL DEFAULT ''",
            "purpose": "TEXT NOT NULL DEFAULT ''",
            "provider": "TEXT NOT NULL DEFAULT 'openai'",
            "model": "TEXT NOT NULL DEFAULT 'gpt-4o-mini'",
            "version": "TEXT NOT NULL DEFAULT '1.0.0'",
            "daily_budget": "REAL NOT NULL DEFAULT 25.0",
            "monthly_budget": "REAL NOT NULL DEFAULT 750.0",
            "average_cost": "REAL NOT NULL DEFAULT 0.0",
            "average_latency": "REAL NOT NULL DEFAULT 0.0",
            "success_rate": "REAL NOT NULL DEFAULT 100.0",
            "permissions": "TEXT NOT NULL DEFAULT '[]'",
            "connected_tools": "TEXT NOT NULL DEFAULT '[]'",
            "policies": "TEXT NOT NULL DEFAULT '[]'",
            "approval_required": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, ddl in registry_columns.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE ai_agents ADD COLUMN {name} {ddl}")
        connection.execute("UPDATE ai_agents SET department = team WHERE department = ''")
        connection.execute("UPDATE ai_agents SET purpose = description WHERE purpose = ''")
        connection.execute(
            "UPDATE ai_agents SET connected_tools = allowed_tools WHERE connected_tools = '[]'"
        )

    def _migrate_action_hash_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(agent_actions)").fetchall()
        }
        if "previous_hash" not in columns:
            connection.execute(
                "ALTER TABLE agent_actions ADD COLUMN previous_hash TEXT NOT NULL DEFAULT ''"
            )
        if "entry_hash" not in columns:
            connection.execute(
                "ALTER TABLE agent_actions ADD COLUMN entry_hash TEXT NOT NULL DEFAULT ''"
            )
        self._backfill_action_hashes(connection)

    def _backfill_action_hashes(self, connection: sqlite3.Connection) -> None:
        tenants = [
            str(row["tenant_id"])
            for row in connection.execute(
                "SELECT DISTINCT tenant_id FROM agent_actions ORDER BY tenant_id"
            ).fetchall()
        ]
        for tenant in tenants:
            previous_hash = ""
            rows = connection.execute(
                "SELECT * FROM agent_actions WHERE tenant_id = ? ORDER BY id ASC",
                (tenant,),
            ).fetchall()
            for row in rows:
                existing_hash = str(row["entry_hash"] or "")
                expected_hash = self._hash_action_row(row, previous_hash)
                if (
                    str(row["previous_hash"] or "") != previous_hash
                    or existing_hash != expected_hash
                ):
                    connection.execute(
                        "UPDATE agent_actions SET previous_hash = ?, entry_hash = ? WHERE id = ?",
                        (previous_hash, expected_hash, row["id"]),
                    )
                    existing_hash = expected_hash
                previous_hash = existing_hash

    def _rebuild_legacy_unique_tables(self, connection: sqlite3.Connection) -> None:
        schemas = {
            "ai_agents": """
                CREATE TABLE ai_agents_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    agent_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    agent_type TEXT NOT NULL DEFAULT 'general',
                    description TEXT NOT NULL DEFAULT '',
                    owner TEXT NOT NULL DEFAULT 'system',
                    team TEXT NOT NULL DEFAULT 'platform',
                    department TEXT NOT NULL DEFAULT '',
                    purpose TEXT NOT NULL DEFAULT '',
                    provider TEXT NOT NULL DEFAULT 'openai',
                    model TEXT NOT NULL DEFAULT 'gpt-4o-mini',
                    version TEXT NOT NULL DEFAULT '1.0.0',
                    status TEXT NOT NULL DEFAULT 'active',
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    trust_score REAL NOT NULL DEFAULT 50.0,
                    daily_budget REAL NOT NULL DEFAULT 25.0,
                    monthly_budget REAL NOT NULL DEFAULT 750.0,
                    average_cost REAL NOT NULL DEFAULT 0.0,
                    average_latency REAL NOT NULL DEFAULT 0.0,
                    success_rate REAL NOT NULL DEFAULT 100.0,
                    permissions TEXT NOT NULL DEFAULT '[]',
                    connected_tools TEXT NOT NULL DEFAULT '[]',
                    policies TEXT NOT NULL DEFAULT '[]',
                    approval_required INTEGER NOT NULL DEFAULT 0,
                    allowed_tools TEXT NOT NULL DEFAULT '[]',
                    allowed_resources TEXT NOT NULL DEFAULT '[]',
                    max_actions_per_hour INTEGER NOT NULL DEFAULT 100,
                    total_actions INTEGER NOT NULL DEFAULT 0,
                    total_denied INTEGER NOT NULL DEFAULT 0,
                    total_anomalies INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_active_at TEXT,
                    UNIQUE (tenant_id, agent_id)
                )
            """,
            "agent_actions": """
                CREATE TABLE agent_actions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    action_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_summary TEXT NOT NULL,
                    target_resource TEXT NOT NULL DEFAULT '',
                    inputs TEXT NOT NULL DEFAULT '{}',
                    outputs TEXT NOT NULL DEFAULT '{}',
                    reasoning TEXT NOT NULL DEFAULT '',
                    confidence_score REAL NOT NULL DEFAULT 0.0,
                    policy_verdict TEXT NOT NULL DEFAULT 'allowed',
                    status TEXT NOT NULL DEFAULT 'success',
                    duration_ms REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL DEFAULT '',
                    entry_hash TEXT NOT NULL DEFAULT '',
                    UNIQUE (tenant_id, action_id)
                )
            """,
            "agent_policies": """
                CREATE TABLE agent_policies_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    policy_type TEXT NOT NULL DEFAULT 'access_control',
                    target_agents TEXT NOT NULL DEFAULT '[]',
                    conditions TEXT NOT NULL DEFAULT '{}',
                    effect TEXT NOT NULL DEFAULT 'allow',
                    priority INTEGER NOT NULL DEFAULT 100,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (tenant_id, name)
                )
            """,
        }
        columns = {
            "ai_agents": "id, tenant_id, agent_id, name, agent_type, description, owner, team, status, risk_level, trust_score, allowed_tools, allowed_resources, max_actions_per_hour, total_actions, total_denied, total_anomalies, created_at, updated_at, last_active_at",
            "agent_actions": "id, tenant_id, action_id, agent_id, action_type, action_summary, target_resource, inputs, outputs, reasoning, confidence_score, policy_verdict, status, duration_ms, created_at",
            "agent_policies": "id, tenant_id, name, description, policy_type, target_agents, conditions, effect, priority, enabled, created_at, updated_at",
        }
        legacy_markers = {
            "ai_agents": "agent_id TEXT NOT NULL UNIQUE",
            "agent_actions": "action_id TEXT NOT NULL UNIQUE",
            "agent_policies": "name TEXT NOT NULL UNIQUE",
        }
        for table, marker in legacy_markers.items():
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            create_sql = str(row["sql"] if row else "")
            if marker not in create_sql:
                continue
            connection.execute(schemas[table])
            connection.execute(
                f"INSERT OR IGNORE INTO {table}_new ({columns[table]}) SELECT {columns[table]} FROM {table}"
            )
            connection.execute(f"DROP TABLE {table}")
            connection.execute(f"ALTER TABLE {table}_new RENAME TO {table}")

    @staticmethod
    def _action_hash_payload(
        row_or_action: Any,
        previous_hash: str,
        tenant_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(row_or_action, AgentAction):
            return {
                "tenant_id": tenant_id or row_or_action.tenant_id,
                "action_id": row_or_action.action_id,
                "agent_id": row_or_action.agent_id,
                "action_type": row_or_action.action_type,
                "action_summary": row_or_action.action_summary,
                "target_resource": row_or_action.target_resource,
                "inputs": row_or_action.inputs,
                "outputs": row_or_action.outputs,
                "reasoning": row_or_action.reasoning,
                "confidence_score": row_or_action.confidence_score,
                "policy_verdict": row_or_action.policy_verdict,
                "status": row_or_action.status,
                "duration_ms": row_or_action.duration_ms,
                "created_at": created_at or row_or_action.created_at,
                "previous_hash": previous_hash,
            }
        return {
            "tenant_id": row_or_action["tenant_id"],
            "action_id": row_or_action["action_id"],
            "agent_id": row_or_action["agent_id"],
            "action_type": row_or_action["action_type"],
            "action_summary": row_or_action["action_summary"],
            "target_resource": row_or_action["target_resource"],
            "inputs": row_or_action["inputs"],
            "outputs": row_or_action["outputs"],
            "reasoning": row_or_action["reasoning"],
            "confidence_score": row_or_action["confidence_score"],
            "policy_verdict": row_or_action["policy_verdict"],
            "status": row_or_action["status"],
            "duration_ms": row_or_action["duration_ms"],
            "created_at": row_or_action["created_at"],
            "previous_hash": previous_hash,
        }

    @classmethod
    def _hash_payload(cls, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _hash_action(
        cls, action: AgentAction, previous_hash: str, tenant_id: str, created_at: str
    ) -> str:
        return cls._hash_payload(
            cls._action_hash_payload(
                action, previous_hash, tenant_id=tenant_id, created_at=created_at
            )
        )

    @classmethod
    def _hash_action_row(cls, row: sqlite3.Row, previous_hash: str) -> str:
        return cls._hash_payload(cls._action_hash_payload(row, previous_hash))

    # ---- Agent Registry ----

    def register_agent(self, agent: AIAgent, tenant_id: str | None = None) -> AIAgent:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        tenant = self._tenant(tenant_id or agent.tenant_id)
        p = self.placeholder
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO ai_agents (
                    tenant_id, agent_id, name, agent_type, description, owner, team,
                    department, purpose, provider, model, version,
                    status, risk_level, trust_score, daily_budget, monthly_budget,
                    average_cost, average_latency, success_rate, permissions,
                    connected_tools, policies, approval_required, allowed_tools, allowed_resources,
                    max_actions_per_hour, total_actions, total_denied, total_anomalies,
                    created_at, updated_at, last_active_at
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
                """,
                (
                    tenant,
                    agent.agent_id,
                    agent.name,
                    agent.agent_type,
                    agent.description,
                    agent.owner,
                    agent.team,
                    agent.department or agent.team,
                    agent.purpose or agent.description,
                    agent.provider,
                    agent.model,
                    agent.version,
                    agent.status,
                    agent.risk_level,
                    agent.trust_score,
                    agent.daily_budget,
                    agent.monthly_budget,
                    agent.average_cost,
                    agent.average_latency,
                    agent.success_rate,
                    agent.permissions,
                    agent.connected_tools,
                    agent.policies,
                    int(agent.approval_required),
                    agent.allowed_tools,
                    agent.allowed_resources,
                    agent.max_actions_per_hour,
                    agent.total_actions,
                    agent.total_denied,
                    agent.total_anomalies,
                    now,
                    now,
                    None,
                ),
            )
        agent.created_at = now
        agent.updated_at = now
        agent.tenant_id = tenant
        _logger.info("Registered AI agent: %s (%s)", agent.name, agent.agent_id)
        return agent

    def get_agent(self, agent_id: str, tenant_id: str = "default") -> AIAgent | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_agents WHERE tenant_id = ? AND agent_id = ?",
                (self._tenant(tenant_id), agent_id),
            ).fetchone()
        return self._row_to_agent(row) if row else None

    def list_agents(
        self,
        status: str | None = None,
        risk_level: str | None = None,
        team: str | None = None,
        tenant_id: str = "default",
    ) -> list[AIAgent]:
        conditions = ["tenant_id = ?"]
        params: list[Any] = [self._tenant(tenant_id)]
        if status:
            conditions.append("status = ?")
            params.append(status)
        if risk_level:
            conditions.append("risk_level = ?")
            params.append(risk_level)
        if team:
            conditions.append("team = ?")
            params.append(team)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM ai_agents {where} ORDER BY total_actions DESC", params
            ).fetchall()
        return [self._row_to_agent(r) for r in rows]

    def update_agent(self, agent_id: str, tenant_id: str = "default", **fields: Any) -> bool:
        if not fields:
            return False
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        fields["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [self._tenant(tenant_id), agent_id]
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE ai_agents SET {set_clause} WHERE tenant_id = ? AND agent_id = ?",
                tuple(values),
            )
        return cursor.rowcount > 0

    def delete_agent(self, agent_id: str, tenant_id: str = "default") -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM ai_agents WHERE tenant_id = ? AND agent_id = ?",
                (self._tenant(tenant_id), agent_id),
            )
        return cursor.rowcount > 0

    def get_agent_history(
        self, agent_id: str, limit: int = 50, tenant_id: str = "default"
    ) -> list[AgentAction]:
        return self.list_actions(agent_id=agent_id, limit=limit, tenant_id=tenant_id)

    def get_agent_policies(self, agent_id: str, tenant_id: str = "default") -> list[AgentPolicy]:
        matched: list[AgentPolicy] = []
        for policy in self.list_policies(tenant_id=tenant_id):
            try:
                targets = (
                    json.loads(policy.target_agents)
                    if isinstance(policy.target_agents, str)
                    else policy.target_agents
                )
            except Exception:
                targets = []
            if "*" in targets or agent_id in targets:
                matched.append(policy)
        return matched

    def get_agent_tools(self, agent_id: str, tenant_id: str = "default") -> dict[str, Any]:
        agent = self.get_agent(agent_id, tenant_id=tenant_id)
        if agent is None:
            return {"tools": [], "permissions": [], "resources": []}
        return {
            "agent_id": agent.agent_id,
            "tools": json.loads(agent.connected_tools)
            if isinstance(agent.connected_tools, str)
            else agent.connected_tools,
            "permissions": json.loads(agent.permissions)
            if isinstance(agent.permissions, str)
            else agent.permissions,
            "resources": json.loads(agent.allowed_resources)
            if isinstance(agent.allowed_resources, str)
            else agent.allowed_resources,
        }

    def get_agent_metrics(self, agent_id: str, tenant_id: str = "default") -> dict[str, Any] | None:
        agent = self.get_agent(agent_id, tenant_id=tenant_id)
        if agent is None:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(AVG(duration_ms), 0) AS avg_latency,
                    COALESCE(AVG(confidence_score), 0) AS avg_confidence,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successes,
                    SUM(CASE WHEN policy_verdict = 'denied' THEN 1 ELSE 0 END) AS denied,
                    MAX(created_at) AS last_execution
                FROM agent_actions
                WHERE tenant_id = ? AND agent_id = ?
                """,
                (self._tenant(tenant_id), agent_id),
            ).fetchone()
        total = int(row["total"] or 0)
        successes = int(row["successes"] or 0)
        return {
            "agent_id": agent.agent_id,
            "execution_count": agent.total_actions,
            "history_count": total,
            "success_rate": round((successes / total * 100), 1) if total else agent.success_rate,
            "stored_success_rate": agent.success_rate,
            "average_cost": agent.average_cost,
            "average_latency": round(float(row["avg_latency"] or agent.average_latency), 1),
            "stored_average_latency": agent.average_latency,
            "average_confidence": round(float(row["avg_confidence"] or 0), 2),
            "denied_count": int(row["denied"] or 0),
            "trust_score": agent.trust_score,
            "daily_budget": agent.daily_budget,
            "monthly_budget": agent.monthly_budget,
            "last_execution": row["last_execution"] or agent.last_active_at,
        }

    def get_agent_stats(self, tenant_id: str = "default") -> dict[str, Any]:
        tenant = self._tenant(tenant_id)
        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) as c FROM ai_agents WHERE tenant_id = ?", (tenant,)
            ).fetchone()["c"]
            active = connection.execute(
                "SELECT COUNT(*) as c FROM ai_agents WHERE tenant_id = ? AND status = 'active'",
                (tenant,),
            ).fetchone()["c"]
            by_risk = {}
            for row in connection.execute(
                "SELECT risk_level, COUNT(*) as c FROM ai_agents WHERE tenant_id = ? GROUP BY risk_level",
                (tenant,),
            ).fetchall():
                by_risk[row["risk_level"]] = row["c"]
            by_type = {}
            for row in connection.execute(
                "SELECT agent_type, COUNT(*) as c FROM ai_agents WHERE tenant_id = ? GROUP BY agent_type",
                (tenant,),
            ).fetchall():
                by_type[row["agent_type"]] = row["c"]
            total_actions = connection.execute(
                "SELECT COALESCE(SUM(total_actions), 0) as c FROM ai_agents WHERE tenant_id = ?",
                (tenant,),
            ).fetchone()["c"]
            total_denied = connection.execute(
                "SELECT COALESCE(SUM(total_denied), 0) as c FROM ai_agents WHERE tenant_id = ?",
                (tenant,),
            ).fetchone()["c"]
            total_anomalies = connection.execute(
                "SELECT COUNT(*) as c FROM agent_anomalies WHERE tenant_id = ? AND status = 'open'",
                (tenant,),
            ).fetchone()["c"]
            avg_trust = connection.execute(
                "SELECT COALESCE(AVG(trust_score), 50) as c FROM ai_agents WHERE tenant_id = ? AND status = 'active'",
                (tenant,),
            ).fetchone()["c"]
        return {
            "total_agents": total,
            "active_agents": active,
            "by_risk": by_risk,
            "by_type": by_type,
            "total_actions": total_actions,
            "total_denied": total_denied,
            "open_anomalies": total_anomalies,
            "avg_trust_score": round(avg_trust, 1),
        }

    # ---- Action Audit ----

    def record_action(self, action: AgentAction, tenant_id: str | None = None) -> AgentAction:
        now = action.created_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
        tenant = self._tenant(tenant_id or action.tenant_id)
        p = self.placeholder
        with self._connect() as connection:
            previous_row = connection.execute(
                "SELECT entry_hash FROM agent_actions WHERE tenant_id = ? ORDER BY id DESC LIMIT 1",
                (tenant,),
            ).fetchone()
            previous_hash = str(previous_row["entry_hash"] or "") if previous_row else ""
            entry_hash = self._hash_action(action, previous_hash, tenant, now)
            connection.execute(
                f"""
                INSERT INTO agent_actions (
                    tenant_id, action_id, agent_id, action_type, action_summary,
                    target_resource, inputs, outputs, reasoning,
                    confidence_score, policy_verdict, status, duration_ms, created_at,
                    previous_hash, entry_hash
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
                """,
                (
                    tenant,
                    action.action_id,
                    action.agent_id,
                    action.action_type,
                    action.action_summary,
                    action.target_resource,
                    action.inputs,
                    action.outputs,
                    action.reasoning,
                    action.confidence_score,
                    action.policy_verdict,
                    action.status,
                    action.duration_ms,
                    now,
                    previous_hash,
                    entry_hash,
                ),
            )
            connection.execute(
                "UPDATE ai_agents SET total_actions = total_actions + 1, last_active_at = ? WHERE tenant_id = ? AND agent_id = ?",
                (now, tenant, action.agent_id),
            )
            if action.policy_verdict == ActionVerdict.DENIED.value:
                connection.execute(
                    "UPDATE ai_agents SET total_denied = total_denied + 1 WHERE tenant_id = ? AND agent_id = ?",
                    (tenant, action.agent_id),
                )
            metrics = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       COALESCE(AVG(duration_ms), 0) AS avg_latency,
                       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successes
                FROM agent_actions
                WHERE tenant_id = ? AND agent_id = ?
                """,
                (tenant, action.agent_id),
            ).fetchone()
            total = int(metrics["total"] or 0)
            success_rate = (int(metrics["successes"] or 0) / total * 100) if total else 100.0
            connection.execute(
                "UPDATE ai_agents SET average_latency = ?, success_rate = ? WHERE tenant_id = ? AND agent_id = ?",
                (
                    round(float(metrics["avg_latency"] or 0), 1),
                    round(success_rate, 1),
                    tenant,
                    action.agent_id,
                ),
            )
        action.created_at = now
        action.tenant_id = tenant
        action.previous_hash = previous_hash
        action.entry_hash = entry_hash
        return action

    def get_action(self, action_id: str, tenant_id: str = "default") -> AgentAction | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_actions WHERE tenant_id = ? AND action_id = ?",
                (self._tenant(tenant_id), action_id),
            ).fetchone()
        return self._row_to_action(row) if row else None

    def list_actions(
        self,
        agent_id: str | None = None,
        action_type: str | None = None,
        verdict: str | None = None,
        limit: int = 100,
        offset: int = 0,
        tenant_id: str = "default",
    ) -> list[AgentAction]:
        conditions = ["tenant_id = ?"]
        params: list[Any] = [self._tenant(tenant_id)]
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)
        if verdict:
            conditions.append("policy_verdict = ?")
            params.append(verdict)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM agent_actions {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
        return [self._row_to_action(r) for r in rows]

    def get_action_stats(
        self, agent_id: str | None = None, hours: int = 24, tenant_id: str = "default"
    ) -> dict[str, Any]:
        since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        agent_filter = "AND agent_id = ?" if agent_id else ""
        params: list[Any] = [since, self._tenant(tenant_id)] + ([agent_id] if agent_id else [])
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) as c FROM agent_actions WHERE created_at >= ? AND tenant_id = ? {agent_filter}",
                params,
            ).fetchone()["c"]
            by_verdict = {}
            for row in connection.execute(
                f"SELECT policy_verdict, COUNT(*) as c FROM agent_actions WHERE created_at >= ? AND tenant_id = ? {agent_filter} GROUP BY policy_verdict",
                params,
            ).fetchall():
                by_verdict[row["policy_verdict"]] = row["c"]
            by_type = {}
            for row in connection.execute(
                f"SELECT action_type, COUNT(*) as c FROM agent_actions WHERE created_at >= ? AND tenant_id = ? {agent_filter} GROUP BY action_type",
                params,
            ).fetchall():
                by_type[row["action_type"]] = row["c"]
            avg_confidence = connection.execute(
                f"SELECT COALESCE(AVG(confidence_score), 0) as c FROM agent_actions WHERE created_at >= ? AND tenant_id = ? {agent_filter}",
                params,
            ).fetchone()["c"]
        return {
            "total_actions": total,
            "by_verdict": by_verdict,
            "by_type": by_type,
            "avg_confidence": round(avg_confidence, 2),
            "hours": hours,
        }

    def verify_action_audit_chain(self, tenant_id: str = "default") -> dict[str, Any]:
        tenant = self._tenant(tenant_id)
        errors: list[dict[str, Any]] = []
        previous_hash = ""
        head_hash = ""
        checked = 0
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_actions WHERE tenant_id = ? ORDER BY id ASC",
                (tenant,),
            ).fetchall()
        for row in rows:
            checked += 1
            expected_hash = self._hash_action_row(row, previous_hash)
            stored_previous = str(row["previous_hash"] or "")
            stored_hash = str(row["entry_hash"] or "")
            if stored_previous != previous_hash:
                errors.append(
                    {
                        "action_id": row["action_id"],
                        "error": "previous_hash_mismatch",
                        "expected": previous_hash,
                        "actual": stored_previous,
                    }
                )
                break
            if stored_hash != expected_hash:
                errors.append(
                    {
                        "action_id": row["action_id"],
                        "error": "entry_hash_mismatch",
                        "expected": expected_hash,
                        "actual": stored_hash,
                    }
                )
                break
            previous_hash = stored_hash
            head_hash = stored_hash
        return {
            "tenant_id": tenant,
            "valid": not errors,
            "total_entries": len(rows),
            "checked_entries": checked,
            "head_hash": head_hash,
            "first_invalid_action_id": errors[0]["action_id"] if errors else None,
            "errors": errors,
        }

    def export_action_audit_csv(self, tenant_id: str = "default", limit: int = 5000) -> str:
        tenant = self._tenant(tenant_id)
        actions = self.list_actions(limit=max(1, min(limit, 25000)), tenant_id=tenant)
        output = io.StringIO()
        fieldnames = [
            "tenant_id",
            "action_id",
            "agent_id",
            "action_type",
            "action_summary",
            "target_resource",
            "policy_verdict",
            "status",
            "confidence_score",
            "duration_ms",
            "created_at",
            "previous_hash",
            "entry_hash",
            "inputs",
            "outputs",
            "reasoning",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for action in actions:
            row = action.to_dict()
            writer.writerow(
                {
                    "tenant_id": row["tenant_id"],
                    "action_id": row["action_id"],
                    "agent_id": row["agent_id"],
                    "action_type": row["action_type"],
                    "action_summary": row["action_summary"],
                    "target_resource": row["target_resource"],
                    "policy_verdict": row["policy_verdict"],
                    "status": row["status"],
                    "confidence_score": row["confidence_score"],
                    "duration_ms": row["duration_ms"],
                    "created_at": row["created_at"],
                    "previous_hash": row["previous_hash"],
                    "entry_hash": row["entry_hash"],
                    "inputs": json.dumps(row["inputs"], sort_keys=True),
                    "outputs": json.dumps(row["outputs"], sort_keys=True),
                    "reasoning": row["reasoning"],
                }
            )
        return output.getvalue()

    # ---- Policy Engine ----

    def create_policy(self, policy: AgentPolicy, tenant_id: str | None = None) -> AgentPolicy:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        tenant = self._tenant(tenant_id or policy.tenant_id)
        p = self.placeholder
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                INSERT INTO agent_policies (
                    tenant_id, name, description, policy_type, target_agents,
                    conditions, effect, priority, enabled, created_at, updated_at
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
                """,
                (
                    tenant,
                    policy.name,
                    policy.description,
                    policy.policy_type,
                    policy.target_agents,
                    policy.conditions,
                    policy.effect,
                    policy.priority,
                    int(policy.enabled),
                    now,
                    now,
                ),
            )
        policy.policy_id = cursor.lastrowid
        policy.created_at = now
        policy.updated_at = now
        policy.tenant_id = tenant
        return policy

    def get_policy(self, name: str, tenant_id: str = "default") -> AgentPolicy | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_policies WHERE tenant_id = ? AND name = ?",
                (self._tenant(tenant_id), name),
            ).fetchone()
        return self._row_to_policy(row) if row else None

    def list_policies(
        self, enabled_only: bool = False, tenant_id: str = "default"
    ) -> list[AgentPolicy]:
        conditions = ["tenant_id = ?"]
        params: list[Any] = [self._tenant(tenant_id)]
        if enabled_only:
            conditions.append("enabled = 1")
        where = f"WHERE {' AND '.join(conditions)}"
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM agent_policies {where} ORDER BY priority ASC, name ASC",
                params,
            ).fetchall()
        return [self._row_to_policy(r) for r in rows]

    def update_policy(self, name: str, tenant_id: str = "default", **fields: Any) -> bool:
        if not fields:
            return False
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        fields["updated_at"] = now
        if "enabled" in fields:
            fields["enabled"] = int(fields["enabled"])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [self._tenant(tenant_id), name]
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE agent_policies SET {set_clause} WHERE tenant_id = ? AND name = ?",
                tuple(values),
            )
        return cursor.rowcount > 0

    def delete_policy(self, name: str, tenant_id: str = "default") -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM agent_policies WHERE tenant_id = ? AND name = ?",
                (self._tenant(tenant_id), name),
            )
        return cursor.rowcount > 0

    def evaluate_policies(
        self, agent_id: str, action_type: str, target: str, tenant_id: str = "default"
    ) -> tuple[str, str | None]:
        """Evaluate policies for a given agent action. Returns (verdict, reason)."""
        agent = self.get_agent(agent_id, tenant_id=tenant_id)
        if agent is None:
            return ActionVerdict.DENIED.value, f"Agent '{agent_id}' not registered"
        if agent.status != AgentStatus.ACTIVE.value:
            return ActionVerdict.DENIED.value, f"Agent status is '{agent.status}', not active"

        policies = self.list_policies(enabled_only=True, tenant_id=tenant_id)
        allow_reason: str | None = None
        for policy in policies:
            targets = (
                json.loads(policy.target_agents)
                if isinstance(policy.target_agents, str)
                else policy.target_agents
            )
            if targets and agent_id not in targets and "*" not in targets:
                continue

            conditions = (
                json.loads(policy.conditions)
                if isinstance(policy.conditions, str)
                else policy.conditions
            )
            if conditions:
                matched = True
                for key, value in conditions.items():
                    if (key == "action_type" and action_type != value) or (
                        key == "target_pattern" and not re.search(value, target)
                    ):
                        matched = False
                if not matched:
                    continue

            if policy.effect == PolicyEffect.DENY.value:
                return ActionVerdict.DENIED.value, f"Denied by policy: {policy.name}"
            if policy.effect == PolicyEffect.APPROVE.value:
                return (
                    ActionVerdict.PENDING_APPROVAL.value,
                    f"Requires approval per policy: {policy.name}",
                )
            if policy.effect == PolicyEffect.ALLOW.value:
                allow_reason = allow_reason or f"Allowed by policy: {policy.name}"

        return ActionVerdict.ALLOWED.value, allow_reason

    # ---- Anomaly Detection ----

    def record_anomaly(self, anomaly: AgentAnomaly, tenant_id: str | None = None) -> AgentAnomaly:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        tenant = self._tenant(tenant_id or anomaly.tenant_id)
        p = self.placeholder
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                INSERT INTO agent_anomalies (
                    tenant_id, agent_id, anomaly_type, description, severity,
                    evidence, status, detected_at
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p})
                """,
                (
                    tenant,
                    anomaly.agent_id,
                    anomaly.anomaly_type,
                    anomaly.description,
                    anomaly.severity,
                    anomaly.evidence,
                    anomaly.status,
                    now,
                ),
            )
            anomaly.anomaly_id = cursor.lastrowid
            connection.execute(
                "UPDATE ai_agents SET total_anomalies = total_anomalies + 1 WHERE tenant_id = ? AND agent_id = ?",
                (tenant, anomaly.agent_id),
            )
        anomaly.detected_at = now
        anomaly.tenant_id = tenant
        return anomaly

    def detect_anomalies(
        self, agent_id: str | None = None, window_hours: int = 1, tenant_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Analyze recent actions for anomalous patterns. Returns detected anomalies."""
        since = (datetime.now(UTC) - timedelta(hours=window_hours)).isoformat()
        agent_filter = "AND agent_id = ?" if agent_id else ""
        tenant = self._tenant(tenant_id)
        params: list[Any] = [since, tenant] + ([agent_id] if agent_id else [])
        detected: list[dict[str, Any]] = []

        with self._connect() as connection:
            # 1. Burst detection: too many actions in short window
            rows = connection.execute(
                f"""
                SELECT agent_id, COUNT(*) as action_count
                FROM agent_actions
                WHERE created_at >= ? AND tenant_id = ? {agent_filter}
                GROUP BY agent_id
                """,
                params,
            ).fetchall()
            for row in rows:
                agent = self.get_agent(row["agent_id"], tenant_id=tenant)
                if agent and row["action_count"] > agent.max_actions_per_hour:
                    detected.append(
                        {
                            "agent_id": row["agent_id"],
                            "anomaly_type": "action_burst",
                            "description": f"Agent executed {row['action_count']} actions in {window_hours}h (limit: {agent.max_actions_per_hour})",
                            "severity": RiskLevel.HIGH.value,
                            "evidence": {
                                "action_count": row["action_count"],
                                "limit": agent.max_actions_per_hour,
                            },
                        }
                    )

            # 2. High denial rate
            if not agent_id:
                rows2 = connection.execute(
                    f"""
                    SELECT agent_id,
                           COUNT(*) as total,
                           SUM(CASE WHEN policy_verdict = 'denied' THEN 1 ELSE 0 END) as denied
                    FROM agent_actions
                    WHERE created_at >= ? AND tenant_id = ? {agent_filter}
                    GROUP BY agent_id
                    HAVING total >= 5
                    """,
                    params,
                ).fetchall()
                for row in rows2:
                    if row["total"] > 0:
                        denial_rate = row["denied"] / row["total"]
                        if denial_rate > 0.3:
                            detected.append(
                                {
                                    "agent_id": row["agent_id"],
                                    "anomaly_type": "high_denial_rate",
                                    "description": f"Agent denial rate is {denial_rate:.0%} ({row['denied']}/{row['total']})",
                                    "severity": RiskLevel.CRITICAL.value
                                    if denial_rate > 0.5
                                    else RiskLevel.HIGH.value,
                                    "evidence": {
                                        "denial_rate": denial_rate,
                                        "denied": row["denied"],
                                        "total": row["total"],
                                    },
                                }
                            )

            # 3. Low confidence actions
            rows3 = connection.execute(
                f"""
                SELECT agent_id, AVG(confidence_score) as avg_conf, COUNT(*) as cnt
                FROM agent_actions
                WHERE created_at >= ? AND tenant_id = ? {agent_filter}
                GROUP BY agent_id
                HAVING avg_conf < 0.3 AND cnt >= 3
                """,
                params,
            ).fetchall()
            for row in rows3:
                detected.append(
                    {
                        "agent_id": row["agent_id"],
                        "anomaly_type": "low_confidence",
                        "description": f"Agent average confidence is {row['avg_conf']:.2f} across {row['cnt']} actions",
                        "severity": RiskLevel.MEDIUM.value,
                        "evidence": {"avg_confidence": row["avg_conf"], "action_count": row["cnt"]},
                    }
                )

        # Record detected anomalies
        for d in detected:
            existing = self._find_open_anomaly(d["agent_id"], d["anomaly_type"], tenant_id=tenant)
            if not existing:
                self.record_anomaly(
                    AgentAnomaly(
                        anomaly_id=0,
                        agent_id=d["agent_id"],
                        anomaly_type=d["anomaly_type"],
                        description=d["description"],
                        severity=d["severity"],
                        evidence=json.dumps(d.get("evidence", {})),
                    ),
                    tenant_id=tenant,
                )

        return detected

    def _find_open_anomaly(
        self, agent_id: str, anomaly_type: str, tenant_id: str = "default"
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM agent_anomalies WHERE tenant_id = ? AND agent_id = ? AND anomaly_type = ? AND status = 'open' LIMIT 1",
                (self._tenant(tenant_id), agent_id, anomaly_type),
            ).fetchone()
        return row is not None

    def list_anomalies(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        tenant_id: str = "default",
    ) -> list[AgentAnomaly]:
        conditions = ["tenant_id = ?"]
        params: list[Any] = [self._tenant(tenant_id)]
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM agent_anomalies {where} ORDER BY detected_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [self._row_to_anomaly(r) for r in rows]

    def resolve_anomaly(
        self,
        anomaly_id: int,
        resolved_by: str,
        status: str = AnomalyStatus.RESOLVED.value,
        tenant_id: str = "default",
    ) -> bool:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE agent_anomalies SET status = ?, resolved_at = ?, resolved_by = ? WHERE tenant_id = ? AND id = ?",
                (status, now, resolved_by, self._tenant(tenant_id), anomaly_id),
            )
        return cursor.rowcount > 0

    # ---- Row converters ----

    @staticmethod
    def _row_to_agent(row: sqlite3.Row) -> AIAgent:
        return AIAgent(
            agent_id=row["agent_id"],
            name=row["name"],
            agent_type=row["agent_type"],
            description=row["description"],
            owner=row["owner"],
            team=row["team"],
            department=row["department"],
            purpose=row["purpose"],
            provider=row["provider"],
            model=row["model"],
            version=row["version"],
            status=row["status"],
            risk_level=row["risk_level"],
            trust_score=row["trust_score"],
            daily_budget=row["daily_budget"],
            monthly_budget=row["monthly_budget"],
            average_cost=row["average_cost"],
            average_latency=row["average_latency"],
            success_rate=row["success_rate"],
            permissions=row["permissions"],
            connected_tools=row["connected_tools"],
            policies=row["policies"],
            approval_required=bool(row["approval_required"]),
            allowed_tools=row["allowed_tools"],
            allowed_resources=row["allowed_resources"],
            max_actions_per_hour=row["max_actions_per_hour"],
            total_actions=row["total_actions"],
            total_denied=row["total_denied"],
            total_anomalies=row["total_anomalies"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_active_at=row["last_active_at"],
            tenant_id=row["tenant_id"],
        )

    @staticmethod
    def _row_to_action(row: sqlite3.Row) -> AgentAction:
        return AgentAction(
            action_id=row["action_id"],
            agent_id=row["agent_id"],
            action_type=row["action_type"],
            action_summary=row["action_summary"],
            target_resource=row["target_resource"],
            inputs=row["inputs"],
            outputs=row["outputs"],
            reasoning=row["reasoning"],
            confidence_score=row["confidence_score"],
            policy_verdict=row["policy_verdict"],
            status=row["status"],
            duration_ms=row["duration_ms"],
            created_at=row["created_at"],
            tenant_id=row["tenant_id"],
            previous_hash=row["previous_hash"],
            entry_hash=row["entry_hash"],
        )

    @staticmethod
    def _row_to_policy(row: sqlite3.Row) -> AgentPolicy:
        return AgentPolicy(
            policy_id=row["id"],
            name=row["name"],
            description=row["description"],
            policy_type=row["policy_type"],
            target_agents=row["target_agents"],
            conditions=row["conditions"],
            effect=row["effect"],
            priority=row["priority"],
            enabled=row["enabled"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tenant_id=row["tenant_id"],
        )

    @staticmethod
    def _row_to_anomaly(row: sqlite3.Row) -> AgentAnomaly:
        return AgentAnomaly(
            anomaly_id=row["id"],
            agent_id=row["agent_id"],
            anomaly_type=row["anomaly_type"],
            description=row["description"],
            severity=row["severity"],
            evidence=row["evidence"],
            status=row["status"],
            detected_at=row["detected_at"],
            resolved_at=row["resolved_at"],
            resolved_by=row["resolved_by"],
            tenant_id=row["tenant_id"],
        )

    @property
    def placeholder(self) -> str:
        return "?"

    @staticmethod
    def _tenant(tenant_id: str | None) -> str:
        return str(tenant_id or "default").strip() or "default"
