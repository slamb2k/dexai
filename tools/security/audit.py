"""
Tool: Security Audit Logger
Purpose: Append-only logging of security-relevant events for forensics and compliance

This provides an immutable audit trail for:
- Authentication attempts (success/failure)
- Permission checks and denials
- Secret access
- Rate limit events
- Command execution
- System errors

Usage:
    python tools/security/audit.py --action log --type auth --user alice --status success
    python tools/security/audit.py --action log --type command --action "memory:write" --status success --details '{"content_id": 5}'
    python tools/security/audit.py --action query --user alice --since "24h"
    python tools/security/audit.py --action query --type auth --status failure --limit 100
    python tools/security/audit.py --action stats
    python tools/security/audit.py --action export --since "7d" --format json

Dependencies:
    - sqlite3 (stdlib)
    - json (stdlib)

Output:
    JSON result with success status and data
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
import re

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data" / "audit.db"

# Valid event types
VALID_TYPES = ['auth', 'command', 'permission', 'secret', 'rate_limit', 'error', 'system', 'security']

# Valid statuses
VALID_STATUSES = ['success', 'failure', 'blocked']


def get_connection():
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Audit log table - append only, no updates or deletes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL CHECK(event_type IN ('auth', 'command', 'permission', 'secret', 'rate_limit', 'error', 'system', 'security')),
            user_id TEXT,
            session_id TEXT,
            channel TEXT,
            action TEXT NOT NULL,
            resource TEXT,
            status TEXT CHECK(status IN ('success', 'failure', 'blocked')),
            details TEXT,
            ip_address TEXT,
            user_agent TEXT
        )
    ''')

    # Indexes for common queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_log(event_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_status ON audit_log(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id)')

    conn.commit()
    return conn


def row_to_dict(row) -> Optional[Dict]:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    d = dict(row)
    # Parse JSON details if present
    if 'details' in d and d['details']:
        try:
            d['details'] = json.loads(d['details'])
        except json.JSONDecodeError:
            pass
    return d


def log_event(
    event_type: str,
    action: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    channel: Optional[str] = None,
    resource: Optional[str] = None,
    status: str = 'success',
    details: Optional[Dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Dict[str, Any]:
    """
    Log a security event. Append-only - events cannot be modified or deleted.

    Args:
        event_type: Type of event (auth, command, permission, secret, rate_limit, error, system, security)
        action: What action was performed
        user_id: User who performed the action
        session_id: Session token (hashed)
        channel: Channel where action occurred (discord, api, cli)
        resource: Resource being accessed
        status: Outcome (success, failure, blocked)
        details: Additional JSON-serializable context
        ip_address: Client IP address
        user_agent: Client user agent

    Returns:
        dict with success status and event ID
    """
    if event_type not in VALID_TYPES:
        return {"success": False, "error": f"Invalid event type. Must be one of: {VALID_TYPES}"}

    if status not in VALID_STATUSES:
        return {"success": False, "error": f"Invalid status. Must be one of: {VALID_STATUSES}"}

    details_json = json.dumps(details) if details else None

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO audit_log
        (event_type, user_id, session_id, channel, action, resource, status, details, ip_address, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (event_type, user_id, session_id, channel, action, resource, status, details_json, ip_address, user_agent))

    event_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "success": True,
        "event_id": event_id,
        "message": f"Audit event logged with ID {event_id}"
    }


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parse duration string like '24h', '7d', '30m' into timedelta."""
    match = re.match(r'^(\d+)([mhdw])$', duration_str.lower())
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == 'm':
        return timedelta(minutes=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'd':
        return timedelta(days=value)
    elif unit == 'w':
        return timedelta(weeks=value)

    return None


def query_events(
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    channel: Optional[str] = None,
    status: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> Dict[str, Any]:
    """
    Query audit log with filters.

    Args:
        event_type: Filter by event type
        user_id: Filter by user
        session_id: Filter by session
        channel: Filter by channel
        status: Filter by status
        since: Duration string (e.g., '24h', '7d') or ISO datetime
        until: ISO datetime for end of range
        limit: Maximum results
        offset: Pagination offset

    Returns:
        dict with matching events
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []

    if event_type:
        if event_type not in VALID_TYPES:
            conn.close()
            return {"success": False, "error": f"Invalid event type. Must be one of: {VALID_TYPES}"}
        conditions.append('event_type = ?')
        params.append(event_type)

    if user_id:
        conditions.append('user_id = ?')
        params.append(user_id)

    if session_id:
        conditions.append('session_id = ?')
        params.append(session_id)

    if channel:
        conditions.append('channel = ?')
        params.append(channel)

    if status:
        if status not in VALID_STATUSES:
            conn.close()
            return {"success": False, "error": f"Invalid status. Must be one of: {VALID_STATUSES}"}
        conditions.append('status = ?')
        params.append(status)

    if since:
        # Try parsing as duration first
        duration = parse_duration(since)
        if duration:
            cutoff = datetime.now() - duration
            conditions.append('timestamp >= ?')
            params.append(cutoff.isoformat())
        else:
            # Try as ISO datetime
            conditions.append('timestamp >= ?')
            params.append(since)

    if until:
        conditions.append('timestamp <= ?')
        params.append(until)

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    cursor.execute(f'''
        SELECT * FROM audit_log
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    ''', params + [limit, offset])

    events = [row_to_dict(row) for row in cursor.fetchall()]

    # Get total count
    cursor.execute(f'SELECT COUNT(*) as count FROM audit_log WHERE {where_clause}', params)
    total = cursor.fetchone()['count']

    conn.close()

    return {
        "success": True,
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset
    }


def get_stats() -> Dict[str, Any]:
    """Get audit log statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    # Total events
    cursor.execute('SELECT COUNT(*) as total FROM audit_log')
    total = cursor.fetchone()['total']

    # By type
    cursor.execute('SELECT event_type, COUNT(*) as count FROM audit_log GROUP BY event_type')
    by_type = {row['event_type']: row['count'] for row in cursor.fetchall()}

    # By status
    cursor.execute('SELECT status, COUNT(*) as count FROM audit_log GROUP BY status')
    by_status = {row['status']: row['count'] for row in cursor.fetchall()}

    # Last 24 hours
    yesterday = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute('SELECT COUNT(*) as count FROM audit_log WHERE timestamp >= ?', (yesterday,))
    last_24h = cursor.fetchone()['count']

    # Failures in last 24h
    cursor.execute(
        'SELECT COUNT(*) as count FROM audit_log WHERE timestamp >= ? AND status = ?',
        (yesterday, 'failure')
    )
    failures_24h = cursor.fetchone()['count']

    # Most active users
    cursor.execute('''
        SELECT user_id, COUNT(*) as count
        FROM audit_log
        WHERE user_id IS NOT NULL
        GROUP BY user_id
        ORDER BY count DESC
        LIMIT 10
    ''')
    top_users = [{row['user_id']: row['count']} for row in cursor.fetchall()]

    # Recent failures
    cursor.execute('''
        SELECT * FROM audit_log
        WHERE status = 'failure'
        ORDER BY timestamp DESC
        LIMIT 10
    ''')
    recent_failures = [row_to_dict(row) for row in cursor.fetchall()]

    # Database size
    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    db_size = cursor.fetchone()['size']

    conn.close()

    return {
        "success": True,
        "stats": {
            "total_events": total,
            "events_24h": last_24h,
            "failures_24h": failures_24h,
            "by_type": by_type,
            "by_status": by_status,
            "top_users": top_users,
            "recent_failures": recent_failures,
            "db_size_bytes": db_size
        }
    }


def export_events(
    since: Optional[str] = None,
    format: str = 'json'
) -> Dict[str, Any]:
    """
    Export audit events for archival or analysis.

    Args:
        since: Duration string or ISO datetime
        format: Output format (json, csv)

    Returns:
        dict with export data or path
    """
    result = query_events(since=since, limit=100000)  # Large limit for export
    if not result['success']:
        return result

    events = result['events']

    if format == 'json':
        return {
            "success": True,
            "format": "json",
            "count": len(events),
            "data": events
        }
    elif format == 'csv':
        # Convert to CSV format
        if not events:
            return {"success": True, "format": "csv", "count": 0, "data": ""}

        headers = ['id', 'timestamp', 'event_type', 'user_id', 'session_id',
                   'channel', 'action', 'resource', 'status', 'ip_address']
        lines = [','.join(headers)]

        for event in events:
            row = [str(event.get(h, '')) for h in headers]
            lines.append(','.join(f'"{v}"' for v in row))

        return {
            "success": True,
            "format": "csv",
            "count": len(events),
            "data": '\n'.join(lines)
        }
    else:
        return {"success": False, "error": f"Unknown format: {format}"}


def cleanup_old_events(retention_days: int = 90, dry_run: bool = False) -> Dict[str, Any]:
    """
    Remove events older than retention period.
    NOTE: Use with caution - this is the only way to delete audit logs.

    Args:
        retention_days: Keep events newer than this
        dry_run: If True, just count without deleting

    Returns:
        dict with deletion count
    """
    conn = get_connection()
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()

    cursor.execute('SELECT COUNT(*) as count FROM audit_log WHERE timestamp < ?', (cutoff,))
    count = cursor.fetchone()['count']

    if dry_run:
        conn.close()
        return {
            "success": True,
            "message": f"Would delete {count} events older than {retention_days} days",
            "count": count,
            "dry_run": True
        }

    cursor.execute('DELETE FROM audit_log WHERE timestamp < ?', (cutoff,))
    conn.commit()

    # Vacuum to reclaim space
    cursor.execute('VACUUM')
    conn.close()

    return {
        "success": True,
        "message": f"Deleted {count} events older than {retention_days} days",
        "count": count
    }


def main():
    parser = argparse.ArgumentParser(description='Security Audit Logger')
    parser.add_argument('--action', required=True,
                       choices=['log', 'query', 'stats', 'export', 'cleanup'],
                       help='Action to perform')

    # Log action args
    parser.add_argument('--type', dest='event_type',
                       choices=VALID_TYPES,
                       help='Event type')
    parser.add_argument('--event-action', dest='event_action',
                       help='Action being logged')
    parser.add_argument('--user', help='User ID')
    parser.add_argument('--session', help='Session ID')
    parser.add_argument('--channel', help='Channel (discord, api, cli)')
    parser.add_argument('--resource', help='Resource being accessed')
    parser.add_argument('--status', choices=VALID_STATUSES, default='success',
                       help='Event status')
    parser.add_argument('--details', help='JSON details')
    parser.add_argument('--ip', help='IP address')
    parser.add_argument('--ua', dest='user_agent', help='User agent')

    # Query args
    parser.add_argument('--since', help='Time range start (e.g., "24h", "7d")')
    parser.add_argument('--until', help='Time range end (ISO datetime)')
    parser.add_argument('--limit', type=int, default=100, help='Max results')
    parser.add_argument('--offset', type=int, default=0, help='Pagination offset')

    # Export args
    parser.add_argument('--format', choices=['json', 'csv'], default='json',
                       help='Export format')

    # Cleanup args
    parser.add_argument('--retention-days', type=int, default=90,
                       help='Keep events newer than this')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be deleted without deleting')

    args = parser.parse_args()
    result = None

    if args.action == 'log':
        if not args.event_type or not args.event_action:
            print("Error: --type and --event-action required for log")
            sys.exit(1)

        details = None
        if args.details:
            try:
                details = json.loads(args.details)
            except json.JSONDecodeError:
                print("Error: --details must be valid JSON")
                sys.exit(1)

        result = log_event(
            event_type=args.event_type,
            action=args.event_action,
            user_id=args.user,
            session_id=args.session,
            channel=args.channel,
            resource=args.resource,
            status=args.status,
            details=details,
            ip_address=args.ip,
            user_agent=args.user_agent
        )

    elif args.action == 'query':
        result = query_events(
            event_type=args.event_type,
            user_id=args.user,
            session_id=args.session,
            channel=args.channel,
            status=args.status,
            since=args.since,
            until=args.until,
            limit=args.limit,
            offset=args.offset
        )

    elif args.action == 'stats':
        result = get_stats()

    elif args.action == 'export':
        result = export_events(since=args.since, format=args.format)

    elif args.action == 'cleanup':
        result = cleanup_old_events(
            retention_days=args.retention_days,
            dry_run=args.dry_run
        )

    if result:
        if result.get('success'):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
