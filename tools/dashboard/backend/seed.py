"""
Database Seeding Script for DexAI Dashboard

Populates the dashboard database with realistic seed data for:
- dashboard_events: Initial system events (startup, channel connections)
- dashboard_metrics: 7 days of hourly metric data for charts
- dex_state: Initial idle state
- Sample tasks in activity.db

Usage:
    python seed.py              # Seed if tables are empty
    python seed.py --force      # Force reseed (clears existing data)
    python seed.py --check      # Check if seeding is needed
"""

import argparse
import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Database paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DASHBOARD_DB_PATH = PROJECT_ROOT / "data" / "dashboard.db"
ACTIVITY_DB_PATH = PROJECT_ROOT / "data" / "activity.db"


def get_db_connection(db_path: Path) -> sqlite3.Connection:
    """Get database connection with row factory."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def is_seeded(conn: sqlite3.Connection) -> bool:
    """Check if database has seed data."""
    cursor = conn.cursor()

    # Check for events
    cursor.execute("SELECT COUNT(*) as count FROM dashboard_events")
    events_count = cursor.fetchone()["count"]

    # Check for metrics
    cursor.execute("SELECT COUNT(*) as count FROM dashboard_metrics")
    metrics_count = cursor.fetchone()["count"]

    return events_count > 10 and metrics_count > 50


def clear_data(conn: sqlite3.Connection) -> None:
    """Clear existing dashboard data."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dashboard_events")
    cursor.execute("DELETE FROM dashboard_metrics")
    cursor.execute("UPDATE dex_state SET state = 'idle', current_task = NULL")
    conn.commit()
    print("  Cleared existing dashboard data")


def seed_events(conn: sqlite3.Connection) -> int:
    """Seed dashboard_events table with realistic events."""
    cursor = conn.cursor()
    now = datetime.now()
    events = []

    # System startup events
    events.append(
        {
            "event_type": "system",
            "timestamp": (now - timedelta(days=7)).isoformat(),
            "channel": None,
            "user_id": None,
            "summary": "DexAI system initialized",
            "details": json.dumps({"version": "1.0.0", "environment": "production"}),
            "severity": "info",
        }
    )

    # Channel connection events
    channels = ["telegram", "discord", "slack"]
    for i, channel in enumerate(channels):
        events.append(
            {
                "event_type": "system",
                "timestamp": (now - timedelta(days=7) + timedelta(minutes=i + 1)).isoformat(),
                "channel": channel,
                "user_id": None,
                "summary": f"{channel.capitalize()} adapter connected",
                "details": json.dumps({"adapter": channel, "status": "connected"}),
                "severity": "info",
            }
        )

    # Generate sample message events over 7 days
    message_summaries = [
        "User requested task breakdown",
        "Check-in message received",
        "Task completion confirmed",
        "Question about schedule",
        "Priority update requested",
        "Morning briefing delivered",
        "Reminder acknowledged",
        "New task added to queue",
        "Status query processed",
        "Daily summary sent",
    ]

    for day in range(7):
        day_start = now - timedelta(days=6 - day)
        # Random number of messages per day (10-30)
        num_messages = random.randint(10, 30)

        for _ in range(num_messages):
            hour = random.randint(8, 22)  # Active hours
            minute = random.randint(0, 59)
            timestamp = day_start.replace(hour=hour, minute=minute, second=random.randint(0, 59))

            channel = random.choice(channels)
            events.append(
                {
                    "event_type": "message",
                    "timestamp": timestamp.isoformat(),
                    "channel": channel,
                    "user_id": "user_001",
                    "summary": random.choice(message_summaries),
                    "details": None,
                    "severity": "info",
                }
            )

    # Generate sample task events over 7 days
    task_summaries = [
        "Completed: Review email inbox",
        "Completed: Prepare meeting notes",
        "Completed: Update project status",
        "Completed: Send follow-up messages",
        "Completed: Organize daily schedule",
        "Started: Research topic",
        "Started: Draft document outline",
        "Blocked: Waiting for response",
    ]

    for day in range(7):
        day_start = now - timedelta(days=6 - day)
        num_tasks = random.randint(3, 8)

        for _ in range(num_tasks):
            hour = random.randint(9, 20)
            minute = random.randint(0, 59)
            timestamp = day_start.replace(hour=hour, minute=minute, second=random.randint(0, 59))

            summary = random.choice(task_summaries)
            severity = "warning" if "Blocked" in summary else "info"

            events.append(
                {
                    "event_type": "task",
                    "timestamp": timestamp.isoformat(),
                    "channel": None,
                    "user_id": "user_001",
                    "summary": summary,
                    "details": json.dumps({"task_id": f"task_{random.randint(100, 999)}"}),
                    "severity": severity,
                }
            )

    # Add a few error events
    error_summaries = [
        "API rate limit temporarily exceeded",
        "Telegram connection timeout - reconnected",
        "Failed to parse message format",
    ]

    for _ in range(random.randint(2, 5)):
        timestamp = now - timedelta(days=random.randint(0, 6), hours=random.randint(1, 20))
        events.append(
            {
                "event_type": "error",
                "timestamp": timestamp.isoformat(),
                "channel": random.choice(channels + [None]),
                "user_id": None,
                "summary": random.choice(error_summaries),
                "details": json.dumps({"error_code": random.choice(["429", "TIMEOUT", "PARSE_ERROR"])}),
                "severity": "error",
            }
        )

    # Insert all events
    for event in events:
        cursor.execute(
            """
            INSERT INTO dashboard_events
            (event_type, timestamp, channel, user_id, summary, details, severity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                event["event_type"],
                event["timestamp"],
                event["channel"],
                event["user_id"],
                event["summary"],
                event["details"],
                event["severity"],
            ),
        )

    conn.commit()
    return len(events)


def seed_metrics(conn: sqlite3.Connection) -> int:
    """Seed dashboard_metrics table with 7 days of hourly data."""
    cursor = conn.cursor()
    now = datetime.now()
    metrics = []

    # Generate hourly metrics for 7 days
    for day in range(7):
        day_start = now - timedelta(days=6 - day)

        for hour in range(24):
            timestamp = day_start.replace(hour=hour, minute=0, second=0, microsecond=0)

            # Skip future hours on the current day
            if timestamp > now:
                continue

            # Activity during work hours (8am-10pm) is higher
            is_active_hour = 8 <= hour <= 22
            activity_multiplier = 1.0 if is_active_hour else 0.1

            # Messages per hour (varies by time of day)
            base_messages = random.randint(2, 8) if is_active_hour else random.randint(0, 1)
            messages = int(base_messages * activity_multiplier)

            if messages > 0:
                metrics.append(
                    {
                        "metric_name": "messages_count",
                        "metric_value": messages,
                        "timestamp": timestamp.isoformat(),
                        "labels": json.dumps({"channel": random.choice(["telegram", "discord", "slack"])}),
                    }
                )

            # Tasks per hour
            base_tasks = random.randint(0, 3) if is_active_hour else 0
            tasks = int(base_tasks * activity_multiplier)

            if tasks > 0:
                metrics.append(
                    {
                        "metric_name": "tasks_completed",
                        "metric_value": tasks,
                        "timestamp": timestamp.isoformat(),
                        "labels": None,
                    }
                )

            # API cost (roughly $0.01-0.05 per active hour)
            if is_active_hour and messages > 0:
                cost = round(random.uniform(0.01, 0.05) * activity_multiplier, 4)
                metrics.append(
                    {
                        "metric_name": "api_cost_usd",
                        "metric_value": cost,
                        "timestamp": timestamp.isoformat(),
                        "labels": json.dumps({"model": "claude-sonnet-4-20250514"}),
                    }
                )

            # Token usage
            if is_active_hour and messages > 0:
                input_tokens = random.randint(500, 2000)
                output_tokens = random.randint(200, 800)

                metrics.append(
                    {
                        "metric_name": "tokens_input",
                        "metric_value": input_tokens,
                        "timestamp": timestamp.isoformat(),
                        "labels": None,
                    }
                )
                metrics.append(
                    {
                        "metric_name": "tokens_output",
                        "metric_value": output_tokens,
                        "timestamp": timestamp.isoformat(),
                        "labels": None,
                    }
                )

            # Response time (ms)
            if is_active_hour and messages > 0:
                response_time = random.randint(500, 3000)
                metrics.append(
                    {
                        "metric_name": "response_time_ms",
                        "metric_value": response_time,
                        "timestamp": timestamp.isoformat(),
                        "labels": None,
                    }
                )

    # Insert all metrics
    for metric in metrics:
        cursor.execute(
            """
            INSERT INTO dashboard_metrics
            (metric_name, metric_value, timestamp, labels)
            VALUES (?, ?, ?, ?)
        """,
            (metric["metric_name"], metric["metric_value"], metric["timestamp"], metric["labels"]),
        )

    conn.commit()
    return len(metrics)


def seed_dex_state(conn: sqlite3.Connection) -> None:
    """Ensure dex_state is set to idle."""
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE dex_state SET
            state = 'idle',
            current_task = NULL,
            updated_at = ?
        WHERE id = 1
    """,
        (datetime.now().isoformat(),),
    )
    conn.commit()


def seed_activity_db() -> int:
    """Seed activity.db with sample completed tasks."""
    conn = get_db_connection(ACTIVITY_DB_PATH)
    cursor = conn.cursor()

    # Ensure tasks table exists
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            source TEXT,
            request TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            summary TEXT
        )
    """
    )

    # Check if already seeded
    cursor.execute("SELECT COUNT(*) as count FROM tasks")
    if cursor.fetchone()["count"] > 5:
        conn.close()
        return 0

    now = datetime.now()
    tasks = [
        {
            "id": "task_001",
            "source": "telegram",
            "request": "Help me organize my day",
            "status": "completed",
            "created_at": (now - timedelta(days=2)).isoformat(),
            "completed_at": (now - timedelta(days=2, hours=-1)).isoformat(),
            "summary": "Created daily schedule with 5 priority tasks",
        },
        {
            "id": "task_002",
            "source": "discord",
            "request": "Break down project planning into smaller tasks",
            "status": "completed",
            "created_at": (now - timedelta(days=1, hours=5)).isoformat(),
            "completed_at": (now - timedelta(days=1, hours=4)).isoformat(),
            "summary": "Decomposed into 12 subtasks with dependencies",
        },
        {
            "id": "task_003",
            "source": "telegram",
            "request": "What did I promise to do this week?",
            "status": "completed",
            "created_at": (now - timedelta(hours=8)).isoformat(),
            "completed_at": (now - timedelta(hours=7, minutes=45)).isoformat(),
            "summary": "Found 3 commitments: email reply, doc review, meeting prep",
        },
        {
            "id": "task_004",
            "source": "slack",
            "request": "Remind me about the team meeting tomorrow",
            "status": "completed",
            "created_at": (now - timedelta(hours=4)).isoformat(),
            "completed_at": (now - timedelta(hours=3, minutes=55)).isoformat(),
            "summary": "Set reminder for 10am team standup",
        },
        {
            "id": "task_005",
            "source": "telegram",
            "request": "Help me draft a response to this email",
            "status": "in_progress",
            "created_at": (now - timedelta(minutes=30)).isoformat(),
            "completed_at": None,
            "summary": None,
        },
    ]

    for task in tasks:
        cursor.execute(
            """
            INSERT OR REPLACE INTO tasks
            (id, source, request, status, created_at, completed_at, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task["id"],
                task["source"],
                task["request"],
                task["status"],
                task["created_at"],
                task["completed_at"],
                task["summary"],
            ),
        )

    conn.commit()
    conn.close()
    return len(tasks)


def seed_database(force: bool = False) -> dict:
    """
    Seed the dashboard database with initial data.

    Args:
        force: If True, clear existing data before seeding

    Returns:
        Dictionary with seeding results
    """
    results = {"success": True, "events": 0, "metrics": 0, "tasks": 0, "message": ""}

    # Connect to dashboard database
    conn = get_db_connection(DASHBOARD_DB_PATH)

    try:
        # Check if already seeded
        if not force and is_seeded(conn):
            results["message"] = "Database already seeded. Use --force to reseed."
            conn.close()
            return results

        # Clear if forcing
        if force:
            clear_data(conn)

        # Seed events
        print("  Seeding dashboard events...")
        results["events"] = seed_events(conn)

        # Seed metrics
        print("  Seeding dashboard metrics...")
        results["metrics"] = seed_metrics(conn)

        # Seed dex state
        print("  Setting dex state to idle...")
        seed_dex_state(conn)

        # Seed activity database
        print("  Seeding activity database...")
        results["tasks"] = seed_activity_db()

        results["message"] = (
            f"Seeded {results['events']} events, "
            f"{results['metrics']} metrics, "
            f"{results['tasks']} tasks"
        )

    except Exception as e:
        results["success"] = False
        results["message"] = f"Seeding failed: {e}"

    finally:
        conn.close()

    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Seed DexAI dashboard database")
    parser.add_argument("--force", action="store_true", help="Force reseed (clears existing data)")
    parser.add_argument("--check", action="store_true", help="Check if seeding is needed")
    args = parser.parse_args()

    print("DexAI Dashboard Database Seeding")
    print("=" * 40)

    if args.check:
        conn = get_db_connection(DASHBOARD_DB_PATH)
        seeded = is_seeded(conn)
        conn.close()
        status = "already seeded" if seeded else "needs seeding"
        print(f"Database status: {status}")
        return

    results = seed_database(force=args.force)

    if results["success"]:
        print(f"\n✓ {results['message']}")
    else:
        print(f"\n✗ {results['message']}")
        exit(1)


if __name__ == "__main__":
    main()
