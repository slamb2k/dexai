"""Dashboard API Routes Package

This module aggregates all route handlers into a single router
that can be included in the main FastAPI application.
"""

from fastapi import APIRouter

from .actions import router as actions_router
from .activity import router as activity_router
from .metrics import router as metrics_router
from .oauth import router as oauth_router
from .office import router as office_router
from .policies import router as policies_router
from .push import router as push_router
from .services import router as services_router
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
api_router.include_router(office_router, prefix="/office", tags=["office"])
api_router.include_router(oauth_router, prefix="/oauth", tags=["oauth"])
api_router.include_router(actions_router, tags=["actions"])
api_router.include_router(policies_router, tags=["policies"])
api_router.include_router(push_router, prefix="/push", tags=["push"])
api_router.include_router(services_router, tags=["services"])

__all__ = ["api_router"]
