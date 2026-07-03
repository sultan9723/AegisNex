from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import AzureOpenAI

from src.intelligence.providers.base import (
    Message,
    ModelProvider,
    ProviderConfig,
    ToolCall,
)


class AzureProvider(ModelProvider):
    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        kwargs: Dict[str, Any] = {"api_version": self.config.extra.get("api_version", "2024-08-01-preview")}
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        if self.config.base_url:
            kwargs["azure_endpoint"] = self.config.base_url
        if self.config.deployment_name:
            kwargs["azure_deployment"] = self.config.deployment_name
        self._client = AzureOpenAI(**kwargs)

    @property
    def provider_name(self) -> str:
        return "azure"

    def chat(self, messages: List[Message], **kwargs: Any) -> Message:
        deployment = kwargs.get("model", self.config.deployment_name or self.config.model)
        resp = self._client.chat.completions.create(
            model=deployment,
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
        deployment = kwargs.get("model", self.config.deployment_name or self.config.model)
        resp = self._client.chat.completions.create(
            model=deployment,
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
        deployment = kwargs.get("model", self.config.extra.get("embedding_deployment", "text-embedding-3-small"))
        resp = self._client.embeddings.create(model=deployment, input=text)
        return resp.data[0].embedding
