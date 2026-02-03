"""
Tool: Office Digest Generator
Purpose: Generate ADHD-friendly daily summaries of Dex actions

Provides a concise, scannable summary of everything Dex did on behalf
of the user. Designed for ADHD users who need quick overviews.

Key Features:
- ADHD-friendly format (concise, scannable)
- Highlights notable actions and warnings
- Tracks undone actions (good catches!)
- Configurable delivery time and channel

Usage:
    python digest.py --account-id <id> --generate
    python digest.py --account-id <id> --generate --date 2026-02-02
    python digest.py --account-id <id> --send --channel email
    python digest.py --account-id <id> --schedule --time 20:00 --timezone America/New_York

Dependencies:
    - sqlite3 (standard library)
    - tools.automation.notify (optional, for sending)
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection


@dataclass
class DigestContent:
    """Content structure for daily digest."""

    date: datetime
    emails_sent: int
    emails_deleted: int
    emails_archived: int
    emails_drafted: int
    meetings_scheduled: int
    meetings_cancelled: int
    actions_undone: int
    total_actions: int
    highlights: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with serializable date."""
        result = asdict(self)
        result["date"] = self.date.isoformat()
        return result


def _format_digest_text(digest: DigestContent) -> str:
    """
    Format digest content as ADHD-friendly plain text.

    The format is designed to be:
    - Scannable (quick glance)
    - Positive framing
    - Action-oriented
    - Brief
    """
    date_str = digest.date.strftime("%B %d, %Y")
    lines = [
        f"Daily Dex Summary - {date_str}",
        "",
    ]

    # Check if any actions were taken
    if digest.total_actions == 0:
        lines.extend([
            "No actions taken today.",
            "",
            "I was here if you needed me!",
        ])
        return "\n".join(lines)

    # Main summary
    lines.append("Today I helped you with:")

    action_lines = []
    if digest.emails_sent > 0:
        action_lines.append(f"  - Sent {digest.emails_sent} email{'s' if digest.emails_sent != 1 else ''}")
    if digest.emails_drafted > 0:
        action_lines.append(f"  - Created {digest.emails_drafted} draft{'s' if digest.emails_drafted != 1 else ''}")
    if digest.meetings_scheduled > 0:
        action_lines.append(f"  - Scheduled {digest.meetings_scheduled} meeting{'s' if digest.meetings_scheduled != 1 else ''}")
    if digest.emails_archived > 0:
        action_lines.append(f"  - Archived {digest.emails_archived} email{'s' if digest.emails_archived != 1 else ''}")
    if digest.emails_deleted > 0:
        action_lines.append(f"  - Deleted {digest.emails_deleted} email{'s' if digest.emails_deleted != 1 else ''}")
    if digest.meetings_cancelled > 0:
        action_lines.append(f"  - Cancelled {digest.meetings_cancelled} meeting{'s' if digest.meetings_cancelled != 1 else ''}")

    if action_lines:
        lines.extend(action_lines)
    else:
        lines.append("  - Various actions")

    lines.append("")

    # Undone actions (positive framing)
    if digest.actions_undone > 0:
        if digest.actions_undone == 1:
            lines.append("You undid 1 action (good catch!)")
        else:
            lines.append(f"You undid {digest.actions_undone} actions (good catches!)")
        lines.append("")

    # Highlights
    if digest.highlights:
        lines.append("Highlights:")
        for highlight in digest.highlights[:3]:  # Limit to 3
            lines.append(f"  - {highlight}")
        lines.append("")

    # Warnings
    if digest.warnings:
        lines.append("Heads up:")
        for warning in digest.warnings[:3]:  # Limit to 3
            lines.append(f"  - {warning}")
        lines.append("")

    # Closing
    if not digest.warnings:
        lines.append("No issues to report.")

    return "\n".join(lines)


async def generate_digest(
    account_id: str,
    date: str | None = None,
) -> dict[str, Any]:
    """
    Generate a daily digest of all Dex actions.

    Args:
        account_id: Office account ID
        date: Date to generate digest for (ISO format, defaults to today)

    Returns:
        {
            "success": bool,
            "digest": DigestContent (as dict),
            "formatted": str (ADHD-friendly text),
        }
    """
    # Parse date
    if date:
        target_date = datetime.fromisoformat(date)
    else:
        target_date = datetime.now()

    # Calculate date range (start and end of day)
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    conn = get_connection()
    cursor = conn.cursor()

    # Get action counts by type
    cursor.execute(
        """
        SELECT action_type, COUNT(*) as count
        FROM office_audit_log
        WHERE account_id = ? AND created_at >= ? AND created_at < ?
        GROUP BY action_type
        """,
        (account_id, start_of_day.isoformat(), end_of_day.isoformat()),
    )
    type_counts = {row["action_type"]: row["count"] for row in cursor.fetchall()}

    # Get undone count
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM office_audit_log
        WHERE account_id = ? AND created_at >= ? AND created_at < ? AND result = 'undone'
        """,
        (account_id, start_of_day.isoformat(), end_of_day.isoformat()),
    )
    undone_count = cursor.fetchone()["count"]

    # Get total actions
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM office_audit_log
        WHERE account_id = ? AND created_at >= ? AND created_at < ?
        """,
        (account_id, start_of_day.isoformat(), end_of_day.isoformat()),
    )
    total_actions = cursor.fetchone()["count"]

    # Get notable actions for highlights (success only, limit to 5)
    cursor.execute(
        """
        SELECT action_summary
        FROM office_audit_log
        WHERE account_id = ? AND created_at >= ? AND created_at < ?
              AND result = 'success'
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (account_id, start_of_day.isoformat(), end_of_day.isoformat()),
    )
    recent_summaries = [row["action_summary"] for row in cursor.fetchall()]

    # Get failed actions for warnings
    cursor.execute(
        """
        SELECT action_summary
        FROM office_audit_log
        WHERE account_id = ? AND created_at >= ? AND created_at < ?
              AND result = 'failed'
        ORDER BY created_at DESC
        LIMIT 3
        """,
        (account_id, start_of_day.isoformat(), end_of_day.isoformat()),
    )
    failed_actions = [f"Failed: {row['action_summary']}" for row in cursor.fetchall()]

    conn.close()

    # Build digest content
    digest = DigestContent(
        date=target_date,
        emails_sent=type_counts.get("email_send", 0),
        emails_deleted=type_counts.get("email_delete", 0),
        emails_archived=type_counts.get("email_archive", 0),
        emails_drafted=type_counts.get("email_draft", 0),
        meetings_scheduled=type_counts.get("meeting_schedule", 0),
        meetings_cancelled=type_counts.get("meeting_cancel", 0),
        actions_undone=undone_count,
        total_actions=total_actions,
        highlights=recent_summaries[:3],  # Top 3 recent actions
        warnings=failed_actions,
    )

    formatted = _format_digest_text(digest)

    return {
        "success": True,
        "digest": digest.to_dict(),
        "formatted": formatted,
    }


async def send_digest(
    account_id: str,
    channel: str = "primary",
    date: str | None = None,
) -> dict[str, Any]:
    """
    Generate and send the daily digest.

    Args:
        account_id: Office account ID
        channel: Delivery channel (primary, email, sms, etc.)
        date: Date to generate digest for (defaults to today)

    Returns:
        {
            "success": bool,
            "sent_via": str,
            "digest": dict,
        }
    """
    # Generate the digest
    result = await generate_digest(account_id, date)
    if not result.get("success"):
        return result

    formatted = result["formatted"]
    digest = result["digest"]

    # Get user_id from account
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": f"Account not found: {account_id}"}

    user_id = row["user_id"]

    # Try to send via notification system
    try:
        from tools.automation.notify import queue_notification, send_notification

        notification_id = queue_notification(
            user_id=user_id,
            content=formatted,
            priority="low",
            channel=channel if channel != "primary" else None,
            source="daily_digest",
        )

        send_result = await send_notification(notification_id)

        if send_result.get("success"):
            return {
                "success": True,
                "sent_via": send_result.get("channel", channel),
                "digest": digest,
            }
        else:
            # Notification queued but not sent immediately
            return {
                "success": True,
                "sent_via": "queued",
                "notification_id": notification_id,
                "digest": digest,
                "message": "Digest queued for delivery",
            }

    except ImportError:
        # Notification system not available - return the digest content
        return {
            "success": True,
            "sent_via": "prepared",
            "digest": digest,
            "formatted": formatted,
            "message": "Digest prepared (notification system not available)",
        }


async def schedule_digest(
    account_id: str,
    send_time: str = "20:00",
    timezone: str = "UTC",
) -> dict[str, Any]:
    """
    Schedule daily digest delivery.

    This stores the schedule preference. Actual scheduling is handled
    by the automation scheduler.

    Args:
        account_id: Office account ID
        send_time: Time to send digest (HH:MM format)
        timezone: Timezone for send_time

    Returns:
        {
            "success": bool,
            "scheduled": {
                "send_time": str,
                "timezone": str,
            }
        }
    """
    # Validate time format
    try:
        datetime.strptime(send_time, "%H:%M")
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid time format: {send_time}. Use HH:MM format.",
        }

    # Store schedule in account settings
    conn = get_connection()
    cursor = conn.cursor()

    # Check if account exists
    cursor.execute(
        "SELECT id FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Account not found: {account_id}"}

    # Store digest schedule in a settings table or as JSON in account
    # For now, we'll use a simple approach with a dedicated table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_digest_settings (
            account_id TEXT PRIMARY KEY,
            send_time TEXT NOT NULL,
            timezone TEXT DEFAULT 'UTC',
            enabled BOOLEAN DEFAULT TRUE,
            last_sent_date TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id)
        )
    """)

    cursor.execute(
        """
        INSERT OR REPLACE INTO office_digest_settings (account_id, send_time, timezone, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (account_id, send_time, timezone, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "scheduled": {
            "send_time": send_time,
            "timezone": timezone,
        },
        "message": f"Digest scheduled for {send_time} {timezone} daily",
    }


async def get_digest_settings(account_id: str) -> dict[str, Any]:
    """
    Get current digest schedule settings.

    Args:
        account_id: Office account ID

    Returns:
        {
            "success": bool,
            "settings": dict or None,
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if settings table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='office_digest_settings'
    """)
    if not cursor.fetchone():
        conn.close()
        return {"success": True, "settings": None}

    cursor.execute(
        "SELECT * FROM office_digest_settings WHERE account_id = ?",
        (account_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "success": True,
            "settings": dict(row),
        }
    else:
        return {"success": True, "settings": None}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Office Digest Generator for ADHD-friendly summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate today's digest
  python digest.py --account-id abc123 --generate

  # Generate digest for a specific date
  python digest.py --account-id abc123 --generate --date 2026-02-02

  # Send the digest
  python digest.py --account-id abc123 --send --channel email

  # Schedule daily digest
  python digest.py --account-id abc123 --schedule --time 20:00 --timezone America/New_York

  # View current schedule settings
  python digest.py --account-id abc123 --settings
        """,
    )

    parser.add_argument("--account-id", required=True, help="Office account ID")

    # Actions (mutually exclusive)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--generate", action="store_true", help="Generate digest")
    actions.add_argument("--send", action="store_true", help="Generate and send digest")
    actions.add_argument("--schedule", action="store_true", help="Schedule daily digest")
    actions.add_argument("--settings", action="store_true", help="View digest settings")

    # Options
    parser.add_argument("--date", help="Date for digest (ISO format, defaults to today)")
    parser.add_argument("--channel", default="primary", help="Delivery channel for --send")
    parser.add_argument("--time", default="20:00", help="Send time for --schedule (HH:MM)")
    parser.add_argument("--timezone", default="UTC", help="Timezone for --schedule")

    args = parser.parse_args()

    result = None

    if args.generate:
        result = asyncio.run(generate_digest(args.account_id, args.date))
        if result.get("success"):
            # Print the formatted digest
            print(result["formatted"])
            print()

    elif args.send:
        result = asyncio.run(send_digest(args.account_id, args.channel, args.date))

    elif args.schedule:
        result = asyncio.run(schedule_digest(args.account_id, args.time, args.timezone))

    elif args.settings:
        result = asyncio.run(get_digest_settings(args.account_id))

    if result:
        if result.get("success"):
            print("OK")
        else:
            print(f"ERROR: {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
