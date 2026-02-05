"""
Service Management API Routes

Provides endpoints to view and control channel adapter services:
- List all services and their status
- Get individual service status
- Start/Stop/Restart services
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


router = APIRouter()


# =============================================================================
# Models
# =============================================================================


class ServiceStatus(BaseModel):
    """Status of a single service."""

    name: str
    display_name: str
    status: str  # 'running', 'stopped', 'error', 'unknown'
    connected: bool
    last_activity: str | None = None
    error: str | None = None
    config_status: str  # 'configured', 'unconfigured', 'partial'
    uptime_seconds: int | None = None


class ServiceAction(BaseModel):
    """Result of a service action."""

    success: bool
    service: str
    action: str
    message: str | None = None
    error: str | None = None


# =============================================================================
# Service Registry
# =============================================================================

# Define known services and their configuration requirements
SERVICE_DEFINITIONS = {
    "telegram": {
        "display_name": "Telegram",
        "config_vars": ["TELEGRAM_BOT_TOKEN"],
        "description": "Telegram bot adapter for messaging",
    },
    "discord": {
        "display_name": "Discord",
        "config_vars": ["DISCORD_BOT_TOKEN"],
        "description": "Discord bot adapter for server messaging",
    },
    "slack": {
        "display_name": "Slack",
        "config_vars": ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"],
        "description": "Slack bot adapter for workspace messaging",
    },
}


def check_service_config(service_name: str) -> str:
    """
    Check if a service has required configuration.

    Returns: 'configured', 'unconfigured', or 'partial'
    """
    definition = SERVICE_DEFINITIONS.get(service_name)
    if not definition:
        return "unknown"

    config_vars = definition.get("config_vars", [])
    if not config_vars:
        return "configured"

    configured_count = 0
    for var in config_vars:
        if os.getenv(var):
            configured_count += 1

    if configured_count == 0:
        return "unconfigured"
    elif configured_count == len(config_vars):
        return "configured"
    else:
        return "partial"


async def get_router_status() -> dict[str, Any]:
    """Get status from the message router."""
    try:
        from tools.channels.router import get_router

        router = get_router()
        return await router.get_status_async()
    except ImportError:
        return {"error": "Router module not available"}
    except Exception as e:
        return {"error": str(e)}


def get_router_sync() -> Any:
    """Get the router instance synchronously."""
    try:
        from tools.channels.router import get_router

        return get_router()
    except ImportError:
        return None


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/services", response_model=list[ServiceStatus])
async def list_services():
    """
    List all known services and their current status.

    Returns information about:
    - Telegram adapter
    - Discord adapter
    - Slack adapter
    """
    router_status = await get_router_status()
    adapter_statuses = router_status.get("adapters", {})
    start_time = router_status.get("start_time")

    services = []
    now = datetime.now()

    for name, definition in SERVICE_DEFINITIONS.items():
        adapter_info = adapter_statuses.get(name, {})
        config_status = check_service_config(name)

        # Determine status
        if "error" in adapter_info:
            status = "error"
            connected = False
            error = adapter_info["error"]
        elif adapter_info.get("connected", False):
            status = "running"
            connected = True
            error = None
        elif config_status == "unconfigured":
            status = "stopped"
            connected = False
            error = None
        elif name in adapter_statuses:
            status = "stopped"
            connected = False
            error = None
        else:
            status = "unknown"
            connected = False
            error = None

        # Calculate uptime if running
        uptime = None
        if status == "running" and start_time:
            try:
                start_dt = datetime.fromisoformat(start_time)
                uptime = int((now - start_dt).total_seconds())
            except (ValueError, TypeError):
                pass

        # Get last activity (would need to query database)
        last_activity = None
        try:
            from tools.dashboard.backend.database import get_events

            events = get_events(channel=name, limit=1)
            if events:
                last_activity = events[0].get("timestamp")
        except Exception:
            pass

        services.append(
            ServiceStatus(
                name=name,
                display_name=definition["display_name"],
                status=status,
                connected=connected,
                last_activity=last_activity,
                error=error,
                config_status=config_status,
                uptime_seconds=uptime,
            )
        )

    return services


@router.get("/services/{name}", response_model=ServiceStatus)
async def get_service_status(name: str):
    """
    Get detailed status for a specific service.
    """
    if name not in SERVICE_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")

    services = await list_services()
    for service in services:
        if service.name == name:
            return service

    raise HTTPException(status_code=404, detail=f"Service '{name}' status unavailable")


@router.post("/services/{name}/start", response_model=ServiceAction)
async def start_service(name: str):
    """
    Start a service adapter.

    Note: This connects the adapter to the platform. The adapter must be
    properly configured with tokens/credentials.
    """
    if name not in SERVICE_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")

    config_status = check_service_config(name)
    if config_status != "configured":
        return ServiceAction(
            success=False,
            service=name,
            action="start",
            error=f"Service not configured. Status: {config_status}. Check environment variables.",
        )

    try:
        router = get_router_sync()
        if not router:
            return ServiceAction(
                success=False,
                service=name,
                action="start",
                error="Router not available",
            )

        adapter = router.adapters.get(name)
        if not adapter:
            return ServiceAction(
                success=False,
                service=name,
                action="start",
                error="Adapter not registered. Restart the gateway to initialize adapters.",
            )

        # Connect adapter
        await adapter.connect()

        return ServiceAction(
            success=True,
            service=name,
            action="start",
            message=f"{SERVICE_DEFINITIONS[name]['display_name']} adapter started successfully",
        )

    except Exception as e:
        return ServiceAction(
            success=False,
            service=name,
            action="start",
            error=str(e),
        )


@router.post("/services/{name}/stop", response_model=ServiceAction)
async def stop_service(name: str):
    """
    Stop a service adapter.

    This disconnects the adapter from the platform but doesn't remove it
    from the router.
    """
    if name not in SERVICE_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")

    try:
        router = get_router_sync()
        if not router:
            return ServiceAction(
                success=False,
                service=name,
                action="stop",
                error="Router not available",
            )

        adapter = router.adapters.get(name)
        if not adapter:
            return ServiceAction(
                success=True,
                service=name,
                action="stop",
                message="Adapter not registered (already stopped)",
            )

        # Disconnect adapter
        await adapter.disconnect()

        return ServiceAction(
            success=True,
            service=name,
            action="stop",
            message=f"{SERVICE_DEFINITIONS[name]['display_name']} adapter stopped",
        )

    except Exception as e:
        return ServiceAction(
            success=False,
            service=name,
            action="stop",
            error=str(e),
        )


@router.post("/services/{name}/restart", response_model=ServiceAction)
async def restart_service(name: str):
    """
    Restart a service adapter.

    Disconnects and reconnects the adapter.
    """
    if name not in SERVICE_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")

    # Stop first
    stop_result = await stop_service(name)
    if not stop_result.success and "not registered" not in (stop_result.error or ""):
        return ServiceAction(
            success=False,
            service=name,
            action="restart",
            error=f"Failed to stop: {stop_result.error}",
        )

    # Brief pause
    await asyncio.sleep(0.5)

    # Start
    start_result = await start_service(name)
    if not start_result.success:
        return ServiceAction(
            success=False,
            service=name,
            action="restart",
            error=f"Failed to start: {start_result.error}",
        )

    return ServiceAction(
        success=True,
        service=name,
        action="restart",
        message=f"{SERVICE_DEFINITIONS[name]['display_name']} adapter restarted successfully",
    )


@router.get("/services/{name}/health")
async def check_service_health(name: str):
    """
    Run a health check on a specific service.

    Returns detailed health information including:
    - Connection status
    - API response time
    - Configuration validity
    """
    if name not in SERVICE_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")

    health = {
        "service": name,
        "timestamp": datetime.now().isoformat(),
        "checks": {},
    }

    # Check configuration
    config_status = check_service_config(name)
    health["checks"]["configuration"] = {
        "status": "pass" if config_status == "configured" else "fail",
        "detail": config_status,
    }

    # Check adapter registration
    router = get_router_sync()
    adapter = router.adapters.get(name) if router else None
    health["checks"]["registered"] = {
        "status": "pass" if adapter else "fail",
        "detail": "Adapter registered in router" if adapter else "Adapter not registered",
    }

    # Check connection/health
    if adapter and hasattr(adapter, "health_check"):
        try:
            adapter_health = await asyncio.wait_for(adapter.health_check(), timeout=5.0)
            health["checks"]["connection"] = {
                "status": "pass" if adapter_health.get("connected") else "fail",
                "detail": adapter_health,
            }
        except asyncio.TimeoutError:
            health["checks"]["connection"] = {
                "status": "fail",
                "detail": "Health check timed out",
            }
        except Exception as e:
            health["checks"]["connection"] = {
                "status": "fail",
                "detail": str(e),
            }
    elif adapter:
        health["checks"]["connection"] = {
            "status": "unknown",
            "detail": "Adapter does not implement health_check",
        }
    else:
        health["checks"]["connection"] = {
            "status": "skip",
            "detail": "Adapter not available",
        }

    # Overall status
    statuses = [c["status"] for c in health["checks"].values()]
    if all(s == "pass" for s in statuses):
        health["overall"] = "healthy"
    elif any(s == "fail" for s in statuses):
        health["overall"] = "unhealthy"
    else:
        health["overall"] = "degraded"

    return health
