from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.platform_db import PlatformRepository


@dataclass
class SearchResult:
    domain: str
    id: str
    title: str
    snippet: str
    url: str
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResults:
    results: List[SearchResult] = field(default_factory=list)
    total: int = 0
    domains: Dict[str, int] = field(default_factory=dict)
    query: str = ""
    duration_ms: float = 0.0


DOMAIN_MAP: Dict[str, Dict[str, Any | str]] = {
    "incidents": {"route": "incidents", "icon": "ShieldAlert", "label": "Incidents"},
    "targets": {"route": "infrastructure", "icon": "Crosshair", "label": "Targets"},
    "reports": {"route": "reports", "icon": "FileText", "label": "Reports"},
    "audit_logs": {"route": "audit", "icon": "ScrollText", "label": "Audit Logs"},
    "runbooks": {"route": "ai", "icon": "BookOpen", "label": "Runbooks"},
    "ai_conversations": {"route": "ai", "icon": "Bot", "label": "AI Conversations"},
    "settings": {"route": "settings", "icon": "Settings", "label": "Settings"},
    "containers": {"route": "containers", "icon": "Container", "label": "Containers"},
    "integrations": {"route": "integrations", "icon": "Puzzle", "label": "Integrations"},
    "knowledge": {"route": "ai", "icon": "Library", "label": "Knowledge"},
    "compliance": {"route": "infrastructure", "icon": "Shield", "label": "Compliance"},
    "workflows": {"route": "ai", "icon": "GitBranch", "label": "Workflows"},
}


def _like_clause(columns: List[str], backend: str) -> str:
    if backend == "postgresql":
        return " OR ".join(f"{c}::TEXT ILIKE %s" for c in columns)
    return " OR ".join(f"{c} LIKE ?" for c in columns)


def _like_params(query: str, columns: List[str]) -> List[str]:
    return [f"%{query}%"] * len(columns)


def _make_result(domain: str, row: Dict[str, Any], id_key: str, title_key: str,
                 snippet_key: str | None = None, route_template: str = "",
                 score: float = 1.0) -> SearchResult:
    rid = str(row.get(id_key, ""))
    title = str(row.get(title_key, ""))
    snippet = str(row.get(snippet_key or title_key, ""))[:300]
    route = route_template.format(id=rid) if route_template else f"/{DOMAIN_MAP.get(domain, {}).get('route', domain)}"
    return SearchResult(
        domain=domain,
        id=rid,
        title=title,
        snippet=snippet,
        url=route,
        score=score,
        metadata=dict(row),
    )


class SearchEngine:
    def __init__(self, repo: PlatformRepository, memory_store: Any) -> None:
        self._repo = repo
        self._memory = memory_store

    def search(self, query: str, domain: str = "all", limit: int = 20,
               filters: dict | None = None) -> SearchResults:
        start = time.monotonic()
        q = query.strip()
        if not q:
            return SearchResults(query=q)

        domain_map: Dict[str, str] = {
            "incidents": "incidents",
            "targets": "targets",
            "reports": "reports",
            "audit_logs": "audit_logs",
            "runbooks": "runbooks",
            "ai_conversations": "ai_conversations",
            "settings": "settings",
            "containers": "containers",
            "integrations": "integrations",
            "knowledge": "knowledge",
            "compliance": "compliance",
            "workflows": "workflows",
        }

        if domain != "all" and domain not in domain_map:
            return SearchResults(query=q)

        domains_to_search = [domain] if domain != "all" else list(domain_map.keys())
        per_domain = max(1, limit // max(1, len(domains_to_search)))

        all_results: List[SearchResult] = []
        domain_counts: Dict[str, int] = {}

        for d in domains_to_search:
            try:
                method = getattr(self, f"search_{domain_map[d]}", None)
                if method is None:
                    continue
                results = method(q, limit=per_domain)
                if results:
                    all_results.extend(results)
                    domain_counts[d] = len(results)
            except Exception:
                continue

        all_results.sort(key=lambda r: r.score, reverse=True)
        all_results = all_results[:limit]
        elapsed = (time.monotonic() - start) * 1000

        return SearchResults(
            results=all_results,
            total=len(all_results),
            domains=domain_counts,
            query=q,
            duration_ms=round(elapsed, 2),
        )

    def search_incidents(self, query: str, limit: int = 10) -> List[SearchResult]:
        p = self._repo.placeholder if hasattr(self._repo, 'placeholder') else "?"
        cols = ["incident_id", "description", "service_name", "severity"]
        where = _like_clause(cols, self._repo.backend)
        sql = f"SELECT * FROM incidents WHERE {where} ORDER BY timestamp DESC LIMIT {p}"
        rows = self._repo._fetch_all(sql, _like_params(query, cols) + [limit])
        return [_make_result("incidents", r, "incident_id", "description",
                             route_template="/incidents/{id}", score=2.0)
                for r in rows]

    def search_targets(self, query: str, limit: int = 10) -> List[SearchResult]:
        p = self._repo.placeholder
        cols = ["name", "address", "target_type"]
        where = _like_clause(cols, self._repo.backend)
        sql = f"SELECT * FROM monitoring_targets WHERE {where} ORDER BY name LIMIT {p}"
        rows = self._repo._fetch_all(sql, _like_params(query, cols) + [limit])
        return [_make_result("targets", r, "id", "name", "address",
                             route_template="/infrastructure", score=1.5)
                for r in rows]

    def search_reports(self, query: str, limit: int = 10) -> List[SearchResult]:
        p = self._repo.placeholder
        cols = ["report_type", "status", "summary", "path"]
        where = _like_clause(cols, self._repo.backend)
        sql = f"SELECT * FROM reports WHERE {where} ORDER BY timestamp DESC LIMIT {p}"
        rows = self._repo._fetch_all(sql, _like_params(query, cols) + [limit])
        return [_make_result("reports", r, "id", "summary", "report_type",
                             route_template="/reports", score=1.5)
                for r in rows]

    def search_audit_logs(self, query: str, limit: int = 10) -> List[SearchResult]:
        p = self._repo.placeholder
        cols = ["actor", "action", "resource_type", "resource_id", "details"]
        where = _like_clause(cols, self._repo.backend)
        sql = f"SELECT * FROM audit_logs WHERE {where} ORDER BY timestamp DESC LIMIT {p}"
        rows = self._repo._fetch_all(sql, _like_params(query, cols) + [limit])
        return [_make_result("audit_logs", r, "id", "action", "details",
                             route_template="/audit", score=1.0)
                for r in rows]

    def search_runbooks(self, query: str, limit: int = 10) -> List[SearchResult]:
        try:
            from src.intelligence.runbooks.registry import get_registry
            registry = get_registry()
            ql = query.lower()
            results: List[SearchResult] = []
            for rb in registry.list_all():
                d = rb.to_dict()
                name = d.get("name", "")
                desc = d.get("description", "")
                if ql in name.lower() or ql in desc.lower():
                    results.append(SearchResult(
                        domain="runbooks",
                        id=name,
                        title=name,
                        snippet=desc[:300],
                        url="/ai",
                        score=1.5,
                        metadata=d,
                    ))
            return results[:limit]
        except Exception:
            return []

    def search_ai_conversations(self, query: str, limit: int = 10) -> List[SearchResult]:
        try:
            res = self._memory.search_conversations(query, limit)  # type: ignore
            return [SearchResult(
                domain="ai_conversations",
                id=str(e.get("id", "")),
                title=e.get("request", "")[:200],
                snippet=e.get("response", "")[:300],
                url="/ai",
                score=float(e.get("confidence", 0.5)),
                metadata=e,
            ) for e in res.entries]
        except Exception:
            return []

    def search_settings(self, query: str, limit: int = 10) -> List[SearchResult]:
        try:
            settings = self._repo.get_settings()
            ql = query.lower()
            results: List[SearchResult] = []
            for key, value in settings.items():
                if ql in key.lower() or ql in value.lower():
                    results.append(SearchResult(
                        domain="settings",
                        id=key,
                        title=key,
                        snippet=value[:300],
                        url="/settings",
                        score=1.0,
                        metadata={"key": key, "value": value},
                    ))
            return results[:limit]
        except Exception:
            return []

    def search_containers(self, query: str, limit: int = 10) -> List[SearchResult]:
        try:
            from src.docker_scanner import DockerScanner
            scanner = DockerScanner()
            report = scanner.run({"include_all": True})
            if report.get("status") != "ok":
                return []
            containers = report.get("containers", [])
            ql = query.lower()
            results: List[SearchResult] = []
            for c in containers:
                name = str(c.get("name", ""))
                image = str(c.get("image", ""))
                status = str(c.get("status", ""))
                if ql in name.lower() or ql in image.lower() or ql in status.lower():
                    results.append(SearchResult(
                        domain="containers",
                        id=name,
                        title=name,
                        snippet=f"{image} — {status}",
                        url="/containers",
                        score=1.5,
                        metadata=c,
                    ))
            return results[:limit]
        except Exception:
            return []

    def search_integrations(self, query: str, limit: int = 10) -> List[SearchResult]:
        try:
            from src.integrations import list_integrations
            integrations = list_integrations()
            ql = query.lower()
            results: List[SearchResult] = []
            for name, provider_cls in integrations.items():
                if ql in name.lower():
                    results.append(SearchResult(
                        domain="integrations",
                        id=name,
                        title=name,
                        snippet=f"{provider_cls.__doc__ or ''}"[:300],
                        url="/integrations",
                        score=1.0,
                    ))
            installed = self._memory.get_integrations()
            for inst in installed:
                name = str(inst.get("name", ""))
                if ql in name.lower() and not any(r.id == name for r in results):
                    results.append(SearchResult(
                        domain="integrations",
                        id=name,
                        title=name,
                        snippet=f"AI integration — {'enabled' if inst.get('enabled') else 'disabled'}",
                        url="/integrations",
                        score=1.0,
                        metadata=inst,
                    ))
            return results[:limit]
        except Exception:
            return []

    def search_knowledge(self, query: str, limit: int = 10) -> List[SearchResult]:
        try:
            res = self._memory.search_learnings(query, limit)
            return [SearchResult(
                domain="knowledge",
                id=str(e.get("id", "")),
                title=e.get("root_cause", "")[:200],
                snippet=e.get("resolution", "")[:300],
                url="/ai",
                score=float(e.get("confidence", 0.5)),
                metadata=e,
            ) for e in res.entries]
        except Exception:
            return []

    def search_compliance(self, query: str, limit: int = 10) -> List[SearchResult]:
        try:
            results: List[SearchResult] = []
            p = self._repo.placeholder
            cols = ["name", "description", "target_type", "severity"]
            where = _like_clause(cols, self._repo.backend)
            sql = f"SELECT * FROM alert_rules WHERE {where} ORDER BY name LIMIT {p}"
            rows = self._repo._fetch_all(sql, _like_params(query, cols) + [limit])
            for r in rows:
                results.append(_make_result("compliance", r, "id", "name",
                                            "description", score=1.5))
            return results
        except Exception:
            return []

    def search_workflows(self, query: str, limit: int = 10) -> List[SearchResult]:
        try:
            from src.intelligence.history import list_history
            histories = list_history(self._repo, limit=100)
            ql = query.lower()
            results: List[SearchResult] = []
            for h in histories:
                obj = str(h.get("objective", ""))
                req = str(h.get("request", ""))
                if ql in obj.lower() or ql in req.lower():
                    results.append(SearchResult(
                        domain="workflows",
                        id=str(h.get("id", "")),
                        title=obj[:200] or req[:200],
                        snippet=str(h.get("result_text", ""))[:300],
                        url="/ai",
                        score=float(h.get("confidence", 0.5)),
                        metadata=h,
                    ))
            return results[:limit]
        except Exception:
            return []
