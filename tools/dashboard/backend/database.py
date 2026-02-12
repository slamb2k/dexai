"""
Dashboard Database Module

Handles SQLite database operations for dashboard-specific tables:
- dashboard_events: Activity and event logging
- dashboard_metrics: Time-series metrics storage
- dex_state: Current Dex avatar state
- dashboard_preferences: User UI preferences
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# Database path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dashboard.db"

# Seeding control via environment variable
SEED_DATA_ON_INIT = os.getenv("DEXAI_SEED_DATA", "false").lower() in ("true", "1", "yes")


def get_db_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize dashboard database tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Dashboard events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            channel TEXT,
            user_id TEXT,
            summary TEXT NOT NULL,
            details TEXT,
            severity TEXT DEFAULT 'info'
        )
    """)

    # Dashboard metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            labels TEXT
        )
    """)

    # Dex state table (singleton - only one row)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dex_state (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            state TEXT DEFAULT 'idle',
            current_task TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Dashboard preferences table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_preferences (
            user_id TEXT PRIMARY KEY,
            display_name TEXT DEFAULT 'User',
            timezone TEXT DEFAULT 'UTC',
            language TEXT DEFAULT 'en',
            theme TEXT DEFAULT 'dark',
            sidebar_collapsed INTEGER DEFAULT 0,
            default_page TEXT DEFAULT 'home',
            activity_filters TEXT,
            metrics_timeframe TEXT DEFAULT '7d',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migrate existing tables - add new columns if they don't exist
    for col, default in [
        ("display_name", "'User'"),
        ("timezone", "'UTC'"),
        ("language", "'en'"),
    ]:
        try:
            cursor.execute(
                f"ALTER TABLE dashboard_preferences ADD COLUMN {col} TEXT DEFAULT {default}"
            )
        except Exception:
            pass  # Column already exists

    # Routing decisions table for model routing analytics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routing_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_id TEXT,
            complexity TEXT NOT NULL,
            model TEXT NOT NULL,
            exacto INTEGER DEFAULT 0,
            reasoning TEXT,
            cost_usd REAL
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_routing_decisions_timestamp
        ON routing_decisions(timestamp DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_routing_decisions_complexity
        ON routing_decisions(complexity)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_routing_decisions_model
        ON routing_decisions(model)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_dashboard_events_timestamp
        ON dashboard_events(timestamp DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_dashboard_events_type
        ON dashboard_events(event_type)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_dashboard_events_severity
        ON dashboard_events(severity)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_dashboard_metrics_name_time
        ON dashboard_metrics(metric_name, timestamp DESC)
    """)
    # Initialize dex_state with default if not exists
    cursor.execute(
        """
        INSERT OR IGNORE INTO dex_state (id, state, current_task, updated_at)
        VALUES (1, 'idle', NULL, ?)
    """,
        (datetime.now().isoformat(),),
    )

    conn.commit()

    # Check if seeding is needed (tables empty or env var set)
    cursor.execute("SELECT COUNT(*) as count FROM dashboard_events")
    events_count = cursor.fetchone()["count"]
    cursor.execute("SELECT COUNT(*) as count FROM dashboard_metrics")
    metrics_count = cursor.fetchone()["count"]

    conn.close()

    # Auto-seed if tables are empty or DEXAI_SEED_DATA is set
    if SEED_DATA_ON_INIT or (events_count == 0 and metrics_count == 0):
        try:
            from . import seed

            print("[Database] Running initial seed...")
            results = seed.seed_database(force=False)
            if results["success"]:
                print(f"[Database] {results['message']}")
            else:
                print(f"[Database] Seed warning: {results['message']}")
        except ImportError:
            # Seed module not available, skip
            pass
        except Exception as e:
            print(f"[Database] Seed error (non-fatal): {e}")


# =============================================================================
# Event Operations
# =============================================================================


def log_event(
    event_type: str,
    summary: str,
    channel: str | None = None,
    user_id: str | None = None,
    details: dict | None = None,
    severity: str = "info",
) -> int:
    """
    Log a dashboard event.

    Args:
        event_type: Type of event (message, task, system, error)
        summary: Short description of the event
        channel: Related channel
        user_id: Related user
        details: Full event data as dict
        severity: info, warning, or error

    Returns:
        Event ID
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    details_json = json.dumps(details) if details else None

    cursor.execute(
        """
        INSERT INTO dashboard_events
        (event_type, timestamp, channel, user_id, summary, details, severity)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (event_type, datetime.now().isoformat(), channel, user_id, summary, details_json, severity),
    )

    event_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return event_id


def record_tool_use(
    tool_name: str,
    tool_use_id: str,
    success: bool,
    user_id: str | None = None,
    duration_ms: float | None = None,
    details: dict | None = None,
) -> int:
    """Record a tool use event for dashboard analytics."""
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO dashboard_events (event_type, timestamp, user_id, summary, details, severity)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "tool_use",
                datetime.now().isoformat(),
                user_id or "system",
                f"Tool: {tool_name} ({'ok' if success else 'fail'})",
                json.dumps({
                    "tool_name": tool_name,
                    "tool_use_id": tool_use_id,
                    "success": success,
                    "duration_ms": duration_ms,
                    **(details or {}),
                }),
                "info" if success else "warning",
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0
    finally:
        conn.close()


def log_audit(
    event_type: str,
    severity: str = "info",
    actor: str | None = None,
    target: str | None = None,
    details: dict | None = None,
) -> int:
    """Log an audit event to the dashboard database.

    Cross-module audit sink called by security modules
    (vault, session, permissions, ratelimit) and dependency_tools.
    """
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO dashboard_events (event_type, timestamp, user_id, summary, details, severity)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                event_type,
                datetime.now().isoformat(),
                actor or "system",
                f"{event_type}: {target or 'n/a'}",
                json.dumps({
                    "severity": severity,
                    "target": target,
                    **(details or {}),
                }),
                severity,
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0
    finally:
        conn.close()


def get_events(
    event_type: str | None = None,
    severity: str | None = None,
    channel: str | None = None,
    limit: int = 100,
    offset: int = 0,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    """
    Get dashboard events with optional filters.

    Returns list of event dictionaries.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM dashboard_events WHERE 1=1"
    params = []

    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)

    if severity:
        query += " AND severity = ?"
        params.append(severity)

    if channel:
        query += " AND channel = ?"
        params.append(channel)

    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date.isoformat())

    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date.isoformat())

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    events = []
    for row in rows:
        event = dict(row)
        if event.get("details"):
            try:
                event["details"] = json.loads(event["details"])
            except json.JSONDecodeError:
                pass
        events.append(event)

    return events


def count_events(
    event_type: str | None = None,
    severity: str | None = None,
    channel: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Count events matching filters."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT COUNT(*) as count FROM dashboard_events WHERE 1=1"
    params = []

    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)

    if severity:
        query += " AND severity = ?"
        params.append(severity)

    if channel:
        query += " AND channel = ?"
        params.append(channel)

    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date.isoformat())

    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date.isoformat())

    cursor.execute(query, params)
    count = cursor.fetchone()["count"]
    conn.close()

    return count


# =============================================================================
# Metrics Operations
# =============================================================================


def record_metric(
    metric_name: str,
    metric_value: float,
    labels: dict[str, str] | None = None,
    timestamp: datetime | None = None,
) -> int:
    """
    Record a metric value.

    Args:
        metric_name: Name of the metric
        metric_value: Numeric value
        labels: Optional dimension labels
        timestamp: Optional timestamp (defaults to now)

    Returns:
        Metric ID
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    labels_json = json.dumps(labels) if labels else None
    ts = (timestamp or datetime.now()).isoformat()

    cursor.execute(
        """
        INSERT INTO dashboard_metrics
        (metric_name, metric_value, timestamp, labels)
        VALUES (?, ?, ?, ?)
    """,
        (metric_name, metric_value, ts, labels_json),
    )

    metric_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return metric_id


def get_metrics(
    metric_name: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    labels: dict[str, str] | None = None,
    limit: int = 1000,
) -> list[dict]:
    """
    Get metric values for a given metric name.

    Returns list of metric dictionaries with timestamp and value.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM dashboard_metrics WHERE metric_name = ?"
    params = [metric_name]

    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date.isoformat())

    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date.isoformat())

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    metrics = []
    for row in rows:
        metric = dict(row)
        if metric.get("labels"):
            try:
                metric["labels"] = json.loads(metric["labels"])
            except json.JSONDecodeError:
                pass
        metrics.append(metric)

    return metrics


def aggregate_metrics(
    metric_name: str,
    aggregation: str = "sum",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    group_by_interval: str = "1h",
) -> list[dict]:
    """
    Aggregate metric values by time interval.

    Args:
        metric_name: Metric to aggregate
        aggregation: sum, avg, max, min, count
        start_date: Start of range
        end_date: End of range
        group_by_interval: 1h, 1d, 1w

    Returns:
        List of {timestamp, value} dicts
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # SQLite date formatting for grouping
    if group_by_interval == "1h":
        date_format = "%Y-%m-%d %H:00:00"
    elif group_by_interval == "1d":
        date_format = "%Y-%m-%d 00:00:00"
    elif group_by_interval == "1w":
        date_format = "%Y-%W"
    else:
        date_format = "%Y-%m-%d %H:00:00"

    agg_func = {"sum": "SUM", "avg": "AVG", "max": "MAX", "min": "MIN", "count": "COUNT"}.get(
        aggregation, "SUM"
    )

    query = f"""
        SELECT
            strftime('{date_format}', timestamp) as period,
            {agg_func}(metric_value) as value
        FROM dashboard_metrics
        WHERE metric_name = ?
    """
    params = [metric_name]

    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date.isoformat())

    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date.isoformat())

    query += " GROUP BY period ORDER BY period"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [{"timestamp": row["period"], "value": row["value"]} for row in rows]


# =============================================================================
# Dex State Operations
# =============================================================================


def get_dex_state() -> dict:
    """Get current Dex avatar state.

    Automatically expires stale active states (thinking, working, listening)
    back to idle if they haven't been updated within the timeout window.
    This prevents the UI from getting permanently stuck when a handler
    crashes without resetting the state.
    """
    # States that should auto-expire if stale
    ACTIVE_STATES = {"thinking", "working", "listening"}
    STALE_TIMEOUT_SECONDS = 300  # 5 minutes

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM dex_state WHERE id = 1")
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"id": 1, "state": "idle", "current_task": None, "updated_at": None}

    state = dict(row)

    # Auto-expire stale active states
    if state.get("state") in ACTIVE_STATES and state.get("updated_at"):
        try:
            updated = datetime.fromisoformat(state["updated_at"])
            age_seconds = (datetime.now() - updated).total_seconds()
            if age_seconds > STALE_TIMEOUT_SECONDS:
                stale_state = state["state"]
                stale_task = state.get("current_task")
                logger.warning(
                    "Auto-expiring stale dex_state: state=%s, task=%s, age=%.0fs (timeout=%ds)",
                    stale_state,
                    stale_task,
                    age_seconds,
                    STALE_TIMEOUT_SECONDS,
                )
                # Log to dashboard_events for UI visibility
                try:
                    cursor.execute(
                        """INSERT INTO dashboard_events
                           (event_type, summary, channel, severity, details)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            "system",
                            f"Auto-expired stale '{stale_state}' state after {int(age_seconds)}s"
                            + (f" (task: {stale_task})" if stale_task else ""),
                            "system",
                            "warning",
                            json.dumps({
                                "expired_state": stale_state,
                                "expired_task": stale_task,
                                "age_seconds": int(age_seconds),
                                "timeout_seconds": STALE_TIMEOUT_SECONDS,
                            }),
                        ),
                    )
                except Exception:
                    pass  # Event logging is best-effort
                cursor.execute(
                    "UPDATE dex_state SET state = 'idle', current_task = NULL, updated_at = ? WHERE id = 1",
                    (datetime.now().isoformat(),),
                )
                conn.commit()
                state["state"] = "idle"
                state["current_task"] = None
        except (ValueError, TypeError):
            pass

    conn.close()
    return state


def set_dex_state(state: str, current_task: str | None = None) -> dict:
    """
    Update Dex avatar state.

    Args:
        state: One of: idle, listening, thinking, working, success, error,
               sleeping, hyperfocus, waiting
        current_task: Optional description of current task

    Returns:
        Updated state dict
    """
    valid_states = [
        "idle",
        "listening",
        "thinking",
        "working",
        "success",
        "error",
        "sleeping",
        "hyperfocus",
        "waiting",
    ]
    if state not in valid_states:
        raise ValueError(f"Invalid state: {state}. Must be one of {valid_states}")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE dex_state SET
            state = ?,
            current_task = ?,
            updated_at = ?
        WHERE id = 1
    """,
        (state, current_task, datetime.now().isoformat()),
    )

    conn.commit()

    cursor.execute("SELECT * FROM dex_state WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    return dict(row)


# =============================================================================
# Preferences Operations
# =============================================================================


def get_preferences(user_id: str) -> dict:
    """Get user dashboard preferences."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM dashboard_preferences WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        prefs = dict(row)
        if prefs.get("activity_filters"):
            try:
                prefs["activity_filters"] = json.loads(prefs["activity_filters"])
            except json.JSONDecodeError:
                pass
        return prefs

    # Return defaults
    return {
        "user_id": user_id,
        "display_name": "User",
        "timezone": "UTC",
        "language": "en",
        "theme": "dark",
        "sidebar_collapsed": False,
        "default_page": "home",
        "activity_filters": None,
        "metrics_timeframe": "7d",
    }


def set_preferences(user_id: str, preferences: dict) -> dict:
    """
    Update user dashboard preferences.

    Args:
        user_id: User identifier
        preferences: Dict of preferences to update

    Returns:
        Updated preferences
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get current preferences
    current = get_preferences(user_id)

    # Merge updates
    updated = {**current, **preferences}
    updated["updated_at"] = datetime.now().isoformat()

    # Serialize activity_filters if present
    activity_filters = updated.get("activity_filters")
    if isinstance(activity_filters, dict):
        activity_filters = json.dumps(activity_filters)

    cursor.execute(
        """
        INSERT INTO dashboard_preferences
        (user_id, display_name, timezone, language, theme, sidebar_collapsed,
         default_page, activity_filters, metrics_timeframe, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            display_name = excluded.display_name,
            timezone = excluded.timezone,
            language = excluded.language,
            theme = excluded.theme,
            sidebar_collapsed = excluded.sidebar_collapsed,
            default_page = excluded.default_page,
            activity_filters = excluded.activity_filters,
            metrics_timeframe = excluded.metrics_timeframe,
            updated_at = excluded.updated_at
    """,
        (
            user_id,
            updated.get("display_name", "User"),
            updated.get("timezone", "UTC"),
            updated.get("language", "en"),
            updated.get("theme", "dark"),
            1 if updated.get("sidebar_collapsed") else 0,
            updated.get("default_page", "home"),
            activity_filters,
            updated.get("metrics_timeframe", "7d"),
            updated["updated_at"],
        ),
    )

    conn.commit()
    conn.close()

    return get_preferences(user_id)


# =============================================================================
# Quick Stats
# =============================================================================


def get_quick_stats() -> dict:
    """Get quick stats for dashboard cards."""
    conn = get_db_connection()
    cursor = conn.cursor()

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Tasks today
    cursor.execute(
        """
        SELECT COUNT(*) as count FROM dashboard_events
        WHERE event_type = 'task' AND timestamp >= ?
    """,
        (today_start.isoformat(),),
    )
    tasks_today = cursor.fetchone()["count"]

    # Messages today
    cursor.execute(
        """
        SELECT COUNT(*) as count FROM dashboard_events
        WHERE event_type = 'message' AND timestamp >= ?
    """,
        (today_start.isoformat(),),
    )
    messages_today = cursor.fetchone()["count"]

    # Errors today
    cursor.execute(
        """
        SELECT COUNT(*) as count FROM dashboard_events
        WHERE severity = 'error' AND timestamp >= ?
    """,
        (today_start.isoformat(),),
    )
    errors_today = cursor.fetchone()["count"]

    # Cost today (if tracked)
    cursor.execute(
        """
        SELECT SUM(metric_value) as total FROM dashboard_metrics
        WHERE metric_name = 'api_cost_usd' AND timestamp >= ?
    """,
        (today_start.isoformat(),),
    )
    row = cursor.fetchone()
    cost_today = row["total"] if row["total"] else 0.0

    # Unique channels
    cursor.execute(
        """
        SELECT COUNT(DISTINCT channel) as count FROM dashboard_events
        WHERE channel IS NOT NULL AND timestamp >= ?
    """,
        (today_start.isoformat(),),
    )
    active_channels = cursor.fetchone()["count"]

    # Average response time from metrics
    cursor.execute(
        """
        SELECT AVG(metric_value) as avg_time FROM dashboard_metrics
        WHERE metric_name = 'response_time_ms' AND timestamp >= ?
    """,
        (today_start.isoformat(),),
    )
    row = cursor.fetchone()
    avg_response_time = row["avg_time"] if row["avg_time"] else 0.0

    conn.close()

    # Calculate error rate
    total_events = tasks_today + messages_today
    error_rate = (errors_today / total_events * 100) if total_events > 0 else 0.0

    return {
        "tasks_today": tasks_today,
        "messages_today": messages_today,
        "cost_today_usd": round(cost_today, 4),
        "active_channels": active_channels,
        "avg_response_time_ms": round(avg_response_time, 2),
        "error_rate_percent": round(error_rate, 2),
    }


# =============================================================================
# Task Operations (for channel-spawned tasks)
# =============================================================================


def create_task(
    source: str,
    request: str,
    status: str = "pending",
) -> str:
    """
    Create a new task and return its ID.

    Args:
        source: Task source (e.g., 'telegram:user123')
        request: Task request/description
        status: Initial status ('pending', 'running', 'completed', 'failed')

    Returns:
        Task ID as string
    """
    import uuid

    task_id = str(uuid.uuid4())

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO dashboard_events
        (event_type, timestamp, channel, user_id, summary, details, severity)
        VALUES ('task', ?, ?, ?, ?, ?, 'info')
    """,
        (
            datetime.now().isoformat(),
            source.split(":")[0] if ":" in source else source,
            source.split(":")[1] if ":" in source else None,
            f"Task created: {request[:50]}...",
            json.dumps({"task_id": task_id, "request": request, "status": status}),
        ),
    )

    conn.commit()
    conn.close()

    return task_id


def update_task(
    task_id: str,
    status: str | None = None,
    summary: str | None = None,
) -> bool:
    """
    Update task status and/or summary.

    Args:
        task_id: Task identifier
        status: New status ('pending', 'running', 'completed', 'failed')
        summary: Result summary

    Returns:
        True if updated, False if not found
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Log task update as event
    cursor.execute(
        """
        INSERT INTO dashboard_events
        (event_type, timestamp, summary, details, severity)
        VALUES ('task', ?, ?, ?, 'info')
    """,
        (
            datetime.now().isoformat(),
            f"Task {status or 'updated'}: {summary[:50] if summary else task_id}",
            json.dumps({"task_id": task_id, "status": status, "summary": summary}),
        ),
    )

    conn.commit()
    conn.close()

    return True


# =============================================================================
# Routing Decision Operations
# =============================================================================


def record_routing_decision(
    user_id: str,
    complexity: str,
    model: str,
    exacto: bool,
    reasoning: str,
    cost_usd: float | None = None,
) -> int:
    """
    Record a model routing decision for analytics.

    Args:
        user_id: User who triggered the request
        complexity: Classified complexity level (trivial, low, moderate, high, critical)
        model: Model ID that was selected
        exacto: Whether Exacto mode was used
        reasoning: Human-readable routing explanation
        cost_usd: Optional cost of the request

    Returns:
        Routing decision ID
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO routing_decisions
        (timestamp, user_id, complexity, model, exacto, reasoning, cost_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            datetime.now().isoformat(),
            user_id,
            complexity,
            model,
            1 if exacto else 0,
            reasoning,
            cost_usd,
        ),
    )

    decision_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return decision_id


def get_routing_stats(days: int = 7) -> dict:
    """
    Get routing statistics for the dashboard.

    Args:
        days: Number of days to include in stats

    Returns:
        Dict with complexity distribution, model distribution, and cost savings estimate
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    start_date = (datetime.now() - __import__("datetime").timedelta(days=days)).isoformat()

    # Total query count
    cursor.execute(
        "SELECT COUNT(*) as count FROM routing_decisions WHERE timestamp >= ?",
        (start_date,),
    )
    total_queries = cursor.fetchone()["count"]

    # Complexity distribution
    cursor.execute(
        """
        SELECT complexity, COUNT(*) as count
        FROM routing_decisions
        WHERE timestamp >= ?
        GROUP BY complexity
        ORDER BY count DESC
    """,
        (start_date,),
    )
    complexity_distribution = {row["complexity"]: row["count"] for row in cursor.fetchall()}

    # Model distribution
    cursor.execute(
        """
        SELECT model, COUNT(*) as count
        FROM routing_decisions
        WHERE timestamp >= ?
        GROUP BY model
        ORDER BY count DESC
    """,
        (start_date,),
    )
    model_distribution = {row["model"]: row["count"] for row in cursor.fetchall()}

    # Exacto usage
    cursor.execute(
        """
        SELECT COUNT(*) as count FROM routing_decisions
        WHERE timestamp >= ? AND exacto = 1
    """,
        (start_date,),
    )
    exacto_count = cursor.fetchone()["count"]

    # Calculate estimated savings (simplified model)
    # Assumes: trivial/low could have used Haiku ($0.80/1M input)
    #          but would have used Sonnet ($3/1M input) without routing
    # Savings = (queries_downgraded) * (sonnet_cost - haiku_cost) * avg_tokens
    trivial_low_count = complexity_distribution.get("trivial", 0) + complexity_distribution.get("low", 0)
    # Rough estimate: 1000 input tokens per query average
    avg_input_tokens = 1000
    sonnet_cost_per_token = 3.0 / 1_000_000
    haiku_cost_per_token = 0.80 / 1_000_000
    savings_per_query = (sonnet_cost_per_token - haiku_cost_per_token) * avg_input_tokens
    estimated_savings_usd = round(trivial_low_count * savings_per_query, 4)

    # Total cost if tracked
    cursor.execute(
        """
        SELECT SUM(cost_usd) as total FROM routing_decisions
        WHERE timestamp >= ? AND cost_usd IS NOT NULL
    """,
        (start_date,),
    )
    row = cursor.fetchone()
    total_cost_usd = row["total"] if row["total"] else 0.0

    conn.close()

    return {
        "total_queries": total_queries,
        "complexity": complexity_distribution,
        "models": model_distribution,
        "exacto_count": exacto_count,
        "exacto_pct": round((exacto_count / total_queries * 100) if total_queries > 0 else 0, 1),
        "estimated_savings_usd": estimated_savings_usd,
        "total_cost_usd": round(total_cost_usd, 4),
        "period_days": days,
    }


def get_routing_decisions(
    user_id: str | None = None,
    complexity: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    Get recent routing decisions with optional filters.

    Args:
        user_id: Filter by user
        complexity: Filter by complexity level
        limit: Maximum results
        offset: Pagination offset

    Returns:
        List of routing decision dicts
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM routing_decisions WHERE 1=1"
    params = []

    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)

    if complexity:
        query += " AND complexity = ?"
        params.append(complexity)

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
