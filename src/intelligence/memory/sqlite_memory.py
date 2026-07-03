from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import asdict
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)

from src.intelligence.memory.base import MemoryStore, MemorySearchResult

_LOCAL = threading.local()


def _get_conn(db_path: str) -> sqlite3.Connection:
    if not hasattr(_LOCAL, "conn") or _LOCAL.conn is None:
        _logger.debug("SQLiteMemoryStore opening connection to %s", db_path)
        _LOCAL.conn = sqlite3.connect(db_path, timeout=30)
        _LOCAL.conn.row_factory = sqlite3.Row
        try:
            _LOCAL.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        try:
            _LOCAL.conn.execute("PRAGMA busy_timeout=30000")
        except sqlite3.OperationalError:
            pass
        try:
            _LOCAL.conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.OperationalError:
            pass
    return _LOCAL.conn


class SQLiteMemoryStore(MemoryStore):
    def __init__(self, db_path: str = "memory.db") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_tables()

    def _conn(self) -> sqlite3.Connection:
        return _get_conn(self._db_path)

    def _ensure_tables(self) -> None:
        with self._lock:
            conn = self._conn()
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS ai_conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request TEXT NOT NULL,
                    response TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    goal_achieved INTEGER DEFAULT 0,
                    steps TEXT DEFAULT '[]',
                    errors TEXT DEFAULT '[]',
                    corrections TEXT DEFAULT '[]',
                    duration_ms REAL DEFAULT 0.0,
                    provider TEXT DEFAULT '',
                    model TEXT DEFAULT '',
                    extra TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS ai_incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    severity TEXT DEFAULT 'info',
                    service TEXT DEFAULT '',
                    status TEXT DEFAULT 'open',
                    resolved INTEGER DEFAULT 0,
                    extra TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS ai_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    was_accepted INTEGER,
                    extra TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS ai_remediations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    successful INTEGER DEFAULT 0,
                    triggered_by TEXT DEFAULT '',
                    duration_ms REAL DEFAULT 0.0,
                    extra TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS ai_tool_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    parameters TEXT DEFAULT '{}',
                    result_status TEXT DEFAULT '',
                    duration_ms REAL DEFAULT 0.0,
                    error TEXT DEFAULT '',
                    extra TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS ai_integrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    enabled INTEGER DEFAULT 1,
                    credentials TEXT DEFAULT '{}',
                    settings TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS ai_learnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    root_cause TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    service TEXT DEFAULT '',
                    severity TEXT DEFAULT 'info',
                    category TEXT DEFAULT '',
                    outcome TEXT DEFAULT '',
                    confidence REAL DEFAULT 0.0,
                    tags TEXT DEFAULT '[]',
                    extra TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_created ON ai_conversations(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_incidents_created ON ai_incidents(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_recommendations_created ON ai_recommendations(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_remediations_created ON ai_remediations(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_tool_executions_created ON ai_tool_executions(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_learnings_created ON ai_learnings(created_at DESC);
                CREATE TABLE IF NOT EXISTS ai_knowledge_docs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL UNIQUE,
                    title TEXT DEFAULT '',
                    doc_type TEXT DEFAULT '',
                    page_count INTEGER DEFAULT 0,
                    chunk_count INTEGER DEFAULT 0,
                    indexed_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS ai_knowledge_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER NOT NULL,
                    chunk_index INTEGER DEFAULT 0,
                    content TEXT NOT NULL,
                    headings TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (doc_id) REFERENCES ai_knowledge_docs(id) ON DELETE CASCADE
                );
            """)

    # ---- Integrations ----

    def store_integration(self, name: str, enabled: bool = True, credentials: Optional[Dict[str, Any]] = None, settings: Optional[Dict[str, Any]] = None) -> int:
        with self._lock:
            cur = self._conn().execute(
                "INSERT OR REPLACE INTO ai_integrations (name, enabled, credentials, settings) VALUES (?,?,?,?)",
                (name, 1 if enabled else 0, json.dumps(credentials or {}), json.dumps(settings or {})),
            )
            self._conn().commit()
            return cur.lastrowid or 0

    def remove_integration(self, name: str) -> bool:
        with self._lock:
            cur = self._conn().execute("DELETE FROM ai_integrations WHERE name = ?", (name,))
            self._conn().commit()
            return cur.rowcount > 0

    def get_integrations(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute("SELECT * FROM ai_integrations ORDER BY created_at DESC").fetchall()
            integrations = []
            for r in rows:
                integration = dict(r)
                integration["credentials"] = json.loads(integration.get("credentials", "{}"))
                integration["settings"] = json.loads(integration.get("settings", "{}"))
                integration["enabled"] = bool(integration.get("enabled", False))
                integrations.append(integration)
            return integrations

    # ---- Store ----

    def store_conversation(self, request: str, response: str, confidence: float = 0.0, goal_achieved: bool = False, **extra: Any) -> int:
        with self._lock:
            cur = self._conn().execute(
                "INSERT INTO ai_conversations (request, response, confidence, goal_achieved, steps, errors, corrections, duration_ms, provider, model, extra) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    request,
                    response,
                    confidence,
                    1 if goal_achieved else 0,
                    json.dumps(extra.pop("steps", [])),
                    json.dumps(extra.pop("errors", [])),
                    json.dumps(extra.pop("corrections", [])),
                    extra.pop("duration_ms", 0.0),
                    extra.pop("provider", ""),
                    extra.pop("model", ""),
                    json.dumps(extra),
                ),
            )
            self._conn().commit()
            return cur.lastrowid or 0

    def store_incident(self, incident_id: str, summary: str, severity: str = "info", service: str = "", **extra: Any) -> int:
        with self._lock:
            cur = self._conn().execute(
                "INSERT INTO ai_incidents (incident_id, summary, severity, service, status, resolved, extra) VALUES (?,?,?,?,?,?,?)",
                (incident_id, summary, severity, service, extra.pop("status", "open"), 1 if extra.pop("resolved", False) else 0, json.dumps(extra)),
            )
            self._conn().commit()
            return cur.lastrowid or 0

    def store_recommendation(self, request: str, recommendation: str, confidence: float = 0.0, **extra: Any) -> int:
        with self._lock:
            cur = self._conn().execute(
                "INSERT INTO ai_recommendations (request, recommendation, confidence, was_accepted, extra) VALUES (?,?,?,?,?)",
                (request, recommendation, confidence, extra.pop("was_accepted", None), json.dumps(extra)),
            )
            self._conn().commit()
            return cur.lastrowid or 0

    def store_remediation(self, action: str, target: str, successful: bool = False, **extra: Any) -> int:
        with self._lock:
            cur = self._conn().execute(
                "INSERT INTO ai_remediations (action, target, successful, triggered_by, duration_ms, extra) VALUES (?,?,?,?,?,?)",
                (action, target, 1 if successful else 0, extra.pop("triggered_by", ""), extra.pop("duration_ms", 0.0), json.dumps(extra)),
            )
            self._conn().commit()
            return cur.lastrowid or 0

    def store_tool_execution(self, tool_name: str, parameters: Optional[Dict[str, Any]] = None, result_status: str = "", duration_ms: float = 0.0, **extra: Any) -> int:
        with self._lock:
            cur = self._conn().execute(
                "INSERT INTO ai_tool_executions (tool_name, parameters, result_status, duration_ms, error, extra) VALUES (?,?,?,?,?,?)",
                (tool_name, json.dumps(parameters or {}), result_status, duration_ms, extra.pop("error", ""), json.dumps(extra)),
            )
            self._conn().commit()
            return cur.lastrowid or 0

    # ---- Search (keyword-based; swapable with vector search later) ----

    _TABLE_COLUMNS: Dict[str, List[str]] = {
        "ai_conversations": ["request", "response"],
        "ai_incidents": ["summary", "incident_id", "service", "severity"],
        "ai_recommendations": ["request", "recommendation"],
        "ai_remediations": ["action", "target", "triggered_by"],
        "ai_tool_executions": ["tool_name", "result_status", "error"],
        "ai_learnings": ["root_cause", "resolution", "service", "category"],
        "ai_knowledge_chunks": ["content"],
    }

    def _search_table(self, table: str, query: str, limit: int = 10) -> MemorySearchResult:
        terms = query.strip().lower().split()
        if not terms:
            return MemorySearchResult(entries=[], count=0, total=0, query=query)
        cols = self._TABLE_COLUMNS.get(table, ["request"])
        conditions = " OR ".join(f"({' OR '.join(f'LOWER({c}) LIKE ?' for c in cols)})" for _ in terms)
        params = []
        for t in terms:
            like = f"%{t}%"
            params.extend([like] * len(cols))
        with self._lock:
            conn = self._conn()
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table} WHERE {conditions}", params).fetchone()
            total = row["cnt"] if row else 0
            rows = conn.execute(f"SELECT * FROM {table} WHERE {conditions} ORDER BY created_at DESC LIMIT ?", [*params, limit]).fetchall()
            entries = [dict(r) for r in rows]
            return MemorySearchResult(entries=entries, count=len(entries), total=total, query=query)

    def search_conversations(self, query: str, limit: int = 10) -> MemorySearchResult:
        return self._search_table("ai_conversations", query, limit)

    def search_incidents(self, query: str, limit: int = 10) -> MemorySearchResult:
        return self._search_table("ai_incidents", query, limit)

    def search_recommendations(self, query: str, limit: int = 10) -> MemorySearchResult:
        return self._search_table("ai_recommendations", query, limit)

    def search_remediations(self, query: str, limit: int = 10) -> MemorySearchResult:
        return self._search_table("ai_remediations", query, limit)

    def store_learning(self, root_cause: str, resolution: str, service: str = "", severity: str = "info", category: str = "", outcome: str = "", confidence: float = 0.0, tags: Optional[List[str]] = None, **extra: Any) -> int:
        with self._lock:
            cur = self._conn().execute(
                "INSERT INTO ai_learnings (root_cause, resolution, service, severity, category, outcome, confidence, tags, extra) VALUES (?,?,?,?,?,?,?,?,?)",
                (root_cause, resolution, service, severity, category, outcome, confidence, json.dumps(tags or []), json.dumps(extra)),
            )
            self._conn().commit()
            return cur.lastrowid or 0

    def search_learnings(self, query: str, limit: int = 10) -> MemorySearchResult:
        return self._search_table("ai_learnings", query, limit)

    def get_recent_learnings(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute("SELECT * FROM ai_learnings ORDER BY created_at DESC LIMIT ?", [limit]).fetchall()
            return [dict(r) for r in rows]

    def search_tool_executions(self, query: str, limit: int = 10) -> MemorySearchResult:
        results = self._search_table("ai_tool_executions", query, limit)
        return results

    def search_all(self, query: str, limit: int = 10) -> MemorySearchResult:
        combined = MemorySearchResult(entries=[], count=0, total=0, query=query)
        for table in ["ai_conversations", "ai_incidents", "ai_recommendations", "ai_remediations", "ai_tool_executions", "ai_learnings"]:
            res = self._search_table(table, query, limit)
            for e in res.entries:
                e["_source_table"] = table
            combined.entries.extend(res.entries)
            combined.total += res.total
        combined.entries = sorted(combined.entries, key=lambda x: x.get("created_at", ""), reverse=True)[:limit]
        combined.count = len(combined.entries)
        return combined

    # ---- Recent ----

    def get_recent_conversations(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute("SELECT * FROM ai_conversations ORDER BY created_at DESC LIMIT ?", [limit]).fetchall()
            return [dict(r) for r in rows]

    def get_recent_incidents(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute("SELECT * FROM ai_incidents ORDER BY created_at DESC LIMIT ?", [limit]).fetchall()
            return [dict(r) for r in rows]

    def get_recent_recommendations(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute("SELECT * FROM ai_recommendations ORDER BY created_at DESC LIMIT ?", [limit]).fetchall()
            return [dict(r) for r in rows]

    def get_recent_remediations(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute("SELECT * FROM ai_remediations ORDER BY created_at DESC LIMIT ?", [limit]).fetchall()
            return [dict(r) for r in rows]

    # ---- Knowledge Base ----

    def store_knowledge_doc(self, source: str, title: str = "", doc_type: str = "", page_count: int = 0, chunk_count: int = 0) -> int:
        with self._lock:
            existing = self._conn().execute("SELECT id FROM ai_knowledge_docs WHERE source = ?", (source,)).fetchone()
            if existing:
                self._conn().execute(
                    "UPDATE ai_knowledge_docs SET title=?, doc_type=?, page_count=?, chunk_count=?, indexed_at=datetime('now') WHERE id=?",
                    (title, doc_type, page_count, chunk_count, existing["id"]),
                )
                self._conn().execute("DELETE FROM ai_knowledge_chunks WHERE doc_id = ?", (existing["id"],))
                self._conn().commit()
                return existing["id"]
            cur = self._conn().execute(
                "INSERT INTO ai_knowledge_docs (source, title, doc_type, page_count, chunk_count) VALUES (?,?,?,?,?)",
                (source, title, doc_type, page_count, chunk_count),
            )
            self._conn().commit()
            return cur.lastrowid or 0

    def get_knowledge_doc_by_source(self, source: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn().execute("SELECT * FROM ai_knowledge_docs WHERE source = ?", (source,)).fetchone()
            return dict(row) if row else None

    def delete_knowledge_doc(self, doc_id: int) -> bool:
        with self._lock:
            self._conn().execute("DELETE FROM ai_knowledge_chunks WHERE doc_id = ?", (doc_id,))
            cur = self._conn().execute("DELETE FROM ai_knowledge_docs WHERE id = ?", (doc_id,))
            self._conn().commit()
            return cur.rowcount > 0

    def _delete_knowledge_doc_by_source(self, source: str) -> bool:
        doc = self.get_knowledge_doc_by_source(source)
        if doc is None:
            return False
        return self.delete_knowledge_doc(doc["id"])

    def store_knowledge_chunk(self, doc_id: int, chunk_index: int, content: str, headings: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None) -> int:
        with self._lock:
            cur = self._conn().execute(
                "INSERT INTO ai_knowledge_chunks (doc_id, chunk_index, content, headings, metadata) VALUES (?,?,?,?,?)",
                (doc_id, chunk_index, content, json.dumps(headings or []), json.dumps(metadata or {})),
            )
            self._conn().commit()
            return cur.lastrowid or 0

    def search_knowledge(self, query: str, limit: int = 10) -> MemorySearchResult:
        return self._search_table("ai_knowledge_chunks", query, limit)

    def list_knowledge_docs(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute("SELECT * FROM ai_knowledge_docs ORDER BY indexed_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_all_knowledge_sources(self) -> List[str]:
        with self._lock:
            rows = self._conn().execute("SELECT source FROM ai_knowledge_docs").fetchall()
            return [r["source"] for r in rows]

    def clear_all_knowledge(self) -> None:
        with self._lock:
            self._conn().execute("DELETE FROM ai_knowledge_chunks")
            self._conn().execute("DELETE FROM ai_knowledge_docs")
            self._conn().commit()

    def get_knowledge_stats(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._conn()
            doc_row = conn.execute("SELECT COUNT(*) as cnt FROM ai_knowledge_docs").fetchone()
            chunk_row = conn.execute("SELECT COUNT(*) as cnt FROM ai_knowledge_chunks").fetchone()
            sources = conn.execute("SELECT source FROM ai_knowledge_docs ORDER BY indexed_at DESC").fetchall()
            return {
                "document_count": doc_row["cnt"] if doc_row else 0,
                "chunk_count": chunk_row["cnt"] if chunk_row else 0,
                "sources": [r["source"] for r in sources],
            }

    # ---- Stats ----

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._conn()
            stats: Dict[str, Any] = {}
            for table in ["ai_conversations", "ai_incidents", "ai_recommendations", "ai_remediations", "ai_tool_executions", "ai_learnings"]:
                row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
                stats[table.replace("ai_", "")] = row["cnt"] if row else 0
            row = conn.execute("SELECT COUNT(*) as cnt FROM ai_conversations WHERE goal_achieved = 1").fetchone()
            stats["successful_conversations"] = row["cnt"] if row else 0
            row = conn.execute("SELECT COUNT(*) as cnt FROM ai_remediations WHERE successful = 1").fetchone()
            stats["successful_remediations"] = row["cnt"] if row else 0
            row = conn.execute("SELECT AVG(duration_ms) as avg_dur FROM ai_tool_executions").fetchone()
            stats["avg_tool_duration_ms"] = round(row["avg_dur"], 2) if row and row["avg_dur"] else 0.0
            row = conn.execute("SELECT AVG(confidence) as avg_conf FROM ai_conversations").fetchone()
            stats["avg_confidence"] = round(row["avg_conf"], 4) if row and row["avg_conf"] else 0.0
            return stats
