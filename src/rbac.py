"""Role-based access control — permission definitions, role mapping, and FastAPI guards."""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Sequence

from fastapi import Depends, HTTPException, Request, status

_logger = logging.getLogger(__name__)

# ======================================================================
# Permission constants
# ======================================================================

# Incident management
INCIDENT_READ = "incident:read"
INCIDENT_WRITE = "incident:write"
INCIDENT_ACK = "incident:acknowledge"
INCIDENT_RESOLVE = "incident:resolve"
INCIDENT_DELETE = "incident:delete"

# Monitoring targets
MONITORING_READ = "monitoring:read"
MONITORING_WRITE = "monitoring:write"
MONITORING_DELETE = "monitoring:delete"

# API Keys
APIKEY_READ = "apikey:read"
APIKEY_WRITE = "apikey:write"
APIKEY_DELETE = "apikey:delete"

# Users & Roles
USER_READ = "user:read"
USER_WRITE = "user:write"
USER_ADMIN = "user:admin"

# Sessions
SESSION_READ = "session:read"
SESSION_REVOKE = "session:revoke"

# Organizations (multi-tenant)
ORG_READ = "org:read"
ORG_WRITE = "org:write"
ORG_ADMIN = "org:admin"

# Settings & Audit
SETTINGS_READ = "settings:read"
SETTINGS_WRITE = "settings:write"
AUDIT_READ = "audit:read"

# AI / Intelligence
AI_CHAT = "ai:chat"
AI_PLAN = "ai:plan"
AI_EXECUTE = "ai:execute"

# Notifications
NOTIFICATION_READ = "notification:read"
NOTIFICATION_WRITE = "notification:write"

# All permissions constant (for super_admin)
ALL_PERMISSIONS = "*"

# ======================================================================
# Role → permission mapping
# ======================================================================

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "super_admin": {ALL_PERMISSIONS},
    "administrator": {
        INCIDENT_READ, INCIDENT_WRITE, INCIDENT_ACK, INCIDENT_RESOLVE, INCIDENT_DELETE,
        MONITORING_READ, MONITORING_WRITE, MONITORING_DELETE,
        APIKEY_READ, APIKEY_WRITE, APIKEY_DELETE,
        USER_READ, USER_WRITE, USER_ADMIN,
        SESSION_READ, SESSION_REVOKE,
        ORG_READ, ORG_WRITE, ORG_ADMIN,
        SETTINGS_READ, SETTINGS_WRITE,
        AUDIT_READ,
        AI_CHAT, AI_PLAN, AI_EXECUTE,
        NOTIFICATION_READ, NOTIFICATION_WRITE,
    },
    "soc_analyst": {
        INCIDENT_READ, INCIDENT_WRITE, INCIDENT_ACK, INCIDENT_RESOLVE,
        MONITORING_READ,
        USER_READ,
        SESSION_READ,
        AI_CHAT, AI_PLAN,
        NOTIFICATION_READ,
    },
    "operator": {
        INCIDENT_READ, INCIDENT_ACK,
        MONITORING_READ,
        AI_CHAT,
        NOTIFICATION_READ,
    },
    "read_only": {
        INCIDENT_READ,
        MONITORING_READ,
        USER_READ,
        NOTIFICATION_READ,
        SETTINGS_READ,
    },
    "auditor": {
        INCIDENT_READ,
        MONITORING_READ,
        USER_READ,
        SESSION_READ,
        AUDIT_READ,
        SETTINGS_READ,
        NOTIFICATION_READ,
    },
}

# ======================================================================
# Helpers
# ======================================================================


def permissions_for_role(role: str) -> set[str]:
    """Return the set of permissions granted to a given role string."""
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS.get("read_only", set()))


def has_permission(user_role: str, required_permission: str) -> bool:
    """Check whether *required_permission* is in the user's role permissions."""
    perms = permissions_for_role(user_role)
    return ALL_PERMISSIONS in perms or required_permission in perms


def has_any_permission(user_role: str, *required: str) -> bool:
    """Check whether the user has *any* of the listed permissions."""
    perms = permissions_for_role(user_role)
    if ALL_PERMISSIONS in perms:
        return True
    return any(p in perms for p in required)


def has_all_permissions(user_role: str, *required: str) -> bool:
    """Check whether the user has *all* of the listed permissions."""
    perms = permissions_for_role(user_role)
    if ALL_PERMISSIONS in perms:
        return True
    return all(p in perms for p in required)


# ======================================================================
# FastAPI dependencies
# ======================================================================


async def get_current_user(request: Request) -> Any:
    """Extract the authenticated user from the request state.

    Requires that a previous middleware (or the route handler) has set
    ``request.state.user``.  Returns the user object or raises 401.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


class RequirePermission:
    """FastAPI dependency — verifies the authenticated user has a permission.

    Usage::

        @router.get("/incidents")
        async def list_incidents(
            request: Request,
            _=Depends(RequirePermission("incident:read")),
        ):
            ...

    Attach to a route as a :class:`Depends`.  The dependency reads
    ``request.state.user``, which must be set by prior middleware.
    """

    def __init__(self, permission: str) -> None:
        self.permission = permission

    async def __call__(self, request: Request) -> None:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        role = getattr(user, "role", "")
        if not has_permission(role, self.permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {self.permission}",
            )


class RequireRole:
    """FastAPI dependency — verifies the user has at least a minimum role level.

    Usage::

        @router.delete("/users/{user_id}")
        async def delete_user(
            request: Request,
            _=Depends(RequireRole("administrator")),
        ):
            ...
    """

    def __init__(self, min_role: str) -> None:
        from src.auth import Role
        self.min_level = Role.from_str(min_role).level()

    async def __call__(self, request: Request) -> None:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        from src.auth import Role
        user_role = getattr(user, "role", "")
        if Role.from_str(user_role).level() < self.min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role level",
            )


Perm = RequirePermission  # shorthand alias
