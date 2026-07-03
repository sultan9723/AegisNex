"""AI workflow history persistence.

Stores and retrieves past AI queries, results, and approval actions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.platform_db import PlatformRepository


TABLE_NAME = "ai_history"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_columns(repo: PlatformRepository) -> None:
    """Migrate table to add new columns if they don't exist."""
    if repo.backend != "sqlite":
        return
    try:
        existing = repo._fetch_all(f"PRAGMA table_info({TABLE_NAME})")
        col_names = {r["name"] for r in existing}
        additions = {
            "evidence": "TEXT NOT NULL DEFAULT '[]'",
            "reasoning_summary": "TEXT NOT NULL DEFAULT ''",
            "remaining_uncertainty": "TEXT NOT NULL DEFAULT ''",
            "provider_used": "TEXT NOT NULL DEFAULT ''",
            "model_used": "TEXT NOT NULL DEFAULT ''",
            "execution_duration_ms": "REAL NOT NULL DEFAULT 0.0",
            "token_usage": "INTEGER NOT NULL DEFAULT 0",
            "tools_used": "TEXT NOT NULL DEFAULT '[]'",
            "plan_text": "TEXT NOT NULL DEFAULT ''",
        }
        for col, dtype in additions.items():
            if col not in col_names:
                repo._execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {col} {dtype}")
    except Exception:
        pass


def ensure_table(repo: PlatformRepository) -> None:
    if repo.table_exists(TABLE_NAME):
        _ensure_columns(repo)
        return
    p = repo.placeholder
    with repo._connect() as conn:
        if repo.backend == "postgresql":
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    id BIGSERIAL PRIMARY KEY,
                    request TEXT NOT NULL,
                    objective TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    goal_achieved INTEGER NOT NULL DEFAULT 0,
                    steps TEXT NOT NULL DEFAULT '[]',
                    observations TEXT NOT NULL DEFAULT '[]',
                    corrections TEXT NOT NULL DEFAULT '[]',
                    errors TEXT NOT NULL DEFAULT '[]',
                    evidence TEXT NOT NULL DEFAULT '[]',
                    reasoning_summary TEXT NOT NULL DEFAULT '',
                    remaining_uncertainty TEXT NOT NULL DEFAULT '',
                    provider_used TEXT NOT NULL DEFAULT '',
                    model_used TEXT NOT NULL DEFAULT '',
                    execution_duration_ms REAL NOT NULL DEFAULT 0.0,
                    token_usage INTEGER NOT NULL DEFAULT 0,
                    tools_used TEXT NOT NULL DEFAULT '[]',
                    plan_text TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
        else:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request TEXT NOT NULL,
                    objective TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    goal_achieved INTEGER NOT NULL DEFAULT 0,
                    steps TEXT NOT NULL DEFAULT '[]',
                    observations TEXT NOT NULL DEFAULT '[]',
                    corrections TEXT NOT NULL DEFAULT '[]',
                    errors TEXT NOT NULL DEFAULT '[]',
                    evidence TEXT NOT NULL DEFAULT '[]',
                    reasoning_summary TEXT NOT NULL DEFAULT '',
                    remaining_uncertainty TEXT NOT NULL DEFAULT '',
                    provider_used TEXT NOT NULL DEFAULT '',
                    model_used TEXT NOT NULL DEFAULT '',
                    execution_duration_ms REAL NOT NULL DEFAULT 0.0,
                    token_usage INTEGER NOT NULL DEFAULT 0,
                    tools_used TEXT NOT NULL DEFAULT '[]',
                    plan_text TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)


def save_workflow(
    repo: PlatformRepository,
    request: str,
    objective: str,
    result_text: str,
    confidence: float,
    goal_achieved: bool,
    steps: List[Dict[str, Any]],
    observations: List[str],
    corrections: List[str],
    errors: List[str],
    evidence: Optional[List[str]] = None,
    reasoning_summary: str = "",
    remaining_uncertainty: str = "",
    provider_used: str = "",
    model_used: str = "",
    execution_duration_ms: float = 0.0,
    token_usage: int = 0,
    tools_used: Optional[List[str]] = None,
    plan_text: str = "",
) -> int:
    ensure_table(repo)
    p = repo.placeholder
    now = _now()
    repo._execute(
        f"""
        INSERT INTO {TABLE_NAME} (
            request, objective, result, confidence, goal_achieved,
            steps, observations, corrections, errors,
            evidence, reasoning_summary, remaining_uncertainty,
            provider_used, model_used, execution_duration_ms, token_usage,
            tools_used, plan_text, created_at
        )
        VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p},
                {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
        """,
        (
            request,
            objective,
            result_text,
            confidence,
            1 if goal_achieved else 0,
            json.dumps(steps, default=str),
            json.dumps(observations),
            json.dumps(corrections),
            json.dumps(errors),
            json.dumps(evidence or []),
            reasoning_summary,
            remaining_uncertainty,
            provider_used,
            model_used,
            execution_duration_ms,
            token_usage,
            json.dumps(tools_used or []),
            plan_text,
            now,
        ),
    )
    rows = repo._fetch_all(f"SELECT last_insert_rowid() as id")
    return int(rows[0]["id"]) if rows else 0


def list_history(
    repo: PlatformRepository,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    ensure_table(repo)
    rows = repo._fetch_all(
        f"SELECT * FROM {TABLE_NAME} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (int(limit), int(offset)),
    )
    for row in rows:
        for field in ("steps", "observations", "corrections", "errors", "evidence", "tools_used"):
            try:
                val = row.get(field, "[]")
                row[field] = json.loads(str(val)) if isinstance(val, str) else val
            except (json.JSONDecodeError, TypeError):
                row[field] = []
    return rows


def get_history_count(repo: PlatformRepository) -> int:
    ensure_table(repo)
    rows = repo._fetch_all(f"SELECT COUNT(*) as cnt FROM {TABLE_NAME}")
    return int(rows[0]["cnt"]) if rows else 0


def get_history_stats(repo: PlatformRepository) -> Dict[str, Any]:
    ensure_table(repo)
    try:
        rows = repo._fetch_all(f"SELECT confidence, goal_achieved, execution_duration_ms FROM {TABLE_NAME}")
        if not rows:
            return {"total": 0}
        confidences = [float(r.get("confidence", 0)) for r in rows]
        durations = [float(r.get("execution_duration_ms", 0)) for r in rows if r.get("execution_duration_ms")]
        succeeded = sum(1 for r in rows if int(r.get("goal_achieved", 0)) == 1)
        return {
            "total": len(rows),
            "successful": succeeded,
            "failed": len(rows) - succeeded,
            "success_rate": round(succeeded / max(len(rows), 1), 4),
            "avg_confidence": round(sum(confidences) / max(len(confidences), 1), 4),
            "avg_execution_duration_ms": round(sum(durations) / max(len(durations), 1), 2) if durations else 0.0,
        }
    except Exception:
        return {"total": 0}
