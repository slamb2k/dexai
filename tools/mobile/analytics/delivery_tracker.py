"""
Tool: Delivery Tracker
Purpose: Track notification delivery metrics and analytics

Usage:
    from tools.mobile.analytics.delivery_tracker import (
        track_sent,
        track_delivered,
        track_clicked,
        track_dismissed,
        get_stats,
    )
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from tools.mobile import get_connection
from tools.mobile.models import DeliveryStatus


async def track_sent(
    notification_id: str,
    subscription_id: str,
    delivery_id: str | None = None,
) -> dict:
    """
    Record that a notification was sent.

    Args:
        notification_id: The notification ID
        subscription_id: The subscription ID
        delivery_id: Optional delivery log ID

    Returns:
        {"success": True, "delivery_id": str}
    """
    import uuid

    conn = get_connection()
    cursor = conn.cursor()

    log_id = delivery_id or f"del_{uuid.uuid4().hex[:12]}"

    cursor.execute(
        """
        INSERT INTO notification_delivery_log
        (id, notification_id, subscription_id, status, sent_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            log_id,
            notification_id,
            subscription_id,
            DeliveryStatus.SENT.value,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    return {"success": True, "delivery_id": log_id}


async def track_delivered(delivery_id: str) -> dict:
    """
    Record that a notification was delivered to the device.

    Called when the service worker receives the push event.

    Args:
        delivery_id: The delivery log ID

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE notification_delivery_log
        SET status = ?, delivered_at = ?
        WHERE id = ?
        """,
        (DeliveryStatus.DELIVERED.value, datetime.now().isoformat(), delivery_id),
    )

    if cursor.rowcount == 0:
        conn.close()
        return {"success": False, "error": "Delivery log not found"}

    conn.commit()
    conn.close()
    return {"success": True}


async def track_clicked(
    delivery_id: str | None = None,
    notification_id: str | None = None,
) -> dict:
    """
    Record that a notification was clicked.

    Args:
        delivery_id: The delivery log ID (preferred)
        notification_id: Alternative: notification ID (updates all deliveries)

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    if delivery_id:
        cursor.execute(
            """
            UPDATE notification_delivery_log
            SET status = ?, clicked_at = ?
            WHERE id = ?
            """,
            (DeliveryStatus.CLICKED.value, now, delivery_id),
        )
    elif notification_id:
        cursor.execute(
            """
            UPDATE notification_delivery_log
            SET status = ?, clicked_at = ?
            WHERE notification_id = ? AND clicked_at IS NULL
            """,
            (DeliveryStatus.CLICKED.value, now, notification_id),
        )
    else:
        conn.close()
        return {"success": False, "error": "Must provide delivery_id or notification_id"}

    conn.commit()
    conn.close()
    return {"success": True}


async def track_dismissed(
    delivery_id: str | None = None,
    notification_id: str | None = None,
) -> dict:
    """
    Record that a notification was dismissed without clicking.

    Args:
        delivery_id: The delivery log ID (preferred)
        notification_id: Alternative: notification ID

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    if delivery_id:
        cursor.execute(
            """
            UPDATE notification_delivery_log
            SET status = ?, dismissed_at = ?
            WHERE id = ?
            """,
            (DeliveryStatus.DISMISSED.value, now, delivery_id),
        )
    elif notification_id:
        cursor.execute(
            """
            UPDATE notification_delivery_log
            SET status = ?, dismissed_at = ?
            WHERE notification_id = ? AND dismissed_at IS NULL AND clicked_at IS NULL
            """,
            (DeliveryStatus.DISMISSED.value, now, notification_id),
        )
    else:
        conn.close()
        return {"success": False, "error": "Must provide delivery_id or notification_id"}

    conn.commit()
    conn.close()
    return {"success": True}


async def get_stats(
    user_id: str | None = None,
    days: int = 7,
) -> dict:
    """
    Get aggregate delivery statistics.

    Args:
        user_id: Optional user ID to filter by
        days: Number of days to look back

    Returns:
        {
            "total_sent": int,
            "total_delivered": int,
            "total_clicked": int,
            "total_dismissed": int,
            "total_failed": int,
            "delivery_rate": float,
            "click_rate": float,
            "dismiss_rate": float,
            "by_category": dict,
            "by_day": list,
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    since = (datetime.now() - timedelta(days=days)).isoformat()

    # Base query with optional user filter
    if user_id:
        user_filter = """
        AND subscription_id IN (
            SELECT id FROM push_subscriptions WHERE user_id = ?
        )
        """
        params = [since, user_id]
    else:
        user_filter = ""
        params = [since]

    # Overall stats
    cursor.execute(
        f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
            SUM(CASE WHEN status = 'clicked' THEN 1 ELSE 0 END) as clicked,
            SUM(CASE WHEN status = 'dismissed' THEN 1 ELSE 0 END) as dismissed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'batched' THEN 1 ELSE 0 END) as batched
        FROM notification_delivery_log
        WHERE sent_at > ?
        {user_filter}
        """,
        params,
    )

    row = cursor.fetchone()
    total = row["total"] or 0
    sent = row["sent"] or 0
    delivered = row["delivered"] or 0
    clicked = row["clicked"] or 0
    dismissed = row["dismissed"] or 0
    failed = row["failed"] or 0
    batched = row["batched"] or 0

    # Calculate rates
    delivery_rate = (delivered / sent * 100) if sent > 0 else 0
    click_rate = (clicked / delivered * 100) if delivered > 0 else 0
    dismiss_rate = (dismissed / delivered * 100) if delivered > 0 else 0

    # Stats by category
    cursor.execute(
        f"""
        SELECT
            n.category,
            COUNT(d.id) as total,
            SUM(CASE WHEN d.status = 'clicked' THEN 1 ELSE 0 END) as clicked,
            SUM(CASE WHEN d.status = 'dismissed' THEN 1 ELSE 0 END) as dismissed
        FROM notification_delivery_log d
        JOIN notification_queue n ON d.notification_id = n.id
        WHERE d.sent_at > ?
        {user_filter}
        GROUP BY n.category
        """,
        params,
    )

    by_category = {}
    for row in cursor.fetchall():
        cat_total = row["total"] or 0
        cat_clicked = row["clicked"] or 0
        by_category[row["category"]] = {
            "total": cat_total,
            "clicked": cat_clicked,
            "click_rate": (cat_clicked / cat_total * 100) if cat_total > 0 else 0,
        }

    # Stats by day
    cursor.execute(
        f"""
        SELECT
            DATE(sent_at) as day,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'clicked' THEN 1 ELSE 0 END) as clicked
        FROM notification_delivery_log
        WHERE sent_at > ?
        {user_filter}
        GROUP BY DATE(sent_at)
        ORDER BY day
        """,
        params,
    )

    by_day = [
        {
            "day": row["day"],
            "total": row["total"],
            "clicked": row["clicked"],
        }
        for row in cursor.fetchall()
    ]

    conn.close()

    return {
        "period_days": days,
        "total_sent": sent + batched,
        "total_delivered": delivered,
        "total_clicked": clicked,
        "total_dismissed": dismissed,
        "total_failed": failed,
        "total_batched": batched,
        "delivery_rate": round(delivery_rate, 1),
        "click_rate": round(click_rate, 1),
        "dismiss_rate": round(dismiss_rate, 1),
        "by_category": by_category,
        "by_day": by_day,
    }


async def get_user_engagement(user_id: str, days: int = 30) -> dict:
    """
    Get engagement metrics for a specific user.

    Args:
        user_id: The user ID
        days: Days to look back

    Returns:
        User engagement metrics
    """
    stats = await get_stats(user_id=user_id, days=days)

    # Add user-specific insights
    click_rate = stats.get("click_rate", 0)

    if click_rate > 30:
        engagement_level = "high"
        suggestion = None
    elif click_rate > 15:
        engagement_level = "moderate"
        suggestion = "Consider adjusting notification timing or categories"
    else:
        engagement_level = "low"
        suggestion = "User may be experiencing notification fatigue - consider reducing frequency"

    stats["engagement_level"] = engagement_level
    stats["suggestion"] = suggestion

    return stats


async def get_notification_history(
    user_id: str,
    limit: int = 50,
    include_failed: bool = False,
) -> list[dict]:
    """
    Get notification history for a user.

    Args:
        user_id: The user ID
        limit: Maximum results
        include_failed: Include failed deliveries

    Returns:
        List of notification records with delivery status
    """
    conn = get_connection()
    cursor = conn.cursor()

    status_filter = ""
    if not include_failed:
        status_filter = "AND d.status != 'failed'"

    cursor.execute(
        f"""
        SELECT
            n.id,
            n.category,
            n.title,
            n.body,
            n.priority,
            n.created_at,
            d.status as delivery_status,
            d.sent_at,
            d.delivered_at,
            d.clicked_at,
            d.dismissed_at
        FROM notification_queue n
        JOIN notification_delivery_log d ON n.id = d.notification_id
        JOIN push_subscriptions s ON d.subscription_id = s.id
        WHERE s.user_id = ?
        {status_filter}
        ORDER BY n.created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# CLI interface
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Notification analytics")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Stats
    stats_parser = subparsers.add_parser("stats", help="Get delivery statistics")
    stats_parser.add_argument("--user-id", "-u", help="Optional user ID")
    stats_parser.add_argument("--days", "-d", type=int, default=7, help="Days to look back")

    # History
    history_parser = subparsers.add_parser("history", help="Get notification history")
    history_parser.add_argument("--user-id", "-u", required=True, help="User ID")
    history_parser.add_argument("--limit", "-l", type=int, default=20, help="Limit")

    args = parser.parse_args()

    if args.command == "stats":
        stats = asyncio.run(get_stats(
            user_id=args.user_id,
            days=args.days,
        ))
        print(json.dumps(stats, indent=2))

    elif args.command == "history":
        history = asyncio.run(get_notification_history(
            user_id=args.user_id,
            limit=args.limit,
        ))
        for notif in history:
            status = notif.get("delivery_status", "unknown")
            print(f"[{status}] {notif['title']}")

    else:
        parser.print_help()
