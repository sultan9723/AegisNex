from __future__ import annotations

from typing import Any

from src.multitenant.manager import TenantManager


class FakePostgresRepository:
    backend = "postgresql"
    placeholder = "%s"

    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def _execute(self, sql: str, values: tuple[Any, ...] = ()) -> int | None:
        self.statements.append((sql, tuple(values)))
        return None

    def _fetch_all(self, sql: str, values: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.statements.append((sql, tuple(values)))
        if "FROM organizations WHERE slug" in sql:
            return [
                {
                    "id": 1,
                    "name": "Acme Security",
                    "slug": "acme-security",
                    "domain": "",
                    "settings": "{}",
                    "is_active": 1,
                    "created_at": "2026-09-14T00:00:00Z",
                }
            ]
        if "FROM organizations WHERE id" in sql:
            return [
                {
                    "id": values[0],
                    "name": "Renamed",
                    "slug": "renamed",
                    "domain": "",
                    "settings": "{}",
                    "is_active": 1,
                    "created_at": "2026-09-14T00:00:00Z",
                }
            ]
        if "FROM tenant_users" in sql:
            return [
                {
                    "id": 1,
                    "user_id": values[0],
                    "org_id": values[1],
                    "role": "operator",
                    "permissions": "{}",
                }
            ]
        return []

    def record_audit_log(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any],
    ) -> None:
        self.statements.append(
            (
                "AUDIT",
                (actor, action, resource_type, resource_id, details),
            )
        )


def test_tenant_manager_uses_postgres_compatible_schema_and_upsert() -> None:
    repo = FakePostgresRepository()

    manager = TenantManager(repo)  # type: ignore[arg-type]
    tenant_user = manager.assign_user_to_org(user_id=7, org_id=3, role="operator")

    sql = "\n".join(statement for statement, _ in repo.statements)
    assert "executescript" not in sql
    assert "SERIAL PRIMARY KEY" in sql
    assert "AUTOINCREMENT" not in sql
    assert "INSERT OR REPLACE" not in sql
    assert "ON CONFLICT (user_id, org_id)" in sql
    assert "VALUES (%s, %s, %s, %s)" in sql
    assert tenant_user.user_id == 7
    assert tenant_user.org_id == 3
    assert tenant_user.role == "operator"


def test_tenant_manager_update_organization_uses_repo_placeholder_for_postgres() -> None:
    repo = FakePostgresRepository()
    manager = TenantManager(repo)  # type: ignore[arg-type]

    manager.update_organization(1, name="Renamed")

    update_sql = next(
        statement
        for statement, _ in repo.statements
        if statement.startswith("UPDATE organizations")
    )
    assert "name = %s" in update_sql
    assert "slug = %s" in update_sql
    assert "id = %s" in update_sql
    assert "?" not in update_sql
