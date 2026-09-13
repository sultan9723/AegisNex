from __future__ import annotations

from typing import Any

from src.intelligence.retrieval.rag import RAGEngine
from src.knowledge.indexer import KnowledgeIndexer


class KnowledgeRetriever:
    def __init__(self, rag: RAGEngine, indexer: KnowledgeIndexer) -> None:
        self._rag = rag
        self._indexer = indexer

    def retrieve(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        if not query.strip():
            return []

        rag_result = self._rag.retrieve(query, limit=limit)
        kb_results = self._indexer.search(query, limit=limit)

        merged: list[dict[str, Any]] = []
        seen_sources: set = set()

        for doc in rag_result.documents:
            key = f"rag:{doc.source}"
            if key not in seen_sources:
                seen_sources.add(key)
                merged.append(
                    {
                        "content": doc.content,
                        "source": doc.source,
                        "source_type": doc.source_type,
                        "relevance_score": doc.relevance_score,
                        "timestamp": doc.timestamp,
                        "strategy": "rag",
                        "metadata": doc.metadata,
                    }
                )

        for entry in kb_results:
            key = f"kb:{entry.get('doc_source', '')}:{entry.get('chunk_index', 0)}"
            if key not in seen_sources:
                seen_sources.add(key)
                merged.append(
                    {
                        "content": entry.get("content", ""),
                        "source": entry.get("doc_source", ""),
                        "source_type": entry.get("doc_type", "knowledge"),
                        "relevance_score": 0.5,
                        "timestamp": entry.get("created_at", ""),
                        "strategy": "knowledge_base",
                        "metadata": {
                            "headings": entry.get("headings", []),
                            "title": entry.get("doc_title", ""),
                            "doc_type": entry.get("doc_type", ""),
                        },
                    }
                )

        merged.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return merged[:limit]

    def retrieve_with_filters(
        self, query: str, doc_types: list[str], limit: int = 10
    ) -> list[dict[str, Any]]:
        if not query.strip():
            return []

        rag_result = self._rag.retrieve(query, limit=limit)
        kb_results = self._indexer.search(query, limit=limit * 2)

        merged: list[dict[str, Any]] = []

        for doc in rag_result.documents:
            if doc.source_type in doc_types or not doc_types:
                merged.append(
                    {
                        "content": doc.content,
                        "source": doc.source,
                        "source_type": doc.source_type,
                        "relevance_score": doc.relevance_score,
                        "timestamp": doc.timestamp,
                        "strategy": "rag",
                        "metadata": doc.metadata,
                    }
                )

        for entry in kb_results:
            dt = entry.get("doc_type", "")
            if dt in doc_types or not doc_types:
                merged.append(
                    {
                        "content": entry.get("content", ""),
                        "source": entry.get("doc_source", ""),
                        "source_type": dt,
                        "relevance_score": 0.5,
                        "timestamp": entry.get("created_at", ""),
                        "strategy": "knowledge_base",
                        "metadata": {
                            "headings": entry.get("headings", []),
                            "title": entry.get("doc_title", ""),
                            "doc_type": dt,
                        },
                    }
                )

        merged.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return merged[:limit]

    def get_relevant_context(self, query: str) -> str:
        results = self.retrieve(query, limit=8)
        if not results:
            return ""

        parts: list[str] = []
        for r in results:
            strategy = r.get("strategy", "?")
            source = r.get("source", "?")
            source_type = r.get("source_type", "?")
            content = r.get("content", "")[:800]
            parts.append(f"[{source_type}|{strategy}] {source}\n{content}")

        return "\n\n".join(parts)
