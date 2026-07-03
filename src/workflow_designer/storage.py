"""JSON-based workflow storage."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.workflow_designer.models import WorkflowDefinition


class WorkflowStorage:
    """Persists workflow definitions as pretty-printed JSON files."""

    def __init__(self, storage_dir: str = "workflows") -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, workflow_id: str) -> Path:
        return self._storage_dir / f"{workflow_id}.json"

    def save(self, workflow: WorkflowDefinition) -> str:
        workflow.updated_at = (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        if not workflow.id:
            workflow.id = uuid.uuid4().hex
        file_path = self._path_for(workflow.id)
        file_path.write_text(
            json.dumps(workflow.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return workflow.id

    def load(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        file_path = self._path_for(workflow_id)
        if not file_path.exists():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return WorkflowDefinition.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise RuntimeError(
                f"Failed to load workflow '{workflow_id}': {exc}"
            ) from exc

    def delete(self, workflow_id: str) -> bool:
        file_path = self._path_for(workflow_id)
        if not file_path.exists():
            return False
        file_path.unlink()
        return True

    def list(self) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for entry in sorted(self._storage_dir.iterdir()):
            if entry.suffix != ".json":
                continue
            try:
                data = json.loads(entry.read_text(encoding="utf-8"))
                summaries.append(
                    {
                        "id": data.get("id", entry.stem),
                        "name": data.get("name", ""),
                        "description": data.get("description", ""),
                        "version": data.get("version", ""),
                        "node_count": len(data.get("nodes", [])),
                        "edge_count": len(data.get("edges", [])),
                        "tags": data.get("tags", []),
                        "enabled": data.get("enabled", True),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                    }
                )
            except (json.JSONDecodeError, OSError):
                continue
        return summaries

    def get(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        file_path = self._path_for(workflow_id)
        if not file_path.exists():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(
                f"Failed to read workflow '{workflow_id}': {exc}"
            ) from exc

    def exists(self, workflow_id: str) -> bool:
        return self._path_for(workflow_id).exists()
