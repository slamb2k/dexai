"""
Tool: Transition Time Calculator
Purpose: Calculate ADHD-appropriate reminder times accounting for transition time

ADHD users need more time to transition between activities because:
- Disengaging from hyperfocus is difficult
- Time blindness makes estimating transition time hard
- Context switching has higher cognitive cost

Standard "15 minute reminder" fails because it assumes neurotypical time perception.
This tool calculates proper transition buffers and learns from actual patterns.

Usage:
    python tools/automation/transition_calculator.py --action calculate --event-time "2024-01-15T14:00:00" --event-type meeting --user alice
    python tools/automation/transition_calculator.py --action record --user alice --event-type meeting --actual-minutes 22 --on-time
    python tools/automation/transition_calculator.py --action patterns --user alice
    python tools/automation/transition_calculator.py --action set-defaults --user alice --meeting 30 --deep-work 35

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

# Valid event types
VALID_EVENT_TYPES = ["meeting", "deep_work", "admin", "social", "appointment", "custom"]


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    default_config = {
        "smart_notifications": {
            "transition_time": {
                "default_buffer_minutes": 25,
                "deep_work_buffer_minutes": 30,
                "admin_buffer_minutes": 15,
                "social_buffer_minutes": 20,
                "appointment_buffer_minutes": 35,
                "learn_from_patterns": True,
                "min_samples_for_learning": 5,
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

    # Transition patterns table - learn from actual transitions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transition_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actual_transition_minutes REAL,
            on_time INTEGER,
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # User transition defaults - personalized buffers
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transition_defaults (
            user_id TEXT PRIMARY KEY,
            meeting_buffer INTEGER DEFAULT 25,
            deep_work_buffer INTEGER DEFAULT 30,
            admin_buffer INTEGER DEFAULT 15,
            social_buffer INTEGER DEFAULT 20,
            appointment_buffer INTEGER DEFAULT 35,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transition_user ON transition_patterns(user_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_transition_type ON transition_patterns(event_type)"
    )

    conn.commit()
    return conn


def row_to_dict(row) -> dict | None:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    return dict(row)


def get_default_buffer(event_type: str, user_id: str | None = None) -> int:
    """
    Get default buffer for event type, checking user overrides first.

    Args:
        event_type: Type of event
        user_id: Optional user for personalized defaults

    Returns:
        Buffer time in minutes
    """
    config = load_config()
    transition_config = config.get("smart_notifications", {}).get("transition_time", {})

    # System defaults
    system_defaults = {
        "meeting": transition_config.get("default_buffer_minutes", 25),
        "deep_work": transition_config.get("deep_work_buffer_minutes", 30),
        "admin": transition_config.get("admin_buffer_minutes", 15),
        "social": transition_config.get("social_buffer_minutes", 20),
        "appointment": transition_config.get("appointment_buffer_minutes", 35),
        "custom": transition_config.get("default_buffer_minutes", 25),
    }

    default = system_defaults.get(event_type, 25)

    # Check for user-specific defaults
    if user_id:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM transition_defaults WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            column_name = f"{event_type}_buffer"
            if column_name in row.keys() and row[column_name] is not None:
                return row[column_name]

    return default


def get_learned_buffer(user_id: str, event_type: str) -> float | None:
    """
    Get learned transition time from historical patterns.

    Args:
        user_id: User identifier
        event_type: Type of event

    Returns:
        Learned buffer in minutes, or None if insufficient data
    """
    config = load_config()
    transition_config = config.get("smart_notifications", {}).get("transition_time", {})

    if not transition_config.get("learn_from_patterns", True):
        return None

    min_samples = transition_config.get("min_samples_for_learning", 5)

    conn = get_connection()
    cursor = conn.cursor()

    # Get recent transitions (last 30)
    cursor.execute(
        """
        SELECT actual_transition_minutes, on_time
        FROM transition_patterns
        WHERE user_id = ? AND event_type = ?
        ORDER BY recorded_at DESC
        LIMIT 30
    """,
        (user_id, event_type),
    )

    rows = cursor.fetchall()
    conn.close()

    if len(rows) < min_samples:
        return None

    # Calculate weighted average (recent transitions weighted more)
    total_weight = 0
    weighted_sum = 0

    for i, row in enumerate(rows):
        # More recent = higher weight (1.0 to 0.5)
        weight = 1.0 - (i * 0.5 / len(rows))

        # On-time transitions weighted slightly less (they might have had margin)
        if row["on_time"]:
            weight *= 0.9

        weighted_sum += row["actual_transition_minutes"] * weight
        total_weight += weight

    if total_weight > 0:
        learned = weighted_sum / total_weight
        # Add 10% buffer to learned time (safety margin)
        return round(learned * 1.1, 1)

    return None


def calculate_reminder_time(
    user_id: str, event_time: str, event_type: str = "meeting"
) -> dict[str, Any]:
    """
    Calculate optimal reminder time for an event.

    Args:
        user_id: User identifier
        event_time: ISO format datetime of the event
        event_type: Type of event (meeting, deep_work, admin, social, appointment)

    Returns:
        dict with reminder time and buffer details
    """
    if event_type not in VALID_EVENT_TYPES:
        return {
            "success": False,
            "error": f"Invalid event type. Must be one of: {VALID_EVENT_TYPES}",
        }

    try:
        event_dt = datetime.fromisoformat(event_time)
    except ValueError:
        return {
            "success": False,
            "error": "Invalid event_time format. Use ISO format (YYYY-MM-DDTHH:MM:SS)",
        }

    # Get buffer: learned takes precedence over default
    learned_buffer = get_learned_buffer(user_id, event_type)
    default_buffer = get_default_buffer(event_type, user_id)

    if learned_buffer is not None:
        buffer_minutes = learned_buffer
        source = "learned_pattern"
        reason = f"Based on your typical {event_type} transition time"
    else:
        buffer_minutes = default_buffer
        source = "default"
        reason = get_buffer_reason(event_type)

    # Calculate reminder time
    reminder_dt = event_dt - timedelta(minutes=buffer_minutes)

    # Sanity check: don't set reminder in the past
    now = datetime.now()
    if reminder_dt < now:
        # If event is very soon, give at least 5 minute warning
        if event_dt > now:
            reminder_dt = max(now, event_dt - timedelta(minutes=5))
            reason = "Event is soon - reduced buffer"
        else:
            return {"success": False, "error": "Event time is in the past"}

    return {
        "success": True,
        "reminder_time": reminder_dt.isoformat(),
        "event_time": event_time,
        "buffer_minutes": round(buffer_minutes, 1),
        "source": source,
        "reason": reason,
        "event_type": event_type,
    }


def get_buffer_reason(event_type: str) -> str:
    """Get human-readable reason for buffer choice."""
    reasons = {
        "meeting": "Meetings need time to disengage, context switch, and arrive ready",
        "deep_work": "Deep work requires longer disengagement from hyperfocus",
        "admin": "Admin tasks have lower cognitive load, easier to switch",
        "social": "Social events need emotional preparation time",
        "appointment": "Appointments usually involve travel and uncertainty",
        "custom": "Standard ADHD-friendly buffer",
    }
    return reasons.get(event_type, "Standard ADHD-friendly buffer")


def record_transition(
    user_id: str, event_type: str, actual_minutes: float, on_time: bool = True
) -> dict[str, Any]:
    """
    Record actual transition time for learning.

    Args:
        user_id: User identifier
        event_type: Type of event
        actual_minutes: How long the transition actually took
        on_time: Whether user arrived on time

    Returns:
        dict with success status and updated average
    """
    if event_type not in VALID_EVENT_TYPES:
        return {
            "success": False,
            "error": f"Invalid event type. Must be one of: {VALID_EVENT_TYPES}",
        }

    if actual_minutes < 0:
        return {"success": False, "error": "actual_minutes must be positive"}

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO transition_patterns (user_id, event_type, actual_transition_minutes, on_time)
        VALUES (?, ?, ?, ?)
    """,
        (user_id, event_type, actual_minutes, 1 if on_time else 0),
    )

    conn.commit()

    # Get new average
    cursor.execute(
        """
        SELECT AVG(actual_transition_minutes) as avg_minutes, COUNT(*) as count
        FROM transition_patterns
        WHERE user_id = ? AND event_type = ?
    """,
        (user_id, event_type),
    )

    stats = cursor.fetchone()
    conn.close()

    return {
        "success": True,
        "message": "Transition recorded",
        "event_type": event_type,
        "actual_minutes": actual_minutes,
        "on_time": on_time,
        "new_average": round(stats["avg_minutes"], 1) if stats["avg_minutes"] else actual_minutes,
        "sample_count": stats["count"],
    }


def get_patterns(user_id: str) -> dict[str, Any]:
    """
    Get transition patterns for user.

    Args:
        user_id: User identifier

    Returns:
        dict with patterns by event type
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get averages by event type
    cursor.execute(
        """
        SELECT
            event_type,
            AVG(actual_transition_minutes) as avg_minutes,
            COUNT(*) as sample_count,
            SUM(CASE WHEN on_time = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as on_time_percent
        FROM transition_patterns
        WHERE user_id = ?
        GROUP BY event_type
    """,
        (user_id,),
    )

    rows = cursor.fetchall()

    # Get user defaults
    cursor.execute("SELECT * FROM transition_defaults WHERE user_id = ?", (user_id,))
    defaults_row = cursor.fetchone()
    conn.close()

    patterns = {}
    for row in rows:
        patterns[row["event_type"]] = {
            "average_minutes": round(row["avg_minutes"], 1),
            "sample_count": row["sample_count"],
            "on_time_percent": round(row["on_time_percent"], 1),
        }

    defaults = {}
    if defaults_row:
        defaults = {
            "meeting": defaults_row["meeting_buffer"],
            "deep_work": defaults_row["deep_work_buffer"],
            "admin": defaults_row["admin_buffer"],
            "social": defaults_row["social_buffer"],
            "appointment": defaults_row["appointment_buffer"],
        }

    return {
        "success": True,
        "patterns": patterns,
        "custom_defaults": defaults,
        "message": f"Found patterns for {len(patterns)} event types",
    }


def set_defaults(
    user_id: str,
    meeting: int | None = None,
    deep_work: int | None = None,
    admin: int | None = None,
    social: int | None = None,
    appointment: int | None = None,
) -> dict[str, Any]:
    """
    Set custom transition defaults for user.

    Args:
        user_id: User identifier
        meeting: Meeting buffer in minutes
        deep_work: Deep work buffer in minutes
        admin: Admin buffer in minutes
        social: Social buffer in minutes
        appointment: Appointment buffer in minutes

    Returns:
        dict with success status
    """
    # Validate ranges (5-120 minutes)
    for name, value in [
        ("meeting", meeting),
        ("deep_work", deep_work),
        ("admin", admin),
        ("social", social),
        ("appointment", appointment),
    ]:
        if value is not None and (value < 5 or value > 120):
            return {"success": False, "error": f"{name} must be between 5 and 120 minutes"}

    conn = get_connection()
    cursor = conn.cursor()

    # Get current defaults
    cursor.execute("SELECT * FROM transition_defaults WHERE user_id = ?", (user_id,))
    existing = cursor.fetchone()

    if existing:
        # Update only provided values
        updates = []
        params = []

        if meeting is not None:
            updates.append("meeting_buffer = ?")
            params.append(meeting)
        if deep_work is not None:
            updates.append("deep_work_buffer = ?")
            params.append(deep_work)
        if admin is not None:
            updates.append("admin_buffer = ?")
            params.append(admin)
        if social is not None:
            updates.append("social_buffer = ?")
            params.append(social)
        if appointment is not None:
            updates.append("appointment_buffer = ?")
            params.append(appointment)

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(user_id)

            cursor.execute(
                f"""
                UPDATE transition_defaults
                SET {", ".join(updates)}
                WHERE user_id = ?
            """,
                params,
            )
    else:
        # Insert new row with defaults
        config = load_config()
        tc = config.get("smart_notifications", {}).get("transition_time", {})

        cursor.execute(
            """
            INSERT INTO transition_defaults
            (user_id, meeting_buffer, deep_work_buffer, admin_buffer, social_buffer, appointment_buffer)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                user_id,
                meeting or tc.get("default_buffer_minutes", 25),
                deep_work or tc.get("deep_work_buffer_minutes", 30),
                admin or tc.get("admin_buffer_minutes", 15),
                social or tc.get("social_buffer_minutes", 20),
                appointment or tc.get("appointment_buffer_minutes", 35),
            ),
        )

    conn.commit()
    conn.close()

    return {"success": True, "message": "Defaults updated", "user_id": user_id}


def get_upcoming_reminder(user_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Get the next reminder time from a list of events.

    Args:
        user_id: User identifier
        events: List of events with 'time' and 'type' keys

    Returns:
        dict with next reminder details
    """
    now = datetime.now()
    next_reminder = None
    next_event = None

    for event in events:
        try:
            event_time = event.get("time")
            event_type = event.get("type", "meeting")

            result = calculate_reminder_time(user_id, event_time, event_type)
            if not result.get("success"):
                continue

            reminder_dt = datetime.fromisoformat(result["reminder_time"])

            if reminder_dt > now:
                if next_reminder is None or reminder_dt < datetime.fromisoformat(
                    next_reminder["reminder_time"]
                ):
                    next_reminder = result
                    next_event = event
        except Exception:
            continue

    if next_reminder:
        return {"success": True, "next_reminder": next_reminder, "event": next_event}

    return {"success": True, "next_reminder": None, "message": "No upcoming events"}


def main():
    parser = argparse.ArgumentParser(description="Transition Time Calculator")
    parser.add_argument(
        "--action",
        required=True,
        choices=["calculate", "record", "patterns", "set-defaults"],
        help="Action to perform",
    )

    parser.add_argument("--user", help="User ID")
    parser.add_argument("--event-time", dest="event_time", help="Event time (ISO format)")
    parser.add_argument(
        "--event-type",
        dest="event_type",
        default="meeting",
        choices=VALID_EVENT_TYPES,
        help="Type of event",
    )
    parser.add_argument(
        "--actual-minutes",
        dest="actual_minutes",
        type=float,
        help="Actual transition time in minutes",
    )
    parser.add_argument(
        "--on-time", dest="on_time", action="store_true", help="Whether user was on time"
    )
    parser.add_argument("--late", dest="late", action="store_true", help="Whether user was late")

    # Defaults for set-defaults action
    parser.add_argument("--meeting", type=int, help="Meeting buffer in minutes")
    parser.add_argument(
        "--deep-work", dest="deep_work", type=int, help="Deep work buffer in minutes"
    )
    parser.add_argument("--admin", type=int, help="Admin buffer in minutes")
    parser.add_argument("--social", type=int, help="Social buffer in minutes")
    parser.add_argument("--appointment", type=int, help="Appointment buffer in minutes")

    args = parser.parse_args()
    result = None

    if args.action == "calculate":
        if not args.user or not args.event_time:
            print("Error: --user and --event-time required for calculate")
            sys.exit(1)
        result = calculate_reminder_time(args.user, args.event_time, args.event_type)

    elif args.action == "record":
        if not args.user or args.actual_minutes is None:
            print("Error: --user and --actual-minutes required for record")
            sys.exit(1)
        on_time = not args.late if args.late else args.on_time
        result = record_transition(args.user, args.event_type, args.actual_minutes, on_time)

    elif args.action == "patterns":
        if not args.user:
            print("Error: --user required for patterns")
            sys.exit(1)
        result = get_patterns(args.user)

    elif args.action == "set-defaults":
        if not args.user:
            print("Error: --user required for set-defaults")
            sys.exit(1)
        result = set_defaults(
            args.user,
            meeting=args.meeting,
            deep_work=args.deep_work,
            admin=args.admin,
            social=args.social,
            appointment=args.appointment,
        )

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
