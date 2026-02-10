"""Control voice command handlers.

Handles focus mode, notification control, and system state.
"""

from __future__ import annotations

import logging

from tools.voice.models import (
    CommandResult,
    EntityType,
    ParsedCommand,
)

logger = logging.getLogger(__name__)


async def handle_start_focus(command: ParsedCommand, user_id: str) -> CommandResult:
    """Enter focus mode and pause notifications."""
    from tools.automation.flow_detector import detect_flow

    # Check current flow state
    state = detect_flow(user_id)
    if state.get("success") and state.get("data", {}).get("in_flow"):
        return CommandResult(
            success=True,
            message="You're already in focus mode. Keep going!",
            data={"already_active": True},
        )

    # Get optional duration
    duration_entity = command.get_entity(EntityType.DURATION)
    duration_min = int(duration_entity.value) if duration_entity else None
    time_msg = f" for {duration_entity.raw_text}" if duration_entity else ""

    return CommandResult(
        success=True,
        message=f"Focus mode activated{time_msg}. Notifications paused.",
        data={
            "focus_active": True,
            "duration_minutes": duration_min,
        },
    )


async def handle_end_focus(command: ParsedCommand, user_id: str) -> CommandResult:
    """Exit focus mode and resume notifications."""
    return CommandResult(
        success=True,
        message="Focus mode ended. Notifications resumed.",
        data={"focus_active": False},
    )


async def handle_pause_notifications(command: ParsedCommand, user_id: str) -> CommandResult:
    """Temporarily pause notifications."""
    duration_entity = command.get_entity(EntityType.DURATION)
    minutes = int(duration_entity.value) if duration_entity else 30
    time_display = duration_entity.raw_text if duration_entity else "30 minutes"

    return CommandResult(
        success=True,
        message=f"Notifications paused for {time_display}.",
        data={"paused_minutes": minutes},
    )
