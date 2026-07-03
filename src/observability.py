"""Observability tracking for AegisNex.

Tracks latency, failures, retries, response times, execution durations,
agent usage, and tool usage across all platform services.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

_logger = logging.getLogger(__name__)


@dataclass
class OTelSpan:
    operation: str
    component: str
    started_at: float
    ended_at: float | None = None
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ObservabilityTracker:
    """Central tracker for platform observability data."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._spans: list[OTelSpan] = []
        self._latency_buckets: Dict[str, list[float]] = defaultdict(list)
        self._failure_counts: Dict[str, int] = defaultdict(int)
        self._retry_counts: Dict[str, int] = defaultdict(int)
        self._agent_usage: Dict[str, int] = defaultdict(int)
        self._tool_usage: Dict[str, int] = defaultdict(int)

    @contextmanager
    def trace(self, operation: str, component: str = "system", metadata: Dict[str, Any] | None = None):
        if not self.enabled:
            yield None
            return
        span = OTelSpan(operation=operation, component=component, started_at=time.perf_counter(), metadata=metadata or {})
        try:
            yield span
            span.ended_at = time.perf_counter()
            span.duration_ms = round((span.ended_at - span.started_at) * 1000, 2)
            span.success = True
        except Exception as exc:
            span.ended_at = time.perf_counter()
            span.duration_ms = round((span.ended_at - span.started_at) * 1000, 2)
            span.success = False
            span.error = str(exc)
            self._failure_counts[operation] += 1
            raise
        finally:
            self._spans.append(span)
            key = f"{component}.{operation}"
            self._latency_buckets[key].append(span.duration_ms)

    def record_retry(self, operation: str) -> None:
        self._retry_counts[operation] += 1

    def record_agent_usage(self, agent_name: str) -> None:
        self._agent_usage[agent_name] += 1

    def record_tool_usage(self, tool_name: str) -> None:
        self._tool_usage[tool_name] += 1

    def get_latency_stats(self, key: str | None = None) -> Dict[str, Any]:
        buckets = {k: v for k, v in self._latency_buckets.items()} if key is None else {key: self._latency_buckets.get(key, [])}
        stats: Dict[str, Any] = {}
        for k, vals in buckets.items():
            if not vals:
                stats[k] = {"count": 0, "avg_ms": 0, "min_ms": 0, "max_ms": 0, "p95_ms": 0}
                continue
            sorted_vals = sorted(vals)
            stats[k] = {
                "count": len(vals),
                "avg_ms": round(sum(vals) / len(vals), 2),
                "min_ms": round(min(vals), 2),
                "max_ms": round(max(vals), 2),
                "p95_ms": round(sorted_vals[int(len(sorted_vals) * 0.95)], 2),
            }
        return stats

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_operations": len(self._spans),
            "latency": self.get_latency_stats(),
            "failures": dict(self._failure_counts),
            "retries": dict(self._retry_counts),
            "agent_usage": dict(self._agent_usage),
            "tool_usage": dict(self._tool_usage),
            "recent_spans": [
                {"operation": s.operation, "component": s.component, "duration_ms": s.duration_ms, "success": s.success, "error": s.error}
                for s in self._spans[-50:]
            ],
        }

    def clear(self) -> None:
        self._spans.clear()
        self._latency_buckets.clear()
        self._failure_counts.clear()
        self._retry_counts.clear()
        self._agent_usage.clear()
        self._tool_usage.clear()


# Module-level singleton
_tracker: ObservabilityTracker | None = None


def get_tracker() -> ObservabilityTracker:
    global _tracker
    if _tracker is None:
        _tracker = ObservabilityTracker(enabled=os.getenv("AEGISNEX_OTEL_ENABLED", "true").lower() == "true")
    return _tracker


def otel_traced(operation: str | None = None, component: str = "system"):
    """Decorator that wraps a function with observability tracing."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            op = operation or fn.__name__
            tracker = get_tracker()
            with tracker.trace(op, component=component):
                return fn(*args, **kwargs)
        return wrapper
    return decorator
