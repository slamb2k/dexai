"""Task-related voice command handlers.

Connects voice intents to the task engine (tools/tasks/).
"""

from __future__ import annotations

import logging
from typing import Any

from tools.voice.models import (
    CommandResult,
    EntityType,
    IntentType,
    ParsedCommand,
)

logger = logging.getLogger(__name__)


async def handle_add_task(command: ParsedCommand, user_id: str) -> CommandResult:
    """Create a new task from voice input."""
    from tools.tasks.manager import create_task

    # Get task description from entities or raw transcript
    desc_entity = command.get_entity(EntityType.TASK_DESCRIPTION)
    description = desc_entity.value if desc_entity else command.raw_transcript

    if not description or len(description.strip()) < 2:
        return CommandResult(
            success=False,
            message='What task would you like to add? Try: "Add task: buy groceries"',
            follow_up_prompt="What's the task?",
        )

    # Extract optional priority and energy
    priority_entity = command.get_entity(EntityType.PRIORITY)
    energy_entity = command.get_entity(EntityType.ENERGY_LEVEL)

    priority = {"high": 8, "medium": 5, "low": 3}.get(
        priority_entity.value if priority_entity else "", 5
    )
    energy = energy_entity.value if energy_entity else None

    result = create_task(
        user_id=user_id,
        raw_input=description,
        title=description,
        energy_level=energy,
        priority=priority,
    )

    if result.get("success"):
        task_data = result.get("data", {})
        return CommandResult(
            success=True,
            message=f"Got it! Task added: {description}",
            data={"task_id": task_data.get("task_id")},
            undo_available=True,
        )

    return CommandResult(
        success=False,
        message="Couldn't add that task. Try again?",
        error=result.get("error", "unknown"),
    )


async def handle_complete_task(command: ParsedCommand, user_id: str) -> CommandResult:
    """Mark the current task as complete."""
    from tools.tasks.current_step import get_current_step
    from tools.tasks.manager import complete_task

    # Find current task
    current = get_current_step(user_id=user_id)
    if not current.get("success") or not current.get("data"):
        return CommandResult(
            success=False,
            message="No active task to complete. You're all caught up!",
        )

    task_id = current["data"].get("task_id")
    if not task_id:
        return CommandResult(
            success=False,
            message="No active task to complete.",
        )

    result = complete_task(task_id)
    if result.get("success"):
        title = current["data"].get("title", "task")
        return CommandResult(
            success=True,
            message=f"Nice! Completed: {title}",
            data={"task_id": task_id},
            undo_available=True,
        )

    return CommandResult(
        success=False,
        message="Couldn't mark that done. Try again?",
        error=result.get("error"),
    )


async def handle_skip_task(command: ParsedCommand, user_id: str) -> CommandResult:
    """Skip the current task and move to the next one."""
    from tools.tasks.current_step import get_current_step
    from tools.tasks.manager import update_task

    current = get_current_step(user_id=user_id)
    if not current.get("success") or not current.get("data"):
        return CommandResult(
            success=False,
            message="No active task to skip.",
        )

    task_id = current["data"].get("task_id")
    if task_id:
        # Move back to pending so another task comes up
        update_task(task_id, status="pending")

    # Get the next task
    next_step = get_current_step(user_id=user_id)
    if next_step.get("success") and next_step.get("data"):
        next_title = next_step["data"].get("formatted", "Next task ready")
        return CommandResult(
            success=True,
            message=f"Skipped. Next up: {next_title}",
            data={"task_id": next_step["data"].get("task_id")},
        )

    return CommandResult(
        success=True,
        message="Skipped. No more tasks right now!",
    )


async def handle_decompose_task(command: ParsedCommand, user_id: str) -> CommandResult:
    """Break down the current task into smaller steps."""
    from tools.tasks.current_step import get_current_step
    from tools.tasks.decompose import decompose_task

    current = get_current_step(user_id=user_id)
    if not current.get("success") or not current.get("data"):
        return CommandResult(
            success=False,
            message="No active task to break down.",
        )

    task_id = current["data"].get("task_id")
    if not task_id:
        return CommandResult(
            success=False,
            message="No active task to break down.",
        )

    result = decompose_task(task_id)
    if result.get("success"):
        steps = result.get("data", {}).get("steps", [])
        step_count = len(steps)
        first_step = steps[0].get("instruction", "Get started") if steps else "Get started"
        return CommandResult(
            success=True,
            message=f"Broken down into {step_count} steps. First: {first_step}",
            data={"task_id": task_id, "step_count": step_count},
        )

    return CommandResult(
        success=False,
        message="Couldn't break that down. Try adding more detail?",
        error=result.get("error"),
    )
