"""Registry of all available runbooks."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.intelligence.runbooks.parser import RunbookDef, RunbookParser


class RunbookRegistry:
    def __init__(self) -> None:
        self._runbooks: Dict[str, RunbookDef] = {}

    def register(self, runbook: RunbookDef) -> None:
        self._runbooks[runbook.name] = runbook

    def register_from_file(self, path: str) -> None:
        rb = RunbookParser.from_file(path)
        self.register(rb)

    def register_from_dict(self, data: Dict[str, Any]) -> None:
        rb = RunbookParser.from_dict(data)
        self.register(rb)

    def get(self, name: str) -> Optional[RunbookDef]:
        return self._runbooks.get(name)

    def list_all(self) -> List[RunbookDef]:
        return list(self._runbooks.values())

    def list(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        result = []
        for rb in self._runbooks.values():
            if category and rb.category != category:
                continue
            result.append(rb.to_dict())
        return result

    def list_categories(self) -> List[str]:
        return list({rb.category for rb in self._runbooks.values()})

    def count(self) -> int:
        return len(self._runbooks)

    def load_directory(self, directory: str) -> int:
        loaded = 0
        path = Path(directory)
        if not path.is_dir():
            return 0
        for ext in (".yaml", ".yml", ".json"):
            for fp in path.glob(f"*{ext}"):
                try:
                    self.register_from_file(str(fp))
                    loaded += 1
                except Exception:
                    continue
        return loaded

    def find_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        return [rb.to_dict() for rb in self._runbooks.values() if tag in rb.tags]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runbooks": [rb.to_dict() for rb in self._runbooks.values()],
            "count": self.count(),
            "categories": self.list_categories(),
        }


_GLOBAL_REGISTRY: Optional[RunbookRegistry] = None


def get_registry() -> RunbookRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = RunbookRegistry()
    return _GLOBAL_REGISTRY
