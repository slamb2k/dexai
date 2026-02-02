"""
Tool: Cron Scheduler
Purpose: Manage scheduled jobs with cron expressions

Features:
- Create/update/delete scheduled jobs
- Cron expression parsing and next-run calculation
- Execution history tracking
- Retry logic with exponential backoff
- Cost and timeout limits

Usage:
    python tools/automation/scheduler.py --action create --name morning_briefing \
        --type cron --schedule "0 7 * * *" --task "Generate morning briefing"
    python tools/automation/scheduler.py --action list
    python tools/automation/scheduler.py --action run --name morning_briefing
    python tools/automation/scheduler.py --action enable --name morning_briefing
    python tools/automation/scheduler.py --action disable --name morning_briefing
    python tools/automation/scheduler.py --action executions --job morning_briefing
    python tools/automation/scheduler.py --action due

Dependencies:
    - croniter>=2.0.0
    - pyyaml
"""

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.automation import CONFIG_PATH, DB_PATH


# Try to import croniter for cron expression parsing
try:
    from croniter import croniter

    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    default_config = {
        "cron": {
            "enabled": True,
            "poll_interval_seconds": 60,
            "default_timeout": 120,
            "default_cost_limit": 0.50,
            "max_concurrent_jobs": 3,
            "retry": {
                "max_attempts": 3,
                "initial_delay_seconds": 60,
                "backoff_multiplier": 2.0,
                "max_delay_seconds": 3600,
            },
            "timezone": "UTC",
        }
    }

    if not CONFIG_PATH.exists():
        return default_config

    try:
        import yaml

        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        return config if config else default_config
    except Exception:
        return default_config


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            job_type TEXT CHECK(job_type IN ('cron', 'heartbeat', 'trigger')) NOT NULL,
            schedule TEXT,
            task TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            timeout_seconds INTEGER DEFAULT 120,
            cost_limit REAL DEFAULT 0.50,
            retry_count INTEGER DEFAULT 3,
            retry_delay_seconds INTEGER DEFAULT 60,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_run DATETIME,
            next_run DATETIME,
            metadata TEXT
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_enabled ON jobs(enabled)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_next_run ON jobs(next_run)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type)")

    # Executions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS executions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            status TEXT CHECK(status IN ('pending', 'running', 'completed', 'failed', 'timeout', 'cancelled')) NOT NULL,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            duration_ms INTEGER,
            cost_usd REAL DEFAULT 0,
            output TEXT,
            error TEXT,
            retry_attempt INTEGER DEFAULT 0,
            triggered_by TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_job ON executions(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_started ON executions(started_at)")

    conn.commit()
    return conn


def calculate_next_run(schedule: str, base_time: datetime | None = None) -> datetime | None:
    """Calculate next run time from cron expression."""
    if not schedule:
        return None

    if not CRONITER_AVAILABLE:
        # Fallback: just add 1 hour
        return (base_time or datetime.now()) + timedelta(hours=1)

    try:
        base = base_time or datetime.now()
        cron = croniter(schedule, base)
        return cron.get_next(datetime)
    except Exception:
        return None


def validate_cron_expression(schedule: str) -> dict[str, Any]:
    """Validate a cron expression."""
    if not schedule:
        return {"valid": False, "error": "Empty schedule"}

    if not CRONITER_AVAILABLE:
        return {"valid": True, "warning": "croniter not installed, schedule not validated"}

    try:
        cron = croniter(schedule)
        next_run = cron.get_next(datetime)
        return {"valid": True, "next_run": next_run.isoformat(), "expression": schedule}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def create_job(
    name: str,
    job_type: str,
    task: str,
    schedule: str | None = None,
    timeout_seconds: int | None = None,
    cost_limit: float | None = None,
    retry_count: int | None = None,
    retry_delay_seconds: int | None = None,
    metadata: dict | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """
    Create a new scheduled job.

    Args:
        name: Unique job name
        job_type: 'cron', 'heartbeat', or 'trigger'
        task: Task description/prompt to execute
        schedule: Cron expression (required for cron jobs)
        timeout_seconds: Max execution time
        cost_limit: Max cost in USD
        retry_count: Number of retry attempts
        retry_delay_seconds: Initial retry delay
        metadata: Additional job metadata
        enabled: Whether job is active

    Returns:
        dict with success status and job details
    """
    config = load_config()
    cron_config = config.get("cron", {})

    # Validate job type
    if job_type not in ("cron", "heartbeat", "trigger"):
        return {
            "success": False,
            "error": f"Invalid job_type: {job_type}. Must be cron, heartbeat, or trigger",
        }

    # Validate schedule for cron jobs
    if job_type == "cron":
        if not schedule:
            return {"success": False, "error": "Schedule required for cron jobs"}
        validation = validate_cron_expression(schedule)
        if not validation.get("valid"):
            return {
                "success": False,
                "error": f"Invalid cron expression: {validation.get('error')}",
            }

    # Apply defaults from config
    timeout_seconds = timeout_seconds or cron_config.get("default_timeout", 120)
    cost_limit = (
        cost_limit if cost_limit is not None else cron_config.get("default_cost_limit", 0.50)
    )
    retry_count = (
        retry_count
        if retry_count is not None
        else cron_config.get("retry", {}).get("max_attempts", 3)
    )
    retry_delay_seconds = retry_delay_seconds or cron_config.get("retry", {}).get(
        "initial_delay_seconds", 60
    )

    job_id = str(uuid.uuid4())
    next_run = calculate_next_run(schedule) if schedule else None

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO jobs (id, name, job_type, schedule, task, enabled,
                             timeout_seconds, cost_limit, retry_count, retry_delay_seconds,
                             next_run, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                job_id,
                name,
                job_type,
                schedule,
                task,
                1 if enabled else 0,
                timeout_seconds,
                cost_limit,
                retry_count,
                retry_delay_seconds,
                next_run.isoformat() if next_run else None,
                json.dumps(metadata) if metadata else None,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return {"success": False, "error": f"Job with name '{name}' already exists"}

    conn.close()

    # Log to audit
    try:
        from tools.security import audit

        audit.log_event(
            event_type="system",
            action="job_created",
            resource=f"job:{name}",
            status="success",
            details={"job_id": job_id, "job_type": job_type},
        )
    except Exception:
        pass

    return {
        "success": True,
        "job_id": job_id,
        "name": name,
        "job_type": job_type,
        "schedule": schedule,
        "next_run": next_run.isoformat() if next_run else None,
        "message": f"Job '{name}' created successfully",
    }


def get_job(job_id_or_name: str) -> dict[str, Any] | None:
    """Get a job by ID or name."""
    conn = get_connection()
    cursor = conn.cursor()

    # Try by ID first, then by name
    cursor.execute("SELECT * FROM jobs WHERE id = ? OR name = ?", (job_id_or_name, job_id_or_name))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row["id"],
        "name": row["name"],
        "job_type": row["job_type"],
        "schedule": row["schedule"],
        "task": row["task"],
        "enabled": bool(row["enabled"]),
        "timeout_seconds": row["timeout_seconds"],
        "cost_limit": row["cost_limit"],
        "retry_count": row["retry_count"],
        "retry_delay_seconds": row["retry_delay_seconds"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_run": row["last_run"],
        "next_run": row["next_run"],
        "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
    }


def list_jobs(job_type: str | None = None, enabled: bool | None = None) -> list[dict[str, Any]]:
    """List all jobs, optionally filtered."""
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM jobs WHERE 1=1"
    params = []

    if job_type:
        query += " AND job_type = ?"
        params.append(job_type)

    if enabled is not None:
        query += " AND enabled = ?"
        params.append(1 if enabled else 0)

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    jobs = []
    for row in rows:
        jobs.append(
            {
                "id": row["id"],
                "name": row["name"],
                "job_type": row["job_type"],
                "schedule": row["schedule"],
                "task": row["task"][:100] + "..." if len(row["task"]) > 100 else row["task"],
                "enabled": bool(row["enabled"]),
                "last_run": row["last_run"],
                "next_run": row["next_run"],
            }
        )

    return jobs


def update_job(job_id: str, **updates) -> dict[str, Any]:
    """Update job properties."""
    job = get_job(job_id)
    if not job:
        return {"success": False, "error": f"Job '{job_id}' not found"}

    allowed_fields = {
        "name",
        "schedule",
        "task",
        "enabled",
        "timeout_seconds",
        "cost_limit",
        "retry_count",
        "retry_delay_seconds",
        "metadata",
    }

    # Filter to allowed fields
    valid_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not valid_updates:
        return {"success": False, "error": "No valid fields to update"}

    # Validate schedule if being updated
    if "schedule" in valid_updates and job["job_type"] == "cron":
        validation = validate_cron_expression(valid_updates["schedule"])
        if not validation.get("valid"):
            return {
                "success": False,
                "error": f"Invalid cron expression: {validation.get('error')}",
            }

    # Build update query
    set_clauses = []
    params = []
    for field, value in valid_updates.items():
        if field == "metadata":
            value = json.dumps(value) if value else None
        elif field == "enabled":
            value = 1 if value else 0
        set_clauses.append(f"{field} = ?")
        params.append(value)

    set_clauses.append("updated_at = CURRENT_TIMESTAMP")

    # Recalculate next_run if schedule changed
    if "schedule" in valid_updates:
        next_run = calculate_next_run(valid_updates["schedule"])
        set_clauses.append("next_run = ?")
        params.append(next_run.isoformat() if next_run else None)

    params.append(job["id"])

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id = ?", params)
    conn.commit()
    conn.close()

    return {
        "success": True,
        "job_id": job["id"],
        "updated_fields": list(valid_updates.keys()),
        "message": f"Job '{job['name']}' updated",
    }


def delete_job(job_id: str) -> dict[str, Any]:
    """Delete a job and its execution history."""
    job = get_job(job_id)
    if not job:
        return {"success": False, "error": f"Job '{job_id}' not found"}

    conn = get_connection()
    cursor = conn.cursor()

    # Delete executions first (foreign key)
    cursor.execute("DELETE FROM executions WHERE job_id = ?", (job["id"],))
    cursor.execute("DELETE FROM jobs WHERE id = ?", (job["id"],))

    conn.commit()
    conn.close()

    # Log to audit
    try:
        from tools.security import audit

        audit.log_event(
            event_type="system",
            action="job_deleted",
            resource=f"job:{job['name']}",
            status="success",
        )
    except Exception:
        pass

    return {
        "success": True,
        "job_id": job["id"],
        "name": job["name"],
        "message": f"Job '{job['name']}' deleted",
    }


def enable_job(job_id: str) -> dict[str, Any]:
    """Enable a job."""
    job = get_job(job_id)
    if not job:
        return {"success": False, "error": f"Job '{job_id}' not found"}

    # Recalculate next_run when enabling
    next_run = calculate_next_run(job["schedule"]) if job["schedule"] else None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE jobs SET enabled = 1, updated_at = CURRENT_TIMESTAMP, next_run = ?
        WHERE id = ?
    """,
        (next_run.isoformat() if next_run else None, job["id"]),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "job_id": job["id"],
        "name": job["name"],
        "next_run": next_run.isoformat() if next_run else None,
        "message": f"Job '{job['name']}' enabled",
    }


def disable_job(job_id: str) -> dict[str, Any]:
    """Disable a job."""
    job = get_job(job_id)
    if not job:
        return {"success": False, "error": f"Job '{job_id}' not found"}

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE jobs SET enabled = 0, updated_at = CURRENT_TIMESTAMP, next_run = NULL
        WHERE id = ?
    """,
        (job["id"],),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "job_id": job["id"],
        "name": job["name"],
        "message": f"Job '{job['name']}' disabled",
    }


def get_due_jobs() -> list[dict[str, Any]]:
    """Get all jobs that are due to run."""
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute(
        """
        SELECT * FROM jobs
        WHERE enabled = 1
        AND job_type = 'cron'
        AND next_run IS NOT NULL
        AND next_run <= ?
        ORDER BY next_run ASC
    """,
        (now,),
    )

    rows = cursor.fetchall()
    conn.close()

    jobs = []
    for row in rows:
        jobs.append(
            {
                "id": row["id"],
                "name": row["name"],
                "job_type": row["job_type"],
                "schedule": row["schedule"],
                "task": row["task"],
                "timeout_seconds": row["timeout_seconds"],
                "cost_limit": row["cost_limit"],
                "next_run": row["next_run"],
            }
        )

    return jobs


def create_execution(job_id: str, triggered_by: str = "schedule", retry_attempt: int = 0) -> str:
    """Create a new execution record and return its ID."""
    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job '{job_id}' not found")

    exec_id = str(uuid.uuid4())

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO executions (id, job_id, status, triggered_by, retry_attempt)
        VALUES (?, ?, 'pending', ?, ?)
    """,
        (exec_id, job["id"], triggered_by, retry_attempt),
    )

    conn.commit()
    conn.close()

    return exec_id


def update_execution(exec_id: str, **updates) -> dict[str, Any]:
    """Update execution status and details."""
    conn = get_connection()
    cursor = conn.cursor()

    # Verify execution exists
    cursor.execute("SELECT id FROM executions WHERE id = ?", (exec_id,))
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Execution '{exec_id}' not found"}

    allowed_fields = {"status", "completed_at", "duration_ms", "cost_usd", "output", "error"}
    valid_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not valid_updates:
        conn.close()
        return {"success": False, "error": "No valid fields to update"}

    set_clauses = [f"{k} = ?" for k in valid_updates]
    params = list(valid_updates.values())
    params.append(exec_id)

    cursor.execute(f"UPDATE executions SET {', '.join(set_clauses)} WHERE id = ?", params)
    conn.commit()
    conn.close()

    return {"success": True, "execution_id": exec_id}


def start_execution(exec_id: str) -> dict[str, Any]:
    """Mark execution as running."""
    return update_execution(exec_id, status="running")


def complete_execution(
    exec_id: str, output: str | None = None, cost_usd: float = 0, duration_ms: int | None = None
) -> dict[str, Any]:
    """Mark execution as completed successfully."""
    return update_execution(
        exec_id,
        status="completed",
        completed_at=datetime.now().isoformat(),
        output=output,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
    )


def fail_execution(exec_id: str, error: str, duration_ms: int | None = None) -> dict[str, Any]:
    """Mark execution as failed."""
    return update_execution(
        exec_id,
        status="failed",
        completed_at=datetime.now().isoformat(),
        error=error,
        duration_ms=duration_ms,
    )


def list_executions(
    job_id: str | None = None, status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """List execution history."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT e.*, j.name as job_name
        FROM executions e
        JOIN jobs j ON e.job_id = j.id
        WHERE 1=1
    """
    params = []

    if job_id:
        # Allow job_id or job_name
        job = get_job(job_id)
        if job:
            query += " AND e.job_id = ?"
            params.append(job["id"])

    if status:
        query += " AND e.status = ?"
        params.append(status)

    query += " ORDER BY e.started_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    executions = []
    for row in rows:
        executions.append(
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "job_name": row["job_name"],
                "status": row["status"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "duration_ms": row["duration_ms"],
                "cost_usd": row["cost_usd"],
                "output": row["output"][:200] + "..."
                if row["output"] and len(row["output"]) > 200
                else row["output"],
                "error": row["error"],
                "retry_attempt": row["retry_attempt"],
                "triggered_by": row["triggered_by"],
            }
        )

    return executions


def mark_job_run(job_id: str) -> dict[str, Any]:
    """Update job's last_run and calculate next_run."""
    job = get_job(job_id)
    if not job:
        return {"success": False, "error": f"Job '{job_id}' not found"}

    now = datetime.now()
    next_run = calculate_next_run(job["schedule"], now) if job["schedule"] else None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE jobs SET last_run = ?, next_run = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """,
        (now.isoformat(), next_run.isoformat() if next_run else None, job["id"]),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "job_id": job["id"],
        "last_run": now.isoformat(),
        "next_run": next_run.isoformat() if next_run else None,
    }


def run_job(job_id: str, triggered_by: str = "manual") -> dict[str, Any]:
    """
    Execute a job immediately.

    This creates an execution record but does not actually run the task.
    The actual execution should be handled by the runner.
    """
    job = get_job(job_id)
    if not job:
        return {"success": False, "error": f"Job '{job_id}' not found"}

    exec_id = create_execution(job["id"], triggered_by=triggered_by)

    return {
        "success": True,
        "execution_id": exec_id,
        "job_id": job["id"],
        "job_name": job["name"],
        "task": job["task"],
        "message": f"Execution created for job '{job['name']}'",
    }


def get_stats() -> dict[str, Any]:
    """Get scheduler statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    # Job counts
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM jobs WHERE enabled = 1")
    enabled_jobs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM jobs WHERE job_type = ?", ("cron",))
    cron_jobs = cursor.fetchone()[0]

    # Execution counts
    cursor.execute("SELECT COUNT(*) FROM executions")
    total_executions = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM executions WHERE started_at > datetime('now', '-24 hours')"
    )
    executions_24h = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM executions WHERE status = 'failed' AND started_at > datetime('now', '-24 hours')"
    )
    failures_24h = cursor.fetchone()[0]

    # Running executions
    cursor.execute("SELECT COUNT(*) FROM executions WHERE status = 'running'")
    running = cursor.fetchone()[0]

    conn.close()

    return {
        "success": True,
        "jobs": {"total": total_jobs, "enabled": enabled_jobs, "cron": cron_jobs},
        "executions": {
            "total": total_executions,
            "last_24h": executions_24h,
            "failures_24h": failures_24h,
            "running": running,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Cron Scheduler")
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "create",
            "get",
            "list",
            "update",
            "delete",
            "enable",
            "disable",
            "run",
            "due",
            "executions",
            "stats",
            "validate",
        ],
        help="Action to perform",
    )

    # Job identifiers
    parser.add_argument("--name", help="Job name")
    parser.add_argument("--job", help="Job ID or name")
    parser.add_argument("--id", help="Job or execution ID")

    # Job properties
    parser.add_argument("--type", choices=["cron", "heartbeat", "trigger"], help="Job type")
    parser.add_argument("--schedule", help="Cron expression")
    parser.add_argument("--task", help="Task description/prompt")
    parser.add_argument("--timeout", type=int, help="Timeout in seconds")
    parser.add_argument("--cost-limit", type=float, help="Cost limit in USD")
    parser.add_argument("--retry-count", type=int, help="Number of retries")
    parser.add_argument("--enabled", type=bool, default=True, help="Enable job")

    # Filters
    parser.add_argument("--status", help="Filter by status")
    parser.add_argument("--limit", type=int, default=50, help="Result limit")

    args = parser.parse_args()
    result = None

    if args.action == "create":
        if not args.name or not args.type or not args.task:
            print("Error: --name, --type, and --task required for create")
            sys.exit(1)
        result = create_job(
            name=args.name,
            job_type=args.type,
            task=args.task,
            schedule=args.schedule,
            timeout_seconds=args.timeout,
            cost_limit=args.cost_limit,
            retry_count=args.retry_count,
            enabled=args.enabled,
        )

    elif args.action == "get":
        job_id = args.job or args.name or args.id
        if not job_id:
            print("Error: --job, --name, or --id required")
            sys.exit(1)
        job = get_job(job_id)
        result = (
            {"success": True, "job": job} if job else {"success": False, "error": "Job not found"}
        )

    elif args.action == "list":
        jobs = list_jobs(
            job_type=args.type, enabled=args.enabled if hasattr(args, "enabled") else None
        )
        result = {"success": True, "jobs": jobs, "count": len(jobs)}

    elif args.action == "update":
        job_id = args.job or args.name or args.id
        if not job_id:
            print("Error: --job, --name, or --id required")
            sys.exit(1)
        updates = {}
        if args.schedule:
            updates["schedule"] = args.schedule
        if args.task:
            updates["task"] = args.task
        if args.timeout:
            updates["timeout_seconds"] = args.timeout
        if args.cost_limit:
            updates["cost_limit"] = args.cost_limit
        result = update_job(job_id, **updates)

    elif args.action == "delete":
        job_id = args.job or args.name or args.id
        if not job_id:
            print("Error: --job, --name, or --id required")
            sys.exit(1)
        result = delete_job(job_id)

    elif args.action == "enable":
        job_id = args.job or args.name or args.id
        if not job_id:
            print("Error: --job, --name, or --id required")
            sys.exit(1)
        result = enable_job(job_id)

    elif args.action == "disable":
        job_id = args.job or args.name or args.id
        if not job_id:
            print("Error: --job, --name, or --id required")
            sys.exit(1)
        result = disable_job(job_id)

    elif args.action == "run":
        job_id = args.job or args.name or args.id
        if not job_id:
            print("Error: --job, --name, or --id required")
            sys.exit(1)
        result = run_job(job_id, triggered_by="manual")

    elif args.action == "due":
        jobs = get_due_jobs()
        result = {"success": True, "due_jobs": jobs, "count": len(jobs)}

    elif args.action == "executions":
        executions = list_executions(
            job_id=args.job or args.name, status=args.status, limit=args.limit
        )
        result = {"success": True, "executions": executions, "count": len(executions)}

    elif args.action == "stats":
        result = get_stats()

    elif args.action == "validate":
        if not args.schedule:
            print("Error: --schedule required for validate")
            sys.exit(1)
        result = validate_cron_expression(args.schedule)
        result["success"] = result.get("valid", False)

    # Output
    if result.get("success"):
        print(f"OK {result.get('message', 'Success')}")
    else:
        print(f"ERROR {result.get('error')}")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
