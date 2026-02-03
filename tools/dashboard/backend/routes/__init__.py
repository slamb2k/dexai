"""Dashboard API Routes Package

This module aggregates all route handlers into a single router
that can be included in the main FastAPI application.
"""

from fastapi import APIRouter

from .activity import router as activity_router
from .metrics import router as metrics_router
from .settings import router as settings_router
from .setup import router as setup_router
from .status import router as status_router
from .tasks import router as tasks_router


# Create main API router
api_router = APIRouter(prefix="/api")

# Include all sub-routers
api_router.include_router(status_router, tags=["status"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
api_router.include_router(activity_router, prefix="/activity", tags=["activity"])
api_router.include_router(metrics_router, prefix="/metrics", tags=["metrics"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(setup_router, prefix="/setup", tags=["setup"])

__all__ = ["api_router"]
