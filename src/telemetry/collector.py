"""Telemetry collector for AegisNex — records API, workflow, agent, tool, and approval metrics."""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from threading import Lock

_logger = logging.getLogger(__name__)


class TelemetryCollector:
    """Persistent telemetry store backed by SQLite with WAL mode.

    Records latency, execution, and failure data for dashboards and alerting.
    """

    def __init__(self, db_path: str = "telemetry.db") -> None:
        self._db_path = db_path
        self._lock = Lock()
        self._conn: sqlite3.Connection | None = None
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            try:
                self._conn.execute("SELECT 1")
                return self._conn
            except (sqlite3.OperationalError, sqlite3.ProgrammingError):
                _logger.debug("Recreating stale telemetry connection")
                self._conn = None
        _logger.debug("TelemetryCollector opening connection to %s", self._db_path)
        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("PRAGMA busy_timeout=10000")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            pass
        self._conn = conn
        return conn

    def _initialize(self) -> None:
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS api_latency (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                duration_ms REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workflow_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                workflow_name TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                success INTEGER NOT NULL,
                steps INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                task TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                success INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tool_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                error TEXT NOT NULL,
                duration_ms REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approval_times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                approval_id TEXT NOT NULL,
                action TEXT NOT NULL,
                decision TEXT NOT NULL,
                duration_ms REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_api_latency_ts ON api_latency(timestamp);
            CREATE INDEX IF NOT EXISTS idx_workflow_ts ON workflow_executions(timestamp);
            CREATE INDEX IF NOT EXISTS idx_agent_ts ON agent_executions(timestamp);
            CREATE INDEX IF NOT EXISTS idx_tool_fail_ts ON tool_failures(timestamp);
            CREATE INDEX IF NOT EXISTS idx_approval_ts ON approval_times(timestamp);
        """)
        conn.commit()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._connect().execute(sql, params)

    def _fetch_all(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._connect().execute(sql, params).fetchall()]

    # ---- Recording methods ----

    def record_api_latency(
        self, method: str, path: str, status_code: int, duration_ms: float
    ) -> None:
        self._execute(
            "INSERT INTO api_latency (timestamp, method, path, status_code, duration_ms) VALUES (?, ?, ?, ?, ?)",
            (self._utc_now(), method, path, status_code, duration_ms),
        )

    def record_workflow_execution(
        self, workflow_name: str, duration_ms: float, success: bool, steps: int
    ) -> None:
        self._execute(
            "INSERT INTO workflow_executions (timestamp, workflow_name, duration_ms, success, steps) VALUES (?, ?, ?, ?, ?)",
            (self._utc_now(), workflow_name, duration_ms, 1 if success else 0, steps),
        )

    def record_agent_execution(
        self, agent_id: str, task: str, duration_ms: float, success: bool
    ) -> None:
        self._execute(
            "INSERT INTO agent_executions (timestamp, agent_id, task, duration_ms, success) VALUES (?, ?, ?, ?, ?)",
            (self._utc_now(), agent_id, task, duration_ms, 1 if success else 0),
        )

    def record_tool_failure(
        self, tool_name: str, error: str, duration_ms: float
    ) -> None:
        self._execute(
            "INSERT INTO tool_failures (timestamp, tool_name, error, duration_ms) VALUES (?, ?, ?, ?)",
            (self._utc_now(), tool_name, error, duration_ms),
        )

    def record_approval_time(
        self, approval_id: str, action: str, decision: str, duration_ms: float
    ) -> None:
        self._execute(
            "INSERT INTO approval_times (timestamp, approval_id, action, decision, duration_ms) VALUES (?, ?, ?, ?, ?)",
            (self._utc_now(), approval_id, action, decision, duration_ms),
        )

    # ---- Stats queries ----

    def get_api_stats(self, hours: int = 24) -> Dict[str, Any]:
        cutoff = (time.time() - hours * 3600) * 1000
        rows = self._fetch_all(
            "SELECT * FROM api_latency WHERE (julianday('now') - julianday(substr(timestamp,1,19))) * 86400 <= ?",
            (hours * 3600,),
        )
        if not rows:
            return {"total_requests": 0, "avg_latency_ms": 0.0, "min_latency_ms": 0.0, "max_latency_ms": 0.0, "error_rate": 0.0, "top_endpoints": []}

        total = len(rows)
        durations = [r["duration_ms"] for r in rows]
        errors = sum(1 for r in rows if r["status_code"] >= 500)

        from collections import Counter
        endpoint_counter: Counter = Counter()
        for r in rows:
            endpoint_counter[f"{r['method']} {r['path']}"] += 1

        return {
            "total_requests": total,
            "avg_latency_ms": round(sum(durations) / total, 2),
            "min_latency_ms": round(min(durations), 2),
            "max_latency_ms": round(max(durations), 2),
            "error_rate": round(errors / total * 100, 2),
            "top_endpoints": endpoint_counter.most_common(10),
        }

    def get_workflow_stats(self, hours: int = 24) -> Dict[str, Any]:
        rows = self._fetch_all(
            "SELECT * FROM workflow_executions WHERE (julianday('now') - julianday(substr(timestamp,1,19))) * 86400 <= ?",
            (hours * 3600,),
        )
        if not rows:
            return {"total_executions": 0, "avg_duration_ms": 0.0, "success_rate": 0.0, "by_workflow": []}

        total = len(rows)
        durations = [r["duration_ms"] for r in rows]
        successes = sum(1 for r in rows if r["success"])

        from collections import Counter
        wf_counter: Counter = Counter()
        for r in rows:
            wf_counter[r["workflow_name"]] += 1

        return {
            "total_executions": total,
            "avg_duration_ms": round(sum(durations) / total, 2),
            "success_rate": round(successes / total * 100, 2),
            "by_workflow": [{"name": name, "count": count} for name, count in wf_counter.most_common()],
        }

    def get_agent_stats(self, hours: int = 24) -> Dict[str, Any]:
        rows = self._fetch_all(
            "SELECT * FROM agent_executions WHERE (julianday('now') - julianday(substr(timestamp,1,19))) * 86400 <= ?",
            (hours * 3600,),
        )
        if not rows:
            return {"total_executions": 0, "executions_per_agent": [], "avg_duration_ms": 0.0}

        from collections import defaultdict
        agent_map: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            agent_map[r["agent_id"]].append(r["duration_ms"])

        return {
            "total_executions": len(rows),
            "executions_per_agent": [
                {"agent_id": agent_id, "count": len(agent_map[agent_id]), "avg_duration_ms": round(sum(agent_map[agent_id]) / len(agent_map[agent_id]), 2)}
                for agent_id in agent_map
            ],
            "avg_duration_ms": round(sum(r["duration_ms"] for r in rows) / len(rows), 2),
        }

    def get_tool_failure_stats(self, hours: int = 24) -> Dict[str, Any]:
        rows = self._fetch_all(
            "SELECT * FROM tool_failures WHERE (julianday('now') - julianday(substr(timestamp,1,19))) * 86400 <= ?",
            (hours * 3600,),
        )
        if not rows:
            return {"total_failures": 0, "failures_per_tool": []}

        from collections import Counter, defaultdict
        tool_counter: Counter = Counter()
        tool_errors: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            tool_counter[r["tool_name"]] += 1
            tool_errors[r["tool_name"]].append(r["error"])

        return {
            "total_failures": len(rows),
            "failures_per_tool": [
                {"tool_name": name, "count": count, "common_errors": list(set(tool_errors[name]))[:5]}
                for name, count in tool_counter.most_common()
            ],
        }

    def get_approval_stats(self, hours: int = 24) -> Dict[str, Any]:
        rows = self._fetch_all(
            "SELECT * FROM approval_times WHERE (julianday('now') - julianday(substr(timestamp,1,19))) * 86400 <= ?",
            (hours * 3600,),
        )
        if not rows:
            return {"total_approvals": 0, "avg_approval_time_ms": 0.0, "approve_count": 0, "reject_count": 0, "ratio": 0.0}

        total = len(rows)
        durations = [r["duration_ms"] for r in rows]
        approves = sum(1 for r in rows if r["decision"] == "approve")
        rejects = sum(1 for r in rows if r["decision"] == "reject")

        return {
            "total_approvals": total,
            "avg_approval_time_ms": round(sum(durations) / total, 2),
            "approve_count": approves,
            "reject_count": rejects,
            "ratio": round(approves / max(rejects, 1), 2),
        }

    def get_dashboard_performance_stats(self, hours: int = 24) -> Dict[str, Any]:
        api_stats = self.get_api_stats(hours=hours)
        return {
            "api_avg_latency_ms": api_stats.get("avg_latency_ms", 0.0),
            "api_error_rate": api_stats.get("error_rate", 0.0),
            "total_api_requests": api_stats.get("total_requests", 0),
        }

    def get_dashboard(self) -> Dict[str, Any]:
        return {
            "api": self.get_api_stats(24),
            "workflows": self.get_workflow_stats(24),
            "agents": self.get_agent_stats(24),
            "tool_failures": self.get_tool_failure_stats(24),
            "approvals": self.get_approval_stats(24),
            "dashboard": self.get_dashboard_performance_stats(24),
            "generated_at": self._utc_now(),
        }
