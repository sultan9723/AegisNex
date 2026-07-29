"""Router modules for AegisNex dashboard."""

from src.routers.auth import router as auth_router
from src.routers.monitoring import router as monitoring_router

__all__ = ["auth_router", "monitoring_router"]
