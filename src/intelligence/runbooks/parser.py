"""Parse runbook definitions from YAML and JSON."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RunbookStep:
    name: str
    action: str
    tool: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 60
    on_failure: str = "stop"
    requires_approval: bool = False
    condition: Optional[str] = None
    retry_count: int = 0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "action": self.action,
            "tool": self.tool,
            "params": self.params,
            "timeout_seconds": self.timeout_seconds,
            "on_failure": self.on_failure,
            "requires_approval": self.requires_approval,
            "condition": self.condition,
            "retry_count": self.retry_count,
            "description": self.description,
        }


@dataclass
class RunbookDef:
    name: str
    description: str
    version: str = "1.0"
    category: str = "general"
    steps: List[RunbookStep] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    timeout_seconds: int = 300
    parallel_steps: List[List[str]] = field(default_factory=list)
    requires_incident: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "steps": [s.to_dict() for s in self.steps],
            "tags": self.tags,
            "timeout_seconds": self.timeout_seconds,
            "parallel_steps": self.parallel_steps,
            "requires_incident": self.requires_incident,
        }


class RunbookParser:
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> RunbookDef:
        steps = []
        for s in data.get("steps", []):
            steps.append(RunbookStep(
                name=s.get("name", ""),
                action=s.get("action", ""),
                tool=s.get("tool", ""),
                params=s.get("params", {}),
                timeout_seconds=s.get("timeout_seconds", 60),
                on_failure=s.get("on_failure", "stop"),
                requires_approval=s.get("requires_approval", False),
                condition=s.get("condition"),
                retry_count=s.get("retry_count", 0),
                description=s.get("description", ""),
            ))
        return RunbookDef(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=str(data.get("version", "1.0")),
            category=data.get("category", "general"),
            steps=steps,
            tags=data.get("tags", []),
            timeout_seconds=data.get("timeout_seconds", 300),
            parallel_steps=data.get("parallel_steps", []),
            requires_incident=data.get("requires_incident", False),
        )

    @staticmethod
    def from_json(path: str) -> RunbookDef:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return RunbookParser.from_dict(data)

    @staticmethod
    def from_yaml(path: str) -> RunbookDef:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return RunbookParser.from_dict(data)

    @staticmethod
    def from_file(path: str) -> RunbookDef:
        ext = Path(path).suffix.lower()
        if ext in (".yaml", ".yml"):
            return RunbookParser.from_yaml(path)
        elif ext == ".json":
            return RunbookParser.from_json(path)
        else:
            raise ValueError(f"Unsupported runbook format: {ext}")
