"""Core AgentX registry and dispatcher."""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Any


class AgentX:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("agentx")
        self.commands: dict[str, Any] = {}

    def register_command(self, name: str, instance: Any) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Command name must be a non-empty string.")
        self.commands[name] = instance

    def register_command_by_path(
        self,
        name: str,
        module_path: str,
        class_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        try:
            module = import_module(module_path)
            command_cls = getattr(module, class_name)
            instance = command_cls(*args, **kwargs)
            self.register_command(name, instance)
            return instance
        except Exception:
            self.logger.exception(
                "Failed to register command %s from %s.%s",
                name,
                module_path,
                class_name,
            )
            raise

    def execute_task(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in self.commands:
            message = f"Unknown command: {name}"
            self.logger.error(message)
            raise KeyError(message)

        command = self.commands[name]
        try:
            if callable(command):
                return command(*args, **kwargs)
            if hasattr(command, "get_stats"):
                return command.get_stats(*args, **kwargs)
            if hasattr(command, "run"):
                return command.run(*args, **kwargs)
            raise AttributeError(f"Command '{name}' has no callable interface.")
        except Exception:
            self.logger.exception("Command execution failed: %s", name)
            raise
