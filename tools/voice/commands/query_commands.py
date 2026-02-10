"""Query voice command handlers.

Handles questions about tasks, schedule, status, and search.
"""

from __future__ import annotations

import logging

from tools.voice.models import (
    CommandResult,
    EntityType,
    ParsedCommand,
)

logger = logging.getLogger(__name__)


async def handle_query_next_task(command: ParsedCommand, user_id: str) -> CommandResult:
    """Return the next task based on current energy."""
    from tools.tasks.current_step import get_current_step

    energy_entity = command.get_entity(EntityType.ENERGY_LEVEL)
    energy = energy_entity.value if energy_entity else None

    result = get_current_step(user_id=user_id, energy_level=energy)

    if result.get("success") and result.get("data"):
        data = result["data"]
        formatted = data.get("formatted", data.get("title", "No task found"))
        return CommandResult(
            success=True,
            message=formatted,
            data=data,
        )

    return CommandResult(
        success=True,
        message="No tasks right now. You're all caught up!",
        data={},
    )


async def handle_query_schedule(command: ParsedCommand, user_id: str) -> CommandResult:
    """Return today's schedule."""
    from tools.tasks.manager import list_tasks

    result = list_tasks(user_id=user_id, status="in_progress")
    in_progress = result.get("data", {}).get("tasks", []) if result.get("success") else []

    pending_result = list_tasks(user_id=user_id, status="pending")
    pending = pending_result.get("data", {}).get("tasks", []) if pending_result.get("success") else []

    total = len(in_progress) + len(pending)
    if total == 0:
        return CommandResult(
            success=True,
            message="Your schedule is clear! No tasks pending.",
            data={"in_progress": 0, "pending": 0},
        )

    lines = []
    if in_progress:
        lines.append(f"{len(in_progress)} in progress")
    if pending:
        lines.append(f"{len(pending)} pending")

    summary = ", ".join(lines)
    message = f"You have {summary}."

    # Add the current task
    if in_progress:
        current_title = in_progress[0].get("title", in_progress[0].get("raw_input", ""))
        message += f" Currently working on: {current_title}"

    return CommandResult(
        success=True,
        message=message,
        data={
            "in_progress": len(in_progress),
            "pending": len(pending),
            "total": total,
        },
    )


async def handle_query_status(command: ParsedCommand, user_id: str) -> CommandResult:
    """Return a progress summary."""
    from tools.tasks.manager import list_tasks

    completed = list_tasks(user_id=user_id, status="completed")
    completed_count = len(completed.get("data", {}).get("tasks", [])) if completed.get("success") else 0

    pending = list_tasks(user_id=user_id, status="pending")
    pending_count = len(pending.get("data", {}).get("tasks", [])) if pending.get("success") else 0

    in_progress = list_tasks(user_id=user_id, status="in_progress")
    in_progress_count = len(in_progress.get("data", {}).get("tasks", [])) if in_progress.get("success") else 0

    total = completed_count + pending_count + in_progress_count
    if total == 0:
        return CommandResult(
            success=True,
            message="No tasks tracked yet. Say 'add task' to get started!",
        )

    message = f"You've completed {completed_count} tasks"
    if pending_count > 0:
        message += f", with {pending_count} still to go"
    if in_progress_count > 0:
        message += f" and {in_progress_count} in progress"
    message += "."

    if completed_count > 0 and total > 0:
        pct = int((completed_count / total) * 100)
        message += f" That's {pct}% done!"

    return CommandResult(
        success=True,
        message=message,
        data={
            "completed": completed_count,
            "pending": pending_count,
            "in_progress": in_progress_count,
            "total": total,
        },
    )


async def handle_query_search(command: ParsedCommand, user_id: str) -> CommandResult:
    """Search tasks and memory."""
    search_entity = command.get_entity(EntityType.SEARCH_QUERY)
    query = search_entity.value if search_entity else command.raw_transcript

    if not query or len(query.strip()) < 2:
        return CommandResult(
            success=False,
            message='What would you like to search for? Try: "Search for groceries"',
            follow_up_prompt="What should I search for?",
        )

    # Search tasks
    from tools.tasks.manager import list_tasks
    results = list_tasks(user_id=user_id)
    tasks = results.get("data", {}).get("tasks", []) if results.get("success") else []

    # Simple keyword filter
    query_lower = query.lower()
    matches = [
        t for t in tasks
        if query_lower in (t.get("title", "") or "").lower()
        or query_lower in (t.get("raw_input", "") or "").lower()
        or query_lower in (t.get("description", "") or "").lower()
    ]

    if matches:
        count = len(matches)
        first = matches[0].get("title", matches[0].get("raw_input", ""))
        message = f"Found {count} task{'s' if count > 1 else ''} matching \"{query}\". First: {first}"
        return CommandResult(
            success=True,
            message=message,
            data={"matches": count, "query": query},
        )

    return CommandResult(
        success=True,
        message=f"No tasks found matching \"{query}\".",
        data={"matches": 0, "query": query},
    )
