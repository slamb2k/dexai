"""
Dashboard Database Module

Handles SQLite database operations for dashboard-specific tables:
- dashboard_events: Activity and event logging
- dashboard_metrics: Time-series metrics storage
- dex_state: Current Dex avatar state
- dashboard_preferences: User UI preferences
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Database path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dashboard.db'


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
    cursor.execute('''
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
    ''')

    # Dashboard metrics table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dashboard_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            labels TEXT
        )
    ''')

    # Dex state table (singleton - only one row)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dex_state (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            state TEXT DEFAULT 'idle',
            current_task TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Dashboard preferences table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dashboard_preferences (
            user_id TEXT PRIMARY KEY,
            theme TEXT DEFAULT 'dark',
            sidebar_collapsed INTEGER DEFAULT 0,
            default_page TEXT DEFAULT 'home',
            activity_filters TEXT,
            metrics_timeframe TEXT DEFAULT '7d',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create indexes
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_dashboard_events_timestamp
        ON dashboard_events(timestamp DESC)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_dashboard_events_type
        ON dashboard_events(event_type)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_dashboard_events_severity
        ON dashboard_events(severity)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_dashboard_metrics_name_time
        ON dashboard_metrics(metric_name, timestamp DESC)
    ''')

    # Initialize dex_state with default if not exists
    cursor.execute('''
        INSERT OR IGNORE INTO dex_state (id, state, current_task, updated_at)
        VALUES (1, 'idle', NULL, ?)
    ''', (datetime.now().isoformat(),))

    conn.commit()
    conn.close()


# =============================================================================
# Event Operations
# =============================================================================

def log_event(
    event_type: str,
    summary: str,
    channel: Optional[str] = None,
    user_id: Optional[str] = None,
    details: Optional[Dict] = None,
    severity: str = 'info'
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

    cursor.execute('''
        INSERT INTO dashboard_events
        (event_type, timestamp, channel, user_id, summary, details, severity)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (event_type, datetime.now().isoformat(), channel, user_id,
          summary, details_json, severity))

    event_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return event_id


def get_events(
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    channel: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[Dict]:
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
        if event.get('details'):
            try:
                event['details'] = json.loads(event['details'])
            except json.JSONDecodeError:
                pass
        events.append(event)

    return events


def count_events(
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    channel: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
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
    count = cursor.fetchone()['count']
    conn.close()

    return count


# =============================================================================
# Metrics Operations
# =============================================================================

def record_metric(
    metric_name: str,
    metric_value: float,
    labels: Optional[Dict[str, str]] = None,
    timestamp: Optional[datetime] = None
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

    cursor.execute('''
        INSERT INTO dashboard_metrics
        (metric_name, metric_value, timestamp, labels)
        VALUES (?, ?, ?, ?)
    ''', (metric_name, metric_value, ts, labels_json))

    metric_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return metric_id


def get_metrics(
    metric_name: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    labels: Optional[Dict[str, str]] = None,
    limit: int = 1000
) -> List[Dict]:
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
        if metric.get('labels'):
            try:
                metric['labels'] = json.loads(metric['labels'])
            except json.JSONDecodeError:
                pass
        metrics.append(metric)

    return metrics


def aggregate_metrics(
    metric_name: str,
    aggregation: str = 'sum',
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    group_by_interval: str = '1h'
) -> List[Dict]:
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
    if group_by_interval == '1h':
        date_format = '%Y-%m-%d %H:00:00'
    elif group_by_interval == '1d':
        date_format = '%Y-%m-%d 00:00:00'
    elif group_by_interval == '1w':
        date_format = '%Y-%W'
    else:
        date_format = '%Y-%m-%d %H:00:00'

    agg_func = {
        'sum': 'SUM',
        'avg': 'AVG',
        'max': 'MAX',
        'min': 'MIN',
        'count': 'COUNT'
    }.get(aggregation, 'SUM')

    query = f'''
        SELECT
            strftime('{date_format}', timestamp) as period,
            {agg_func}(metric_value) as value
        FROM dashboard_metrics
        WHERE metric_name = ?
    '''
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

    return [{'timestamp': row['period'], 'value': row['value']} for row in rows]


# =============================================================================
# Dex State Operations
# =============================================================================

def get_dex_state() -> Dict:
    """Get current Dex avatar state."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM dex_state WHERE id = 1')
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return {'id': 1, 'state': 'idle', 'current_task': None, 'updated_at': None}


def set_dex_state(
    state: str,
    current_task: Optional[str] = None
) -> Dict:
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
        'idle', 'listening', 'thinking', 'working', 'success',
        'error', 'sleeping', 'hyperfocus', 'waiting'
    ]
    if state not in valid_states:
        raise ValueError(f"Invalid state: {state}. Must be one of {valid_states}")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE dex_state SET
            state = ?,
            current_task = ?,
            updated_at = ?
        WHERE id = 1
    ''', (state, current_task, datetime.now().isoformat()))

    conn.commit()

    cursor.execute('SELECT * FROM dex_state WHERE id = 1')
    row = cursor.fetchone()
    conn.close()

    return dict(row)


# =============================================================================
# Preferences Operations
# =============================================================================

def get_preferences(user_id: str) -> Dict:
    """Get user dashboard preferences."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        'SELECT * FROM dashboard_preferences WHERE user_id = ?',
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        prefs = dict(row)
        if prefs.get('activity_filters'):
            try:
                prefs['activity_filters'] = json.loads(prefs['activity_filters'])
            except json.JSONDecodeError:
                pass
        return prefs

    # Return defaults
    return {
        'user_id': user_id,
        'theme': 'dark',
        'sidebar_collapsed': False,
        'default_page': 'home',
        'activity_filters': None,
        'metrics_timeframe': '7d'
    }


def set_preferences(user_id: str, preferences: Dict) -> Dict:
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
    updated['updated_at'] = datetime.now().isoformat()

    # Serialize activity_filters if present
    activity_filters = updated.get('activity_filters')
    if isinstance(activity_filters, dict):
        activity_filters = json.dumps(activity_filters)

    cursor.execute('''
        INSERT INTO dashboard_preferences
        (user_id, theme, sidebar_collapsed, default_page, activity_filters,
         metrics_timeframe, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            theme = excluded.theme,
            sidebar_collapsed = excluded.sidebar_collapsed,
            default_page = excluded.default_page,
            activity_filters = excluded.activity_filters,
            metrics_timeframe = excluded.metrics_timeframe,
            updated_at = excluded.updated_at
    ''', (
        user_id,
        updated.get('theme', 'dark'),
        1 if updated.get('sidebar_collapsed') else 0,
        updated.get('default_page', 'home'),
        activity_filters,
        updated.get('metrics_timeframe', '7d'),
        updated['updated_at']
    ))

    conn.commit()
    conn.close()

    return get_preferences(user_id)


# =============================================================================
# Quick Stats
# =============================================================================

def get_quick_stats() -> Dict:
    """Get quick stats for dashboard cards."""
    conn = get_db_connection()
    cursor = conn.cursor()

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Tasks today
    cursor.execute('''
        SELECT COUNT(*) as count FROM dashboard_events
        WHERE event_type = 'task' AND timestamp >= ?
    ''', (today_start.isoformat(),))
    tasks_today = cursor.fetchone()['count']

    # Messages today
    cursor.execute('''
        SELECT COUNT(*) as count FROM dashboard_events
        WHERE event_type = 'message' AND timestamp >= ?
    ''', (today_start.isoformat(),))
    messages_today = cursor.fetchone()['count']

    # Errors today
    cursor.execute('''
        SELECT COUNT(*) as count FROM dashboard_events
        WHERE severity = 'error' AND timestamp >= ?
    ''', (today_start.isoformat(),))
    errors_today = cursor.fetchone()['count']

    # Cost today (if tracked)
    cursor.execute('''
        SELECT SUM(metric_value) as total FROM dashboard_metrics
        WHERE metric_name = 'api_cost_usd' AND timestamp >= ?
    ''', (today_start.isoformat(),))
    row = cursor.fetchone()
    cost_today = row['total'] if row['total'] else 0.0

    # Unique channels
    cursor.execute('''
        SELECT COUNT(DISTINCT channel) as count FROM dashboard_events
        WHERE channel IS NOT NULL AND timestamp >= ?
    ''', (today_start.isoformat(),))
    active_channels = cursor.fetchone()['count']

    conn.close()

    # Calculate error rate
    total_events = tasks_today + messages_today
    error_rate = (errors_today / total_events * 100) if total_events > 0 else 0.0

    return {
        'tasks_today': tasks_today,
        'messages_today': messages_today,
        'cost_today_usd': round(cost_today, 4),
        'active_channels': active_channels,
        'avg_response_time_ms': 0.0,  # Would need timing data
        'error_rate_percent': round(error_rate, 2)
    }
