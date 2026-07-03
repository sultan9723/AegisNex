"""Tool Scheduler — scheduled AI tasks with cron-like timing."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

_logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    name: str
    cron_expression: str
    task_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "cron_expression": self.cron_expression,
            "task_type": self.task_type,
            "params": self.params,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "next_run": self.next_run,
        }


class Scheduler:
    def __init__(self, db_path: str = "ai_scheduler.db") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._executor: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._ensure_tables()

    def set_executor(self, fn: Callable[[str, Dict[str, Any]], None]) -> None:
        self._executor = fn

    def _ensure_tables(self) -> None:
        with self._lock:
            _logger.debug("Scheduler ensuring tables in %s", self._db_path)
            conn = sqlite3.connect(self._db_path, timeout=30)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("PRAGMA busy_timeout=30000")
            except sqlite3.OperationalError:
                pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    cron_expression TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    params TEXT DEFAULT '{}',
                    enabled INTEGER DEFAULT 1,
                    last_run TEXT,
                    next_run TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_task_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_ms REAL DEFAULT 0.0
                )
            """)
            conn.commit()
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        _logger.debug("Scheduler opening connection to %s", self._db_path)
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("PRAGMA busy_timeout=30000")
        except sqlite3.OperationalError:
            pass
        return conn

    def add_task(self, name: str, cron_expression: str, task_type: str, params: Optional[Dict[str, Any]] = None) -> int:
        with self._lock:
            conn = self._conn()
            cur = conn.execute(
                "INSERT INTO scheduled_tasks (name, cron_expression, task_type, params) VALUES (?, ?, ?, ?)",
                (name, cron_expression, task_type, json.dumps(params or {})),
            )
            conn.commit()
            conn.close()
            return cur.lastrowid or 0

    def remove_task(self, task_id: int) -> bool:
        with self._lock:
            conn = self._conn()
            conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
            conn.commit()
            conn.close()
            return True

    def list_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            rows = conn.execute("SELECT * FROM scheduled_tasks ORDER BY id").fetchall()
            conn.close()
            result = []
            for r in rows:
                task = dict(r)
                task["params"] = json.loads(task.get("params", "{}"))
                task["enabled"] = bool(task["enabled"])
                result.append(task)
            return result

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            row = conn.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)).fetchone()
            conn.close()
            if row:
                task = dict(row)
                task["params"] = json.loads(task.get("params", "{}"))
                return task
            return None

    def update_task(self, task_id: int, **updates: Any) -> bool:
        allowed = {"name", "cron_expression", "task_type", "params", "enabled", "last_run", "next_run"}
        with self._lock:
            conn = self._conn()
            for key, value in updates.items():
                if key in allowed:
                    if key == "params":
                        value = json.dumps(value)
                    elif key == "enabled":
                        value = 1 if value else 0
                    conn.execute(f"UPDATE scheduled_tasks SET {key} = ? WHERE id = ?", (value, task_id))
            conn.commit()
            conn.close()
            return True

    def log_execution(self, task_name: str, status: str, result: str = "", duration_ms: float = 0.0) -> None:
        with self._lock:
            conn = self._conn()
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO scheduled_task_log (task_name, status, result, started_at, completed_at, duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
                (task_name, status, result, now, now, duration_ms),
            )
            conn.commit()
            conn.close()

    def get_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            rows = conn.execute("SELECT * FROM scheduled_task_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def _parse_cron(self, cron: str) -> List[int]:
        parts = cron.strip().split()
        if len(parts) < 5:
            return []
        now = datetime.now(timezone.utc)
        current = [now.minute, now.hour, now.day, now.month, now.weekday()]
        matches = 0
        for i, part in enumerate(parts[:5]):
            if part == "*":
                matches += 1
            elif "/" in part:
                base = int(part.split("/")[0]) if part.split("/")[0] != "*" else 0
                step = int(part.split("/")[1])
                if (current[i] - base) % step == 0:
                    matches += 1
            elif "," in part:
                if current[i] in [int(x) for x in part.split(",")]:
                    matches += 1
            elif "-" in part:
                lo, hi = int(part.split("-")[0]), int(part.split("-")[1])
                if lo <= current[i] <= hi:
                    matches += 1
            else:
                try:
                    if current[i] == int(part):
                        matches += 1
                except ValueError:
                    pass
        return [matches, len(parts[:5])]

    def _should_run(self, cron: str, last_run: Optional[str]) -> bool:
        match_count, total = self._parse_cron(cron)
        if match_count < total:
            return False
        if last_run:
            try:
                last = datetime.fromisoformat(last_run)
                now = datetime.now(timezone.utc)
                if (now - last).total_seconds() < 30:
                    return False
            except Exception:
                pass
        return True

    def tick(self) -> None:
        tasks = self.list_tasks()
        for task in tasks:
            if not task.get("enabled", True):
                continue
            if self._should_run(task.get("cron_expression", ""), task.get("last_run")):
                if self._executor:
                    try:
                        self._executor(task["name"], task.get("params", {}))
                        self.update_task(task["id"], last_run=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
                        self.log_execution(task["name"], "completed")
                    except Exception as e:
                        self.log_execution(task["name"], "error", str(e))

    def start(self, interval_seconds: int = 60) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, args=(interval_seconds,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _run_loop(self, interval: int) -> None:
        while self._running:
            try:
                self.tick()
            except Exception:
                pass
            time.sleep(interval)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._conn()
            total = conn.execute("SELECT COUNT(*) as cnt FROM scheduled_tasks").fetchone()["cnt"]
            enabled = conn.execute("SELECT COUNT(*) as cnt FROM scheduled_tasks WHERE enabled = 1").fetchone()["cnt"]
            logs = conn.execute("SELECT COUNT(*) as cnt FROM scheduled_task_log").fetchone()["cnt"]
            conn.close()
            return {"total_tasks": total, "enabled_tasks": enabled, "total_executions": logs}
