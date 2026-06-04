import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GRAFANA_DIR = ROOT / "grafana"


def test_grafana_provisioning_files_exist() -> None:
    required_files = [
        GRAFANA_DIR / "docker-compose.yml",
        GRAFANA_DIR / "prometheus" / "prometheus.yml",
        GRAFANA_DIR / "provisioning" / "datasources" / "prometheus.yml",
        GRAFANA_DIR / "provisioning" / "dashboards" / "aegisnex.yml",
    ]

    for path in required_files:
        assert path.exists(), f"Missing Grafana asset: {path}"


def test_grafana_dashboard_json_loads_correctly() -> None:
    dashboards = sorted((GRAFANA_DIR / "dashboards").glob("*.json"))

    assert {path.name for path in dashboards} == {
        "containers.json",
        "incidents.json",
        "infrastructure.json",
        "remediation.json",
    }
    for path in dashboards:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["uid"].startswith("aegisnex-")
        assert payload["title"].startswith("AegisNex")
        assert payload["schemaVersion"] >= 39
        assert payload["panels"]


def test_grafana_dashboards_include_expected_queries() -> None:
    expected_queries = {
        "infrastructure.json": {
            "aegisnex_system_cpu_usage_percent",
            "aegisnex_system_memory_usage_percent",
            "aegisnex_system_disk_usage_percent",
            "rate(aegisnex_system_network_bytes_sent[5m])",
            "rate(aegisnex_system_network_bytes_received[5m])",
        },
        "containers.json": {
            "aegisnex_containers_running",
            "aegisnex_containers_stopped",
            "aegisnex_containers_unhealthy",
        },
        "incidents.json": {
            "aegisnex_incidents_active",
            "aegisnex_incidents_resolved",
            "aegisnex_incidents_total",
        },
        "remediation.json": {
            "aegisnex_remediation_restart_attempts_total",
            "aegisnex_remediation_successful_restarts_total",
            "aegisnex_remediation_failed_restarts_total",
        },
    }

    for filename, queries in expected_queries.items():
        payload = json.loads(
            (GRAFANA_DIR / "dashboards" / filename).read_text(encoding="utf-8")
        )
        expressions = {
            target["expr"]
            for panel in payload["panels"]
            for target in panel.get("targets", [])
        }
        assert queries.issubset(expressions)


def test_prometheus_datasource_and_scrape_target_are_configured() -> None:
    datasource = (
        GRAFANA_DIR / "provisioning" / "datasources" / "prometheus.yml"
    ).read_text(encoding="utf-8")
    scrape_config = (GRAFANA_DIR / "prometheus" / "prometheus.yml").read_text(
        encoding="utf-8"
    )
    compose = (GRAFANA_DIR / "docker-compose.yml").read_text(encoding="utf-8")

    assert "AegisNex Prometheus" in datasource
    assert "http://prometheus:9090" in datasource
    assert "host.docker.internal:8000" in scrape_config
    assert "/metrics" in scrape_config
    assert "grafana/grafana" in compose
    assert "prom/prometheus" in compose
