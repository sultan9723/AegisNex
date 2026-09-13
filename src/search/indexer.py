from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from typing import Any

_logger = logging.getLogger(__name__)

from src.platform_db import PlatformRepository

_SEARCH_DB_PATH: str = ""
_INDEX_LOCK = threading.Lock()


def _get_fts_path() -> str:
    return os.getenv("AEGISNEX_SEARCH_INDEX_DB", "search_index.db")


def _get_conn() -> sqlite3.Connection:
    path = _get_fts_path()
    _logger.debug("Search indexer opening connection to %s", path)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("PRAGMA busy_timeout=30000")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("PRAGMA synchronous=OFF")
    except sqlite3.OperationalError:
        pass
    return conn


def _ensure_fts(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
            domain,
            doc_id,
            title,
            body,
            metadata,
            tokenize='porter unicode61'
        );
        CREATE TABLE IF NOT EXISTS search_index_meta (
            domain TEXT PRIMARY KEY,
            doc_count INTEGER NOT NULL DEFAULT 0,
            last_indexed TEXT
        );
    """)


def _rebuild_fts(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    conn.execute("DELETE FROM search_fts WHERE domain = ?", (rows[0].get("_domain", ""),))
    count = 0
    for row in rows:
        domain = row.pop("_domain", "")
        doc_id = row.pop("_doc_id", "")
        title = row.pop("_title", "")
        body = row.pop("_body", "")
        metadata = json.dumps(row, sort_keys=True, default=str)
        try:
            conn.execute(
                "INSERT INTO search_fts (domain, doc_id, title, body, metadata) VALUES (?, ?, ?, ?, ?)",
                (domain, doc_id, title, body, metadata),
            )
            count += 1
        except sqlite3.IntegrityError:
            continue
    return count


_DOMAIN_INDEXERS: dict[str, str] = {
    "incidents": "incidents",
    "targets": "monitoring_targets",
    "reports": "reports",
    "audit_logs": "audit_logs",
    "containers": "__containers__",
    "runbooks": "__runbooks__",
    "ai_conversations": "__ai_conversations__",
    "knowledge": "__knowledge__",
    "workflows": "__workflows__",
    "settings": "app_settings",
    "compliance": "alert_rules",
}


def _collect_incidents(repo: PlatformRepository, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = repo._fetch_all("SELECT * FROM incidents ORDER BY timestamp DESC LIMIT 5000")
    docs: list[dict[str, Any]] = []
    for r in rows:
        desc = r.get("description", "") or ""
        sid = r.get("service_name", "") or ""
        docs.append(
            {
                "_domain": "incidents",
                "_doc_id": f"inc-{r.get('incident_id')}",
                "_title": f"[{r.get('severity')}] {sid} — {desc[:120]}",
                "_body": json.dumps(
                    {k: v for k, v in r.items() if k not in ("health_check_results",)}
                ),
                **{k: v for k, v in r.items() if k not in ("health_check_results",)},
            }
        )
    return docs


def _collect_targets(repo: PlatformRepository, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = repo._fetch_all("SELECT * FROM monitoring_targets ORDER BY name")
    return [
        {
            "_domain": "targets",
            "_doc_id": f"tgt-{r.get('id')}",
            "_title": r.get("name", ""),
            "_body": f"{r.get('name')} {r.get('address')} {r.get('target_type')}",
            **dict(r),
        }
        for r in rows
    ]


def _collect_reports(repo: PlatformRepository, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = repo._fetch_all("SELECT * FROM reports ORDER BY timestamp DESC LIMIT 2000")
    return [
        {
            "_domain": "reports",
            "_doc_id": f"rpt-{r.get('id')}",
            "_title": f"{r.get('report_type')} — {r.get('summary', '')[:120]}",
            "_body": r.get("summary", ""),
            **dict(r),
        }
        for r in rows
    ]


def _collect_audit_logs(repo: PlatformRepository, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = repo._fetch_all("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 5000")
    return [
        {
            "_domain": "audit_logs",
            "_doc_id": f"aud-{r.get('id')}",
            "_title": f"{r.get('actor')} — {r.get('action')} on {r.get('resource_type')}",
            "_body": str(r.get("details", "")),
            **dict(r),
        }
        for r in rows
    ]


def _collect_settings(repo: PlatformRepository, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = repo._fetch_all("SELECT * FROM app_settings")
    return [
        {
            "_domain": "settings",
            "_doc_id": f"set-{r.get('key')}",
            "_title": r.get("key", ""),
            "_body": r.get("value", ""),
            **dict(r),
        }
        for r in rows
    ]


def _collect_compliance(repo: PlatformRepository, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = repo._fetch_all("SELECT * FROM alert_rules ORDER BY name")
    return [
        {
            "_domain": "compliance",
            "_doc_id": f"cmp-{r.get('id')}",
            "_title": r.get("name", ""),
            "_body": f"{r.get('description')} {r.get('condition')} {r.get('threshold')}",
            **dict(r),
        }
        for r in rows
    ]


def _collect_containers(repo: PlatformRepository, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        from src.docker_scanner import DockerScanner

        scanner = DockerScanner()
        report = scanner.run({"include_all": True})
        if report.get("status") != "ok":
            return []
        containers = report.get("containers", [])
        return [
            {
                "_domain": "containers",
                "_doc_id": f"ctn-{c.get('name', 'unknown')}",
                "_title": c.get("name", "unknown"),
                "_body": f"{c.get('image', '')} {c.get('status', '')} {c.get('health_status', '')}",
                **c,
            }
            for c in containers
        ]
    except Exception:
        return []


def _collect_runbooks(repo: PlatformRepository, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        from src.intelligence.runbooks.registry import get_registry

        registry = get_registry()
        docs: list[dict[str, Any]] = []
        for rb in registry.list_all():
            d = rb.to_dict()
            docs.append(
                {
                    "_domain": "runbooks",
                    "_doc_id": f"rb-{d.get('name', 'unknown')}",
                    "_title": d.get("name", ""),
                    "_body": f"{d.get('description', '')} {' '.join(d.get('tags', []))}",
                    **d,
                }
            )
        return docs
    except Exception:
        return []


def _collect_ai_conversations(
    repo: PlatformRepository, conn: sqlite3.Connection
) -> list[dict[str, Any]]:
    try:
        import os as _os

        from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore

        db_path = _os.getenv("AEGIS_AI_MEMORY_DB", "aegisnex.db")
        store = SQLiteMemoryStore(db_path=db_path)
        rows = (
            store._conn()
            .execute("SELECT * FROM ai_conversations ORDER BY created_at DESC LIMIT 2000")
            .fetchall()
        )
        return [
            {
                "_domain": "ai_conversations",
                "_doc_id": f"aiconv-{r['id']}",
                "_title": str(r["request"])[:200],
                "_body": str(r["response"]),
                **dict(r),
            }
            for r in rows
        ]
    except Exception:
        return []


def _collect_knowledge(repo: PlatformRepository, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        import os as _os

        from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore

        db_path = _os.getenv("AEGIS_AI_MEMORY_DB", "aegisnex.db")
        store = SQLiteMemoryStore(db_path=db_path)
        rows = (
            store._conn()
            .execute("SELECT * FROM ai_learnings ORDER BY created_at DESC LIMIT 2000")
            .fetchall()
        )
        return [
            {
                "_domain": "knowledge",
                "_doc_id": f"know-{r['id']}",
                "_title": str(r["root_cause"])[:200],
                "_body": f"{r['resolution']} {r['service']} {r['category']}",
                **dict(r),
            }
            for r in rows
        ]
    except Exception:
        return []


def _collect_workflows(repo: PlatformRepository, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        from src.intelligence.history import list_history

        histories = list_history(repo, limit=2000)
        return [
            {
                "_domain": "workflows",
                "_doc_id": f"wf-{h.get('id', '')}",
                "_title": str(h.get("objective", "") or h.get("request", ""))[:200],
                "_body": str(h.get("result_text", "")),
                **h,
            }
            for h in histories
        ]
    except Exception:
        return []


_DOMAIN_COLLECTORS = {
    "incidents": _collect_incidents,
    "targets": _collect_targets,
    "reports": _collect_reports,
    "audit_logs": _collect_audit_logs,
    "settings": _collect_settings,
    "compliance": _collect_compliance,
    "containers": _collect_containers,
    "runbooks": _collect_runbooks,
    "ai_conversations": _collect_ai_conversations,
    "knowledge": _collect_knowledge,
    "workflows": _collect_workflows,
}


class SearchIndexer:
    def __init__(self, repo: PlatformRepository) -> None:
        self._repo = repo

    def build_index(self, domains: list[str] | None = None) -> dict[str, Any]:
        with _INDEX_LOCK:
            conn = _get_conn()
            try:
                _ensure_fts(conn)
                if domains is None:
                    domains = list(_DOMAIN_COLLECTORS.keys())
                results: dict[str, Any] = {}
                for domain in domains:
                    if domain not in _DOMAIN_COLLECTORS:
                        results[domain] = {"status": "skipped", "reason": "unknown_domain"}
                        continue
                    try:
                        count = self._index_domain_raw(domain, conn)
                        results[domain] = {"status": "indexed", "count": count}
                    except Exception as exc:
                        results[domain] = {"status": "error", "error": str(exc)}
                conn.commit()
                return results
            finally:
                conn.close()

    def _index_domain_raw(self, domain: str, conn: sqlite3.Connection) -> int:
        collector = _DOMAIN_COLLECTORS[domain]
        docs = collector(self._repo, conn)
        if not docs:
            conn.execute(
                "INSERT OR REPLACE INTO search_index_meta (domain, doc_count, last_indexed) VALUES (?, ?, datetime('now'))",
                (domain, 0),
            )
            conn.commit()
            return 0
        count = _rebuild_fts(conn, docs)
        conn.execute(
            "INSERT OR REPLACE INTO search_index_meta (domain, doc_count, last_indexed) VALUES (?, ?, datetime('now'))",
            (domain, count),
        )
        conn.commit()
        return count

    def index_domain(self, domain: str) -> int:
        if domain not in _DOMAIN_COLLECTORS:
            raise ValueError(
                f"Unknown domain: {domain}. Available: {list(_DOMAIN_COLLECTORS.keys())}"
            )
        with _INDEX_LOCK:
            conn = _get_conn()
            try:
                _ensure_fts(conn)
                count = self._index_domain_raw(domain, conn)
                return count
            finally:
                conn.close()

    def get_index_stats(self) -> dict[str, Any]:
        with _INDEX_LOCK:
            conn = _get_conn()
            try:
                _ensure_fts(conn)
                meta_rows = conn.execute(
                    "SELECT domain, doc_count, last_indexed FROM search_index_meta ORDER BY domain"
                ).fetchall()
                domains: dict[str, Any] = {}
                total_docs = 0
                for row in meta_rows:
                    d = dict(row)
                    domains[str(d["domain"])] = {
                        "doc_count": d["doc_count"],
                        "last_indexed": d["last_indexed"],
                    }
                    total_docs += d["doc_count"]
                row = conn.execute("SELECT COUNT(*) as cnt FROM search_fts").fetchone()
                index_size = row["cnt"] if row else 0
                return {
                    "index_size": index_size,
                    "total_docs": total_docs,
                    "domains": domains,
                    "last_indexed": max(
                        (v["last_indexed"] for v in domains.values() if v["last_indexed"]),
                        default=None,
                    ),
                }
            finally:
                conn.close()

    def clear_index(self, domain: str | None = None) -> None:
        with _INDEX_LOCK:
            conn = _get_conn()
            try:
                _ensure_fts(conn)
                if domain:
                    conn.execute("DELETE FROM search_fts WHERE domain = ?", (domain,))
                    conn.execute("DELETE FROM search_index_meta WHERE domain = ?", (domain,))
                else:
                    conn.execute("DELETE FROM search_fts")
                    conn.execute("DELETE FROM search_index_meta")
                conn.commit()
            finally:
                conn.close()

    def search_fts(
        self, query: str, domain: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        with _INDEX_LOCK:
            conn = _get_conn()
            try:
                _ensure_fts(conn)
                if domain:
                    sql = (
                        "SELECT *, rank FROM search_fts WHERE search_fts MATCH ? AND domain = ? "
                        "ORDER BY rank LIMIT ?"
                    )
                    params = [query, domain, limit]
                else:
                    sql = (
                        "SELECT *, rank FROM search_fts WHERE search_fts MATCH ? "
                        "ORDER BY rank LIMIT ?"
                    )
                    params = [query, limit]
                rows = conn.execute(sql, params).fetchall()
                results = []
                for row in rows:
                    r = dict(row)
                    try:
                        r["metadata"] = json.loads(r.get("metadata", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        r["metadata"] = {}
                    results.append(r)
                return results
            except sqlite3.OperationalError:
                return []
            finally:
                conn.close()
