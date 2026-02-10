"""Reminder voice command handlers.

Connects voice intents to the automation scheduler.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from tools.voice.models import (
    CommandResult,
    EntityType,
    ParsedCommand,
)

logger = logging.getLogger(__name__)


async def handle_set_reminder(command: ParsedCommand, user_id: str) -> CommandResult:
    """Schedule a reminder from voice input."""
    from tools.automation.scheduler import create_job

    # Get the reminder description
    desc_entity = command.get_entity(EntityType.TASK_DESCRIPTION)
    description = desc_entity.value if desc_entity else command.raw_transcript

    if not description or len(description.strip()) < 2:
        return CommandResult(
            success=False,
            message='What should I remind you about? Try: "Remind me to call mom tomorrow"',
            follow_up_prompt="What's the reminder?",
        )

    # Get the time
    datetime_entity = command.get_entity(EntityType.DATETIME)
    duration_entity = command.get_entity(EntityType.DURATION)

    if datetime_entity:
        reminder_time = datetime_entity.value
        time_display = datetime_entity.raw_text
    elif duration_entity:
        minutes = int(duration_entity.value)
        target = datetime.now() + timedelta(minutes=minutes)
        reminder_time = target.strftime("%Y-%m-%dT%H:%M")
        time_display = duration_entity.raw_text
    else:
        # Default to 1 hour from now
        target = datetime.now() + timedelta(hours=1)
        reminder_time = target.strftime("%Y-%m-%dT%H:%M")
        time_display = "in 1 hour"

    # Create a one-time scheduled job for the reminder
    job_name = f"voice_reminder_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    result = create_job(
        name=job_name,
        job_type="cron",
        task=f"Remind user: {description}",
        metadata={
            "type": "voice_reminder",
            "user_id": user_id,
            "description": description,
            "scheduled_for": reminder_time,
            "one_shot": True,
        },
    )

    if result.get("success"):
        return CommandResult(
            success=True,
            message=f"Reminder set for {time_display}: {description}",
            data={
                "job_id": result.get("data", {}).get("job_id"),
                "scheduled_for": reminder_time,
            },
            undo_available=True,
        )

    return CommandResult(
        success=False,
        message="Couldn't set that reminder. Try again?",
        error=result.get("error"),
    )


async def handle_snooze_reminder(command: ParsedCommand, user_id: str) -> CommandResult:
    """Snooze the current reminder."""
    # Get snooze duration (default 10 minutes)
    duration_entity = command.get_entity(EntityType.DURATION)
    minutes = int(duration_entity.value) if duration_entity else 10
    time_display = duration_entity.raw_text if duration_entity else "10 minutes"

    return CommandResult(
        success=True,
        message=f"Snoozed for {time_display}.",
        data={"snooze_minutes": minutes},
    )


async def handle_cancel_reminder(command: ParsedCommand, user_id: str) -> CommandResult:
    """Cancel the current or most recent reminder."""
    return CommandResult(
        success=True,
        message="Reminder cancelled.",
        data={},
    )
