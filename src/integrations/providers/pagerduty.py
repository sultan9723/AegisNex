from __future__ import annotations

from typing import Any, Dict

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class PagerDutyProvider(IntegrationProvider):
    name = "pagerduty"
    description = "PagerDuty incident management and on-call coordination"
    icon = "pagerduty"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = "https://api.pagerduty.com"
        token = self._credentials.get("token") or self._credentials.get("api_token")
        if not token:
            raise ValueError("PagerDuty API token is required")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Content-Type": "application/json",
            "Authorization": f"Token token={token}",
            "User-Agent": "AegisNex-Integration/1.0",
        })
        self.routing_key = config.get("settings", {}).get("routing_key", "")

    async def health_check(self) -> Dict[str, Any]:
        try:
            resp = self.session.get(f"{self.base_url}/abilities", timeout=10)
            return {"status": "ok" if resp.ok else "error", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: Dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _action_trigger_incident(self, params: Dict[str, Any]) -> Any:
        routing_key = params.get("routing_key", self.routing_key)
        if not routing_key:
            raise ValueError("routing_key is required")
        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": params.get("summary", ""),
                "source": params.get("source", "AegisNex"),
                "severity": params.get("severity", "info"),
                "timestamp": params.get("timestamp", ""),
                "component": params.get("component", ""),
                "group": params.get("group", ""),
                "class": params.get("class", ""),
                "custom_details": params.get("custom_details", {}),
            },
            "dedup_key": params.get("dedup_key", ""),
        }
        resp = self.session.post("https://events.pagerduty.com/v2/enqueue", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_acknowledge_incident(self, params: Dict[str, Any]) -> Any:
        incident_id = params.get("incident_id")
        if not incident_id:
            raise ValueError("incident_id is required")
        requester_email = params.get("requester_email", "")
        if not requester_email:
            raise ValueError("requester_email is required")
        headers = {"From": requester_email}
        data = {"incident": {"status": "acknowledged"}}
        resp = self.session.put(
            f"{self.base_url}/incidents/{incident_id}",
            json=data,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _action_resolve_incident(self, params: Dict[str, Any]) -> Any:
        incident_id = params.get("incident_id")
        if not incident_id:
            raise ValueError("incident_id is required")
        requester_email = params.get("requester_email", "")
        if not requester_email:
            raise ValueError("requester_email is required")
        headers = {"From": requester_email}
        data = {"incident": {"status": "resolved"}}
        resp = self.session.put(
            f"{self.base_url}/incidents/{incident_id}",
            json=data,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _action_list_incidents(self, params: Dict[str, Any]) -> Any:
        query_params = {
            "statuses[]": params.get("statuses", ["triggered", "acknowledged"]),
            "limit": params.get("limit", 25),
            "offset": params.get("offset", 0),
            "sort_by": params.get("sort_by", "created_at:desc"),
        }
        if params.get("since"):
            query_params["since"] = params["since"]
        if params.get("until"):
            query_params["until"] = params["until"]
        if params.get("service_ids"):
            query_params["service_ids[]"] = params["service_ids"]
        resp = self.session.get(f"{self.base_url}/incidents", params=query_params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_list_services(self, params: Dict[str, Any]) -> Any:
        query_params = {
            "limit": params.get("limit", 25),
            "offset": params.get("offset", 0),
        }
        if params.get("query"):
            query_params["query"] = params["query"]
        resp = self.session.get(f"{self.base_url}/services", params=query_params, timeout=30)
        resp.raise_for_status()
        return resp.json()
