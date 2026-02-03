"""Office Integration — Email and Calendar for Microsoft 365 and Google Workspace

Philosophy:
    Office integration should match the user's trust level. ADHD users benefit
    from automation but need appropriate safeguards. The 5-level integration
    model allows progressive capability unlocking as trust builds.

Integration Levels:
    1. Sandboxed: Dex has its own email/calendar, user forwards content
    2. Read-Only: Dex can read user's inbox/calendar, suggests actions
    3. Collaborative: Dex creates drafts, schedules meetings as user
    4. Managed Proxy: Dex sends with undo window, full audit trail
    5. Autonomous: Policy-based automation, continuous background processing

Design Principles:
    1. Progressive Trust — Start low, unlock higher levels over time
    2. Extended Undo — 60-second windows for impulsivity protection
    3. Audit Everything — Full trail for accountability and debugging
    4. Emergency Escape — One-click pause for when overwhelmed

Components:
    models.py: Data models (Email, CalendarEvent, OfficeAccount)
    oauth_manager.py: OAuth flows for Google and Microsoft
    level_detector.py: Determine current integration level
    onboarding.py: Integration level selection wizard
    providers/: Platform-specific implementations
    email/: Email operations (read, summarize, draft, send)
    calendar/: Calendar operations (read, schedule)
    actions/: Action queue and undo management (Level 4+)
    policies/: Policy engine for autonomous actions (Level 5)
"""

import sqlite3
from pathlib import Path


# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "args"
DATA_PATH = PROJECT_ROOT / "data"
DB_PATH = DATA_PATH / "office.db"


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

    # Office accounts (linked OAuth connections)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_accounts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            integration_level INTEGER DEFAULT 1,
            email_address TEXT,
            access_token_encrypted TEXT,
            refresh_token_encrypted TEXT,
            token_expiry DATETIME,
            scopes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Cached emails
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_email_cache (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            thread_id TEXT,
            subject TEXT,
            sender TEXT,
            recipients TEXT,
            snippet TEXT,
            received_at DATETIME,
            labels TEXT,
            is_read BOOLEAN DEFAULT FALSE,
            is_starred BOOLEAN DEFAULT FALSE,
            cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id)
        )
    """)

    # Cached calendar events
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_calendar_cache (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            calendar_id TEXT,
            title TEXT,
            description TEXT,
            location TEXT,
            start_time DATETIME,
            end_time DATETIME,
            all_day BOOLEAN DEFAULT FALSE,
            recurrence TEXT,
            attendees TEXT,
            status TEXT,
            cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id)
        )
    """)

    # Action queue (Level 4+)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_actions (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action_data TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            undo_deadline DATETIME,
            executed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id)
        )
    """)

    # Audit log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_audit_log (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action_summary TEXT,
            action_data TEXT,
            result TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id)
        )
    """)

    # Policies (Level 5)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_policies (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            name TEXT NOT NULL,
            policy_type TEXT NOT NULL,
            conditions TEXT NOT NULL,
            actions TEXT NOT NULL,
            enabled BOOLEAN DEFAULT TRUE,
            priority INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id)
        )
    """)

    # Indexes
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_account_date "
        "ON office_email_cache(account_id, received_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_calendar_account_date "
        "ON office_calendar_cache(account_id, start_time)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_actions_status "
        "ON office_actions(status, undo_deadline)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_account_date "
        "ON office_audit_log(account_id, created_at)"
    )

    conn.commit()
    return conn
