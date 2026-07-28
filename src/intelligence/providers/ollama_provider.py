from __future__ import annotations

import json
from typing import Any

import httpx

from src.intelligence.providers.base import (
    Message,
    ModelProvider,
    ProviderConfig,
    ToolCall,
)


class OllamaProvider(ModelProvider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self._base_url = (self.config.base_url or "http://localhost:11434").rstrip("/")

    @property
    def provider_name(self) -> str:
        return "ollama"

    def chat(self, messages: list[Message], **kwargs: Any) -> Message:
        model = kwargs.get("model", self.config.model)
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            },
            "stream": False,
        }
        resp = httpx.post(f"{self._base_url}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return Message(
            role=data.get("message", {}).get("role", "assistant"),
            content=data.get("message", {}).get("content", ""),
        )

    def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> Message:
        model = kwargs.get("model", self.config.model)
        ollama_tools = []
        for t in tools:
            params = t.get("function", t).get("parameters", {})
            ollama_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.get("function", t).get("name", ""),
                        "description": t.get("function", t).get("description", ""),
                        "parameters": params,
                    },
                }
            )
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "tools": ollama_tools,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            },
            "stream": False,
        }
        resp = httpx.post(f"{self._base_url}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        msg = data.get("message", {})
        tool_calls = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            args_raw = fn.get("arguments", {})
            if isinstance(args_raw, str):
                try:
                    args_raw = json.loads(args_raw)
                except json.JSONDecodeError:
                    args_raw = {}
            tool_calls.append(ToolCall(name=fn.get("name", ""), args=args_raw, id=""))
        return Message(
            role=msg.get("role", "assistant"), content=msg.get("content", ""), tool_calls=tool_calls
        )

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        model = kwargs.get("model", "nomic-embed-text")
        resp = httpx.post(
            f"{self._base_url}/api/embeddings", json={"model": model, "prompt": text}, timeout=30
        )
        resp.raise_for_status()
        return resp.json().get("embedding", [])
