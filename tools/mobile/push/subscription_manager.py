"""
Tool: Push Subscription Manager
Purpose: Store and manage Web Push subscriptions

Usage:
    from tools.mobile.push.subscription_manager import (
        register_subscription,
        unregister_subscription,
        get_user_subscriptions,
        prune_stale_subscriptions,
    )
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from tools.mobile import get_connection
from tools.mobile.models import PushSubscription


async def register_subscription(
    user_id: str,
    endpoint: str,
    p256dh_key: str,
    auth_key: str,
    device_name: str | None = None,
    device_type: str = "web",
    browser: str | None = None,
) -> dict:
    """
    Register a new push subscription.

    Args:
        user_id: The user ID
        endpoint: Web Push endpoint URL from browser
        p256dh_key: Client public key (p256dh)
        auth_key: Auth secret
        device_name: User-provided device name
        device_type: 'web', 'android', 'ios'
        browser: Browser name ('chrome', 'firefox', 'safari', 'edge')

    Returns:
        {"success": True, "subscription_id": str}
        or {"success": False, "error": str}
    """
    if not endpoint or not p256dh_key or not auth_key:
        return {"success": False, "error": "Missing required subscription fields"}

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Check if endpoint already exists
        cursor.execute(
            "SELECT id, is_active FROM push_subscriptions WHERE endpoint = ?",
            (endpoint,),
        )
        existing = cursor.fetchone()

        if existing:
            # Reactivate existing subscription
            subscription_id = existing["id"]
            cursor.execute(
                """
                UPDATE push_subscriptions
                SET is_active = TRUE,
                    p256dh_key = ?,
                    auth_key = ?,
                    device_name = ?,
                    device_type = ?,
                    browser = ?,
                    user_id = ?,
                    last_used_at = ?
                WHERE id = ?
                """,
                (
                    p256dh_key,
                    auth_key,
                    device_name,
                    device_type,
                    browser,
                    user_id,
                    datetime.now().isoformat(),
                    subscription_id,
                ),
            )
            conn.commit()
            conn.close()

            return {
                "success": True,
                "subscription_id": subscription_id,
                "reactivated": True,
            }

        # Create new subscription
        subscription_id = PushSubscription.generate_id()
        now = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO push_subscriptions
            (id, user_id, endpoint, p256dh_key, auth_key, device_name, device_type, browser, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE)
            """,
            (
                subscription_id,
                user_id,
                endpoint,
                p256dh_key,
                auth_key,
                device_name,
                device_type,
                browser,
                now,
            ),
        )
        conn.commit()
        conn.close()

        return {"success": True, "subscription_id": subscription_id}

    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}


async def unregister_subscription(subscription_id: str) -> dict:
    """
    Mark a subscription as inactive.

    Args:
        subscription_id: The subscription ID

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "UPDATE push_subscriptions SET is_active = FALSE WHERE id = ?",
            (subscription_id,),
        )

        if cursor.rowcount == 0:
            conn.close()
            return {"success": False, "error": "Subscription not found"}

        conn.commit()
        conn.close()
        return {"success": True}

    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}


async def unregister_by_endpoint(endpoint: str) -> dict:
    """
    Mark a subscription as inactive by endpoint URL.

    Useful for handling 410 Gone responses.

    Args:
        endpoint: The Web Push endpoint URL

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "UPDATE push_subscriptions SET is_active = FALSE WHERE endpoint = ?",
            (endpoint,),
        )
        conn.commit()
        conn.close()
        return {"success": True, "updated": cursor.rowcount}

    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}


async def get_user_subscriptions(
    user_id: str,
    active_only: bool = True,
) -> list[dict]:
    """
    Get all subscriptions for a user.

    Args:
        user_id: The user ID
        active_only: If True, only return active subscriptions

    Returns:
        List of subscription dicts
    """
    conn = get_connection()
    cursor = conn.cursor()

    if active_only:
        cursor.execute(
            """
            SELECT * FROM push_subscriptions
            WHERE user_id = ? AND is_active = TRUE
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM push_subscriptions
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


async def get_subscription(subscription_id: str) -> dict | None:
    """
    Get a single subscription by ID.

    Args:
        subscription_id: The subscription ID

    Returns:
        Subscription dict or None
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM push_subscriptions WHERE id = ?",
        (subscription_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return dict(row)


async def has_active_subscriptions(user_id: str) -> bool:
    """
    Check if user has any active push subscriptions.

    Args:
        user_id: The user ID

    Returns:
        True if user has at least one active subscription
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM push_subscriptions WHERE user_id = ? AND is_active = TRUE LIMIT 1",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    return row is not None


async def prune_stale_subscriptions(days_inactive: int = 30) -> dict:
    """
    Remove subscriptions that haven't been used recently.

    Args:
        days_inactive: Mark subscriptions inactive after this many days

    Returns:
        {"success": True, "pruned": int}
    """
    conn = get_connection()
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=days_inactive)).isoformat()

    try:
        # Mark stale subscriptions as inactive
        cursor.execute(
            """
            UPDATE push_subscriptions
            SET is_active = FALSE
            WHERE is_active = TRUE
            AND (
                last_used_at IS NULL AND created_at < ?
                OR last_used_at < ?
            )
            """,
            (cutoff, cutoff),
        )

        pruned = cursor.rowcount
        conn.commit()
        conn.close()

        return {"success": True, "pruned": pruned}

    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}


async def update_last_used(subscription_id: str) -> None:
    """Update the last_used_at timestamp for a subscription."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE push_subscriptions SET last_used_at = ? WHERE id = ?",
        (datetime.now().isoformat(), subscription_id),
    )
    conn.commit()
    conn.close()


async def get_subscription_stats(user_id: str | None = None) -> dict:
    """
    Get subscription statistics.

    Args:
        user_id: Optional user ID to filter by

    Returns:
        Statistics dict
    """
    conn = get_connection()
    cursor = conn.cursor()

    if user_id:
        cursor.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN is_active = FALSE THEN 1 ELSE 0 END) as inactive,
                COUNT(DISTINCT browser) as browsers,
                COUNT(DISTINCT device_type) as device_types
            FROM push_subscriptions
            WHERE user_id = ?
            """,
            (user_id,),
        )
    else:
        cursor.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN is_active = FALSE THEN 1 ELSE 0 END) as inactive,
                COUNT(DISTINCT user_id) as users,
                COUNT(DISTINCT browser) as browsers,
                COUNT(DISTINCT device_type) as device_types
            FROM push_subscriptions
            """
        )

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else {}


# CLI interface
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Push subscription management")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List subscriptions
    list_parser = subparsers.add_parser("list", help="List subscriptions for a user")
    list_parser.add_argument("--user-id", "-u", required=True, help="User ID")
    list_parser.add_argument("--all", "-a", action="store_true", help="Include inactive")

    # Prune stale
    prune_parser = subparsers.add_parser("prune", help="Prune stale subscriptions")
    prune_parser.add_argument("--days", "-d", type=int, default=30, help="Days inactive")

    # Stats
    stats_parser = subparsers.add_parser("stats", help="Get subscription statistics")
    stats_parser.add_argument("--user-id", "-u", help="Optional user ID")

    args = parser.parse_args()

    if args.command == "list":
        subs = asyncio.run(get_user_subscriptions(
            args.user_id,
            active_only=not args.all,
        ))
        print(f"Found {len(subs)} subscriptions:")
        for sub in subs:
            status = "active" if sub.get("is_active") else "inactive"
            print(f"  {sub['id']}: {sub.get('device_name', 'Unknown')} ({sub.get('browser', '?')}) [{status}]")

    elif args.command == "prune":
        result = asyncio.run(prune_stale_subscriptions(args.days))
        if result["success"]:
            print(f"Pruned {result['pruned']} stale subscriptions")
        else:
            print(f"Error: {result['error']}")

    elif args.command == "stats":
        stats = asyncio.run(get_subscription_stats(args.user_id))
        print(json.dumps(stats, indent=2))

    else:
        parser.print_help()
