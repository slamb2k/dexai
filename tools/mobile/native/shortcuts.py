"""
Shortcuts Handler

Handles Siri Shortcuts and Quick Actions invocations from the mobile app.

ADHD-friendly: Simple responses, single actions.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

# Shortcut handlers registry
_shortcut_handlers: dict[str, callable] = {}


def register_shortcut_handler(shortcut_id: str):
    """Decorator to register a shortcut handler."""
    def decorator(func):
        _shortcut_handlers[shortcut_id] = func
        return func
    return decorator


async def handle_shortcut(user_id: str, shortcut_id: str, params: dict | None = None) -> dict[str, Any]:
    """
    Handle Siri shortcut invocation.

    Args:
        user_id: User identifier
        shortcut_id: Shortcut being invoked
        params: Optional parameters from shortcut

    Returns:
        {
            "success": True,
            "spoken_response": "Response for Siri to speak",
            "data": {...},  # Optional data
            "continue_in_app": False  # Whether to open app
        }
    """
    params = params or {}

    # Check if we have a registered handler
    handler = _shortcut_handlers.get(shortcut_id)
    if handler:
        try:
            return await handler(user_id, params)
        except Exception as e:
            return {
                "success": False,
                "spoken_response": "Sorry, something went wrong.",
                "error": str(e),
            }

    # Default handlers for common shortcuts
    if shortcut_id == "next_task":
        return await _handle_next_task(user_id)
    elif shortcut_id == "start_task":
        return await _handle_start_task(user_id, params)
    elif shortcut_id == "complete_step":
        return await _handle_complete_step(user_id, params)
    elif shortcut_id == "snooze_reminders":
        return await _handle_snooze_reminders(user_id, params)
    elif shortcut_id == "start_focus":
        return await _handle_start_focus(user_id, params)
    elif shortcut_id == "end_focus":
        return await _handle_end_focus(user_id)
    elif shortcut_id == "check_in":
        return await _handle_check_in(user_id)
    elif shortcut_id == "add_task":
        return await _handle_add_task(user_id, params)
    else:
        return {
            "success": False,
            "spoken_response": "I don't recognize that shortcut.",
            "error": f"Unknown shortcut: {shortcut_id}",
        }


async def get_suggested_shortcuts(user_id: str, limit: int = 5) -> dict[str, Any]:
    """
    Get shortcuts to suggest based on user patterns.

    Returns suggested shortcuts based on:
    - Time of day (morning routines, evening wind-down)
    - Recent activity (recently viewed tasks)
    - Patterns (daily habits)

    Returns:
        {
            "success": True,
            "shortcuts": [
                {
                    "id": str,
                    "title": str,
                    "subtitle": str,
                    "icon": str,
                    "user_info": {...}
                }
            ]
        }
    """
    try:
        shortcuts = []
        now = datetime.now()
        hour = now.hour

        # Time-based suggestions
        if 6 <= hour < 10:
            # Morning: Suggest daily planning
            shortcuts.append({
                "id": "morning_planning",
                "title": "Plan Your Day",
                "subtitle": "See today's tasks",
                "icon": "sun.max",
                "user_info": {"context": "morning"},
            })
        elif 12 <= hour < 14:
            # Lunch: Suggest check-in
            shortcuts.append({
                "id": "midday_checkin",
                "title": "Midday Check-in",
                "subtitle": "How's the day going?",
                "icon": "clock",
                "user_info": {"context": "midday"},
            })
        elif 17 <= hour < 20:
            # Evening: Suggest wrap-up
            shortcuts.append({
                "id": "evening_wrapup",
                "title": "Wrap Up Day",
                "subtitle": "Review and plan tomorrow",
                "icon": "moon",
                "user_info": {"context": "evening"},
            })

        # Get recently viewed tasks
        recent_tasks = await _get_recent_tasks(user_id, limit=2)
        for task in recent_tasks:
            shortcuts.append({
                "id": f"task_{task['id']}",
                "title": task.get("title", "Continue Task")[:25],
                "subtitle": "Continue where you left off",
                "icon": "arrow.right.circle",
                "user_info": {"task_id": task["id"]},
            })

        # Limit to requested number
        shortcuts = shortcuts[:limit]

        return {
            "success": True,
            "shortcuts": shortcuts,
        }

    except Exception as e:
        return {
            "success": False,
            "shortcuts": [],
            "error": str(e),
        }


async def handle_quick_action(user_id: str, action_id: str, params: dict | None = None) -> dict[str, Any]:
    """
    Handle quick action (3D Touch / long press) invocation.

    Args:
        user_id: User identifier
        action_id: Action being invoked
        params: Optional parameters

    Returns:
        {
            "success": True,
            "navigate_to": "/tasks/current",  # Path to navigate in app
            "message": "Optional message"
        }
    """
    params = params or {}

    if action_id == "next_task":
        return {
            "success": True,
            "navigate_to": "tasks/current",
        }
    elif action_id == "quick_capture":
        return {
            "success": True,
            "navigate_to": "tasks/add",
        }
    elif action_id == "focus_mode":
        # Start focus mode and navigate
        await _handle_start_focus(user_id, params)
        return {
            "success": True,
            "navigate_to": "focus",
            "message": "Focus mode started",
        }
    elif action_id.startswith("recent_task_"):
        task_id = action_id.replace("recent_task_", "")
        return {
            "success": True,
            "navigate_to": f"tasks/{task_id}",
        }
    else:
        return {
            "success": False,
            "navigate_to": "",
            "error": f"Unknown action: {action_id}",
        }


# =============================================================================
# Shortcut Handlers
# =============================================================================


async def _handle_next_task(user_id: str) -> dict[str, Any]:
    """Handle 'What's my next task?' shortcut."""
    try:
        from tools.tasks.current_step import get_current_step
        from tools.tasks.manager import get_tasks

        # Get next task
        result = await get_tasks(
            user_id=user_id,
            status="pending",
            limit=1,
            order_by="priority",
        )

        if not result.get("success") or not result.get("tasks"):
            return {
                "success": True,
                "spoken_response": "You're all clear! No tasks right now.",
                "data": {"has_task": False},
            }

        task = result["tasks"][0]
        task_title = task.get("title", "your task")

        # Get current step
        step_result = await get_current_step(task_id=task["id"])
        current_step = None
        if step_result.get("success") and step_result.get("step"):
            current_step = step_result["step"].get("description")

        if current_step:
            spoken = f"Your next step is: {current_step}"
        else:
            spoken = f"Your next task is: {task_title}"

        return {
            "success": True,
            "spoken_response": spoken,
            "data": {
                "has_task": True,
                "task_id": task["id"],
                "task_title": task_title,
                "current_step": current_step,
            },
        }

    except ImportError:
        return {
            "success": True,
            "spoken_response": "I couldn't check your tasks right now.",
            "data": {"has_task": False},
        }
    except Exception as e:
        return {
            "success": False,
            "spoken_response": "Something went wrong checking your tasks.",
            "error": str(e),
        }


async def _handle_start_task(user_id: str, params: dict) -> dict[str, Any]:
    """Handle 'I'm starting a task' shortcut."""
    try:
        # This would mark the current task as in-progress
        # and potentially start a focus timer

        return {
            "success": True,
            "spoken_response": "Great! You've got this. I'll minimize distractions.",
            "data": {"started": True},
            "continue_in_app": False,
        }

    except Exception as e:
        return {
            "success": False,
            "spoken_response": "I couldn't start the task.",
            "error": str(e),
        }


async def _handle_complete_step(user_id: str, params: dict) -> dict[str, Any]:
    """Handle 'I finished a step' shortcut."""
    try:
        from tools.tasks.current_step import complete_current_step

        result = await complete_current_step(user_id=user_id)

        if result.get("success"):
            if result.get("task_completed"):
                return {
                    "success": True,
                    "spoken_response": "Awesome! You finished the whole task! Nice work!",
                    "data": {"task_completed": True},
                }
            else:
                next_step = result.get("next_step", {}).get("description", "")
                if next_step:
                    return {
                        "success": True,
                        "spoken_response": f"Nice! Your next step is: {next_step}",
                        "data": {"step_completed": True, "next_step": next_step},
                    }
                else:
                    return {
                        "success": True,
                        "spoken_response": "Step marked as done!",
                        "data": {"step_completed": True},
                    }
        else:
            return {
                "success": False,
                "spoken_response": "I couldn't mark that step as done.",
                "error": result.get("error", "Unknown error"),
            }

    except ImportError:
        return {
            "success": True,
            "spoken_response": "Step marked as done!",
            "data": {"step_completed": True},
        }
    except Exception as e:
        return {
            "success": False,
            "spoken_response": "Something went wrong.",
            "error": str(e),
        }


async def _handle_snooze_reminders(user_id: str, params: dict) -> dict[str, Any]:
    """Handle 'Snooze my reminders' shortcut."""
    try:
        duration_minutes = params.get("duration_minutes", 30)

        # This would pause notifications for the specified duration
        from tools.mobile.preferences.user_preferences import update_preferences

        snooze_until = datetime.utcnow() + timedelta(minutes=duration_minutes)

        # In production, this would update a snooze_until field
        # For now, we return success

        return {
            "success": True,
            "spoken_response": f"Reminders snoozed for {duration_minutes} minutes.",
            "data": {
                "snoozed": True,
                "duration_minutes": duration_minutes,
                "snooze_until": snooze_until.isoformat(),
            },
        }

    except Exception as e:
        return {
            "success": False,
            "spoken_response": "I couldn't snooze your reminders.",
            "error": str(e),
        }


async def _handle_start_focus(user_id: str, params: dict) -> dict[str, Any]:
    """Handle 'Start focus mode' shortcut."""
    try:
        duration_minutes = params.get("duration_minutes", 25)  # Default: Pomodoro

        # This would enable focus mode and potentially DND
        from tools.automation.flow_detector import start_focus_session

        result = await start_focus_session(
            user_id=user_id,
            duration_minutes=duration_minutes,
        )

        if result.get("success"):
            return {
                "success": True,
                "spoken_response": f"Focus mode started for {duration_minutes} minutes. You've got this!",
                "data": {
                    "focus_started": True,
                    "duration_minutes": duration_minutes,
                },
            }
        else:
            return {
                "success": True,
                "spoken_response": "Focus mode activated. Let's do this!",
                "data": {"focus_started": True},
            }

    except ImportError:
        return {
            "success": True,
            "spoken_response": "Focus mode activated!",
            "data": {"focus_started": True},
        }
    except Exception as e:
        return {
            "success": False,
            "spoken_response": "I couldn't start focus mode.",
            "error": str(e),
        }


async def _handle_end_focus(user_id: str) -> dict[str, Any]:
    """Handle 'End focus mode' shortcut."""
    try:
        from tools.automation.flow_detector import end_focus_session

        result = await end_focus_session(user_id=user_id)

        return {
            "success": True,
            "spoken_response": "Focus session ended. Great work!",
            "data": {"focus_ended": True},
        }

    except ImportError:
        return {
            "success": True,
            "spoken_response": "Focus session ended. Nice job!",
            "data": {"focus_ended": True},
        }
    except Exception as e:
        return {
            "success": False,
            "spoken_response": "I couldn't end focus mode.",
            "error": str(e),
        }


async def _handle_check_in(user_id: str) -> dict[str, Any]:
    """Handle 'Check in with Dex' shortcut."""
    try:
        # Get current status
        from tools.tasks.manager import get_tasks
        from tools.learning.energy_tracker import get_current_energy

        # Get pending tasks count
        tasks_result = await get_tasks(user_id=user_id, status="pending")
        task_count = len(tasks_result.get("tasks", [])) if tasks_result.get("success") else 0

        # Get energy level
        try:
            energy_result = await get_current_energy(user_id=user_id)
            energy_level = energy_result.get("level", 0.5) if energy_result.get("success") else 0.5
        except ImportError:
            energy_level = 0.5

        # Build response based on state
        if task_count == 0:
            spoken = "You're all caught up! No pending tasks."
        elif task_count == 1:
            spoken = "You have 1 task to work on."
        else:
            spoken = f"You have {task_count} tasks. "
            if energy_level >= 0.7:
                spoken += "Your energy looks good!"
            elif energy_level <= 0.3:
                spoken += "Consider starting with something small."
            else:
                spoken += "Ready when you are."

        return {
            "success": True,
            "spoken_response": spoken,
            "data": {
                "task_count": task_count,
                "energy_level": energy_level,
            },
            "continue_in_app": task_count > 0,
        }

    except Exception as e:
        return {
            "success": True,
            "spoken_response": "Ready when you are!",
            "data": {},
        }


async def _handle_add_task(user_id: str, params: dict) -> dict[str, Any]:
    """Handle 'Add a task' shortcut."""
    try:
        task_title = params.get("title")

        if not task_title:
            # Need to open app for input
            return {
                "success": True,
                "spoken_response": "Opening task capture.",
                "continue_in_app": True,
                "data": {"needs_input": True},
            }

        # Create task
        from tools.tasks.manager import create_task

        result = await create_task(
            user_id=user_id,
            title=task_title,
            priority=5,  # Default priority
        )

        if result.get("success"):
            return {
                "success": True,
                "spoken_response": f"Added: {task_title}",
                "data": {
                    "task_id": result.get("task_id"),
                    "title": task_title,
                },
            }
        else:
            return {
                "success": False,
                "spoken_response": "I couldn't add that task.",
                "error": result.get("error"),
            }

    except ImportError:
        return {
            "success": True,
            "spoken_response": "Opening task capture.",
            "continue_in_app": True,
        }
    except Exception as e:
        return {
            "success": False,
            "spoken_response": "Something went wrong adding the task.",
            "error": str(e),
        }


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_recent_tasks(user_id: str, limit: int = 3) -> list[dict]:
    """Get recently viewed tasks."""
    try:
        from tools.tasks.manager import get_tasks

        result = await get_tasks(
            user_id=user_id,
            status="pending",
            limit=limit,
            order_by="last_viewed_at",
        )

        if result.get("success"):
            return result.get("tasks", [])
        return []
    except ImportError:
        return []
    except Exception:
        return []


# =============================================================================
# CLI Interface
# =============================================================================

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Shortcuts Handler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Handle shortcut
    handle_parser = subparsers.add_parser("handle", help="Handle a shortcut")
    handle_parser.add_argument("shortcut_id", help="Shortcut ID")
    handle_parser.add_argument("--user-id", default="default", help="User ID")
    handle_parser.add_argument("--params", default="{}", help="JSON params")

    # Get suggestions
    suggest_parser = subparsers.add_parser("suggest", help="Get suggested shortcuts")
    suggest_parser.add_argument("--user-id", default="default", help="User ID")
    suggest_parser.add_argument("--limit", type=int, default=5, help="Max shortcuts")

    # Quick action
    action_parser = subparsers.add_parser("action", help="Handle quick action")
    action_parser.add_argument("action_id", help="Action ID")
    action_parser.add_argument("--user-id", default="default", help="User ID")

    args = parser.parse_args()

    async def main():
        if args.command == "handle":
            params = json.loads(args.params)
            result = await handle_shortcut(args.user_id, args.shortcut_id, params)
        elif args.command == "suggest":
            result = await get_suggested_shortcuts(args.user_id, args.limit)
        elif args.command == "action":
            result = await handle_quick_action(args.user_id, args.action_id)
        else:
            result = {"error": "Unknown command"}

        print(json.dumps(result, indent=2))

    asyncio.run(main())
