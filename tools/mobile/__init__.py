"""Mobile Push Notifications — Web Push + PWA for DexAI

Philosophy:
    Mobile notifications for ADHD users should minimize unnecessary interruptions
    while ensuring truly important things get through. This is the opposite of
    typical engagement-maximizing notification systems.

Design Principles:
    1. Flow Protection — Don't interrupt hyperfocus for low-priority items
    2. Batching — Group related notifications to reduce interruption count
    3. Quiet Hours — Automatic DND with easy override for emergencies
    4. Granular Control — Per-category enable/disable
    5. Supportive Tone — No guilt language, forward-facing messages

Components:
    push/: Web Push delivery (VAPID, pywebpush)
    queue/: Notification queueing, batching, and scheduling
    preferences/: User notification preferences and category management
    analytics/: Delivery tracking and statistics

Database: data/mobile.db
    - push_subscriptions: Web Push endpoints
    - notification_queue: Priority queue for pending notifications
    - notification_delivery_log: Delivery tracking
    - notification_preferences: User settings
    - notification_categories: Category definitions
"""

import sqlite3
from pathlib import Path


# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "args"
DATA_PATH = PROJECT_ROOT / "data"
DB_PATH = DATA_PATH / "mobile.db"


def get_connection() -> sqlite3.Connection:
    """
    Get database connection, creating tables if needed.

    Returns:
        SQLite connection with row_factory set
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Push subscriptions (Web Push endpoints)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh_key TEXT NOT NULL,
            auth_key TEXT NOT NULL,
            device_name TEXT,
            device_type TEXT DEFAULT 'web',
            browser TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_used_at DATETIME,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)

    # Notification queue
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_queue (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            category TEXT NOT NULL,
            priority INTEGER DEFAULT 5,
            title TEXT NOT NULL,
            body TEXT,
            data TEXT,
            icon_url TEXT,
            action_url TEXT,
            scheduled_for DATETIME,
            expires_at DATETIME,
            batch_key TEXT,
            batch_window_seconds INTEGER DEFAULT 300,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            sent_at DATETIME,
            respect_flow_state BOOLEAN DEFAULT TRUE,
            min_priority_to_interrupt INTEGER DEFAULT 8
        )
    """)

    # Notification delivery log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_delivery_log (
            id TEXT PRIMARY KEY,
            notification_id TEXT NOT NULL,
            subscription_id TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            delivered_at DATETIME,
            clicked_at DATETIME,
            dismissed_at DATETIME,
            FOREIGN KEY (notification_id) REFERENCES notification_queue(id),
            FOREIGN KEY (subscription_id) REFERENCES push_subscriptions(id)
        )
    """)

    # User notification preferences
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_preferences (
            user_id TEXT PRIMARY KEY,
            enabled BOOLEAN DEFAULT TRUE,
            quiet_hours_start TEXT,
            quiet_hours_end TEXT,
            timezone TEXT DEFAULT 'UTC',
            category_settings TEXT,
            respect_flow_state BOOLEAN DEFAULT TRUE,
            flow_interrupt_threshold INTEGER DEFAULT 8,
            batch_notifications BOOLEAN DEFAULT TRUE,
            batch_window_minutes INTEGER DEFAULT 5,
            max_notifications_per_hour INTEGER DEFAULT 6,
            cooldown_after_burst_minutes INTEGER DEFAULT 30,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Notification categories
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            default_priority INTEGER DEFAULT 5,
            default_icon TEXT,
            color TEXT,
            can_batch BOOLEAN DEFAULT TRUE,
            can_suppress BOOLEAN DEFAULT TRUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes for efficient queries
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_queue_user_status "
        "ON notification_queue(user_id, status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_queue_scheduled "
        "ON notification_queue(scheduled_for) WHERE status = 'pending'"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_queue_batch "
        "ON notification_queue(user_id, batch_key, status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_subscriptions_user "
        "ON push_subscriptions(user_id, is_active)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_delivery_notification "
        "ON notification_delivery_log(notification_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_delivery_subscription "
        "ON notification_delivery_log(subscription_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_delivery_status "
        "ON notification_delivery_log(status, sent_at)"
    )

    conn.commit()
    return conn


def ensure_default_categories() -> None:
    """Ensure default notification categories exist."""
    from tools.mobile.preferences.category_manager import seed_default_categories
    seed_default_categories()
