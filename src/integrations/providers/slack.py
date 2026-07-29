from __future__ import annotations

from typing import Any

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class SlackProvider(IntegrationProvider):
    name = "slack"
    description = "Slack workspace messaging and channel management"
    icon = "slack"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = "https://slack.com/api"
        token = self._credentials.get("token") or self._credentials.get("bot_token")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "AegisNex-Integration/1.0",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    async def health_check(self) -> dict[str, Any]:
        try:
            resp = self.session.get(f"{self.base_url}/auth.test", timeout=10)
            data = resp.json()
            return {"status": "ok" if data.get("ok") else "error", "data": data}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _action_send_message(self, params: dict[str, Any]) -> Any:
        channel = params.get("channel")
        if not channel:
            raise ValueError("channel is required")
        data = {
            "channel": channel,
            "text": params.get("text", ""),
        }
        if params.get("blocks"):
            data["blocks"] = params["blocks"]
        if params.get("thread_ts"):
            data["thread_ts"] = params["thread_ts"]
        resp = self.session.post(f"{self.base_url}/chat.postMessage", json=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise ValueError(result.get("error", "slack API error"))
        return result

    def _action_list_channels(self, params: dict[str, Any]) -> Any:
        query_params = {
            "exclude_archived": params.get("exclude_archived", True),
            "limit": params.get("limit", 100),
            "types": params.get("types", "public_channel"),
        }
        if params.get("cursor"):
            query_params["cursor"] = params["cursor"]
        resp = self.session.get(
            f"{self.base_url}/conversations.list", params=query_params, timeout=30
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise ValueError(result.get("error", "slack API error"))
        return result

    def _action_create_channel(self, params: dict[str, Any]) -> Any:
        name = params.get("name")
        if not name:
            raise ValueError("name is required")
        data = {
            "name": name,
            "is_private": params.get("is_private", False),
        }
        resp = self.session.post(f"{self.base_url}/conversations.create", json=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise ValueError(result.get("error", "slack API error"))
        return result

    def _action_invite_user(self, params: dict[str, Any]) -> Any:
        channel = params.get("channel")
        users = params.get("users")
        if not channel or not users:
            raise ValueError("channel and users are required")
        if isinstance(users, str):
            users = [users]
        data = {"channel": channel, "users": ",".join(users)}
        resp = self.session.post(f"{self.base_url}/conversations.invite", json=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise ValueError(result.get("error", "slack API error"))
        return result

    def _action_get_channel_history(self, params: dict[str, Any]) -> Any:
        channel = params.get("channel")
        if not channel:
            raise ValueError("channel is required")
        query_params = {
            "channel": channel,
            "limit": params.get("limit", 100),
        }
        if params.get("latest"):
            query_params["latest"] = params["latest"]
        if params.get("oldest"):
            query_params["oldest"] = params["oldest"]
        resp = self.session.get(
            f"{self.base_url}/conversations.history", params=query_params, timeout=30
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise ValueError(result.get("error", "slack API error"))
        return result
