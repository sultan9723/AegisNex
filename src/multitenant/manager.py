"""Tenant management — organizations, teams, projects, and user-org assignments."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from src.multitenant.models import Organization, Project, Team, TenantUser
from src.platform_db import PlatformRepository


def _slugify(name: str) -> str:
    s = name.lower().strip().replace(" ", "-").replace("_", "-")
    return re.sub(r"[^a-z0-9-]", "", s)[:64]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class TenantManager:
    """Manages multi-tenant organization, team, project, and user assignment data.

    All tables live in the same database as PlatformRepository.
    """

    def __init__(self, repo: PlatformRepository) -> None:
        self._repo = repo
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        with self._repo._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS organizations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL DEFAULT '',
                    settings TEXT NOT NULL DEFAULT '{}',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL REFERENCES organizations(id),
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    settings TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(org_id, slug)
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL REFERENCES organizations(id),
                    team_id INTEGER NOT NULL REFERENCES teams(id),
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(org_id, team_id, slug)
                );
                CREATE TABLE IF NOT EXISTS tenant_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    org_id INTEGER NOT NULL REFERENCES organizations(id),
                    role TEXT NOT NULL DEFAULT 'viewer',
                    permissions TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(user_id, org_id)
                );
                CREATE TABLE IF NOT EXISTS tenant_user_teams (
                    user_id INTEGER NOT NULL,
                    org_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    PRIMARY KEY (user_id, org_id, team_id)
                );
            """)

    def _p(self) -> str:
        return self._repo.placeholder

    def _execute(self, sql: str, params: tuple = ()) -> int | None:
        return self._repo._execute(sql, params)

    def _fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return self._repo._fetch_all(sql, params)

    def _fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = self._fetch_all(sql, params)
        return rows[0] if rows else None

    def _row_to_org(self, row: dict[str, Any]) -> Organization:
        return Organization(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            domain=row.get("domain", ""),
            settings=json.loads(row.get("settings", "{}")),
            is_active=bool(row.get("is_active", 1)),
            created_at=row.get("created_at", ""),
        )

    def _row_to_team(self, row: dict[str, Any]) -> Team:
        return Team(
            id=row["id"],
            org_id=row["org_id"],
            name=row["name"],
            slug=row["slug"],
            description=row.get("description", ""),
            settings=json.loads(row.get("settings", "{}")),
            created_at=row.get("created_at", ""),
        )

    def _row_to_project(self, row: dict[str, Any]) -> Project:
        return Project(
            id=row["id"],
            org_id=row["org_id"],
            team_id=row["team_id"],
            name=row["name"],
            slug=row["slug"],
            description=row.get("description", ""),
            created_at=row.get("created_at", ""),
        )

    def _row_to_tenant_user(
        self, row: dict[str, Any], team_ids: list[int] | None = None
    ) -> TenantUser:
        return TenantUser(
            id=row["id"],
            user_id=row["user_id"],
            org_id=row["org_id"],
            team_ids=team_ids or [],
            role=row.get("role", "viewer"),
            permissions=json.loads(row.get("permissions", "{}")),
        )

    # ---- Organizations ----

    def create_organization(
        self, name: str, domain: str = "", settings: dict[str, Any] | None = None
    ) -> Organization:
        slug = _slugify(name)
        now = _utc_now()
        settings_json = json.dumps(settings or {}, sort_keys=True)
        p = self._p()
        new_id = self._execute(
            f"INSERT INTO organizations (name, slug, domain, settings, is_active, created_at) VALUES ({p}, {p}, {p}, {p}, 1, {p})",
            (name, slug, domain, settings_json, now),
        )
        if new_id is None:
            rows = self._fetch_all(f"SELECT * FROM organizations WHERE slug = {p}", (slug,))
            if not rows:
                raise RuntimeError("Failed to create organization")
            return self._row_to_org(rows[0])
        self._repo.record_audit_log(
            "system", "create", "organization", str(new_id), {"name": name, "slug": slug}
        )
        return self.get_organization(new_id)

    def get_organization(self, org_id: int) -> Organization:
        p = self._p()
        row = self._fetch_one(f"SELECT * FROM organizations WHERE id = {p}", (org_id,))
        if row is None:
            raise ValueError(f"Organization {org_id} not found")
        return self._row_to_org(row)

    def list_organizations(self) -> list[Organization]:
        rows = self._fetch_all("SELECT * FROM organizations ORDER BY name")
        return [self._row_to_org(r) for r in rows]

    def update_organization(self, org_id: int, **updates: Any) -> Organization:
        existing = self.get_organization(org_id)
        allowed = {"name", "domain", "settings", "is_active"}
        fields: dict[str, Any] = {}
        for key, value in updates.items():
            if key in allowed:
                fields[key] = value
        if not fields:
            return existing
        if "name" in fields:
            fields["slug"] = _slugify(str(fields["name"]))
        if "settings" in fields and isinstance(fields["settings"], dict):
            fields["settings"] = json.dumps(fields["settings"], sort_keys=True)
        if "is_active" in fields:
            fields["is_active"] = 1 if fields["is_active"] else 0
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [org_id]
        p = self._p()
        self._execute(f"UPDATE organizations SET {set_clause} WHERE id = {p}", tuple(values))
        self._repo.record_audit_log("system", "update", "organization", str(org_id), fields)
        return self.get_organization(org_id)

    def deactivate_organization(self, org_id: int) -> bool:
        try:
            self.get_organization(org_id)
        except ValueError:
            return False
        p = self._p()
        self._execute(f"UPDATE organizations SET is_active = 0 WHERE id = {p}", (org_id,))
        self._repo.record_audit_log("system", "deactivate", "organization", str(org_id), {})
        return True

    # ---- Teams ----

    def create_team(self, org_id: int, name: str, description: str = "") -> Team:
        slug = _slugify(name)
        now = _utc_now()
        p = self._p()
        new_id = self._execute(
            f"INSERT INTO teams (org_id, name, slug, description, created_at) VALUES ({p}, {p}, {p}, {p}, {p})",
            (org_id, name, slug, description, now),
        )
        if new_id is None:
            rows = self._fetch_all(
                f"SELECT * FROM teams WHERE org_id = {p} AND slug = {p}", (org_id, slug)
            )
            if not rows:
                raise RuntimeError("Failed to create team")
            return self._row_to_team(rows[0])
        self._repo.record_audit_log(
            "system", "create", "team", str(new_id), {"org_id": org_id, "name": name}
        )
        return self._row_to_team(self._fetch_one(f"SELECT * FROM teams WHERE id = {p}", (new_id,)))

    def list_teams(self, org_id: int) -> list[Team]:
        p = self._p()
        rows = self._fetch_all(f"SELECT * FROM teams WHERE org_id = {p} ORDER BY name", (org_id,))
        return [self._row_to_team(r) for r in rows]

    # ---- Projects ----

    def create_project(
        self, org_id: int, team_id: int, name: str, description: str = ""
    ) -> Project:
        slug = _slugify(name)
        now = _utc_now()
        p = self._p()
        new_id = self._execute(
            f"INSERT INTO projects (org_id, team_id, name, slug, description, created_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p})",
            (org_id, team_id, name, slug, description, now),
        )
        if new_id is None:
            rows = self._fetch_all(
                f"SELECT * FROM projects WHERE org_id = {p} AND team_id = {p} AND slug = {p}",
                (org_id, team_id, slug),
            )
            if not rows:
                raise RuntimeError("Failed to create project")
            return self._row_to_project(rows[0])
        self._repo.record_audit_log(
            "system",
            "create",
            "project",
            str(new_id),
            {"org_id": org_id, "team_id": team_id, "name": name},
        )
        return self._row_to_project(
            self._fetch_one(f"SELECT * FROM projects WHERE id = {p}", (new_id,))
        )

    def list_projects(self, org_id: int, team_id: int | None = None) -> list[Project]:
        p = self._p()
        if team_id is not None:
            rows = self._fetch_all(
                f"SELECT * FROM projects WHERE org_id = {p} AND team_id = {p} ORDER BY name",
                (org_id, team_id),
            )
        else:
            rows = self._fetch_all(
                f"SELECT * FROM projects WHERE org_id = {p} ORDER BY name", (org_id,)
            )
        return [self._row_to_project(r) for r in rows]

    # ---- User assignments ----

    def assign_user_to_org(self, user_id: int, org_id: int, role: str = "read_only") -> TenantUser:
        p = self._p()
        from src.auth import Role as AuthRole

        normalized = AuthRole.from_str(role).value
        role = normalized
        self._execute(
            f"INSERT OR REPLACE INTO tenant_users (user_id, org_id, role, permissions) VALUES ({p}, {p}, {p}, {p})",
            (user_id, org_id, role, "{}"),
        )
        row = self._fetch_one(
            f"SELECT * FROM tenant_users WHERE user_id = {p} AND org_id = {p}", (user_id, org_id)
        )
        if row is None:
            raise RuntimeError("Failed to assign user to organization")
        tu = self._row_to_tenant_user(row)
        self._repo.record_audit_log(
            "system",
            "assign",
            "tenant_user",
            f"u{user_id}_o{org_id}",
            {"user_id": user_id, "org_id": org_id, "role": role},
        )
        return tu

    def get_user_tenants(self, user_id: int) -> list[TenantUser]:
        p = self._p()
        rows = self._fetch_all(f"SELECT * FROM tenant_users WHERE user_id = {p}", (user_id,))
        result: list[TenantUser] = []
        for row in rows:
            team_rows = self._fetch_all(
                f"SELECT team_id FROM tenant_user_teams WHERE user_id = {p} AND org_id = {p}",
                (user_id, row["org_id"]),
            )
            team_ids = [r["team_id"] for r in team_rows]
            result.append(self._row_to_tenant_user(row, team_ids))
        return result

    # ---- Org stats ----

    def get_org_stats(self, org_id: int) -> dict[str, Any]:
        p = self._p()
        user_rows = self._fetch_all(
            f"SELECT COUNT(*) AS cnt FROM tenant_users WHERE org_id = {p}", (org_id,)
        )
        team_rows = self._fetch_all(
            f"SELECT COUNT(*) AS cnt FROM teams WHERE org_id = {p}", (org_id,)
        )
        project_rows = self._fetch_all(
            f"SELECT COUNT(*) AS cnt FROM projects WHERE org_id = {p}", (org_id,)
        )
        return {
            "org_id": org_id,
            "user_count": user_rows[0]["cnt"] if user_rows else 0,
            "team_count": team_rows[0]["cnt"] if team_rows else 0,
            "project_count": project_rows[0]["cnt"] if project_rows else 0,
        }

    # ---- Isolation helpers ----

    def check_isolation(self, user_id: int, org_id: int) -> bool:
        p = self._p()
        row = self._fetch_one(
            f"SELECT 1 AS ok FROM tenant_users WHERE user_id = {p} AND org_id = {p}",
            (user_id, org_id),
        )
        return row is not None

    def get_role_inheritance(self, user_id: int, org_id: int) -> str:
        p = self._p()
        row = self._fetch_one(
            f"SELECT role FROM tenant_users WHERE user_id = {p} AND org_id = {p}", (user_id, org_id)
        )
        if row is None:
            return ""
        return str(row["role"])
