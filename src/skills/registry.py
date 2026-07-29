"""Skill registry for managing AI skill plugins."""

from __future__ import annotations

import builtins
from typing import Any

from src.plugins.base import PluginStatus, SkillPlugin


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillPlugin] = {}

    def register(self, skill: SkillPlugin) -> None:
        self._skills[skill.manifest.id] = skill

    def unregister(self, skill_id: str) -> bool:
        return self._skills.pop(skill_id, None) is not None

    def get(self, skill_id: str) -> SkillPlugin | None:
        return self._skills.get(skill_id)

    def list(self) -> builtins.list[dict[str, Any]]:
        return [skill.to_dict() for skill in self._skills.values()]

    def find_by_tool(self, tool_name: str) -> builtins.list[SkillPlugin]:
        return [skill for skill in self._skills.values() if tool_name in skill.required_tools]

    def get_enabled(self) -> builtins.list[SkillPlugin]:
        return [skill for skill in self._skills.values() if skill.status == PluginStatus.ENABLED]

    def enable(self, skill_id: str) -> bool:
        skill = self._skills.get(skill_id)
        if skill is None:
            return False
        skill._status = PluginStatus.ENABLED
        return True

    def disable(self, skill_id: str) -> bool:
        skill = self._skills.get(skill_id)
        if skill is None:
            return False
        skill._status = PluginStatus.DISABLED
        return True

    def count(self) -> int:
        return len(self._skills)
