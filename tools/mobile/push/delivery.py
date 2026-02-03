"""
Tool: Push Notification Delivery
Purpose: Send notifications with retry logic and delivery tracking

Usage:
    from tools.mobile.push.delivery import deliver, deliver_batch
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any

from tools.mobile import get_connection
from tools.mobile.models import Notification, DeliveryResult, DeliveryStatus
from tools.mobile.push.web_push import send_push, send_batch
from tools.mobile.push.subscription_manager import (
    get_user_subscriptions,
    unregister_subscription,
)


async def deliver(
    notification: Notification,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> dict:
    """
    Deliver a notification to all user's subscriptions with retry logic.

    Args:
        notification: The notification to deliver
        max_retries: Maximum retry attempts per subscription
        retry_delay: Initial delay between retries (exponential backoff)

    Returns:
        {
            "success": True,
            "total_subscriptions": int,
            "successful": int,
            "failed": int,
            "delivery_ids": list[str],
        }
    """
    # Get all active subscriptions for user
    subscriptions = await get_user_subscriptions(notification.user_id, active_only=True)

    if not subscriptions:
        return {
            "success": True,
            "total_subscriptions": 0,
            "successful": 0,
            "failed": 0,
            "delivery_ids": [],
            "message": "No active subscriptions for user",
        }

    results = {
        "success": True,
        "total_subscriptions": len(subscriptions),
        "successful": 0,
        "failed": 0,
        "delivery_ids": [],
    }

    # Send to each subscription
    for sub in subscriptions:
        delivery_result = await _deliver_to_subscription(
            notification=notification,
            subscription_id=sub["id"],
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        if delivery_result.success:
            results["successful"] += 1
            if delivery_result.delivery_id:
                results["delivery_ids"].append(delivery_result.delivery_id)
        else:
            results["failed"] += 1

            # Handle should_unsubscribe (410 Gone)
            if delivery_result.should_unsubscribe:
                await unregister_subscription(sub["id"])

    # Update notification status
    final_status = DeliveryStatus.SENT if results["successful"] > 0 else DeliveryStatus.FAILED
    await _update_notification_status(notification.id, final_status)

    return results


async def _deliver_to_subscription(
    notification: Notification,
    subscription_id: str,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> DeliveryResult:
    """Deliver notification to a single subscription with retries."""
    last_error = None

    for attempt in range(max_retries):
        result = await send_push(
            subscription_id=subscription_id,
            title=notification.title,
            body=notification.body,
            data=notification.data,
            icon_url=notification.icon_url,
            action_url=notification.action_url,
            tag=notification.batch_key or notification.id,
            require_interaction=notification.priority >= 8,
            silent=notification.priority < 3,
        )

        if result["success"]:
            # Log successful delivery
            delivery_id = result.get("delivery_id")
            await _log_delivery(
                notification_id=notification.id,
                subscription_id=subscription_id,
                status=DeliveryStatus.SENT,
                delivery_id=delivery_id,
            )

            return DeliveryResult(
                success=True,
                delivery_id=delivery_id,
                subscription_id=subscription_id,
                notification_id=notification.id,
            )

        # Handle specific error cases
        if result.get("should_unsubscribe"):
            # Don't retry - endpoint is invalid
            await _log_delivery(
                notification_id=notification.id,
                subscription_id=subscription_id,
                status=DeliveryStatus.FAILED,
                error=result.get("error", "Endpoint invalid"),
            )
            return DeliveryResult(
                success=False,
                subscription_id=subscription_id,
                notification_id=notification.id,
                error=result.get("error"),
                should_unsubscribe=True,
            )

        # Check for rate limiting
        retry_after = result.get("retry_after")
        if retry_after:
            await asyncio.sleep(retry_after)
            continue

        last_error = result.get("error")

        # Exponential backoff
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay * (2 ** attempt))

    # All retries failed
    await _log_delivery(
        notification_id=notification.id,
        subscription_id=subscription_id,
        status=DeliveryStatus.FAILED,
        error=last_error,
    )

    return DeliveryResult(
        success=False,
        subscription_id=subscription_id,
        notification_id=notification.id,
        error=last_error,
    )


async def deliver_batch(
    notifications: list[Notification],
    user_id: str,
) -> dict:
    """
    Deliver a batch of notifications as a single summary notification.

    Args:
        notifications: List of notifications to batch
        user_id: The user ID

    Returns:
        Same format as deliver()
    """
    if not notifications:
        return {
            "success": True,
            "total_subscriptions": 0,
            "successful": 0,
            "failed": 0,
            "delivery_ids": [],
        }

    subscriptions = await get_user_subscriptions(user_id, active_only=True)

    if not subscriptions:
        return {
            "success": True,
            "total_subscriptions": 0,
            "successful": 0,
            "failed": 0,
            "delivery_ids": [],
        }

    results = {
        "success": True,
        "total_subscriptions": len(subscriptions),
        "successful": 0,
        "failed": 0,
        "delivery_ids": [],
        "batched_count": len(notifications),
    }

    # Convert notifications to dicts for batch sending
    notif_dicts = [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "category": n.category,
            "data": n.data,
            "action_url": n.action_url,
            "batch_key": n.batch_key,
        }
        for n in notifications
    ]

    # Send to each subscription
    for sub in subscriptions:
        result = await send_batch(
            subscription_id=sub["id"],
            notifications=notif_dicts,
        )

        if result.get("success"):
            results["successful"] += 1
            if result.get("delivery_id"):
                results["delivery_ids"].append(result["delivery_id"])

            # Log delivery for each notification
            for n in notifications:
                await _log_delivery(
                    notification_id=n.id,
                    subscription_id=sub["id"],
                    status=DeliveryStatus.BATCHED,
                )
        else:
            results["failed"] += 1

    # Update notification statuses
    for n in notifications:
        status = DeliveryStatus.BATCHED if results["successful"] > 0 else DeliveryStatus.FAILED
        await _update_notification_status(n.id, status)

    return results


async def _log_delivery(
    notification_id: str,
    subscription_id: str,
    status: DeliveryStatus,
    delivery_id: str | None = None,
    error: str | None = None,
) -> None:
    """Log a delivery attempt."""
    conn = get_connection()
    cursor = conn.cursor()

    log_id = delivery_id or f"log_{uuid.uuid4().hex[:12]}"

    cursor.execute(
        """
        INSERT INTO notification_delivery_log
        (id, notification_id, subscription_id, status, error_message, sent_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            log_id,
            notification_id,
            subscription_id,
            status.value if isinstance(status, DeliveryStatus) else status,
            error,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


async def _update_notification_status(
    notification_id: str,
    status: DeliveryStatus,
) -> None:
    """Update notification status in queue."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE notification_queue
        SET status = ?, sent_at = ?
        WHERE id = ?
        """,
        (
            status.value if isinstance(status, DeliveryStatus) else status,
            datetime.now().isoformat(),
            notification_id,
        ),
    )
    conn.commit()
    conn.close()


async def track_delivery_event(
    delivery_id: str,
    event_type: str,
) -> dict:
    """
    Track a delivery event (delivered, clicked, dismissed).

    Args:
        delivery_id: The delivery log ID
        event_type: 'delivered', 'clicked', or 'dismissed'

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    if event_type == "delivered":
        cursor.execute(
            "UPDATE notification_delivery_log SET status = ?, delivered_at = ? WHERE id = ?",
            (DeliveryStatus.DELIVERED.value, now, delivery_id),
        )
    elif event_type == "clicked":
        cursor.execute(
            "UPDATE notification_delivery_log SET status = ?, clicked_at = ? WHERE id = ?",
            (DeliveryStatus.CLICKED.value, now, delivery_id),
        )
    elif event_type == "dismissed":
        cursor.execute(
            "UPDATE notification_delivery_log SET status = ?, dismissed_at = ? WHERE id = ?",
            (DeliveryStatus.DISMISSED.value, now, delivery_id),
        )
    else:
        conn.close()
        return {"success": False, "error": f"Unknown event type: {event_type}"}

    conn.commit()
    conn.close()
    return {"success": True}


async def get_delivery_history(
    notification_id: str | None = None,
    subscription_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Get delivery history.

    Args:
        notification_id: Filter by notification
        subscription_id: Filter by subscription
        limit: Maximum results

    Returns:
        List of delivery log dicts
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM notification_delivery_log WHERE 1=1"
    params = []

    if notification_id:
        query += " AND notification_id = ?"
        params.append(notification_id)
    if subscription_id:
        query += " AND subscription_id = ?"
        params.append(subscription_id)

    query += " ORDER BY sent_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
