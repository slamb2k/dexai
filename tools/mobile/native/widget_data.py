"""
Widget and Watch Data Provider

Provides data formatted for:
- Home screen widgets (iOS/Android)
- Apple Watch app and complications

ADHD-friendly: Single-focus data, no overwhelm.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

# Note: In production, these would import from the actual task/learning modules
# For now, we provide mock data structures that match the expected interface


async def get_widget_data(user_id: str) -> dict[str, Any]:
    """
    Get data formatted for home screen widget display.

    Returns:
        {
            "success": True,
            "next_task": {
                "id": str,
                "title": str,
                "priority": int,
                "due_time": str | None,
                "is_overdue": bool
            } | None,
            "current_step": {
                "description": str,
                "step_number": int,
                "total_steps": int
            } | None,
            "energy_level": "high" | "medium" | "low" | "unknown",
            "upcoming_count": int,
            "last_updated": str
        }
    """
    try:
        # Fetch next task from task manager
        next_task = await _get_next_task(user_id)

        # Fetch current step if task exists
        current_step = None
        if next_task:
            current_step = await _get_current_step(user_id, next_task.get("id"))

        # Get energy level from learning module
        energy_level = await _get_energy_level(user_id)

        # Get upcoming task count
        upcoming_count = await _get_upcoming_count(user_id)

        return {
            "success": True,
            "next_task": next_task,
            "current_step": current_step,
            "energy_level": energy_level,
            "upcoming_count": upcoming_count,
            "last_updated": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "next_task": None,
            "current_step": None,
            "energy_level": "unknown",
            "upcoming_count": 0,
            "last_updated": datetime.utcnow().isoformat(),
        }


async def get_watch_data(user_id: str) -> dict[str, Any]:
    """
    Get data formatted for Apple Watch display.

    Returns:
        {
            "success": True,
            "next_task": {...},
            "current_step": {...},
            "tasks_today": int,
            "energy_level": str,
            "in_flow_state": bool,
            "pending_actions": int,
            "complications": [
                {
                    "id": str,
                    "type": str,
                    "data": {...},
                    "expires_at": str
                }
            ]
        }
    """
    try:
        # Get widget data as base
        widget_data = await get_widget_data(user_id)

        # Get additional watch-specific data
        tasks_today = await _get_tasks_today_count(user_id)
        in_flow_state = await _check_flow_state(user_id)
        pending_actions = await _get_pending_actions_count(user_id)

        # Build complications data
        complications = await _build_complications(
            user_id, widget_data, tasks_today, in_flow_state
        )

        return {
            "success": True,
            "next_task": widget_data.get("next_task"),
            "current_step": widget_data.get("current_step"),
            "tasks_today": tasks_today,
            "energy_level": widget_data.get("energy_level", "unknown"),
            "in_flow_state": in_flow_state,
            "pending_actions": pending_actions,
            "complications": complications,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "next_task": None,
            "current_step": None,
            "tasks_today": 0,
            "energy_level": "unknown",
            "in_flow_state": False,
            "pending_actions": 0,
            "complications": [],
        }


# =============================================================================
# Internal Helper Functions
# =============================================================================


async def _get_next_task(user_id: str) -> dict[str, Any] | None:
    """Get the next task for the user."""
    try:
        # In production, this would call tools.tasks.current_step.get_current_task()
        # For now, return a mock structure
        from tools.tasks.manager import get_tasks

        result = await get_tasks(
            user_id=user_id,
            status="pending",
            limit=1,
            order_by="priority",
        )

        if result.get("success") and result.get("tasks"):
            task = result["tasks"][0]
            return {
                "id": task.get("id"),
                "title": task.get("title", "Untitled"),
                "priority": task.get("priority", 5),
                "due_time": task.get("due_at"),
                "is_overdue": _is_overdue(task.get("due_at")),
            }

        return None
    except ImportError:
        # Tasks module not available, return None
        return None
    except Exception:
        return None


async def _get_current_step(user_id: str, task_id: str | None) -> dict[str, Any] | None:
    """Get the current step for a task."""
    if not task_id:
        return None

    try:
        # In production, this would call tools.tasks.current_step.get_current_step()
        from tools.tasks.current_step import get_current_step

        result = await get_current_step(task_id=task_id)

        if result.get("success") and result.get("step"):
            step = result["step"]
            return {
                "description": step.get("description", ""),
                "step_number": step.get("step_number", 1),
                "total_steps": step.get("total_steps", 1),
            }

        return None
    except ImportError:
        return None
    except Exception:
        return None


async def _get_energy_level(user_id: str) -> str:
    """Get the current energy level for the user."""
    try:
        # In production, this would call tools.learning.energy_tracker
        from tools.learning.energy_tracker import get_current_energy

        result = await get_current_energy(user_id=user_id)

        if result.get("success"):
            level = result.get("level", 0.5)
            if level >= 0.7:
                return "high"
            elif level >= 0.4:
                return "medium"
            else:
                return "low"

        return "unknown"
    except ImportError:
        return "unknown"
    except Exception:
        return "unknown"


async def _get_upcoming_count(user_id: str) -> int:
    """Get count of upcoming tasks."""
    try:
        from tools.tasks.manager import get_tasks

        result = await get_tasks(
            user_id=user_id,
            status="pending",
            limit=100,
        )

        if result.get("success"):
            # Exclude the first task (it's the "next" task)
            tasks = result.get("tasks", [])
            return max(0, len(tasks) - 1)

        return 0
    except ImportError:
        return 0
    except Exception:
        return 0


async def _get_tasks_today_count(user_id: str) -> int:
    """Get count of tasks for today."""
    try:
        from tools.tasks.manager import get_tasks

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        result = await get_tasks(
            user_id=user_id,
            due_before=today_end.isoformat(),
            due_after=today_start.isoformat(),
        )

        if result.get("success"):
            return len(result.get("tasks", []))

        return 0
    except ImportError:
        return 0
    except Exception:
        return 0


async def _check_flow_state(user_id: str) -> bool:
    """Check if user is in flow state."""
    try:
        from tools.automation.flow_detector import get_flow_state

        result = await get_flow_state(user_id=user_id)

        return result.get("in_flow", False)
    except ImportError:
        return False
    except Exception:
        return False


async def _get_pending_actions_count(user_id: str) -> int:
    """Get count of pending actions in queue."""
    try:
        from tools.mobile.queue.notification_queue import get_pending

        pending = await get_pending(user_id=user_id)
        return len(pending) if pending else 0
    except ImportError:
        return 0
    except Exception:
        return 0


async def _build_complications(
    user_id: str,
    widget_data: dict,
    tasks_today: int,
    in_flow_state: bool,
) -> list[dict[str, Any]]:
    """Build complication data for Apple Watch."""
    complications = []
    expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()

    # Current task complication
    next_task = widget_data.get("next_task")
    if next_task:
        title = next_task.get("title", "")
        short_title = title[:15] + "..." if len(title) > 15 else title

        complications.append({
            "id": "current_task",
            "type": "current_task",
            "data": {
                "shortText": short_title,
                "longText": title,
                "symbolName": "checklist",
                "tintColor": "#4F46E5",
            },
            "expires_at": expires_at,
        })

    # Task count complication
    complications.append({
        "id": "task_count",
        "type": "task_count",
        "data": {
            "value": tasks_today,
            "shortText": f"{tasks_today} tasks",
            "symbolName": "list.bullet",
            "tintColor": "#6B7280",
        },
        "expires_at": expires_at,
    })

    # Energy level complication
    energy = widget_data.get("energy_level", "unknown")
    energy_colors = {
        "high": "#10B981",
        "medium": "#F59E0B",
        "low": "#EF4444",
        "unknown": "#9CA3AF",
    }
    energy_values = {
        "high": 0.9,
        "medium": 0.5,
        "low": 0.2,
        "unknown": 0.5,
    }

    complications.append({
        "id": "energy_level",
        "type": "energy_level",
        "data": {
            "gaugeValue": energy_values.get(energy, 0.5),
            "shortText": energy.title(),
            "symbolName": "battery.100" if energy == "high" else "battery.50" if energy == "medium" else "battery.25",
            "tintColor": energy_colors.get(energy, "#9CA3AF"),
        },
        "expires_at": expires_at,
    })

    # Flow state indicator (if in flow)
    if in_flow_state:
        complications.append({
            "id": "flow_state",
            "type": "flow_state",
            "data": {
                "shortText": "Flow",
                "symbolName": "scope",
                "tintColor": "#8B5CF6",
            },
            "expires_at": expires_at,
        })

    return complications


def _is_overdue(due_at: str | None) -> bool:
    """Check if a due date is overdue."""
    if not due_at:
        return False

    try:
        due_dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        return due_dt < datetime.now(due_dt.tzinfo)
    except Exception:
        return False


# =============================================================================
# CLI Interface
# =============================================================================

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Widget and Watch Data Provider")
    parser.add_argument("command", choices=["widget", "watch"], help="Data type to fetch")
    parser.add_argument("--user-id", default="default", help="User ID")

    args = parser.parse_args()

    async def main():
        if args.command == "widget":
            result = await get_widget_data(args.user_id)
        else:
            result = await get_watch_data(args.user_id)

        print(json.dumps(result, indent=2))

    asyncio.run(main())
