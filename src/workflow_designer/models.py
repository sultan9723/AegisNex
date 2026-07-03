"""Data models for visual workflow definitions."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


class WorkflowNodeType(str, enum.Enum):
    TRIGGER = "TRIGGER"
    AI_PLANNING = "AI_PLANNING"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    APPROVAL = "APPROVAL"
    RUNBOOK = "RUNBOOK"
    NOTIFICATION = "NOTIFICATION"
    CONDITION = "CONDITION"
    END = "END"


@dataclass
class WorkflowNode:
    id: str
    type: WorkflowNodeType
    label: str
    config: Dict[str, Any] = field(default_factory=dict)
    position: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
            "config": self.config,
            "position": self.position,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowNode:
        return cls(
            id=data["id"],
            type=WorkflowNodeType(data["type"]),
            label=data.get("label", ""),
            config=data.get("config", {}),
            position=data.get("position", {"x": 0.0, "y": 0.0}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class WorkflowEdge:
    id: str
    source: str
    target: str
    label: str = ""
    condition: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "condition": self.condition,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowEdge:
        return cls(
            id=data["id"],
            source=data["source"],
            target=data["target"],
            label=data.get("label", ""),
            condition=data.get("condition", ""),
        )


@dataclass
class WorkflowDefinition:
    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    nodes: List[WorkflowNode] = field(default_factory=list)
    edges: List[WorkflowEdge] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    enabled: bool = True

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowDefinition:
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            nodes=[WorkflowNode.from_dict(n) for n in data.get("nodes", [])],
            edges=[WorkflowEdge.from_dict(e) for e in data.get("edges", [])],
            tags=data.get("tags", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            enabled=data.get("enabled", True),
        )

    def validate(self) -> Tuple[bool, List[str]]:
        errors: List[str] = []

        if not self.id:
            errors.append("Workflow ID is required")
        if not self.name:
            errors.append("Workflow name is required")
        if not self.nodes:
            errors.append("Workflow must have at least one node")
        if not self.edges:
            errors.append("Workflow must have at least one edge")

        node_ids = {n.id for n in self.nodes}

        # Check for duplicate node IDs
        if len(node_ids) != len(self.nodes):
            seen: List[str] = []
            for n in self.nodes:
                if n.id in seen:
                    errors.append(f"Duplicate node id: {n.id}")
                seen.append(n.id)

        # All edges reference valid nodes
        for edge in self.edges:
            if edge.source not in node_ids:
                errors.append(f"Edge {edge.id} references unknown source node: {edge.source}")
            if edge.target not in node_ids:
                errors.append(f"Edge {edge.id} references unknown target node: {edge.target}")

        # Must have exactly one TRIGGER node (no incoming edges)
        trigger_nodes = [n for n in self.nodes if n.type == WorkflowNodeType.TRIGGER]
        if len(trigger_nodes) != 1:
            errors.append("Workflow must have exactly one TRIGGER node")

        # Must have at least one END node
        end_nodes = [n for n in self.nodes if n.type == WorkflowNodeType.END]
        if not end_nodes:
            errors.append("Workflow must have at least one END node")

        # All nodes (except TRIGGER) must have at least one incoming edge
        has_incoming = {s for s, _ in {(e.target, e.source) for e in self.edges}}
        for node in self.nodes:
            if node.type != WorkflowNodeType.TRIGGER and node.id not in has_incoming:
                errors.append(f"Node '{node.id}' ({node.label}) has no incoming connections")

        # CONDITION nodes must have at least two outgoing edges
        for node in self.nodes:
            if node.type == WorkflowNodeType.CONDITION:
                outgoing = [e for e in self.edges if e.source == node.id]
                if len(outgoing) < 2:
                    errors.append(
                        f"CONDITION node '{node.id}' must have at least 2 outgoing edges, "
                        f"found {len(outgoing)}"
                    )

        return (len(errors) == 0, errors)

    def to_execution_graph(self) -> List[Dict[str, Any]]:
        _, errors = self.validate()
        if errors:
            raise ValueError(f"Invalid workflow: {'; '.join(errors)}")

        adjacency: Dict[str, List[Tuple[str, str]]] = {}
        for edge in self.edges:
            adjacency.setdefault(edge.source, []).append((edge.target, edge.condition))

        trigger = next(n for n in self.nodes if n.type == WorkflowNodeType.TRIGGER)
        ordered: List[Dict[str, Any]] = []
        visited: set = set()

        def _traverse(node_id: str) -> None:
            if node_id in visited:
                return
            visited.add(node_id)
            node = next((n for n in self.nodes if n.id == node_id), None)
            if node is None:
                return
            entry = {
                "node_id": node.id,
                "type": node.type.value,
                "label": node.label,
                "config": dict(node.config),
            }
            if node.type == WorkflowNodeType.CONDITION:
                outgoing = adjacency.get(node_id, [])
                entry["branches"] = [
                    {"target": t, "condition": c} for t, c in outgoing
                ]
            ordered.append(entry)
            if node.type == WorkflowNodeType.END:
                return
            if node.type == WorkflowNodeType.CONDITION:
                for target_id, condition in adjacency.get(node_id, []):
                    _traverse(target_id)
            else:
                targets = adjacency.get(node_id, [])
                if targets:
                    _traverse(targets[0][0])

        _traverse(trigger.id)
        return ordered
