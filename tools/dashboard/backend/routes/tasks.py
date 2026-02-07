"""
Tasks Route - Task List and Detail Views

Provides endpoints for viewing task execution history:
- List tasks with filters (status, channel, date range)
- Get detailed task information
- Get current task
- Task actions: stuck, decompose, skip
- Create new tasks
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from tools.dashboard.backend.models import (
    TaskDetail,
    TaskListResponse,
    TaskStatus,
    TaskSummary,
)

logger = logging.getLogger(__name__)


router = APIRouter()

# Task database path (from existing activity.db)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
ACTIVITY_DB = PROJECT_ROOT / "data" / "activity.db"


def get_task_connection() -> sqlite3.Connection:
    """Get connection to activity database."""
    conn = sqlite3.connect(str(ACTIVITY_DB))
    conn.row_factory = sqlite3.Row
    return conn


def parse_task_status(status_str: str) -> TaskStatus:
    """Convert database status string to TaskStatus enum."""
    status_map = {
        "pending": TaskStatus.PENDING,
        "running": TaskStatus.RUNNING,
        "in_progress": TaskStatus.RUNNING,
        "completed": TaskStatus.COMPLETED,
        "done": TaskStatus.COMPLETED,
        "failed": TaskStatus.FAILED,
        "error": TaskStatus.FAILED,
        "cancelled": TaskStatus.CANCELLED,
        "canceled": TaskStatus.CANCELLED,
    }
    return status_map.get(status_str.lower(), TaskStatus.PENDING)


# =============================================================================
# Current Task Endpoint (must be before /{task_id} to avoid route conflict)
# =============================================================================


@router.get("/current")
async def get_current_task():
    """
    Get the current active task (the ONE thing to focus on).

    Returns the highest priority pending task or None if all done.
    """
    try:
        conn = get_task_connection()
        cursor = conn.cursor()

        # Get first pending/running task
        cursor.execute(
            """
            SELECT * FROM tasks
            WHERE status IN ('pending', 'running', 'in_progress')
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {
                "current_task": None,
                "message": "All done! No tasks waiting.",
            }

        return {
            "current_task": {
                "id": row["id"],
                "title": row["request"] or "No title",
                "description": row["summary"] if row["summary"] else None,
                "status": row["status"],
                "energy_required": "medium",  # Would come from metadata
                "estimated_time": None,
                "category": row["source"],
                "created_at": row["created_at"],
            }
        }

    except sqlite3.OperationalError:
        return {"current_task": None, "message": "No tasks available"}


@router.get("/friction")
async def get_detected_friction():
    """
    Get list of detected friction/blockers across tasks.

    Proactively identifies what might be blocking progress.
    """
    friction_items = []

    try:
        # Check for tasks that have been pending too long
        conn = get_task_connection()
        cursor = conn.cursor()

        # Find tasks pending for more than 1 day
        cursor.execute(
            """
            SELECT * FROM tasks
            WHERE status IN ('pending', 'running')
            AND created_at < datetime('now', '-1 day')
            ORDER BY created_at ASC
            LIMIT 5
            """
        )

        for row in cursor.fetchall():
            friction_items.append(
                FrictionItem(
                    task_id=row["id"],
                    task_title=row["request"] or "Task",
                    blocker="This task has been waiting - might need attention or breakdown",
                    suggested_action="Consider breaking into smaller steps",
                    confidence=0.7,
                )
            )

        conn.close()

    except Exception as e:
        logger.warning(f"Error detecting friction: {e}")

    return FrictionResponse(
        friction_items=friction_items,
        total=len(friction_items),
    )


# =============================================================================
# Task List
# =============================================================================


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: str | None = Query(None, description="Filter by status"),
    channel: str | None = Query(None, description="Filter by channel"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    search: str | None = Query(None, description="Search in request text"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """
    List tasks with optional filters.

    Supports pagination and filtering by status, channel, date range, and search text.
    """
    try:
        conn = get_task_connection()
        cursor = conn.cursor()

        # Build query
        query = "SELECT * FROM tasks WHERE 1=1"
        count_query = "SELECT COUNT(*) as count FROM tasks WHERE 1=1"
        params = []

        if status:
            # Map input status to possible DB values
            status_values = []
            if status.lower() == "running":
                status_values = ["running", "in_progress"]
            elif status.lower() == "completed":
                status_values = ["completed", "done"]
            elif status.lower() == "failed":
                status_values = ["failed", "error"]
            else:
                status_values = [status]

            placeholders = ",".join(["?" for _ in status_values])
            query += f" AND status IN ({placeholders})"
            count_query += f" AND status IN ({placeholders})"
            params.extend(status_values)

        if channel:
            query += " AND source = ?"
            count_query += " AND source = ?"
            params.append(channel)

        if start_date:
            query += " AND created_at >= ?"
            count_query += " AND created_at >= ?"
            params.append(start_date)

        if end_date:
            query += " AND created_at <= ?"
            count_query += " AND created_at <= ?"
            params.append(end_date)

        if search:
            query += " AND request LIKE ?"
            count_query += " AND request LIKE ?"
            params.append(f"%{search}%")

        # Get total count
        cursor.execute(count_query, params)
        total = cursor.fetchone()["count"]

        # Add pagination
        offset = (page - 1) * page_size
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([page_size, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to TaskSummary objects
        tasks = []
        for row in rows:
            # Calculate duration if completed
            duration = None
            if row["completed_at"] and row["created_at"]:
                try:
                    created = datetime.fromisoformat(row["created_at"])
                    completed = datetime.fromisoformat(row["completed_at"])
                    duration = (completed - created).total_seconds()
                except (ValueError, TypeError):
                    pass

            tasks.append(
                TaskSummary(
                    id=row["id"],
                    request=row["request"] or "No request",
                    status=parse_task_status(row["status"]),
                    channel=row["source"],
                    created_at=datetime.fromisoformat(row["created_at"])
                    if row["created_at"]
                    else datetime.now(),
                    completed_at=datetime.fromisoformat(row["completed_at"])
                    if row["completed_at"]
                    else None,
                    duration_seconds=duration,
                    cost_usd=None,  # Would need cost tracking
                )
            )

        return TaskListResponse(
            tasks=tasks,
            total=total,
            page=page,
            page_size=page_size,
            has_more=(offset + len(tasks)) < total,
        )

    except sqlite3.OperationalError:
        # Database doesn't exist yet
        return TaskListResponse(tasks=[], total=0, page=page, page_size=page_size, has_more=False)


@router.get("/{task_id}", response_model=TaskDetail)
async def get_task(task_id: str):
    """
    Get detailed information about a specific task.

    Args:
        task_id: Task ID to retrieve
    """
    try:
        conn = get_task_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        # Calculate duration
        duration = None
        if row["completed_at"] and row["created_at"]:
            try:
                created = datetime.fromisoformat(row["created_at"])
                completed = datetime.fromisoformat(row["completed_at"])
                duration = (completed - created).total_seconds()
            except (ValueError, TypeError):
                pass

        return TaskDetail(
            id=row["id"],
            request=row["request"] or "No request",
            status=parse_task_status(row["status"]),
            channel=row["source"],
            created_at=datetime.fromisoformat(row["created_at"])
            if row["created_at"]
            else datetime.now(),
            completed_at=datetime.fromisoformat(row["completed_at"])
            if row["completed_at"]
            else None,
            duration_seconds=duration,
            cost_usd=None,
            response=row["summary"] if row["summary"] else None,
            tools_used=[],  # Would need to track this
            tokens_in=None,
            tokens_out=None,
            error_message=None,
            metadata={},
        )

    except sqlite3.OperationalError:
        raise HTTPException(status_code=404, detail="Task database not found")


# =============================================================================
# Request Models
# =============================================================================


class CreateTaskRequest(BaseModel):
    """Request model for creating a new task."""

    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    energy_required: str = "medium"  # low, medium, high
    estimated_time: Optional[str] = None
    category: Optional[str] = None


class TaskActionResponse(BaseModel):
    """Response for task actions."""

    success: bool
    task_id: str
    action: str
    message: Optional[str] = None
    data: Optional[dict] = None


class FrictionItem(BaseModel):
    """Detected friction/blocker for a task."""

    task_id: str
    task_title: str
    blocker: str
    suggested_action: Optional[str] = None
    confidence: float = 0.0


class FrictionResponse(BaseModel):
    """Response for friction detection."""

    friction_items: list[FrictionItem]
    total: int


@router.post("", response_model=TaskActionResponse)
async def create_task(request: CreateTaskRequest):
    """
    Create a new task.

    The task will be added to the pending queue.
    """
    try:
        conn = get_task_connection()
        cursor = conn.cursor()

        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO tasks (id, source, request, status, created_at, summary)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                request.category or "dashboard",
                request.title,
                "pending",
                now,
                request.description,
            ),
        )
        conn.commit()
        conn.close()

        return TaskActionResponse(
            success=True,
            task_id=task_id,
            action="create",
            message="Task created successfully",
        )

    except sqlite3.OperationalError as e:
        logger.error(f"Database error creating task: {e}")
        raise HTTPException(status_code=500, detail="Failed to create task")


@router.post("/{task_id}/stuck", response_model=TaskActionResponse)
async def mark_task_stuck(task_id: str):
    """
    Mark a task as stuck and trigger friction detection.

    This will analyze the task and identify potential blockers,
    then suggest actions to resolve them.
    """
    try:
        # First verify task exists
        conn = get_task_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        task_title = row["request"] or "Task"

        # Try to use friction solver
        friction_data = None
        try:
            from tools.agent.mcp.task_tools import solve_friction

            result = solve_friction(task_id=task_id, task_description=task_title)
            if result.get("success"):
                friction_data = result.get("friction", {})
        except ImportError:
            # Friction solver not available, provide generic response
            friction_data = {
                "blocker": "Unable to analyze - please describe what's blocking you",
                "suggestions": ["Break the task into smaller steps", "Ask for clarification"],
            }
        except Exception as e:
            logger.warning(f"Friction solver error: {e}")
            friction_data = {"blocker": "Analysis failed", "error": str(e)}

        return TaskActionResponse(
            success=True,
            task_id=task_id,
            action="stuck",
            message="Friction analysis completed",
            data=friction_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking task stuck: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/decompose", response_model=TaskActionResponse)
async def decompose_task(task_id: str):
    """
    Decompose a task into smaller subtasks.

    Uses LLM to break down complex tasks into actionable steps.
    """
    try:
        # Verify task exists
        conn = get_task_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        task_title = row["request"] or "Task"
        task_description = row.get("summary", "")

        # Try to use task decomposition
        subtasks = None
        try:
            from tools.agent.mcp.task_tools import decompose_task as do_decompose

            result = do_decompose(
                task_description=f"{task_title}. {task_description}".strip(),
                max_subtasks=5,
            )
            if result.get("success"):
                subtasks = result.get("subtasks", [])
        except ImportError:
            # Decomposition not available, provide generic breakdown
            subtasks = [
                {"title": f"Step 1: Understand {task_title}", "energy": "low"},
                {"title": f"Step 2: Plan approach", "energy": "medium"},
                {"title": f"Step 3: Execute", "energy": "high"},
            ]
        except Exception as e:
            logger.warning(f"Decomposition error: {e}")
            subtasks = []

        return TaskActionResponse(
            success=True,
            task_id=task_id,
            action="decompose",
            message=f"Task broken into {len(subtasks)} subtasks",
            data={"subtasks": subtasks},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error decomposing task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{task_id}/skip")
async def skip_task(task_id: str):
    """
    Skip a task for now (move to end of queue).

    The task remains pending but won't be shown as current.
    No guilt language - just moving on for now.
    """
    try:
        conn = get_task_connection()
        cursor = conn.cursor()

        # Verify exists
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Task not found")

        # Update timestamp to move to end of queue
        cursor.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task_id),
        )
        conn.commit()
        conn.close()

        return {
            "success": True,
            "task_id": task_id,
            "action": "skip",
            "message": "Task moved to later",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error skipping task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{task_id}/complete")
async def complete_task(task_id: str):
    """
    Mark a task as completed.
    """
    try:
        conn = get_task_connection()
        cursor = conn.cursor()

        # Verify exists
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Task not found")

        # Mark completed
        cursor.execute(
            "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
            ("completed", datetime.now().isoformat(), task_id),
        )
        conn.commit()
        conn.close()

        return {
            "success": True,
            "task_id": task_id,
            "action": "complete",
            "message": "Nice work!",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing task: {e}")
        raise HTTPException(status_code=500, detail=str(e))
