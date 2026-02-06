"""
Tool: Session Manager
Purpose: Track authenticated sessions with security controls

Features:
- 256-bit random session tokens
- Configurable TTL (default 24h, max 7d)
- Channel/device binding
- Activity tracking with idle timeout
- Force logout capability

Usage:
    python tools/security/session.py --action create --user alice --channel discord
    python tools/security/session.py --action validate --token "abc123..."
    python tools/security/session.py --action refresh --token "abc123..."
    python tools/security/session.py --action revoke --token "abc123..."
    python tools/security/session.py --action revoke-all --user alice
    python tools/security/session.py --action list --user alice
    python tools/security/session.py --action cleanup  # Remove expired sessions

Dependencies:
    - secrets (stdlib)
    - hashlib (stdlib)
    - sqlite3 (stdlib)

Security Notes:
    - Only token hash is stored, never raw token
    - Raw token returned only on creation
    - Validates both token and expiry on every check
"""

import argparse
import hashlib
import json
import secrets
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data" / "sessions.db"

# Default session settings (can be overridden by args/security.yaml)
DEFAULT_TTL_HOURS = 24
MAX_TTL_HOURS = 168  # 7 days
IDLE_TIMEOUT_HOURS = 4
TOKEN_BYTES = 32  # 256 bits


def get_connection():
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            channel TEXT,
            device_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL,
            last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            metadata TEXT
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")

    conn.commit()
    return conn


def generate_token() -> str:
    """Generate a secure random session token."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Hash a token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def log_session_event(action: str, user_id: str, status: str, session_id: str | None = None):
    """Log session event to audit log."""
    try:
        from . import audit

        audit.log_event(
            event_type="auth",
            action=f"session_{action}",
            user_id=user_id,
            session_id=session_id,
            status=status,
        )
    except Exception:
        pass

    # Also log to dashboard audit for UI visibility
    try:
        from tools.dashboard.backend.database import log_audit

        event_type = f"auth.{action}"
        severity = "info" if status == "success" else "warning"

        log_audit(
            event_type=event_type,
            severity=severity,
            actor=user_id,
            target=f"session:{session_id}" if session_id else None,
            details={"status": status, "action": action},
        )
    except Exception:
        pass


def create_session(
    user_id: str,
    channel: str | None = None,
    device_id: str | None = None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """
    Create a new session.

    Args:
        user_id: User identifier
        channel: Channel (discord, api, cli)
        device_id: Device identifier for binding
        ttl_hours: Session lifetime in hours
        metadata: Additional session metadata

    Returns:
        dict with session info and RAW TOKEN (only time it's returned)
    """
    # Enforce max TTL
    ttl_hours = min(ttl_hours, MAX_TTL_HOURS)

    # Generate token
    token = generate_token()
    token_hash = hash_token(token)

    # Calculate expiry
    expires_at = datetime.now() + timedelta(hours=ttl_hours)

    conn = get_connection()
    cursor = conn.cursor()

    # Check concurrent session limit (default 5)
    cursor.execute(
        "SELECT COUNT(*) as count FROM sessions WHERE user_id = ? AND is_active = 1", (user_id,)
    )
    active_count = cursor.fetchone()["count"]

    max_concurrent = 5  # Could load from config
    if active_count >= max_concurrent:
        # Revoke oldest session
        cursor.execute(
            """
            UPDATE sessions SET is_active = 0
            WHERE user_id = ? AND is_active = 1
            ORDER BY created_at ASC
            LIMIT 1
        """,
            (user_id,),
        )

    metadata_json = json.dumps(metadata) if metadata else None

    cursor.execute(
        """
        INSERT INTO sessions
        (token_hash, user_id, channel, device_id, expires_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (token_hash, user_id, channel, device_id, expires_at.isoformat(), metadata_json),
    )

    session_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_session_event("create", user_id, "success", str(session_id))

    return {
        "success": True,
        "token": token,  # Only time raw token is returned!
        "session_id": session_id,
        "user_id": user_id,
        "channel": channel,
        "expires_at": expires_at.isoformat(),
        "message": "Session created",
    }


def validate_session(
    token: str,
    channel: str | None = None,
    device_id: str | None = None,
    update_activity: bool = True,
) -> dict[str, Any]:
    """
    Validate a session token.

    Args:
        token: Session token to validate
        channel: Expected channel (for binding check)
        device_id: Expected device (for binding check)
        update_activity: Update last activity timestamp

    Returns:
        dict with validation result and session info
    """
    token_hash = hash_token(token)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM sessions WHERE token_hash = ?
    """,
        (token_hash,),
    )

    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"success": True, "valid": False, "reason": "token_not_found"}

    # Check if active
    if not row["is_active"]:
        conn.close()
        return {"success": True, "valid": False, "reason": "session_revoked"}

    # Check expiry
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.now() > expires_at:
        # Mark as inactive
        cursor.execute("UPDATE sessions SET is_active = 0 WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        return {"success": True, "valid": False, "reason": "session_expired"}

    # Check idle timeout
    if row["last_activity"]:
        last_activity = datetime.fromisoformat(row["last_activity"])
        idle_seconds = (datetime.now() - last_activity).total_seconds()
        if idle_seconds > IDLE_TIMEOUT_HOURS * 3600:
            cursor.execute("UPDATE sessions SET is_active = 0 WHERE id = ?", (row["id"],))
            conn.commit()
            conn.close()
            return {"success": True, "valid": False, "reason": "idle_timeout"}

    # Check channel binding
    if channel and row["channel"] and row["channel"] != channel:
        conn.close()
        log_session_event("validate", row["user_id"], "failure", str(row["id"]))
        return {"success": True, "valid": False, "reason": "channel_mismatch"}

    # Check device binding
    if device_id and row["device_id"] and row["device_id"] != device_id:
        conn.close()
        log_session_event("validate", row["user_id"], "failure", str(row["id"]))
        return {"success": True, "valid": False, "reason": "device_mismatch"}

    # Update last activity
    if update_activity:
        cursor.execute(
            "UPDATE sessions SET last_activity = ? WHERE id = ?",
            (datetime.now().isoformat(), row["id"]),
        )
        conn.commit()

    conn.close()

    # Parse metadata
    metadata = None
    if row["metadata"]:
        try:
            metadata = json.loads(row["metadata"])
        except json.JSONDecodeError:
            pass

    return {
        "success": True,
        "valid": True,
        "session_id": row["id"],
        "user_id": row["user_id"],
        "channel": row["channel"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "last_activity": row["last_activity"],
        "metadata": metadata,
    }


def refresh_session(token: str, extend_hours: int = DEFAULT_TTL_HOURS) -> dict[str, Any]:
    """
    Refresh a session's expiry time.

    Args:
        token: Session token
        extend_hours: Hours to extend from now

    Returns:
        dict with new expiry time
    """
    # First validate
    validation = validate_session(token, update_activity=False)
    if not validation.get("valid"):
        return validation

    token_hash = hash_token(token)
    extend_hours = min(extend_hours, MAX_TTL_HOURS)
    new_expires = datetime.now() + timedelta(hours=extend_hours)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE sessions SET
            expires_at = ?,
            last_activity = ?
        WHERE token_hash = ?
    """,
        (new_expires.isoformat(), datetime.now().isoformat(), token_hash),
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "session_id": validation["session_id"],
        "user_id": validation["user_id"],
        "new_expires_at": new_expires.isoformat(),
        "message": "Session refreshed",
    }


def revoke_session(token: str) -> dict[str, Any]:
    """Revoke a single session."""
    token_hash = hash_token(token)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id FROM sessions WHERE token_hash = ?", (token_hash,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"success": False, "error": "Session not found"}

    cursor.execute("UPDATE sessions SET is_active = 0 WHERE token_hash = ?", (token_hash,))
    conn.commit()
    conn.close()

    log_session_event("revoke", row["user_id"], "success", str(row["id"]))

    return {"success": True, "session_id": row["id"], "message": "Session revoked"}


def revoke_all_sessions(user_id: str) -> dict[str, Any]:
    """Revoke all sessions for a user."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) as count FROM sessions WHERE user_id = ? AND is_active = 1", (user_id,)
    )
    count = cursor.fetchone()["count"]

    cursor.execute(
        "UPDATE sessions SET is_active = 0 WHERE user_id = ? AND is_active = 1", (user_id,)
    )
    conn.commit()
    conn.close()

    log_session_event("revoke_all", user_id, "success")

    return {
        "success": True,
        "user_id": user_id,
        "revoked_count": count,
        "message": f"Revoked {count} sessions",
    }


def list_sessions(user_id: str | None = None, active_only: bool = True) -> dict[str, Any]:
    """List sessions, optionally filtered by user."""
    conn = get_connection()
    cursor = conn.cursor()

    if user_id:
        if active_only:
            cursor.execute(
                """
                SELECT id, user_id, channel, device_id, created_at, expires_at, last_activity
                FROM sessions
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at DESC
            """,
                (user_id,),
            )
        else:
            cursor.execute(
                """
                SELECT id, user_id, channel, device_id, created_at, expires_at, last_activity, is_active
                FROM sessions
                WHERE user_id = ?
                ORDER BY created_at DESC
            """,
                (user_id,),
            )
    else:
        if active_only:
            cursor.execute("""
                SELECT id, user_id, channel, device_id, created_at, expires_at, last_activity
                FROM sessions
                WHERE is_active = 1
                ORDER BY created_at DESC
                LIMIT 100
            """)
        else:
            cursor.execute("""
                SELECT id, user_id, channel, device_id, created_at, expires_at, last_activity, is_active
                FROM sessions
                ORDER BY created_at DESC
                LIMIT 100
            """)

    sessions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {"success": True, "sessions": sessions, "count": len(sessions)}


def cleanup_expired() -> dict[str, Any]:
    """Remove expired and revoked sessions."""
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # Mark expired as inactive
    cursor.execute(
        "UPDATE sessions SET is_active = 0 WHERE expires_at < ? AND is_active = 1", (now,)
    )
    expired = cursor.rowcount

    # Delete old inactive sessions (older than 30 days)
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute("DELETE FROM sessions WHERE is_active = 0 AND created_at < ?", (cutoff,))
    deleted = cursor.rowcount

    conn.commit()
    conn.close()

    return {
        "success": True,
        "expired_count": expired,
        "deleted_count": deleted,
        "message": f"Marked {expired} expired, deleted {deleted} old sessions",
    }


def get_stats() -> dict[str, Any]:
    """Get session statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    # Active sessions
    cursor.execute("SELECT COUNT(*) as count FROM sessions WHERE is_active = 1")
    active = cursor.fetchone()["count"]

    # Total sessions
    cursor.execute("SELECT COUNT(*) as count FROM sessions")
    total = cursor.fetchone()["count"]

    # By channel
    cursor.execute("""
        SELECT channel, COUNT(*) as count
        FROM sessions
        WHERE is_active = 1
        GROUP BY channel
    """)
    by_channel = {row["channel"] or "unknown": row["count"] for row in cursor.fetchall()}

    # Unique users with active sessions
    cursor.execute("SELECT COUNT(DISTINCT user_id) as count FROM sessions WHERE is_active = 1")
    unique_users = cursor.fetchone()["count"]

    conn.close()

    return {
        "success": True,
        "stats": {
            "active_sessions": active,
            "total_sessions": total,
            "unique_users": unique_users,
            "by_channel": by_channel,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Session Manager")
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "create",
            "validate",
            "refresh",
            "revoke",
            "revoke-all",
            "list",
            "cleanup",
            "stats",
        ],
        help="Action to perform",
    )

    parser.add_argument("--user", help="User ID")
    parser.add_argument("--token", help="Session token")
    parser.add_argument("--channel", help="Channel (discord, api, cli)")
    parser.add_argument("--device", help="Device ID")
    parser.add_argument(
        "--ttl",
        type=int,
        default=DEFAULT_TTL_HOURS,
        help=f"Session TTL in hours (default: {DEFAULT_TTL_HOURS})",
    )
    parser.add_argument("--metadata", help="JSON metadata")
    parser.add_argument(
        "--include-inactive", action="store_true", help="Include inactive sessions in list"
    )

    args = parser.parse_args()
    result = None

    if args.action == "create":
        if not args.user:
            print("Error: --user required for create")
            sys.exit(1)
        metadata = None
        if args.metadata:
            try:
                metadata = json.loads(args.metadata)
            except json.JSONDecodeError:
                print("Error: --metadata must be valid JSON")
                sys.exit(1)
        result = create_session(
            user_id=args.user,
            channel=args.channel,
            device_id=args.device,
            ttl_hours=args.ttl,
            metadata=metadata,
        )

    elif args.action == "validate":
        if not args.token:
            print("Error: --token required for validate")
            sys.exit(1)
        result = validate_session(token=args.token, channel=args.channel, device_id=args.device)

    elif args.action == "refresh":
        if not args.token:
            print("Error: --token required for refresh")
            sys.exit(1)
        result = refresh_session(token=args.token, extend_hours=args.ttl)

    elif args.action == "revoke":
        if not args.token:
            print("Error: --token required for revoke")
            sys.exit(1)
        result = revoke_session(token=args.token)

    elif args.action == "revoke-all":
        if not args.user:
            print("Error: --user required for revoke-all")
            sys.exit(1)
        result = revoke_all_sessions(user_id=args.user)

    elif args.action == "list":
        result = list_sessions(user_id=args.user, active_only=not args.include_inactive)

    elif args.action == "cleanup":
        result = cleanup_expired()

    elif args.action == "stats":
        result = get_stats()

    if result.get("success"):
        print(f"OK {result.get('message', 'Success')}")
    else:
        print(f"ERROR {result.get('error')}")
        sys.exit(1)

    # Don't print token in normal JSON output
    output = result.copy()
    if "token" in output:
        print(f"\n** SESSION TOKEN (save this!) **\n{output['token']}\n")
        output["token"] = "***CREATED***"

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
