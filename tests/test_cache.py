from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

from src.cache import DashboardCache


def test_dashboard_cache_coalesces_concurrent_computation() -> None:
    cache = DashboardCache()
    calls = 0
    calls_lock = Lock()

    def compute() -> dict[str, int]:
        nonlocal calls
        with calls_lock:
            calls += 1
        sleep(0.05)
        return {"value": 42}

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(lambda _: cache.get_or_compute("system_metrics.latest", compute), range(8))
        )

    assert results == [{"value": 42}] * 8
    assert calls == 1


def test_dashboard_cache_keeps_scoped_values_separate() -> None:
    cache = DashboardCache()

    assert cache.get_or_compute("governance_stats.org-a::24", lambda: {"total_actions": 1}) == {
        "total_actions": 1
    }
    assert cache.get_or_compute("governance_stats.org-b::24", lambda: {"total_actions": 2}) == {
        "total_actions": 2
    }


def test_short_lived_health_cache_prevents_repeated_checks() -> None:
    cache = DashboardCache()
    calls = 0

    def check() -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"status": "ok"}

    assert cache.get_or_compute("platform_health.latest", check) == {"status": "ok"}
    assert cache.get_or_compute("platform_health.latest", check) == {"status": "ok"}
    assert calls == 1
