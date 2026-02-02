"""
Tool: Current Step Provider
Purpose: Return ONLY the single next action. No lists. No future steps. Just ONE thing.

This is the core ADHD-friendly interface. When a user asks "what should I do?",
they get exactly ONE actionable step with friction pre-solved.

A list of five things is actually zero things for ADHD decision fatigue.

Usage:
    python tools/tasks/current_step.py --action get --user alice
    python tools/tasks/current_step.py --action get --user alice --task-id abc123
    python tools/tasks/current_step.py --action get --user alice --energy low

Dependencies:
    - sqlite3 (stdlib)

Output:
    JSON result with single current step
"""

import argparse
import json
import sys
from typing import Any

from . import ENERGY_LEVELS
from .manager import get_connection, row_to_dict


def get_current_step(
    user_id: str,
    task_id: str | None = None,
    energy_level: str | None = None,
) -> dict[str, Any]:
    """
    Get the single next action for a user.

    This is the primary interface for ADHD-friendly task management.
    Returns ONE step, not a list. Includes pre-solved friction.

    Args:
        user_id: User to get step for
        task_id: Specific task (optional - otherwise picks highest priority)
        energy_level: Match tasks to energy level (low/medium/high)

    Returns:
        dict with single current step and formatted instruction
    """
    if energy_level and energy_level not in ENERGY_LEVELS:
        return {"success": False, "error": f"Invalid energy level. Must be one of: {ENERGY_LEVELS}"}

    conn = get_connection()
    cursor = conn.cursor()

    if task_id:
        # Get specific task
        cursor.execute(
            """
            SELECT * FROM tasks
            WHERE id = ? AND user_id = ? AND status IN ('pending', 'in_progress')
        """,
            (task_id, user_id),
        )
        task = row_to_dict(cursor.fetchone())

        if not task:
            conn.close()
            return {"success": False, "error": f"Task not found or not active: {task_id}"}
    else:
        # Find highest priority active task
        conditions = ["user_id = ?", "status IN ('pending', 'in_progress')"]
        params: list[Any] = [user_id]

        if energy_level:
            conditions.append("(energy_level = ? OR energy_level IS NULL)")
            params.append(energy_level)

        where_clause = " AND ".join(conditions)

        cursor.execute(
            f"""
            SELECT * FROM tasks
            WHERE {where_clause}
            ORDER BY
                CASE status WHEN 'in_progress' THEN 0 ELSE 1 END,
                priority DESC,
                created_at ASC
            LIMIT 1
        """,
            params,
        )
        task = row_to_dict(cursor.fetchone())

        if not task:
            conn.close()
            return {
                "success": True,
                "data": {
                    "has_step": False,
                    "message": "No active tasks right now",  # Positive framing
                },
            }

    # Get current step
    if task.get("current_step_id"):
        cursor.execute("SELECT * FROM task_steps WHERE id = ?", (task["current_step_id"],))
        step = row_to_dict(cursor.fetchone())
    else:
        # Get first pending step
        cursor.execute(
            """
            SELECT * FROM task_steps
            WHERE task_id = ? AND status = 'pending'
            ORDER BY step_number
            LIMIT 1
        """,
            (task["id"],),
        )
        step = row_to_dict(cursor.fetchone())

    if not step:
        conn.close()
        # Task has no steps - maybe not decomposed yet
        return {
            "success": True,
            "data": {
                "has_step": False,
                "task_id": task["id"],
                "task_title": task["title"],
                "message": "Task needs to be broken down into steps",
            },
        }

    # Get friction for this step (pre-solved info)
    cursor.execute(
        """
        SELECT * FROM task_friction
        WHERE (step_id = ? OR task_id = ?)
        AND resolved = 0
        ORDER BY created_at
    """,
        (step["id"], task["id"]),
    )
    friction_points = [row_to_dict(row) for row in cursor.fetchall()]

    conn.close()

    # Build friction pre-solved text
    friction_pre_solved = None
    if step.get("friction_notes"):
        friction_pre_solved = step["friction_notes"]
    elif friction_points:
        # Get first unresolved friction with suggested resolution
        for fp in friction_points:
            if fp.get("description"):
                friction_pre_solved = fp["description"]
                break

    # Format the instruction
    formatted = format_step_instruction(
        step_description=step["description"],
        friction_pre_solved=friction_pre_solved,
        action_verb=step.get("action_verb"),
    )

    return {
        "success": True,
        "data": {
            "has_step": True,
            "task_id": task["id"],
            "task_title": task["title"],
            "current_step": {
                "id": step["id"],
                "step_number": step["step_number"],
                "description": step["description"],
                "action_verb": step.get("action_verb"),
                "friction_pre_solved": friction_pre_solved,
                "estimated_minutes": step.get("estimated_minutes"),
            },
            "friction_points": friction_points,
            "formatted": formatted,
        },
    }


def format_step_instruction(
    step_description: str,
    friction_pre_solved: str | None = None,
    action_verb: str | None = None,
) -> str:
    """
    Format a step as a clean, actionable instruction.

    Args:
        step_description: The step text
        friction_pre_solved: Pre-solved friction hint
        action_verb: The action verb

    Returns:
        Clean formatted string
    """
    # Clean up description
    instruction = step_description.strip()

    # Capitalize first letter if needed
    if instruction and instruction[0].islower():
        instruction = instruction[0].upper() + instruction[1:]

    # Add friction pre-solve as helpful hint
    if friction_pre_solved:
        instruction = f"{instruction} - {friction_pre_solved}"

    return instruction


def get_next_step_preview(user_id: str, task_id: str) -> dict[str, Any]:
    """
    Preview what the next step will be after current is done.

    NOT for showing to user by default - just for system use.

    Args:
        user_id: User ID
        task_id: Task ID

    Returns:
        dict with next step preview (if any)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get task and current step
    cursor.execute(
        """
        SELECT * FROM tasks
        WHERE id = ? AND user_id = ?
    """,
        (task_id, user_id),
    )
    task = row_to_dict(cursor.fetchone())

    if not task:
        conn.close()
        return {"success": False, "error": "Task not found"}

    # Get current step number
    current_step_num = 0
    if task.get("current_step_id"):
        cursor.execute(
            "SELECT step_number FROM task_steps WHERE id = ?", (task["current_step_id"],)
        )
        row = cursor.fetchone()
        if row:
            current_step_num = row["step_number"]

    # Get next step
    cursor.execute(
        """
        SELECT * FROM task_steps
        WHERE task_id = ? AND step_number > ? AND status = 'pending'
        ORDER BY step_number
        LIMIT 1
    """,
        (task_id, current_step_num),
    )
    next_step = row_to_dict(cursor.fetchone())

    conn.close()

    if not next_step:
        return {
            "success": True,
            "data": {
                "has_next": False,
                "message": "Current step is the last one",
            },
        }

    return {
        "success": True,
        "data": {
            "has_next": True,
            "next_step": {
                "id": next_step["id"],
                "step_number": next_step["step_number"],
                "description": next_step["description"],
            },
        },
    }


def get_task_progress(user_id: str, task_id: str) -> dict[str, Any]:
    """
    Get progress on a task (completed vs total steps).

    Use sparingly - showing progress can create pressure.
    Better for end-of-day summaries than during work.

    Args:
        user_id: User ID
        task_id: Task ID

    Returns:
        dict with progress info
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Verify task belongs to user
    cursor.execute("SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    task = row_to_dict(cursor.fetchone())

    if not task:
        conn.close()
        return {"success": False, "error": "Task not found"}

    # Count steps
    cursor.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
        FROM task_steps
        WHERE task_id = ?
    """,
        (task_id,),
    )
    counts = cursor.fetchone()

    conn.close()

    total = counts["total"] or 0
    completed = counts["completed"] or 0

    return {
        "success": True,
        "data": {
            "task_id": task_id,
            "task_title": task["title"],
            "completed_steps": completed,
            "total_steps": total,
            "percentage": round((completed / total * 100) if total > 0 else 0),
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Current Step - Get the single next action (ADHD-friendly)"
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["get", "preview-next", "progress"],
        help="Action to perform",
    )

    parser.add_argument("--user", required=True, help="User ID")
    parser.add_argument("--task-id", help="Specific task ID")
    parser.add_argument("--energy", choices=ENERGY_LEVELS, help="Match to energy level")

    args = parser.parse_args()
    result = None

    if args.action == "get":
        result = get_current_step(
            user_id=args.user,
            task_id=args.task_id,
            energy_level=args.energy,
        )

    elif args.action == "preview-next":
        if not args.task_id:
            print(json.dumps({"success": False, "error": "--task-id required for preview-next"}))
            sys.exit(1)
        result = get_next_step_preview(args.user, args.task_id)

    elif args.action == "progress":
        if not args.task_id:
            print(json.dumps({"success": False, "error": "--task-id required for progress"}))
            sys.exit(1)
        result = get_task_progress(args.user, args.task_id)

    if result:
        print(json.dumps(result, indent=2, default=str))
        if not result.get("success"):
            sys.exit(1)


if __name__ == "__main__":
    main()
