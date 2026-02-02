"""
Status Route - Current Dex State for Avatar Display

Provides the current state of Dex for the avatar component:
- Current avatar state (idle, listening, thinking, working, etc.)
- Current task description (if any)
- System uptime
- Version information
"""

from datetime import datetime

from fastapi import APIRouter, Request

from tools.dashboard.backend.database import get_dex_state, set_dex_state
from tools.dashboard.backend.models import AvatarState, DexStatus


router = APIRouter()


@router.get("/status", response_model=DexStatus)
async def get_status(request: Request):
    """
    Get current Dex state for avatar display.

    Returns:
        DexStatus with current avatar state, task, uptime, and version.
    """
    # Get state from database
    state_data = get_dex_state()

    # Get uptime from app state
    get_uptime = getattr(request.app.state, "get_uptime", lambda: 0)
    uptime = get_uptime()

    # Parse last activity time
    last_activity = None
    if state_data.get("updated_at"):
        try:
            last_activity = datetime.fromisoformat(state_data["updated_at"])
        except (ValueError, TypeError):
            pass

    # Map state string to enum
    state_str = state_data.get("state", "idle")
    try:
        avatar_state = AvatarState(state_str)
    except ValueError:
        avatar_state = AvatarState.IDLE

    return DexStatus(
        state=avatar_state,
        current_task=state_data.get("current_task"),
        uptime_seconds=uptime,
        version="0.1.0",
        last_activity=last_activity,
    )


@router.put("/status", response_model=DexStatus)
async def update_status(
    state: AvatarState, current_task: str | None = None, request: Request = None
):
    """
    Update Dex avatar state.

    This endpoint is called by internal systems when Dex state changes.
    It also triggers a WebSocket broadcast to connected clients.

    Args:
        state: New avatar state
        current_task: Optional task description
    """
    # Update in database
    state_data = set_dex_state(state.value, current_task)

    # Get uptime
    get_uptime = getattr(request.app.state, "get_uptime", lambda: 0)
    uptime = get_uptime()

    # Parse last activity time
    last_activity = None
    if state_data.get("updated_at"):
        try:
            last_activity = datetime.fromisoformat(state_data["updated_at"])
        except (ValueError, TypeError):
            pass

    # Trigger WebSocket broadcast
    try:
        from tools.dashboard.backend.websocket import broadcast_state_change

        await broadcast_state_change(state.value, current_task)
    except Exception:
        pass  # WebSocket broadcast is best-effort

    return DexStatus(
        state=state,
        current_task=current_task,
        uptime_seconds=uptime,
        version="0.1.0",
        last_activity=last_activity,
    )
