"""
Tool: Task Manager
Purpose: CRUD operations for tasks with parent/subtask relationships

This provides task lifecycle management for ADHD-friendly task tracking:
- Create tasks from vague input
- Track status progression
- Maintain parent/child relationships
- Record step completion

Usage:
    python tools/tasks/manager.py --action create --user alice --task "do taxes"
    python tools/tasks/manager.py --action list --user alice --status pending
    python tools/tasks/manager.py --action get --task-id abc123
    python tools/tasks/manager.py --action update --task-id abc123 --status in_progress
    python tools/tasks/manager.py --action complete --task-id abc123
    python tools/tasks/manager.py --action abandon --task-id abc123 --reason "no longer needed"
    python tools/tasks/manager.py --action complete-step --step-id step123

Dependencies:
    - sqlite3 (stdlib)
    - uuid (stdlib)

Output:
    JSON result with success status and data
"""

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import (
    DB_PATH,
    ENERGY_LEVELS,
    FRICTION_TYPES,
    STEP_STATUSES,
    TASK_STATUSES,
)


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    cursor = conn.cursor()

    # Main tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            raw_input TEXT NOT NULL,
            title TEXT,
            description TEXT,
            parent_task_id TEXT,
            current_step_id TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'abandoned')),
            energy_level TEXT CHECK(energy_level IN ('low', 'medium', 'high') OR energy_level IS NULL),
            estimated_minutes INTEGER,
            priority INTEGER DEFAULT 5,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            completed_at DATETIME,
            abandon_reason TEXT,
            FOREIGN KEY(parent_task_id) REFERENCES tasks(id)
        )
    """)

    # Task steps table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_steps (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            description TEXT NOT NULL,
            action_verb TEXT,
            friction_notes TEXT,
            friction_solved INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'skipped')),
            estimated_minutes INTEGER,
            completed_at DATETIME,
            FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
    """)

    # Task friction table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_friction (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            step_id TEXT,
            friction_type TEXT CHECK(friction_type IN ('missing_info', 'phone_call', 'decision', 'password', 'document', 'appointment')),
            description TEXT,
            resolution TEXT,
            resolved INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME,
            FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY(step_id) REFERENCES task_steps(id) ON DELETE CASCADE
        )
    """)

    # Indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_steps_task ON task_steps(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_steps_status ON task_steps(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_friction_task ON task_friction(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_friction_step ON task_friction(step_id)")

    conn.commit()
    return conn


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    return dict(row)


def generate_id() -> str:
    """Generate a short unique ID."""
    return uuid.uuid4().hex[:12]


def create_task(
    user_id: str,
    raw_input: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    energy_level: Optional[str] = None,
    estimated_minutes: Optional[int] = None,
    priority: int = 5,
) -> Dict[str, Any]:
    """
    Create a new task from raw input.

    Args:
        user_id: User who owns the task
        raw_input: Original task description (e.g., "do taxes")
        title: Cleaned up title (optional, can be set during decomposition)
        description: Detailed description (optional)
        parent_task_id: Parent task if this is a subtask
        energy_level: Required energy (low/medium/high)
        estimated_minutes: Estimated time to complete
        priority: 1-10, higher = more important

    Returns:
        dict with success status and task data
    """
    if energy_level and energy_level not in ENERGY_LEVELS:
        return {"success": False, "error": f"Invalid energy level. Must be one of: {ENERGY_LEVELS}"}

    task_id = generate_id()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO tasks (id, user_id, raw_input, title, description, parent_task_id, energy_level, estimated_minutes, priority)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (task_id, user_id, raw_input, title or raw_input, description, parent_task_id, energy_level, estimated_minutes, priority))

    conn.commit()

    # Fetch the created task
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = row_to_dict(cursor.fetchone())

    conn.close()

    return {
        "success": True,
        "data": {"task_id": task_id, "task": task},
        "message": f"Task created with ID {task_id}",
    }


def get_task(task_id: str, include_steps: bool = True, include_friction: bool = True) -> Dict[str, Any]:
    """
    Get task details by ID.

    Args:
        task_id: Task ID to fetch
        include_steps: Include task steps
        include_friction: Include friction points

    Returns:
        dict with task data
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = row_to_dict(cursor.fetchone())

    if not task:
        conn.close()
        return {"success": False, "error": f"Task not found: {task_id}"}

    if include_steps:
        cursor.execute("""
            SELECT * FROM task_steps
            WHERE task_id = ?
            ORDER BY step_number
        """, (task_id,))
        task["steps"] = [row_to_dict(row) for row in cursor.fetchall()]

    if include_friction:
        cursor.execute("""
            SELECT * FROM task_friction
            WHERE task_id = ?
            ORDER BY created_at
        """, (task_id,))
        task["friction_points"] = [row_to_dict(row) for row in cursor.fetchall()]

    conn.close()

    return {"success": True, "data": task}


def list_tasks(
    user_id: str,
    status: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    energy_level: Optional[str] = None,
    include_subtasks: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    List tasks for a user with optional filters.

    Args:
        user_id: User whose tasks to list
        status: Filter by status
        parent_task_id: Filter by parent task
        energy_level: Filter by energy level
        include_subtasks: Include subtasks in results
        limit: Maximum results
        offset: Pagination offset

    Returns:
        dict with task list
    """
    if status and status not in TASK_STATUSES:
        return {"success": False, "error": f"Invalid status. Must be one of: {TASK_STATUSES}"}

    conn = get_connection()
    cursor = conn.cursor()

    conditions = ["user_id = ?"]
    params: List[Any] = [user_id]

    if status:
        conditions.append("status = ?")
        params.append(status)

    if parent_task_id:
        conditions.append("parent_task_id = ?")
        params.append(parent_task_id)
    elif not include_subtasks:
        conditions.append("parent_task_id IS NULL")

    if energy_level:
        conditions.append("energy_level = ?")
        params.append(energy_level)

    where_clause = " AND ".join(conditions)

    cursor.execute(f"""
        SELECT * FROM tasks
        WHERE {where_clause}
        ORDER BY priority DESC, created_at DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    tasks = [row_to_dict(row) for row in cursor.fetchall()]

    # Get total count
    cursor.execute(f"SELECT COUNT(*) as count FROM tasks WHERE {where_clause}", params)
    total = cursor.fetchone()["count"]

    conn.close()

    return {
        "success": True,
        "data": {"tasks": tasks, "total": total, "limit": limit, "offset": offset},
    }


def update_task(
    task_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    energy_level: Optional[str] = None,
    estimated_minutes: Optional[int] = None,
    priority: Optional[int] = None,
    current_step_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update task fields.

    Args:
        task_id: Task to update
        title: New title
        description: New description
        status: New status
        energy_level: New energy level
        estimated_minutes: New time estimate
        priority: New priority
        current_step_id: ID of current step

    Returns:
        dict with updated task
    """
    if status and status not in TASK_STATUSES:
        return {"success": False, "error": f"Invalid status. Must be one of: {TASK_STATUSES}"}

    if energy_level and energy_level not in ENERGY_LEVELS:
        return {"success": False, "error": f"Invalid energy level. Must be one of: {ENERGY_LEVELS}"}

    conn = get_connection()
    cursor = conn.cursor()

    # Check task exists
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Task not found: {task_id}"}

    updates = []
    params: List[Any] = []

    if title is not None:
        updates.append("title = ?")
        params.append(title)

    if description is not None:
        updates.append("description = ?")
        params.append(description)

    if status is not None:
        updates.append("status = ?")
        params.append(status)
        if status == "in_progress":
            updates.append("started_at = ?")
            params.append(datetime.now().isoformat())
        elif status in ("completed", "abandoned"):
            updates.append("completed_at = ?")
            params.append(datetime.now().isoformat())

    if energy_level is not None:
        updates.append("energy_level = ?")
        params.append(energy_level)

    if estimated_minutes is not None:
        updates.append("estimated_minutes = ?")
        params.append(estimated_minutes)

    if priority is not None:
        updates.append("priority = ?")
        params.append(priority)

    if current_step_id is not None:
        updates.append("current_step_id = ?")
        params.append(current_step_id)

    if not updates:
        conn.close()
        return {"success": False, "error": "No fields to update"}

    params.append(task_id)
    cursor.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()

    # Fetch updated task
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = row_to_dict(cursor.fetchone())

    conn.close()

    return {"success": True, "data": task, "message": f"Task {task_id} updated"}


def complete_task(task_id: str) -> Dict[str, Any]:
    """
    Mark a task as completed.

    Args:
        task_id: Task to complete

    Returns:
        dict with success status
    """
    return update_task(task_id, status="completed")


def abandon_task(task_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """
    Mark a task as abandoned (without guilt!).

    Sometimes tasks become irrelevant. That's okay.

    Args:
        task_id: Task to abandon
        reason: Optional reason (for future reference, not judgment)

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE tasks
        SET status = 'abandoned', completed_at = ?, abandon_reason = ?
        WHERE id = ?
    """, (datetime.now().isoformat(), reason, task_id))

    if cursor.rowcount == 0:
        conn.close()
        return {"success": False, "error": f"Task not found: {task_id}"}

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Task {task_id} marked as no longer needed",  # Note: positive framing
    }


def add_step(
    task_id: str,
    step_number: int,
    description: str,
    action_verb: Optional[str] = None,
    friction_notes: Optional[str] = None,
    estimated_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Add a step to a task.

    Args:
        task_id: Task to add step to
        step_number: Order in the task
        description: What to do
        action_verb: The action (find, send, call, etc.)
        friction_notes: Pre-identified friction
        estimated_minutes: Time estimate

    Returns:
        dict with step data
    """
    step_id = generate_id()

    conn = get_connection()
    cursor = conn.cursor()

    # Verify task exists
    cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Task not found: {task_id}"}

    cursor.execute("""
        INSERT INTO task_steps (id, task_id, step_number, description, action_verb, friction_notes, estimated_minutes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (step_id, task_id, step_number, description, action_verb, friction_notes, estimated_minutes))

    conn.commit()

    cursor.execute("SELECT * FROM task_steps WHERE id = ?", (step_id,))
    step = row_to_dict(cursor.fetchone())

    conn.close()

    return {"success": True, "data": step, "message": f"Step added with ID {step_id}"}


def complete_step(step_id: str) -> Dict[str, Any]:
    """
    Mark a step as completed and advance to next step.

    Args:
        step_id: Step to complete

    Returns:
        dict with next step info
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get step and its task
    cursor.execute("""
        SELECT s.*, t.id as task_id
        FROM task_steps s
        JOIN tasks t ON s.task_id = t.id
        WHERE s.id = ?
    """, (step_id,))
    step = row_to_dict(cursor.fetchone())

    if not step:
        conn.close()
        return {"success": False, "error": f"Step not found: {step_id}"}

    # Mark step complete
    cursor.execute("""
        UPDATE task_steps
        SET status = 'completed', completed_at = ?
        WHERE id = ?
    """, (datetime.now().isoformat(), step_id))

    # Find next pending step
    cursor.execute("""
        SELECT * FROM task_steps
        WHERE task_id = ? AND status = 'pending'
        ORDER BY step_number
        LIMIT 1
    """, (step["task_id"],))
    next_step = row_to_dict(cursor.fetchone())

    # Update task's current step
    if next_step:
        cursor.execute("""
            UPDATE tasks SET current_step_id = ? WHERE id = ?
        """, (next_step["id"], step["task_id"]))
    else:
        # No more steps - task may be complete
        cursor.execute("""
            UPDATE tasks SET current_step_id = NULL WHERE id = ?
        """, (step["task_id"],))

    conn.commit()
    conn.close()

    result = {
        "success": True,
        "message": "Step completed",  # Short, positive
        "data": {
            "completed_step_id": step_id,
            "next_step": next_step,
            "all_steps_complete": next_step is None,
        },
    }

    return result


def get_step(step_id: str) -> Dict[str, Any]:
    """
    Get step details by ID.

    Args:
        step_id: Step ID to fetch

    Returns:
        dict with step data
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM task_steps WHERE id = ?", (step_id,))
    step = row_to_dict(cursor.fetchone())

    conn.close()

    if not step:
        return {"success": False, "error": f"Step not found: {step_id}"}

    return {"success": True, "data": step}


def add_friction(
    friction_type: str,
    description: str,
    task_id: Optional[str] = None,
    step_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Record a friction point for a task or step.

    Args:
        friction_type: Type of friction (missing_info, phone_call, etc.)
        description: What the friction is
        task_id: Associated task
        step_id: Associated step

    Returns:
        dict with friction data
    """
    if friction_type not in FRICTION_TYPES:
        return {"success": False, "error": f"Invalid friction type. Must be one of: {FRICTION_TYPES}"}

    if not task_id and not step_id:
        return {"success": False, "error": "Must specify task_id or step_id"}

    friction_id = generate_id()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO task_friction (id, task_id, step_id, friction_type, description)
        VALUES (?, ?, ?, ?, ?)
    """, (friction_id, task_id, step_id, friction_type, description))

    conn.commit()

    cursor.execute("SELECT * FROM task_friction WHERE id = ?", (friction_id,))
    friction = row_to_dict(cursor.fetchone())

    conn.close()

    return {"success": True, "data": friction, "message": f"Friction point recorded"}


def delete_task(task_id: str) -> Dict[str, Any]:
    """
    Delete a task and all its steps/friction.

    Args:
        task_id: Task to delete

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Task not found: {task_id}"}

    # Cascading delete will handle steps and friction
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    return {"success": True, "message": f"Task {task_id} deleted"}


def main():
    parser = argparse.ArgumentParser(
        description="Task Manager - ADHD-friendly task CRUD operations"
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["create", "list", "get", "update", "complete", "abandon", "delete", "add-step", "complete-step", "get-step"],
        help="Action to perform",
    )

    # Task identification
    parser.add_argument("--task-id", help="Task ID for operations")
    parser.add_argument("--step-id", help="Step ID for step operations")
    parser.add_argument("--user", help="User ID")

    # Task creation/update
    parser.add_argument("--task", help="Raw task input text")
    parser.add_argument("--title", help="Task title")
    parser.add_argument("--description", help="Task description")
    parser.add_argument("--status", choices=TASK_STATUSES, help="Task status")
    parser.add_argument("--energy", choices=ENERGY_LEVELS, help="Energy level")
    parser.add_argument("--minutes", type=int, help="Estimated minutes")
    parser.add_argument("--priority", type=int, help="Priority (1-10)")
    parser.add_argument("--parent-id", help="Parent task ID for subtasks")
    parser.add_argument("--reason", help="Reason for abandoning")

    # Step creation
    parser.add_argument("--step-number", type=int, help="Step number in sequence")
    parser.add_argument("--step-desc", help="Step description")
    parser.add_argument("--action-verb", help="Action verb (find, send, call, etc.)")
    parser.add_argument("--friction-notes", help="Pre-identified friction")

    # List filters
    parser.add_argument("--include-subtasks", action="store_true", help="Include subtasks")
    parser.add_argument("--limit", type=int, default=50, help="Max results")
    parser.add_argument("--offset", type=int, default=0, help="Pagination offset")

    args = parser.parse_args()
    result = None

    if args.action == "create":
        if not args.user or not args.task:
            print(json.dumps({"success": False, "error": "--user and --task required for create"}))
            sys.exit(1)
        result = create_task(
            user_id=args.user,
            raw_input=args.task,
            title=args.title,
            description=args.description,
            parent_task_id=args.parent_id,
            energy_level=args.energy,
            estimated_minutes=args.minutes,
            priority=args.priority or 5,
        )

    elif args.action == "list":
        if not args.user:
            print(json.dumps({"success": False, "error": "--user required for list"}))
            sys.exit(1)
        result = list_tasks(
            user_id=args.user,
            status=args.status,
            parent_task_id=args.parent_id,
            energy_level=args.energy,
            include_subtasks=args.include_subtasks,
            limit=args.limit,
            offset=args.offset,
        )

    elif args.action == "get":
        if not args.task_id:
            print(json.dumps({"success": False, "error": "--task-id required for get"}))
            sys.exit(1)
        result = get_task(args.task_id)

    elif args.action == "update":
        if not args.task_id:
            print(json.dumps({"success": False, "error": "--task-id required for update"}))
            sys.exit(1)
        result = update_task(
            task_id=args.task_id,
            title=args.title,
            description=args.description,
            status=args.status,
            energy_level=args.energy,
            estimated_minutes=args.minutes,
            priority=args.priority,
        )

    elif args.action == "complete":
        if not args.task_id:
            print(json.dumps({"success": False, "error": "--task-id required for complete"}))
            sys.exit(1)
        result = complete_task(args.task_id)

    elif args.action == "abandon":
        if not args.task_id:
            print(json.dumps({"success": False, "error": "--task-id required for abandon"}))
            sys.exit(1)
        result = abandon_task(args.task_id, args.reason)

    elif args.action == "delete":
        if not args.task_id:
            print(json.dumps({"success": False, "error": "--task-id required for delete"}))
            sys.exit(1)
        result = delete_task(args.task_id)

    elif args.action == "add-step":
        if not args.task_id or not args.step_number or not args.step_desc:
            print(json.dumps({"success": False, "error": "--task-id, --step-number, and --step-desc required"}))
            sys.exit(1)
        result = add_step(
            task_id=args.task_id,
            step_number=args.step_number,
            description=args.step_desc,
            action_verb=args.action_verb,
            friction_notes=args.friction_notes,
            estimated_minutes=args.minutes,
        )

    elif args.action == "complete-step":
        if not args.step_id:
            print(json.dumps({"success": False, "error": "--step-id required for complete-step"}))
            sys.exit(1)
        result = complete_step(args.step_id)

    elif args.action == "get-step":
        if not args.step_id:
            print(json.dumps({"success": False, "error": "--step-id required for get-step"}))
            sys.exit(1)
        result = get_step(args.step_id)

    if result:
        print(json.dumps(result, indent=2, default=str))
        if not result.get("success"):
            sys.exit(1)


if __name__ == "__main__":
    main()
