"""
Tool: Context Capture
Purpose: Auto-snapshot user context when switches occur for ADHD working memory support

This tool captures the user's current context when they switch tasks, become idle,
or manually request a snapshot. This enables "you were here..." resumption when
they return, reducing the 20-45 minute re-orientation cost typical of ADHD.

Usage:
    # Capture context on task switch
    python tools/memory/context_capture.py --action capture --user alice \\
        --trigger switch \\
        --active-file "/path/to/file.py" \\
        --last-action "Wrote the auth middleware" \\
        --next-step "Wire up the endpoints" \\
        --channel discord

    # List recent snapshots
    python tools/memory/context_capture.py --action list --user alice --limit 10

    # Get specific snapshot
    python tools/memory/context_capture.py --action get --id "snap_abc123"

    # Cleanup old snapshots
    python tools/memory/context_capture.py --action cleanup --older-than "7d"

Dependencies:
    - sqlite3 (stdlib)
    - json (stdlib)
    - yaml (pyyaml)

Output:
    JSON result with success status and data
"""

import argparse
import json
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from tools.agent.constants import OWNER_USER_ID

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "context.db"
CONFIG_PATH = PROJECT_ROOT / "args" / "working_memory.yaml"

# Valid trigger types
VALID_TRIGGERS = ["switch", "timeout", "manual"]


def load_config() -> dict[str, Any]:
    """Load working memory configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Context snapshots table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS context_snapshots (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            captured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            trigger TEXT CHECK(trigger IN ('switch', 'timeout', 'manual')),
            state TEXT,
            summary TEXT,
            expires_at DATETIME
        )
    """)

    # Indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_user ON context_snapshots(user_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_captured ON context_snapshots(captured_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_user_captured ON context_snapshots(user_id, captured_at DESC)"
    )

    conn.commit()
    return conn


def row_to_dict(row) -> dict | None:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    d = dict(row)
    # Parse JSON state if present
    if d.get("state"):
        try:
            d["state"] = json.loads(d["state"])
        except json.JSONDecodeError:
            pass
    return d


def generate_snapshot_id(user_id: str) -> str:
    """Generate a unique snapshot ID."""
    timestamp = int(datetime.now().timestamp())
    short_uuid = uuid.uuid4().hex[:8]
    return f"snap_{timestamp}_{user_id}_{short_uuid}"


def parse_duration(duration_str: str) -> timedelta | None:
    """Parse duration string like '24h', '7d', '30m' into timedelta."""
    match = re.match(r"^(\d+)([mhdw])$", duration_str.lower())
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        return timedelta(minutes=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    elif unit == "w":
        return timedelta(weeks=value)

    return None


def capture_context(
    trigger: str,
    active_file: str | None = None,
    last_action: str | None = None,
    next_step: str | None = None,
    channel: str | None = None,
    metadata: dict | None = None,
    summary: str | None = None,
    ttl_hours: int | None = None,
    user_id: str = OWNER_USER_ID,
) -> dict[str, Any]:
    """
    Capture a context snapshot.

    Args:
        trigger: What triggered the capture ('switch', 'timeout', 'manual')
        active_file: Path to the file user was working on
        last_action: Description of what user just did
        next_step: What user was about to do
        channel: Channel where activity occurred
        metadata: Additional context data
        summary: Optional human-readable summary
        ttl_hours: Hours until snapshot expires (None = never)

    Returns:
        dict with success status and snapshot data
    """
    if trigger not in VALID_TRIGGERS:
        return {"success": False, "error": f"Invalid trigger. Must be one of: {VALID_TRIGGERS}"}

    if not user_id:
        return {"success": False, "error": "user_id is required"}

    # Build state object
    state = {
        "active_file": active_file,
        "last_action": last_action,
        "next_step": next_step,
        "channel": channel,
        "metadata": metadata or {},
    }

    # Remove None values from state
    state = {k: v for k, v in state.items() if v is not None}

    # Calculate expiration
    expires_at = None
    if ttl_hours:
        expires_at = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
    else:
        # Use config default
        config = load_config()
        retention_days = (
            config.get("working_memory", {}).get("cleanup", {}).get("snapshot_retention_days", 7)
        )
        if retention_days:
            expires_at = (datetime.now() + timedelta(days=retention_days)).isoformat()

    snapshot_id = generate_snapshot_id(user_id)
    captured_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO context_snapshots
        (id, user_id, captured_at, trigger, state, summary, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (snapshot_id, user_id, captured_at, trigger, json.dumps(state), summary, expires_at),
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Context captured for user {user_id}",
        "data": {
            "id": snapshot_id,
            "user_id": user_id,
            "captured_at": captured_at,
            "trigger": trigger,
            "state": state,
            "summary": summary,
            "expires_at": expires_at,
        },
    }


def list_snapshots(
    limit: int = 10,
    offset: int = 0,
    trigger: str | None = None,
    include_expired: bool = False,
    user_id: str = OWNER_USER_ID,
) -> dict[str, Any]:
    """
    List context snapshots for a user.

    Args:
        limit: Maximum results to return
        offset: Pagination offset
        trigger: Filter by trigger type
        include_expired: Include expired snapshots

    Returns:
        dict with list of snapshots
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = ["user_id = ?"]
    params: list[Any] = [user_id]

    if trigger:
        if trigger not in VALID_TRIGGERS:
            conn.close()
            return {"success": False, "error": f"Invalid trigger. Must be one of: {VALID_TRIGGERS}"}
        conditions.append("trigger = ?")
        params.append(trigger)

    if not include_expired:
        conditions.append("(expires_at IS NULL OR expires_at > ?)")
        params.append(datetime.now().isoformat())

    where_clause = " AND ".join(conditions)

    cursor.execute(
        f"""
        SELECT * FROM context_snapshots
        WHERE {where_clause}
        ORDER BY captured_at DESC
        LIMIT ? OFFSET ?
    """,
        params + [limit, offset],
    )

    snapshots = [row_to_dict(row) for row in cursor.fetchall()]

    # Get total count
    cursor.execute(f"SELECT COUNT(*) as count FROM context_snapshots WHERE {where_clause}", params)
    total = cursor.fetchone()["count"]

    conn.close()

    return {
        "success": True,
        "data": {"snapshots": snapshots, "total": total, "limit": limit, "offset": offset},
    }


def get_snapshot(snapshot_id: str) -> dict[str, Any]:
    """
    Get a specific context snapshot.

    Args:
        snapshot_id: Snapshot identifier

    Returns:
        dict with snapshot data
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM context_snapshots WHERE id = ?", (snapshot_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": f"Snapshot not found: {snapshot_id}"}

    snapshot = row_to_dict(row)

    # Check if expired
    if snapshot.get("expires_at"):
        if datetime.fromisoformat(snapshot["expires_at"]) < datetime.now():
            snapshot["is_expired"] = True

    return {"success": True, "data": snapshot}


def get_latest_snapshot(user_id: str = OWNER_USER_ID) -> dict[str, Any]:
    """
    Get the most recent context snapshot for a user.

    Args:
        user_id: User identifier

    Returns:
        dict with snapshot data or message if none found
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM context_snapshots
        WHERE user_id = ?
          AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY captured_at DESC
        LIMIT 1
    """,
        (user_id, datetime.now().isoformat()),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "success": True,
            "data": None,
            "message": f"No context snapshots found for user {user_id}",
        }

    snapshot = row_to_dict(row)

    # Calculate age
    captured_at = datetime.fromisoformat(snapshot["captured_at"])
    age = datetime.now() - captured_at
    snapshot["age_minutes"] = int(age.total_seconds() / 60)
    snapshot["age_hours"] = round(age.total_seconds() / 3600, 1)

    return {"success": True, "data": snapshot}


def cleanup_snapshots(
    older_than: str | None = None, user_id: str | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """
    Clean up old or expired context snapshots.

    Args:
        older_than: Duration string (e.g., '7d', '24h')
        user_id: Only cleanup for specific user
        dry_run: If True, just count without deleting

    Returns:
        dict with deletion count
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params: list[Any] = []

    # Delete expired snapshots
    conditions.append("(expires_at IS NOT NULL AND expires_at < ?)")
    params.append(datetime.now().isoformat())

    # Or delete older than specified duration
    if older_than:
        duration = parse_duration(older_than)
        if not duration:
            conn.close()
            return {
                "success": False,
                "error": f"Invalid duration format: {older_than}. Use format like '7d', '24h', '30m'",
            }
        cutoff = (datetime.now() - duration).isoformat()
        conditions.append("captured_at < ?")
        params.append(cutoff)

    if user_id:
        # This applies to all conditions
        pass  # Will add below

    # Build query - delete if expired OR older than cutoff
    where_clause = " OR ".join(conditions)
    if user_id:
        where_clause = f"user_id = ? AND ({where_clause})"
        params.insert(0, user_id)

    # Count first
    cursor.execute(f"SELECT COUNT(*) as count FROM context_snapshots WHERE {where_clause}", params)
    count = cursor.fetchone()["count"]

    if dry_run:
        conn.close()
        return {
            "success": True,
            "message": f"Would delete {count} snapshots",
            "count": count,
            "dry_run": True,
        }

    # Delete
    cursor.execute(f"DELETE FROM context_snapshots WHERE {where_clause}", params)
    conn.commit()
    conn.close()

    return {"success": True, "message": f"Deleted {count} snapshots", "count": count}


def delete_snapshot(snapshot_id: str) -> dict[str, Any]:
    """
    Delete a specific snapshot.

    Args:
        snapshot_id: Snapshot identifier

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM context_snapshots WHERE id = ?", (snapshot_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted == 0:
        return {"success": False, "error": f"Snapshot not found: {snapshot_id}"}

    return {"success": True, "message": f"Deleted snapshot {snapshot_id}"}


def get_stats(user_id: str | None = None) -> dict[str, Any]:
    """Get context capture statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    base_condition = "user_id = ?" if user_id else "1=1"
    params = [user_id] if user_id else []

    # Total snapshots
    cursor.execute(
        f"SELECT COUNT(*) as total FROM context_snapshots WHERE {base_condition}", params
    )
    total = cursor.fetchone()["total"]

    # By trigger
    cursor.execute(
        f"""
        SELECT trigger, COUNT(*) as count
        FROM context_snapshots
        WHERE {base_condition}
        GROUP BY trigger
    """,
        params,
    )
    by_trigger = {row["trigger"]: row["count"] for row in cursor.fetchall()}

    # Last 24 hours
    yesterday = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute(
        f"""
        SELECT COUNT(*) as count
        FROM context_snapshots
        WHERE {base_condition} AND captured_at >= ?
    """,
        params + [yesterday],
    )
    last_24h = cursor.fetchone()["count"]

    # Expired count
    cursor.execute(
        f"""
        SELECT COUNT(*) as count
        FROM context_snapshots
        WHERE {base_condition} AND expires_at IS NOT NULL AND expires_at < ?
    """,
        params + [datetime.now().isoformat()],
    )
    expired = cursor.fetchone()["count"]

    conn.close()

    return {
        "success": True,
        "stats": {
            "total_snapshots": total,
            "snapshots_24h": last_24h,
            "expired_snapshots": expired,
            "by_trigger": by_trigger,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Context Capture - Auto-snapshot user context for ADHD working memory support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Capture context on task switch
    %(prog)s --action capture --user alice --trigger switch \\
        --active-file "/path/to/file.py" \\
        --last-action "Wrote the auth middleware" \\
        --next-step "Wire up the endpoints"

    # List recent snapshots
    %(prog)s --action list --user alice --limit 10

    # Get specific snapshot
    %(prog)s --action get --id "snap_abc123"

    # Cleanup old snapshots
    %(prog)s --action cleanup --older-than "7d"
        """,
    )

    parser.add_argument(
        "--action",
        required=True,
        choices=["capture", "list", "get", "latest", "cleanup", "delete", "stats"],
        help="Action to perform",
    )

    # Capture action args
    parser.add_argument("--user", help="User ID")
    parser.add_argument("--trigger", choices=VALID_TRIGGERS, help="What triggered the capture")
    parser.add_argument("--active-file", help="Path to file user was working on")
    parser.add_argument("--last-action", help="What user just did")
    parser.add_argument("--next-step", help="What user was about to do")
    parser.add_argument("--channel", help="Channel where activity occurred")
    parser.add_argument("--metadata", help="Additional JSON metadata")
    parser.add_argument("--summary", help="Human-readable summary")
    parser.add_argument("--ttl-hours", type=int, help="Hours until snapshot expires")

    # List/query args
    parser.add_argument("--limit", type=int, default=10, help="Max results")
    parser.add_argument("--offset", type=int, default=0, help="Pagination offset")
    parser.add_argument(
        "--include-expired", action="store_true", help="Include expired snapshots in results"
    )

    # Get/delete args
    parser.add_argument("--id", help="Snapshot ID")

    # Cleanup args
    parser.add_argument("--older-than", help='Delete snapshots older than (e.g., "7d", "24h")')
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be deleted without deleting"
    )

    args = parser.parse_args()
    result = None

    if args.action == "capture":
        if not args.user:
            print("Error: --user required for capture")
            sys.exit(1)
        if not args.trigger:
            print("Error: --trigger required for capture")
            sys.exit(1)

        metadata = None
        if args.metadata:
            try:
                metadata = json.loads(args.metadata)
            except json.JSONDecodeError:
                print("Error: --metadata must be valid JSON")
                sys.exit(1)

        result = capture_context(
            user_id=args.user,
            trigger=args.trigger,
            active_file=args.active_file,
            last_action=args.last_action,
            next_step=args.next_step,
            channel=args.channel,
            metadata=metadata,
            summary=args.summary,
            ttl_hours=args.ttl_hours,
        )

    elif args.action == "list":
        if not args.user:
            print("Error: --user required for list")
            sys.exit(1)

        result = list_snapshots(
            user_id=args.user,
            limit=args.limit,
            offset=args.offset,
            trigger=args.trigger,
            include_expired=args.include_expired,
        )

    elif args.action == "get":
        if not args.id:
            print("Error: --id required for get")
            sys.exit(1)

        result = get_snapshot(args.id)

    elif args.action == "latest":
        if not args.user:
            print("Error: --user required for latest")
            sys.exit(1)

        result = get_latest_snapshot(args.user)

    elif args.action == "cleanup":
        result = cleanup_snapshots(
            older_than=args.older_than, user_id=args.user, dry_run=args.dry_run
        )

    elif args.action == "delete":
        if not args.id:
            print("Error: --id required for delete")
            sys.exit(1)

        result = delete_snapshot(args.id)

    elif args.action == "stats":
        result = get_stats(user_id=args.user)

    if result:
        if result.get("success"):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
