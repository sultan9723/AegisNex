from __future__ import annotations

from typing import Any

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class TeamsProvider(IntegrationProvider):
    name = "teams"
    description = "Microsoft Teams messaging and channel management"
    icon = "teams"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.webhook_url = config.get("settings", {}).get("webhook_url", "")
        self.tenant_id = config.get("settings", {}).get("tenant_id", "")
        self.client_id = self._credentials.get("client_id", "")
        self.client_secret = self._credentials.get("client_secret", "")
        self.graph_token: str = ""
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "AegisNex-Integration/1.0",
            }
        )

    def _ensure_graph_token(self) -> None:
        if not self.tenant_id or not self.client_id or not self.client_secret:
            return
        if self.graph_token:
            return
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        resp = requests.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data=data,
            timeout=30,
        )
        resp.raise_for_status()
        self.graph_token = resp.json().get("access_token", "")

    async def health_check(self) -> dict[str, Any]:
        if self.webhook_url:
            return {"status": "ok", "note": "webhook configured"}
        try:
            self._ensure_graph_token()
            if self.graph_token:
                return {"status": "ok", "note": "graph token acquired"}
            return {"status": "error", "note": "no webhook or graph credentials"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _send_via_webhook(self, message: str) -> None:
        if not self.webhook_url:
            raise ValueError("webhook_url not configured")
        payload = {
            "text": message,
            "type": "message",
            "attachments": [],
        }
        resp = self.session.post(self.webhook_url, json=payload, timeout=30)
        resp.raise_for_status()

    def _action_send_message(self, params: dict[str, Any]) -> Any:
        channel = params.get("channel", "")
        message = params.get("text", "") or params.get("message", "")
        if not message:
            raise ValueError("text is required")
        if self.webhook_url:
            self._send_via_webhook(message)
            return {"status": "sent", "method": "webhook"}
        self._ensure_graph_token()
        if not self.graph_token:
            raise ValueError("no webhook or graph credentials configured")
        team_id = params.get("team_id")
        channel_id = channel or params.get("channel_id")
        if not team_id or not channel_id:
            raise ValueError("team_id and channel_id are required for Graph API")
        headers = {"Authorization": f"Bearer {self.graph_token}"}
        data = {
            "body": {"contentType": "html", "content": message},
        }
        resp = requests.post(
            f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages",
            headers=headers,
            json=data,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _action_list_channels(self, params: dict[str, Any]) -> Any:
        self._ensure_graph_token()
        if not self.graph_token:
            raise ValueError("graph credentials required to list channels")
        team_id = params.get("team_id")
        if not team_id:
            raise ValueError("team_id is required")
        headers = {"Authorization": f"Bearer {self.graph_token}"}
        resp = requests.get(
            f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _action_create_channel(self, params: dict[str, Any]) -> Any:
        self._ensure_graph_token()
        if not self.graph_token:
            raise ValueError("graph credentials required to create channels")
        team_id = params.get("team_id")
        channel_name = params.get("name")
        if not team_id or not channel_name:
            raise ValueError("team_id and name are required")
        headers = {
            "Authorization": f"Bearer {self.graph_token}",
            "Content-Type": "application/json",
        }
        data = {
            "displayName": channel_name,
            "description": params.get("description", ""),
            "membershipType": params.get("membership_type", "standard"),
        }
        resp = requests.post(
            f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels",
            headers=headers,
            json=data,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
