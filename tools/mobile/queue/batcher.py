"""
Tool: Notification Batcher
Purpose: Batch related notifications to reduce interruptions

Usage:
    from tools.mobile.queue.batcher import (
        should_batch,
        get_batch,
        create_batch_summary,
        process_expired_batches,
    )

ADHD-Specific Design:
    - Groups related notifications to reduce total interruption count
    - Summary notifications are clear and concise
    - Single action per batch notification
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from tools.mobile import get_connection
from tools.mobile.models import Notification, DeliveryStatus
from tools.mobile.push.delivery import deliver_batch


async def should_batch(notification: Notification) -> bool:
    """
    Check if notification should be batched with others.

    A notification should be batched if:
    - It has a batch_key
    - Priority is below 8 (high priority never batches)
    - There are other pending notifications with same batch_key
    - Batch window hasn't expired

    Args:
        notification: The notification to check

    Returns:
        True if notification should wait for batch
    """
    # No batch key = no batching
    if not notification.batch_key:
        return False

    # High priority notifications never batch
    if notification.priority >= 8:
        return False

    # Check if there are others in the batch
    batch = await get_batch(notification.user_id, notification.batch_key)

    if len(batch) <= 1:
        # Only this notification - check if within batch window
        if notification.created_at:
            window_end = notification.created_at + timedelta(seconds=notification.batch_window_seconds)
            if datetime.now() < window_end:
                return True  # Wait for more notifications

    # Multiple notifications in batch - wait for window
    return True


async def get_batch(user_id: str, batch_key: str) -> list[dict]:
    """
    Get all notifications in a batch.

    Args:
        user_id: The user ID
        batch_key: The batch key

    Returns:
        List of notification dicts in the batch
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM notification_queue
        WHERE user_id = ?
        AND batch_key = ?
        AND status IN ('pending', 'batched')
        ORDER BY priority DESC, created_at ASC
        """,
        (user_id, batch_key),
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


async def create_batch_summary(notifications: list[dict]) -> dict:
    """
    Create a summary notification for a batch.

    ADHD-friendly: Clear, concise, single action.

    Args:
        notifications: List of notification dicts in the batch

    Returns:
        {
            "title": str,
            "body": str,
            "count": int,
            "notification_ids": list[str],
            "category": str,
            "priority": int,
        }
    """
    if not notifications:
        return {
            "title": "No notifications",
            "body": "",
            "count": 0,
            "notification_ids": [],
            "category": "system",
            "priority": 1,
        }

    count = len(notifications)
    notification_ids = [n.get("id") for n in notifications]

    # Get highest priority in batch
    max_priority = max(n.get("priority", 5) for n in notifications)

    # Get categories
    categories = set(n.get("category", "notification") for n in notifications)
    category = categories.pop() if len(categories) == 1 else "mixed"

    # Create ADHD-friendly title
    if count == 1:
        title = notifications[0].get("title", "Notification")
        body = notifications[0].get("body", "")
    else:
        # Supportive, forward-facing language
        category_labels = {
            "task_reminder": "tasks ready",
            "message_received": "messages",
            "commitment_due": "items needing attention",
            "daily_summary": "updates",
        }
        label = category_labels.get(category, "notifications")
        title = f"{count} {label} when you're ready"

        # Show first 2-3 items
        preview_count = min(3, count)
        previews = []
        for n in notifications[:preview_count]:
            t = n.get("title", "")
            if len(t) > 30:
                t = t[:27] + "..."
            previews.append(f"- {t}")

        body = "\n".join(previews)
        remaining = count - preview_count
        if remaining > 0:
            body += f"\n...and {remaining} more"

    return {
        "title": title,
        "body": body,
        "count": count,
        "notification_ids": notification_ids,
        "category": category,
        "priority": max_priority,
    }


async def process_expired_batches() -> dict:
    """
    Send batches that have exceeded their batch window.

    Should be called periodically by the queue processor.

    Returns:
        {
            "batches_processed": int,
            "sent": int,
            "errors": int,
        }
    """
    results = {
        "batches_processed": 0,
        "sent": 0,
        "errors": 0,
    }

    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()

    # Find distinct batch keys with expired windows
    # A batch window is expired when:
    # oldest notification in batch + batch_window_seconds < now
    cursor.execute(
        """
        SELECT DISTINCT user_id, batch_key, MIN(created_at) as oldest, batch_window_seconds
        FROM notification_queue
        WHERE batch_key IS NOT NULL
        AND status IN ('pending', 'batched')
        GROUP BY user_id, batch_key
        """
    )

    batches = cursor.fetchall()
    conn.close()

    for batch_row in batches:
        user_id = batch_row["user_id"]
        batch_key = batch_row["batch_key"]
        oldest = datetime.fromisoformat(batch_row["oldest"]) if batch_row["oldest"] else now
        window_seconds = batch_row["batch_window_seconds"] or 300

        # Check if window expired
        window_end = oldest + timedelta(seconds=window_seconds)
        if now < window_end:
            continue  # Window still open

        # Get batch notifications
        batch_notifs = await get_batch(user_id, batch_key)
        if not batch_notifs:
            continue

        results["batches_processed"] += 1

        # Convert to Notification objects
        notifications = [Notification.from_dict(n) for n in batch_notifs]

        # Deliver batch
        try:
            delivery_result = await deliver_batch(notifications, user_id)
            if delivery_result.get("successful", 0) > 0:
                results["sent"] += len(notifications)

                # Mark all as batched/sent
                await _mark_batch_sent(batch_key, user_id)
            else:
                results["errors"] += 1
        except Exception as e:
            results["errors"] += 1

    return results


async def _mark_batch_sent(batch_key: str, user_id: str) -> None:
    """Mark all notifications in a batch as sent."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE notification_queue
        SET status = ?, sent_at = ?
        WHERE batch_key = ? AND user_id = ? AND status IN ('pending', 'batched')
        """,
        (DeliveryStatus.BATCHED.value, datetime.now().isoformat(), batch_key, user_id),
    )
    conn.commit()
    conn.close()


async def get_batch_stats() -> dict:
    """Get statistics about batched notifications."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            batch_key,
            COUNT(*) as count,
            MAX(priority) as max_priority,
            MIN(created_at) as oldest
        FROM notification_queue
        WHERE batch_key IS NOT NULL
        AND status IN ('pending', 'batched')
        GROUP BY batch_key
        """
    )

    rows = cursor.fetchall()
    conn.close()

    return {
        "pending_batches": len(rows),
        "total_batched": sum(row["count"] for row in rows),
        "batches": [dict(row) for row in rows],
    }
