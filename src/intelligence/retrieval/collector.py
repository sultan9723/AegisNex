from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.intelligence.retrieval.base import RetrievalResult, SourceDocument


class KnowledgeCollector:
    def __init__(self, repo: Any = None, runbooks_dir: Optional[str] = None) -> None:
        self._repo = repo
        self._runbooks_dir = runbooks_dir or str(Path(__file__).resolve().parents[1] / "runbooks")

    def collect_incidents(self, query: str, limit: int = 5) -> List[SourceDocument]:
        if self._repo is None:
            return []
        docs: List[SourceDocument] = []
        try:
            terms = query.lower().split()
            incidents = self._repo.get_incidents(limit=limit * 3)
            raw = incidents if isinstance(incidents, list) else incidents.get("incidents", [])
            for inc in raw[:limit]:
                text = f"Incident {inc.get('incident_id', '?')}: {inc.get('description', inc.get('summary', ''))} (severity={inc.get('severity', '?')}, service={inc.get('service_name', '?')}, status={inc.get('status', '?')})"
                score = sum(1 for t in terms if t in text.lower()) / max(len(terms), 1)
                docs.append(SourceDocument(content=text, source=f"incident:{inc.get('incident_id', '?')}", source_type="incident", relevance_score=score, timestamp=str(inc.get("timestamp", "")), metadata=dict(inc)))
        except Exception:
            pass
        docs.sort(key=lambda d: d.relevance_score, reverse=True)
        return docs[:limit]

    def collect_audit_logs(self, query: str, limit: int = 5) -> List[SourceDocument]:
        if self._repo is None:
            return []
        docs: List[SourceDocument] = []
        try:
            terms = query.lower().split()
            logs = self._repo.get_audit_logs(limit=limit * 3)
            raw = logs if isinstance(logs, list) else logs.get("logs", [])
            for log in raw[:limit]:
                text = f"Audit: {log.get('action', '?')} on {log.get('target', '?')} by {log.get('actor', '?')} — {log.get('details', '')}"
                score = sum(1 for t in terms if t in text.lower()) / max(len(terms), 1)
                docs.append(SourceDocument(content=text, source="audit", source_type="audit", relevance_score=score, timestamp=str(log.get("timestamp", "")), metadata=dict(log)))
        except Exception:
            pass
        docs.sort(key=lambda d: d.relevance_score, reverse=True)
        return docs[:limit]

    def collect_reports(self, query: str, limit: int = 3) -> List[SourceDocument]:
        if self._repo is None:
            return []
        docs: List[SourceDocument] = []
        try:
            from src.intelligence.tools import _report_tool
            result = _report_tool(repo=self._repo, report_type="weekly")
            report = result.get("report", {})
            text = f"Report ({report.get('period', '?')}): {report.get('summary', '')}"
            docs.append(SourceDocument(content=text, source="report:weekly", source_type="report", relevance_score=0.5, timestamp=str(report.get("generated_at", "")), metadata=report))
        except Exception:
            pass
        return docs[:limit]

    def collect_monitoring_history(self, query: str, limit: int = 5) -> List[SourceDocument]:
        if self._repo is None:
            return []
        docs: List[SourceDocument] = []
        try:
            terms = query.lower().split()
            targets = self._repo.get_monitoring_targets()
            raw = targets if isinstance(targets, list) else targets.get("targets", [])
            for tgt in raw[:limit]:
                text = f"Target {tgt.get('name', '?')} ({tgt.get('target_type', '?')}): {tgt.get('address', '?')} — status={tgt.get('last_status_code', 'N/A')}, last checked={tgt.get('last_successful_check_at', 'never')}"
                score = sum(1 for t in terms if t in text.lower()) / max(len(terms), 1)
                docs.append(SourceDocument(content=text, source=f"target:{tgt.get('name', '?')}", source_type="monitoring", relevance_score=score, metadata=dict(tgt)))
        except Exception:
            pass
        docs.sort(key=lambda d: d.relevance_score, reverse=True)
        return docs[:limit]

    def collect_runbooks(self, query: str, limit: int = 5) -> List[SourceDocument]:
        docs: List[SourceDocument] = []
        runbooks_dir = Path(self._runbooks_dir)
        if not runbooks_dir.is_dir():
            return docs
        terms = query.lower().split()
        files = list(runbooks_dir.glob("*.md")) + list(runbooks_dir.glob("*.mdx"))
        for fp in files:
            try:
                content = fp.read_text(encoding="utf-8")
                title = fp.stem.replace("-", " ").replace("_", " ")
                score = sum(1 for t in terms if t in content.lower() or t in title.lower()) / max(len(terms), 1)
                if score > 0:
                    docs.append(SourceDocument(content=content[:2000], source=f"runbook:{fp.name}", source_type="runbook", relevance_score=score, metadata={"path": str(fp), "title": title}))
            except Exception:
                continue
        docs.sort(key=lambda d: d.relevance_score, reverse=True)
        return docs[:limit]

    def collect_all(self, query: str, limit: int = 5) -> List[SourceDocument]:
        all_docs: List[SourceDocument] = []
        collectors = [
            self.collect_incidents,
            self.collect_audit_logs,
            self.collect_reports,
            self.collect_monitoring_history,
            self.collect_runbooks,
        ]
        for collector in collectors:
            try:
                all_docs.extend(collector(query, limit))
            except Exception:
                continue
        all_docs.sort(key=lambda d: d.relevance_score, reverse=True)
        seen = set()
        deduped = []
        for doc in all_docs:
            key = f"{doc.source}:{doc.source_type}"
            if key not in seen:
                seen.add(key)
                deduped.append(doc)
        return deduped[:limit]
