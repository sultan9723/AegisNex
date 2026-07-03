from __future__ import annotations

from typing import Any, Dict, List, Optional

import anthropic
from anthropic.types import MessageParam, ToolUseBlock

from src.intelligence.providers.base import (
    Message,
    ModelProvider,
    ProviderConfig,
    ToolCall,
)


class AnthropicProvider(ModelProvider):
    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        self._client = anthropic.Anthropic(api_key=self.config.api_key)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def chat(self, messages: List[Message], **kwargs: Any) -> Message:
        model = kwargs.get("model", self.config.model)
        resp = self._client.messages.create(
            model=model,
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            temperature=kwargs.get("temperature", self.config.temperature),
            system="You are an AI operations assistant for AegisNex infrastructure monitoring.",
            messages=[MessageParam(role=m.role, content=m.content) for m in messages if m.role != "system"],
        )
        return Message(role="assistant", content=resp.content[0].text if resp.content else "")

    def chat_with_tools(
        self,
        messages: List[Message],
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Message:
        model = kwargs.get("model", self.config.model)
        anthropic_tools = []
        for t in tools:
            fn = t.get("function", t)
            anthropic_tools.append({"name": fn.get("name", ""), "description": fn.get("description", ""), "input_schema": fn.get("parameters", {"type": "object", "properties": {}})})
        resp = self._client.messages.create(
            model=model,
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            temperature=kwargs.get("temperature", self.config.temperature),
            system="You are an AI operations assistant for AegisNex infrastructure monitoring.",
            messages=[MessageParam(role=m.role, content=m.content) for m in messages if m.role != "system"],
            tools=anthropic_tools,
        )
        content_blocks = resp.content
        text = ""
        tool_calls = []
        for block in content_blocks:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                assert isinstance(block, ToolUseBlock)
                tool_calls.append(ToolCall(name=block.name, args=dict(block.input), id=block.id))
        return Message(role="assistant", content=text, tool_calls=tool_calls)

    def embed(self, text: str, **kwargs: Any) -> List[float]:
        raise NotImplementedError("Anthropic does not provide a standalone embedding API through this SDK path")
