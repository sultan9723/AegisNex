"""Tests for TelemetryCollector's container-safe SQLite path handling and
src.dashboard.resolve_telemetry_db_path's path-resolution priority.

Regression coverage for a Blitz production crash:
    TelemetryCollector(telemetry_db_path) -> sqlite3.connect(...)
    -> sqlite3.OperationalError: unable to open database file

Root cause: AEGISNEX_DATA_DIR was never set in the container, so
telemetry_db_path resolved to a bare relative "telemetry.db" whose parent
directory sqlite3.connect() does not create itself, and no code created it
either.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.dashboard import resolve_telemetry_db_path
from src.telemetry.collector import TelemetryCollector

# --- TelemetryCollector: parent directory creation + SQLite initialization ---


def test_collector_creates_missing_parent_directory(tmp_path: Path) -> None:
    """The exact failure mode: a configured path whose parent directory
    (analogous to /app/data in a container) does not exist yet."""
    nested_path = tmp_path / "data" / "nested" / "telemetry.db"
    assert not nested_path.parent.exists()

    TelemetryCollector(str(nested_path))

    assert nested_path.parent.is_dir()
    assert nested_path.exists()


def test_collector_initializes_sqlite_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"

    collector = TelemetryCollector(str(db_path))

    tables = {
        row["name"]
        for row in collector._connect()
        .execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        .fetchall()
    }
    assert {
        "api_latency",
        "workflow_executions",
        "agent_executions",
        "tool_failures",
        "approval_times",
    }.issubset(tables)


def test_collector_records_and_reads_back(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    collector = TelemetryCollector(str(db_path))

    collector.record_api_latency("GET", "/api/health", 200, 12.5)
    stats = collector.get_api_stats(hours=24)

    assert stats["total_requests"] == 1
    assert stats["error_rate"] == 0.0


def test_collector_survives_reopen_after_parent_already_exists(tmp_path: Path) -> None:
    """Second collector against the same (now-existing) path must not error
    on the already-created parent directory (os.makedirs(exist_ok=True))."""
    db_path = tmp_path / "data" / "telemetry.db"
    TelemetryCollector(str(db_path))

    second = TelemetryCollector(str(db_path))
    second.record_tool_failure("scanner", "boom", 5.0)

    assert second.get_tool_failure_stats(hours=24)["total_failures"] == 1


# --- resolve_telemetry_db_path: configured/production/local behavior ---


@pytest.fixture(autouse=True)
def _clean_telemetry_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AEGISNEX_TELEMETRY_DB_PATH", raising=False)
    monkeypatch.delenv("AEGISNEX_DATA_DIR", raising=False)
    monkeypatch.delenv("AEGISNEX_ENV", raising=False)


def test_resolve_explicit_argument_wins_over_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEGISNEX_TELEMETRY_DB_PATH", "/should-not-be-used.db")
    monkeypatch.setenv("AEGISNEX_ENV", "production")

    assert resolve_telemetry_db_path("explicit/path.db") == "explicit/path.db"


def test_resolve_configured_telemetry_path_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEGISNEX_TELEMETRY_DB_PATH", "/custom/telemetry.db")

    assert resolve_telemetry_db_path() == "/custom/telemetry.db"


def test_resolve_preserves_existing_data_dir_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    """AEGISNEX_DATA_DIR already existed for this purpose before
    AEGISNEX_TELEMETRY_DB_PATH was introduced - must keep working."""
    monkeypatch.setenv("AEGISNEX_DATA_DIR", "/mydata")

    resolved = resolve_telemetry_db_path()

    assert Path(resolved) == Path("/mydata") / "telemetry.db"


def test_resolve_telemetry_path_env_var_takes_priority_over_data_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEGISNEX_TELEMETRY_DB_PATH", "/explicit/telemetry.db")
    monkeypatch.setenv("AEGISNEX_DATA_DIR", "/mydata")

    assert resolve_telemetry_db_path() == "/explicit/telemetry.db"


def test_resolve_production_default_is_container_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """The actual fix: production with no AEGISNEX_DATA_DIR/
    AEGISNEX_TELEMETRY_DB_PATH set must default under /app/data, not a bare
    relative path that crashes when the working directory isn't writable."""
    monkeypatch.setenv("AEGISNEX_ENV", "production")

    assert resolve_telemetry_db_path() == "/app/data/telemetry.db"


@pytest.mark.parametrize("env_value", ["development", "dev", "local", "test"])
def test_resolve_local_development_default_is_unchanged(
    env_value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing local-development behavior (bare relative path, resolved
    against the current working directory) must not change."""
    monkeypatch.setenv("AEGISNEX_ENV", env_value)

    assert resolve_telemetry_db_path() == "telemetry.db"


def test_resolve_no_aegisnex_env_defaults_to_local_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """is_production_environment() treats an unset AEGISNEX_ENV as
    development, matching every other production/local switch in this
    codebase (TLS redirect, Docker scanner, etc.) - telemetry follows the
    same convention rather than inventing its own."""
    assert resolve_telemetry_db_path() == "telemetry.db"
