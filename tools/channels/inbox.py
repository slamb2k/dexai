"""
Tool: Unified Inbox
Purpose: Message storage, cross-channel identity, and user preferences

Usage:
    python tools/channels/inbox.py --action store --message '<json>'
    python tools/channels/inbox.py --action history --user-id alice --limit 20
    python tools/channels/inbox.py --action get-user --channel telegram --channel-user-id 12345
    python tools/channels/inbox.py --action link --user-id alice --channel discord --channel-user-id 67890
    python tools/channels/inbox.py --action preference --user-id alice --key preferred_channel --value telegram
    python tools/channels/inbox.py --action status

Database: data/inbox.db
"""

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.channels.models import (
    Attachment,
    UnifiedMessage,
)


# Database path
DB_PATH = PROJECT_ROOT / "data" / "inbox.db"


def get_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """Initialize database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # Messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            channel_message_id TEXT NOT NULL,
            session_id TEXT,
            user_id TEXT,
            channel_user_id TEXT NOT NULL,
            direction TEXT CHECK(direction IN ('inbound', 'outbound')),
            content TEXT,
            content_type TEXT DEFAULT 'text',
            attachments TEXT,
            reply_to TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT,
            UNIQUE(channel, channel_message_id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_channel_user ON messages(channel, channel_user_id)"
    )

    # NOTE: channel_users, identity_links, pairing_codes tables removed
    # in single-tenant simplification. See migration script for cleanup.

    conn.commit()
    conn.close()


# Initialize database on import
init_database()


# =============================================================================
# Message Operations
# =============================================================================


def store_message(message: UnifiedMessage) -> dict[str, Any]:
    """
    Store a message in the inbox.

    Args:
        message: UnifiedMessage to store

    Returns:
        {"success": True, "message_id": str} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        attachments_json = (
            json.dumps([a.to_dict() if hasattr(a, "to_dict") else a for a in message.attachments])
            if message.attachments
            else None
        )

        metadata_json = json.dumps(message.metadata) if message.metadata else None

        cursor.execute(
            """
            INSERT OR REPLACE INTO messages
            (id, channel, channel_message_id, session_id, user_id, channel_user_id,
             direction, content, content_type, attachments, reply_to, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                message.id,
                message.channel,
                message.channel_message_id,
                message.session_id,
                message.user_id,
                message.channel_user_id,
                message.direction,
                message.content,
                message.content_type,
                attachments_json,
                message.reply_to,
                message.timestamp.isoformat(),
                metadata_json,
            ),
        )

        conn.commit()
        return {"success": True, "message_id": message.id}

    except sqlite3.IntegrityError as e:
        return {"success": False, "error": f"integrity_error: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_message(message_id: str) -> UnifiedMessage | None:
    """
    Retrieve a message by ID.

    Args:
        message_id: Message ID to retrieve

    Returns:
        UnifiedMessage or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return _row_to_message(row)


def get_conversation_history(
    user_id: str, limit: int = 50, offset: int = 0, channel: str | None = None
) -> list[UnifiedMessage]:
    """
    Get conversation history for a user.

    Args:
        user_id: User ID to get history for
        limit: Maximum messages to return
        offset: Offset for pagination
        channel: Optional channel filter

    Returns:
        List of UnifiedMessage objects, ordered by timestamp descending
    """
    conn = get_connection()
    cursor = conn.cursor()

    if channel:
        cursor.execute(
            """
            SELECT * FROM messages
            WHERE user_id = ? AND channel = ?
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """,
            (user_id, channel, limit, offset),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM messages
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """,
            (user_id, limit, offset),
        )

    rows = cursor.fetchall()
    conn.close()

    return [_row_to_message(row) for row in rows]


def get_channel_history(
    channel: str, channel_user_id: str, limit: int = 50
) -> list[UnifiedMessage]:
    """
    Get message history for a specific channel user.

    Args:
        channel: Channel name
        channel_user_id: Platform-specific user ID
        limit: Maximum messages to return

    Returns:
        List of UnifiedMessage objects
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM messages
        WHERE channel = ? AND channel_user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """,
        (channel, channel_user_id, limit),
    )

    rows = cursor.fetchall()
    conn.close()

    return [_row_to_message(row) for row in rows]


def _row_to_message(row: sqlite3.Row) -> UnifiedMessage:
    """Convert database row to UnifiedMessage."""
    attachments = []
    if row["attachments"]:
        attachments_data = json.loads(row["attachments"])
        attachments = [Attachment(**a) for a in attachments_data]

    metadata = {}
    if row["metadata"]:
        metadata = json.loads(row["metadata"])

    timestamp = row["timestamp"]
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)

    return UnifiedMessage(
        id=row["id"],
        channel=row["channel"],
        channel_message_id=row["channel_message_id"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        channel_user_id=row["channel_user_id"],
        direction=row["direction"],
        content=row["content"] or "",
        content_type=row["content_type"] or "text",
        attachments=attachments,
        reply_to=row["reply_to"],
        timestamp=timestamp,
        metadata=metadata,
    )




# =============================================================================
# Status & Maintenance
# =============================================================================


def get_status() -> dict[str, Any]:
    """
    Get inbox status and statistics.

    Returns:
        Dict with message counts by channel and direction.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Message counts
    cursor.execute("SELECT COUNT(*) as total FROM messages")
    total_messages = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT channel, COUNT(*) as count
        FROM messages
        GROUP BY channel
    """)
    messages_by_channel = {row["channel"]: row["count"] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT direction, COUNT(*) as count
        FROM messages
        GROUP BY direction
    """)
    messages_by_direction = {row["direction"]: row["count"] for row in cursor.fetchall()}

    conn.close()

    return {
        "database": str(DB_PATH),
        "messages": {
            "total": total_messages,
            "by_channel": messages_by_channel,
            "by_direction": messages_by_direction,
        },
    }


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Unified Inbox - Message Storage")
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "store",
            "get",
            "history",
            "channel-history",
            "status",
        ],
    )
    parser.add_argument("--message", help="JSON message for store action")
    parser.add_argument("--message-id", help="Message ID for get action")
    parser.add_argument("--user-id", help="User ID for history (default: owner)")
    parser.add_argument("--channel", help="Channel name")
    parser.add_argument("--channel-user-id", help="Platform-specific user ID")
    parser.add_argument("--limit", type=int, default=50, help="Limit for history")

    args = parser.parse_args()

    try:
        if args.action == "store":
            if not args.message:
                print("ERROR: --message required for store action")
                sys.exit(1)
            msg_data = json.loads(args.message)
            message = UnifiedMessage.from_dict(msg_data)
            result = store_message(message)

        elif args.action == "get":
            if not args.message_id:
                print("ERROR: --message-id required for get action")
                sys.exit(1)
            message = get_message(args.message_id)
            result = message.to_dict() if message else {"error": "not_found"}

        elif args.action == "history":
            user_id = args.user_id or "owner"
            messages = get_conversation_history(user_id, args.limit, channel=args.channel)
            result = {"messages": [m.to_dict() for m in messages], "count": len(messages)}

        elif args.action == "channel-history":
            if not args.channel or not args.channel_user_id:
                print("ERROR: --channel and --channel-user-id required for channel-history action")
                sys.exit(1)
            messages = get_channel_history(args.channel, args.channel_user_id, args.limit)
            result = {"messages": [m.to_dict() for m in messages], "count": len(messages)}

        elif args.action == "status":
            result = get_status()

        else:
            print(f"ERROR: Unknown action: {args.action}")
            sys.exit(1)

        print("OK" if result.get("success", True) else "ERROR")
        print(json.dumps(result, indent=2))

    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
