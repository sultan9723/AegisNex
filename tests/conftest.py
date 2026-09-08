"""Shared pytest fixtures for the AegisNex test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _disable_rate_limiter() -> None:
    """Disable the app-wide slowapi limiter for the entire test session.

    ``src.dashboard.limiter`` is a module-level singleton shared by every
    ``create_app()`` call, and every ``TestClient`` request shares the same
    client host. Its fixed 1-minute windows therefore leak across tests,
    causing order-dependent 429s on endpoints like ``/api/login`` even though
    each test builds a fresh app/database and the old per-test ``limiter.reset()``
    approach could not fully isolate state.

    No test asserts on 429 responses, so disabling the limiter for tests is safe
    and makes the suite deterministic regardless of execution order.
    """
    from src.dashboard import limiter

    limiter.enabled = False
    yield
    limiter.enabled = True
