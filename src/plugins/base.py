"""Plugin base classes for the AegisNex plugin framework."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PluginType(str, Enum):
    TOOL = "tool"
    WORKFLOW = "workflow"
    AI_CAPABILITY = "ai_capability"
    INTEGRATION = "integration"
    NOTIFICATION = "notification"
    COMPLIANCE = "compliance"
    SKILL = "skill"


class PluginStatus(str, Enum):
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    plugin_type: PluginType
    description: str = ""
    author: str = ""
    license: str = ""
    dependencies: List[str] = field(default_factory=list)
    min_platform_version: str = "3.0.0"
    config_schema: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "plugin_type": self.plugin_type.value,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "dependencies": self.dependencies,
            "min_platform_version": self.min_platform_version,
        }


class Plugin(ABC):
    def __init__(self, manifest: PluginManifest) -> None:
        self._manifest = manifest
        self._status = PluginStatus.LOADED
        self._config: Dict[str, Any] = {}

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    @property
    def status(self) -> PluginStatus:
        return self._status

    def get_config(self) -> Dict[str, Any]:
        return dict(self._config)

    def set_config(self, config: Dict[str, Any]) -> None:
        self._config = dict(config)

    async def on_load(self) -> None:
        pass

    async def on_enable(self) -> None:
        self._status = PluginStatus.ENABLED

    async def on_disable(self) -> None:
        self._status = PluginStatus.DISABLED

    async def on_unload(self) -> None:
        self._status = PluginStatus.LOADED

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self._manifest.to_dict(),
            "status": self._status.value,
            "enabled": self._status == PluginStatus.ENABLED,
        }


class ToolPlugin(Plugin):
    def __init__(self, manifest: PluginManifest) -> None:
        super().__init__(manifest)
        self._manifest.plugin_type = PluginType.TOOL

    @abstractmethod
    def register_tools(self) -> List[Dict[str, Any]]:
        ...


class IntegrationPlugin(Plugin):
    def __init__(self, manifest: PluginManifest) -> None:
        super().__init__(manifest)
        self._manifest.plugin_type = PluginType.INTEGRATION

    @abstractmethod
    def get_client(self) -> Any:
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        ...


class SkillPlugin(Plugin):
    def __init__(self, manifest: PluginManifest) -> None:
        super().__init__(manifest)
        self._manifest.plugin_type = PluginType.SKILL
        self._required_tools: List[str] = []
        self._expected_outputs: List[str] = []

    @property
    def required_tools(self) -> List[str]:
        return list(self._required_tools)

    @property
    def expected_outputs(self) -> List[str]:
        return list(self._expected_outputs)

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ...
