from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ConversationEntry:
    request: str
    response: str
    confidence: float = 0.0
    goal_achieved: bool = False
    steps: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    corrections: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    provider: str = ""
    model: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationalEntry:
    query: str
    result: str
    tool_count: int = 0
    confidence: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IncidentEntry:
    incident_id: str
    summary: str
    severity: str = "info"
    service: str = ""
    status: str = "open"
    resolved: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecommendationEntry:
    request: str
    recommendation: str
    confidence: float = 0.0
    was_accepted: Optional[bool] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RemediationEntry:
    action: str
    target: str
    successful: bool = False
    triggered_by: str = ""
    duration_ms: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionEntry:
    tool_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    result_status: str = ""
    duration_ms: float = 0.0
    error: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningEntry:
    root_cause: str
    resolution: str
    service: str = ""
    severity: str = "info"
    category: str = ""
    outcome: str = ""
    confidence: float = 0.0
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


MemoryEntry = Dict[str, Any]
