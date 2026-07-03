"""Data isolation utilities for multi-tenant queries and access validation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class TenantAwareQuery:
    """Wraps SQL queries with org_id filters for data isolation."""

    def __init__(self, org_id: int, table_column: str = "org_id") -> None:
        self.org_id = org_id
        self.table_column = table_column

    def filter(self, sql: str, params: Optional[tuple] = None) -> tuple[str, tuple]:
        """Inject an org_id WHERE clause into a SQL query."""
        if params is None:
            params = ()
        lower_sql = sql.lower().strip()
        filter_clause = f"{self.table_column} = ?"
        if lower_sql.startswith("select"):
            if "where" in lower_sql.split("from")[-1] if "from" in lower_sql else "":
                clause = f" AND {filter_clause}"
            else:
                clause = f" WHERE {filter_clause}"
            idx = sql.rfind("ORDER BY") if "ORDER BY" in sql else len(sql)
            idx = min(idx, sql.rfind("LIMIT") if "LIMIT" in sql else len(sql)) if "ORDER BY" not in sql else idx
            sql = sql[:idx] + clause + sql[idx:]
        else:
            sql = f"{sql} AND {filter_clause}" if "WHERE" in sql else f"{sql} WHERE {filter_clause}"
        return sql, params + (self.org_id,)


def isolate_query(query: str, org_id: int, table_column: str = "org_id") -> tuple[str, tuple]:
    """Add a WHERE org_id = ? clause to a query string."""
    aw = TenantAwareQuery(org_id, table_column)
    return aw.filter(query)


def get_isolation_filter(user: Any, resource_type: str) -> Dict[str, Any]:
    """Return a filter dict for scoping resource queries to the user's org.

    The user object must have an 'org_id' attribute (or one can be derived
    from user_tenants).
    """
    org_id = getattr(user, "org_id", None)
    if org_id is not None:
        return {"org_id": org_id}
    tenants = getattr(user, "tenants", None) or getattr(user, "user_tenants", None)
    if tenants and len(tenants) > 0:
        return {"org_id": tenants[0].org_id}
    return {}


def validate_tenant_access(user: Any, org_id: int, resource_id: Any, resource_type: str) -> bool:
    """Verify that a user has access to a resource within a specific org.

    Checks that the user belongs to the given org (via check_isolation style
    logic) and optionally that the resource exists under that org.
    """
    user_org_id = getattr(user, "org_id", None)
    if user_org_id is not None:
        return user_org_id == org_id
    tenants = getattr(user, "tenants", None) or getattr(user, "user_tenants", None)
    if tenants:
        return any(t.org_id == org_id for t in tenants)
    return False
