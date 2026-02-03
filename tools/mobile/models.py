"""
Tool: Mobile Push Notification Models
Purpose: Data structures for push notifications

Usage:
    from tools.mobile.models import (
        PushSubscription,
        Notification,
        NotificationCategory,
        DeliveryStatus,
        DeliveryResult,
    )
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DeliveryStatus(str, Enum):
    """Notification delivery status."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    CLICKED = "clicked"
    DISMISSED = "dismissed"
    FAILED = "failed"
    BATCHED = "batched"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"


class NotificationPriority(int, Enum):
    """
    Notification priority levels.

    ADHD-friendly: lower priorities batch, higher priorities interrupt.
    """

    LOWEST = 1      # Daily summaries, informational
    LOW = 3         # Non-urgent reminders
    NORMAL = 5      # Standard notifications
    HIGH = 7        # Important tasks
    URGENT = 8      # Can interrupt flow state
    CRITICAL = 10   # Always delivered immediately


@dataclass
class PushSubscription:
    """
    Web Push subscription.

    Represents a browser's push notification endpoint with VAPID keys.
    """

    id: str
    user_id: str
    endpoint: str  # Web Push endpoint URL
    p256dh_key: str  # Client public key for encryption
    auth_key: str  # Auth secret

    # Device info
    device_name: str | None = None
    device_type: str = "web"  # 'web', 'android', 'ios'
    browser: str | None = None  # 'chrome', 'firefox', 'safari', 'edge'

    # Status
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for database storage."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "endpoint": self.endpoint,
            "p256dh_key": self.p256dh_key,
            "auth_key": self.auth_key,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "browser": self.browser,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PushSubscription":
        """Create from dict."""
        data = data.copy()
        for field_name in ["created_at", "last_used_at"]:
            if isinstance(data.get(field_name), str):
                data[field_name] = datetime.fromisoformat(data[field_name])
        return cls(**data)

    @staticmethod
    def generate_id() -> str:
        """Generate a new subscription ID."""
        return f"sub_{uuid.uuid4().hex[:12]}"

    def get_subscription_info(self) -> dict:
        """Get subscription info for pywebpush."""
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": self.p256dh_key,
                "auth": self.auth_key,
            },
        }


@dataclass
class Notification:
    """
    Push notification.

    Represents a notification in the queue with all metadata.
    """

    id: str
    user_id: str
    category: str
    title: str

    # Content
    body: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    icon_url: str | None = None
    action_url: str | None = None

    # Priority and timing
    priority: int = 5
    scheduled_for: datetime | None = None
    expires_at: datetime | None = None

    # Batching
    batch_key: str | None = None
    batch_window_seconds: int = 300

    # Flow protection
    respect_flow_state: bool = True
    min_priority_to_interrupt: int = 8

    # Status
    status: DeliveryStatus = DeliveryStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    sent_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for database storage."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category": self.category,
            "title": self.title,
            "body": self.body,
            "data": json.dumps(self.data) if self.data else None,
            "icon_url": self.icon_url,
            "action_url": self.action_url,
            "priority": self.priority,
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "batch_key": self.batch_key,
            "batch_window_seconds": self.batch_window_seconds,
            "respect_flow_state": self.respect_flow_state,
            "min_priority_to_interrupt": self.min_priority_to_interrupt,
            "status": self.status.value if isinstance(self.status, DeliveryStatus) else self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Notification":
        """Create from dict."""
        data = data.copy()

        # Parse JSON data
        if isinstance(data.get("data"), str):
            data["data"] = json.loads(data["data"]) if data["data"] else {}
        elif data.get("data") is None:
            data["data"] = {}

        # Parse datetime fields
        for field_name in ["scheduled_for", "expires_at", "created_at", "sent_at"]:
            if isinstance(data.get(field_name), str):
                data[field_name] = datetime.fromisoformat(data[field_name])

        # Parse status
        if isinstance(data.get("status"), str):
            data["status"] = DeliveryStatus(data["status"])

        return cls(**data)

    @staticmethod
    def generate_id() -> str:
        """Generate a new notification ID."""
        return f"notif_{uuid.uuid4().hex[:12]}"

    def to_push_payload(self) -> dict:
        """Convert to Web Push notification payload."""
        payload = {
            "title": self.title,
            "body": self.body,
            "icon": self.icon_url or "/icons/dex-192.png",
            "badge": "/icons/badge-72.png",
            "data": {
                **self.data,
                "notification_id": self.id,
                "action_url": self.action_url or "/",
            },
            "tag": self.batch_key or self.id,
            "requireInteraction": self.priority >= 8,
            "silent": self.priority < 3,
        }

        return payload

    def can_batch(self) -> bool:
        """Check if this notification can be batched."""
        return self.batch_key is not None and self.priority < 8

    def is_expired(self) -> bool:
        """Check if notification has expired."""
        if not self.expires_at:
            return False
        return datetime.now() > self.expires_at


@dataclass
class NotificationCategory:
    """
    Notification category definition.

    Defines default behavior for a category of notifications.
    """

    id: str
    name: str
    description: str | None = None
    default_priority: int = 5
    default_icon: str | None = None
    color: str | None = None
    can_batch: bool = True
    can_suppress: bool = True  # Can be suppressed by flow state
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for database storage."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "default_priority": self.default_priority,
            "default_icon": self.default_icon,
            "color": self.color,
            "can_batch": self.can_batch,
            "can_suppress": self.can_suppress,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NotificationCategory":
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


@dataclass
class DeliveryResult:
    """
    Result of attempting to deliver a notification.
    """

    success: bool
    delivery_id: str | None = None
    subscription_id: str | None = None
    notification_id: str | None = None
    error: str | None = None
    should_unsubscribe: bool = False  # True if endpoint is invalid (410 Gone)
    retry_after: int | None = None  # Seconds to wait before retry

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return asdict(self)


@dataclass
class UserPreferences:
    """
    User notification preferences.
    """

    user_id: str
    enabled: bool = True

    # Quiet hours
    quiet_hours_start: str | None = None  # "22:00"
    quiet_hours_end: str | None = None  # "08:00"
    timezone: str = "UTC"

    # Category settings (JSON string in DB)
    category_settings: dict[str, dict] = field(default_factory=dict)

    # Flow protection
    respect_flow_state: bool = True
    flow_interrupt_threshold: int = 8

    # Batching
    batch_notifications: bool = True
    batch_window_minutes: int = 5

    # Rate limiting (ADHD-specific)
    max_notifications_per_hour: int = 6
    cooldown_after_burst_minutes: int = 30

    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for database storage."""
        return {
            "user_id": self.user_id,
            "enabled": self.enabled,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "timezone": self.timezone,
            "category_settings": json.dumps(self.category_settings),
            "respect_flow_state": self.respect_flow_state,
            "flow_interrupt_threshold": self.flow_interrupt_threshold,
            "batch_notifications": self.batch_notifications,
            "batch_window_minutes": self.batch_window_minutes,
            "max_notifications_per_hour": self.max_notifications_per_hour,
            "cooldown_after_burst_minutes": self.cooldown_after_burst_minutes,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserPreferences":
        """Create from dict."""
        data = data.copy()

        if isinstance(data.get("category_settings"), str):
            data["category_settings"] = json.loads(data["category_settings"]) if data["category_settings"] else {}
        elif data.get("category_settings") is None:
            data["category_settings"] = {}

        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        return cls(**data)


# Default categories for seeding
DEFAULT_CATEGORIES = [
    NotificationCategory(
        id="task_reminder",
        name="Task Reminder",
        description="Reminders about upcoming or pending tasks",
        default_priority=6,
        default_icon="task",
        color="#4F46E5",
        can_batch=True,
        can_suppress=True,
    ),
    NotificationCategory(
        id="commitment_due",
        name="Commitment Due",
        description="Important deadlines and commitments",
        default_priority=8,
        default_icon="commitment",
        color="#DC2626",
        can_batch=False,
        can_suppress=False,  # Always deliver
    ),
    NotificationCategory(
        id="message_received",
        name="Message Received",
        description="New messages from channels",
        default_priority=5,
        default_icon="message",
        color="#059669",
        can_batch=True,
        can_suppress=True,
    ),
    NotificationCategory(
        id="flow_state_ended",
        name="Flow State Ended",
        description="Notification when flow/focus session ends",
        default_priority=4,
        default_icon="flow",
        color="#8B5CF6",
        can_batch=False,
        can_suppress=False,
    ),
    NotificationCategory(
        id="daily_summary",
        name="Daily Summary",
        description="Daily progress and upcoming tasks summary",
        default_priority=3,
        default_icon="summary",
        color="#6B7280",
        can_batch=False,
        can_suppress=True,
    ),
]


if __name__ == "__main__":
    # Self-test
    import sys

    print("Testing mobile notification models...")

    # Test PushSubscription
    sub = PushSubscription(
        id=PushSubscription.generate_id(),
        user_id="user-1",
        endpoint="https://fcm.googleapis.com/fcm/send/abc123",
        p256dh_key="BNcRdreALR...",
        auth_key="tBHItJI5...",
        device_name="Chrome Desktop",
        browser="chrome",
    )
    d = sub.to_dict()
    sub2 = PushSubscription.from_dict(d)
    assert sub.endpoint == sub2.endpoint
    assert sub.id == sub2.id

    # Test subscription info
    info = sub.get_subscription_info()
    assert "endpoint" in info
    assert "keys" in info
    assert "p256dh" in info["keys"]

    # Test Notification
    notif = Notification(
        id=Notification.generate_id(),
        user_id="user-1",
        category="task_reminder",
        title="Time for your next task",
        body="Your focus session is complete. Ready for the next step?",
        priority=6,
        data={"task_id": "task-123"},
        action_url="/tasks/task-123",
        batch_key="task_reminders",
    )
    d = notif.to_dict()
    notif2 = Notification.from_dict(d)
    assert notif.title == notif2.title
    assert notif.data == notif2.data
    assert notif.can_batch()

    # Test push payload
    payload = notif.to_push_payload()
    assert payload["title"] == notif.title
    assert "notification_id" in payload["data"]

    # Test NotificationCategory
    cat = NotificationCategory(
        id="test_category",
        name="Test",
        default_priority=5,
        can_batch=True,
        can_suppress=True,
    )
    d = cat.to_dict()
    cat2 = NotificationCategory.from_dict(d)
    assert cat.id == cat2.id

    # Test DeliveryResult
    result = DeliveryResult(
        success=True,
        delivery_id="del-123",
        notification_id=notif.id,
    )
    d = result.to_dict()
    assert d["success"]

    # Test UserPreferences
    prefs = UserPreferences(
        user_id="user-1",
        quiet_hours_start="22:00",
        quiet_hours_end="08:00",
        category_settings={"task_reminder": {"enabled": True, "priority_threshold": 5}},
    )
    d = prefs.to_dict()
    prefs2 = UserPreferences.from_dict(d)
    assert prefs.quiet_hours_start == prefs2.quiet_hours_start
    assert prefs.category_settings == prefs2.category_settings

    print("OK: All mobile model tests passed")
    sys.exit(0)
