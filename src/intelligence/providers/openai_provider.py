from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI

from src.intelligence.providers.base import (
    Message,
    ModelProvider,
    ProviderConfig,
    ToolCall,
)


class OpenAIProvider(ModelProvider):
    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        kwargs: Dict[str, Any] = {}
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        if self.config.organization:
            kwargs["organization"] = self.config.organization
        self._client = OpenAI(**kwargs)

    @property
    def provider_name(self) -> str:
        return "openai"

    def chat(self, messages: List[Message], **kwargs: Any) -> Message:
        resp = self._client.chat.completions.create(
            model=kwargs.get("model", self.config.model),
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        choice = resp.choices[0]
        return Message(role=choice.message.role or "assistant", content=choice.message.content or "")

    def chat_with_tools(
        self,
        messages: List[Message],
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Message:
        resp = self._client.chat.completions.create(
            model=kwargs.get("model", self.config.model),
            messages=[{"role": m.role, "content": m.content} for m in messages],
            tools=tools,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        choice = resp.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(name=tc.function.name, args=tc.function.arguments, id=tc.id))
        return Message(role=choice.message.role or "assistant", content=choice.message.content or "", tool_calls=tool_calls)

    def embed(self, text: str, **kwargs: Any) -> List[float]:
        resp = self._client.embeddings.create(
            model=kwargs.get("model", "text-embedding-3-small"),
            input=text,
        )
        return resp.data[0].embedding
