"""
Push Notification Routes - Web Push API for Dashboard

Provides endpoints for Web Push notification management:
- VAPID key retrieval for client subscription
- Subscription management (register, unregister, list)
- Native token registration (Expo/FCM/APNs) for mobile apps
- Notification preferences
- Category management
- Analytics and history
"""

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

# Import mobile push tools
from tools.mobile.push.web_push import get_vapid_public_key, send_push
from tools.mobile.push.subscription_manager import (
    register_subscription,
    unregister_subscription,
    get_user_subscriptions,
    get_subscription_stats,
)
from tools.mobile.push.native_tokens import (
    register_native_token,
    unregister_native_token,
    get_native_tokens,
    send_native_push_batch,
)
from tools.mobile.queue.notification_queue import enqueue, get_pending, cancel
from tools.mobile.preferences.user_preferences import (
    get_preferences,
    update_preferences,
    set_quiet_hours,
    set_category_preference,
)
from tools.mobile.preferences.category_manager import (
    get_categories,
    get_category,
    update_category,
    seed_default_categories,
)
from tools.mobile.analytics.delivery_tracker import get_stats, get_notification_history


router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class SubscribeRequest(BaseModel):
    """Request to register a push subscription."""

    endpoint: str = Field(..., description="Web Push endpoint URL")
    p256dh: str = Field(..., description="Client public key (p256dh)")
    auth: str = Field(..., description="Auth secret")
    device_name: str | None = Field(None, description="User-provided device name")
    device_type: str = Field("web", description="Device type (web, android, ios)")
    browser: str | None = Field(None, description="Browser name")


class SubscriptionResponse(BaseModel):
    """Push subscription response."""

    id: str
    device_name: str | None
    device_type: str
    browser: str | None
    is_active: bool
    created_at: str
    last_used_at: str | None


class PreferencesUpdateRequest(BaseModel):
    """Request to update notification preferences."""

    enabled: bool | None = None
    quiet_hours_start: str | None = Field(None, description="Start time (HH:MM)")
    quiet_hours_end: str | None = Field(None, description="End time (HH:MM)")
    timezone: str | None = None
    respect_flow_state: bool | None = None
    flow_interrupt_threshold: int | None = Field(None, ge=1, le=10)
    batch_notifications: bool | None = None
    batch_window_minutes: int | None = Field(None, ge=1, le=60)
    max_notifications_per_hour: int | None = Field(None, ge=1, le=30)


class CategoryUpdateRequest(BaseModel):
    """Request to update user's category preferences."""

    enabled: bool = True
    priority_threshold: int = Field(1, ge=1, le=10)
    batch: bool | None = None


class TestNotificationRequest(BaseModel):
    """Request to send a test notification."""

    title: str = Field("Test from DexAI", description="Notification title")
    body: str = Field("This is a test notification", description="Notification body")


class NativeTokenRequest(BaseModel):
    """Request to register a native push token (Expo/FCM/APNs)."""

    token: str = Field(..., description="Push token from mobile app")
    tokenType: str = Field(..., description="Token type: 'expo', 'fcm', or 'apns'")
    deviceInfo: dict | None = Field(None, description="Device information")


class NativeTokenResponse(BaseModel):
    """Response for native token registration."""

    success: bool
    subscriptionId: str | None = Field(None, alias="subscription_id")
    reactivated: bool = False


# =============================================================================
# VAPID Key Endpoint
# =============================================================================


@router.get("/vapid-key")
async def get_vapid_key():
    """
    Get the server's VAPID public key for client subscription.

    This key is needed by the browser to subscribe to push notifications.
    """
    public_key = get_vapid_public_key()

    if not public_key:
        raise HTTPException(
            status_code=500,
            detail="VAPID keys not configured. Generate with: python -m tools.mobile.push.web_push generate-keys",
        )

    return {"public_key": public_key}


# =============================================================================
# Subscription Endpoints
# =============================================================================


@router.post("/subscribe")
async def subscribe(
    request: SubscribeRequest,
    user_id: str = Query("default", description="User ID"),
):
    """
    Register a new push subscription.

    Called after the browser successfully subscribes to push notifications.
    """
    result = await register_subscription(
        user_id=user_id,
        endpoint=request.endpoint,
        p256dh_key=request.p256dh,
        auth_key=request.auth,
        device_name=request.device_name,
        device_type=request.device_type,
        browser=request.browser,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to register subscription"))

    return {
        "success": True,
        "subscription_id": result["subscription_id"],
        "reactivated": result.get("reactivated", False),
    }


@router.delete("/subscribe/{subscription_id}")
async def unsubscribe(subscription_id: str):
    """
    Unsubscribe a device from push notifications.
    """
    result = await unregister_subscription(subscription_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to unsubscribe"))

    return {"success": True}


@router.get("/subscriptions", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    user_id: str = Query("default", description="User ID"),
    include_inactive: bool = Query(False, description="Include inactive subscriptions"),
):
    """
    List user's push subscriptions.
    """
    subscriptions = await get_user_subscriptions(
        user_id=user_id,
        active_only=not include_inactive,
    )

    return [
        SubscriptionResponse(
            id=sub["id"],
            device_name=sub.get("device_name"),
            device_type=sub.get("device_type", "web"),
            browser=sub.get("browser"),
            is_active=sub.get("is_active", True),
            created_at=sub.get("created_at", ""),
            last_used_at=sub.get("last_used_at"),
        )
        for sub in subscriptions
    ]


# =============================================================================
# Native Token Endpoints (Expo Mobile App)
# =============================================================================


@router.post("/native-token")
async def register_native_push_token(
    request: NativeTokenRequest,
    user_id: str = Query("default", description="User ID"),
):
    """
    Register a native push token from the Expo mobile app.

    Supports Expo Push tokens (managed), FCM tokens (Android), and APNs tokens (iOS).
    This enables native push notifications for the DexAI mobile wrapper app.
    """
    result = await register_native_token(
        user_id=user_id,
        token=request.token,
        token_type=request.tokenType,
        device_info=request.deviceInfo,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Failed to register native token"),
        )

    return {
        "success": True,
        "subscription_id": result["subscription_id"],
        "reactivated": result.get("reactivated", False),
    }


@router.delete("/native-token/{token}")
async def unregister_native_push_token(
    token: str,
    user_id: str = Query("default", description="User ID"),
    token_type: str | None = Query(None, description="Token type for faster lookup"),
):
    """
    Unregister a native push token (e.g., on user logout).
    """
    result = await unregister_native_token(token=token, token_type=token_type)

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Failed to unregister token"),
        )

    return {"success": True}


@router.get("/native-tokens")
async def list_native_tokens(
    user_id: str = Query("default", description="User ID"),
    include_inactive: bool = Query(False, description="Include inactive tokens"),
):
    """
    List user's native push tokens (mobile app registrations).
    """
    tokens = await get_native_tokens(
        user_id=user_id,
        active_only=not include_inactive,
    )

    return {
        "tokens": tokens,
        "total": len(tokens),
    }


@router.post("/native-test")
async def send_native_test_notification(
    request: TestNotificationRequest,
    user_id: str = Query("default", description="User ID"),
):
    """
    Send a test notification to all native tokens for a user.

    Tests the Expo/FCM/APNs push delivery path.
    """
    result = await send_native_push_batch(
        user_id=user_id,
        notification={
            "title": request.title,
            "body": request.body,
            "data": {"action_url": "/settings/push", "category": "test"},
        },
    )

    if not result.get("success") and result.get("sent", 0) == 0:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "No native tokens or delivery failed"),
        )

    return result


@router.get("/sync")
async def get_sync_status(
    user_id: str = Query("default", description="User ID"),
):
    """
    Get sync status for background fetch.

    Returns badge count and any pending notifications that should be displayed.
    Used by the mobile app's background fetch task.
    """
    # Get badge count from pending notifications
    pending = await get_pending(user_id, include_scheduled=False)
    badge_count = len(pending)

    # Get high-priority pending notifications that should be shown immediately
    urgent_notifications = [
        {
            "id": n.get("id"),
            "title": n.get("title"),
            "body": n.get("body"),
            "data": n.get("data"),
            "priority": n.get("priority", 5),
        }
        for n in pending
        if n.get("priority", 5) >= 8
    ]

    return {
        "badgeCount": badge_count,
        "pendingNotifications": urgent_notifications,
        "lastSync": datetime.utcnow().isoformat(),
    }


# =============================================================================
# Test Notification Endpoint
# =============================================================================


@router.post("/test")
async def send_test_notification(
    request: TestNotificationRequest,
    user_id: str = Query("default", description="User ID"),
):
    """
    Send a test notification to verify push is working.

    ADHD-friendly: Uses supportive language.
    """
    subscriptions = await get_user_subscriptions(user_id, active_only=True)

    if not subscriptions:
        raise HTTPException(
            status_code=400,
            detail="No active subscriptions. Please enable notifications first.",
        )

    results = []
    for sub in subscriptions:
        result = await send_push(
            subscription_id=sub["id"],
            title=request.title,
            body=request.body,
            action_url="/settings/push",
            tag="test_notification",
        )
        results.append({
            "subscription_id": sub["id"],
            "success": result.get("success", False),
            "error": result.get("error"),
        })

    successful = sum(1 for r in results if r["success"])

    return {
        "success": successful > 0,
        "sent_to": successful,
        "total_subscriptions": len(subscriptions),
        "results": results,
    }


# =============================================================================
# Preferences Endpoints
# =============================================================================


@router.get("/preferences")
async def get_user_preferences(
    user_id: str = Query("default", description="User ID"),
):
    """
    Get user's notification preferences.
    """
    prefs = await get_preferences(user_id)
    return prefs


@router.put("/preferences")
async def update_user_preferences(
    request: PreferencesUpdateRequest,
    user_id: str = Query("default", description="User ID"),
):
    """
    Update notification preferences.
    """
    updates = request.model_dump(exclude_none=True)

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    # Handle quiet hours specially
    if "quiet_hours_start" in updates and "quiet_hours_end" in updates:
        result = await set_quiet_hours(
            user_id=user_id,
            start=updates.pop("quiet_hours_start"),
            end=updates.pop("quiet_hours_end"),
            timezone=updates.pop("timezone", None),
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))

    # Update remaining preferences
    if updates:
        result = await update_preferences(user_id, **updates)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))

    # Return updated preferences
    return await get_preferences(user_id)


# =============================================================================
# Category Endpoints
# =============================================================================


@router.get("/categories")
async def list_categories():
    """
    List all notification categories.

    Returns categories with their default settings.
    """
    # Ensure default categories exist
    seed_default_categories()

    categories = await get_categories()
    return {"categories": categories}


@router.put("/categories/{category_id}")
async def update_category_preference(
    category_id: str,
    request: CategoryUpdateRequest,
    user_id: str = Query("default", description="User ID"),
):
    """
    Update user's preferences for a notification category.
    """
    result = await set_category_preference(
        user_id=user_id,
        category=category_id,
        enabled=request.enabled,
        priority_threshold=request.priority_threshold,
        batch=request.batch,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return {"success": True}


# =============================================================================
# History and Stats Endpoints
# =============================================================================


@router.get("/history")
async def get_push_history(
    user_id: str = Query("default", description="User ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
):
    """
    Get notification history for a user.
    """
    history = await get_notification_history(
        user_id=user_id,
        limit=limit,
        include_failed=False,
    )

    return {
        "notifications": history,
        "total": len(history),
    }


@router.get("/stats")
async def get_push_stats(
    user_id: str = Query(None, description="Optional user ID"),
    days: int = Query(7, ge=1, le=90, description="Days to look back"),
):
    """
    Get notification delivery statistics.

    Returns aggregate metrics and trends.
    """
    stats = await get_stats(user_id=user_id, days=days)

    return stats


@router.get("/pending")
async def get_pending_notifications(
    user_id: str = Query("default", description="User ID"),
):
    """
    Get pending notifications in the queue.
    """
    pending = await get_pending(user_id, include_scheduled=True)

    return {
        "pending": pending,
        "total": len(pending),
    }


@router.delete("/pending/{notification_id}")
async def cancel_pending_notification(notification_id: str):
    """
    Cancel a pending notification.
    """
    result = await cancel(notification_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return {"success": True}


# =============================================================================
# Tracking Endpoints (for service worker callbacks)
# =============================================================================


@router.post("/track/delivered")
async def track_notification_delivered(
    notification_id: str = Query(..., description="Notification ID"),
):
    """
    Track that a notification was delivered to the device.

    Called by the service worker when it receives a push event.
    """
    from tools.mobile.analytics.delivery_tracker import track_delivered

    # Note: In a full implementation, we'd look up the delivery_id
    # For now, we track by notification_id
    result = await track_delivered(notification_id)

    return {"success": True}


@router.post("/track/clicked")
async def track_notification_clicked(
    notification_id: str = Query(..., description="Notification ID"),
):
    """
    Track that a notification was clicked.

    Called when user clicks the notification.
    """
    from tools.mobile.analytics.delivery_tracker import track_clicked

    result = await track_clicked(notification_id=notification_id)

    return {"success": True}


@router.post("/track/dismissed")
async def track_notification_dismissed(
    notification_id: str = Query(..., description="Notification ID"),
):
    """
    Track that a notification was dismissed.

    Called when user dismisses without clicking.
    """
    from tools.mobile.analytics.delivery_tracker import track_dismissed

    result = await track_dismissed(notification_id=notification_id)

    return {"success": True}
