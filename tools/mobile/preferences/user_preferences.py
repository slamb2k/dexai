"""
Tool: User Notification Preferences
Purpose: Manage per-user notification settings

Usage:
    from tools.mobile.preferences.user_preferences import (
        get_preferences,
        update_preferences,
        set_quiet_hours,
        set_category_preference,
    )

ADHD-Specific Design:
    - Sensible defaults that minimize interruptions
    - Easy quiet hours configuration
    - Per-category control for granularity
"""

import asyncio
import json
from datetime import datetime
from typing import Any

from tools.mobile import get_connection
from tools.mobile.models import UserPreferences


# Default preferences optimized for ADHD
DEFAULT_PREFERENCES = {
    "enabled": True,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "08:00",
    "timezone": "UTC",
    "category_settings": {},
    "respect_flow_state": True,
    "flow_interrupt_threshold": 8,
    "batch_notifications": True,
    "batch_window_minutes": 5,
    "max_notifications_per_hour": 6,
    "cooldown_after_burst_minutes": 30,
}


async def get_preferences(user_id: str) -> dict:
    """
    Get user's notification preferences with defaults.

    Args:
        user_id: The user ID

    Returns:
        Preferences dict with all fields
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM notification_preferences WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        # Return defaults
        return {**DEFAULT_PREFERENCES, "user_id": user_id}

    prefs = dict(row)

    # Parse category_settings JSON
    if prefs.get("category_settings"):
        try:
            prefs["category_settings"] = json.loads(prefs["category_settings"])
        except (json.JSONDecodeError, TypeError):
            prefs["category_settings"] = {}
    else:
        prefs["category_settings"] = {}

    # Fill in any missing defaults
    for key, default_value in DEFAULT_PREFERENCES.items():
        if key not in prefs or prefs[key] is None:
            prefs[key] = default_value

    return prefs


async def update_preferences(user_id: str, **updates) -> dict:
    """
    Update user preferences.

    Args:
        user_id: The user ID
        **updates: Fields to update

    Returns:
        {"success": True, "preferences": dict} or {"success": False, "error": str}
    """
    # Validate updates
    valid_fields = {
        "enabled",
        "quiet_hours_start",
        "quiet_hours_end",
        "timezone",
        "category_settings",
        "respect_flow_state",
        "flow_interrupt_threshold",
        "batch_notifications",
        "batch_window_minutes",
        "max_notifications_per_hour",
        "cooldown_after_burst_minutes",
    }

    invalid_fields = set(updates.keys()) - valid_fields
    if invalid_fields:
        return {"success": False, "error": f"Invalid fields: {invalid_fields}"}

    conn = get_connection()
    cursor = conn.cursor()

    # Check if preferences exist
    cursor.execute(
        "SELECT user_id FROM notification_preferences WHERE user_id = ?",
        (user_id,),
    )
    exists = cursor.fetchone() is not None

    # Prepare category_settings for storage
    if "category_settings" in updates and isinstance(updates["category_settings"], dict):
        updates["category_settings"] = json.dumps(updates["category_settings"])

    updates["updated_at"] = datetime.now().isoformat()

    if exists:
        # Update existing
        set_clauses = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [user_id]

        cursor.execute(
            f"UPDATE notification_preferences SET {set_clauses} WHERE user_id = ?",
            values,
        )
    else:
        # Insert new with defaults
        prefs = {**DEFAULT_PREFERENCES, **updates, "user_id": user_id}

        if isinstance(prefs.get("category_settings"), dict):
            prefs["category_settings"] = json.dumps(prefs["category_settings"])

        columns = ", ".join(prefs.keys())
        placeholders = ", ".join("?" * len(prefs))

        cursor.execute(
            f"INSERT INTO notification_preferences ({columns}) VALUES ({placeholders})",
            list(prefs.values()),
        )

    conn.commit()
    conn.close()

    # Return updated preferences
    updated_prefs = await get_preferences(user_id)
    return {"success": True, "preferences": updated_prefs}


async def set_quiet_hours(
    user_id: str,
    start: str,
    end: str,
    timezone: str | None = None,
) -> dict:
    """
    Set quiet hours (e.g., '22:00' to '08:00').

    Args:
        user_id: The user ID
        start: Start time in HH:MM format
        end: End time in HH:MM format
        timezone: Optional timezone (defaults to existing or UTC)

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    # Validate time format
    for time_str in [start, end]:
        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                raise ValueError()
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError()
        except (ValueError, AttributeError):
            return {"success": False, "error": f"Invalid time format: {time_str}. Use HH:MM"}

    updates = {
        "quiet_hours_start": start,
        "quiet_hours_end": end,
    }

    if timezone:
        updates["timezone"] = timezone

    return await update_preferences(user_id, **updates)


async def set_category_preference(
    user_id: str,
    category: str,
    enabled: bool = True,
    priority_threshold: int = 1,
    batch: bool | None = None,
) -> dict:
    """
    Configure preferences for a notification category.

    Args:
        user_id: The user ID
        category: Category ID (e.g., 'task_reminder')
        enabled: Whether to receive notifications for this category
        priority_threshold: Only receive if priority >= this value
        batch: Override batching setting for this category (None = use default)

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    prefs = await get_preferences(user_id)
    category_settings = prefs.get("category_settings", {})

    category_settings[category] = {
        "enabled": enabled,
        "priority_threshold": priority_threshold,
    }

    if batch is not None:
        category_settings[category]["batch"] = batch

    return await update_preferences(user_id, category_settings=category_settings)


async def get_effective_settings(user_id: str, category: str) -> dict:
    """
    Get merged settings for a specific category.

    Combines user preferences with category defaults.

    Args:
        user_id: The user ID
        category: Category ID

    Returns:
        Effective settings dict for the category
    """
    from tools.mobile.preferences.category_manager import get_category

    prefs = await get_preferences(user_id)
    cat_defaults = await get_category(category)

    # Start with category defaults
    settings = {
        "enabled": True,
        "priority": cat_defaults.get("default_priority", 5) if cat_defaults else 5,
        "can_batch": cat_defaults.get("can_batch", True) if cat_defaults else True,
        "can_suppress": cat_defaults.get("can_suppress", True) if cat_defaults else True,
    }

    # Apply user category overrides
    user_cat_settings = prefs.get("category_settings", {}).get(category, {})

    if "enabled" in user_cat_settings:
        settings["enabled"] = user_cat_settings["enabled"]
    if "priority_threshold" in user_cat_settings:
        settings["priority_threshold"] = user_cat_settings["priority_threshold"]
    if "batch" in user_cat_settings:
        settings["can_batch"] = user_cat_settings["batch"]

    return settings


async def disable_notifications(user_id: str) -> dict:
    """Quickly disable all notifications for a user."""
    return await update_preferences(user_id, enabled=False)


async def enable_notifications(user_id: str) -> dict:
    """Re-enable notifications for a user."""
    return await update_preferences(user_id, enabled=True)


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="User notification preferences")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Get preferences
    get_parser = subparsers.add_parser("get", help="Get user preferences")
    get_parser.add_argument("--user-id", "-u", required=True, help="User ID")

    # Set quiet hours
    quiet_parser = subparsers.add_parser("quiet-hours", help="Set quiet hours")
    quiet_parser.add_argument("--user-id", "-u", required=True, help="User ID")
    quiet_parser.add_argument("--start", "-s", required=True, help="Start time (HH:MM)")
    quiet_parser.add_argument("--end", "-e", required=True, help="End time (HH:MM)")
    quiet_parser.add_argument("--timezone", "-tz", help="Timezone")

    # Update preference
    update_parser = subparsers.add_parser("update", help="Update a preference")
    update_parser.add_argument("--user-id", "-u", required=True, help="User ID")
    update_parser.add_argument("--field", "-f", required=True, help="Field name")
    update_parser.add_argument("--value", "-v", required=True, help="New value")

    args = parser.parse_args()

    if args.command == "get":
        prefs = asyncio.run(get_preferences(args.user_id))
        print(json.dumps(prefs, indent=2))

    elif args.command == "quiet-hours":
        result = asyncio.run(set_quiet_hours(
            args.user_id,
            args.start,
            args.end,
            args.timezone,
        ))
        if result["success"]:
            print(f"Quiet hours set: {args.start} - {args.end}")
        else:
            print(f"Error: {result['error']}")

    elif args.command == "update":
        # Try to parse value as JSON for complex types
        value = args.value
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            # Keep as string if not valid JSON
            pass

        result = asyncio.run(update_preferences(args.user_id, **{args.field: value}))
        if result["success"]:
            print("Preference updated")
        else:
            print(f"Error: {result['error']}")

    else:
        parser.print_help()
