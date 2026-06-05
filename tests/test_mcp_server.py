from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.incidents import Incident
from src.mcp_server import (
    AegisNexMCPServices,
    AegisNexMCPTools,
    create_mcp_server,
)


class FakeMonitor:
    def run(self, params):
        return {"status": "ok", "cpu_percent": 10.0, "ram_percent": 20.0}


class FakeDockerScanner:
    def run(self, params):
        return {
            "status": "ok",
            "include_all": params["include_all"],
            "containers": [{"name": "api", "status": "running"}],
        }

    def restart_container(self, container_name):
        return {
            "status": "ok",
            "container": container_name,
            "action": "restarted",
        }


class FakeHealthChecker:
    def run(self, params):
        return {
            "status": "ok",
            "hardware": {"status": "ok"},
            "docker": {"status": "ok"},
        }


class FakeIncidentManager:
    def list_incidents(self):
        return [
            Incident(
                incident_id="INC-1",
                timestamp="2026-06-05T12:00:00Z",
                severity="high",
                service_name="api",
                incident_type="health_check_failed",
                description="api failed",
                health_check_results=[],
                remediation_attempted=False,
                remediation_successful=False,
                status="active",
                resolved_timestamp=None,
            ),
            Incident(
                incident_id="INC-2",
                timestamp="2026-06-05T13:00:00Z",
                severity="low",
                service_name="db",
                incident_type="container_status",
                description="db recovered",
                health_check_results=[],
                remediation_attempted=True,
                remediation_successful=True,
                status="resolved",
                resolved_timestamp="2026-06-05T13:05:00Z",
            ),
        ]


class FakeReporter:
    def weekly_report(self):
        return {"report_type": "weekly", "summary": {"total_incidents": 2}}

    def monthly_report(self):
        return {"report_type": "monthly", "summary": {"total_incidents": 3}}

    def service_health_report(self, service_name=None):
        return {
            "report_type": "service_health",
            "service_name": service_name,
            "services": [],
        }


class FakeRepository:
    def fetch_all(self, table_name):
        if table_name == "metrics_snapshots":
            return [
                {"timestamp": "2026-06-05T11:00:00Z", "cpu_percent": 20},
                {"timestamp": "2026-06-05T12:00:00Z", "cpu_percent": 30},
            ]
        return []


def build_services() -> AegisNexMCPServices:
    return AegisNexMCPServices(
        monitor=FakeMonitor(),
        docker_scanner=FakeDockerScanner(),
        health_checker=FakeHealthChecker(),
        incident_manager=FakeIncidentManager(),
        reporter=FakeReporter(),
        storage_repository=FakeRepository(),
    )


def test_mcp_tools_return_system_health_and_containers() -> None:
    tools = AegisNexMCPTools(build_services())

    assert tools.get_system_health()["status"] == "ok"
    containers = tools.list_containers(include_all=False)

    assert containers["status"] == "ok"
    assert containers["include_all"] is False
    assert containers["containers"][0]["name"] == "api"


def test_mcp_tools_list_and_filter_incidents() -> None:
    tools = AegisNexMCPTools(build_services())

    all_incidents = tools.list_incidents()
    active_incidents = tools.list_incidents(status="active")

    assert all_incidents["count"] == 2
    assert active_incidents["count"] == 1
    assert active_incidents["incidents"][0]["incident_id"] == "INC-1"


def test_mcp_tools_get_metrics_includes_latest_snapshot() -> None:
    tools = AegisNexMCPTools(build_services())

    metrics = tools.get_metrics()

    assert metrics["current"]["cpu_percent"] == 10.0
    assert metrics["latest_snapshot"]["cpu_percent"] == 30


def test_mcp_tools_generate_reports() -> None:
    tools = AegisNexMCPTools(build_services())

    assert tools.generate_report("weekly")["report_type"] == "weekly"
    assert tools.generate_report("monthly")["report_type"] == "monthly"
    service_report = tools.generate_report("service_health", service_name="api")
    assert service_report["service_name"] == "api"
    assert tools.generate_report("bad")["status"] == "error"


def test_mcp_tools_restart_container() -> None:
    tools = AegisNexMCPTools(build_services())

    assert tools.restart_container("api") == {
        "status": "ok",
        "container": "api",
        "action": "restarted",
    }
    assert tools.restart_container("")["status"] == "error"


def test_create_mcp_server_registers_expected_tools_with_fallback() -> None:
    server = create_mcp_server(build_services(), allow_fallback=True)

    assert set(server.tools) == {
        "get_system_health",
        "list_containers",
        "list_incidents",
        "get_metrics",
        "generate_report",
        "restart_container",
    }
    assert server.tools["list_containers"](include_all=True)["status"] == "ok"
