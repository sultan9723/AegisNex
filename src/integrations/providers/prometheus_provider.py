from __future__ import annotations

from typing import Any, Dict

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class PrometheusIntegration(IntegrationProvider):
    name = "prometheus"
    description = "Prometheus metrics querying and alert management"
    icon = "prometheus"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("settings", {}).get("base_url", "http://localhost:9090").rstrip("/")
        self.api_url = f"{self.base_url}/api/v1"
        token = self._credentials.get("token") or self._credentials.get("bearer_token")
        username = self._credentials.get("username")
        password = self._credentials.get("password")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AegisNex-Integration/1.0",
        })
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        if username and password:
            self.session.auth = (username, password)

    async def health_check(self) -> Dict[str, Any]:
        try:
            resp = self.session.get(f"{self.base_url}/-/ready", timeout=10)
            return {"status": "ok" if resp.ok else "error", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: Dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _action_query(self, params: Dict[str, Any]) -> Any:
        query = params.get("query", "")
        if not query:
            raise ValueError("query is required")
        query_params = {"query": query}
        if params.get("time"):
            query_params["time"] = params["time"]
        resp = self.session.get(f"{self.api_url}/query", params=query_params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise ValueError(data.get("error", "prometheus query failed"))
        return data["data"]

    def _action_query_range(self, params: Dict[str, Any]) -> Any:
        query = params.get("query", "")
        start = params.get("start")
        end = params.get("end")
        step = params.get("step", "15s")
        if not query or not start or not end:
            raise ValueError("query, start, and end are required")
        query_params = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        }
        resp = self.session.get(f"{self.api_url}/query_range", params=query_params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise ValueError(data.get("error", "prometheus query_range failed"))
        return data["data"]

    def _action_list_targets(self, params: Dict[str, Any]) -> Any:
        state = params.get("state", "")  # active, dropped, any
        query_params = {}
        if state and state != "any":
            query_params["state"] = state
        resp = self.session.get(f"{self.api_url}/targets", params=query_params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise ValueError(data.get("error", "prometheus targets failed"))
        return data["data"]

    def _action_get_alerts(self, params: Dict[str, Any]) -> Any:
        resp = self.session.get(f"{self.api_url}/alerts", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise ValueError(data.get("error", "prometheus alerts failed"))
        return data["data"]
