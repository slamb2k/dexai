"""
Tool: Flow State Detector
Purpose: Detect hyperfocus/flow state to protect productive ADHD users from interruptions

Flow detection uses multiple signals:
- Activity density (messages in time window)
- Response time patterns (rapid responses = engaged)
- Historical patterns (learn when user typically focuses)
- Manual overrides (user-declared focus mode)

Usage:
    python tools/automation/flow_detector.py --action detect --user alice
    python tools/automation/flow_detector.py --action score --user alice
    python tools/automation/flow_detector.py --action set-override --user alice --duration 60
    python tools/automation/flow_detector.py --action clear-override --user alice
    python tools/automation/flow_detector.py --action get-override --user alice
    python tools/automation/flow_detector.py --action record --user alice --response-time 5.2
    python tools/automation/flow_detector.py --action patterns --user alice

Dependencies:
    - sqlite3 (stdlib)
    - pyyaml (for config)

Output:
    JSON result with success status and data
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.automation import DB_PATH


# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "smart_notifications.yaml"


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    default_config = {
        "smart_notifications": {
            "flow_protection": {
                "enabled": True,
                "detection_window_minutes": 15,
                "min_activity_for_flow": 3,
                "flow_score_threshold": 60,
                "suppress_low_priority": True,
                "suppress_medium_during_deep_flow": True,
                "deep_flow_threshold": 80,
            }
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

    # Activity patterns table - tracks flow patterns by time of day
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_patterns (
            user_id TEXT NOT NULL,
            hour INTEGER,
            day_of_week INTEGER,
            message_count INTEGER DEFAULT 0,
            avg_response_time_seconds REAL,
            flow_score REAL DEFAULT 0,
            sample_count INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, hour, day_of_week)
        )
    """)

    # Flow overrides table - manual focus mode
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS flow_overrides (
            user_id TEXT PRIMARY KEY,
            is_focusing INTEGER DEFAULT 0,
            until DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Recent activity table - for real-time flow detection
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recent_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            response_time_seconds REAL,
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_patterns(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recent_user ON recent_activity(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recent_time ON recent_activity(recorded_at)")

    conn.commit()
    return conn


def row_to_dict(row) -> dict | None:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    return dict(row)


def record_activity(user_id: str, response_time_seconds: float | None = None) -> dict[str, Any]:
    """
    Record user activity for flow detection.

    Args:
        user_id: User identifier
        response_time_seconds: Time between message receipt and response (if applicable)

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()

    # Record in recent_activity for real-time detection
    cursor.execute(
        """
        INSERT INTO recent_activity (user_id, response_time_seconds, recorded_at)
        VALUES (?, ?, ?)
    """,
        (user_id, response_time_seconds, now.isoformat()),
    )

    # Update activity_patterns for historical learning
    hour = now.hour
    day_of_week = now.weekday()

    cursor.execute(
        """
        INSERT INTO activity_patterns (user_id, hour, day_of_week, message_count, avg_response_time_seconds, sample_count, updated_at)
        VALUES (?, ?, ?, 1, ?, 1, ?)
        ON CONFLICT(user_id, hour, day_of_week) DO UPDATE SET
            message_count = message_count + 1,
            avg_response_time_seconds = CASE
                WHEN excluded.avg_response_time_seconds IS NOT NULL THEN
                    (COALESCE(avg_response_time_seconds, 0) * sample_count + excluded.avg_response_time_seconds) / (sample_count + 1)
                ELSE avg_response_time_seconds
            END,
            sample_count = sample_count + 1,
            updated_at = excluded.updated_at
    """,
        (user_id, hour, day_of_week, response_time_seconds, now.isoformat()),
    )

    # Clean up old recent_activity (keep last 24 hours)
    cutoff = (now - timedelta(hours=24)).isoformat()
    cursor.execute("DELETE FROM recent_activity WHERE recorded_at < ?", (cutoff,))

    conn.commit()
    conn.close()

    return {"success": True, "message": "Activity recorded", "user_id": user_id}


def get_flow_score(user_id: str, window_minutes: int | None = None) -> dict[str, Any]:
    """
    Calculate current flow score for user.

    Score 0-100 based on:
    - Recent activity density (50%)
    - Response time patterns (30%)
    - Historical patterns for this time slot (20%)

    Args:
        user_id: User identifier
        window_minutes: Time window for activity analysis (default from config)

    Returns:
        dict with flow score and components
    """
    config = load_config()
    flow_config = config.get("smart_notifications", {}).get("flow_protection", {})

    if window_minutes is None:
        window_minutes = flow_config.get("detection_window_minutes", 15)

    min_activity = flow_config.get("min_activity_for_flow", 3)

    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()
    cutoff = (now - timedelta(minutes=window_minutes)).isoformat()

    # Get recent activity count and avg response time
    cursor.execute(
        """
        SELECT
            COUNT(*) as activity_count,
            AVG(response_time_seconds) as avg_response_time
        FROM recent_activity
        WHERE user_id = ? AND recorded_at >= ?
    """,
        (user_id, cutoff),
    )

    recent = cursor.fetchone()
    activity_count = recent["activity_count"] or 0
    avg_response_time = recent["avg_response_time"]

    # Get historical pattern for this time slot
    hour = now.hour
    day_of_week = now.weekday()

    cursor.execute(
        """
        SELECT flow_score, message_count, avg_response_time_seconds, sample_count
        FROM activity_patterns
        WHERE user_id = ? AND hour = ? AND day_of_week = ?
    """,
        (user_id, hour, day_of_week),
    )

    historical = cursor.fetchone()
    conn.close()

    # Calculate component scores

    # Activity density score (0-100)
    # More activity = higher score, normalized against min threshold
    if activity_count >= min_activity:
        activity_score = min(100, (activity_count / min_activity) * 50 + 50)
    else:
        activity_score = (activity_count / min_activity) * 50

    # Response time score (0-100)
    # Faster responses = higher score
    # < 30s = high engagement, > 5 min = low engagement
    if avg_response_time is not None:
        if avg_response_time < 30:
            response_score = 100
        elif avg_response_time < 60:
            response_score = 80
        elif avg_response_time < 180:
            response_score = 50
        elif avg_response_time < 300:
            response_score = 30
        else:
            response_score = 10
    else:
        response_score = 0  # No response time data

    # Historical pattern score (0-100)
    if historical and historical["sample_count"] >= 5:
        # Use stored flow score if we have enough samples
        historical_score = historical["flow_score"] or 0
    else:
        historical_score = 50  # Neutral if insufficient data

    # Weighted combination
    flow_score = activity_score * 0.50 + response_score * 0.30 + historical_score * 0.20

    return {
        "success": True,
        "score": round(flow_score, 1),
        "window_minutes": window_minutes,
        "components": {
            "activity": round(activity_score, 1),
            "response_time": round(response_score, 1),
            "historical": round(historical_score, 1),
        },
        "activity_count": activity_count,
        "avg_response_time_seconds": round(avg_response_time, 1) if avg_response_time else None,
    }


def detect_flow(user_id: str) -> dict[str, Any]:
    """
    Detect if user is currently in flow state.

    Checks:
    1. Manual override (takes precedence)
    2. Activity-based detection

    Args:
        user_id: User identifier

    Returns:
        dict with flow state and source
    """
    config = load_config()
    flow_config = config.get("smart_notifications", {}).get("flow_protection", {})

    if not flow_config.get("enabled", True):
        return {"success": True, "in_flow": False, "score": 0, "source": "disabled"}

    threshold = flow_config.get("flow_score_threshold", 60)
    deep_threshold = flow_config.get("deep_flow_threshold", 80)

    # Check manual override first
    override = get_override(user_id)
    if override.get("success") and override.get("is_focusing"):
        return {
            "success": True,
            "in_flow": True,
            "deep_flow": True,  # Manual focus always counts as deep
            "score": 100,
            "source": "manual_override",
            "until": override.get("until"),
        }

    # Calculate flow score
    score_result = get_flow_score(user_id)
    if not score_result.get("success"):
        return score_result

    score = score_result["score"]
    in_flow = score >= threshold
    deep_flow = score >= deep_threshold

    return {
        "success": True,
        "in_flow": in_flow,
        "deep_flow": deep_flow,
        "score": score,
        "source": "activity_pattern" if in_flow else "no_flow",
        "components": score_result.get("components"),
    }


def set_override(user_id: str, duration_minutes: int) -> dict[str, Any]:
    """
    Set manual focus mode for user.

    Args:
        user_id: User identifier
        duration_minutes: How long to maintain focus mode

    Returns:
        dict with success status and expiry time
    """
    if duration_minutes <= 0:
        return {"success": False, "error": "Duration must be positive"}

    if duration_minutes > 480:  # Max 8 hours
        return {"success": False, "error": "Duration cannot exceed 480 minutes (8 hours)"}

    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()
    until = now + timedelta(minutes=duration_minutes)

    cursor.execute(
        """
        INSERT INTO flow_overrides (user_id, is_focusing, until, created_at)
        VALUES (?, 1, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            is_focusing = 1,
            until = excluded.until,
            created_at = excluded.created_at
    """,
        (user_id, until.isoformat(), now.isoformat()),
    )

    conn.commit()
    conn.close()

    # Log to audit
    try:
        from tools.security import audit

        audit.log_event(
            event_type="system",
            action="flow_override_set",
            user_id=user_id,
            status="success",
            details={"duration_minutes": duration_minutes, "until": until.isoformat()},
        )
    except Exception:
        pass

    return {
        "success": True,
        "until": until.isoformat(),
        "duration_minutes": duration_minutes,
        "message": f"Focus mode enabled for {duration_minutes} minutes",
    }


def clear_override(user_id: str) -> dict[str, Any]:
    """
    Clear manual focus mode for user.

    Args:
        user_id: User identifier

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE flow_overrides
        SET is_focusing = 0, until = NULL
        WHERE user_id = ?
    """,
        (user_id,),
    )

    affected = cursor.rowcount
    conn.commit()
    conn.close()

    # Log to audit
    try:
        from tools.security import audit

        audit.log_event(
            event_type="system", action="flow_override_cleared", user_id=user_id, status="success"
        )
    except Exception:
        pass

    return {
        "success": True,
        "message": "Focus mode cleared" if affected > 0 else "No active focus mode",
    }


def get_override(user_id: str) -> dict[str, Any]:
    """
    Get current focus mode status for user.

    Args:
        user_id: User identifier

    Returns:
        dict with focus mode status
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT is_focusing, until, created_at
        FROM flow_overrides
        WHERE user_id = ?
    """,
        (user_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": True, "is_focusing": False, "message": "No focus mode set"}

    is_focusing = bool(row["is_focusing"])
    until = row["until"]

    # Check if override has expired
    if is_focusing and until:
        try:
            until_dt = datetime.fromisoformat(until)
            if datetime.now() > until_dt:
                # Expired - clear it
                clear_override(user_id)
                return {"success": True, "is_focusing": False, "message": "Focus mode expired"}
        except ValueError:
            pass

    return {
        "success": True,
        "is_focusing": is_focusing,
        "until": until if is_focusing else None,
        "created_at": row["created_at"],
    }


def get_patterns(user_id: str) -> dict[str, Any]:
    """
    Get historical activity patterns for user.

    Args:
        user_id: User identifier

    Returns:
        dict with patterns and identified peak hours
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT hour, day_of_week, message_count, avg_response_time_seconds, flow_score, sample_count
        FROM activity_patterns
        WHERE user_id = ?
        ORDER BY day_of_week, hour
    """,
        (user_id,),
    )

    patterns = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()

    if not patterns:
        return {
            "success": True,
            "patterns": [],
            "peak_hours": [],
            "message": "No activity patterns recorded yet",
        }

    # Identify peak hours (highest activity)
    hourly_activity = {}
    for p in patterns:
        hour = p["hour"]
        count = p["message_count"] or 0
        if hour not in hourly_activity:
            hourly_activity[hour] = 0
        hourly_activity[hour] += count

    # Sort by activity and get top 3
    sorted_hours = sorted(hourly_activity.items(), key=lambda x: x[1], reverse=True)
    peak_hours = [h[0] for h in sorted_hours[:3] if h[1] > 0]

    return {
        "success": True,
        "patterns": patterns,
        "peak_hours": peak_hours,
        "total_samples": sum(p.get("sample_count", 0) for p in patterns),
    }


def update_historical_flow_scores() -> dict[str, Any]:
    """
    Update stored flow scores based on accumulated data.
    Run periodically (e.g., daily) to recalculate historical patterns.

    Returns:
        dict with update count
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get all patterns with enough samples
    cursor.execute("""
        SELECT user_id, hour, day_of_week, message_count, avg_response_time_seconds, sample_count
        FROM activity_patterns
        WHERE sample_count >= 5
    """)

    patterns = cursor.fetchall()
    updated = 0

    for p in patterns:
        # Calculate flow score based on historical data
        msg_count = p["message_count"] or 0
        avg_response = p["avg_response_time_seconds"]
        samples = p["sample_count"]

        # Normalize message count per sample
        avg_messages = msg_count / samples if samples > 0 else 0

        # Activity score component
        if avg_messages >= 3:
            activity_score = min(100, avg_messages * 20)
        else:
            activity_score = avg_messages * 33

        # Response time component
        if avg_response is not None:
            if avg_response < 30:
                response_score = 100
            elif avg_response < 60:
                response_score = 80
            elif avg_response < 180:
                response_score = 50
            else:
                response_score = 30
        else:
            response_score = 50

        # Combined flow score
        flow_score = activity_score * 0.6 + response_score * 0.4

        cursor.execute(
            """
            UPDATE activity_patterns
            SET flow_score = ?
            WHERE user_id = ? AND hour = ? AND day_of_week = ?
        """,
            (flow_score, p["user_id"], p["hour"], p["day_of_week"]),
        )

        updated += 1

    conn.commit()
    conn.close()

    return {
        "success": True,
        "updated": updated,
        "message": f"Updated {updated} historical flow scores",
    }


def main():
    parser = argparse.ArgumentParser(description="Flow State Detector")
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "detect",
            "score",
            "set-override",
            "clear-override",
            "get-override",
            "record",
            "patterns",
            "update-scores",
        ],
        help="Action to perform",
    )

    parser.add_argument("--user", help="User ID")
    parser.add_argument("--duration", type=int, help="Focus mode duration in minutes")
    parser.add_argument(
        "--response-time", type=float, dest="response_time", help="Response time in seconds"
    )
    parser.add_argument("--window", type=int, help="Detection window in minutes")

    args = parser.parse_args()
    result = None

    if args.action == "detect":
        if not args.user:
            print("Error: --user required for detect")
            sys.exit(1)
        result = detect_flow(args.user)

    elif args.action == "score":
        if not args.user:
            print("Error: --user required for score")
            sys.exit(1)
        result = get_flow_score(args.user, args.window)

    elif args.action == "set-override":
        if not args.user:
            print("Error: --user required for set-override")
            sys.exit(1)
        if not args.duration:
            print("Error: --duration required for set-override")
            sys.exit(1)
        result = set_override(args.user, args.duration)

    elif args.action == "clear-override":
        if not args.user:
            print("Error: --user required for clear-override")
            sys.exit(1)
        result = clear_override(args.user)

    elif args.action == "get-override":
        if not args.user:
            print("Error: --user required for get-override")
            sys.exit(1)
        result = get_override(args.user)

    elif args.action == "record":
        if not args.user:
            print("Error: --user required for record")
            sys.exit(1)
        result = record_activity(args.user, args.response_time)

    elif args.action == "patterns":
        if not args.user:
            print("Error: --user required for patterns")
            sys.exit(1)
        result = get_patterns(args.user)

    elif args.action == "update-scores":
        result = update_historical_flow_scores()

    # Output
    if result:
        if result.get("success"):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
