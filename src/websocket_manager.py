"""WebSocket connection management for AegisNex realtime updates.

Supports multiple named channels for broadcasting different event types.
"""

from __future__ import annotations

import asyncio
import logging
from threading import Lock
from typing import Any, Dict, Set


logger = logging.getLogger(__name__)


class WebSocketManager:
    """Track active WebSocket clients per channel and broadcast JSON events with error isolation."""

    def __init__(self) -> None:
        self._channels: Dict[str, Set[Any]] = {}
        self._lock = Lock()
        self._consecutive_failures = 0
        self._max_backoff_seconds = 60

    @property
    def connection_count(self) -> int:
        return sum(len(ws) for ws in self._channels.values())

    def _channel(self, name: str) -> Set[Any]:
        if name not in self._channels:
            self._channels[name] = set()
        return self._channels[name]

    async def connect(self, websocket: Any, channel: str = "dashboard") -> None:
        await websocket.accept()
        with self._lock:
            self._channel(channel).add(websocket)
            self._consecutive_failures = 0

    def disconnect(self, websocket: Any, channel: str = "dashboard") -> None:
        with self._lock:
            self._channel(channel).discard(websocket)

    async def broadcast(self, event: Dict[str, Any], channel: str = "dashboard") -> None:
        stale_connections = []
        with self._lock:
            connections = list(self._channel(channel))
        for websocket in connections:
            try:
                await websocket.send_json(event)
            except Exception as exc:
                logger.debug("WebSocket send failed (stale connection): %s", exc)
                stale_connections.append(websocket)
        if stale_connections:
            with self._lock:
                for ws in stale_connections:
                    self._channel(channel).discard(ws)
            self._consecutive_failures += 1
        else:
            self._consecutive_failures = 0

    async def broadcast_with_backoff(self, event: Dict[str, Any], channel: str = "dashboard") -> None:
        try:
            await self.broadcast(event, channel=channel)
        except Exception as exc:
            logger.error("WebSocket broadcast error on channel '%s': %s", channel, exc, exc_info=True)
            self._consecutive_failures += 1
            backoff = min(2 ** self._consecutive_failures, self._max_backoff_seconds)
            await asyncio.sleep(backoff)

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def reset_failures(self) -> None:
        self._consecutive_failures = 0
