from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class MemorySearchResult:
    entries: list[dict[str, Any]]
    count: int
    total: int
    query: str
    similarity: float | None = None


class MemoryStore(ABC):
    @abstractmethod
    def store_conversation(
        self, request: str, response: str, confidence: float, goal_achieved: bool, **extra: Any
    ) -> int: ...

    @abstractmethod
    def store_incident(
        self, incident_id: str, summary: str, severity: str, service: str, **extra: Any
    ) -> int: ...

    @abstractmethod
    def store_recommendation(
        self, request: str, recommendation: str, confidence: float, **extra: Any
    ) -> int: ...

    @abstractmethod
    def store_remediation(
        self, action: str, target: str, successful: bool, **extra: Any
    ) -> int: ...

    @abstractmethod
    def store_tool_execution(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        result_status: str,
        duration_ms: float,
        **extra: Any,
    ) -> int: ...

    @abstractmethod
    def search_conversations(self, query: str, limit: int = 10) -> MemorySearchResult: ...

    @abstractmethod
    def search_incidents(self, query: str, limit: int = 10) -> MemorySearchResult: ...

    @abstractmethod
    def search_recommendations(self, query: str, limit: int = 10) -> MemorySearchResult: ...

    @abstractmethod
    def search_remediations(self, query: str, limit: int = 10) -> MemorySearchResult: ...

    @abstractmethod
    def search_tool_executions(self, query: str, limit: int = 10) -> MemorySearchResult: ...

    @abstractmethod
    def search_all(self, query: str, limit: int = 10) -> MemorySearchResult: ...

    @abstractmethod
    def get_recent_conversations(self, limit: int = 10) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_recent_incidents(self, limit: int = 10) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_recent_recommendations(self, limit: int = 10) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_recent_remediations(self, limit: int = 10) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_stats(self) -> dict[str, Any]: ...
