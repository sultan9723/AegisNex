"""Skill execution engine for running AI skills in the AegisNex platform."""

from __future__ import annotations

from typing import Any, Dict, List

from src.plugins.base import PluginStatus
from src.skills.builtin import create_default_skills
from src.skills.registry import SkillRegistry


class SkillEngine:
    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    async def execute_skill(self, skill_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        skill = self._registry.get(skill_id)
        if skill is None:
            return {"status": "error", "error": f"Skill '{skill_id}' not found"}
        if skill.status != PluginStatus.ENABLED:
            return {"status": "error", "error": f"Skill '{skill_id}' is not enabled"}
        try:
            result = await skill.execute(context)
            result.setdefault("skill_id", skill_id)
            return result
        except Exception as exc:
            return {"status": "error", "skill_id": skill_id, "error": str(exc)}

    async def auto_select_skills(self, task: str) -> List[Any]:
        task_lower = task.lower()
        matched: List[Any] = []
        for skill in self._registry.get_enabled():
            name = skill.manifest.name.lower()
            desc = skill.manifest.description.lower()
            tools = " ".join(skill.required_tools)
            combined = f"{name} {desc} {tools}"
            if any(kw in task_lower for kw in combined.split()):
                matched.append(skill)
        if not matched:
            for skill in self._registry.get_enabled():
                desc_words = skill.manifest.description.lower().split()
                if any(w in task_lower for w in desc_words if len(w) > 3):
                    matched.append(skill)
        seen: set = set()
        unique: List[Any] = []
        for s in matched:
            if s.manifest.id not in seen:
                seen.add(s.manifest.id)
                unique.append(s)
        return unique

    async def execute_pipeline(self, skill_ids: List[str], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        pipeline_context = dict(context)
        for skill_id in skill_ids:
            result = await self.execute_skill(skill_id, pipeline_context)
            results.append(result)
            if result.get("status") == "ok":
                pipeline_context.update(result)
        return results

    def get_skill_tools(self, skill_id: str) -> List[str]:
        skill = self._registry.get(skill_id)
        if skill is None:
            return []
        return skill.required_tools

    def validate_skill_output(self, skill_id: str, output: Dict[str, Any]) -> bool:
        skill = self._registry.get(skill_id)
        if skill is None:
            return False
        expected = skill.expected_outputs
        if not expected:
            return True
        return all(e in output for e in expected)


def create_default_engine() -> SkillEngine:
    registry = SkillRegistry()
    for skill in create_default_skills():
        registry.register(skill)
        registry.enable(skill.manifest.id)
    return SkillEngine(registry)
