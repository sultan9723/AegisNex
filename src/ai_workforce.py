"""AI Workforce — agent lifecycle, versions, prompts, permissions, knowledge,
executions, trust scoring, budget tracking, health monitoring, clone/pause/resume.

Transforms the legacy Agent Registry into a full AI Workforce system.
All operations are database-backed with zero placeholder data.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

_logger = logging.getLogger(__name__)

TABLE_AGENTS = "workforce_agents"
TABLE_VERSIONS = "workforce_agent_versions"
TABLE_PROMPTS = "workforce_prompt_versions"
TABLE_TOOL_PERMS = "workforce_tool_permissions"
TABLE_KNOWLEDGE = "workforce_knowledge_assignments"
TABLE_EXECUTIONS = "workforce_executions"
TABLE_HEALTH = "workforce_health_log"


class WorkforceExecutionBlocked(ValueError):
    """Raised when an agent is not allowed to execute a requested task."""

    def __init__(self, reason: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def new_id() -> str:
    return uuid.uuid4().hex[:24]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LifecycleStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    DECOMMISSIONED = "decommissioned"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class PromptRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AccessLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"


class ExecutionResult(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class WorkforceAgent:
    agent_id: str = ""
    name: str = ""
    description: str = ""
    agent_type: str = "general"
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    version: int = 1
    lifecycle_status: str = LifecycleStatus.DRAFT.value
    trust_score: float = 50.0
    confidence: float = 0.0
    daily_budget: float = 25.0
    monthly_budget: float = 750.0
    total_cost: float = 0.0
    success_rate: float = 100.0
    average_latency_ms: float = 0.0
    total_executions: int = 0
    health_status: str = HealthStatus.UNKNOWN.value
    health_last_checked: str | None = None
    tools: list[dict] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    owner: str = ""
    team: str = ""
    org_id: int | None = None
    team_id: int | None = None
    created_at: str = ""
    updated_at: str = ""
    last_active_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tools"] = self.tools if isinstance(self.tools, list) else json.loads(self.tools)
        d["permissions"] = self.permissions if isinstance(self.permissions, list) else json.loads(self.permissions)
        d["metadata"] = self.metadata if isinstance(self.metadata, dict) else json.loads(self.metadata)
        d["tags"] = self.tags if isinstance(self.tags, list) else json.loads(self.tags)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkforceAgent:
        valid = {k for k in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


@dataclass
class AgentVersion:
    id: int = 0
    agent_id: str = ""
    version: int = 1
    config_snapshot: dict = field(default_factory=dict)
    prompt_ids: list[str] = field(default_factory=list)
    change_summary: str = ""
    created_by: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentVersion:
        valid = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


@dataclass
class PromptVersion:
    prompt_id: str = ""
    agent_id: str = ""
    name: str = ""
    content: str = ""
    version: int = 1
    role: str = PromptRole.SYSTEM.value
    variables: list[str] = field(default_factory=list)
    hash: str = ""
    description: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["variables"] = self.variables if isinstance(self.variables, list) else json.loads(self.variables)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptVersion:
        valid = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


@dataclass
class ToolPermission:
    id: int = 0
    agent_id: str = ""
    tool_name: str = ""
    allowed: bool = True
    config: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["config"] = self.config if isinstance(self.config, dict) else json.loads(self.config)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolPermission:
        valid = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


@dataclass
class KnowledgeAssignment:
    id: int = 0
    agent_id: str = ""
    knowledge_source_id: str = ""
    knowledge_source_type: str = "collection"
    access_level: str = AccessLevel.READ_WRITE.value
    priority: int = 100
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeAssignment:
        valid = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


@dataclass
class WorkforceExecution:
    execution_id: str = ""
    agent_id: str = ""
    task: str = ""
    response: str = ""
    latency_ms: float = 0.0
    cost: float = 0.0
    confidence: float = 0.0
    tools_used: list[str] = field(default_factory=list)
    status: str = ExecutionResult.SUCCESS.value
    error: str = ""
    prompt_version_id: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tools_used"] = self.tools_used if isinstance(self.tools_used, list) else json.loads(self.tools_used)
        d["metadata"] = self.metadata if isinstance(self.metadata, dict) else json.loads(self.metadata)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkforceExecution:
        valid = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


@dataclass
class HealthRecord:
    id: int = 0
    agent_id: str = ""
    status: str = HealthStatus.HEALTHY.value
    check_type: str = "heartbeat"
    metric_value: float = 0.0
    details: dict = field(default_factory=dict)
    checked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["details"] = self.details if isinstance(self.details, dict) else json.loads(self.details)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HealthRecord:
        valid = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


def _ensure_table_agents(repo: Any) -> None:
    if repo is None:
        return
    if repo.table_exists(TABLE_AGENTS):
        _add_column_if_missing(repo, TABLE_AGENTS, "org_id", "INTEGER")
        _add_column_if_missing(repo, TABLE_AGENTS, "team_id", "INTEGER")
        return
    pkey = "INTEGER PRIMARY KEY AUTOINCREMENT" if repo.backend == "sqlite" else "SERIAL PRIMARY KEY"
    repo._execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_AGENTS} (
            id {pkey},
            agent_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            agent_type TEXT NOT NULL DEFAULT 'general',
            provider TEXT NOT NULL DEFAULT 'openai',
            model TEXT NOT NULL DEFAULT 'gpt-4o-mini',
            version INTEGER NOT NULL DEFAULT 1,
            lifecycle_status TEXT NOT NULL DEFAULT 'draft',
            trust_score REAL NOT NULL DEFAULT 50.0,
            confidence REAL NOT NULL DEFAULT 0.0,
            daily_budget REAL NOT NULL DEFAULT 25.0,
            monthly_budget REAL NOT NULL DEFAULT 750.0,
            total_cost REAL NOT NULL DEFAULT 0.0,
            success_rate REAL NOT NULL DEFAULT 100.0,
            average_latency_ms REAL NOT NULL DEFAULT 0.0,
            total_executions INTEGER NOT NULL DEFAULT 0,
            health_status TEXT NOT NULL DEFAULT 'unknown',
            health_last_checked TEXT,
            tools TEXT NOT NULL DEFAULT '[]',
            permissions TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{{}}',
            tags TEXT NOT NULL DEFAULT '[]',
            owner TEXT NOT NULL DEFAULT '',
            team TEXT NOT NULL DEFAULT '',
            org_id INTEGER,
            team_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_active_at TEXT
        )
    """)
    _add_column_if_missing(repo, TABLE_AGENTS, "org_id", "INTEGER")
    _add_column_if_missing(repo, TABLE_AGENTS, "team_id", "INTEGER")


def _table_columns(repo: Any, table: str) -> set[str]:
    try:
        if getattr(repo, "backend", "sqlite") == "sqlite":
            rows = repo._fetch_all(f"PRAGMA table_info({table})")
            return {str(row.get("name")) for row in rows}
    except Exception:
        return set()
    return set()


def _add_column_if_missing(repo: Any, table: str, column: str, ddl: str) -> None:
    if repo is None:
        return
    columns = _table_columns(repo, table)
    if columns and column not in columns:
        try:
            repo._execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        except Exception:
            _logger.debug("Could not add %s.%s", table, column, exc_info=True)


def _ensure_table_versions(repo: Any) -> None:
    if repo is None or repo.table_exists(TABLE_VERSIONS):
        return
    pkey = "INTEGER PRIMARY KEY AUTOINCREMENT" if repo.backend == "sqlite" else "SERIAL PRIMARY KEY"
    repo._execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_VERSIONS} (
            id {pkey},
            agent_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            config_snapshot TEXT NOT NULL DEFAULT '{{}}',
            prompt_ids TEXT NOT NULL DEFAULT '[]',
            change_summary TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(agent_id, version)
        )
    """)


def _ensure_table_prompts(repo: Any) -> None:
    if repo is None or repo.table_exists(TABLE_PROMPTS):
        return
    pkey = "INTEGER PRIMARY KEY AUTOINCREMENT" if repo.backend == "sqlite" else "SERIAL PRIMARY KEY"
    repo._execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_PROMPTS} (
            id {pkey},
            prompt_id TEXT UNIQUE NOT NULL,
            agent_id TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            role TEXT NOT NULL DEFAULT 'system',
            variables TEXT NOT NULL DEFAULT '[]',
            hash TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)


def _ensure_table_tool_perms(repo: Any) -> None:
    if repo is None or repo.table_exists(TABLE_TOOL_PERMS):
        return
    pkey = "INTEGER PRIMARY KEY AUTOINCREMENT" if repo.backend == "sqlite" else "SERIAL PRIMARY KEY"
    repo._execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_TOOL_PERMS} (
            id {pkey},
            agent_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 1,
            config TEXT NOT NULL DEFAULT '{{}}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(agent_id, tool_name)
        )
    """)


def _ensure_table_knowledge(repo: Any) -> None:
    if repo is None or repo.table_exists(TABLE_KNOWLEDGE):
        return
    pkey = "INTEGER PRIMARY KEY AUTOINCREMENT" if repo.backend == "sqlite" else "SERIAL PRIMARY KEY"
    repo._execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_KNOWLEDGE} (
            id {pkey},
            agent_id TEXT NOT NULL,
            knowledge_source_id TEXT NOT NULL,
            knowledge_source_type TEXT NOT NULL DEFAULT 'collection',
            access_level TEXT NOT NULL DEFAULT 'read_write',
            priority INTEGER NOT NULL DEFAULT 100,
            created_at TEXT NOT NULL,
            UNIQUE(agent_id, knowledge_source_id)
        )
    """)


def _ensure_table_executions(repo: Any) -> None:
    if repo is None or repo.table_exists(TABLE_EXECUTIONS):
        return
    pkey = "INTEGER PRIMARY KEY AUTOINCREMENT" if repo.backend == "sqlite" else "SERIAL PRIMARY KEY"
    repo._execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_EXECUTIONS} (
            id {pkey},
            execution_id TEXT UNIQUE NOT NULL,
            agent_id TEXT NOT NULL,
            task TEXT NOT NULL DEFAULT '',
            response TEXT NOT NULL DEFAULT '',
            latency_ms REAL NOT NULL DEFAULT 0.0,
            cost REAL NOT NULL DEFAULT 0.0,
            confidence REAL NOT NULL DEFAULT 0.0,
            tools_used TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'success',
            error TEXT NOT NULL DEFAULT '',
            prompt_version_id TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{{}}',
            created_at TEXT NOT NULL
        )
    """)


def _ensure_table_health(repo: Any) -> None:
    if repo is None or repo.table_exists(TABLE_HEALTH):
        return
    pkey = "INTEGER PRIMARY KEY AUTOINCREMENT" if repo.backend == "sqlite" else "SERIAL PRIMARY KEY"
    repo._execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_HEALTH} (
            id {pkey},
            agent_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'healthy',
            check_type TEXT NOT NULL DEFAULT 'heartbeat',
            metric_value REAL NOT NULL DEFAULT 0.0,
            details TEXT NOT NULL DEFAULT '{{}}',
            checked_at TEXT NOT NULL
        )
    """)


def ensure_all_tables(repo: Any) -> None:
    if repo is None:
        return
    _ensure_table_agents(repo)
    _ensure_table_versions(repo)
    _ensure_table_prompts(repo)
    _ensure_table_tool_perms(repo)
    _ensure_table_knowledge(repo)
    _ensure_table_executions(repo)
    _ensure_table_health(repo)


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _row_to_agent(row: dict[str, Any]) -> WorkforceAgent:
    agent = WorkforceAgent(
        agent_id=str(row.get("agent_id", "")),
        name=str(row.get("name", "")),
        description=str(row.get("description", "")),
        agent_type=str(row.get("agent_type", "general")),
        provider=str(row.get("provider", "openai")),
        model=str(row.get("model", "gpt-4o-mini")),
        version=int(row.get("version", 1)),
        lifecycle_status=str(row.get("lifecycle_status", "draft")),
        trust_score=float(row.get("trust_score", 50.0)),
        confidence=float(row.get("confidence", 0.0)),
        daily_budget=float(row.get("daily_budget", 25.0)),
        monthly_budget=float(row.get("monthly_budget", 750.0)),
        total_cost=float(row.get("total_cost", 0.0)),
        success_rate=float(row.get("success_rate", 100.0)),
        average_latency_ms=float(row.get("average_latency_ms", 0.0)),
        total_executions=int(row.get("total_executions", 0)),
        health_status=str(row.get("health_status", "unknown")),
        health_last_checked=row.get("health_last_checked"),
        owner=str(row.get("owner", "")),
        team=str(row.get("team", "")),
        org_id=int(row["org_id"]) if row.get("org_id") not in (None, "") else None,
        team_id=int(row["team_id"]) if row.get("team_id") not in (None, "") else None,
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        last_active_at=row.get("last_active_at"),
    )
    for col in ("tools", "permissions", "metadata", "tags"):
        val = row.get(col, "[]" if col in ("tools", "permissions", "tags") else "{}")
        parsed: Any = []
        if col in ("tools", "permissions", "tags"):
            parsed = json.loads(val) if isinstance(val, str) else val
        else:
            parsed = json.loads(val) if isinstance(val, str) else val
        setattr(agent, col, parsed)
    return agent


def _row_to_version(row: dict[str, Any]) -> AgentVersion:
    return AgentVersion(
        id=int(row.get("id", 0)),
        agent_id=str(row.get("agent_id", "")),
        version=int(row.get("version", 1)),
        config_snapshot=json.loads(row["config_snapshot"]) if isinstance(row.get("config_snapshot"), str) else (row.get("config_snapshot") or {}),
        prompt_ids=json.loads(row["prompt_ids"]) if isinstance(row.get("prompt_ids"), str) else (row.get("prompt_ids") or []),
        change_summary=str(row.get("change_summary", "")),
        created_by=str(row.get("created_by", "")),
        created_at=str(row.get("created_at", "")),
    )


def _row_to_prompt(row: dict[str, Any]) -> PromptVersion:
    return PromptVersion(
        prompt_id=str(row.get("prompt_id", "")),
        agent_id=str(row.get("agent_id", "")),
        name=str(row.get("name", "")),
        content=str(row.get("content", "")),
        version=int(row.get("version", 1)),
        role=str(row.get("role", "system")),
        variables=json.loads(row["variables"]) if isinstance(row.get("variables"), str) else (row.get("variables") or []),
        hash=str(row.get("hash", "")),
        description=str(row.get("description", "")),
        created_at=str(row.get("created_at", "")),
    )


def _row_to_tool_perm(row: dict[str, Any]) -> ToolPermission:
    return ToolPermission(
        id=int(row.get("id", 0)),
        agent_id=str(row.get("agent_id", "")),
        tool_name=str(row.get("tool_name", "")),
        allowed=bool(row.get("allowed", True)),
        config=json.loads(row["config"]) if isinstance(row.get("config"), str) else (row.get("config") or {}),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
    )


def _row_to_knowledge(row: dict[str, Any]) -> KnowledgeAssignment:
    return KnowledgeAssignment(
        id=int(row.get("id", 0)),
        agent_id=str(row.get("agent_id", "")),
        knowledge_source_id=str(row.get("knowledge_source_id", "")),
        knowledge_source_type=str(row.get("knowledge_source_type", "collection")),
        access_level=str(row.get("access_level", "read_write")),
        priority=int(row.get("priority", 100)),
        created_at=str(row.get("created_at", "")),
    )


def _row_to_execution(row: dict[str, Any]) -> WorkforceExecution:
    return WorkforceExecution(
        execution_id=str(row.get("execution_id", "")),
        agent_id=str(row.get("agent_id", "")),
        task=str(row.get("task", "")),
        response=str(row.get("response", "")),
        latency_ms=float(row.get("latency_ms", 0.0)),
        cost=float(row.get("cost", 0.0)),
        confidence=float(row.get("confidence", 0.0)),
        tools_used=json.loads(row["tools_used"]) if isinstance(row.get("tools_used"), str) else (row.get("tools_used") or []),
        status=str(row.get("status", "success")),
        error=str(row.get("error", "")),
        prompt_version_id=str(row.get("prompt_version_id", "")),
        metadata=json.loads(row["metadata"]) if isinstance(row.get("metadata"), str) else (row.get("metadata") or {}),
        created_at=str(row.get("created_at", "")),
    )


def _row_to_health(row: dict[str, Any]) -> HealthRecord:
    return HealthRecord(
        id=int(row.get("id", 0)),
        agent_id=str(row.get("agent_id", "")),
        status=str(row.get("status", "healthy")),
        check_type=str(row.get("check_type", "heartbeat")),
        metric_value=float(row.get("metric_value", 0.0)),
        details=json.loads(row["details"]) if isinstance(row.get("details"), str) else (row.get("details") or {}),
        checked_at=str(row.get("checked_at", "")),
    )


# ---------------------------------------------------------------------------
# Trust score calculation
# ---------------------------------------------------------------------------


def _calculate_trust_score(executions: list[WorkforceExecution], current_score: float = 50.0) -> float:
    if not executions:
        return current_score
    total = len(executions)
    outcome_score = sum(_execution_outcome_score(e) for e in executions) / total
    avg_confidence = _calculate_agent_confidence(executions)
    policy_penalty = sum(_policy_penalty(e) for e in executions) / total
    stale_penalty = _staleness_penalty(executions)

    raw = (outcome_score * 65.0) + (avg_confidence * 25.0) + 10.0
    raw -= policy_penalty + stale_penalty
    return round(max(0.0, min(100.0, raw)), 1)


def _calculate_agent_confidence(executions: list[WorkforceExecution]) -> float:
    if not executions:
        return 0.0
    values = [_execution_confidence(e) for e in executions]
    return round(sum(values) / len(values), 4)


def _execution_confidence(execution: WorkforceExecution) -> float:
    if execution.confidence > 0:
        confidence = execution.confidence
    elif execution.status == ExecutionResult.SUCCESS.value:
        confidence = 0.75
    elif execution.status == ExecutionResult.FAILED.value:
        confidence = 0.25
    elif execution.status == ExecutionResult.TIMEOUT.value:
        confidence = 0.15
    else:
        confidence = 0.1

    penalty = _policy_penalty(execution) / 100.0
    return round(max(0.0, min(1.0, confidence - penalty)), 4)


def _execution_outcome_score(execution: WorkforceExecution) -> float:
    if execution.status == ExecutionResult.SUCCESS.value:
        return 1.0
    if execution.status == ExecutionResult.FAILED.value:
        return 0.25
    if execution.status == ExecutionResult.TIMEOUT.value:
        return 0.15
    return 0.0


def _policy_penalty(execution: WorkforceExecution) -> float:
    verdicts = _policy_verdicts(execution.metadata)
    penalty = 0.0
    for verdict in verdicts:
        if verdict == "approval_required":
            penalty += 8.0
        elif verdict == "forbidden":
            penalty += 20.0
    return penalty


def _policy_verdicts(metadata: dict) -> list[str]:
    candidates: list[Any] = []
    for key in ("policy_verdict", "policy_verdicts", "policy", "policy_evaluation"):
        value = metadata.get(key)
        if value is not None:
            candidates.append(value)
    candidates.extend(metadata.get("policy_decisions", []) or [])

    verdicts: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, str):
            verdicts.append(candidate.strip().lower())
        elif isinstance(candidate, dict):
            value = candidate.get("verdict") or candidate.get("policy_verdict")
            if value is not None:
                verdicts.append(str(value).strip().lower())
        elif isinstance(candidate, list):
            verdicts.extend(_policy_verdicts({"policy_verdicts": candidate}))
    return verdicts


def _staleness_penalty(executions: list[WorkforceExecution]) -> float:
    timestamps: list[datetime] = []
    for execution in executions:
        if not execution.created_at:
            continue
        try:
            timestamps.append(datetime.fromisoformat(execution.created_at.replace("Z", "+00:00")))
        except ValueError:
            continue
    if not timestamps:
        return 0.0
    newest = max(timestamps)
    age_days = (datetime.now(UTC) - newest).total_seconds() / 86400
    if age_days <= 7:
        return 0.0
    return min(15.0, (age_days - 7) * 0.25)


def _calculate_success_rate(executions: list[WorkforceExecution]) -> float:
    if not executions:
        return 100.0
    successes = sum(1 for e in executions if e.status == "success")
    return round(successes / len(executions) * 100.0, 1)


def _calculate_avg_latency(executions: list[WorkforceExecution]) -> float:
    if not executions:
        return 0.0
    return sum(e.latency_ms for e in executions) / len(executions)


# ---------------------------------------------------------------------------
# Workforce Manager
# ---------------------------------------------------------------------------


class WorkforceManager:
    """Manages the AI workforce: agent lifecycle, versions, prompts, permissions,
    knowledge assignments, execution history, trust scoring, budget, health."""

    def __init__(self, repo: Any) -> None:
        self.repo = repo
        self.p = getattr(repo, "placeholder", "?")
        ensure_all_tables(repo)

    def _supports_column(self, table: str, column: str) -> bool:
        columns = _table_columns(self.repo, table)
        return not columns or column in columns

    def _agent_insert_columns(self) -> list[str]:
        columns = [
            "agent_id", "name", "description", "agent_type", "provider", "model", "version",
            "lifecycle_status", "trust_score", "confidence", "daily_budget", "monthly_budget",
            "total_cost", "success_rate", "average_latency_ms", "total_executions",
            "health_status", "health_last_checked", "tools", "permissions", "metadata", "tags",
            "owner", "team",
        ]
        if self._supports_column(TABLE_AGENTS, "org_id"):
            columns.append("org_id")
        if self._supports_column(TABLE_AGENTS, "team_id"):
            columns.append("team_id")
        columns.extend(["created_at", "updated_at", "last_active_at"])
        return columns

    def _agent_values(self, agent: WorkforceAgent) -> list[Any]:
        values: list[Any] = [
            agent.agent_id, agent.name, agent.description, agent.agent_type,
            agent.provider, agent.model, agent.version,
            agent.lifecycle_status, agent.trust_score, agent.confidence,
            agent.daily_budget, agent.monthly_budget,
            agent.total_cost, agent.success_rate, agent.average_latency_ms,
            agent.total_executions,
            agent.health_status, agent.health_last_checked,
            json.dumps(agent.tools), json.dumps(agent.permissions),
            json.dumps(agent.metadata), json.dumps(agent.tags),
            agent.owner, agent.team,
        ]
        if self._supports_column(TABLE_AGENTS, "org_id"):
            values.append(agent.org_id)
        if self._supports_column(TABLE_AGENTS, "team_id"):
            values.append(agent.team_id)
        values.extend([agent.created_at, agent.updated_at, agent.last_active_at])
        return values

    # ---- Agent CRUD ----

    def register_agent(self, agent: WorkforceAgent) -> WorkforceAgent:
        if not agent.agent_id:
            agent.agent_id = new_id()
        now = utc_now()
        agent.created_at = now
        agent.updated_at = now
        if not agent.lifecycle_status:
            agent.lifecycle_status = LifecycleStatus.DRAFT.value
        ensure_all_tables(self.repo)
        columns = self._agent_insert_columns()
        placeholders = ",".join([self.p] * len(columns))
        self.repo._execute(
            f"INSERT INTO {TABLE_AGENTS} ({','.join(columns)}) VALUES ({placeholders})",
            tuple(self._agent_values(agent)),
        )
        return agent

    def get_agent(self, agent_id: str) -> WorkforceAgent | None:
        ensure_all_tables(self.repo)
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_AGENTS} WHERE agent_id = {self.p}", (agent_id,)
        )
        if not rows:
            return None
        return _row_to_agent(rows[0])

    def list_agents(
        self,
        lifecycle_status: str | None = None,
        agent_type: str | None = None,
        search: str | None = None,
        org_id: int | None = None,
        include_unassigned: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkforceAgent]:
        ensure_all_tables(self.repo)
        conditions: list[str] = []
        params: list[Any] = []
        if lifecycle_status:
            conditions.append(f"lifecycle_status = {self.p}")
            params.append(lifecycle_status)
        if agent_type:
            conditions.append(f"agent_type = {self.p}")
            params.append(agent_type)
        if search:
            conditions.append(f"(name LIKE {self.p} OR description LIKE {self.p})")
            search_pat = f"%{search}%"
            params.append(search_pat)
            params.append(search_pat)
        if org_id is not None and self._supports_column(TABLE_AGENTS, "org_id"):
            if include_unassigned:
                conditions.append(f"(org_id = {self.p} OR org_id IS NULL)")
            else:
                conditions.append(f"org_id = {self.p}")
            params.append(org_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_AGENTS}{where} ORDER BY updated_at DESC LIMIT {self.p} OFFSET {self.p}",
            tuple(params + [limit, offset]),
        )
        return [_row_to_agent(r) for r in rows]

    def count_agents(
        self,
        lifecycle_status: str | None = None,
        org_id: int | None = None,
        include_unassigned: bool = True,
    ) -> int:
        conditions: list[str] = []
        params: list[Any] = []
        if lifecycle_status:
            conditions.append(f"lifecycle_status = {self.p}")
            params.append(lifecycle_status)
        if org_id is not None and self._supports_column(TABLE_AGENTS, "org_id"):
            if include_unassigned:
                conditions.append(f"(org_id = {self.p} OR org_id IS NULL)")
            else:
                conditions.append(f"org_id = {self.p}")
            params.append(org_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.repo._fetch_all(
            f"SELECT COUNT(*) as cnt FROM {TABLE_AGENTS}{where}", tuple(params)
        )
        return rows[0]["cnt"] if rows else 0

    def update_agent(self, agent: WorkforceAgent) -> bool:
        existing = self.get_agent(agent.agent_id)
        if not existing:
            return False
        agent.updated_at = utc_now()
        org_update = ""
        values: list[Any] = [
            agent.name, agent.description, agent.agent_type,
            agent.provider, agent.model, agent.version,
            agent.lifecycle_status, agent.trust_score, agent.confidence,
            agent.daily_budget, agent.monthly_budget,
            agent.total_cost, agent.success_rate, agent.average_latency_ms,
            agent.total_executions,
            agent.health_status, agent.health_last_checked,
            json.dumps(agent.tools), json.dumps(agent.permissions),
            json.dumps(agent.metadata), json.dumps(agent.tags),
            agent.owner, agent.team,
        ]
        if self._supports_column(TABLE_AGENTS, "org_id"):
            org_update += f", org_id={self.p}"
            values.append(agent.org_id)
        if self._supports_column(TABLE_AGENTS, "team_id"):
            org_update += f", team_id={self.p}"
            values.append(agent.team_id)
        values.extend([agent.updated_at, agent.last_active_at, agent.agent_id])
        self.repo._execute(
            f"""UPDATE {TABLE_AGENTS} SET
                name={self.p}, description={self.p}, agent_type={self.p},
                provider={self.p}, model={self.p}, version={self.p},
                lifecycle_status={self.p}, trust_score={self.p}, confidence={self.p},
                daily_budget={self.p}, monthly_budget={self.p},
                total_cost={self.p}, success_rate={self.p}, average_latency_ms={self.p},
                total_executions={self.p},
                health_status={self.p}, health_last_checked={self.p},
                tools={self.p}, permissions={self.p}, metadata={self.p}, tags={self.p},
                owner={self.p}, team={self.p}{org_update}, updated_at={self.p}, last_active_at={self.p}
            WHERE agent_id={self.p}""",
            tuple(values),
        )
        return True

    def delete_agent(self, agent_id: str) -> bool:
        ensure_all_tables(self.repo)
        existing = self.get_agent(agent_id)
        if not existing:
            return False
        self.repo._execute(
            f"DELETE FROM {TABLE_AGENTS} WHERE agent_id = {self.p}", (agent_id,)
        )
        # Cascade clean related data
        for table in (TABLE_VERSIONS, TABLE_TOOL_PERMS, TABLE_KNOWLEDGE, TABLE_EXECUTIONS, TABLE_HEALTH):
            self.repo._execute(
                f"DELETE FROM {table} WHERE agent_id = {self.p}", (agent_id,)
            )
        return True

    # ---- Lifecycle ----

    def activate_agent(self, agent_id: str) -> WorkforceAgent | None:
        agent = self.get_agent(agent_id)
        if not agent:
            return None
        if agent.lifecycle_status in (LifecycleStatus.ARCHIVED.value, LifecycleStatus.DECOMMISSIONED.value):
            return None
        agent.lifecycle_status = LifecycleStatus.ACTIVE.value
        agent.last_active_at = utc_now()
        self.update_agent(agent)
        return agent

    def pause_agent(self, agent_id: str) -> WorkforceAgent | None:
        agent = self.get_agent(agent_id)
        if not agent or agent.lifecycle_status != LifecycleStatus.ACTIVE.value:
            return None
        agent.lifecycle_status = LifecycleStatus.PAUSED.value
        self.update_agent(agent)
        return agent

    def resume_agent(self, agent_id: str) -> WorkforceAgent | None:
        agent = self.get_agent(agent_id)
        if not agent or agent.lifecycle_status != LifecycleStatus.PAUSED.value:
            return None
        agent.lifecycle_status = LifecycleStatus.ACTIVE.value
        agent.last_active_at = utc_now()
        self.update_agent(agent)
        return agent

    def archive_agent(self, agent_id: str) -> WorkforceAgent | None:
        agent = self.get_agent(agent_id)
        if not agent:
            return None
        agent.lifecycle_status = LifecycleStatus.ARCHIVED.value
        self.update_agent(agent)
        return agent

    # ---- Clone ----

    def clone_agent(
        self,
        agent_id: str,
        new_name: str | None = None,
        new_agent_id: str | None = None,
    ) -> WorkforceAgent | None:
        original = self.get_agent(agent_id)
        if not original:
            return None
        clone = WorkforceAgent(
            agent_id=new_agent_id or new_id(),
            name=new_name or f"{original.name} (Clone)",
            description=original.description,
            agent_type=original.agent_type,
            provider=original.provider,
            model=original.model,
            version=1,
            lifecycle_status=LifecycleStatus.DRAFT.value,
            trust_score=original.trust_score,
            confidence=original.confidence,
            daily_budget=original.daily_budget,
            monthly_budget=original.monthly_budget,
            tools=list(original.tools),
            permissions=list(original.permissions),
            metadata=dict(original.metadata),
            tags=list(original.tags),
            owner=original.owner,
            team=original.team,
            org_id=original.org_id,
            team_id=original.team_id,
        )
        self.register_agent(clone)

        # Clone tool permissions
        for perm in self.get_tool_permissions(agent_id):
            self.set_tool_permission(clone.agent_id, perm.tool_name, perm.allowed, perm.config)

        # Clone knowledge assignments
        for ka in self.list_knowledge_assignments(agent_id):
            self.assign_knowledge(clone.agent_id, ka.knowledge_source_id, ka.knowledge_source_type, ka.access_level, ka.priority)

        return clone

    # ---- Versions ----

    def create_agent_version(
        self,
        agent_id: str,
        change_summary: str = "",
        created_by: str = "",
    ) -> AgentVersion | None:
        agent = self.get_agent(agent_id)
        if not agent:
            return None

        rows = self.repo._fetch_all(
            f"SELECT MAX(version) as mv FROM {TABLE_VERSIONS} WHERE agent_id = {self.p}",
            (agent_id,),
        )
        next_ver = (rows[0]["mv"] or 0) + 1 if rows else 1

        version = AgentVersion(
            agent_id=agent_id,
            version=next_ver,
            config_snapshot=agent.to_dict(),
            prompt_ids=[],
            change_summary=change_summary,
            created_by=created_by,
            created_at=utc_now(),
        )
        self.repo._execute(
            f"""INSERT INTO {TABLE_VERSIONS}
                (agent_id, version, config_snapshot, prompt_ids, change_summary, created_by, created_at)
            VALUES ({self.p},{self.p},{self.p},{self.p},{self.p},{self.p},{self.p})""",
            (
                version.agent_id, version.version,
                json.dumps(version.config_snapshot), json.dumps(version.prompt_ids),
                version.change_summary, version.created_by, version.created_at,
            ),
        )
        return version

    def list_agent_versions(self, agent_id: str) -> list[AgentVersion]:
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_VERSIONS} WHERE agent_id = {self.p} ORDER BY version DESC",
            (agent_id,),
        )
        return [_row_to_version(r) for r in rows]

    def get_agent_version(self, agent_id: str, version: int) -> AgentVersion | None:
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_VERSIONS} WHERE agent_id = {self.p} AND version = {self.p}",
            (agent_id, version),
        )
        if not rows:
            return None
        return _row_to_version(rows[0])

    def restore_agent_version(self, agent_id: str, version: int) -> WorkforceAgent | None:
        agent = self.get_agent(agent_id)
        snap = self.get_agent_version(agent_id, version)
        if not agent or not snap:
            return None
        config = snap.config_snapshot
        for key in ("agent_id", "created_at", "updated_at", "last_active_at", "lifecycle_status"):
            config.pop(key, None)
        for key, val in config.items():
            if hasattr(agent, key):
                setattr(agent, key, val)
        agent.version += 1
        agent.updated_at = utc_now()
        self.update_agent(agent)
        return agent

    # ---- Prompt Versions ----

    def save_prompt_version(
        self,
        agent_id: str,
        name: str,
        content: str,
        role: str = PromptRole.SYSTEM.value,
        variables: list[str] | None = None,
        description: str = "",
    ) -> PromptVersion:
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        prompt_id = f"prompt_{new_id()}"

        rows = self.repo._fetch_all(
            f"SELECT MAX(version) as mv FROM {TABLE_PROMPTS} WHERE agent_id = {self.p} AND name = {self.p}",
            (agent_id, name),
        )
        next_ver = (rows[0]["mv"] or 0) + 1 if rows else 1

        prompt = PromptVersion(
            prompt_id=prompt_id,
            agent_id=agent_id,
            name=name,
            content=content,
            version=next_ver,
            role=role,
            variables=variables or [],
            hash=content_hash,
            description=description,
            created_at=utc_now(),
        )
        self.repo._execute(
            f"""INSERT INTO {TABLE_PROMPTS}
                (prompt_id, agent_id, name, content, version, role, variables, hash, description, created_at)
            VALUES ({self.p},{self.p},{self.p},{self.p},{self.p},{self.p},{self.p},{self.p},{self.p},{self.p})""",
            (
                prompt.prompt_id, prompt.agent_id, prompt.name, prompt.content,
                prompt.version, prompt.role, json.dumps(prompt.variables),
                prompt.hash, prompt.description, prompt.created_at,
            ),
        )
        return prompt

    def get_prompt_version(self, prompt_id: str) -> PromptVersion | None:
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_PROMPTS} WHERE prompt_id = {self.p}", (prompt_id,)
        )
        if not rows:
            return None
        return _row_to_prompt(rows[0])

    def list_prompt_versions(
        self, agent_id: str | None = None, name: str | None = None,
    ) -> list[PromptVersion]:
        conditions: list[str] = []
        params: list[Any] = []
        if agent_id:
            conditions.append(f"agent_id = {self.p}")
            params.append(agent_id)
        if name:
            conditions.append(f"name = {self.p}")
            params.append(name)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_PROMPTS}{where} ORDER BY created_at DESC",
            tuple(params),
        )
        return [_row_to_prompt(r) for r in rows]

    # ---- Tool Permissions ----

    def set_tool_permission(
        self, agent_id: str, tool_name: str, allowed: bool = True, config: dict | None = None,
    ) -> ToolPermission:
        now = utc_now()
        existing = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_TOOL_PERMS} WHERE agent_id = {self.p} AND tool_name = {self.p}",
            (agent_id, tool_name),
        )
        perm = ToolPermission(
            agent_id=agent_id, tool_name=tool_name, allowed=allowed,
            config=config or {}, created_at=now, updated_at=now,
        )
        if existing:
            self.repo._execute(
                f"""UPDATE {TABLE_TOOL_PERMS} SET allowed={self.p}, config={self.p}, updated_at={self.p}
                WHERE agent_id={self.p} AND tool_name={self.p}""",
                (int(allowed), json.dumps(config or {}), now, agent_id, tool_name),
            )
        else:
            self.repo._execute(
                f"""INSERT INTO {TABLE_TOOL_PERMS}
                    (agent_id, tool_name, allowed, config, created_at, updated_at)
                VALUES ({self.p},{self.p},{self.p},{self.p},{self.p},{self.p})""",
                (agent_id, tool_name, int(allowed), json.dumps(config or {}), now, now),
            )
        return perm

    def get_tool_permissions(self, agent_id: str) -> list[ToolPermission]:
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_TOOL_PERMS} WHERE agent_id = {self.p} ORDER BY tool_name",
            (agent_id,),
        )
        return [_row_to_tool_perm(r) for r in rows]

    def delete_tool_permission(self, agent_id: str, tool_name: str) -> bool:
        self.repo._execute(
            f"DELETE FROM {TABLE_TOOL_PERMS} WHERE agent_id = {self.p} AND tool_name = {self.p}",
            (agent_id, tool_name),
        )
        return True

    # ---- Knowledge Assignments ----

    def assign_knowledge(
        self,
        agent_id: str,
        knowledge_source_id: str,
        source_type: str = "collection",
        access_level: str = AccessLevel.READ_WRITE.value,
        priority: int = 100,
    ) -> KnowledgeAssignment:
        ka = KnowledgeAssignment(
            agent_id=agent_id,
            knowledge_source_id=knowledge_source_id,
            knowledge_source_type=source_type,
            access_level=access_level,
            priority=priority,
            created_at=utc_now(),
        )
        self.repo._execute(
            f"""INSERT OR REPLACE INTO {TABLE_KNOWLEDGE}
                (agent_id, knowledge_source_id, knowledge_source_type, access_level, priority, created_at)
            VALUES ({self.p},{self.p},{self.p},{self.p},{self.p},{self.p})""",
            (ka.agent_id, ka.knowledge_source_id, ka.knowledge_source_type,
             ka.access_level, ka.priority, ka.created_at),
        )
        return ka

    def list_knowledge_assignments(self, agent_id: str) -> list[KnowledgeAssignment]:
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_KNOWLEDGE} WHERE agent_id = {self.p} ORDER BY priority ASC",
            (agent_id,),
        )
        return [_row_to_knowledge(r) for r in rows]

    def remove_knowledge_assignment(self, agent_id: str, knowledge_source_id: str) -> bool:
        self.repo._execute(
            f"DELETE FROM {TABLE_KNOWLEDGE} WHERE agent_id = {self.p} AND knowledge_source_id = {self.p}",
            (agent_id, knowledge_source_id),
        )
        return True

    # ---- Execution History ----

    def record_execution(self, execution: WorkforceExecution) -> WorkforceExecution:
        if not execution.execution_id:
            execution.execution_id = f"exec_{new_id()}"
        execution.created_at = utc_now()
        if execution.confidence <= 0:
            execution.confidence = _execution_confidence(execution)

        self.repo._execute(
            f"""INSERT INTO {TABLE_EXECUTIONS}
                (execution_id, agent_id, task, response, latency_ms, cost, confidence,
                 tools_used, status, error, prompt_version_id, metadata, created_at)
            VALUES ({self.p},{self.p},{self.p},{self.p},{self.p},{self.p},{self.p},
                    {self.p},{self.p},{self.p},{self.p},{self.p},{self.p})""",
            (
                execution.execution_id, execution.agent_id, execution.task,
                execution.response, execution.latency_ms, execution.cost,
                execution.confidence, json.dumps(execution.tools_used),
                execution.status, execution.error, execution.prompt_version_id,
                json.dumps(execution.metadata), execution.created_at,
            ),
        )

        # Update agent aggregate stats
        agent = self.get_agent(execution.agent_id)
        if agent:
            recent = self.list_executions(execution.agent_id, limit=100)
            agent.total_executions = len(recent)
            agent.total_cost += execution.cost
            agent.success_rate = _calculate_success_rate(recent)
            agent.average_latency_ms = _calculate_avg_latency(recent)
            agent.last_active_at = utc_now()
            agent.confidence = _calculate_agent_confidence(recent)
            agent.trust_score = _calculate_trust_score(recent, agent.trust_score)
            self.update_agent(agent)

        return execution

    def list_executions(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkforceExecution]:
        conditions: list[str] = []
        params: list[Any] = []
        if agent_id:
            conditions.append(f"agent_id = {self.p}")
            params.append(agent_id)
        if status:
            conditions.append(f"status = {self.p}")
            params.append(status)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_EXECUTIONS}{where} ORDER BY created_at DESC LIMIT {self.p} OFFSET {self.p}",
            tuple(params + [limit, offset]),
        )
        return [_row_to_execution(r) for r in rows]

    def get_execution_stats(self, agent_id: str | None = None) -> dict[str, Any]:
        params: list[Any] = []
        where = ""
        if agent_id:
            where = f" WHERE agent_id = {self.p}"
            params.append(agent_id)

        rows = self.repo._fetch_all(
            f"""SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failures,
                AVG(latency_ms) as avg_latency,
                AVG(cost) as avg_cost,
                AVG(confidence) as avg_confidence,
                SUM(cost) as total_cost
            FROM {TABLE_EXECUTIONS}{where}""",
            tuple(params),
        ) if agent_id else self.repo._fetch_all(
            f"""SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failures,
                AVG(latency_ms) as avg_latency,
                AVG(cost) as avg_cost,
                AVG(confidence) as avg_confidence,
                SUM(cost) as total_cost
            FROM {TABLE_EXECUTIONS}""",
        )
        if not rows:
            return {"total": 0, "successes": 0, "failures": 0, "avg_latency": 0, "avg_cost": 0, "avg_confidence": 0, "total_cost": 0}
        r = rows[0]
        return {
            "total": r.get("total", 0),
            "successes": r.get("successes", 0),
            "failures": r.get("failures", 0),
            "avg_latency": round(float(r.get("avg_latency") or 0), 1),
            "avg_cost": round(float(r.get("avg_cost") or 0), 6),
            "avg_confidence": round(float(r.get("avg_confidence") or 0), 3),
            "total_cost": round(float(r.get("total_cost") or 0), 6),
        }

    # ---- Health ----

    def record_health_check(
        self,
        agent_id: str,
        status: str = HealthStatus.HEALTHY.value,
        check_type: str = "heartbeat",
        metric_value: float = 0.0,
        details: dict | None = None,
    ) -> HealthRecord:
        record = HealthRecord(
            agent_id=agent_id, status=status, check_type=check_type,
            metric_value=metric_value, details=details or {},
            checked_at=utc_now(),
        )
        self.repo._execute(
            f"""INSERT INTO {TABLE_HEALTH}
                (agent_id, status, check_type, metric_value, details, checked_at)
            VALUES ({self.p},{self.p},{self.p},{self.p},{self.p},{self.p})""",
            (record.agent_id, record.status, record.check_type,
             record.metric_value, json.dumps(record.details), record.checked_at),
        )

        # Update agent health status
        agent = self.get_agent(agent_id)
        if agent:
            agent.health_status = status
            agent.health_last_checked = record.checked_at
            self.update_agent(agent)

        return record

    def get_health_history(
        self, agent_id: str, limit: int = 50,
    ) -> list[HealthRecord]:
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_HEALTH} WHERE agent_id = {self.p} ORDER BY checked_at DESC LIMIT {self.p}",
            (agent_id, limit),
        )
        return [_row_to_health(r) for r in rows]

    def get_latest_health(self, agent_id: str) -> HealthRecord | None:
        rows = self.repo._fetch_all(
            f"SELECT * FROM {TABLE_HEALTH} WHERE agent_id = {self.p} ORDER BY checked_at DESC LIMIT 1",
            (agent_id,),
        )
        if not rows:
            return None
        return _row_to_health(rows[0])

    # ---- Budget ----

    def get_budget_usage(self, agent_id: str) -> dict[str, Any]:
        agent = self.get_agent(agent_id)
        if not agent:
            return {"daily_used": 0, "monthly_used": 0, "daily_budget": 0, "monthly_budget": 0, "remaining_daily": 0, "remaining_monthly": 0}

        today = utc_now()[:10]
        month_start = utc_now()[:7]

        daily_rows = self.repo._fetch_all(
            f"SELECT SUM(cost) as total FROM {TABLE_EXECUTIONS} WHERE agent_id={self.p} AND created_at LIKE {self.p}",
            (agent_id, f"{today}%"),
        )
        monthly_rows = self.repo._fetch_all(
            f"SELECT SUM(cost) as total FROM {TABLE_EXECUTIONS} WHERE agent_id={self.p} AND created_at LIKE {self.p}",
            (agent_id, f"{month_start}%"),
        )

        daily_used = round(float(daily_rows[0]["total"] or 0), 6) if daily_rows else 0
        monthly_used = round(float(monthly_rows[0]["total"] or 0), 6) if monthly_rows else 0

        return {
            "daily_used": daily_used,
            "monthly_used": monthly_used,
            "daily_budget": agent.daily_budget,
            "monthly_budget": agent.monthly_budget,
            "remaining_daily": round(agent.daily_budget - daily_used, 6),
            "remaining_monthly": round(agent.monthly_budget - monthly_used, 6),
            "daily_exceeded": daily_used >= agent.daily_budget,
            "monthly_exceeded": monthly_used >= agent.monthly_budget,
        }

    def check_budget_available(self, agent_id: str, estimated_cost: float = 0.0) -> dict[str, Any]:
        usage = self.get_budget_usage(agent_id)
        projected_daily = float(usage.get("daily_used", 0)) + max(0.0, estimated_cost)
        projected_monthly = float(usage.get("monthly_used", 0)) + max(0.0, estimated_cost)
        daily_budget = float(usage.get("daily_budget", 0))
        monthly_budget = float(usage.get("monthly_budget", 0))
        allowed = projected_daily <= daily_budget and projected_monthly <= monthly_budget
        return {
            **usage,
            "estimated_cost": estimated_cost,
            "projected_daily": round(projected_daily, 6),
            "projected_monthly": round(projected_monthly, 6),
            "allowed": allowed,
            "reason": "" if allowed else "budget_exceeded",
        }

    def get_allowed_tool_names(self, agent_id: str) -> set[str]:
        perms = self.get_tool_permissions(agent_id)
        explicit = {p.tool_name for p in perms if p.allowed}
        denied = {p.tool_name for p in perms if not p.allowed}
        agent = self.get_agent(agent_id)
        configured = set()
        if agent:
            for item in agent.tools:
                if isinstance(item, dict):
                    name = item.get("name")
                    if name:
                        configured.add(str(name))
                elif item:
                    configured.add(str(item))
        return (explicit or configured) - denied

    def require_tool_allowed(self, agent_id: str, tool_name: str) -> None:
        if tool_name not in self.get_allowed_tool_names(agent_id):
            raise WorkforceExecutionBlocked("tool_not_allowed", {"tool": tool_name})

    def get_readable_knowledge_sources(self, agent_id: str) -> list[KnowledgeAssignment]:
        readable = {AccessLevel.READ.value, AccessLevel.READ_WRITE.value}
        return [k for k in self.list_knowledge_assignments(agent_id) if k.access_level in readable]

    # ---- Workforce Stats ----

    def get_workforce_stats(self, org_id: int | None = None) -> dict[str, Any]:
        agents = self.list_agents(org_id=org_id) if org_id is not None else self.list_agents()
        active = [a for a in agents if a.lifecycle_status == LifecycleStatus.ACTIVE.value]
        paused = [a for a in agents if a.lifecycle_status == LifecycleStatus.PAUSED.value]
        draft = [a for a in agents if a.lifecycle_status == LifecycleStatus.DRAFT.value]

        type_counts: dict[str, int] = {}
        for a in agents:
            type_counts[a.agent_type] = type_counts.get(a.agent_type, 0) + 1

        health_counts: dict[str, int] = {}
        for a in agents:
            health_counts[a.health_status] = health_counts.get(a.health_status, 0) + 1

        avg_trust = round(sum(a.trust_score for a in agents) / max(len(agents), 1), 1)

        if org_id is None:
            exec_stats = self.get_execution_stats()
        else:
            scoped_execs: list[WorkforceExecution] = []
            for agent in agents:
                scoped_execs.extend(self.list_executions(agent_id=agent.agent_id, limit=500))
            exec_stats = {
                "total": len(scoped_execs),
                "successes": sum(1 for e in scoped_execs if e.status == ExecutionResult.SUCCESS.value),
                "failures": sum(1 for e in scoped_execs if e.status in {ExecutionResult.FAILED.value, ExecutionResult.ERROR.value, ExecutionResult.TIMEOUT.value}),
                "total_cost": round(sum(e.cost for e in scoped_execs), 6),
            }

        return {
            "total_agents": len(agents),
            "active_agents": len(active),
            "paused_agents": len(paused),
            "draft_agents": len(draft),
            "by_type": type_counts,
            "by_health": health_counts,
            "avg_trust_score": avg_trust,
            "total_executions": exec_stats["total"],
            "total_successes": exec_stats["successes"],
            "total_failures": exec_stats["failures"],
            "total_cost": exec_stats["total_cost"],
            "avg_success_rate": round(exec_stats["successes"] / max(exec_stats["total"], 1) * 100, 1),
        }

    def _knowledge_doc_matches(self, assignment: KnowledgeAssignment, doc: Any) -> bool:
        source_id = assignment.knowledge_source_id.strip()
        if not source_id or source_id == "*":
            return True
        metadata = getattr(doc, "metadata", {}) or {}
        candidates = [
            getattr(doc, "source", ""),
            getattr(doc, "source_type", ""),
            str(metadata.get("id", "")),
            str(metadata.get("source", "")),
            str(metadata.get("path", "")),
            str(metadata.get("title", "")),
            str(metadata.get("incident_id", "")),
            str(metadata.get("name", "")),
        ]
        return any(source_id == value or source_id in value for value in candidates if value)

    # ---- Playground ----

    def playground_execute(
        self,
        agent_id: str,
        task: str,
        prompt_override: str | None = None,
        simulate: bool = True,
        provider: Any = None,
        repo: Any = None,
    ) -> WorkforceExecution:
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        if agent.lifecycle_status != LifecycleStatus.ACTIVE.value:
            raise WorkforceExecutionBlocked("agent_not_active", {"status": agent.lifecycle_status})

        budget = self.check_budget_available(agent_id, estimated_cost=0.001 if simulate else 0.005)
        if not budget["allowed"]:
            raise WorkforceExecutionBlocked("budget_exceeded", budget)

        start = time.time()
        execution = WorkforceExecution(
            agent_id=agent_id,
            task=task,
            status=ExecutionResult.SUCCESS.value,
        )

        try:
            if simulate:
                execution.response = f"[Playground] Simulated response for: {task}"
                execution.confidence = 0.85
                execution.cost = 0.001
                execution.tools_used = ["playground_simulator"]
            else:
                from src.intelligence.providers.factory import create_provider
                from src.intelligence.retrieval.rag import RAGEngine
                from src.intelligence.tools import execute_tool

                allowed_tools = sorted(self.get_allowed_tool_names(agent_id))
                readable_sources = self.get_readable_knowledge_sources(agent_id)
                tool_results: dict[str, Any] = {}
                for tool_name in allowed_tools:
                    if tool_name == "playground_simulator":
                        continue
                    self.require_tool_allowed(agent_id, tool_name)
                    tool_results[tool_name] = execute_tool(tool_name, repo=repo or self.repo)

                prompts = self.list_prompt_versions(agent_id=agent_id, name="system_prompt")
                system_prompt = prompt_override or (prompts[0].content if prompts else "")
                live_provider = provider or create_provider(agent.provider)
                if agent.model and getattr(live_provider, "config", None):
                    live_provider.config.model = agent.model
                rag = RAGEngine(provider=live_provider, repo=repo or self.repo)
                context = ""
                if readable_sources:
                    contexts = []
                    for source in readable_sources:
                        result = rag.retrieve_by_type(task, source.knowledge_source_type, limit=3)
                        docs = [doc for doc in result.documents if self._knowledge_doc_matches(source, doc)]
                        contexts.extend(f"[{doc.source_type}] {doc.source}\n{doc.content}" for doc in docs)
                    context = "\n\n".join(c for c in contexts if c)
                response = rag.generate_with_context(
                    f"{system_prompt}\n\nTask: {task}" if system_prompt else task,
                    context=context,
                    tool_results=tool_results,
                )
                execution.response = response
                execution.confidence = 0.9
                execution.cost = 0.005
                execution.tools_used = list(tool_results.keys())
                execution.metadata = {
                    "mode": "live",
                    "provider": getattr(live_provider, "provider_name", agent.provider),
                    "knowledge_sources": [k.knowledge_source_id for k in readable_sources],
                    "budget": budget,
                }

            execution.latency_ms = round((time.time() - start) * 1000, 1)
        except Exception as e:
            execution.status = ExecutionResult.ERROR.value
            execution.error = str(e)
            execution.latency_ms = round((time.time() - start) * 1000, 1)

        return self.record_execution(execution)

    # ---- Create Agent Wizard ----

    def create_agent_wizard(
        self,
        name: str,
        agent_type: str = "general",
        description: str = "",
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        tools: list[dict] | None = None,
        permissions: list[str] | None = None,
        knowledge_sources: list[str] | None = None,
        daily_budget: float = 25.0,
        monthly_budget: float = 750.0,
        owner: str = "",
        team: str = "",
        org_id: int | None = None,
        team_id: int | None = None,
        tags: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> WorkforceAgent:
        agent = WorkforceAgent(
            name=name,
            description=description,
            agent_type=agent_type,
            provider=provider,
            model=model,
            version=1,
            lifecycle_status=LifecycleStatus.DRAFT.value,
            tools=tools or [],
            permissions=permissions or [],
            daily_budget=daily_budget,
            monthly_budget=monthly_budget,
            owner=owner,
            team=team,
            org_id=org_id,
            team_id=team_id,
            tags=tags or [],
        )
        self.register_agent(agent)

        if system_prompt:
            self.save_prompt_version(
                agent_id=agent.agent_id,
                name="system_prompt",
                content=system_prompt,
                role=PromptRole.SYSTEM.value,
                description="System prompt created during agent setup",
            )

        for ks in (knowledge_sources or []):
            self.assign_knowledge(agent.agent_id, ks, "collection", AccessLevel.READ_WRITE.value)

        if tools:
            for t in tools:
                tool_name = t.get("name", t) if isinstance(t, dict) else t
                allowed = t.get("allowed", True) if isinstance(t, dict) else True
                tool_config = t.get("config", {}) if isinstance(t, dict) else {}
                self.set_tool_permission(agent.agent_id, tool_name, allowed, tool_config)

        self.create_agent_version(agent.agent_id, "Initial version from setup wizard", owner or "wizard")

        return agent
