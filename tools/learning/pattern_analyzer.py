"""
Tool: Pattern Analyzer
Purpose: Detect recurring behavioral patterns from activity history

This tool identifies patterns in user behavior without requiring explicit
tracking or self-reporting. Patterns emerge from observation over time.

Pattern Types:
- daily_routine: Same-time activities (e.g., "checks email at 9am")
- weekly_cycle: Day-of-week patterns (e.g., "Mondays are meeting-heavy")
- avoidance: Tasks repeatedly postponed (critical for ADHD)
- productive_burst: Clusters of task completions
- context_switch: Frequent topic changes (potential focus issues)

Usage:
    # Analyze all patterns for user
    python tools/learning/pattern_analyzer.py --action analyze --user alice

    # Get detected habits
    python tools/learning/pattern_analyzer.py --action habits --user alice

    # Get avoidance patterns (important for ADHD)
    python tools/learning/pattern_analyzer.py --action avoidance --user alice

    # Get weekly overview
    python tools/learning/pattern_analyzer.py --action weekly --user alice

    # Force pattern re-detection
    python tools/learning/pattern_analyzer.py --action detect --user alice --since 30d

Dependencies:
    - sqlite3 (stdlib)
    - yaml (PyYAML)

Output:
    JSON result with success status and pattern data
"""

import argparse
import json
import re
import sqlite3
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "learning.db"
CONFIG_PATH = PROJECT_ROOT / "args" / "learning.yaml"
TASKS_DB_PATH = PROJECT_ROOT / "data" / "tasks.db"
ACTIVITY_DB_PATH = PROJECT_ROOT / "data" / "activity.db"

# Pattern types
PATTERN_TYPES = ["daily_routine", "weekly_cycle", "avoidance", "productive_burst", "context_switch"]

# Day name mapping
DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
            return config.get("learning", {}).get("pattern_detection", {})
    # Return defaults if no config
    return {
        "enabled": True,
        "min_occurrences": 3,
        "lookback_days": 30,
        "avoidance_threshold": 3,
        "routine_time_tolerance": 30,
        "pattern_decay_days": 14,
        "confidence_boost_per_occurrence": 0.1,
        "max_confidence": 0.95,
    }


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Behavior patterns table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS behavior_patterns (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pattern_type TEXT NOT NULL,
            pattern_data TEXT NOT NULL,
            confidence REAL DEFAULT 0.5,
            sample_count INTEGER DEFAULT 0,
            first_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)

    # Task events table (for tracking postponements, completions)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            task_name TEXT,
            event_type TEXT NOT NULL,
            event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            details TEXT
        )
    """)

    # Activity events table (for general activity tracking)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            activity_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            hour INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            details TEXT
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patterns_user ON behavior_patterns(user_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_patterns_type ON behavior_patterns(user_id, pattern_type)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_events_user ON task_events(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_events_user ON activity_events(user_id)"
    )

    conn.commit()
    return conn


def row_to_dict(row) -> dict | None:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    d = dict(row)
    # Parse JSON fields
    for field in ["pattern_data", "details"]:
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except json.JSONDecodeError:
                pass
    return d


def parse_duration(duration_str: str) -> timedelta | None:
    """Parse duration string like '24h', '7d', '30m' into timedelta."""
    match = re.match(r"^(\d+)([mhdw])$", duration_str.lower())
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        return timedelta(minutes=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    elif unit == "w":
        return timedelta(weeks=value)

    return None


def record_task_event(
    user_id: str,
    task_id: str,
    event_type: str,
    task_name: str | None = None,
    details: dict | None = None,
) -> dict[str, Any]:
    """
    Record a task event (completion, postponement, etc.).

    Args:
        user_id: User identifier
        task_id: Task identifier
        event_type: Type of event (completed, postponed, started, abandoned)
        task_name: Human-readable task name
        details: Additional event details

    Returns:
        dict with success status
    """
    event_id = str(uuid.uuid4())[:8]
    now = datetime.now()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO task_events (id, user_id, task_id, task_name, event_type, event_time, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            event_id,
            user_id,
            task_id,
            task_name,
            event_type,
            now.isoformat(),
            json.dumps(details) if details else None,
        ),
    )

    conn.commit()
    conn.close()

    return {"success": True, "event_id": event_id, "event_type": event_type}


def record_activity(
    user_id: str, activity_type: str, details: dict | None = None, timestamp: datetime | None = None
) -> dict[str, Any]:
    """
    Record a general activity event.

    Args:
        user_id: User identifier
        activity_type: Type of activity (message, session_start, command, etc.)
        details: Additional details
        timestamp: When it happened (defaults to now)

    Returns:
        dict with success status
    """
    event_id = str(uuid.uuid4())[:8]
    ts = timestamp or datetime.now()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO activity_events (id, user_id, activity_type, activity_time, hour, day_of_week, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            event_id,
            user_id,
            activity_type,
            ts.isoformat(),
            ts.hour,
            ts.weekday(),
            json.dumps(details) if details else None,
        ),
    )

    conn.commit()
    conn.close()

    return {"success": True, "event_id": event_id, "activity_type": activity_type}


def detect_avoidance_patterns(user_id: str, config: dict[str, Any]) -> list[dict]:
    """Detect tasks that are repeatedly postponed."""
    threshold = config.get("avoidance_threshold", 3)
    lookback = config.get("lookback_days", 30)
    cutoff = (datetime.now() - timedelta(days=lookback)).isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    # Find tasks with multiple postponements
    cursor.execute(
        """
        SELECT task_id, task_name, COUNT(*) as postpone_count,
               MIN(event_time) as first_postponed,
               MAX(event_time) as last_postponed
        FROM task_events
        WHERE user_id = ? AND event_type = 'postponed' AND event_time >= ?
        GROUP BY task_id
        HAVING COUNT(*) >= ?
        ORDER BY postpone_count DESC
    """,
        (user_id, cutoff, threshold),
    )

    patterns = []
    for row in cursor.fetchall():
        # Check if task was eventually completed
        cursor.execute(
            """
            SELECT COUNT(*) as completed
            FROM task_events
            WHERE user_id = ? AND task_id = ? AND event_type = 'completed'
        """,
            (user_id, row["task_id"]),
        )

        completed = cursor.fetchone()["completed"] > 0

        patterns.append(
            {
                "task_id": row["task_id"],
                "task_name": row["task_name"],
                "postpone_count": row["postpone_count"],
                "first_postponed": row["first_postponed"],
                "last_postponed": row["last_postponed"],
                "eventually_completed": completed,
                "confidence": min(
                    config.get("max_confidence", 0.95),
                    0.5
                    + row["postpone_count"] * config.get("confidence_boost_per_occurrence", 0.1),
                ),
            }
        )

    conn.close()
    return patterns


def detect_daily_routines(user_id: str, config: dict[str, Any]) -> list[dict]:
    """Detect same-time daily activities."""
    min_occurrences = config.get("min_occurrences", 3)
    time_tolerance = config.get("routine_time_tolerance", 30)  # minutes
    lookback = config.get("lookback_days", 30)
    cutoff = (datetime.now() - timedelta(days=lookback)).isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    # Group activities by type and approximate hour
    cursor.execute(
        """
        SELECT activity_type, hour, COUNT(*) as count,
               GROUP_CONCAT(DISTINCT day_of_week) as days
        FROM activity_events
        WHERE user_id = ? AND activity_time >= ?
        GROUP BY activity_type, hour
        HAVING COUNT(*) >= ?
        ORDER BY count DESC
    """,
        (user_id, cutoff, min_occurrences),
    )

    patterns = []
    for row in cursor.fetchall():
        days = [int(d) for d in row["days"].split(",")]
        patterns.append(
            {
                "activity_type": row["activity_type"],
                "typical_hour": row["hour"],
                "occurrence_count": row["count"],
                "days_observed": [DAY_NAMES[d] for d in days],
                "confidence": min(config.get("max_confidence", 0.95), 0.4 + row["count"] * 0.05),
            }
        )

    conn.close()
    return patterns


def detect_weekly_cycles(user_id: str, config: dict[str, Any]) -> list[dict]:
    """Detect day-of-week patterns."""
    min_occurrences = config.get("min_occurrences", 3)
    lookback = config.get("lookback_days", 30)
    cutoff = (datetime.now() - timedelta(days=lookback)).isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    # Count activities per day of week
    cursor.execute(
        """
        SELECT day_of_week, activity_type, COUNT(*) as count
        FROM activity_events
        WHERE user_id = ? AND activity_time >= ?
        GROUP BY day_of_week, activity_type
        ORDER BY day_of_week, count DESC
    """,
        (user_id, cutoff),
    )

    # Organize by day
    day_activities = defaultdict(list)
    for row in cursor.fetchall():
        day_activities[row["day_of_week"]].append(
            {"activity_type": row["activity_type"], "count": row["count"]}
        )

    # Also check task completions per day
    cursor.execute(
        """
        SELECT
            CAST(strftime('%w', event_time) AS INTEGER) as dow,
            COUNT(*) as completions
        FROM task_events
        WHERE user_id = ? AND event_type = 'completed' AND event_time >= ?
        GROUP BY dow
    """,
        (user_id, cutoff),
    )

    completions_by_day = {row["dow"]: row["completions"] for row in cursor.fetchall()}

    conn.close()

    patterns = []
    for dow, activities in day_activities.items():
        day_name = DAY_NAMES[dow]
        total_activity = sum(a["count"] for a in activities)

        patterns.append(
            {
                "day": day_name,
                "total_activities": total_activity,
                "top_activities": activities[:3],
                "task_completions": completions_by_day.get(dow, 0),
                "confidence": min(0.8, 0.3 + total_activity * 0.02),
            }
        )

    return sorted(patterns, key=lambda x: x["total_activities"], reverse=True)


def detect_productive_bursts(user_id: str, config: dict[str, Any]) -> list[dict]:
    """Detect clusters of task completions."""
    lookback = config.get("lookback_days", 30)
    cutoff = (datetime.now() - timedelta(days=lookback)).isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    # Find hours with multiple completions
    cursor.execute(
        """
        SELECT
            date(event_time) as completion_date,
            CAST(strftime('%H', event_time) AS INTEGER) as hour,
            COUNT(*) as completions
        FROM task_events
        WHERE user_id = ? AND event_type = 'completed' AND event_time >= ?
        GROUP BY completion_date, hour
        HAVING COUNT(*) >= 2
        ORDER BY completions DESC
    """,
        (user_id, cutoff),
    )

    bursts = []
    for row in cursor.fetchall():
        bursts.append(
            {"date": row["completion_date"], "hour": row["hour"], "completions": row["completions"]}
        )

    conn.close()

    if not bursts:
        return []

    # Identify recurring burst hours
    hour_counts = defaultdict(int)
    for burst in bursts:
        hour_counts[burst["hour"]] += 1

    recurring_hours = [h for h, c in hour_counts.items() if c >= config.get("min_occurrences", 3)]

    return [
        {
            "burst_hours": sorted(recurring_hours),
            "total_bursts": len(bursts),
            "sample_bursts": bursts[:5],
            "confidence": min(0.8, 0.3 + len(bursts) * 0.05),
        }
    ]


def save_pattern(
    user_id: str,
    pattern_type: str,
    pattern_data: dict[str, Any],
    confidence: float,
    sample_count: int,
) -> str:
    """Save or update a detected pattern."""
    conn = get_connection()
    cursor = conn.cursor()

    # Check if similar pattern exists
    pattern_key = json.dumps(pattern_data, sort_keys=True)
    cursor.execute(
        """
        SELECT id, sample_count FROM behavior_patterns
        WHERE user_id = ? AND pattern_type = ? AND pattern_data = ?
    """,
        (user_id, pattern_type, pattern_key),
    )

    existing = cursor.fetchone()

    if existing:
        # Update existing pattern
        cursor.execute(
            """
            UPDATE behavior_patterns
            SET confidence = ?, sample_count = ?, last_observed = ?, is_active = 1
            WHERE id = ?
        """,
            (confidence, sample_count, datetime.now().isoformat(), existing["id"]),
        )
        pattern_id = existing["id"]
    else:
        # Create new pattern
        pattern_id = str(uuid.uuid4())[:8]
        cursor.execute(
            """
            INSERT INTO behavior_patterns
            (id, user_id, pattern_type, pattern_data, confidence, sample_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (pattern_id, user_id, pattern_type, pattern_key, confidence, sample_count),
        )

    conn.commit()
    conn.close()

    return pattern_id


def analyze_patterns(user_id: str, since: str | None = None) -> dict[str, Any]:
    """
    Run full pattern analysis for a user.

    Args:
        user_id: User identifier
        since: Duration to look back (e.g., '30d')

    Returns:
        dict with all detected patterns
    """
    config = load_config()

    if not config.get("enabled", True):
        return {"success": False, "error": "Pattern detection is disabled"}

    if since:
        duration = parse_duration(since)
        if duration:
            config["lookback_days"] = duration.days

    # Detect all pattern types
    avoidance = detect_avoidance_patterns(user_id, config)
    routines = detect_daily_routines(user_id, config)
    weekly = detect_weekly_cycles(user_id, config)
    bursts = detect_productive_bursts(user_id, config)

    # Save significant patterns
    patterns_saved = 0

    for pattern in avoidance:
        if pattern["confidence"] >= 0.5:
            save_pattern(
                user_id,
                "avoidance",
                {"task_id": pattern["task_id"], "task_name": pattern["task_name"]},
                pattern["confidence"],
                pattern["postpone_count"],
            )
            patterns_saved += 1

    for pattern in routines:
        if pattern["confidence"] >= 0.5:
            save_pattern(
                user_id,
                "daily_routine",
                {"activity_type": pattern["activity_type"], "hour": pattern["typical_hour"]},
                pattern["confidence"],
                pattern["occurrence_count"],
            )
            patterns_saved += 1

    if bursts and bursts[0]["confidence"] >= 0.5:
        save_pattern(
            user_id,
            "productive_burst",
            {"hours": bursts[0]["burst_hours"]},
            bursts[0]["confidence"],
            bursts[0]["total_bursts"],
        )
        patterns_saved += 1

    return {
        "success": True,
        "user_id": user_id,
        "patterns": {
            "avoidance": avoidance,
            "daily_routines": routines,
            "weekly_cycles": weekly,
            "productive_bursts": bursts,
        },
        "patterns_saved": patterns_saved,
        "lookback_days": config.get("lookback_days", 30),
    }


def get_habits(user_id: str) -> dict[str, Any]:
    """
    Get detected habits (daily routines) for a user.

    Args:
        user_id: User identifier

    Returns:
        dict with habit patterns
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM behavior_patterns
        WHERE user_id = ? AND pattern_type = 'daily_routine' AND is_active = 1
        ORDER BY confidence DESC
    """,
        (user_id,),
    )

    habits = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()

    if not habits:
        return {
            "success": True,
            "user_id": user_id,
            "habits": [],
            "message": "No habits detected yet - I'm still learning your routines.",
        }

    return {"success": True, "user_id": user_id, "habits": habits}


def get_avoidance(user_id: str) -> dict[str, Any]:
    """
    Get avoidance patterns for a user (ADHD critical).

    Args:
        user_id: User identifier

    Returns:
        dict with avoidance patterns
    """
    config = load_config()

    # Get real-time avoidance detection
    avoidance = detect_avoidance_patterns(user_id, config)

    if not avoidance:
        return {
            "success": True,
            "user_id": user_id,
            "avoidance_patterns": [],
            "message": "No avoidance patterns detected - you're staying on top of things.",
        }

    # Format in ADHD-friendly way (no guilt)
    formatted = []
    for pattern in avoidance:
        formatted.append(
            {
                "task_name": pattern["task_name"] or f"Task {pattern['task_id']}",
                "times_postponed": pattern["postpone_count"],
                "suggestion": "Want me to find the smallest first step for this?",
                "eventually_completed": pattern["eventually_completed"],
                "confidence": pattern["confidence"],
            }
        )

    return {
        "success": True,
        "user_id": user_id,
        "avoidance_patterns": formatted,
        "note": "These patterns might indicate hidden friction - not failure.",
    }


def get_weekly_overview(user_id: str) -> dict[str, Any]:
    """
    Get weekly pattern overview for a user.

    Args:
        user_id: User identifier

    Returns:
        dict with weekly patterns
    """
    config = load_config()
    weekly = detect_weekly_cycles(user_id, config)

    if not weekly:
        return {
            "success": True,
            "user_id": user_id,
            "weekly_overview": {},
            "message": "Not enough data for weekly patterns yet.",
        }

    # Find most and least productive days
    most_productive = max(weekly, key=lambda x: x["task_completions"])
    least_active = min(weekly, key=lambda x: x["total_activities"])

    return {
        "success": True,
        "user_id": user_id,
        "weekly_overview": weekly,
        "insights": {
            "most_productive_day": most_productive["day"],
            "most_productive_completions": most_productive["task_completions"],
            "quietest_day": least_active["day"],
            "quietest_activities": least_active["total_activities"],
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Pattern Analyzer - Detect recurring behavioral patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Analyze all patterns for user
    python pattern_analyzer.py --action analyze --user alice

    # Get detected habits
    python pattern_analyzer.py --action habits --user alice

    # Get avoidance patterns (important for ADHD)
    python pattern_analyzer.py --action avoidance --user alice

    # Get weekly overview
    python pattern_analyzer.py --action weekly --user alice

    # Force pattern detection with custom lookback
    python pattern_analyzer.py --action detect --user alice --since 30d

    # Record a task event
    python pattern_analyzer.py --action record-task --user alice \\
        --task-id abc123 --event postponed --task-name "Do taxes"

    # Record an activity
    python pattern_analyzer.py --action record-activity --user alice \\
        --activity-type message
        """,
    )

    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "analyze",
            "habits",
            "avoidance",
            "weekly",
            "detect",
            "record-task",
            "record-activity",
        ],
        help="Action to perform",
    )
    parser.add_argument("--user", required=True, help="User ID")
    parser.add_argument("--since", help="Lookback duration (e.g., 30d)")
    parser.add_argument("--task-id", help="Task ID for task events")
    parser.add_argument("--task-name", help="Task name for task events")
    parser.add_argument(
        "--event", help="Event type for task events (completed, postponed, started, abandoned)"
    )
    parser.add_argument("--activity-type", help="Activity type for activity events")
    parser.add_argument("--details", help="JSON details for events")

    args = parser.parse_args()
    result = None

    if args.action == "analyze" or args.action == "detect":
        result = analyze_patterns(args.user, args.since)

    elif args.action == "habits":
        result = get_habits(args.user)

    elif args.action == "avoidance":
        result = get_avoidance(args.user)

    elif args.action == "weekly":
        result = get_weekly_overview(args.user)

    elif args.action == "record-task":
        if not args.task_id or not args.event:
            print(json.dumps({"success": False, "error": "--task-id and --event required"}))
            sys.exit(1)

        details = None
        if args.details:
            try:
                details = json.loads(args.details)
            except json.JSONDecodeError:
                pass

        result = record_task_event(args.user, args.task_id, args.event, args.task_name, details)

    elif args.action == "record-activity":
        if not args.activity_type:
            print(json.dumps({"success": False, "error": "--activity-type required"}))
            sys.exit(1)

        details = None
        if args.details:
            try:
                details = json.loads(args.details)
            except json.JSONDecodeError:
                pass

        result = record_activity(args.user, args.activity_type, details)

    if result:
        print(json.dumps(result, indent=2, default=str))
        if not result.get("success"):
            sys.exit(1)


if __name__ == "__main__":
    main()
