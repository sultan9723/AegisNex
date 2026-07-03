from __future__ import annotations

from typing import Any, Dict, List, Optional

import src.integrations.providers  # noqa: F401 — ensures all integrations are registered

from src.integrations.base import (
    INTEGRATION_REGISTRY,
    IntegrationConfig,
    IntegrationProvider,
    get_integration,
    list_integrations,
)
from src.intelligence.memory.sqlite_memory import SQLiteMemoryStore


def _get_store() -> SQLiteMemoryStore:
    return SQLiteMemoryStore(db_path="aegisnex.db")


CATALOG_METADATA: Dict[str, Dict[str, Any]] = {
    "github": {
        "name": "GitHub",
        "description": "Repository management, issue tracking, PRs, and commit history",
        "icon": "github",
        "category": "source_control",
        "docs_url": "https://docs.github.com/en/rest",
        "config_schema": {
            "credentials": {"token": {"type": "string", "required": True, "label": "Personal Access Token"}},
            "settings": {"base_url": {"type": "string", "required": False, "label": "API Base URL", "default": "https://api.github.com"}},
        },
    },
    "gitlab": {
        "name": "GitLab",
        "description": "Project management, issues, merge requests, and commits",
        "icon": "gitlab",
        "category": "source_control",
        "docs_url": "https://docs.gitlab.com/ee/api/",
        "config_schema": {
            "credentials": {"token": {"type": "string", "required": True, "label": "Personal Access Token"}},
            "settings": {"base_url": {"type": "string", "required": False, "label": "API Base URL", "default": "https://gitlab.com/api/v4"}},
        },
    },
    "jira": {
        "name": "Jira",
        "description": "Issue tracking, project management, and agile boards",
        "icon": "jira",
        "category": "project_management",
        "docs_url": "https://developer.atlassian.com/cloud/jira/platform/rest/",
        "config_schema": {
            "credentials": {
                "username": {"type": "string", "required": False, "label": "Email / Username"},
                "password": {"type": "string", "required": False, "label": "API Token / Password"},
                "token": {"type": "string", "required": False, "label": "Bearer Token"},
            },
            "settings": {"base_url": {"type": "string", "required": True, "label": "Jira Instance URL"}},
        },
    },
    "servicenow": {
        "name": "ServiceNow",
        "description": "ITSM incident management and service request fulfillment",
        "icon": "servicenow",
        "category": "itsm",
        "docs_url": "https://developer.servicenow.com/dev.do#!/reference/api/rest/",
        "config_schema": {
            "credentials": {
                "username": {"type": "string", "required": True, "label": "Username"},
                "password": {"type": "string", "required": True, "label": "Password"},
            },
            "settings": {"instance": {"type": "string", "required": True, "label": "Instance URL"}},
        },
    },
    "slack": {
        "name": "Slack",
        "description": "Messaging, channels, and workspace collaboration",
        "icon": "slack",
        "category": "communication",
        "docs_url": "https://api.slack.com/methods",
        "config_schema": {
            "credentials": {"token": {"type": "string", "required": True, "label": "Bot Token"}},
            "settings": {},
        },
    },
    "teams": {
        "name": "Microsoft Teams",
        "description": "Team messaging, channels, and collaboration via Microsoft Graph",
        "icon": "teams",
        "category": "communication",
        "docs_url": "https://learn.microsoft.com/en-us/graph/api/resources/teams-api-overview",
        "config_schema": {
            "credentials": {
                "client_id": {"type": "string", "required": False, "label": "Client ID"},
                "client_secret": {"type": "string", "required": False, "label": "Client Secret"},
            },
            "settings": {
                "webhook_url": {"type": "string", "required": False, "label": "Incoming Webhook URL"},
                "tenant_id": {"type": "string", "required": False, "label": "Tenant ID"},
            },
        },
    },
    "pagerduty": {
        "name": "PagerDuty",
        "description": "Incident alerting, on-call management, and escalation",
        "icon": "pagerduty",
        "category": "incident_response",
        "docs_url": "https://developer.pagerduty.com/api-reference/",
        "config_schema": {
            "credentials": {"token": {"type": "string", "required": True, "label": "API Token"}},
            "settings": {"routing_key": {"type": "string", "required": False, "label": "Events Routing Key"}},
        },
    },
    "discord": {
        "name": "Discord",
        "description": "Server messaging, channels, and thread management",
        "icon": "discord",
        "category": "communication",
        "docs_url": "https://discord.com/developers/docs/intro",
        "config_schema": {
            "credentials": {"token": {"type": "string", "required": False, "label": "Bot Token"}},
            "settings": {"webhook_url": {"type": "string", "required": False, "label": "Webhook URL"}},
        },
    },
    "kubernetes": {
        "name": "Kubernetes",
        "description": "Cluster management, pods, deployments, services, and nodes",
        "icon": "kubernetes",
        "category": "infrastructure",
        "docs_url": "https://kubernetes.io/docs/reference/",
        "config_schema": {
            "credentials": {},
            "settings": {
                "kubeconfig": {"type": "string", "required": False, "label": "Kubeconfig Path"},
                "context": {"type": "string", "required": False, "label": "Context Name"},
                "in_cluster": {"type": "bool", "required": False, "label": "Use In-Cluster Config"},
                "use_kubectl": {"type": "bool", "required": False, "label": "Use kubectl CLI"},
            },
        },
    },
    "prometheus": {
        "name": "Prometheus",
        "description": "Metrics querying, alert monitoring, and target discovery",
        "icon": "prometheus",
        "category": "monitoring",
        "docs_url": "https://prometheus.io/docs/prometheus/latest/querying/api/",
        "config_schema": {
            "credentials": {
                "token": {"type": "string", "required": False, "label": "Bearer Token"},
                "username": {"type": "string", "required": False, "label": "Username"},
                "password": {"type": "string", "required": False, "label": "Password"},
            },
            "settings": {"base_url": {"type": "string", "required": False, "label": "Prometheus URL", "default": "http://localhost:9090"}},
        },
    },
    "grafana": {
        "name": "Grafana",
        "description": "Dashboards, datasources, annotations, and alerting",
        "icon": "grafana",
        "category": "monitoring",
        "docs_url": "https://grafana.com/docs/grafana/latest/http_api/",
        "config_schema": {
            "credentials": {
                "token": {"type": "string", "required": False, "label": "API Token"},
                "username": {"type": "string", "required": False, "label": "Username"},
                "password": {"type": "string", "required": False, "label": "Password"},
            },
            "settings": {"base_url": {"type": "string", "required": False, "label": "Grafana URL", "default": "http://localhost:3000"}},
        },
    },
}


def get_marketplace_catalog() -> List[Dict[str, Any]]:
    """Return all available integrations with full metadata."""
    catalog: List[Dict[str, Any]] = []
    for name in INTEGRATION_REGISTRY:
        entry = dict(CATALOG_METADATA.get(name, {}))
        entry["integration_id"] = name
        if "name" not in entry:
            entry["name"] = name.title()
        if "description" not in entry:
            try:
                cls = INTEGRATION_REGISTRY[name]
                inst = cls(config={})
                entry["description"] = inst.description
            except Exception:
                entry["description"] = ""
        if "icon" not in entry:
            entry["icon"] = name
        if "category" not in entry:
            entry["category"] = "general"
        if "config_schema" not in entry:
            entry["config_schema"] = {"credentials": {}, "settings": {}}
        catalog.append(entry)
    return sorted(catalog, key=lambda x: x["name"])


def install_integration(name: str, config: Dict[str, Any]) -> Optional[IntegrationProvider]:
    """Install (register and persist) an integration by name.

    Args:
        name: Integration identifier (e.g. 'github', 'slack').
        config: Dict with optional 'credentials' and 'settings' keys.

    Returns:
        The instantiated IntegrationProvider, or None if the name is unknown.
    """
    provider = get_integration(name, config)
    if provider is None:
        return None

    credentials = config.get("credentials", {})
    settings = config.get("settings", {})
    store = _get_store()
    store.store_integration(
        name=name,
        enabled=True,
        credentials=credentials,
        settings=settings,
    )
    return provider


def uninstall_integration(name: str) -> bool:
    """Remove an installed integration from persistent storage."""
    store = _get_store()
    return store.remove_integration(name)


def get_installed_integrations() -> List[Dict[str, Any]]:
    """Return list of installed integrations with their stored config."""
    store = _get_store()
    integrations = store.get_integrations()
    result: List[Dict[str, Any]] = []
    for integration in integrations:
        name = integration.get("name", "")
        meta = CATALOG_METADATA.get(name, {})
        result.append({
            "integration_id": name,
            "name": meta.get("name", name.title()),
            "description": meta.get("description", ""),
            "icon": meta.get("icon", name),
            "category": meta.get("category", "general"),
            "enabled": integration.get("enabled", False),
            "credentials": integration.get("credentials", {}),
            "settings": integration.get("settings", {}),
            "created_at": integration.get("created_at", ""),
        })
    return result
