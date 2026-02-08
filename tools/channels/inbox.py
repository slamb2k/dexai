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
    ChannelUser,
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

    # Channel users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_users (
            id TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            channel_user_id TEXT NOT NULL,
            display_name TEXT,
            username TEXT,
            is_paired INTEGER DEFAULT 0,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT,
            UNIQUE(channel, channel_user_id)
        )
    """)

    # User preferences table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT PRIMARY KEY,
            preferred_channel TEXT,
            fallback_channel TEXT,
            dnd_start TEXT,
            dnd_end TEXT,
            metadata TEXT
        )
    """)

    # Cross-channel identity linking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS identity_links (
            user_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            channel_user_id TEXT NOT NULL,
            linked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, channel)
        )
    """)

    # Pairing codes table (for cross-channel linking)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pairing_codes (
            code TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            channel_user_id TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            used INTEGER DEFAULT 0
        )
    """)

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
# User Operations
# =============================================================================


def get_user_by_channel(channel: str, channel_user_id: str) -> ChannelUser | None:
    """
    Get user by their channel-specific ID.

    Args:
        channel: Channel name (telegram, discord, etc.)
        channel_user_id: Platform-specific user ID

    Returns:
        ChannelUser or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM channel_users
        WHERE channel = ? AND channel_user_id = ?
    """,
        (channel, channel_user_id),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return _row_to_user(row)


def get_user_by_id(user_id: str) -> ChannelUser | None:
    """
    Get user by internal user ID.

    Args:
        user_id: Internal user ID

    Returns:
        ChannelUser or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM channel_users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return _row_to_user(row)


def create_or_update_user(user: ChannelUser) -> dict[str, Any]:
    """
    Create or update a channel user.

    Args:
        user: ChannelUser to create/update

    Returns:
        {"success": True, "user_id": str} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        metadata_json = json.dumps(user.metadata) if user.metadata else None

        cursor.execute(
            """
            INSERT OR REPLACE INTO channel_users
            (id, channel, channel_user_id, display_name, username, is_paired, first_seen, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                user.id,
                user.channel,
                user.channel_user_id,
                user.display_name,
                user.username,
                1 if user.is_paired else 0,
                user.first_seen.isoformat(),
                metadata_json,
            ),
        )

        conn.commit()
        return {"success": True, "user_id": user.id}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def update_user_paired_status(user_id: str, is_paired: bool) -> dict[str, Any]:
    """
    Update a user's pairing status.

    Args:
        user_id: Internal user ID
        is_paired: New pairing status

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE channel_users SET is_paired = ? WHERE id = ?
        """,
            (1 if is_paired else 0, user_id),
        )

        conn.commit()
        return {"success": True, "updated": cursor.rowcount}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def _row_to_user(row: sqlite3.Row) -> ChannelUser:
    """Convert database row to ChannelUser."""
    metadata = {}
    if row["metadata"]:
        metadata = json.loads(row["metadata"])

    first_seen = row["first_seen"]
    if isinstance(first_seen, str):
        first_seen = datetime.fromisoformat(first_seen)

    return ChannelUser(
        id=row["id"],
        channel=row["channel"],
        channel_user_id=row["channel_user_id"],
        display_name=row["display_name"] or "",
        username=row["username"],
        is_paired=bool(row["is_paired"]),
        first_seen=first_seen,
        metadata=metadata,
    )


# =============================================================================
# Identity Linking
# =============================================================================


def link_identity(user_id: str, channel: str, channel_user_id: str) -> dict[str, Any]:
    """
    Link a channel identity to a user.

    Args:
        user_id: Internal user ID
        channel: Channel name
        channel_user_id: Platform-specific user ID

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT OR REPLACE INTO identity_links
            (user_id, channel, channel_user_id, linked_at)
            VALUES (?, ?, ?, ?)
        """,
            (user_id, channel, channel_user_id, datetime.now().isoformat()),
        )

        # Also update the channel_users table if the user exists there
        cursor.execute(
            """
            UPDATE channel_users
            SET id = ?, is_paired = 1
            WHERE channel = ? AND channel_user_id = ?
        """,
            (user_id, channel, channel_user_id),
        )

        conn.commit()
        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_linked_channels(user_id: str) -> list[dict[str, str]]:
    """
    Get all channels linked to a user.

    Args:
        user_id: Internal user ID

    Returns:
        List of {"channel": str, "channel_user_id": str, "linked_at": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT channel, channel_user_id, linked_at
        FROM identity_links
        WHERE user_id = ?
        ORDER BY linked_at
    """,
        (user_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "channel": row["channel"],
            "channel_user_id": row["channel_user_id"],
            "linked_at": row["linked_at"],
        }
        for row in rows
    ]


def get_user_by_linked_channel(channel: str, channel_user_id: str) -> str | None:
    """
    Get internal user ID from a linked channel identity.

    Args:
        channel: Channel name
        channel_user_id: Platform-specific user ID

    Returns:
        Internal user ID or None if not linked
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT user_id FROM identity_links
        WHERE channel = ? AND channel_user_id = ?
    """,
        (channel, channel_user_id),
    )

    row = cursor.fetchone()
    conn.close()

    return row["user_id"] if row else None


# =============================================================================
# Pairing Codes
# =============================================================================


def create_pairing_code(
    user_id: str, channel: str, channel_user_id: str, code: str, ttl_seconds: int = 600
) -> dict[str, Any]:
    """
    Create a pairing code for cross-channel identity linking.

    Args:
        user_id: Internal user ID
        channel: Channel where code was generated
        channel_user_id: Platform-specific user ID
        code: The pairing code
        ttl_seconds: Time to live in seconds

    Returns:
        {"success": True, "code": str, "expires_at": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    from datetime import timedelta

    expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

    try:
        cursor.execute(
            """
            INSERT INTO pairing_codes
            (code, user_id, channel, channel_user_id, created_at, expires_at, used)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
            (
                code,
                user_id,
                channel,
                channel_user_id,
                datetime.now().isoformat(),
                expires_at.isoformat(),
            ),
        )

        conn.commit()
        return {"success": True, "code": code, "expires_at": expires_at.isoformat()}

    except sqlite3.IntegrityError:
        return {"success": False, "error": "code_already_exists"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def validate_pairing_code(code: str) -> dict[str, Any]:
    """
    Validate a pairing code and return its data.

    Args:
        code: The pairing code to validate

    Returns:
        {"success": True, "user_id": str, "channel": str, ...} or
        {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM pairing_codes WHERE code = ?
    """,
        (code,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": "code_not_found"}

    if row["used"]:
        return {"success": False, "error": "code_already_used"}

    expires_at = datetime.fromisoformat(row["expires_at"])
    now = datetime.now()
    if now > expires_at:
        logger.warning(f"[PAIRING] Code '{code}' expired. Now: {now.isoformat()}, Expires: {expires_at.isoformat()}, Diff: {(now - expires_at).total_seconds()}s")
        return {"success": False, "error": "code_expired"}

    return {
        "success": True,
        "user_id": row["user_id"],
        "channel": row["channel"],
        "channel_user_id": row["channel_user_id"],
    }


def consume_pairing_code(code: str) -> dict[str, Any]:
    """
    Mark a pairing code as used.

    Args:
        code: The pairing code to consume

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    # First validate
    validation = validate_pairing_code(code)
    if not validation["success"]:
        return validation

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE pairing_codes SET used = 1 WHERE code = ?
        """,
            (code,),
        )

        conn.commit()
        return {"success": True, **validation}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


# =============================================================================
# User Preferences
# =============================================================================


def set_preference(user_id: str, key: str, value: Any) -> dict[str, Any]:
    """
    Set a user preference.

    Valid keys: preferred_channel, fallback_channel, dnd_start, dnd_end

    Args:
        user_id: Internal user ID
        key: Preference key
        value: Preference value

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    valid_keys = {"preferred_channel", "fallback_channel", "dnd_start", "dnd_end"}
    if key not in valid_keys:
        return {"success": False, "error": f"invalid_key: {key}"}

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Ensure user preferences row exists
        cursor.execute(
            """
            INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)
        """,
            (user_id,),
        )

        # Update the specific preference
        cursor.execute(
            f"""
            UPDATE user_preferences SET {key} = ? WHERE user_id = ?
        """,
            (value, user_id),
        )

        conn.commit()
        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_preference(user_id: str, key: str) -> Any | None:
    """
    Get a user preference.

    Args:
        user_id: Internal user ID
        key: Preference key

    Returns:
        Preference value or None if not set
    """
    valid_keys = {"preferred_channel", "fallback_channel", "dnd_start", "dnd_end", "metadata"}
    if key not in valid_keys:
        return None

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        SELECT {key} FROM user_preferences WHERE user_id = ?
    """,
        (user_id,),
    )

    row = cursor.fetchone()
    conn.close()

    return row[key] if row else None


def get_preferred_channel(user_id: str) -> str | None:
    """
    Get user's preferred channel for notifications.

    Args:
        user_id: Internal user ID

    Returns:
        Channel name or None if not set
    """
    return get_preference(user_id, "preferred_channel")


def get_all_preferences(user_id: str) -> dict[str, Any]:
    """
    Get all preferences for a user.

    Args:
        user_id: Internal user ID

    Returns:
        Dict of all preferences
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {}

    return {
        "preferred_channel": row["preferred_channel"],
        "fallback_channel": row["fallback_channel"],
        "dnd_start": row["dnd_start"],
        "dnd_end": row["dnd_end"],
        "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
    }


# =============================================================================
# Status & Maintenance
# =============================================================================


def get_status() -> dict[str, Any]:
    """
    Get inbox status and statistics.

    Returns:
        Dict with message counts, user counts, etc.
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

    # User counts
    cursor.execute("SELECT COUNT(*) as total FROM channel_users")
    total_users = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as paired FROM channel_users WHERE is_paired = 1")
    paired_users = cursor.fetchone()["paired"]

    # Identity links
    cursor.execute("SELECT COUNT(*) as total FROM identity_links")
    total_links = cursor.fetchone()["total"]

    conn.close()

    return {
        "database": str(DB_PATH),
        "messages": {
            "total": total_messages,
            "by_channel": messages_by_channel,
            "by_direction": messages_by_direction,
        },
        "users": {
            "total": total_users,
            "paired": paired_users,
            "unpaired": total_users - paired_users,
        },
        "identity_links": total_links,
    }


def cleanup_expired_pairing_codes() -> dict[str, Any]:
    """
    Remove expired pairing codes.

    Returns:
        {"success": True, "deleted": int}
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM pairing_codes
        WHERE expires_at < ? OR used = 1
    """,
        (datetime.now().isoformat(),),
    )

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return {"success": True, "deleted": deleted}


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
            "get-user",
            "create-user",
            "link",
            "get-links",
            "preference",
            "status",
            "cleanup",
        ],
    )
    parser.add_argument("--message", help="JSON message for store action")
    parser.add_argument("--message-id", help="Message ID for get action")
    parser.add_argument("--user-id", help="Internal user ID")
    parser.add_argument("--channel", help="Channel name")
    parser.add_argument("--channel-user-id", help="Platform-specific user ID")
    parser.add_argument("--limit", type=int, default=50, help="Limit for history")
    parser.add_argument("--key", help="Preference key")
    parser.add_argument("--value", help="Preference value")
    parser.add_argument("--display-name", help="User display name")
    parser.add_argument("--username", help="Platform username")

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
            if not args.user_id:
                print("ERROR: --user-id required for history action")
                sys.exit(1)
            messages = get_conversation_history(args.user_id, args.limit, channel=args.channel)
            result = {"messages": [m.to_dict() for m in messages], "count": len(messages)}

        elif args.action == "get-user":
            if not args.channel or not args.channel_user_id:
                print("ERROR: --channel and --channel-user-id required for get-user action")
                sys.exit(1)
            user = get_user_by_channel(args.channel, args.channel_user_id)
            result = user.to_dict() if user else {"error": "not_found"}

        elif args.action == "create-user":
            if not args.channel or not args.channel_user_id:
                print("ERROR: --channel and --channel-user-id required for create-user action")
                sys.exit(1)
            user = ChannelUser(
                id=ChannelUser.generate_id(),
                channel=args.channel,
                channel_user_id=args.channel_user_id,
                display_name=args.display_name or "Unknown",
                username=args.username,
            )
            result = create_or_update_user(user)

        elif args.action == "link":
            if not args.user_id or not args.channel or not args.channel_user_id:
                print("ERROR: --user-id, --channel, and --channel-user-id required for link action")
                sys.exit(1)
            result = link_identity(args.user_id, args.channel, args.channel_user_id)

        elif args.action == "get-links":
            if not args.user_id:
                print("ERROR: --user-id required for get-links action")
                sys.exit(1)
            links = get_linked_channels(args.user_id)
            result = {"links": links, "count": len(links)}

        elif args.action == "preference":
            if not args.user_id or not args.key:
                print("ERROR: --user-id and --key required for preference action")
                sys.exit(1)
            if args.value:
                result = set_preference(args.user_id, args.key, args.value)
            else:
                value = get_preference(args.user_id, args.key)
                result = {"key": args.key, "value": value}

        elif args.action == "status":
            result = get_status()

        elif args.action == "cleanup":
            result = cleanup_expired_pairing_codes()

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
