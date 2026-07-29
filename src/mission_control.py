"""Mission Control: Execution tracking and visualization for AegisNex AI operations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

TABLE_NAME = "mc_executions"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


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
        )


def ensure_table(repo: Any) -> None:
    """Create the mc_executions table if it doesn't exist."""
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
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
    _ensure_columns(repo)


def _ensure_columns(repo: Any) -> None:
    """Add missing columns for forward compatibility."""
    try:
        rows = (
            repo._fetch_all(f"PRAGMA table_info({TABLE_NAME})") if repo.backend == "sqlite" else []
        )
        existing = {r.get("name") for r in rows}
        migrations = [
            ("metadata", "TEXT DEFAULT '{}'"),
        ]
        for col, typedef in migrations:
            if col not in existing:
                repo._execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {col} {typedef}")
    except Exception:
        pass


def create_execution(
    repo: Any,
    execution_id: str,
    request: str,
    user: str = "",
    metadata: dict[str, Any] | None = None,
) -> Execution:
    """Create and persist a new execution."""
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
    )
    _save_execution(repo, execution)
    return execution


def update_execution(repo: Any, execution: Execution) -> None:
    """Persist execution updates."""
    _save_execution(repo, execution)


def _save_execution(repo: Any, execution: Execution) -> None:
    """Upsert execution to database."""
    p = repo.placeholder
    stages_json = json.dumps([s.to_dict() for s in execution.stages])
    metadata_json = json.dumps(execution.metadata)
    existing = repo._fetch_all(
        f"SELECT id FROM {TABLE_NAME} WHERE execution_id = {p}", (execution.execution_id,)
    )
    if existing:
        repo._execute(
            f"""UPDATE {TABLE_NAME} SET
                request = {p}, user_name = {p}, timestamp = {p},
                current_status = {p}, total_latency_ms = {p}, total_cost = {p},
                confidence = {p}, overall_result = {p}, stages = {p},
                error = {p}, metadata = {p}
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
                execution.execution_id,
            ),
        )
    else:
        repo._execute(
            f"""INSERT INTO {TABLE_NAME}
                (execution_id, request, user_name, timestamp, current_status,
                 total_latency_ms, total_cost, confidence, overall_result,
                 stages, error, metadata)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})""",
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
            ),
        )


def get_execution(repo: Any, execution_id: str) -> Execution | None:
    """Retrieve a single execution by ID."""
    ensure_table(repo)
    p = repo.placeholder
    rows = repo._fetch_all(f"SELECT * FROM {TABLE_NAME} WHERE execution_id = {p}", (execution_id,))
    if not rows:
        return None
    return _row_to_execution(rows[0])


def list_executions(
    repo: Any,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
    user: str | None = None,
) -> list[Execution]:
    """List executions with optional filters."""
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
) -> int:
    """Count total executions with optional filters."""
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
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = repo._fetch_all(f"SELECT COUNT(*) as cnt FROM {TABLE_NAME} {where}", tuple(params))
    return rows[0].get("cnt", 0) if rows else 0


def get_execution_stats(repo: Any) -> dict[str, Any]:
    """Get aggregate execution statistics."""
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
            SUM(total_cost) as total_cost
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
    }


def delete_execution(repo: Any, execution_id: str) -> bool:
    """Delete an execution."""
    ensure_table(repo)
    p = repo.placeholder
    repo._execute(f"DELETE FROM {TABLE_NAME} WHERE execution_id = {p}", (execution_id,))
    return True


def _row_to_execution(row: dict[str, Any]) -> Execution:
    """Convert a database row to an Execution object."""
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
    )
