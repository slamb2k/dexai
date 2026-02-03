"""Office Actions — Action Queue and Undo Management for Level 4+ Integration

This module provides the action queue system for Managed Proxy (Level 4) integration.
Actions are queued with undo windows, allowing users to cancel before execution.

Philosophy:
    ADHD users may act impulsively. The action queue provides a buffer between
    intention and execution, allowing time for reconsideration. All actions are
    logged for full accountability and undo capability.

Components:
    queue.py: Action queue management (queue, cancel, expedite)
    executor.py: Action execution engine (runs after undo window)
    validator.py: Pre-queue validation (permissions, rate limits, safety)
    undo.py: Undo implementation for each action type
    audit_logger.py: Permanent, immutable log of all actions
    digest.py: Daily summary generation (ADHD-friendly format)

Action Types:
    Email: send_email, delete_email, archive_email, mark_read
    Calendar: schedule_meeting, cancel_meeting, accept_meeting, decline_meeting

Action States:
    pending: Queued, awaiting undo window expiry
    executed: Action completed successfully
    undone: User cancelled before execution
    expired: Undo window passed, action failed to execute
    failed: Execution attempted but failed
"""

import sys
from enum import Enum
from pathlib import Path

# Add project root to path for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.office import DB_PATH, PROJECT_ROOT, get_connection


# Re-export path constants from parent
__all__ = [
    "PROJECT_ROOT",
    "DB_PATH",
    "ActionType",
    "ActionStatus",
    "Priority",
    "get_connection",
    "ensure_action_indexes",
]


class ActionType(str, Enum):
    """
    Valid action types for the office action queue.

    Matches VALID_ACTION_TYPES from models.py but limited to
    actions supported by the Managed Proxy level.
    """

    # Email actions
    SEND_EMAIL = "send_email"
    DELETE_EMAIL = "delete_email"
    ARCHIVE_EMAIL = "archive_email"
    MARK_READ = "mark_read"

    # Calendar actions
    SCHEDULE_MEETING = "schedule_meeting"
    CANCEL_MEETING = "cancel_meeting"
    ACCEPT_MEETING = "accept_meeting"
    DECLINE_MEETING = "decline_meeting"

    @classmethod
    def values(cls) -> set[str]:
        """Get all action type values as a set."""
        return {item.value for item in cls}

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a string is a valid action type."""
        return value in cls.values()

    @property
    def category(self) -> str:
        """Get the category (email or calendar) for this action."""
        if self.value in {"send_email", "delete_email", "archive_email", "mark_read"}:
            return "email"
        return "calendar"

    @property
    def is_destructive(self) -> bool:
        """Check if this action is destructive (harder to undo)."""
        return self.value in {"delete_email", "cancel_meeting"}

    @property
    def default_undo_seconds(self) -> int:
        """Get the default undo window for this action type."""
        if self.is_destructive:
            return 120
        return 60


class ActionStatus(str, Enum):
    """
    Status values for queued actions.
    """

    PENDING = "pending"
    EXECUTED = "executed"
    UNDONE = "undone"
    EXPIRED = "expired"
    FAILED = "failed"

    @classmethod
    def values(cls) -> set[str]:
        """Get all status values as a set."""
        return {item.value for item in cls}

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) status."""
        return self != ActionStatus.PENDING


class Priority(str, Enum):
    """
    Priority levels for queued actions.
    """

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

    @classmethod
    def values(cls) -> set[str]:
        """Get all priority values as a set."""
        return {item.value for item in cls}

    @property
    def sort_order(self) -> int:
        """Get numeric sort order (higher priority = lower number)."""
        orders = {"high": 0, "normal": 1, "low": 2}
        return orders.get(self.value, 1)


def ensure_action_indexes() -> None:
    """
    Create performance indexes for the action queue.

    These indexes optimize common queries:
    - Fetching pending actions for an account
    - Finding actions with expired undo deadlines
    - Audit log queries by action type and date

    Safe to call multiple times (uses IF NOT EXISTS).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Index for fetching pending actions by account
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_actions_account_status
        ON office_actions(account_id, status)
    """)

    # Index for finding actions with expired undo deadlines
    # Partial index on pending actions only
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_actions_deadline
        ON office_actions(undo_deadline)
        WHERE status = 'pending'
    """)

    # Index for audit log queries by action type and date
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_type_date
        ON office_audit_log(action_type, created_at)
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys

    print("Testing office actions module...")

    # Test ActionType
    assert ActionType.SEND_EMAIL.value == "send_email"
    assert ActionType.is_valid("send_email")
    assert not ActionType.is_valid("invalid_action")
    assert ActionType.DELETE_EMAIL.is_destructive
    assert not ActionType.SEND_EMAIL.is_destructive
    assert ActionType.SEND_EMAIL.category == "email"
    assert ActionType.SCHEDULE_MEETING.category == "calendar"
    assert len(ActionType.values()) == 8

    # Test ActionStatus
    assert ActionStatus.PENDING.value == "pending"
    assert not ActionStatus.PENDING.is_terminal
    assert ActionStatus.EXECUTED.is_terminal
    assert ActionStatus.FAILED.is_terminal
    assert len(ActionStatus.values()) == 5

    # Test Priority
    assert Priority.HIGH.sort_order < Priority.NORMAL.sort_order
    assert Priority.NORMAL.sort_order < Priority.LOW.sort_order
    assert len(Priority.values()) == 3

    # Test index creation (requires database)
    ensure_action_indexes()
    print("OK: Indexes created successfully")

    print("OK: All office actions tests passed")
    sys.exit(0)
