from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceDocument:
    content: str
    source: str
    source_type: str
    relevance_score: float = 0.0
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    documents: list[SourceDocument]
    query: str
    total_found: int = 0
    execution_ms: float = 0.0
    strategy: str = ""

    @property
    def context_text(self) -> str:
        parts = []
        for doc in self.documents:
            header = f"[{doc.source_type}] {doc.source}"
            parts.append(f"{header}\n{doc.content}")
        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "documents": [
                {
                    "content": d.content[:500],
                    "source": d.source,
                    "source_type": d.source_type,
                    "relevance_score": d.relevance_score,
                }
                for d in self.documents
            ],
            "query": self.query,
            "total_found": self.total_found,
            "execution_ms": self.execution_ms,
            "strategy": self.strategy,
        }


class Retriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, limit: int = 5) -> RetrievalResult: ...

    @abstractmethod
    def retrieve_by_type(self, query: str, source_type: str, limit: int = 5) -> RetrievalResult: ...
