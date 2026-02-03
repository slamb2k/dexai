"""
Tool: Emergency Pause System
Purpose: Instantly stop all autonomous actions for an account

Provides immediate control over automation with pause/resume functionality.
Critical for ADHD users who may need to quickly stop all automation when
overwhelmed or when things go wrong.

Usage:
    from tools.office.automation.emergency import (
        emergency_pause,
        resume_automation,
        get_pause_status,
        schedule_pause,
        check_pause_status,
        auto_pause_on_failures,
    )

    # Immediately pause all automation
    result = await emergency_pause("account-123", reason="Taking a break")

    # Resume automation
    result = await resume_automation("account-123")

    # Check if paused (synchronous, for quick checks)
    is_paused = check_pause_status("account-123")

Emergency Triggers:
    - Dashboard "Emergency Stop" button (big, red, always visible)
    - Channel command: !pause or !stop dex
    - Keyboard shortcut: Ctrl+Shift+P
    - API endpoint for integrations

When Paused:
    - No new policy executions
    - Pending actions in queue continue (already committed)
    - User notified via all channels
    - Dashboard shows prominent "PAUSED" indicator

CLI:
    python tools/office/automation/emergency.py --account-id <id> --pause --reason "Taking a break"
    python tools/office/automation/emergency.py --account-id <id> --pause --hours 4
    python tools/office/automation/emergency.py --account-id <id> --resume
    python tools/office/automation/emergency.py --account-id <id> --status
    python tools/office/automation/emergency.py --account-id <id> --schedule --start "2024-01-15 22:00" --end "2024-01-16 08:00"
    python tools/office/automation/emergency.py --account-id <id> --list-schedules
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection


def _ensure_emergency_tables() -> None:
    """Create emergency state tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Check if old schema exists and migrate if needed
    cursor.execute("PRAGMA table_info(office_emergency_state)")
    columns = {row[1] for row in cursor.fetchall()}

    if columns and "id" not in columns:
        # Old schema exists - migrate by dropping and recreating
        # This is safe for development; production would need proper migration
        cursor.execute("DROP TABLE IF EXISTS office_emergency_state")
        conn.commit()

    # Emergency pause state
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_emergency_state (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL UNIQUE,
            is_paused BOOLEAN DEFAULT FALSE,
            paused_at DATETIME,
            paused_until DATETIME,
            reason TEXT,
            pause_type TEXT DEFAULT 'manual',
            failure_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Scheduled pauses
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_scheduled_pauses (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'scheduled',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id)
        )
    """)

    # Indexes
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_emergency_account "
        "ON office_emergency_state(account_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_pauses_account "
        "ON office_scheduled_pauses(account_id, start_time)"
    )

    conn.commit()


def _get_or_create_state(account_id: str) -> dict[str, Any]:
    """Get or create emergency state record for an account."""
    _ensure_emergency_tables()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM office_emergency_state WHERE account_id = ?",
        (account_id,),
    )
    row = cursor.fetchone()

    if row:
        return dict(row)

    # Create new state record
    state_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO office_emergency_state (id, account_id, is_paused, failure_count)
        VALUES (?, ?, FALSE, 0)
        """,
        (state_id, account_id),
    )
    conn.commit()

    return {
        "id": state_id,
        "account_id": account_id,
        "is_paused": False,
        "paused_at": None,
        "paused_until": None,
        "reason": None,
        "pause_type": "manual",
        "failure_count": 0,
    }


async def emergency_pause(
    account_id: str,
    reason: str = "User requested",
    duration_hours: int | None = None,
) -> dict[str, Any]:
    """
    Instantly pause all automation for an account.

    Args:
        account_id: Account to pause
        reason: Human-readable reason for the pause
        duration_hours: Hours to pause (None = until manual resume)

    Returns:
        dict with success status and pause details
    """
    _ensure_emergency_tables()
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()
    paused_until = None

    if duration_hours is not None:
        paused_until = now + timedelta(hours=duration_hours)

    # Get or create state
    _get_or_create_state(account_id)

    # Update to paused
    cursor.execute(
        """
        UPDATE office_emergency_state
        SET is_paused = TRUE,
            paused_at = ?,
            paused_until = ?,
            reason = ?,
            pause_type = 'manual',
            updated_at = ?
        WHERE account_id = ?
        """,
        (
            now.isoformat(),
            paused_until.isoformat() if paused_until else None,
            reason,
            now.isoformat(),
            account_id,
        ),
    )
    conn.commit()

    return {
        "success": True,
        "account_id": account_id,
        "is_paused": True,
        "paused_at": now.isoformat(),
        "paused_until": paused_until.isoformat() if paused_until else None,
        "reason": reason,
    }


async def resume_automation(account_id: str) -> dict[str, Any]:
    """
    Resume automation after pause.

    Args:
        account_id: Account to resume

    Returns:
        dict with success status and pause duration
    """
    _ensure_emergency_tables()
    conn = get_connection()
    cursor = conn.cursor()

    # Get current state
    state = _get_or_create_state(account_id)

    if not state.get("is_paused"):
        return {
            "success": True,
            "account_id": account_id,
            "message": "Automation was not paused",
            "paused_duration": None,
        }

    now = datetime.now()
    paused_at = state.get("paused_at")
    paused_duration = None

    if paused_at:
        paused_dt = datetime.fromisoformat(paused_at)
        duration = now - paused_dt
        paused_duration = str(duration)

    # Update to resumed
    cursor.execute(
        """
        UPDATE office_emergency_state
        SET is_paused = FALSE,
            paused_at = NULL,
            paused_until = NULL,
            reason = NULL,
            failure_count = 0,
            updated_at = ?
        WHERE account_id = ?
        """,
        (now.isoformat(), account_id),
    )
    conn.commit()

    return {
        "success": True,
        "account_id": account_id,
        "is_paused": False,
        "resumed_at": now.isoformat(),
        "paused_duration": paused_duration,
    }


async def get_pause_status(account_id: str) -> dict[str, Any]:
    """
    Get current pause state for an account.

    Args:
        account_id: Account to check

    Returns:
        dict with pause status details
    """
    state = _get_or_create_state(account_id)

    # Check if timed pause has expired
    is_paused = state.get("is_paused", False)
    paused_until = state.get("paused_until")

    if is_paused and paused_until:
        paused_until_dt = datetime.fromisoformat(paused_until)
        if datetime.now() >= paused_until_dt:
            # Auto-resume expired timed pause
            await resume_automation(account_id)
            is_paused = False
            paused_until = None

    return {
        "success": True,
        "account_id": account_id,
        "is_paused": is_paused,
        "paused_at": state.get("paused_at"),
        "paused_until": paused_until,
        "reason": state.get("reason") if is_paused else None,
        "pause_type": state.get("pause_type") if is_paused else None,
        "failure_count": state.get("failure_count", 0),
    }


async def schedule_pause(
    account_id: str,
    start_time: datetime,
    end_time: datetime,
    reason: str = "Scheduled pause",
) -> dict[str, Any]:
    """
    Pre-schedule a pause period.

    Useful for known focus periods, meetings, or off-hours.

    Args:
        account_id: Account to schedule pause for
        start_time: When to start the pause
        end_time: When to end the pause
        reason: Human-readable reason

    Returns:
        dict with schedule details
    """
    _ensure_emergency_tables()

    if end_time <= start_time:
        return {
            "success": False,
            "error": "End time must be after start time",
        }

    conn = get_connection()
    cursor = conn.cursor()

    schedule_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO office_scheduled_pauses (id, account_id, start_time, end_time, reason)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            schedule_id,
            account_id,
            start_time.isoformat(),
            end_time.isoformat(),
            reason,
        ),
    )
    conn.commit()

    return {
        "success": True,
        "schedule_id": schedule_id,
        "account_id": account_id,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "reason": reason,
        "status": "scheduled",
    }


def check_pause_status(account_id: str) -> bool:
    """
    Quick synchronous check if automation is paused.

    Use this for fast checks in hot paths. For full details,
    use get_pause_status() instead.

    Args:
        account_id: Account to check

    Returns:
        True if automation is paused, False otherwise
    """
    _ensure_emergency_tables()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT is_paused, paused_until FROM office_emergency_state WHERE account_id = ?",
        (account_id,),
    )
    row = cursor.fetchone()

    if not row:
        return False

    is_paused = row["is_paused"]
    paused_until = row["paused_until"]

    # If timed pause, check if expired
    if is_paused and paused_until:
        paused_until_dt = datetime.fromisoformat(paused_until)
        if datetime.now() >= paused_until_dt:
            return False

    # Check scheduled pauses
    now = datetime.now().isoformat()
    cursor.execute(
        """
        SELECT id FROM office_scheduled_pauses
        WHERE account_id = ?
          AND start_time <= ?
          AND end_time > ?
          AND status = 'scheduled'
        LIMIT 1
        """,
        (account_id, now, now),
    )

    if cursor.fetchone():
        return True

    return bool(is_paused)


async def auto_pause_on_failures(
    account_id: str,
    failure_count: int,
    threshold: int = 5,
) -> dict[str, Any]:
    """
    Automatically pause if too many failures occur.

    Protects against runaway automation that keeps failing.

    Args:
        account_id: Account to check
        failure_count: Number of recent failures
        threshold: Number of failures before auto-pause

    Returns:
        dict with pause status (if triggered)
    """
    _ensure_emergency_tables()
    conn = get_connection()
    cursor = conn.cursor()

    # Get or create state
    state = _get_or_create_state(account_id)

    # Update failure count
    cursor.execute(
        """
        UPDATE office_emergency_state
        SET failure_count = ?,
            updated_at = ?
        WHERE account_id = ?
        """,
        (failure_count, datetime.now().isoformat(), account_id),
    )
    conn.commit()

    # Check if threshold exceeded
    if failure_count >= threshold:
        reason = f"Auto-paused: {failure_count} failures exceeded threshold of {threshold}"

        now = datetime.now()
        # Auto-pause for 1 hour by default
        paused_until = now + timedelta(hours=1)

        cursor.execute(
            """
            UPDATE office_emergency_state
            SET is_paused = TRUE,
                paused_at = ?,
                paused_until = ?,
                reason = ?,
                pause_type = 'auto',
                updated_at = ?
            WHERE account_id = ?
            """,
            (
                now.isoformat(),
                paused_until.isoformat(),
                reason,
                now.isoformat(),
                account_id,
            ),
        )
        conn.commit()

        return {
            "success": True,
            "auto_paused": True,
            "account_id": account_id,
            "failure_count": failure_count,
            "threshold": threshold,
            "paused_until": paused_until.isoformat(),
            "reason": reason,
        }

    return {
        "success": True,
        "auto_paused": False,
        "account_id": account_id,
        "failure_count": failure_count,
        "threshold": threshold,
        "remaining_before_pause": threshold - failure_count,
    }


async def get_scheduled_pauses(account_id: str) -> dict[str, Any]:
    """
    Get all scheduled pauses for an account.

    Args:
        account_id: Account to get schedules for

    Returns:
        dict with list of scheduled pauses
    """
    _ensure_emergency_tables()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM office_scheduled_pauses
        WHERE account_id = ?
        ORDER BY start_time ASC
        """,
        (account_id,),
    )
    rows = cursor.fetchall()

    schedules = [dict(row) for row in rows]

    return {
        "success": True,
        "account_id": account_id,
        "schedules": schedules,
        "count": len(schedules),
    }


async def cancel_scheduled_pause(schedule_id: str) -> dict[str, Any]:
    """
    Cancel a scheduled pause.

    Args:
        schedule_id: ID of the scheduled pause to cancel

    Returns:
        dict with cancellation result
    """
    _ensure_emergency_tables()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM office_scheduled_pauses WHERE id = ?",
        (schedule_id,),
    )
    row = cursor.fetchone()

    if not row:
        return {
            "success": False,
            "error": f"Scheduled pause {schedule_id} not found",
        }

    cursor.execute(
        "UPDATE office_scheduled_pauses SET status = 'cancelled' WHERE id = ?",
        (schedule_id,),
    )
    conn.commit()

    return {
        "success": True,
        "schedule_id": schedule_id,
        "status": "cancelled",
    }


def main() -> None:
    """CLI entry point for the emergency pause system."""
    parser = argparse.ArgumentParser(
        description="Emergency Pause System for Office Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Pause automation indefinitely
  python emergency.py --account-id <id> --pause --reason "Taking a break"

  # Pause for 4 hours
  python emergency.py --account-id <id> --pause --hours 4

  # Resume automation
  python emergency.py --account-id <id> --resume

  # Check status
  python emergency.py --account-id <id> --status

  # Schedule a pause
  python emergency.py --account-id <id> --schedule --start "2024-01-15 22:00" --end "2024-01-16 08:00"
        """,
    )

    parser.add_argument("--account-id", required=True, help="Account ID")

    # Actions (mutually exclusive)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--pause", action="store_true", help="Pause automation")
    actions.add_argument("--resume", action="store_true", help="Resume automation")
    actions.add_argument("--status", action="store_true", help="Get pause status")
    actions.add_argument(
        "--schedule", action="store_true", help="Schedule a pause period"
    )
    actions.add_argument(
        "--list-schedules", action="store_true", help="List scheduled pauses"
    )

    # Pause options
    parser.add_argument(
        "--reason",
        default="User requested",
        help="Reason for pause",
    )
    parser.add_argument(
        "--hours",
        type=int,
        help="Duration in hours (omit for indefinite pause)",
    )

    # Schedule options
    parser.add_argument(
        "--start",
        help="Schedule start time (YYYY-MM-DD HH:MM)",
    )
    parser.add_argument(
        "--end",
        help="Schedule end time (YYYY-MM-DD HH:MM)",
    )

    args = parser.parse_args()
    result = None

    if args.pause:
        result = asyncio.run(
            emergency_pause(
                args.account_id,
                reason=args.reason,
                duration_hours=args.hours,
            )
        )

    elif args.resume:
        result = asyncio.run(resume_automation(args.account_id))

    elif args.status:
        result = asyncio.run(get_pause_status(args.account_id))

    elif args.schedule:
        if not args.start or not args.end:
            parser.error("--schedule requires --start and --end times")

        start_time = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(args.end, "%Y-%m-%d %H:%M")
        result = asyncio.run(
            schedule_pause(
                args.account_id,
                start_time=start_time,
                end_time=end_time,
                reason=args.reason,
            )
        )

    elif args.list_schedules:
        result = asyncio.run(get_scheduled_pauses(args.account_id))

    if result:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
