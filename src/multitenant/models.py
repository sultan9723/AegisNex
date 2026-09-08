"""Data models for the Multi-Tenant module."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Organization:
    id: int
    name: str
    slug: str
    domain: str
    settings: dict = field(default_factory=dict)
    is_active: bool = True
    created_at: str = ""


@dataclass
class Team:
    id: int
    org_id: int
    name: str
    slug: str
    description: str = ""
    settings: dict = field(default_factory=dict)
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
    team_ids: list[int] = field(default_factory=list)
    role: str = "viewer"
    permissions: dict = field(default_factory=dict)
