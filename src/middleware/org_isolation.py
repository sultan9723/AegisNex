"""Middleware and helpers for org-level data isolation."""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.multitenant.isolation import get_isolation_filter

_logger = logging.getLogger(__name__)

# Resource types that support org_id scoping
ORG_SCOPED_RESOURCES = {
    "incidents",
    "monitoring_targets",
    "check_results",
    "notifications",
    "remediation_actions",
    "reports",
    "alert_rules",
    "secrets",
}


class OrgIsolationMiddleware(BaseHTTPMiddleware):
    """Middleware that attaches the user's org context to ``request.state``.

    It reads the authenticated user from ``request.state.user`` and, if the
    user has tenant assignments, sets ``request.state.org_id`` to the first
    org.  Super-admin / administrator users are exempt (they see all orgs).
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        user = getattr(request.state, "user", None)
        org_id: int | None = None

        if user is not None:
            role = getattr(user, "role", "")
            if role in ("super_admin", "administrator"):
                # Admins see everything — no org filter
                org_id = None
            else:
                # Try to get org_id from request header (set by frontend)
                header_org = request.headers.get("X-Org-Id", "")
                if header_org:
                    try:
                        org_id = int(header_org)
                    except (ValueError, TypeError):
                        pass

                if org_id is None:
                    # Derive from user object
                    tenants = getattr(user, "tenants", None) or getattr(user, "user_tenants", None)
                    if tenants and len(tenants) > 0:
                        org_id = tenants[0].org_id

        request.state.org_id = org_id
        return await call_next(request)


def require_org_access(resource_type: str) -> Callable:
    """Factory for a dependency that enforces org-scoped access.

    Usage::

        @router.get("/incidents")
        async def list_incidents(
            request: Request,
            _=Depends(require_org_access("incidents")),
        ):
            ...

    The dependency checks:
    1. If the user is super_admin/administrator → allow (no filter needed).
    2. If the user has an ``org_id`` in request state → allow.
    3. Otherwise → 403 Forbidden.
    """

    async def dependency(request: Request) -> None:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

        role = getattr(user, "role", "")
        if role in ("super_admin", "administrator"):
            return

        # Get org_id from request state (set by OrgIsolationMiddleware)
        org_id = getattr(request.state, "org_id", None)
        if org_id is not None:
            return

        # Try header fallback
        header_org = request.headers.get("X-Org-Id", "")
        if header_org:
            try:
                int(header_org)
                return
            except (ValueError, TypeError):
                pass

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access to {resource_type} requires an organization context",
        )

    return dependency


def apply_org_filter(
    query: str,
    org_id: int | None,
    table_alias: str = "",
) -> str:
    """Inject an ``org_id = ?`` WHERE clause into a SQL query.

    If *org_id* is ``None`` the query is returned unchanged (admin bypass).
    If *table_alias* is provided (e.g. ``"t"``), the filter uses ``t.org_id``.
    """
    if org_id is None:
        return query

    prefix = f"{table_alias}." if table_alias else ""
    lower = query.lower().strip()

    filter_clause = f"{prefix}org_id = ?"

    if lower.startswith("select"):
        # Insert before ORDER BY / LIMIT
        insertion_point = len(query)
        for keyword in ("ORDER BY", "LIMIT", "OFFSET"):
            idx = query.upper().rfind(keyword)
            if idx != -1 and idx < insertion_point:
                insertion_point = idx
        has_where = "where" in lower.split("from")[-1] if "from" in lower else False
        clause = f" AND {filter_clause}" if has_where else f" WHERE {filter_clause}"
        query = query[:insertion_point] + clause + query[insertion_point:]
    else:
        query = f"{query} AND {filter_clause}" if "WHERE" in query else f"{query} WHERE {filter_clause}"

    return query


def get_user_org_filter(user: Any) -> tuple[str, int | None]:
    """Return a SQL fragment and org_id value for scoping queries.

    Returns ``("", None)`` for admins (no scoping).
    Returns ``("org_id = ?", org_id)`` for org-scoped users.
    """
    role = getattr(user, "role", "")
    if role in ("super_admin", "administrator"):
        return "", None

    org_id = getattr(user, "org_id", None)
    if org_id is not None:
        return "org_id = ?", org_id

    tenants = getattr(user, "tenants", None) or getattr(user, "user_tenants", None)
    if tenants and len(tenants) > 0:
        return "org_id = ?", tenants[0].org_id

    return "1=0", None  # No access
