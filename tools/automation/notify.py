"""
Tool: Notification Dispatch
Purpose: Queue and send notifications to users via channels

Features:
- Priority-based notification queue (low, normal, high, urgent)
- Do Not Disturb (DND) respect with queue-for-later
- Channel preference routing
- Notification aggregation to reduce noise
- Integration with channels router
- Flow state awareness (suppress during hyperfocus)
- ADHD-friendly batching of suppressed notifications

Usage:
    python tools/automation/notify.py --action send --user alice --content "Your task completed"
    python tools/automation/notify.py --action queue --user alice --content "Reminder" --priority normal
    python tools/automation/notify.py --action list --status pending
    python tools/automation/notify.py --action process
    python tools/automation/notify.py --action send --user alice --content "FYI" --priority low --flow-aware
    python tools/automation/notify.py --action check-flow --user alice --priority normal
    python tools/automation/notify.py --action suppressed-count --user alice
    python tools/automation/notify.py --action list-suppressed --user alice
    python tools/automation/notify.py --action release-suppressed --user alice

Dependencies:
    - pyyaml
    - tools.channels.router (for sending)
    - tools.automation.flow_detector (for flow state)
"""

import argparse
import asyncio
import json
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.automation import CONFIG_PATH, DB_PATH


# Valid priorities
VALID_PRIORITIES = ["low", "normal", "high", "urgent"]
VALID_STATUSES = ["pending", "sent", "failed", "queued_dnd", "suppressed"]

# Smart notifications config path
SMART_NOTIFICATIONS_CONFIG = PROJECT_ROOT / "args" / "smart_notifications.yaml"


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    default_config = {
        "notifications": {
            "enabled": True,
            "process_interval": 10,
            "use_preferred_channel": True,
            "priorities": {
                "urgent": {"ignore_dnd": True, "retry_count": 5},
                "high": {"ignore_dnd": False, "retry_count": 3},
                "normal": {"ignore_dnd": False, "retry_count": 2},
                "low": {"ignore_dnd": False, "retry_count": 1},
            },
            "dnd": {
                "enabled": True,
                "default_start": "22:00",
                "default_end": "08:00",
                "queue_during_dnd": True,
            },
            "aggregation": {"enabled": True, "window_seconds": 300, "max_batch_size": 10},
        }
    }

    if not CONFIG_PATH.exists():
        return default_config

    try:
        import yaml

        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        return config if config else default_config
    except Exception:
        return default_config


def load_smart_notifications_config() -> dict[str, Any]:
    """Load smart notifications configuration."""
    default_config = {
        "smart_notifications": {
            "flow_protection": {
                "enabled": True,
                "detection_window_minutes": 15,
                "min_activity_for_flow": 3,
                "flow_score_threshold": 60,
                "suppress_low_priority": True,
                "suppress_medium_during_deep_flow": True,
                "deep_flow_threshold": 80,
            },
            "priority_tiers": {
                "low": {"suppress_during_flow": True},
                "medium": {"suppress_during_deep_flow": True},
                "high": {"suppress_during_flow": False, "use_gentle_during_focus": True},
                "urgent": {"suppress_during_flow": False, "always_deliver": True},
            },
        }
    }

    if not SMART_NOTIFICATIONS_CONFIG.exists():
        return default_config

    try:
        import yaml

        with open(SMART_NOTIFICATIONS_CONFIG) as f:
            config = yaml.safe_load(f)
        return config if config else default_config
    except Exception:
        return default_config


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Notifications table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            priority TEXT CHECK(priority IN ('low', 'normal', 'high', 'urgent')) DEFAULT 'normal',
            channel TEXT,
            status TEXT CHECK(status IN ('pending', 'sent', 'failed', 'queued_dnd')) DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            sent_at DATETIME,
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            source TEXT,
            aggregation_key TEXT
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_priority ON notifications(priority)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at)"
    )

    # Suppressed notifications table - for flow state queuing
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppressed_notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            priority TEXT DEFAULT 'normal',
            original_channel TEXT,
            suppression_reason TEXT,
            suppressed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            release_after DATETIME,
            released INTEGER DEFAULT 0,
            released_at DATETIME
        )
    """)

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_suppressed_user ON suppressed_notifications(user_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_suppressed_released ON suppressed_notifications(released)"
    )

    conn.commit()
    return conn


def queue_notification(
    user_id: str,
    content: str,
    priority: str = "normal",
    channel: str | None = None,
    source: str | None = None,
    aggregation_key: str | None = None,
) -> str:
    """
    Queue a notification for delivery.

    Args:
        user_id: Target user ID
        content: Notification message content
        priority: 'low', 'normal', 'high', or 'urgent'
        channel: Specific channel to use (or None for preferred)
        source: Source of notification (e.g., 'heartbeat', 'cron:job_name')
        aggregation_key: Key for grouping similar notifications

    Returns:
        Notification ID
    """
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority: {priority}. Must be one of {VALID_PRIORITIES}")

    notification_id = str(uuid.uuid4())

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO notifications (id, user_id, content, priority, channel, source, aggregation_key)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (notification_id, user_id, content, priority, channel, source, aggregation_key),
    )

    conn.commit()
    conn.close()

    # Log to audit
    try:
        from tools.security import audit

        audit.log_event(
            event_type="system",
            action="notification_queued",
            user_id=user_id,
            resource=f"notification:{notification_id}",
            status="success",
            details={"priority": priority, "source": source},
        )
    except Exception:
        pass

    return notification_id


def get_notification(notification_id: str) -> dict[str, Any] | None:
    """Get a notification by ID."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "content": row["content"],
        "priority": row["priority"],
        "channel": row["channel"],
        "status": row["status"],
        "created_at": row["created_at"],
        "sent_at": row["sent_at"],
        "error": row["error"],
        "retry_count": row["retry_count"],
        "source": row["source"],
        "aggregation_key": row["aggregation_key"],
    }


def list_notifications(
    user_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List notifications with optional filters."""
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM notifications WHERE 1=1"
    params = []

    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)

    if status:
        query += " AND status = ?"
        params.append(status)

    if priority:
        query += " AND priority = ?"
        params.append(priority)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    notifications = []
    for row in rows:
        notifications.append(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "content": row["content"][:100] + "..."
                if len(row["content"]) > 100
                else row["content"],
                "priority": row["priority"],
                "channel": row["channel"],
                "status": row["status"],
                "created_at": row["created_at"],
                "sent_at": row["sent_at"],
                "source": row["source"],
            }
        )

    return notifications


def get_user_dnd_settings(user_id: str) -> dict[str, Any]:
    """
    Get DND settings for a user.

    First checks user preferences in inbox.db, falls back to defaults.
    """
    config = load_config()
    dnd_config = config.get("notifications", {}).get("dnd", {})

    defaults = {
        "enabled": dnd_config.get("enabled", True),
        "start": dnd_config.get("default_start", "22:00"),
        "end": dnd_config.get("default_end", "08:00"),
    }

    # Try to get user preferences
    try:
        inbox_db = PROJECT_ROOT / "data" / "inbox.db"
        if inbox_db.exists():
            conn = sqlite3.connect(str(inbox_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT preferences FROM user_preferences WHERE user_id = ?
            """,
                (user_id,),
            )
            row = cursor.fetchone()
            conn.close()

            if row and row["preferences"]:
                prefs = json.loads(row["preferences"])
                if "dnd" in prefs:
                    return prefs["dnd"]
    except Exception:
        pass

    return defaults


def is_in_dnd(user_id: str) -> bool:
    """Check if user is currently in Do Not Disturb period."""
    dnd_settings = get_user_dnd_settings(user_id)

    if not dnd_settings.get("enabled", False):
        return False

    start_str = dnd_settings.get("start", "22:00")
    end_str = dnd_settings.get("end", "08:00")

    now = datetime.now()
    current_time = now.strftime("%H:%M")

    # Handle overnight DND (e.g., 22:00 to 08:00)
    if start_str > end_str:
        # Overnight: in DND if after start OR before end
        return current_time >= start_str or current_time <= end_str
    else:
        # Same day: in DND if between start and end
        return start_str <= current_time <= end_str


def get_delivery_channel(user_id: str) -> str | None:
    """
    Get the preferred delivery channel for a user.

    Checks user preferences in inbox.db.
    """
    try:
        inbox_db = PROJECT_ROOT / "data" / "inbox.db"
        if inbox_db.exists():
            conn = sqlite3.connect(str(inbox_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT preferences FROM user_preferences WHERE user_id = ?
            """,
                (user_id,),
            )
            row = cursor.fetchone()
            conn.close()

            if row and row["preferences"]:
                prefs = json.loads(row["preferences"])
                return prefs.get("preferred_channel")
    except Exception:
        pass

    return None


def update_notification(notification_id: str, **updates) -> dict[str, Any]:
    """Update notification fields."""
    conn = get_connection()
    cursor = conn.cursor()

    allowed_fields = {"status", "sent_at", "error", "retry_count", "channel"}
    valid_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not valid_updates:
        conn.close()
        return {"success": False, "error": "No valid fields to update"}

    set_clauses = [f"{k} = ?" for k in valid_updates]
    params = list(valid_updates.values())
    params.append(notification_id)

    cursor.execute(f"UPDATE notifications SET {', '.join(set_clauses)} WHERE id = ?", params)

    if cursor.rowcount == 0:
        conn.close()
        return {"success": False, "error": f"Notification '{notification_id}' not found"}

    conn.commit()
    conn.close()

    return {"success": True, "notification_id": notification_id}


async def send_notification(notification_id: str) -> dict[str, Any]:
    """
    Send a single notification via the channels router.

    Args:
        notification_id: ID of notification to send

    Returns:
        dict with success status and details
    """
    notification = get_notification(notification_id)
    if not notification:
        return {"success": False, "error": f"Notification '{notification_id}' not found"}

    if notification["status"] == "sent":
        return {"success": True, "already_sent": True}

    config = load_config()
    notif_config = config.get("notifications", {})
    priority_config = notif_config.get("priorities", {}).get(notification["priority"], {})

    # Check DND
    in_dnd = is_in_dnd(notification["user_id"])
    ignore_dnd = priority_config.get("ignore_dnd", False)

    if in_dnd and not ignore_dnd:
        if notif_config.get("dnd", {}).get("queue_during_dnd", True):
            update_notification(notification_id, status="queued_dnd")
            return {
                "success": True,
                "queued_dnd": True,
                "message": "Notification queued during DND period",
            }
        else:
            return {"success": False, "error": "User in DND and queuing disabled"}

    # Determine channel
    channel = notification["channel"]
    if not channel and notif_config.get("use_preferred_channel", True):
        channel = get_delivery_channel(notification["user_id"])

    # Try to send via router
    try:
        from tools.channels.router import get_router

        router = get_router()

        result = await router.broadcast(
            user_id=notification["user_id"],
            content=notification["content"],
            priority=notification["priority"],
            channel=channel,
        )

        if result.get("success"):
            update_notification(
                notification_id,
                status="sent",
                sent_at=datetime.now().isoformat(),
                channel=result.get("channel"),
            )
            return {
                "success": True,
                "notification_id": notification_id,
                "channel": result.get("channel"),
                "message": "Notification sent successfully",
            }
        else:
            # Increment retry count
            retry_count = notification["retry_count"] + 1
            max_retries = priority_config.get("retry_count", 2)

            if retry_count >= max_retries:
                update_notification(
                    notification_id,
                    status="failed",
                    error=result.get("error", "Send failed"),
                    retry_count=retry_count,
                )
            else:
                update_notification(
                    notification_id, error=result.get("error"), retry_count=retry_count
                )

            return {
                "success": False,
                "error": result.get("error", "Send failed"),
                "retry_count": retry_count,
            }

    except ImportError:
        # Router not available - mark as failed or pending
        update_notification(notification_id, status="pending", error="Router not available")
        return {"success": False, "error": "Channels router not available"}
    except Exception as e:
        update_notification(notification_id, status="failed", error=str(e))
        return {"success": False, "error": str(e)}


async def process_pending() -> dict[str, Any]:
    """
    Process all pending notifications.

    Handles aggregation, DND, and priority ordering.
    """
    config = load_config()
    notif_config = config.get("notifications", {})

    if not notif_config.get("enabled", True):
        return {"success": True, "skipped": True, "reason": "Notifications disabled"}

    conn = get_connection()
    cursor = conn.cursor()

    # Get pending notifications, ordered by priority and age
    priority_order = "CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 END"
    cursor.execute(f"""
        SELECT id FROM notifications
        WHERE status IN ('pending', 'queued_dnd')
        ORDER BY {priority_order}, created_at ASC
    """)

    pending_ids = [row["id"] for row in cursor.fetchall()]
    conn.close()

    if not pending_ids:
        return {"success": True, "processed": 0, "message": "No pending notifications"}

    sent = 0
    failed = 0
    queued = 0

    for notification_id in pending_ids:
        result = await send_notification(notification_id)

        if result.get("success"):
            if result.get("queued_dnd"):
                queued += 1
            elif not result.get("already_sent"):
                sent += 1
        else:
            failed += 1

    return {
        "success": True,
        "processed": len(pending_ids),
        "sent": sent,
        "failed": failed,
        "queued_dnd": queued,
        "message": f"Processed {len(pending_ids)}: {sent} sent, {failed} failed, {queued} queued",
    }


def get_stats() -> dict[str, Any]:
    """Get notification statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    # Total by status
    cursor.execute("""
        SELECT status, COUNT(*) as count FROM notifications
        GROUP BY status
    """)
    by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

    # Total by priority
    cursor.execute("""
        SELECT priority, COUNT(*) as count FROM notifications
        GROUP BY priority
    """)
    by_priority = {row["priority"]: row["count"] for row in cursor.fetchall()}

    # Recent (24h)
    cursor.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE created_at > datetime('now', '-24 hours')
    """)
    last_24h = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE status = 'sent' AND sent_at > datetime('now', '-24 hours')
    """)
    sent_24h = cursor.fetchone()[0]

    conn.close()

    return {
        "success": True,
        "by_status": by_status,
        "by_priority": by_priority,
        "last_24h": {"created": last_24h, "sent": sent_24h},
    }


# =============================================================================
# Flow Awareness Functions (Phase 4: Smart Notifications)
# =============================================================================


def should_suppress(user_id: str, priority: str) -> dict[str, Any]:
    """
    Check if a notification should be suppressed based on flow state.

    Uses flow_detector to check user's current state and applies
    priority-based suppression rules from smart_notifications.yaml.

    Args:
        user_id: User identifier
        priority: Notification priority ('low', 'normal', 'high', 'urgent')

    Returns:
        dict with should_suppress flag and reason
    """
    config = load_smart_notifications_config()
    flow_config = config.get("smart_notifications", {}).get("flow_protection", {})
    priority_tiers = config.get("smart_notifications", {}).get("priority_tiers", {})

    # Check if flow protection is enabled
    if not flow_config.get("enabled", True):
        return {"success": True, "should_suppress": False, "reason": "Flow protection disabled"}

    # Urgent always gets through
    if priority == "urgent":
        return {
            "success": True,
            "should_suppress": False,
            "reason": "Urgent priority always delivered",
        }

    # Get flow state from detector
    try:
        from tools.automation.flow_detector import detect_flow

        flow_result = detect_flow(user_id)

        if not flow_result.get("success"):
            # If flow detection fails, allow notification through
            return {
                "success": True,
                "should_suppress": False,
                "reason": "Flow detection unavailable",
            }

        in_flow = flow_result.get("in_flow", False)
        deep_flow = flow_result.get("deep_flow", False)
        flow_score = flow_result.get("score", 0)

        if not in_flow:
            return {
                "success": True,
                "should_suppress": False,
                "reason": "User not in flow state",
                "flow_score": flow_score,
            }

        # Apply priority-based rules
        tier_config = priority_tiers.get(priority, {})

        # Map 'normal' priority to 'medium' tier if needed
        if priority == "normal" and not tier_config:
            tier_config = priority_tiers.get("medium", {})

        # Low priority: suppress during any flow
        if priority == "low" and (
            tier_config.get("suppress_during_flow", True)
            or flow_config.get("suppress_low_priority", True)
        ):
            return {
                "success": True,
                "should_suppress": True,
                "reason": "Low priority suppressed during flow",
                "flow_score": flow_score,
                "deep_flow": deep_flow,
            }

        # Normal/medium priority: suppress during deep flow only
        if priority == "normal":
            if deep_flow and (
                tier_config.get("suppress_during_deep_flow", True)
                or flow_config.get("suppress_medium_during_deep_flow", True)
            ):
                return {
                    "success": True,
                    "should_suppress": True,
                    "reason": "Medium priority suppressed during deep flow",
                    "flow_score": flow_score,
                    "deep_flow": deep_flow,
                }
            else:
                return {
                    "success": True,
                    "should_suppress": False,
                    "reason": "Medium priority allowed during light flow",
                    "flow_score": flow_score,
                }

        # High priority: never suppress (but may use gentler channel)
        if priority == "high":
            return {
                "success": True,
                "should_suppress": False,
                "reason": "High priority not suppressed",
                "flow_score": flow_score,
                "use_gentle_channel": tier_config.get("use_gentle_during_focus", True) and in_flow,
            }

        # Default: don't suppress
        return {
            "success": True,
            "should_suppress": False,
            "reason": "Default: notification allowed",
            "flow_score": flow_score,
        }

    except ImportError:
        return {"success": True, "should_suppress": False, "reason": "Flow detector not available"}
    except Exception as e:
        return {"success": True, "should_suppress": False, "reason": f"Flow check error: {e!s}"}


def queue_for_later(
    user_id: str,
    content: str,
    priority: str = "normal",
    channel: str | None = None,
    release_after: str | None = None,
    suppression_reason: str | None = None,
) -> dict[str, Any]:
    """
    Queue a notification for delivery after flow state ends.

    Args:
        user_id: Target user ID
        content: Notification content
        priority: Notification priority
        channel: Original intended channel
        release_after: Optional datetime to release (ISO format)
        suppression_reason: Why the notification was suppressed

    Returns:
        dict with success status and suppression ID
    """
    suppression_id = str(uuid.uuid4())

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO suppressed_notifications
        (id, user_id, content, priority, original_channel, suppression_reason, release_after)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            suppression_id,
            user_id,
            content,
            priority,
            channel,
            suppression_reason or "flow_state",
            release_after,
        ),
    )

    conn.commit()
    conn.close()

    # Log to audit
    try:
        from tools.security import audit

        audit.log_event(
            event_type="system",
            action="notification_suppressed",
            user_id=user_id,
            resource=f"suppressed:{suppression_id}",
            status="success",
            details={"priority": priority, "reason": suppression_reason},
        )
    except Exception:
        pass

    return {
        "success": True,
        "suppression_id": suppression_id,
        "message": "Notification queued for later delivery",
        "queued_until": "flow_ends" if not release_after else release_after,
    }


def get_suppressed_count(user_id: str) -> dict[str, Any]:
    """
    Get count of suppressed notifications for a user.

    Args:
        user_id: User identifier

    Returns:
        dict with count by priority
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT priority, COUNT(*) as count
        FROM suppressed_notifications
        WHERE user_id = ? AND released = 0
        GROUP BY priority
    """,
        (user_id,),
    )

    priorities = {}
    total = 0
    for row in cursor.fetchall():
        priorities[row["priority"]] = row["count"]
        total += row["count"]

    conn.close()

    return {"success": True, "count": total, "priorities": priorities}


def list_suppressed(user_id: str, limit: int = 50) -> dict[str, Any]:
    """
    List suppressed notifications for a user.

    Args:
        user_id: User identifier
        limit: Maximum results

    Returns:
        dict with suppressed notifications list
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, content, priority, suppression_reason, suppressed_at
        FROM suppressed_notifications
        WHERE user_id = ? AND released = 0
        ORDER BY suppressed_at ASC
        LIMIT ?
    """,
        (user_id, limit),
    )

    notifications = []
    for row in cursor.fetchall():
        notifications.append(
            {
                "id": row["id"],
                "content": row["content"][:100] + "..."
                if len(row["content"]) > 100
                else row["content"],
                "priority": row["priority"],
                "reason": row["suppression_reason"],
                "suppressed_at": row["suppressed_at"],
            }
        )

    conn.close()

    return {"success": True, "notifications": notifications, "count": len(notifications)}


def release_suppressed(user_id: str, send_immediately: bool = False) -> dict[str, Any]:
    """
    Release all suppressed notifications for a user.

    Args:
        user_id: User identifier
        send_immediately: If True, send notifications now; otherwise just mark as released

    Returns:
        dict with release count
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get suppressed notifications
    cursor.execute(
        """
        SELECT id, content, priority, original_channel
        FROM suppressed_notifications
        WHERE user_id = ? AND released = 0
        ORDER BY suppressed_at ASC
    """,
        (user_id,),
    )

    to_release = cursor.fetchall()

    if not to_release:
        conn.close()
        return {"success": True, "released": 0, "message": "No suppressed notifications to release"}

    released_count = 0
    sent_count = 0
    now = datetime.now().isoformat()

    for row in to_release:
        # Mark as released
        cursor.execute(
            """
            UPDATE suppressed_notifications
            SET released = 1, released_at = ?
            WHERE id = ?
        """,
            (now, row["id"]),
        )
        released_count += 1

        # Optionally send immediately
        if send_immediately:
            try:
                notification_id = queue_notification(
                    user_id=user_id,
                    content=row["content"],
                    priority=row["priority"],
                    channel=row["original_channel"],
                    source="released_suppression",
                )
                sent_count += 1
            except Exception:
                pass

    conn.commit()
    conn.close()

    # Log to audit
    try:
        from tools.security import audit

        audit.log_event(
            event_type="system",
            action="notifications_released",
            user_id=user_id,
            status="success",
            details={"released": released_count, "sent": sent_count},
        )
    except Exception:
        pass

    return {
        "success": True,
        "released": released_count,
        "sent": sent_count if send_immediately else 0,
        "message": f"{released_count} notifications released",
    }


async def send_with_flow_awareness(
    user_id: str,
    content: str,
    priority: str = "normal",
    channel: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """
    Send a notification with flow state awareness.

    If user is in flow and priority allows suppression, queues for later.
    Otherwise sends immediately.

    Args:
        user_id: Target user ID
        content: Notification content
        priority: Notification priority
        channel: Specific channel to use
        source: Source of notification

    Returns:
        dict with result (sent or suppressed)
    """
    # Check if we should suppress
    suppress_check = should_suppress(user_id, priority)

    if suppress_check.get("should_suppress"):
        # Queue for later
        result = queue_for_later(
            user_id=user_id,
            content=content,
            priority=priority,
            channel=channel,
            suppression_reason=suppress_check.get("reason"),
        )
        result["suppressed"] = True
        result["flow_score"] = suppress_check.get("flow_score")
        return result

    # Send immediately
    notification_id = queue_notification(
        user_id=user_id, content=content, priority=priority, channel=channel, source=source
    )

    send_result = await send_notification(notification_id)
    send_result["suppressed"] = False
    send_result["flow_score"] = suppress_check.get("flow_score")

    # If high priority during focus, note the gentle channel suggestion
    if suppress_check.get("use_gentle_channel"):
        send_result["used_gentle_channel"] = True

    return send_result


def main():
    parser = argparse.ArgumentParser(description="Notification Dispatch")
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "queue",
            "send",
            "list",
            "process",
            "get",
            "stats",
            "check-flow",
            "suppressed-count",
            "list-suppressed",
            "release-suppressed",
        ],
        help="Action to perform",
    )

    parser.add_argument("--user", help="User ID")
    parser.add_argument("--content", help="Notification content")
    parser.add_argument(
        "--priority", default="normal", choices=VALID_PRIORITIES, help="Notification priority"
    )
    parser.add_argument("--channel", help="Specific channel to use")
    parser.add_argument("--source", help="Source of notification")
    parser.add_argument("--id", help="Notification ID")
    parser.add_argument("--status", help="Filter by status")
    parser.add_argument("--limit", type=int, default=50, help="Result limit")
    parser.add_argument(
        "--flow-aware",
        dest="flow_aware",
        action="store_true",
        help="Check flow state before sending (suppress if in flow)",
    )
    parser.add_argument(
        "--send-on-release",
        dest="send_on_release",
        action="store_true",
        help="Send notifications immediately when releasing suppressed",
    )

    args = parser.parse_args()
    result = None

    if args.action == "queue":
        if not args.user or not args.content:
            print("Error: --user and --content required for queue")
            sys.exit(1)
        notification_id = queue_notification(
            user_id=args.user,
            content=args.content,
            priority=args.priority,
            channel=args.channel,
            source=args.source,
        )
        result = {
            "success": True,
            "notification_id": notification_id,
            "message": f"Notification queued with ID {notification_id}",
        }

    elif args.action == "send":
        if not args.id:
            # If no ID but user/content provided, queue and send immediately
            if args.user and args.content:
                if args.flow_aware:
                    # Use flow-aware sending
                    result = asyncio.run(
                        send_with_flow_awareness(
                            user_id=args.user,
                            content=args.content,
                            priority=args.priority,
                            channel=args.channel,
                            source=args.source,
                        )
                    )
                else:
                    notification_id = queue_notification(
                        user_id=args.user,
                        content=args.content,
                        priority=args.priority,
                        channel=args.channel,
                        source=args.source,
                    )
                    result = asyncio.run(send_notification(notification_id))
            else:
                print("Error: --id or (--user and --content) required for send")
                sys.exit(1)
        else:
            result = asyncio.run(send_notification(args.id))

    elif args.action == "get":
        if not args.id:
            print("Error: --id required for get")
            sys.exit(1)
        notification = get_notification(args.id)
        result = (
            {"success": True, "notification": notification}
            if notification
            else {"success": False, "error": "Not found"}
        )

    elif args.action == "list":
        notifications = list_notifications(
            user_id=args.user, status=args.status, priority=args.priority, limit=args.limit
        )
        result = {"success": True, "notifications": notifications, "count": len(notifications)}

    elif args.action == "process":
        result = asyncio.run(process_pending())

    elif args.action == "stats":
        result = get_stats()

    elif args.action == "check-flow":
        if not args.user:
            print("Error: --user required for check-flow")
            sys.exit(1)
        result = should_suppress(args.user, args.priority)

    elif args.action == "suppressed-count":
        if not args.user:
            print("Error: --user required for suppressed-count")
            sys.exit(1)
        result = get_suppressed_count(args.user)

    elif args.action == "list-suppressed":
        if not args.user:
            print("Error: --user required for list-suppressed")
            sys.exit(1)
        result = list_suppressed(args.user, args.limit)

    elif args.action == "release-suppressed":
        if not args.user:
            print("Error: --user required for release-suppressed")
            sys.exit(1)
        result = release_suppressed(args.user, send_immediately=args.send_on_release)

    # Output
    if result.get("success"):
        print(f"OK {result.get('message', 'Success')}")
    else:
        print(f"ERROR {result.get('error')}")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
