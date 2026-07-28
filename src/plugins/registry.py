"""Plugin registry — lifecycle management for all plugins."""

from __future__ import annotations

import importlib
import inspect
import os
import sys
from pathlib import Path
from typing import Any

from src.plugins.base import (
    IntegrationPlugin,
    Plugin,
    PluginManifest,
    PluginType,
    SkillPlugin,
    ToolPlugin,
)


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._plugin_dirs: list[str] = []

    def register(self, plugin: Plugin) -> None:
        self._plugins[plugin.manifest.id] = plugin

    def unregister(self, plugin_id: str) -> bool:
        return self._plugins.pop(plugin_id, None) is not None

    def get(self, plugin_id: str) -> Plugin | None:
        return self._plugins.get(plugin_id)

    def get_by_type(self, plugin_type: PluginType) -> list[Plugin]:
        return [p for p in self._plugins.values() if p.manifest.plugin_type == plugin_type]

    def list_all(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._plugins.values()]

    def count(self) -> int:
        return len(self._plugins)

    def enable(self, plugin_id: str) -> bool:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return False
        try:
            import asyncio

            asyncio.get_event_loop().run_until_complete(plugin.on_enable())
            return True
        except RuntimeError:
            import asyncio

            loop = asyncio.new_event_loop()
            loop.run_until_complete(plugin.on_enable())
            return True

    def disable(self, plugin_id: str) -> bool:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return False
        try:
            import asyncio

            asyncio.get_event_loop().run_until_complete(plugin.on_disable())
            return True
        except RuntimeError:
            return True

    def add_plugin_dir(self, directory: str) -> None:
        resolved = str(Path(directory).resolve())
        if resolved not in sys.path:
            sys.path.insert(0, str(Path(directory).parent))
        if resolved not in self._plugin_dirs:
            self._plugin_dirs.append(resolved)

    def scan_and_load(self, directory: str | None = None) -> int:
        loaded = 0
        scan_dirs = [directory] if directory else list(self._plugin_dirs)
        if not scan_dirs:
            default = os.path.join(os.path.dirname(__file__), "..", "integrations", "providers")
            if os.path.isdir(default):
                scan_dirs.append(default)

        for scan_dir in scan_dirs:
            path = Path(scan_dir)
            if not path.is_dir():
                continue
            for entry in path.iterdir():
                if entry.suffix == ".py" and entry.stem != "__init__":
                    try:
                        plugin = self._load_plugin_from_module(str(entry))
                        if plugin:
                            self.register(plugin)
                            loaded += 1
                    except Exception:
                        pass
        return loaded

    def _load_plugin_from_module(self, filepath: str) -> Plugin | None:
        module_name = Path(filepath).stem
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, (ToolPlugin, IntegrationPlugin, SkillPlugin))
                and obj is not ToolPlugin
                and obj is not IntegrationPlugin
                and obj is not SkillPlugin
            ):
                manifest_attr = getattr(obj, "manifest", None)
                if isinstance(manifest_attr, PluginManifest):
                    return obj(manifest_attr)
                manifest = self._try_extract_manifest(obj)
                if manifest:
                    return obj(manifest)
        return None

    def _try_extract_manifest(self, cls: type) -> PluginManifest | None:
        defaults = {
            "id": getattr(cls, "plugin_id", cls.__name__.lower()),
            "name": getattr(cls, "plugin_name", cls.__name__),
            "version": getattr(cls, "plugin_version", "1.0.0"),
            "description": getattr(cls, "plugin_description", ""),
        }
        plugin_type = PluginType.TOOL
        if issubclass(cls, IntegrationPlugin):
            plugin_type = PluginType.INTEGRATION
        elif issubclass(cls, SkillPlugin):
            plugin_type = PluginType.SKILL
        return PluginManifest(**defaults, plugin_type=plugin_type)


_GLOBAL_REGISTRY: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = PluginRegistry()
        default_dirs = [
            os.path.join(os.path.dirname(__file__), "..", "integrations", "providers"),
            os.path.join(os.path.dirname(__file__), "..", "skills"),
        ]
        for d in default_dirs:
            if os.path.isdir(d):
                _GLOBAL_REGISTRY.add_plugin_dir(d)
        _GLOBAL_REGISTRY.scan_and_load()
    return _GLOBAL_REGISTRY
