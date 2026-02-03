"""
Tool: Notification Queue
Purpose: Priority queue for push notifications with batching support

Usage:
    from tools.mobile.queue.notification_queue import (
        enqueue,
        process_queue,
        get_pending,
        cancel,
    )
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from tools.mobile import get_connection
from tools.mobile.models import Notification, DeliveryStatus
from tools.mobile.push.delivery import deliver, deliver_batch
from tools.mobile.queue.scheduler import can_send_now
from tools.mobile.queue.batcher import (
    should_batch,
    get_batch,
    process_expired_batches,
)


async def enqueue(
    user_id: str,
    category: str,
    title: str,
    body: str | None = None,
    priority: int = 5,
    data: dict | None = None,
    icon_url: str | None = None,
    action_url: str | None = None,
    scheduled_for: datetime | None = None,
    expires_at: datetime | None = None,
    batch_key: str | None = None,
    batch_window_seconds: int = 300,
    respect_flow_state: bool = True,
    min_priority_to_interrupt: int = 8,
) -> dict:
    """
    Add a notification to the queue.

    Args:
        user_id: The user to notify
        category: Notification category (task_reminder, commitment_due, etc.)
        title: Notification title
        body: Notification body
        priority: 1-10, higher = more important (8+ can interrupt flow)
        data: Additional data for click handling
        icon_url: Custom icon URL
        action_url: URL to open on click
        scheduled_for: When to send (None = ASAP)
        expires_at: Don't send after this time
        batch_key: Key for batching related notifications
        batch_window_seconds: How long to wait for batch
        respect_flow_state: Whether to check flow state before sending
        min_priority_to_interrupt: Minimum priority to interrupt flow

    Returns:
        {
            "success": True,
            "notification_id": str,
            "status": "pending" | "scheduled" | "batched"
        }
    """
    notification = Notification(
        id=Notification.generate_id(),
        user_id=user_id,
        category=category,
        title=title,
        body=body,
        priority=priority,
        data=data or {},
        icon_url=icon_url,
        action_url=action_url,
        scheduled_for=scheduled_for,
        expires_at=expires_at,
        batch_key=batch_key,
        batch_window_seconds=batch_window_seconds,
        respect_flow_state=respect_flow_state,
        min_priority_to_interrupt=min_priority_to_interrupt,
        status=DeliveryStatus.PENDING,
    )

    # Determine initial status
    if scheduled_for and scheduled_for > datetime.now():
        status = "scheduled"
    elif batch_key:
        status = "batched"
    else:
        status = "pending"

    # Save to database
    conn = get_connection()
    cursor = conn.cursor()

    try:
        notif_dict = notification.to_dict()

        cursor.execute(
            """
            INSERT INTO notification_queue
            (id, user_id, category, priority, title, body, data, icon_url, action_url,
             scheduled_for, expires_at, batch_key, batch_window_seconds, status,
             created_at, respect_flow_state, min_priority_to_interrupt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                notif_dict["id"],
                notif_dict["user_id"],
                notif_dict["category"],
                notif_dict["priority"],
                notif_dict["title"],
                notif_dict["body"],
                notif_dict["data"],
                notif_dict["icon_url"],
                notif_dict["action_url"],
                notif_dict["scheduled_for"],
                notif_dict["expires_at"],
                notif_dict["batch_key"],
                notif_dict["batch_window_seconds"],
                status,
                notif_dict["created_at"],
                notif_dict["respect_flow_state"],
                notif_dict["min_priority_to_interrupt"],
            ),
        )
        conn.commit()
        conn.close()

        return {
            "success": True,
            "notification_id": notification.id,
            "status": status,
        }

    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}


async def process_queue(limit: int = 100) -> dict:
    """
    Process pending notifications, respecting flow state and batching.

    This is the main processing loop that should be called periodically.

    Args:
        limit: Maximum notifications to process per run

    Returns:
        {
            "processed": int,
            "sent": int,
            "batched": int,
            "suppressed": int,
            "expired": int,
        }
    """
    results = {
        "processed": 0,
        "sent": 0,
        "batched": 0,
        "suppressed": 0,
        "expired": 0,
        "errors": 0,
    }

    # First, process expired batches
    batch_results = await process_expired_batches()
    results["batched"] = batch_results.get("sent", 0)

    # Get pending notifications (not scheduled for future, not batched)
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # Get non-batched pending notifications
    cursor.execute(
        """
        SELECT * FROM notification_queue
        WHERE status = 'pending'
        AND (scheduled_for IS NULL OR scheduled_for <= ?)
        AND (batch_key IS NULL)
        ORDER BY priority DESC, created_at ASC
        LIMIT ?
        """,
        (now, limit),
    )

    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        notification = Notification.from_dict(dict(row))
        results["processed"] += 1

        # Check if expired
        if notification.is_expired():
            await _mark_expired(notification.id)
            results["expired"] += 1
            continue

        # Check if should batch
        if await should_batch(notification):
            # Will be processed when batch window expires
            continue

        # Check if can send now (flow state, quiet hours, rate limits)
        send_check = await can_send_now(notification.user_id, notification.priority)

        if not send_check["can_send"]:
            # Suppress or reschedule
            reason = send_check.get("reason", "unknown")

            if reason == "quiet_hours" and send_check.get("retry_at"):
                # Reschedule for after quiet hours
                await _reschedule(notification.id, send_check["retry_at"])
                results["suppressed"] += 1
            elif reason == "flow_state" and notification.respect_flow_state:
                # Suppress (will retry on next process)
                results["suppressed"] += 1
            elif reason == "rate_limit":
                # Reschedule for after cooldown
                if send_check.get("retry_at"):
                    await _reschedule(notification.id, send_check["retry_at"])
                results["suppressed"] += 1
            else:
                results["suppressed"] += 1
            continue

        # Send notification
        try:
            delivery_result = await deliver(notification)
            if delivery_result.get("successful", 0) > 0:
                results["sent"] += 1
            else:
                results["errors"] += 1
        except Exception as e:
            results["errors"] += 1

    return results


async def get_pending(
    user_id: str,
    include_scheduled: bool = False,
) -> list[dict]:
    """
    Get pending notifications for a user.

    Args:
        user_id: The user ID
        include_scheduled: Include future scheduled notifications

    Returns:
        List of notification dicts
    """
    conn = get_connection()
    cursor = conn.cursor()

    if include_scheduled:
        cursor.execute(
            """
            SELECT * FROM notification_queue
            WHERE user_id = ? AND status IN ('pending', 'scheduled')
            ORDER BY priority DESC, created_at ASC
            """,
            (user_id,),
        )
    else:
        now = datetime.now().isoformat()
        cursor.execute(
            """
            SELECT * FROM notification_queue
            WHERE user_id = ? AND status = 'pending'
            AND (scheduled_for IS NULL OR scheduled_for <= ?)
            ORDER BY priority DESC, created_at ASC
            """,
            (user_id, now),
        )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


async def cancel(notification_id: str) -> dict:
    """
    Cancel a pending notification.

    Args:
        notification_id: The notification ID

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE notification_queue
            SET status = 'cancelled'
            WHERE id = ? AND status IN ('pending', 'scheduled')
            """,
            (notification_id,),
        )

        if cursor.rowcount == 0:
            conn.close()
            return {"success": False, "error": "Notification not found or already processed"}

        conn.commit()
        conn.close()
        return {"success": True}

    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}


async def _mark_expired(notification_id: str) -> None:
    """Mark a notification as expired."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE notification_queue SET status = 'expired' WHERE id = ?",
        (notification_id,),
    )
    conn.commit()
    conn.close()


async def _reschedule(notification_id: str, scheduled_for: datetime) -> None:
    """Reschedule a notification for later."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE notification_queue SET scheduled_for = ? WHERE id = ?",
        (scheduled_for.isoformat(), notification_id),
    )
    conn.commit()
    conn.close()


async def get_queue_stats(user_id: str | None = None) -> dict:
    """
    Get queue statistics.

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
                status,
                COUNT(*) as count
            FROM notification_queue
            WHERE user_id = ?
            GROUP BY status
            """,
            (user_id,),
        )
    else:
        cursor.execute(
            """
            SELECT
                status,
                COUNT(*) as count
            FROM notification_queue
            GROUP BY status
            """
        )

    rows = cursor.fetchall()
    conn.close()

    stats = {row["status"]: row["count"] for row in rows}
    stats["total"] = sum(stats.values())

    return stats


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Notification queue management")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Process queue
    process_parser = subparsers.add_parser("process", help="Process pending notifications")
    process_parser.add_argument("--limit", "-l", type=int, default=100, help="Max to process")

    # Stats
    stats_parser = subparsers.add_parser("stats", help="Get queue statistics")
    stats_parser.add_argument("--user-id", "-u", help="Optional user ID")

    # Enqueue test
    test_parser = subparsers.add_parser("test", help="Enqueue test notification")
    test_parser.add_argument("--user-id", "-u", required=True, help="User ID")
    test_parser.add_argument("--title", "-t", default="Test Notification", help="Title")
    test_parser.add_argument("--body", "-b", default="This is a test", help="Body")

    args = parser.parse_args()

    if args.command == "process":
        results = asyncio.run(process_queue(args.limit))
        print(f"Processed: {results['processed']}")
        print(f"  Sent: {results['sent']}")
        print(f"  Batched: {results['batched']}")
        print(f"  Suppressed: {results['suppressed']}")
        print(f"  Expired: {results['expired']}")
        print(f"  Errors: {results['errors']}")

    elif args.command == "stats":
        stats = asyncio.run(get_queue_stats(args.user_id))
        import json
        print(json.dumps(stats, indent=2))

    elif args.command == "test":
        result = asyncio.run(enqueue(
            user_id=args.user_id,
            category="test",
            title=args.title,
            body=args.body,
            priority=5,
        ))
        if result["success"]:
            print(f"Enqueued notification: {result['notification_id']}")
        else:
            print(f"Error: {result['error']}")

    else:
        parser.print_help()
