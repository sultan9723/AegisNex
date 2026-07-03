from __future__ import annotations

from typing import Any, Dict

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class GrafanaProvider(IntegrationProvider):
    name = "grafana"
    description = "Grafana dashboards, datasources, and alerting"
    icon = "grafana"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("settings", {}).get("base_url", "http://localhost:3000").rstrip("/")
        self.api_url = f"{self.base_url}/api"
        token = self._credentials.get("token") or self._credentials.get("api_token")
        username = self._credentials.get("username")
        password = self._credentials.get("password")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AegisNex-Integration/1.0",
        })
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        elif username and password:
            self.session.auth = (username, password)

    async def health_check(self) -> Dict[str, Any]:
        try:
            resp = self.session.get(f"{self.api_url}/health", timeout=10)
            return {"status": "ok" if resp.ok else "error", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: Dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _action_list_dashboards(self, params: Dict[str, Any]) -> Any:
        query_params = {
            "query": params.get("query", ""),
            "limit": params.get("limit", 50),
            "page": params.get("page", 1),
        }
        resp = self.session.get(f"{self.api_url}/search", params=query_params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_get_dashboard(self, params: Dict[str, Any]) -> Any:
        uid = params.get("uid")
        if not uid:
            raise ValueError("uid is required")
        resp = self.session.get(f"{self.api_url}/dashboards/uid/{uid}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_list_datasources(self, params: Dict[str, Any]) -> Any:
        resp = self.session.get(f"{self.api_url}/datasources", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_create_annotation(self, params: Dict[str, Any]) -> Any:
        data = {
            "text": params.get("text", ""),
            "tags": params.get("tags", []),
            "time": params.get("time", 0),
            "timeEnd": params.get("time_end", 0),
            "dashboardUID": params.get("dashboard_uid", ""),
            "panelId": params.get("panel_id", 0),
        }
        resp = self.session.post(f"{self.api_url}/annotations", json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_list_alerts(self, params: Dict[str, Any]) -> Any:
        query_params = {
            "limit": params.get("limit", 50),
            "state": params.get("state", ""),
            "folder": params.get("folder", ""),
            "dashboard_query": params.get("dashboard_query", ""),
            "dashboard_tag": params.get("dashboard_tag", ""),
        }
        resp = self.session.get(f"{self.api_url}/alerts", params=query_params, timeout=30)
        resp.raise_for_status()
        return resp.json()
