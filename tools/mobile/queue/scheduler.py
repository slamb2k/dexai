"""
Tool: Notification Scheduler
Purpose: Schedule notifications respecting user preferences and flow state

Usage:
    from tools.mobile.queue.scheduler import (
        can_send_now,
        get_next_send_window,
        is_in_quiet_hours,
        check_rate_limit,
    )

ADHD-Specific Design:
    - Flow state protection: Don't interrupt hyperfocus
    - Quiet hours: Automatic DND
    - Rate limiting: Prevent notification fatigue
    - Transition buffer: Wait after task switches
"""

import asyncio
from datetime import datetime, timedelta, time
from typing import Any
from zoneinfo import ZoneInfo

from tools.mobile import get_connection
from tools.mobile.preferences.user_preferences import get_preferences


async def can_send_now(user_id: str, priority: int) -> dict:
    """
    Check if we can send a notification right now.

    Checks (in order):
    1. User has notifications enabled
    2. Not in quiet hours (unless high priority)
    3. Not in flow state (unless priority >= threshold)
    4. Rate limits not exceeded

    Args:
        user_id: The user ID
        priority: Notification priority (1-10)

    Returns:
        {
            "can_send": bool,
            "reason": str | None,
            "retry_at": datetime | None,
        }
    """
    # Get user preferences
    prefs = await get_preferences(user_id)

    # Check if notifications are enabled
    if not prefs.get("enabled", True):
        return {
            "can_send": False,
            "reason": "notifications_disabled",
            "retry_at": None,
        }

    # Check quiet hours (high priority can bypass)
    if priority < 9:  # Only priority 9+ can bypass quiet hours
        quiet_check = await is_in_quiet_hours(user_id)
        if quiet_check["in_quiet_hours"]:
            return {
                "can_send": False,
                "reason": "quiet_hours",
                "retry_at": quiet_check.get("ends_at"),
            }

    # Check flow state
    if prefs.get("respect_flow_state", True):
        flow_threshold = prefs.get("flow_interrupt_threshold", 8)
        if priority < flow_threshold:
            flow_check = await _check_flow_state(user_id)
            if flow_check.get("in_flow"):
                return {
                    "can_send": False,
                    "reason": "flow_state",
                    "retry_at": flow_check.get("expected_end"),
                }

    # Check rate limits
    rate_check = await check_rate_limit(user_id)
    if not rate_check["allowed"]:
        return {
            "can_send": False,
            "reason": "rate_limit",
            "retry_at": rate_check.get("reset_at"),
        }

    return {
        "can_send": True,
        "reason": None,
        "retry_at": None,
    }


async def get_next_send_window(user_id: str) -> datetime:
    """
    Get the next time we can send non-urgent notifications.

    Considers quiet hours and rate limits.

    Args:
        user_id: The user ID

    Returns:
        datetime when notifications can be sent
    """
    prefs = await get_preferences(user_id)
    now = datetime.now()

    # Check quiet hours
    quiet_check = await is_in_quiet_hours(user_id)
    if quiet_check["in_quiet_hours"]:
        return quiet_check["ends_at"]

    # Check rate limit
    rate_check = await check_rate_limit(user_id)
    if not rate_check["allowed"]:
        return rate_check["reset_at"]

    # Can send now
    return now


async def is_in_quiet_hours(user_id: str) -> dict:
    """
    Check if user is currently in quiet hours.

    Args:
        user_id: The user ID

    Returns:
        {
            "in_quiet_hours": bool,
            "starts_at": time | None,
            "ends_at": datetime | None,
        }
    """
    prefs = await get_preferences(user_id)

    quiet_start = prefs.get("quiet_hours_start")
    quiet_end = prefs.get("quiet_hours_end")

    if not quiet_start or not quiet_end:
        return {
            "in_quiet_hours": False,
            "starts_at": None,
            "ends_at": None,
        }

    # Parse times
    try:
        start_time = time.fromisoformat(quiet_start)
        end_time = time.fromisoformat(quiet_end)
    except ValueError:
        return {
            "in_quiet_hours": False,
            "starts_at": None,
            "ends_at": None,
        }

    # Get user's timezone
    tz_str = prefs.get("timezone", "UTC")
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)
    current_time = now.time()

    # Check if in quiet hours
    # Handle overnight quiet hours (e.g., 22:00 - 08:00)
    if start_time <= end_time:
        # Same day range
        in_quiet = start_time <= current_time <= end_time
    else:
        # Overnight range
        in_quiet = current_time >= start_time or current_time <= end_time

    if not in_quiet:
        return {
            "in_quiet_hours": False,
            "starts_at": start_time,
            "ends_at": None,
        }

    # Calculate when quiet hours end
    today = now.date()
    if start_time <= end_time:
        # Same day - ends today
        ends_at = datetime.combine(today, end_time, tzinfo=tz)
    else:
        # Overnight - ends tomorrow if past midnight, today if before midnight
        if current_time >= start_time:
            # Before midnight - ends tomorrow
            tomorrow = today + timedelta(days=1)
            ends_at = datetime.combine(tomorrow, end_time, tzinfo=tz)
        else:
            # After midnight - ends today
            ends_at = datetime.combine(today, end_time, tzinfo=tz)

    return {
        "in_quiet_hours": True,
        "starts_at": start_time,
        "ends_at": ends_at,
    }


async def check_rate_limit(user_id: str) -> dict:
    """
    Check if user has exceeded notification rate limits.

    ADHD-specific: Limits notifications to prevent fatigue.

    Args:
        user_id: The user ID

    Returns:
        {
            "allowed": bool,
            "sent_this_hour": int,
            "limit": int,
            "reset_at": datetime,
        }
    """
    prefs = await get_preferences(user_id)

    max_per_hour = prefs.get("max_notifications_per_hour", 6)
    cooldown_minutes = prefs.get("cooldown_after_burst_minutes", 30)

    # Count notifications sent in the last hour
    conn = get_connection()
    cursor = conn.cursor()

    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()

    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM notification_delivery_log
        WHERE subscription_id IN (
            SELECT id FROM push_subscriptions WHERE user_id = ?
        )
        AND sent_at > ?
        AND status IN ('sent', 'delivered', 'clicked', 'batched')
        """,
        (user_id, one_hour_ago),
    )

    row = cursor.fetchone()
    sent_this_hour = row["count"] if row else 0
    conn.close()

    if sent_this_hour >= max_per_hour:
        # Check if in cooldown
        reset_at = datetime.now() + timedelta(minutes=cooldown_minutes)
        return {
            "allowed": False,
            "sent_this_hour": sent_this_hour,
            "limit": max_per_hour,
            "reset_at": reset_at,
        }

    return {
        "allowed": True,
        "sent_this_hour": sent_this_hour,
        "limit": max_per_hour,
        "reset_at": None,
    }


async def _check_flow_state(user_id: str) -> dict:
    """
    Check if user is currently in a flow state.

    Integrates with the ADHD flow detector if available.

    Args:
        user_id: The user ID

    Returns:
        {
            "in_flow": bool,
            "expected_end": datetime | None,
        }
    """
    try:
        # Try to import flow detector from ADHD tools
        from tools.adhd.flow_detector import get_flow_state

        flow_state = await get_flow_state(user_id)

        if flow_state and flow_state.get("in_flow"):
            return {
                "in_flow": True,
                "expected_end": flow_state.get("expected_end"),
            }
    except ImportError:
        # Flow detector not available - assume not in flow
        pass
    except Exception:
        # Error checking flow state - err on the side of not interrupting
        pass

    return {
        "in_flow": False,
        "expected_end": None,
    }


async def get_send_schedule(
    user_id: str,
    hours_ahead: int = 24,
) -> list[dict]:
    """
    Get the notification send schedule for upcoming hours.

    Shows when notifications can be sent based on quiet hours.

    Args:
        user_id: The user ID
        hours_ahead: How many hours to look ahead

    Returns:
        List of time windows with send availability
    """
    prefs = await get_preferences(user_id)

    quiet_start = prefs.get("quiet_hours_start")
    quiet_end = prefs.get("quiet_hours_end")

    tz_str = prefs.get("timezone", "UTC")
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)
    schedule = []

    for hour in range(hours_ahead):
        check_time = now + timedelta(hours=hour)

        # Check if in quiet hours
        in_quiet = False
        if quiet_start and quiet_end:
            try:
                start_time = time.fromisoformat(quiet_start)
                end_time = time.fromisoformat(quiet_end)
                check_t = check_time.time()

                if start_time <= end_time:
                    in_quiet = start_time <= check_t <= end_time
                else:
                    in_quiet = check_t >= start_time or check_t <= end_time
            except ValueError:
                pass

        schedule.append({
            "time": check_time.isoformat(),
            "can_send": not in_quiet,
            "quiet_hours": in_quiet,
        })

    return schedule
