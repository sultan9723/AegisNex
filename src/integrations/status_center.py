from __future__ import annotations

import asyncio
import os
import socket
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from src.integrations.base import get_integration
from src.integrations.marketplace import get_installed_integrations


StatusRow = Dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def _status(health: str, label: str, message: str) -> Dict[str, str]:
    return {"health": health, "status": label, "message": message}


def _socket_probe(host: str, port: int, timeout: float = 1.5) -> tuple[bool, int | None, str]:
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = int((time.perf_counter() - start) * 1000)
            return True, latency, ""
    except socket.timeout:
        return False, None, "Timeout"
    except OSError as exc:
        return False, None, str(exc)


def _http_probe(url: str, timeout: float = 2.5, headers: Mapping[str, str] | None = None) -> tuple[bool, int | None, int | None, str]:
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency = int((time.perf_counter() - start) * 1000)
            return 200 <= resp.status < 400, resp.status, latency, ""
    except urllib.error.HTTPError as exc:
        latency = int((time.perf_counter() - start) * 1000)
        return False, exc.code, latency, "Authentication Failed" if exc.code in (401, 403) else f"HTTP {exc.code}"
    except TimeoutError:
        return False, None, None, "Timeout"
    except urllib.error.URLError as exc:
        return False, None, None, str(exc.reason)
    except Exception as exc:
        return False, None, None, str(exc)


def _installed_configs() -> Dict[str, Dict[str, Any]]:
    configs: Dict[str, Dict[str, Any]] = {}
    for item in get_installed_integrations():
        configs[str(item.get("integration_id", ""))] = {
            "credentials": item.get("credentials", {}),
            "settings": item.get("settings", {}),
            "created_at": item.get("created_at", ""),
            "enabled": bool(item.get("enabled", False)),
        }
    return configs


def _base_row(
    integration_id: str,
    name: str,
    category: str,
    description: str,
    *,
    configure_href: str = "/settings",
    testable: bool = True,
    configurable: bool = True,
    details: Mapping[str, Any] | None = None,
    result: Mapping[str, str] | None = None,
) -> StatusRow:
    resolved = dict(result or _status("unknown", "Unknown", "Status not verified"))
    return {
        "id": integration_id,
        "name": name,
        "category": category,
        "description": description,
        "health": resolved["health"],
        "status": resolved["status"],
        "message": resolved["message"],
        "details": dict(details or {}),
        "last_verification": utc_now(),
        "configure_href": configure_href,
        "testable": testable,
        "configurable": configurable,
    }


def _configured_http_provider(
    integration_id: str,
    name: str,
    category: str,
    description: str,
    url: str,
    env_names: Iterable[str],
    *,
    headers: Mapping[str, str] | None = None,
    details: Mapping[str, Any] | None = None,
) -> StatusRow:
    configured = bool(url or _env_first(*env_names))
    if not configured:
        result = _status("unknown", "Not Configured", "No endpoint or credentials configured")
        return _base_row(integration_id, name, category, description, details=details, result=result)

    ok, status_code, latency, error = _http_probe(url)
    health = "healthy" if ok else ("warning" if status_code in (401, 403) else "offline")
    label = "Healthy" if ok else ("Authentication Failed" if status_code in (401, 403) else "Service Offline")
    message = "Connection verified" if ok else error or "Connection failed"
    merged = {"api_status": status_code or "Unavailable", "latency": f"{latency} ms" if latency is not None else "Unavailable", **dict(details or {})}
    return _base_row(integration_id, name, category, description, details=merged, result=_status(health, label, message))


def _ai_provider(provider: str, label: str, model_env: str, key_envs: Iterable[str], url: str = "") -> StatusRow:
    key = _env_first(*key_envs)
    model = os.getenv(model_env, "Not configured")
    details = {"configured_model": model, "api_status": "Not verified"}
    if not key and not url:
        result = _status("unknown", "Not Configured", "API key or endpoint is not configured")
    elif url:
        ok, status_code, latency, error = _http_probe(url)
        details.update({"api_status": status_code or "Unavailable", "latency": f"{latency} ms" if latency is not None else "Unavailable"})
        result = _status("healthy" if ok else "offline", "Healthy" if ok else "Connection Failed", "Connection verified" if ok else error)
    else:
        result = _status("warning", "Needs Verification", "Credentials are present; live API verification is available from Test Connection")
        details["api_status"] = "Credentials present"
    return _base_row(provider, label, "AI Providers", "Model provider for AI analysis and automation.", details=details, result=result)


def _docker_status(services: Any) -> StatusRow:
    scanner = getattr(services, "docker_scanner", None)
    details: Dict[str, Any] = {"version": "Unavailable", "connection": "Unavailable", "latency": "Unavailable"}
    if scanner is None:
        result = _status("unknown", "Unavailable", "Docker scanner is not available")
    else:
        start = time.perf_counter()
        try:
            report = scanner.run({"include_all": True})
            latency = int((time.perf_counter() - start) * 1000)
            if report.get("status") == "ok":
                containers = report.get("containers", [])
                running = sum(1 for item in containers if item.get("status") == "running")
                details.update({"connection": "Connected", "latency": f"{latency} ms", "last_sync": utc_now(), "health": f"{running}/{len(containers)} running"})
                result = _status("healthy", "Healthy", "Container runtime inventory verified")
            else:
                result = _status("offline", "Service Offline", str(report.get("error", "Docker scan failed")))
        except Exception as exc:
            result = _status("offline", "Connection Failed", str(exc))
    return _base_row("docker", "Docker", "Infrastructure", "Container runtime inventory and controls.", details=details, result=result)


def _sqlite_status(services: Any) -> StatusRow:
    repository = getattr(services, "platform_repository", None)
    details = {"version": sqlite3.sqlite_version, "connection": "Unavailable", "latency": "Unavailable"}
    if repository is None:
        result = _status("unknown", "Unavailable", "Platform repository is not available")
    else:
        start = time.perf_counter()
        try:
            repository.fetch_all("incidents", limit=1)
            details.update({"connection": "Connected", "latency": f"{int((time.perf_counter() - start) * 1000)} ms", "last_sync": utc_now()})
            result = _status("healthy", "Healthy", "SQLite repository query succeeded")
        except Exception as exc:
            result = _status("offline", "Connection Failed", str(exc))
    return _base_row("sqlite", "SQLite", "Infrastructure", "Local platform persistence.", details=details, result=result)


def _tcp_infra(integration_id: str, name: str, host_env: str, port_env: str, default_port: int) -> StatusRow:
    host = os.getenv(host_env, "")
    port = int(os.getenv(port_env, str(default_port)))
    details = {"version": "Unavailable", "connection": "Not Configured", "latency": "Unavailable", "last_sync": "Never"}
    if not host:
        result = _status("unknown", "Not Configured", f"{host_env} is not configured")
    else:
        ok, latency, error = _socket_probe(host, port)
        details.update({"connection": "Connected" if ok else "Failed", "latency": f"{latency} ms" if latency is not None else "Unavailable", "last_sync": utc_now()})
        result = _status("healthy" if ok else "offline", "Healthy" if ok else "Host Unreachable", "Connection verified" if ok else error)
    return _base_row(integration_id, name, "Infrastructure", f"{name} service connectivity.", details=details, result=result)


def _installed_provider_status(integration_id: str, name: str, category: str, description: str, installed: Mapping[str, Dict[str, Any]]) -> StatusRow:
    config = installed.get(integration_id)
    details = {"connection": "Not Configured", "last_sync": "Never"}
    if not config:
        return _base_row(integration_id, name, category, description, details=details, result=_status("unknown", "Not Configured", "Integration is not configured"))
    provider = get_integration(integration_id, config)
    if provider is None:
        return _base_row(integration_id, name, category, description, details=details, result=_status("unknown", "Unavailable", "Provider is not registered"))
    start = time.perf_counter()
    try:
        health = asyncio.run(provider.health_check())
        latency = int((time.perf_counter() - start) * 1000)
        ok = health.get("status") == "ok"
        details.update({"connection": "Connected" if ok else "Failed", "latency": f"{latency} ms", "last_sync": utc_now(), "api_status": health.get("status_code", health.get("status", "Unknown"))})
        result = _status("healthy" if ok else "offline", "Healthy" if ok else "Connection Failed", "Connection verified" if ok else str(health.get("error", "Health check failed")))
    except Exception as exc:
        result = _status("offline", "Connection Failed", str(exc))
    return _base_row(integration_id, name, category, description, details=details, result=result)


def build_integration_status_center(services: Any) -> Dict[str, Any]:
    installed = _installed_configs()
    rows: List[StatusRow] = [
        _ai_provider("openai", "OpenAI", "AEGIS_AI_OPENAI_MODEL", ("AEGIS_AI_OPENAI_API_KEY", "OPENAI_API_KEY")),
        _ai_provider("anthropic", "Anthropic", "AEGIS_AI_ANTHROPIC_MODEL", ("AEGIS_AI_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")),
        _ai_provider("gemini", "Google Gemini", "AEGIS_AI_GEMINI_MODEL", ("AEGIS_AI_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")),
        _ai_provider("ollama", "Ollama", "AEGIS_AI_OLLAMA_MODEL", (), os.getenv("AEGIS_AI_OLLAMA_BASE_URL", "").rstrip("/") + "/api/tags" if os.getenv("AEGIS_AI_OLLAMA_BASE_URL") else ""),
        _docker_status(services),
        _installed_provider_status("prometheus", "Prometheus", "Infrastructure", "Metrics and target health.", installed),
        _installed_provider_status("grafana", "Grafana", "Infrastructure", "Dashboards and observability APIs.", installed),
        _tcp_infra("redis", "Redis", "REDIS_HOST", "REDIS_PORT", 6379),
        _tcp_infra("postgresql", "PostgreSQL", "POSTGRES_HOST", "POSTGRES_PORT", 5432),
        _sqlite_status(services),
        _installed_provider_status("slack", "Slack", "Notifications", "Workspace notifications.", installed),
        _installed_provider_status("discord", "Discord", "Notifications", "Discord bot or webhook notifications.", installed),
        _base_row("email", "Email", "Notifications", "SMTP notification delivery.", details={"connection": "Configured" if _env_first("SMTP_HOST", "AEGISNEX_SMTP_HOST") else "Not Configured"}, result=_status("warning" if _env_first("SMTP_HOST", "AEGISNEX_SMTP_HOST") else "unknown", "Needs Verification" if _env_first("SMTP_HOST", "AEGISNEX_SMTP_HOST") else "Not Configured", "SMTP settings present; send verification from notification settings" if _env_first("SMTP_HOST", "AEGISNEX_SMTP_HOST") else "SMTP host is not configured")),
        _installed_provider_status("teams", "Microsoft Teams", "Notifications", "Teams webhook or Graph notifications.", installed),
        _installed_provider_status("pagerduty", "PagerDuty", "Notifications", "Incident alerting and escalation.", installed),
        _installed_provider_status("github", "GitHub", "Developer Tools", "Repository and pull request access.", installed),
        _installed_provider_status("gitlab", "GitLab", "Developer Tools", "Repository and merge request access.", installed),
        _installed_provider_status("jira", "Jira", "Developer Tools", "Issue tracking and project sync.", installed),
        _base_row("aws", "AWS", "Cloud", "AWS account and region connectivity.", details={"region": os.getenv("AWS_REGION", "Not Configured"), "connection": "Configured" if _env_first("AWS_ACCESS_KEY_ID", "AWS_PROFILE") else "Not Configured"}, result=_status("warning" if _env_first("AWS_ACCESS_KEY_ID", "AWS_PROFILE") else "unknown", "Needs Verification" if _env_first("AWS_ACCESS_KEY_ID", "AWS_PROFILE") else "Not Configured", "Credentials present; cloud API verification is not configured" if _env_first("AWS_ACCESS_KEY_ID", "AWS_PROFILE") else "AWS credentials are not configured")),
        _base_row("azure", "Azure", "Cloud", "Azure subscription connectivity.", details={"region": os.getenv("AZURE_LOCATION", "Not Configured"), "connection": "Configured" if _env_first("AZURE_CLIENT_ID") else "Not Configured"}, result=_status("warning" if _env_first("AZURE_CLIENT_ID") else "unknown", "Needs Verification" if _env_first("AZURE_CLIENT_ID") else "Not Configured", "Credentials present; cloud API verification is not configured" if _env_first("AZURE_CLIENT_ID") else "Azure credentials are not configured")),
        _base_row("gcp", "Google Cloud", "Cloud", "Google Cloud project connectivity.", details={"region": os.getenv("GOOGLE_CLOUD_REGION", "Not Configured"), "connection": "Configured" if _env_first("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT") else "Not Configured"}, result=_status("warning" if _env_first("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT") else "unknown", "Needs Verification" if _env_first("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT") else "Not Configured", "Credentials present; cloud API verification is not configured" if _env_first("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT") else "Google Cloud credentials are not configured")),
        _base_row("mcp-filesystem", "Filesystem", "MCP", "Filesystem MCP server access.", details={"available_tools": "File read/write tools", "connection": "Available" if Path.cwd().exists() else "Unavailable"}, result=_status("healthy" if Path.cwd().exists() else "offline", "Healthy" if Path.cwd().exists() else "Unavailable", "Workspace filesystem is available" if Path.cwd().exists() else "Workspace filesystem is unavailable")),
        _base_row("mcp-github", "GitHub MCP", "MCP", "GitHub MCP tools.", details={"available_tools": "Configured by runtime", "connection": "Configured" if _env_first("GITHUB_TOKEN") else "Not Configured"}, result=_status("warning" if _env_first("GITHUB_TOKEN") else "unknown", "Needs Verification" if _env_first("GITHUB_TOKEN") else "Not Configured", "GitHub token is present" if _env_first("GITHUB_TOKEN") else "GitHub MCP credentials are not configured")),
        _base_row("mcp-browser", "Browser", "MCP", "Browser automation tools.", details={"available_tools": "Configured by runtime", "connection": "Runtime Managed"}, result=_status("unknown", "Unavailable", "Browser MCP availability is managed outside the backend")),
        _base_row("mcp-custom", "Custom Servers", "MCP", "Custom MCP server registry.", details={"available_tools": os.getenv("MCP_SERVERS", "Not Configured"), "connection": "Configured" if _env_first("MCP_SERVERS") else "Not Configured"}, result=_status("warning" if _env_first("MCP_SERVERS") else "unknown", "Needs Verification" if _env_first("MCP_SERVERS") else "Not Configured", "Custom MCP server configuration is present" if _env_first("MCP_SERVERS") else "No custom MCP servers configured")),
    ]
    configured_count = sum(1 for row in rows if row["status"] not in {"Not Configured", "Unavailable"})
    return {"categories": _group(rows), "integrations": rows, "configured_count": configured_count, "count": len(rows), "timestamp": utc_now()}


def _group(rows: Iterable[StatusRow]) -> List[Dict[str, Any]]:
    order = ["AI Providers", "Infrastructure", "Notifications", "Developer Tools", "Cloud", "MCP"]
    grouped: Dict[str, List[StatusRow]] = {name: [] for name in order}
    for row in rows:
        grouped.setdefault(str(row["category"]), []).append(row)
    return [{"name": name, "integrations": grouped[name], "count": len(grouped[name])} for name in order if grouped.get(name)]


def test_integration_connection(services: Any, integration_id: str) -> Dict[str, Any]:
    status = build_integration_status_center(services)
    for row in status["integrations"]:
        if row["id"] == integration_id:
            if row["status"] == "Not Configured":
                outcome = "Invalid Configuration"
            elif row["status"] == "Authentication Failed":
                outcome = "Authentication Failed"
            elif row["status"] in {"Service Offline", "Unavailable"}:
                outcome = "Host Unreachable"
            elif row["health"] == "healthy":
                outcome = "Success"
            else:
                outcome = row["status"]
            return {"status": "ok" if row["health"] == "healthy" else "error", "outcome": outcome, "integration": row}
    return {"status": "error", "outcome": "Invalid Configuration", "error": f"Unknown integration: {integration_id}"}
