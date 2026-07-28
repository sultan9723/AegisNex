from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str = ""


@dataclass
class Message:
    role: str
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    name: str | None = None


@dataclass
class ProviderConfig:
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 2048
    api_key: str | None = None
    base_url: str | None = None
    organization: str | None = None
    deployment_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ModelProvider(ABC):
    config: ProviderConfig

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    @abstractmethod
    def chat(self, messages: list[Message], **kwargs: Any) -> Message: ...

    @abstractmethod
    def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> Message: ...

    @abstractmethod
    def embed(self, text: str, **kwargs: Any) -> list[float]: ...

    def count_tokens(self, text: str) -> int:
        import re

        return len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE))

    @property
    @abstractmethod
    def provider_name(self) -> str: ...
