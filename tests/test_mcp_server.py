from __future__ import annotations

from src.incidents import Incident
import src.mcp_server as mcp_server
from src.mcp_server import (
    AegisNexMCPServices,
    AegisNexMCPTools,
)


EXPECTED_MCP_TOOL_NAMES = {
    "get_system_health",
    "list_containers",
    "list_incidents",
    "get_metrics",
    "get_http_monitoring",
    "get_ssl_monitoring",
    "get_tcp_monitoring",
    "generate_report",
    "restart_container",
}


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


class FakeHttpMonitor:
    def run(self, params):
        return {
            "status": "ok",
            "params": params,
            "availability_percent": 100.0,
            "available_count": 1,
            "total_count": 1,
            "checks": [{"name": params.get("endpoint_name") or "api"}],
        }


class FakeSslMonitor:
    def run(self, params):
        return {
            "status": "ok",
            "params": params,
            "warning_count": 0,
            "total_count": 1,
            "checks": [{"name": params.get("target_name") or "public"}],
        }


class FakeTcpMonitor:
    def run(self, params):
        return {
            "status": "ok",
            "params": params,
            "availability_percent": 100.0,
            "reachable_count": 1,
            "total_count": 1,
            "checks": [{"name": params.get("target_name") or "db"}],
        }


def build_services() -> AegisNexMCPServices:
    return AegisNexMCPServices(
        monitor=FakeMonitor(),
        docker_scanner=FakeDockerScanner(),
        health_checker=FakeHealthChecker(),
        incident_manager=FakeIncidentManager(),
        reporter=FakeReporter(),
        platform_repository=FakeRepository(),
        http_monitor=FakeHttpMonitor(),
        ssl_monitor=FakeSslMonitor(),
        tcp_monitor=FakeTcpMonitor(),
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


def test_mcp_tools_get_http_monitoring() -> None:
    tools = AegisNexMCPTools(build_services())

    result = tools.get_http_monitoring(endpoint_name="api")

    assert result["status"] == "ok"
    assert result["params"] == {"endpoint_name": "api"}
    assert result["checks"][0]["name"] == "api"


def test_mcp_tools_get_ssl_monitoring() -> None:
    tools = AegisNexMCPTools(build_services())

    result = tools.get_ssl_monitoring(target_name="public")

    assert result["status"] == "ok"
    assert result["params"] == {"target_name": "public"}
    assert result["checks"][0]["name"] == "public"


def test_mcp_tools_get_tcp_monitoring() -> None:
    tools = AegisNexMCPTools(build_services())

    result = tools.get_tcp_monitoring(target_name="db")

    assert result["status"] == "ok"
    assert result["params"] == {"target_name": "db"}
    assert result["checks"][0]["name"] == "db"


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


def test_create_mcp_server_registers_expected_tools_with_fallback(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "FastMCP", None)

    server = mcp_server.create_mcp_server(build_services(), allow_fallback=True)

    assert isinstance(server, mcp_server.FastMCPShim)
    assert set(server.tools) == EXPECTED_MCP_TOOL_NAMES
    assert server.tools["list_containers"](include_all=True)["status"] == "ok"


def test_create_mcp_server_supports_fastmcp_without_tools_attribute(monkeypatch) -> None:
    registered_tool_names: list[str] = []

    class FakeFastMCP:
        def __init__(self, name: str) -> None:
            self.name = name

        def tool(self, name: str | None = None):
            def decorator(func):
                registered_tool_names.append(name or func.__name__)
                return func

            return decorator

    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)

    server = mcp_server.create_mcp_server(build_services(), allow_fallback=True)

    assert server.name == "AegisNex"
    assert not hasattr(server, "tools")
    assert set(registered_tool_names) == EXPECTED_MCP_TOOL_NAMES
