from __future__ import annotations

from typing import Any

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class DiscordProvider(IntegrationProvider):
    name = "discord"
    description = "Discord server messaging and channel management"
    icon = "discord"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = "https://discord.com/api/v10"
        self.webhook_url = config.get("settings", {}).get("webhook_url", "")
        token = self._credentials.get("token") or self._credentials.get("bot_token")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "DiscordBot (AegisNex, 1.0)",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bot {token}"

    async def health_check(self) -> dict[str, Any]:
        if self.webhook_url:
            return {"status": "ok", "note": "webhook configured"}
        try:
            resp = self.session.get(f"{self.base_url}/users/@me", timeout=10)
            return {"status": "ok" if resp.ok else "error", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _send_via_webhook(self, content: str, params: dict[str, Any]) -> None:
        if not self.webhook_url:
            raise ValueError("webhook_url not configured")
        data = {"content": content}
        if params.get("username"):
            data["username"] = params["username"]
        if params.get("avatar_url"):
            data["avatar_url"] = params["avatar_url"]
        if params.get("embeds"):
            data["embeds"] = params["embeds"]
        resp = self.session.post(self.webhook_url, json=data, timeout=30)
        resp.raise_for_status()

    def _action_send_message(self, params: dict[str, Any]) -> Any:
        content = params.get("content", "") or params.get("text", "") or params.get("message", "")
        channel_id = params.get("channel_id")
        if not content and not channel_id:
            raise ValueError("content or channel_id is required")
        if self.webhook_url and not channel_id:
            self._send_via_webhook(content, params)
            return {"status": "sent", "method": "webhook"}
        if not channel_id:
            raise ValueError("channel_id is required for bot API")
        data = {"content": content}
        if params.get("embeds"):
            data["embeds"] = params["embeds"]
        if params.get("tts"):
            data["tts"] = True
        resp = self.session.post(
            f"{self.base_url}/channels/{channel_id}/messages", json=data, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _action_list_channels(self, params: dict[str, Any]) -> Any:
        guild_id = params.get("guild_id")
        if not guild_id:
            raise ValueError("guild_id is required")
        resp = self.session.get(f"{self.base_url}/guilds/{guild_id}/channels", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_create_thread(self, params: dict[str, Any]) -> Any:
        channel_id = params.get("channel_id")
        name = params.get("name")
        if not channel_id or not name:
            raise ValueError("channel_id and name are required")
        data = {
            "name": name,
            "type": params.get("type", 11),
            "auto_archive_duration": params.get("auto_archive_duration", 1440),
        }
        message_id = params.get("message_id")
        if message_id:
            resp = self.session.post(
                f"{self.base_url}/channels/{channel_id}/messages/{message_id}/threads",
                json=data,
                timeout=30,
            )
        else:
            resp = self.session.post(
                f"{self.base_url}/channels/{channel_id}/threads",
                json=data,
                timeout=30,
            )
        resp.raise_for_status()
        return resp.json()
