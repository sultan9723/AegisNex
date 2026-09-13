"""Mission Control: Execution tracking and visualization for AegisNex AI operations.

Every AI request (chat, analyze, plan, knowledge search, Docker action,
governance approval, policy check) creates an Execution record. The module
supports replay mode, execution history, audit links, and multi-agent tracking.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

TABLE_NAME = "mc_executions"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionType(StrEnum):
    CHAT = "chat"
    ANALYZE = "analyze"
    PLAN = "plan"
    KNOWLEDGE_SEARCH = "knowledge_search"
    DOCKER_ACTION = "docker_action"
    GOVERNANCE_APPROVAL = "governance_approval"
    POLICY_CHECK = "policy_check"
    WORKFLOW = "workflow"
    AGENT_DISPATCH = "agent_dispatch"
    SEARCH = "search"


STAGE_ORDER = [
    "planner",
    "knowledge",
    "metrics",
    "docker",
    "policy",
    "risk",
    "verifier",
    "executor",
]


@dataclass
class StageResult:
    stage_id: str
    start_time: str | None = None
    finish_time: str | None = None
    latency_ms: float = 0.0
    status: str = "queued"
    confidence: float = 0.0
    model: str = ""
    provider: str = ""
    tokens: int = 0
    estimated_cost: float = 0.0
    summary: str = ""
    connected_tools: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    policy_decisions: list[dict[str, Any]] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageResult:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Execution:
    execution_id: str
    request: str
    user: str
    timestamp: str
    current_status: str = "queued"
    total_latency_ms: float = 0.0
    total_cost: float = 0.0
    confidence: float = 0.0
    overall_result: str = ""
    stages: list[StageResult] = field(default_factory=list)
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_type: str = "chat"
    organization: str = ""
    agents: list[str] = field(default_factory=list)
    audit_links: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stages"] = [s.to_dict() if isinstance(s, StageResult) else s for s in self.stages]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Execution:
        stages_data = data.get("stages", [])
        stages = [StageResult.from_dict(s) if isinstance(s, dict) else s for s in stages_data]
        return cls(
            execution_id=data["execution_id"],
            request=data.get("request", ""),
            user=data.get("user", ""),
            timestamp=data.get("timestamp", ""),
            current_status=data.get("current_status", "queued"),
            total_latency_ms=data.get("total_latency_ms", 0.0),
            total_cost=data.get("total_cost", 0.0),
            confidence=data.get("confidence", 0.0),
            overall_result=data.get("overall_result", ""),
            stages=stages,
            error=data.get("error", ""),
            metadata=data.get("metadata", {}),
            execution_type=data.get("execution_type", "chat"),
            organization=data.get("organization", ""),
            agents=data.get("agents", []),
            audit_links=data.get("audit_links", {}),
        )

    def replay_data(self) -> dict[str, Any]:
        """Return execution with full stage inputs/outputs for replay mode."""
        return {
            "execution_id": self.execution_id,
            "execution_type": self.execution_type,
            "request": self.request,
            "user": self.user,
            "organization": self.organization,
            "agents": self.agents,
            "current_status": self.current_status,
            "total_latency_ms": self.total_latency_ms,
            "total_cost": self.total_cost,
            "confidence": self.confidence,
            "overall_result": self.overall_result,
            "error": self.error,
            "audit_links": self.audit_links,
            "timeline": [
                {
                    "stage_id": s.stage_id,
                    "status": s.status,
                    "start_time": s.start_time,
                    "finish_time": s.finish_time,
                    "latency_ms": s.latency_ms,
                    "summary": s.summary,
                    "confidence": s.confidence,
                    "model": s.model,
                    "provider": s.provider,
                    "tokens": s.tokens,
                    "estimated_cost": s.estimated_cost,
                    "connected_tools": s.connected_tools,
                    "evidence": s.evidence,
                    "policy_decisions": s.policy_decisions,
                    "inputs": s.inputs,
                    "outputs": s.outputs,
                }
                for s in self.stages
            ],
            "timestamp": self.timestamp,
        }


def ensure_table(repo: Any) -> None:
    if repo is None:
        return
    if repo.table_exists(TABLE_NAME):
        _ensure_columns(repo)
        return
    if repo.backend == "sqlite":
        repo._execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT UNIQUE NOT NULL,
                request TEXT NOT NULL,
                user_name TEXT DEFAULT '',
                timestamp TEXT NOT NULL,
                current_status TEXT DEFAULT 'queued',
                total_latency_ms REAL DEFAULT 0.0,
                total_cost REAL DEFAULT 0.0,
                confidence REAL DEFAULT 0.0,
                overall_result TEXT DEFAULT '',
                stages TEXT DEFAULT '[]',
                error TEXT DEFAULT '',
                metadata TEXT DEFAULT '{{}}',
                execution_type TEXT DEFAULT 'chat',
                organization TEXT DEFAULT '',
                agents TEXT DEFAULT '[]',
                audit_links TEXT DEFAULT '{{}}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
    else:
        repo._execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id SERIAL PRIMARY KEY,
                execution_id VARCHAR(255) UNIQUE NOT NULL,
                request TEXT NOT NULL,
                user_name VARCHAR(255) DEFAULT '',
                timestamp VARCHAR(255) NOT NULL,
                current_status VARCHAR(50) DEFAULT 'queued',
                total_latency_ms REAL DEFAULT 0.0,
                total_cost REAL DEFAULT 0.0,
                confidence REAL DEFAULT 0.0,
                overall_result TEXT DEFAULT '',
                stages TEXT DEFAULT '[]',
                error TEXT DEFAULT '',
                metadata TEXT DEFAULT '{{}}',
                execution_type VARCHAR(50) DEFAULT 'chat',
                organization VARCHAR(255) DEFAULT '',
                agents TEXT DEFAULT '[]',
                audit_links TEXT DEFAULT '{{}}',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
    _ensure_columns(repo)


def _ensure_columns(repo: Any) -> None:
    try:
        rows = (
            repo._fetch_all(f"PRAGMA table_info({TABLE_NAME})") if repo.backend == "sqlite" else []
        )
        existing = {r.get("name") for r in rows}
        migrations = [
            ("metadata", "TEXT DEFAULT '{}'"),
            ("execution_type", "TEXT DEFAULT 'chat'"),
            ("organization", "TEXT DEFAULT ''"),
            ("agents", "TEXT DEFAULT '[]'"),
            ("audit_links", "TEXT DEFAULT '{}'"),
        ]
        for col, typedef in migrations:
            if col not in existing:
                repo._execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {col} {typedef}")
    except Exception:
        pass


def _org_membership_filter(user: Any, repo: Any) -> str | None:
    """Return an org_id to filter by, or None for superusers."""
    if user is None:
        return None
    if hasattr(user, "is_superuser") and user.is_superuser:
        return None
    if hasattr(user, "role") and user.role == "super_admin":
        return None
    try:
        tm = getattr(repo, "_tenant_manager", None)
        if tm is None and hasattr(repo, "_get_tenant_manager"):
            tm = repo._get_tenant_manager()
        if tm is not None and hasattr(user, "id") and user.id > 0:
            tenants = tm.get_user_tenants(user.id)
            if tenants:
                return str(tenants[0].org_id)
    except Exception:
        pass
    return None


def create_execution(
    repo: Any,
    execution_id: str,
    request: str,
    user: str = "",
    metadata: dict[str, Any] | None = None,
    execution_type: str = "chat",
    organization: str = "",
    agents: list[str] | None = None,
    audit_links: dict[str, str] | None = None,
) -> Execution:
    ensure_table(repo)
    timestamp = utc_now()
    stages = [StageResult(stage_id=sid) for sid in STAGE_ORDER]
    execution = Execution(
        execution_id=execution_id,
        request=request,
        user=user,
        timestamp=timestamp,
        current_status="queued",
        stages=stages,
        metadata=metadata or {},
        execution_type=execution_type,
        organization=organization,
        agents=agents or [],
        audit_links=audit_links or {},
    )
    _save_execution(repo, execution)
    return execution


def update_execution(repo: Any, execution: Execution) -> None:
    _save_execution(repo, execution)


def _save_execution(repo: Any, execution: Execution) -> None:
    p = repo.placeholder
    stages_json = json.dumps([s.to_dict() for s in execution.stages])
    metadata_json = json.dumps(execution.metadata)
    agents_json = json.dumps(execution.agents)
    audit_links_json = json.dumps(execution.audit_links)
    existing = repo._fetch_all(
        f"SELECT id FROM {TABLE_NAME} WHERE execution_id = {p}", (execution.execution_id,)
    )
    if existing:
        repo._execute(
            f"""UPDATE {TABLE_NAME} SET
                request = {p}, user_name = {p}, timestamp = {p},
                current_status = {p}, total_latency_ms = {p}, total_cost = {p},
                confidence = {p}, overall_result = {p}, stages = {p},
                error = {p}, metadata = {p}, execution_type = {p},
                organization = {p}, agents = {p}, audit_links = {p}
            WHERE execution_id = {p}""",
            (
                execution.request,
                execution.user,
                execution.timestamp,
                execution.current_status,
                execution.total_latency_ms,
                execution.total_cost,
                execution.confidence,
                execution.overall_result,
                stages_json,
                execution.error,
                metadata_json,
                execution.execution_type,
                execution.organization,
                agents_json,
                audit_links_json,
                execution.execution_id,
            ),
        )
    else:
        repo._execute(
            f"""INSERT INTO {TABLE_NAME}
                (execution_id, request, user_name, timestamp, current_status,
                 total_latency_ms, total_cost, confidence, overall_result,
                 stages, error, metadata, execution_type, organization,
                 agents, audit_links)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p},
                    {p}, {p}, {p}, {p}, {p}, {p})""",
            (
                execution.execution_id,
                execution.request,
                execution.user,
                execution.timestamp,
                execution.current_status,
                execution.total_latency_ms,
                execution.total_cost,
                execution.confidence,
                execution.overall_result,
                stages_json,
                execution.error,
                metadata_json,
                execution.execution_type,
                execution.organization,
                agents_json,
                audit_links_json,
            ),
        )


def get_execution(repo: Any, execution_id: str) -> Execution | None:
    ensure_table(repo)
    p = repo.placeholder
    rows = repo._fetch_all(f"SELECT * FROM {TABLE_NAME} WHERE execution_id = {p}", (execution_id,))
    if not rows:
        return None
    return _row_to_execution(rows[0])


def get_stage(repo: Any, execution_id: str, stage_id: str) -> StageResult | None:
    exec_ = get_execution(repo, execution_id)
    if exec_ is None:
        return None
    for s in exec_.stages:
        if s.stage_id == stage_id:
            return s
    return None


def list_executions(
    repo: Any,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
    user: str | None = None,
    execution_type: str | None = None,
    organization: str | None = None,
    days: int | None = None,
) -> list[Execution]:
    ensure_table(repo)
    p = repo.placeholder
    conditions = []
    params: list[Any] = []
    if status:
        conditions.append(f"current_status = {p}")
        params.append(status)
    if search:
        conditions.append(f"(request LIKE {p} OR overall_result LIKE {p})")
        params.extend([f"%{search}%", f"%{search}%"])
    if user:
        conditions.append(f"user_name = {p}")
        params.append(user)
    if execution_type:
        conditions.append(f"execution_type = {p}")
        params.append(execution_type)
    if organization:
        conditions.append(f"organization = {p}")
        params.append(organization)
    if days is not None:
        try:
            from datetime import timedelta

            cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
            conditions.append(f"timestamp >= {p}")
            params.append(cutoff)
        except Exception:
            pass
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM {TABLE_NAME} {where} ORDER BY id DESC LIMIT {p} OFFSET {p}"
    params.extend([limit, offset])
    rows = repo._fetch_all(sql, tuple(params))
    return [_row_to_execution(r) for r in rows]


def count_executions(
    repo: Any,
    status: str | None = None,
    search: str | None = None,
    user: str | None = None,
    execution_type: str | None = None,
    organization: str | None = None,
    days: int | None = None,
) -> int:
    ensure_table(repo)
    p = repo.placeholder
    conditions = []
    params: list[Any] = []
    if status:
        conditions.append(f"current_status = {p}")
        params.append(status)
    if search:
        conditions.append(f"(request LIKE {p} OR overall_result LIKE {p})")
        params.extend([f"%{search}%", f"%{search}%"])
    if user:
        conditions.append(f"user_name = {p}")
        params.append(user)
    if execution_type:
        conditions.append(f"execution_type = {p}")
        params.append(execution_type)
    if organization:
        conditions.append(f"organization = {p}")
        params.append(organization)
    if days is not None:
        try:
            from datetime import timedelta

            cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
            conditions.append(f"timestamp >= {p}")
            params.append(cutoff)
        except Exception:
            pass
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = repo._fetch_all(f"SELECT COUNT(*) as cnt FROM {TABLE_NAME} {where}", tuple(params))
    return rows[0].get("cnt", 0) if rows else 0


def get_execution_stats(repo: Any) -> dict[str, Any]:
    ensure_table(repo)
    rows = repo._fetch_all(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN current_status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN current_status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN current_status = 'running' THEN 1 ELSE 0 END) as running,
            SUM(CASE WHEN current_status = 'queued' THEN 1 ELSE 0 END) as queued,
            AVG(total_latency_ms) as avg_latency,
            AVG(total_cost) as avg_cost,
            AVG(confidence) as avg_confidence,
            SUM(total_cost) as total_cost,
            COUNT(DISTINCT execution_type) as type_count,
            COUNT(DISTINCT user_name) as user_count
        FROM {TABLE_NAME}
    """)
    if not rows:
        return {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "running": 0,
            "queued": 0,
            "avg_latency": 0,
            "avg_cost": 0,
            "avg_confidence": 0,
            "total_cost": 0,
            "type_count": 0,
            "user_count": 0,
        }
    r = rows[0]
    return {
        "total": r.get("total", 0),
        "completed": r.get("completed", 0),
        "failed": r.get("failed", 0),
        "running": r.get("running", 0),
        "queued": r.get("queued", 0),
        "avg_latency": round(r.get("avg_latency") or 0, 1),
        "avg_cost": round(r.get("avg_cost") or 0, 6),
        "avg_confidence": round(r.get("avg_confidence") or 0, 3),
        "total_cost": round(r.get("total_cost") or 0, 6),
        "type_count": r.get("type_count", 0),
        "user_count": r.get("user_count", 0),
    }


def get_execution_type_stats(repo: Any) -> list[dict[str, Any]]:
    ensure_table(repo)
    rows = repo._fetch_all(f"""
        SELECT
            execution_type,
            COUNT(*) as count,
            SUM(CASE WHEN current_status = 'completed' THEN 1 ELSE 0 END) as completed,
            AVG(total_latency_ms) as avg_latency,
            AVG(confidence) as avg_confidence,
            SUM(total_cost) as total_cost
        FROM {TABLE_NAME}
        GROUP BY execution_type
        ORDER BY count DESC
    """)
    result = []
    for r in rows:
        result.append(
            {
                "execution_type": r.get("execution_type", "unknown"),
                "count": r.get("count", 0),
                "completed": r.get("completed", 0),
                "avg_latency": round(r.get("avg_latency") or 0, 1),
                "avg_confidence": round(r.get("avg_confidence") or 0, 3),
                "total_cost": round(r.get("total_cost") or 0, 6),
            }
        )
    return result


def delete_execution(repo: Any, execution_id: str) -> bool:
    ensure_table(repo)
    p = repo.placeholder
    repo._execute(f"DELETE FROM {TABLE_NAME} WHERE execution_id = {p}", (execution_id,))
    return True


def _row_to_execution(row: dict[str, Any]) -> Execution:
    stages_raw = row.get("stages", "[]")
    if isinstance(stages_raw, str):
        try:
            stages_raw = json.loads(stages_raw)
        except (json.JSONDecodeError, TypeError):
            stages_raw = []
    stages = [StageResult.from_dict(s) for s in stages_raw if isinstance(s, dict)]
    metadata_raw = row.get("metadata", "{}")
    if isinstance(metadata_raw, str):
        try:
            metadata_raw = json.loads(metadata_raw)
        except (json.JSONDecodeError, TypeError):
            metadata_raw = {}
    agents_raw = row.get("agents", "[]")
    if isinstance(agents_raw, str):
        try:
            agents_raw = json.loads(agents_raw)
        except (json.JSONDecodeError, TypeError):
            agents_raw = []
    audit_raw = row.get("audit_links", "{}")
    if isinstance(audit_raw, str):
        try:
            audit_raw = json.loads(audit_raw)
        except (json.JSONDecodeError, TypeError):
            audit_raw = {}
    return Execution(
        execution_id=row.get("execution_id", ""),
        request=row.get("request", ""),
        user=row.get("user_name", ""),
        timestamp=row.get("timestamp", ""),
        current_status=row.get("current_status", "queued"),
        total_latency_ms=row.get("total_latency_ms", 0.0),
        total_cost=row.get("total_cost", 0.0),
        confidence=row.get("confidence", 0.0),
        overall_result=row.get("overall_result", ""),
        stages=stages,
        error=row.get("error", ""),
        metadata=metadata_raw if isinstance(metadata_raw, dict) else {},
        execution_type=row.get("execution_type", "chat"),
        organization=row.get("organization", ""),
        agents=agents_raw if isinstance(agents_raw, list) else [],
        audit_links=audit_raw if isinstance(audit_raw, dict) else {},
    )


def stage_to_stage_result(
    stage_id: str,
    status: str = "queued",
    latency_ms: float = 0.0,
    confidence: float = 0.0,
    model: str = "",
    provider: str = "",
    tokens: int = 0,
    estimated_cost: float = 0.0,
    summary: str = "",
    connected_tools: list[str] | None = None,
    evidence: list[str] | None = None,
    policy_decisions: list[dict[str, Any]] | None = None,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
) -> StageResult:
    return StageResult(
        stage_id=stage_id,
        start_time=utc_now(),
        finish_time=utc_now(),
        latency_ms=latency_ms,
        status=status,
        confidence=confidence,
        model=model,
        provider=provider,
        tokens=tokens,
        estimated_cost=estimated_cost,
        summary=summary,
        connected_tools=connected_tools or [],
        evidence=evidence or [],
        policy_decisions=policy_decisions or [],
        inputs=inputs or {},
        outputs=outputs or {},
    )


def complete_stage(
    execution: Execution,
    stage_id: str,
    status: str = "completed",
    latency_ms: float = 0.0,
    confidence: float = 0.0,
    model: str = "",
    provider: str = "",
    tokens: int = 0,
    estimated_cost: float = 0.0,
    summary: str = "",
    connected_tools: list[str] | None = None,
    evidence: list[str] | None = None,
    policy_decisions: list[dict[str, Any]] | None = None,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
) -> bool:
    for i, s in enumerate(execution.stages):
        if s.stage_id == stage_id:
            execution.stages[i] = StageResult(
                stage_id=stage_id,
                start_time=s.start_time or utc_now(),
                finish_time=utc_now(),
                latency_ms=latency_ms,
                status=status,
                confidence=confidence,
                model=model or s.model,
                provider=provider or s.provider,
                tokens=tokens or s.tokens,
                estimated_cost=estimated_cost or s.estimated_cost,
                summary=summary or s.summary,
                connected_tools=connected_tools or s.connected_tools,
                evidence=evidence or s.evidence,
                policy_decisions=policy_decisions or s.policy_decisions,
                inputs=inputs or s.inputs,
                outputs=outputs or s.outputs,
            )
            return True
    return False


def update_stage(
    execution: Execution,
    stage_id: str,
    **kwargs: Any,
) -> bool:
    for i, s in enumerate(execution.stages):
        if s.stage_id == stage_id:
            updated = dict(asdict(s).items())
            updated.update(kwargs)
            execution.stages[i] = StageResult.from_dict(updated)
            return True
    return False


def mark_stage_started(execution: Execution, stage_id: str) -> bool:
    return update_stage(execution, stage_id, status="running", start_time=utc_now())
