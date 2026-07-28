"""Monitoring routes for containers, incidents, and metrics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from src.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["monitoring"])

VIEWER_ROLES = ("super_admin", "administrator", "soc_analyst", "operator", "read_only", "auditor")
OPERATOR_ROLES = ("super_admin", "administrator", "soc_analyst", "operator")


def _require_role(request: Request, *roles: str) -> None:
    """Check if user has required role."""
    from src.dashboard import require_auth
    auth_manager = request.app.state.auth_manager
    user = require_auth(request, auth_manager)
    if not user.has_role(*roles):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail=f"Role '{user.role}' not permitted. Required: {', '.join(roles)}",
        )


@router.get("/api/containers")
async def api_containers(request: Request) -> Any:
    """List all Docker containers."""
    _require_role(request, *VIEWER_ROLES)
    scanner = request.app.state.services.docker_scanner
    try:
        containers = scanner.list_containers()
        return {"containers": containers, "count": len(containers)}
    except Exception as exc:
        logger.error("Failed to list containers: %s", exc)
        return {"containers": [], "count": 0, "error": str(exc)}


@router.get("/api/incidents")
async def api_incidents(request: Request) -> Any:
    """List all incidents."""
    _require_role(request, *VIEWER_ROLES)
    incident_manager = request.app.state.services.incident_manager
    try:
        incidents = incident_manager.list_incidents()
        return {"incidents": incidents, "count": len(incidents)}
    except Exception as exc:
        logger.error("Failed to list incidents: %s", exc)
        return {"incidents": [], "count": 0, "error": str(exc)}


@router.get("/api/incidents/{incident_id}")
async def api_incident_detail(incident_id: str, request: Request) -> Any:
    """Get incident details."""
    _require_role(request, *VIEWER_ROLES)
    incident_manager = request.app.state.services.incident_manager
    try:
        incident = incident_manager.get_incident(incident_id)
        if incident is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Incident not found")
        return incident.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get incident %s: %s", incident_id, exc)
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/incidents/{incident_id}/acknowledge")
async def api_acknowledge_incident(incident_id: str, request: Request) -> Any:
    """Acknowledge an incident."""
    _require_role(request, *OPERATOR_ROLES)
    incident_manager = request.app.state.services.incident_manager
    try:
        incident = incident_manager.acknowledge_incident(incident_id)
        if incident is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Incident not found")
        return incident.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to acknowledge incident %s: %s", incident_id, exc)
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/metrics")
async def api_metrics(request: Request) -> Any:
    """Get system metrics."""
    _require_role(request, *VIEWER_ROLES)
    monitor = request.app.state.services.monitor
    try:
        return monitor.get_current_metrics()
    except Exception as exc:
        logger.error("Failed to get metrics: %s", exc)
        return {"error": str(exc)}


@router.get("/api/system-health")
async def api_system_health(request: Request) -> Any:
    """Get system health status."""
    _require_role(request, *VIEWER_ROLES)
    try:
        import psutil
        health = {
            "status": "healthy",
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "uptime_seconds": None,
        }
        try:
            import time
            health["uptime_seconds"] = int(time.time() - psutil.boot_time())
        except Exception:
            pass
        return health
    except Exception as exc:
        logger.error("Failed to get system health: %s", exc)
        return {"status": "error", "error": str(exc)}


@router.get("/api/notifications")
async def api_notifications(request: Request) -> Any:
    """Get notification history."""
    _require_role(request, *VIEWER_ROLES)
    repo = getattr(request.app.state.services, "platform_repository", None)
    if repo is None:
        return {"notifications": [], "count": 0}
    try:
        notifications = repo.get_notification_history(limit=50)
        return {"notifications": notifications, "count": len(notifications)}
    except Exception as exc:
        logger.error("Failed to get notifications: %s", exc)
        return {"notifications": [], "count": 0, "error": str(exc)}


@router.get("/api/remediations")
async def api_remediations(request: Request) -> Any:
    """Get remediation history."""
    _require_role(request, *VIEWER_ROLES)
    repo = getattr(request.app.state.services, "platform_repository", None)
    if repo is None:
        return {"remediations": [], "count": 0}
    try:
        remediations = repo.get_remediation_history(limit=50)
        return {"remediations": remediations, "count": len(remediations)}
    except Exception as exc:
        logger.error("Failed to get remediations: %s", exc)
        return {"remediations": [], "count": 0, "error": str(exc)}
