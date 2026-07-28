from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntegrationConfig:
    name: str
    enabled: bool = True
    credentials: dict[str, str] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntegrationResult:
    success: bool
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0


INTEGRATION_REGISTRY: dict[str, type[IntegrationProvider]] = {}


def register_integration(cls: type[IntegrationProvider]) -> type[IntegrationProvider]:
    name = getattr(cls, "name", cls.__name__.lower())
    INTEGRATION_REGISTRY[name] = cls
    return cls


def get_integration(name: str, config: dict[str, Any] | None = None) -> IntegrationProvider | None:
    cls = INTEGRATION_REGISTRY.get(name)
    if cls is None:
        return None
    return cls(config=config or {})


def list_integrations() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, cls in INTEGRATION_REGISTRY.items():
        try:
            inst = cls(config={})
            result[name] = {
                "name": inst.name,
                "description": inst.description,
                "icon": inst.icon,
            }
        except Exception:
            result[name] = {
                "name": name,
                "description": "",
                "icon": "",
            }
    return result


class IntegrationProvider(ABC):
    name = ""
    description = ""
    icon = ""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._credentials = config.get("credentials", {})
        self._settings = config.get("settings", {})

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def display_description(self) -> str:
        return self.description

    @property
    def display_icon(self) -> str:
        return self.icon

    @abstractmethod
    async def health_check(self) -> dict[str, Any]: ...

    @abstractmethod
    async def execute(self, action: str, params: dict[str, Any]) -> IntegrationResult: ...

    def _timed(self, fn, *args, **kwargs) -> IntegrationResult:
        start = time.perf_counter()
        try:
            data = fn(*args, **kwargs)
            elapsed = (time.perf_counter() - start) * 1000
            return IntegrationResult(success=True, data=data, duration_ms=round(elapsed, 2))
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return IntegrationResult(success=False, error=str(e), duration_ms=round(elapsed, 2))
