"""
DexAI Dashboard Backend - FastAPI Application

This is the main entry point for the dashboard REST API.
It provides endpoints for monitoring, configuration, and real-time updates.

Usage:
    uvicorn tools.dashboard.backend.main:app --host 127.0.0.1 --port 8080 --reload

    Or run directly:
    python -m tools.dashboard.backend.main
"""

import sys
import yaml
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.dashboard.backend.models import ErrorResponse, HealthCheck
from tools.dashboard.backend.routes import api_router
from tools.dashboard.backend.websocket import ws_router
from tools.dashboard.backend.database import init_db, get_db_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration paths
CONFIG_PATH = PROJECT_ROOT / 'args' / 'dashboard.yaml'


def load_config() -> dict:
    """Load dashboard configuration from YAML."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


# Global config
config = load_config()
dashboard_config = config.get('dashboard', {})

# Track startup time for uptime calculation
startup_time: Optional[datetime] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    global startup_time

    # Startup
    logger.info("Starting DexAI Dashboard Backend...")
    startup_time = datetime.now()

    # Initialize database
    init_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down DexAI Dashboard Backend...")


# Create FastAPI application
app = FastAPI(
    title="DexAI Dashboard API",
    description="REST API for DexAI monitoring and configuration",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Configure CORS
security_config = dashboard_config.get('security', {})
allowed_origins = security_config.get('allowed_origins', [
    "http://localhost:3000",
    "http://127.0.0.1:3000"
])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Authentication Dependency
# =============================================================================

async def get_current_user(request: Request) -> Optional[dict]:
    """
    Validate session and return current user.

    Integrates with existing session management from tools/security/session.py
    """
    require_auth = security_config.get('require_auth', True)
    cookie_name = security_config.get('session_cookie_name', 'dexai_session')

    if not require_auth:
        # Auth disabled - return mock user
        return {"user_id": "anonymous", "role": "user"}

    # Get session token from cookie or header
    token = request.cookies.get(cookie_name)
    if not token:
        # Try Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    # Validate session using existing session module
    try:
        from tools.security.session import validate_session
        result = validate_session(token, update_activity=True)

        if not result.get('valid'):
            reason = result.get('reason', 'invalid_session')
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Session invalid: {reason}"
            )

        return {
            "user_id": result.get('user_id'),
            "session_id": result.get('session_id'),
            "channel": result.get('channel'),
            "role": result.get('metadata', {}).get('role', 'user')
        }
    except ImportError:
        # Session module not available - allow anonymous access in dev
        logger.warning("Session module not available, allowing anonymous access")
        return {"user_id": "anonymous", "role": "user"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session validation failed"
        )


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require admin or owner role."""
    admin_roles = security_config.get('admin_roles', ['admin', 'owner'])
    if user.get('role') not in admin_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


# =============================================================================
# Health Check Endpoint
# =============================================================================

@app.get("/api/health", response_model=HealthCheck, tags=["health"])
async def health_check():
    """
    Check system health status.

    Returns overall health and status of individual services.
    """
    services = {}

    # Check database
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        services["database"] = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        services["database"] = "unhealthy"

    # Check session database
    try:
        from tools.security.session import get_connection as get_session_db
        conn = get_session_db()
        conn.execute("SELECT 1")
        conn.close()
        services["sessions"] = "healthy"
    except Exception:
        services["sessions"] = "unavailable"

    # Check memory database
    try:
        from tools.memory.memory_db import get_connection as get_memory_db
        conn = get_memory_db()
        conn.execute("SELECT 1")
        conn.close()
        services["memory"] = "healthy"
    except Exception:
        services["memory"] = "unavailable"

    # Overall status
    overall = "healthy" if services.get("database") == "healthy" else "degraded"

    return HealthCheck(
        status=overall,
        version="0.1.0",
        timestamp=datetime.now(),
        services=services
    )


# =============================================================================
# Error Handlers
# =============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            code=f"HTTP_{exc.status_code}"
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            code="INTERNAL_ERROR"
        ).model_dump()
    )


# =============================================================================
# Include Routers
# =============================================================================

# REST API routes
app.include_router(api_router)

# WebSocket routes
app.include_router(ws_router)


# =============================================================================
# Utility Functions
# =============================================================================

def get_uptime_seconds() -> int:
    """Get server uptime in seconds."""
    if startup_time is None:
        return 0
    delta = datetime.now() - startup_time
    return int(delta.total_seconds())


# Export for use in routes
app.state.get_uptime = get_uptime_seconds
app.state.config = dashboard_config


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    host = dashboard_config.get('host', '127.0.0.1')
    port = dashboard_config.get('api_port', 8080)

    uvicorn.run(
        "tools.dashboard.backend.main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
