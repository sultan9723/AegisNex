"""Data models for the Multi-Tenant module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Organization:
    id: int
    name: str
    slug: str
    domain: str
    settings: Dict = field(default_factory=dict)
    is_active: bool = True
    created_at: str = ""


@dataclass
class Team:
    id: int
    org_id: int
    name: str
    slug: str
    description: str = ""
    settings: Dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class Project:
    id: int
    org_id: int
    team_id: int
    name: str
    slug: str
    description: str = ""
    created_at: str = ""


@dataclass
class TenantUser:
    id: int
    user_id: int
    org_id: int
    team_ids: List[int] = field(default_factory=list)
    role: str = "viewer"
    permissions: Dict = field(default_factory=dict)
