"""Thread-safe shared state for multi-agent collaboration."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional


class SharedAgentState:
    """Thread-safe shared state wrapper for agent collaboration."""

    def __init__(self) -> None:
        self._state: Dict[str, Any] = {}
        self._history: List[Dict[str, Any]] = []
        self._lock = Lock()

    def set(self, key: str, value: Any, agent_id: str = "") -> None:
        with self._lock:
            self._state[key] = value
            self._history.append({
                "key": key,
                "value": value,
                "agent_id": agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            })

    def get(self, key: str) -> Any:
        with self._lock:
            return self._state.get(key)

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history[-limit:])

    def clear(self) -> None:
        with self._lock:
            self._state.clear()
            self._history.clear()
