"""TTL-based caching layer for dashboard context.

Decouples dashboard page loads from live monitoring engine checks.
Uses cachetools for thread-safe TTL caches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from cachetools import TTLCache

# Default TTLs in seconds
DEFAULT_CACHE_TTLS = {
    "system_metrics": 10,
    "container_states": 30,
    "incident_summaries": 30,
    "recent_check_results": 15,
    "chart_data": 15,
    "notification_stats": 30,
}


@dataclass
class DashboardCache:
    """TTL-based cache for dashboard context data.

    Each data category has its own TTL. Caches are invalidated on mutation
    events (incident created/resolved, target added/removed).
    """

    ttls: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_CACHE_TTLS))
    _lock: Lock = field(default_factory=Lock)

    def __post_init__(self) -> None:
        self._caches: dict[str, TTLCache] = {}
        for key, ttl in self.ttls.items():
            self._caches[key] = TTLCache(maxsize=100, ttl=ttl)

    def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None if not present or expired."""
        category, cache_key = self._parse_key(key)
        cache = self._caches.get(category)
        if cache is None:
            return None
        with self._lock:
            return cache.get(cache_key)

    def set(self, key: str, value: Any) -> None:
        """Set a cached value."""
        category, cache_key = self._parse_key(key)
        cache = self._caches.get(category)
        if cache is None:
            return
        with self._lock:
            cache[cache_key] = value

    def invalidate(self, category: str) -> None:
        """Invalidate all cached values for a category."""
        cache = self._caches.get(category)
        if cache is not None:
            with self._lock:
                cache.clear()

    def invalidate_all(self) -> None:
        """Invalidate all caches."""
        with self._lock:
            for cache in self._caches.values():
                cache.clear()

    @staticmethod
    def _parse_key(key: str) -> tuple[str, str]:
        """Parse a dot-separated key into (category, cache_key).

        Examples:
            "system_metrics.cpu" -> ("system_metrics", "cpu")
            "incident_summaries.active" -> ("incident_summaries", "active")
        """
        parts = key.split(".", 1)
        category = parts[0]
        cache_key = parts[1] if len(parts) > 1 else "default"
        return category, cache_key

    # Convenience methods for common dashboard data categories

    def get_system_metrics(self) -> dict[str, Any] | None:
        return self.get("system_metrics.latest")

    def set_system_metrics(self, metrics: dict[str, Any]) -> None:
        self.set("system_metrics.latest", metrics)

    def get_container_states(self) -> dict[str, Any] | None:
        return self.get("container_states.latest")

    def set_container_states(self, states: dict[str, Any]) -> None:
        self.set("container_states.latest", states)

    def get_incident_summaries(self) -> dict[str, Any] | None:
        return self.get("incident_summaries.latest")

    def set_incident_summaries(self, summaries: dict[str, Any]) -> None:
        self.set("incident_summaries.latest", summaries)

    def get_chart_data(self) -> dict[str, Any] | None:
        return self.get("chart_data.latest")

    def set_chart_data(self, data: dict[str, Any]) -> None:
        self.set("chart_data.latest", data)

    def get_notification_stats(self) -> dict[str, Any] | None:
        return self.get("notification_stats.latest")

    def set_notification_stats(self, stats: dict[str, Any]) -> None:
        self.set("notification_stats.latest", stats)

    # Cache invalidation hooks for mutation events

    def on_incident_created(self) -> None:
        """Invalidate caches when an incident is created."""
        self.invalidate("incident_summaries")
        self.invalidate("chart_data")

    def on_incident_resolved(self) -> None:
        """Invalidate caches when an incident is resolved."""
        self.invalidate("incident_summaries")
        self.invalidate("chart_data")

    def on_target_added(self) -> None:
        """Invalidate caches when a monitoring target is added."""
        self.invalidate("recent_check_results")
        self.invalidate("system_metrics")

    def on_target_removed(self) -> None:
        """Invalidate caches when a monitoring target is removed."""
        self.invalidate("recent_check_results")
        self.invalidate("system_metrics")

    def on_container_change(self) -> None:
        """Invalidate caches when container state changes."""
        self.invalidate("container_states")
