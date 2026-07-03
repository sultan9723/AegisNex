from __future__ import annotations

from typing import Any, Dict

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class ServiceNowProvider(IntegrationProvider):
    name = "servicenow"
    description = "ServiceNow IT Service Management"
    icon = "servicenow"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.instance = config.get("settings", {}).get("instance", "").rstrip("/")
        if not self.instance:
            raise ValueError("ServiceNow instance URL is required in settings")
        self.api_url = f"{self.instance}/api/now"
        username = self._credentials.get("username")
        password = self._credentials.get("password")
        if not username or not password:
            raise ValueError("ServiceNow credentials (username, password) are required")
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AegisNex-Integration/1.0",
        })

    async def health_check(self) -> Dict[str, Any]:
        try:
            resp = self.session.get(f"{self.api_url}/table/incident?sysparm_limit=1", timeout=10)
            return {"status": "ok" if resp.ok else "error", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: Dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _action_create_incident(self, params: Dict[str, Any]) -> Any:
        data = {
            "short_description": params.get("short_description", ""),
            "description": params.get("description", ""),
            "urgency": params.get("urgency", "3"),
            "impact": params.get("impact", "3"),
            "category": params.get("category", ""),
            "caller_id": params.get("caller_id", ""),
            "assignment_group": params.get("assignment_group", ""),
            "assigned_to": params.get("assigned_to", ""),
        }
        resp = self.session.post(f"{self.api_url}/table/incident", json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_update_incident(self, params: Dict[str, Any]) -> Any:
        sys_id = params.get("sys_id")
        if not sys_id:
            raise ValueError("sys_id is required")
        data = {}
        for field in ("short_description", "description", "urgency", "impact", "state", "category",
                       "assignment_group", "assigned_to", "work_notes"):
            if field in params:
                data[field] = params[field]
        if not data:
            raise ValueError("at least one field to update is required")
        resp = self.session.patch(f"{self.api_url}/table/incident/{sys_id}", json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_get_incident(self, params: Dict[str, Any]) -> Any:
        sys_id = params.get("sys_id")
        if not sys_id:
            raise ValueError("sys_id is required")
        resp = self.session.get(f"{self.api_url}/table/incident/{sys_id}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_search_incidents(self, params: Dict[str, Any]) -> Any:
        query_params = {
            "sysparm_query": params.get("query", ""),
            "sysparm_limit": params.get("limit", 50),
            "sysparm_offset": params.get("offset", 0),
            "sysparm_display_value": params.get("display_value", "true"),
        }
        if params.get("fields"):
            query_params["sysparm_fields"] = ",".join(params["fields"])
        resp = self.session.get(f"{self.api_url}/table/incident", params=query_params, timeout=30)
        resp.raise_for_status()
        return resp.json()
