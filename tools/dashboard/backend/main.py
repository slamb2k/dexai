"""
DexAI Dashboard Backend - FastAPI Application

This is the main entry point for the dashboard REST API.
It provides endpoints for monitoring, configuration, and real-time updates.

Usage:
    uvicorn tools.dashboard.backend.main:app --host 127.0.0.1 --port 8080 --reload

    Or run directly:
    python -m tools.dashboard.backend.main
"""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

# Load .env file before anything else
from dotenv import load_dotenv
load_dotenv()

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.dashboard.backend.database import get_db_connection, init_db
from tools.dashboard.backend.models import ErrorResponse, HealthCheck
from tools.dashboard.backend.routes import api_router
from tools.dashboard.backend.websocket import ws_router


# Configure structured logging
try:
    from tools.logging_config import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
logger = logging.getLogger(__name__)

# Configuration paths
CONFIG_PATH = PROJECT_ROOT / "args" / "dashboard.yaml"


def load_config() -> dict:
    """Load dashboard configuration from YAML."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


# Global config
config = load_config()
dashboard_config = config.get("dashboard", {})

# Track startup time for uptime calculation
startup_time: datetime | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    global startup_time

    # Startup
    logger.info("Starting DexAI Dashboard Backend...")
    startup_time = datetime.now()

    # Run database migrations
    try:
        from tools.ops.migrate import run_migrations
        result = run_migrations()
        if result["applied"]:
            logger.info(f"Migrations applied: {result['applied']}")
    except Exception as e:
        logger.warning(f"Migration runner unavailable: {e}")

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Start hook metrics periodic flush
    try:
        from tools.agent.hooks import start_metrics_flush_task
        start_metrics_flush_task(interval_seconds=60)
        logger.info("Hook metrics flush task started")
    except Exception as e:
        logger.debug(f"Hook metrics flush not started: {e}")

    # Initialize channel router and adapters
    adapters_started = []
    try:
        from tools.channels.router import get_router

        router = get_router()
        logger.info("Channel router initialized")

        # Register SDK message handler for processing messages with Claude
        # Uses streaming handler which routes to channel-specific implementations
        try:
            from tools.channels.sdk_handler import sdk_handler_with_streaming
            router.add_message_handler(sdk_handler_with_streaming)
            logger.info("SDK streaming message handler registered")
        except ImportError as e:
            logger.warning(f"SDK handler not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to register SDK handler: {e}")

        # Try to start configured channel adapters
        import os

        # Read from environment or .env file
        def get_env_var(name: str) -> str:
            value = os.environ.get(name, "")
            if not value:
                env_file = PROJECT_ROOT / ".env"
                if env_file.exists():
                    with open(env_file) as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                key, _, val = line.partition("=")
                                if key.strip() == name:
                                    return val.strip()
            return value

        # Register Telegram adapter if configured
        telegram_token = get_env_var("TELEGRAM_BOT_TOKEN")
        if telegram_token:
            try:
                from tools.channels.telegram_adapter import TelegramAdapter

                telegram_adapter = TelegramAdapter(telegram_token)
                router.register_adapter(telegram_adapter)
                await telegram_adapter.connect()
                logger.info("Telegram adapter registered and connected")
                adapters_started.append(("telegram", telegram_adapter))
            except Exception as e:
                logger.warning(f"Failed to register Telegram adapter: {e}")

        # Register Discord adapter if configured
        discord_token = get_env_var("DISCORD_BOT_TOKEN")
        if discord_token:
            try:
                from tools.channels.discord import DiscordAdapter

                discord_adapter = DiscordAdapter(discord_token)
                router.register_adapter(discord_adapter)
                await discord_adapter.connect()
                logger.info("Discord adapter registered and connected")
                adapters_started.append(("discord", discord_adapter))
            except Exception as e:
                logger.warning(f"Failed to register Discord adapter: {e}")

        # Store adapters in app state for access in routes
        app.state.channel_router = router
        app.state.adapters = {name: adapter for name, adapter in adapters_started}

    except ImportError as e:
        logger.warning(f"Channel router not available: {e}")
    except Exception as e:
        logger.error(f"Failed to initialize channel router: {e}")

    yield

    # Shutdown
    logger.info("Shutting down DexAI Dashboard Backend...")

    # Disconnect adapters
    for name, adapter in adapters_started:
        try:
            await adapter.disconnect()
            logger.info(f"{name} adapter disconnected")
        except Exception as e:
            logger.warning(f"Error disconnecting {name} adapter: {e}")


# Create FastAPI application
app = FastAPI(
    title="DexAI Dashboard API",
    description="REST API for DexAI monitoring and configuration",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
security_config = dashboard_config.get("security", {})
allowed_origins = security_config.get(
    "allowed_origins", ["http://localhost:3000", "http://127.0.0.1:3000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Authentication Middleware
# =============================================================================

# Routes that don't require authentication
PUBLIC_ROUTES = (
    "/api/health",
    "/api/auth/",
    "/api/setup/",
    "/api/status",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/ws/",
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Enforce authentication on non-public API routes."""
    path = request.url.path

    # Skip auth for non-API routes and public endpoints
    if not path.startswith("/api/") or any(path.startswith(r) for r in PUBLIC_ROUTES):
        return await call_next(request)

    # Skip auth if disabled in config
    require_auth = security_config.get("require_auth", True)
    if not require_auth:
        return await call_next(request)

    # Check for session token
    cookie_name = security_config.get("session_cookie_name", "dexai_session")
    token = request.cookies.get(cookie_name)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Authentication required", "code": "AUTH_REQUIRED"},
        )

    # Validate session
    try:
        from tools.security.session import validate_session

        result = validate_session(token, update_activity=True)
        if not result.get("valid"):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Session expired", "code": "SESSION_EXPIRED"},
            )
    except ImportError:
        # Session module not available — allow in dev
        logger.warning("Session module not available, skipping auth")
    except Exception as e:
        logger.error(f"Auth middleware error: {e}")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Authentication failed", "code": "AUTH_FAILED"},
        )

    return await call_next(request)


# =============================================================================
# Authentication Dependency (for route-level auth when needed)
# =============================================================================


async def get_current_user(request: Request) -> dict | None:
    """
    Validate session and return current user.

    Integrates with existing session management from tools/security/session.py
    """
    require_auth = security_config.get("require_auth", True)
    cookie_name = security_config.get("session_cookie_name", "dexai_session")

    if not require_auth:
        # Auth disabled - return mock user
        return {"user_id": "anonymous", "role": "user"}

    # Get session token from cookie or header
    token = request.cookies.get(cookie_name)
    if not token:
        # Try Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    # Validate session using existing session module
    try:
        from tools.security.session import validate_session

        result = validate_session(token, update_activity=True)

        if not result.get("valid"):
            reason = result.get("reason", "invalid_session")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Session invalid: {reason}"
            )

        return {
            "user_id": result.get("user_id"),
            "session_id": result.get("session_id"),
            "channel": result.get("channel"),
            "role": result.get("metadata", {}).get("role", "user"),
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
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session validation failed"
        )


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require admin or owner role."""
    admin_roles = security_config.get("admin_roles", ["admin", "owner"])
    if user.get("role") not in admin_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# =============================================================================
# Health Check Endpoint
# =============================================================================


@app.get("/api/health", response_model=HealthCheck, tags=["health"])
async def health_check():
    """
    Check system health status.

    Returns overall health and status of individual services including channels.
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

    # Check channel adapters
    channels = {}
    try:
        from tools.channels.router import get_router

        router = get_router()
        if router.adapters:
            # Get async status with health checks
            router_status = await router.get_status_async()
            channels = router_status.get("adapters", {})

            # Summarize channel health
            connected_count = sum(1 for c in channels.values() if c.get("connected"))
            total_count = len(channels)

            if total_count > 0:
                if connected_count == total_count:
                    services["channels"] = "healthy"
                elif connected_count > 0:
                    services["channels"] = "degraded"
                else:
                    services["channels"] = "unhealthy"
            else:
                services["channels"] = "no_adapters"
        else:
            services["channels"] = "no_adapters"
    except Exception as e:
        logger.warning(f"Channel health check failed: {e}")
        services["channels"] = "unavailable"

    # Overall status
    core_healthy = services.get("database") == "healthy"
    channels_ok = services.get("channels") in ("healthy", "degraded", "no_adapters", "unavailable")
    overall = "healthy" if core_healthy and channels_ok else "degraded"

    # Build extended response with channel details
    response = HealthCheck(
        status=overall,
        version="0.1.0",
        timestamp=datetime.now(),
        services=services
    )

    # Add channel details to response if available
    if channels:
        response.services["channel_details"] = channels

    return response


# =============================================================================
# Error Handlers
# =============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=exc.detail, code=f"HTTP_{exc.status_code}").model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(error="Internal server error", code="INTERNAL_ERROR").model_dump(),
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

    host = dashboard_config.get("host", "127.0.0.1")
    port = dashboard_config.get("api_port", 8080)

    uvicorn.run(
        "tools.dashboard.backend.main:app", host=host, port=port, reload=True, log_level="info"
    )
