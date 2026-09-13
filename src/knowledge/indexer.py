from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore
from src.intelligence.retrieval.rag import RAGEngine
from src.knowledge.loader import (
    load_document as _load_document,
)


class KnowledgeIndexer:
    def __init__(self, store: SQLiteMemoryStore, rag: RAGEngine) -> None:
        self._store = store
        self._rag = rag

    def index_document(self, path: str) -> int:
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Document not found: {path}")

        chunks = _load_document(path)
        if not chunks:
            return 0

        source = str(Path(path).resolve())
        title = chunks[0].metadata.get("title", Path(path).stem)
        doc_type = chunks[0].metadata.get("format", "unknown")
        page_count = len({c.metadata.get("page", -1) for c in chunks if "page" in c.metadata})

        doc_id = self._store.store_knowledge_doc(
            source=source,
            title=title,
            doc_type=doc_type,
            page_count=page_count,
            chunk_count=len(chunks),
        )

        for i, chunk in enumerate(chunks):
            self._store.store_knowledge_chunk(
                doc_id=doc_id,
                chunk_index=i,
                content=chunk.content,
                headings=chunk.metadata.get("headings", []),
                metadata=chunk.metadata,
            )

        return len(chunks)

    def index_directory(self, directory: str) -> int:
        directory = os.path.abspath(directory)
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"Directory not found: {directory}")

        total = 0
        for root, _dirs, files in os.walk(directory):
            for file in files:
                fp = os.path.join(root, file)
                ext = Path(file).suffix.lower()
                if ext in {".md", ".mdx", ".txt", ".log", ".pdf"} or file.endswith(
                    (".sop.md", ".retro.md", ".sop", ".retro")
                ):
                    try:
                        total += self.index_document(fp)
                    except Exception:
                        continue
        return total

    def reindex_all(self) -> int:
        sources = self._store.get_all_knowledge_sources()
        self._store.clear_all_knowledge()
        total = 0
        for source in sources:
            if os.path.isfile(source):
                try:
                    total += self.index_document(source)
                except Exception:
                    continue
        return total

    def remove_document(self, source: str) -> bool:
        return self._store._delete_knowledge_doc_by_source(source)

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        result = self._store.search_knowledge(query, limit=limit)
        entries: list[dict[str, Any]] = []
        for entry in result.entries:
            try:
                import json

                h = (
                    json.loads(entry.get("headings", "[]"))
                    if isinstance(entry.get("headings"), str)
                    else (entry.get("headings") or [])
                )
                m = (
                    json.loads(entry.get("metadata", "{}"))
                    if isinstance(entry.get("metadata"), str)
                    else (entry.get("metadata") or {})
                )
            except (json.JSONDecodeError, TypeError):
                h = []
                m = {}
            doc = self._store.get_knowledge_doc_by_source(m.get("source", ""))
            entries.append(
                {
                    "id": entry.get("id"),
                    "chunk_index": entry.get("chunk_index", 0),
                    "content": entry.get("content", ""),
                    "headings": h,
                    "metadata": m,
                    "doc_source": m.get("source", ""),
                    "doc_title": m.get("title", ""),
                    "doc_type": m.get("format", ""),
                    "created_at": entry.get("created_at", ""),
                }
            )
        return entries

    def get_stats(self) -> dict[str, Any]:
        return self._store.get_knowledge_stats()
