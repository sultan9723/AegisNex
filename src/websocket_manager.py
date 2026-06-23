"""WebSocket connection management for AegisNex realtime updates."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Set

from src.cache import DashboardCache


logger = logging.getLogger(__name__)


class WebSocketManager:
    """Track active WebSocket clients and broadcast JSON events with error isolation."""

    def __init__(self, cache: DashboardCache | None = None) -> None:
        self._connections: Set[Any] = set()
        self._lock = asyncio.Lock()
        self._cache = cache
        self._consecutive_failures = 0
        self._max_backoff_seconds = 60

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: Any) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            self._consecutive_failures = 0

    def disconnect(self, websocket: Any) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, event: Dict[str, Any]) -> None:
        stale_connections = []
        async with self._lock:
            connections = list(self._connections)
        for websocket in connections:
            try:
                await websocket.send_json(event)
            except Exception as exc:
                logger.debug("WebSocket send failed (stale connection): %s", exc)
                stale_connections.append(websocket)
        if stale_connections:
            async with self._lock:
                for ws in stale_connections:
                    self._connections.discard(ws)
            self._consecutive_failures += 1
        else:
            self._consecutive_failures = 0

    async def broadcast_with_backoff(self, event: Dict[str, Any]) -> None:
        try:
            await self.broadcast(event)
        except Exception as exc:
            logger.error("WebSocket broadcast error: %s", exc, exc_info=True)
            self._consecutive_failures += 1
            backoff = min(2 ** self._consecutive_failures, self._max_backoff_seconds)
            await asyncio.sleep(backoff)

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def reset_failures(self) -> None:
        self._consecutive_failures = 0