"""
Tasks Route - Task List and Detail Views

Provides endpoints for viewing task execution history:
- List tasks with filters (status, channel, date range)
- Get detailed task information
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from tools.dashboard.backend.models import (
    TaskDetail,
    TaskListResponse,
    TaskStatus,
    TaskSummary,
)


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
