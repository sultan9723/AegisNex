from pathlib import Path

from src.http_monitor import HttpEndpointCheck, HttpEndpointMonitor
from src.incidents import IncidentManager
from src.monitoring_engine import MonitoringEngine
from src.platform_db import PlatformRepository


def test_monitoring_engine_persists_results_and_incident_transitions(tmp_path: Path) -> None:
    repository = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    incident_manager = IncidentManager(tmp_path / "incidents.json")
    target = repository.create_monitoring_target(
        {"name": "db", "target_type": "tcp", "address": "localhost:1"}
    )
    engine = MonitoringEngine(repository, incident_manager, interval_seconds=5)

    engine._run_target = lambda target: {  # type: ignore[method-assign]
        "name": target["name"],
        "target_type": "tcp",
        "timestamp": "2026-06-21T12:00:00Z",
        "status": "failed",
        "reachable": False,
        "latency_ms": 1.0,
        "error": "connection refused",
    }
    engine.run_once()

    assert repository.latest_check_results()[0]["details"]["reachable"] is False
    assert incident_manager.get_active_incidents()[0].incident_type == "tcp_target_unreachable"
    assert repository.list_audit_logs()

    engine._run_target = lambda target: {  # type: ignore[method-assign]
        "name": target["name"],
        "target_type": "tcp",
        "timestamp": "2026-06-21T12:01:00Z",
        "status": "ok",
        "reachable": True,
        "latency_ms": 1.0,
        "error": "",
    }
    engine.run_once()

    assert incident_manager.list_incidents()[0].status == "resolved"
    assert repository.get_monitoring_target(int(target["id"])) is not None


def make_engine(tmp_path: Path) -> tuple[MonitoringEngine, PlatformRepository, IncidentManager]:
    repository = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    incident_manager = IncidentManager(tmp_path / "incidents.json", storage_repository=repository)
    engine = MonitoringEngine(repository, incident_manager, interval_seconds=5)
    # These tests verify per-target (HTTP) incident lifecycle in isolation.
    # run_once() also calls _check_system_metrics(), which reads the real
    # test machine's actual CPU/memory/disk via psutil - on a loaded machine
    # that can independently create a real "system" incident and make
    # get_active_incidents() assertions flaky for reasons unrelated to what
    # these tests check. Disabled here; covered by its own tests below.
    engine._check_system_metrics = lambda: None  # type: ignore[method-assign]
    return engine, repository, incident_manager


def failing_http_check(self, name, url):  # noqa: ANN001 - monkeypatch target signature
    return HttpEndpointCheck(
        name=name, url=url, timestamp="2026-06-21T12:00:00Z", status="failed",
        available=False, expected_status=200, status_code=None, latency_ms=1.0,
        error="connection refused", availability_percent=0.0,
    )


def healthy_http_check(self, name, url):  # noqa: ANN001
    return HttpEndpointCheck(
        name=name, url=url, timestamp="2026-06-21T12:01:00Z", status="ok",
        available=True, expected_status=200, status_code=200, latency_ms=1.0,
        error="", availability_percent=100.0,
    )


# ---------------------------------------------------------------------------
# _get_or_create_monitor no longer wires incident_manager into the protocol
# monitors it constructs. Root cause: each protocol monitor (HttpEndpointMonitor
# et al.) is self-sufficient and runs its own incident create/resolve inside
# .run() whenever it's given an incident_manager - correct for their
# standalone/static-config use (create_services()'s http_monitor), but
# MonitoringEngine._sync_incident (called explicitly right after .run()
# in _process_target) already does the same create/resolve uniformly for
# every target type, AND additionally records the incident.created
# transition/audit-log entry the protocol monitors don't. Wiring
# incident_manager into both meant the protocol monitor's plainer internal
# sync always won the race (it runs first, inside .run()), so
# MonitoringEngine._sync_incident's richer branch never actually fired -
# incidents still got created/resolved, but with no incident.created audit
# entry and a generic/None resolution reason instead of the intended one.
# ---------------------------------------------------------------------------


def test_get_or_create_monitor_does_not_wire_incident_manager_into_protocol_monitors(tmp_path: Path) -> None:
    engine, repository, _ = make_engine(tmp_path)
    http_target = repository.create_monitoring_target(
        {"name": "web", "target_type": "http", "address": "https://example.invalid"}
    )
    tcp_target = repository.create_monitoring_target(
        {"name": "db", "target_type": "tcp", "address": "localhost:1"}
    )

    http_monitor = engine._get_or_create_monitor("http", "web", "https://example.invalid", http_target)
    tcp_monitor = engine._get_or_create_monitor("tcp", "db", "localhost:1", tcp_target)

    assert http_monitor.incident_manager is None
    assert tcp_monitor.incident_manager is None


def test_real_http_check_cycle_creates_one_incident_with_full_audit_trail(tmp_path: Path, monkeypatch) -> None:
    """End-to-end through the real HttpEndpointMonitor.run() path (unlike
    the older test above, which bypasses it via a _run_target monkeypatch) -
    proves the protocol monitor no longer races MonitoringEngine's own
    incident sync and steals the audit/transition recording."""
    engine, repository, incident_manager = make_engine(tmp_path)
    repository.create_monitoring_target({"name": "web", "target_type": "http", "address": "https://example.invalid"})
    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", failing_http_check)

    engine.run_once()

    active = incident_manager.get_active_incidents()
    assert len(active) == 1
    incident = active[0]
    audit_actions = [row["action"] for row in repository.list_audit_logs(limit=50)]
    assert "incident.created" in audit_actions
    transitions = repository.list_incident_transitions(incident.incident_id)
    assert any(t["to_status"] == "active" for t in transitions)


def test_real_http_recovery_resolves_with_intended_reason(tmp_path: Path, monkeypatch) -> None:
    engine, repository, incident_manager = make_engine(tmp_path)
    repository.create_monitoring_target({"name": "web", "target_type": "http", "address": "https://example.invalid"})
    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", failing_http_check)
    engine.run_once()
    incident_id = incident_manager.get_active_incidents()[0].incident_id

    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", healthy_http_check)
    engine.run_once()

    assert incident_manager.get_active_incidents() == []
    resolved = repository.get_incident(incident_id)
    assert resolved["incident_status"] == "resolved"
    # Only MonitoringEngine._sync_incident's resolve branch uses this text -
    # the protocol monitor's own resolve call passes no reason at all.
    assert resolved["resolution_notes"] == "Recovered automatically after a successful check."


# ---------------------------------------------------------------------------
# Required regression coverage: healthy->unhealthy->healthy->unhealthy again,
# with dedup in between.
# ---------------------------------------------------------------------------


def test_healthy_to_unhealthy_creates_exactly_one_incident(tmp_path: Path, monkeypatch) -> None:
    engine, repository, incident_manager = make_engine(tmp_path)
    repository.create_monitoring_target({"name": "web", "target_type": "http", "address": "https://example.invalid"})
    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", healthy_http_check)
    engine.run_once()
    assert incident_manager.get_active_incidents() == []

    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", failing_http_check)
    engine.run_once()

    active = incident_manager.get_active_incidents()
    assert len(active) == 1
    assert active[0].incident_type == "http_endpoint_failure"


def test_repeated_unhealthy_checks_do_not_flood_duplicate_active_incidents(tmp_path: Path, monkeypatch) -> None:
    engine, repository, incident_manager = make_engine(tmp_path)
    repository.create_monitoring_target({"name": "web", "target_type": "http", "address": "https://example.invalid"})
    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", failing_http_check)

    engine.run_once()
    first_id = incident_manager.get_active_incidents()[0].incident_id
    for _ in range(5):
        engine.run_once()

    active = incident_manager.get_active_incidents()
    assert len(active) == 1
    assert active[0].incident_id == first_id


def test_unhealthy_to_healthy_performs_recovery_transition(tmp_path: Path, monkeypatch) -> None:
    engine, repository, incident_manager = make_engine(tmp_path)
    repository.create_monitoring_target({"name": "web", "target_type": "http", "address": "https://example.invalid"})
    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", failing_http_check)
    engine.run_once()
    incident_id = incident_manager.get_active_incidents()[0].incident_id

    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", healthy_http_check)
    engine.run_once()

    assert incident_manager.get_active_incidents() == []
    resolved = repository.get_incident(incident_id)
    assert resolved["incident_status"] == "resolved"
    # Original failure evidence must survive the recovery, not be overwritten.
    assert resolved["health_check_results"]


def test_new_outage_after_recovery_creates_a_new_incident(tmp_path: Path, monkeypatch) -> None:
    engine, repository, incident_manager = make_engine(tmp_path)
    repository.create_monitoring_target({"name": "web", "target_type": "http", "address": "https://example.invalid"})

    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", failing_http_check)
    engine.run_once()
    first_incident_id = incident_manager.get_active_incidents()[0].incident_id

    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", healthy_http_check)
    engine.run_once()
    assert incident_manager.get_active_incidents() == []

    monkeypatch.setattr(HttpEndpointMonitor, "_check_endpoint", failing_http_check)
    engine.run_once()

    active = incident_manager.get_active_incidents()
    assert len(active) == 1
    second_incident_id = active[0].incident_id
    assert second_incident_id != first_incident_id
    # Both real incidents remain in history - the first is not deleted or
    # merged away by the second.
    all_ids = {i.incident_id for i in incident_manager.list_incidents()}
    assert {first_incident_id, second_incident_id} <= all_ids


# ---------------------------------------------------------------------------
# System-metric (CPU/memory/disk) incident deduplication/flapping fix.
#
# Real E2E symptom: the UI showed many CPU >90% incidents with 50+ resolved
# in a single day. Root cause: _sync_system_incident resolved the incident
# the instant a single check sample dropped below the 90% threshold, then
# immediately recreated it on the next sample if CPU was still hovering near
# the threshold - one ongoing noisy condition, split into hundreds of
# separate create/resolve cycles instead of being correlated as one.
# ---------------------------------------------------------------------------


def test_system_incident_created_immediately_on_first_breach(tmp_path: Path) -> None:
    engine, _, incident_manager = make_engine(tmp_path)
    engine._sync_system_incident("high_cpu", True, "high", "CPU usage at 95.0% exceeds 90% threshold")
    active = incident_manager.get_active_incidents()
    assert len(active) == 1
    assert active[0].incident_type == "high_cpu"


def test_system_incident_does_not_resolve_on_a_single_noisy_recovery_sample(tmp_path: Path) -> None:
    engine, _, incident_manager = make_engine(tmp_path)
    engine._sync_system_incident("high_cpu", True, "high", "breach")
    incident_id = incident_manager.get_active_incidents()[0].incident_id

    engine._sync_system_incident("high_cpu", False, "high", "breach")  # one good sample

    active = incident_manager.get_active_incidents()
    assert len(active) == 1
    assert active[0].incident_id == incident_id


def test_system_incident_resolves_after_sustained_recovery(tmp_path: Path) -> None:
    engine, _, incident_manager = make_engine(tmp_path)
    engine._sync_system_incident("high_cpu", True, "high", "breach")

    for _ in range(MonitoringEngine.RECOVERY_STREAK_REQUIRED):
        engine._sync_system_incident("high_cpu", False, "high", "breach")

    assert incident_manager.get_active_incidents() == []


def test_system_incident_flapping_does_not_flood_duplicates(tmp_path: Path) -> None:
    """Simulates CPU bouncing right around the threshold - must stay as one
    correlated incident, not many."""
    engine, _, incident_manager = make_engine(tmp_path)
    pattern = [True, False, True, False, True, False, True]  # never 3 clean recoveries in a row
    for breached in pattern:
        engine._sync_system_incident("high_cpu", breached, "high", "flapping")

    active = incident_manager.get_active_incidents()
    assert len(active) == 1
    assert len(incident_manager.list_incidents()) == 1


def test_system_incident_new_breach_after_full_recovery_creates_new_incident(tmp_path: Path) -> None:
    engine, _, incident_manager = make_engine(tmp_path)
    engine._sync_system_incident("high_cpu", True, "high", "breach 1")
    first_id = incident_manager.get_active_incidents()[0].incident_id

    for _ in range(MonitoringEngine.RECOVERY_STREAK_REQUIRED):
        engine._sync_system_incident("high_cpu", False, "high", "breach 1")
    assert incident_manager.get_active_incidents() == []

    engine._sync_system_incident("high_cpu", True, "high", "breach 2")

    active = incident_manager.get_active_incidents()
    assert len(active) == 1
    assert active[0].incident_id != first_id
