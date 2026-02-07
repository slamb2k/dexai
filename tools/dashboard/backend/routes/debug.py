"""
Debug Routes for Dashboard

Provides diagnostic and debugging endpoints for the dashboard.
Admin-only access recommended.

Endpoints:
- GET /debug/system - System information and database sizes
- GET /debug/logs - Application logs with filtering
- POST /debug/tools/{tool_name} - Execute debug tools
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query

from tools.dashboard.backend.database import DB_PATH, get_db_connection


router = APIRouter(prefix="/debug")

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _get_uptime_seconds() -> int:
    """Get server uptime in seconds."""
    try:
        from tools.dashboard.backend.main import startup_time

        if startup_time:
            delta = datetime.now() - startup_time
            return int(delta.total_seconds())
    except Exception:
        pass
    return 0


def _get_database_sizes() -> dict:
    """Get sizes of all database files."""
    sizes = {}

    # Dashboard database
    if DB_PATH.exists():
        sizes["dashboard.db"] = os.path.getsize(DB_PATH)

    # Activity database
    activity_db = DATA_DIR / "activity.db"
    if activity_db.exists():
        sizes["activity.db"] = os.path.getsize(activity_db)

    # Memory database
    memory_db = DATA_DIR / "memory.db"
    if memory_db.exists():
        sizes["memory.db"] = os.path.getsize(memory_db)

    # Session database
    session_db = DATA_DIR / "sessions.db"
    if session_db.exists():
        sizes["sessions.db"] = os.path.getsize(session_db)

    # Security database
    security_db = DATA_DIR / "security.db"
    if security_db.exists():
        sizes["security.db"] = os.path.getsize(security_db)

    return sizes


def _get_connected_channels() -> list[str]:
    """Get list of connected channel adapters."""
    try:
        from tools.channels.router import get_router

        router_instance = get_router()
        return list(router_instance.adapters.keys())
    except Exception:
        return []


def _get_active_tasks_count() -> int:
    """Get count of active/running tasks."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count FROM dashboard_events
            WHERE event_type = 'task'
            AND details LIKE '%"status": "running"%'
            AND timestamp >= datetime('now', '-1 hour')
        """)
        count = cursor.fetchone()["count"]
        conn.close()
        return count
    except Exception:
        return 0


@router.get("/system")
async def get_system_info():
    """
    Get system information for debugging.

    Returns version, uptime, Python version, database sizes,
    connected channels, and environment information.
    """
    return {
        "version": "0.1.0",
        "uptime_seconds": _get_uptime_seconds(),
        "python_version": sys.version,
        "platform": sys.platform,
        "databases": _get_database_sizes(),
        "channels": _get_connected_channels(),
        "active_tasks": _get_active_tasks_count(),
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "debug_mode": os.environ.get("DEBUG", "false").lower() == "true",
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/logs")
async def get_logs(
    source: str = Query("all", description="Log source: all, backend, channels"),
    lines: int = Query(100, ge=1, le=1000, description="Number of log lines to return"),
    level: str = Query(None, description="Filter by log level: debug, info, warn, error"),
):
    """
    Get recent log entries.

    Reads from dashboard events table and formats as log entries.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build query based on filters
        query = """
            SELECT id, timestamp, event_type, summary, severity, channel, details
            FROM dashboard_events
            WHERE 1=1
        """
        params = []

        if source == "channels":
            query += " AND channel IS NOT NULL"
        elif source == "backend":
            query += " AND channel IS NULL"

        if level:
            level_map = {
                "debug": "info",
                "info": "info",
                "warn": "warning",
                "warning": "warning",
                "error": "error",
            }
            mapped_level = level_map.get(level.lower(), level.lower())
            query += " AND severity = ?"
            params.append(mapped_level)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(lines)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Format as log strings
        logs = []
        for row in rows:
            level_str = (row["severity"] or "INFO").upper()
            if level_str == "WARNING":
                level_str = "WARN"

            channel_str = f"[{row['channel']}] " if row["channel"] else ""
            log_entry = f"[{row['timestamp']}] {level_str:5} - {channel_str}{row['summary']}"
            logs.append(log_entry)

        return {"logs": logs, "total": len(logs), "source": source}

    except Exception as e:
        return {"logs": [f"[ERROR] Failed to fetch logs: {str(e)}"], "total": 1, "error": str(e)}


@router.get("/db")
async def query_database(
    table: str = Query(..., description="Table name to query"),
    limit: int = Query(10, ge=1, le=100, description="Number of rows to return"),
):
    """
    Query a database table (read-only).

    Returns columns and rows from the specified table.
    Limited to dashboard database tables for security.
    """
    # Whitelist of allowed tables
    allowed_tables = [
        "dashboard_events",
        "dashboard_metrics",
        "dashboard_settings",
        "chat_conversations",
        "chat_messages",
    ]

    if table not in allowed_tables:
        # Check memory database tables
        memory_tables = ["memory_entries", "contexts", "commitments"]
        if table in memory_tables:
            try:
                from tools.memory.memory_db import get_connection

                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(f"SELECT * FROM {table} LIMIT ?", (limit,))  # noqa: S608
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                conn.close()
                return {
                    "columns": columns,
                    "rows": [dict(row) for row in rows],
                    "table": table,
                    "total": len(rows),
                }
            except Exception as e:
                return {"columns": [], "rows": [], "error": str(e)}

        return {
            "columns": [],
            "rows": [],
            "error": f"Table '{table}' not in allowed list: {allowed_tables + memory_tables}",
        }

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table} LIMIT ?", (limit,))  # noqa: S608
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        conn.close()

        return {
            "columns": columns,
            "rows": [dict(row) for row in rows],
            "table": table,
            "total": len(rows),
        }
    except Exception as e:
        return {"columns": [], "rows": [], "error": str(e)}


@router.get("/metrics")
async def get_debug_metrics():
    """
    Get detailed debug metrics.

    Returns runtime metrics including memory usage, request counts,
    and performance statistics.
    """
    import resource

    metrics = {
        "timestamp": datetime.now().isoformat(),
        "memory": {},
        "requests": {},
        "performance": {},
    }

    # Memory usage
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        metrics["memory"] = {
            "max_rss_kb": usage.ru_maxrss,
            "shared_mem_kb": usage.ru_ixrss,
            "unshared_mem_kb": usage.ru_idrss,
        }
    except Exception:
        metrics["memory"] = {"error": "Unable to get memory stats"}

    # Request counts from dashboard events
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Requests in last hour
        cursor.execute("""
            SELECT COUNT(*) as count FROM dashboard_events
            WHERE timestamp >= datetime('now', '-1 hour')
        """)
        metrics["requests"]["last_hour"] = cursor.fetchone()["count"]

        # Requests today
        cursor.execute("""
            SELECT COUNT(*) as count FROM dashboard_events
            WHERE date(timestamp) = date('now')
        """)
        metrics["requests"]["today"] = cursor.fetchone()["count"]

        # Errors in last hour
        cursor.execute("""
            SELECT COUNT(*) as count FROM dashboard_events
            WHERE timestamp >= datetime('now', '-1 hour')
            AND severity = 'error'
        """)
        metrics["requests"]["errors_last_hour"] = cursor.fetchone()["count"]

        conn.close()
    except Exception as e:
        metrics["requests"] = {"error": str(e)}

    # Performance stats
    metrics["performance"] = {
        "uptime_seconds": _get_uptime_seconds(),
        "active_tasks": _get_active_tasks_count(),
    }

    return metrics


@router.post("/tools/{tool_name}")
async def run_debug_tool(tool_name: str):
    """
    Execute a debug tool.

    Available tools:
    - clear_cache: Clear temporary files and rate limiter state
    - test_connections: Test all service connections
    - reset_demo_data: Re-run database seeding
    """
    results = {"tool": tool_name, "success": False, "message": ""}

    try:
        if tool_name == "clear_cache":
            # Clear temp files
            temp_dir = PROJECT_ROOT / ".tmp"
            cleared = 0
            if temp_dir.exists():
                for f in temp_dir.glob("*"):
                    if f.is_file():
                        f.unlink()
                        cleared += 1

            results["success"] = True
            results["message"] = f"Cleared {cleared} temporary files"

        elif tool_name == "test_connections":
            connections = {}

            # Test database
            try:
                conn = get_db_connection()
                conn.execute("SELECT 1")
                conn.close()
                connections["database"] = {"status": "healthy"}
            except Exception as e:
                connections["database"] = {"status": "error", "error": str(e)}

            # Test memory database
            try:
                from tools.memory.memory_db import get_connection

                conn = get_connection()
                conn.execute("SELECT 1")
                conn.close()
                connections["memory"] = {"status": "healthy"}
            except Exception as e:
                connections["memory"] = {"status": "unavailable", "error": str(e)}

            # Test channel router
            try:
                from tools.channels.router import get_router

                router_instance = get_router()
                connections["channels"] = {
                    "status": "healthy" if router_instance.adapters else "no_adapters",
                    "adapters": list(router_instance.adapters.keys()),
                }
            except Exception as e:
                connections["channels"] = {"status": "error", "error": str(e)}

            results["success"] = True
            results["results"] = connections
            results["message"] = "Connection tests completed"

        elif tool_name == "reset_demo_data":
            try:
                from tools.dashboard.backend import seed

                seed_results = seed.seed_database(force=True)
                results["success"] = seed_results.get("success", False)
                results["message"] = seed_results.get("message", "Seed completed")
            except ImportError:
                results["message"] = "Seed module not available"
            except Exception as e:
                results["message"] = f"Seed failed: {str(e)}"

        else:
            results["message"] = f"Unknown tool: {tool_name}"

    except Exception as e:
        results["message"] = f"Tool execution failed: {str(e)}"

    return results
