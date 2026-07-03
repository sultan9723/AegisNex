from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any]
    id: str = ""


@dataclass
class Message:
    role: str
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    name: Optional[str] = None


@dataclass
class ProviderConfig:
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 2048
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    organization: Optional[str] = None
    deployment_name: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class ModelProvider(ABC):
    config: ProviderConfig

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        self.config = config or ProviderConfig()

    @abstractmethod
    def chat(self, messages: List[Message], **kwargs: Any) -> Message:
        ...

    @abstractmethod
    def chat_with_tools(
        self,
        messages: List[Message],
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Message:
        ...

    @abstractmethod
    def embed(self, text: str, **kwargs: Any) -> List[float]:
        ...

    def count_tokens(self, text: str) -> int:
        import re
        return len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE))

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...
