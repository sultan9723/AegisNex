from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationEntry:
    request: str
    response: str
    confidence: float = 0.0
    goal_achieved: bool = False
    steps: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    provider: str = ""
    model: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationalEntry:
    query: str
    result: str
    tool_count: int = 0
    confidence: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class IncidentEntry:
    incident_id: str
    summary: str
    severity: str = "info"
    service: str = ""
    status: str = "open"
    resolved: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecommendationEntry:
    request: str
    recommendation: str
    confidence: float = 0.0
    was_accepted: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RemediationEntry:
    action: str
    target: str
    successful: bool = False
    triggered_by: str = ""
    duration_ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionEntry:
    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    result_status: str = ""
    duration_ms: float = 0.0
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningEntry:
    root_cause: str
    resolution: str
    service: str = ""
    severity: str = "info"
    category: str = ""
    outcome: str = ""
    confidence: float = 0.0
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


MemoryEntry = dict[str, Any]
