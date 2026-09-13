"""FastAPI middleware that captures API telemetry — request duration, method, path, status code."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.telemetry.collector import TelemetryCollector


class TelemetryMiddleware(BaseHTTPMiddleware):
    """Records API request latency, method, path, and status code to TelemetryCollector."""

    def __init__(self, app: Any, collector: TelemetryCollector | None = None) -> None:
        super().__init__(app)
        self._collector = collector or TelemetryCollector()

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        path = request.url.path
        method = request.method

        # Skip health-check noise
        if path.startswith("/api/health") or path.startswith("/ws"):
            return response

        try:
            await asyncio.to_thread(
                self._collector.record_api_latency,
                method=method,
                path=path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )
        except Exception:
            pass

        return response
