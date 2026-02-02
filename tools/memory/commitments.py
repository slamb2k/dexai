"""
Tool: Commitments Tracker
Purpose: Track promises made in conversations so nothing falls through the cracks

ADHD users frequently damage relationships through *forgetting*, not lack of caring.
This tool tracks commitments extracted from conversations and surfaces them gently
when appropriate.

Design principles (from adhd_design_principles.md):
- Surface commitments as opportunities, not obligations
- "Sarah's waiting on those docs - want to send them now?" (helpful)
- NOT "You still haven't sent Sarah the docs (3 days overdue)" (guilt-inducing)
- Group by target person when displaying (relationship context)

Usage:
    # Add a commitment
    python tools/memory/commitments.py --action add --user alice \\
        --content "Send Sarah the API docs" \\
        --target-person "Sarah" \\
        --due-date "2024-02-05"

    # List active commitments
    python tools/memory/commitments.py --action list --user alice --status active

    # Complete a commitment
    python tools/memory/commitments.py --action complete --id "comm_abc123"

    # Get commitments due soon
    python tools/memory/commitments.py --action due-soon --user alice --hours 24

    # Extract commitments from text
    python tools/memory/commitments.py --action extract --user alice \\
        --text "I'll send you the docs tomorrow"

Dependencies:
    - sqlite3 (stdlib)
    - json (stdlib)
    - yaml (pyyaml)

Output:
    JSON result with success status and commitment data
"""

import os
import sys
import json
import sqlite3
import argparse
import uuid
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

import yaml

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "context.db"
CONFIG_PATH = PROJECT_ROOT / "args" / "working_memory.yaml"
HARDPROMPT_PATH = PROJECT_ROOT / "hardprompts" / "memory" / "commitment_detection.md"

# Valid statuses
VALID_STATUSES = ['active', 'completed', 'cancelled']


def load_config() -> Dict[str, Any]:
    """Load working memory configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Commitments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commitments (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            source_message_id TEXT,
            source_channel TEXT,
            target_person TEXT,
            due_date DATETIME,
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'cancelled')),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            reminder_sent INTEGER DEFAULT 0,
            notes TEXT
        )
    ''')

    # Indexes for common queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commitments_user ON commitments(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commitments_user_status ON commitments(user_id, status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commitments_due ON commitments(due_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commitments_target ON commitments(target_person)')

    conn.commit()
    return conn


def row_to_dict(row) -> Optional[Dict]:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    d = dict(row)
    return d


def generate_commitment_id(user_id: str) -> str:
    """Generate a unique commitment ID."""
    timestamp = int(datetime.now().timestamp())
    short_uuid = uuid.uuid4().hex[:8]
    return f"comm_{timestamp}_{user_id}_{short_uuid}"


def parse_due_date(due_date_str: str) -> Optional[str]:
    """Parse various date formats into ISO format."""
    if not due_date_str:
        return None

    # Try ISO format first
    try:
        dt = datetime.fromisoformat(due_date_str)
        return dt.isoformat()
    except ValueError:
        pass

    # Try common formats
    formats = [
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%d-%m-%Y',
        '%d/%m/%Y',
        '%m-%d-%Y',
        '%m/%d/%Y',
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(due_date_str, fmt)
            return dt.isoformat()
        except ValueError:
            continue

    # Try relative dates
    due_date_lower = due_date_str.lower().strip()
    now = datetime.now()

    if due_date_lower == 'today':
        return now.replace(hour=23, minute=59, second=59).isoformat()
    elif due_date_lower == 'tomorrow':
        return (now + timedelta(days=1)).replace(hour=23, minute=59, second=59).isoformat()
    elif due_date_lower in ('next week', 'nextweek'):
        return (now + timedelta(weeks=1)).isoformat()

    # Try "in X days/hours" format
    match = re.match(r'in\s+(\d+)\s+(day|days|hour|hours|week|weeks)', due_date_lower)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if 'day' in unit:
            return (now + timedelta(days=value)).isoformat()
        elif 'hour' in unit:
            return (now + timedelta(hours=value)).isoformat()
        elif 'week' in unit:
            return (now + timedelta(weeks=value)).isoformat()

    return None


def add_commitment(
    user_id: str,
    content: str,
    target_person: Optional[str] = None,
    due_date: Optional[str] = None,
    source_message_id: Optional[str] = None,
    source_channel: Optional[str] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add a new commitment.

    Args:
        user_id: User identifier
        content: What was promised
        target_person: Who it was promised to
        due_date: When it's due (various formats accepted)
        source_message_id: ID of the message containing the promise
        source_channel: Channel where promise was made
        notes: Additional notes

    Returns:
        dict with success status and commitment data
    """
    if not user_id:
        return {"success": False, "error": "user_id is required"}
    if not content:
        return {"success": False, "error": "content is required"}

    # Parse due date
    parsed_due_date = parse_due_date(due_date) if due_date else None

    commitment_id = generate_commitment_id(user_id)
    created_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO commitments
        (id, user_id, content, source_message_id, source_channel, target_person, due_date, status, created_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
    ''', (
        commitment_id,
        user_id,
        content,
        source_message_id,
        source_channel,
        target_person,
        parsed_due_date,
        created_at,
        notes
    ))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Commitment added for user {user_id}",
        "data": {
            "id": commitment_id,
            "user_id": user_id,
            "content": content,
            "target_person": target_person,
            "due_date": parsed_due_date,
            "status": "active",
            "created_at": created_at
        }
    }


def list_commitments(
    user_id: str,
    status: Optional[str] = None,
    target_person: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    group_by_person: bool = False
) -> Dict[str, Any]:
    """
    List commitments for a user.

    Args:
        user_id: User identifier
        status: Filter by status ('active', 'completed', 'cancelled')
        target_person: Filter by target person
        limit: Maximum results
        offset: Pagination offset
        group_by_person: Group results by target person

    Returns:
        dict with list of commitments
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = ['user_id = ?']
    params: List[Any] = [user_id]

    if status:
        if status not in VALID_STATUSES:
            conn.close()
            return {"success": False, "error": f"Invalid status. Must be one of: {VALID_STATUSES}"}
        conditions.append('status = ?')
        params.append(status)

    if target_person:
        conditions.append('target_person = ?')
        params.append(target_person)

    where_clause = ' AND '.join(conditions)

    # Order by due date (NULL last), then created_at
    cursor.execute(f'''
        SELECT * FROM commitments
        WHERE {where_clause}
        ORDER BY
            CASE WHEN due_date IS NULL THEN 1 ELSE 0 END,
            due_date ASC,
            created_at DESC
        LIMIT ? OFFSET ?
    ''', params + [limit, offset])

    commitments = [row_to_dict(row) for row in cursor.fetchall()]

    # Add age information
    for comm in commitments:
        created_at = datetime.fromisoformat(comm['created_at'])
        age = datetime.now() - created_at
        comm['age_days'] = round(age.total_seconds() / 86400, 1)

        # Check if overdue
        if comm['due_date'] and comm['status'] == 'active':
            due = datetime.fromisoformat(comm['due_date'])
            comm['is_overdue'] = datetime.now() > due
            if comm['is_overdue']:
                comm['overdue_days'] = round((datetime.now() - due).total_seconds() / 86400, 1)

    # Get total count
    cursor.execute(f'SELECT COUNT(*) as count FROM commitments WHERE {where_clause}', params)
    total = cursor.fetchone()['count']

    conn.close()

    # Group by person if requested
    if group_by_person and commitments:
        grouped = {}
        for comm in commitments:
            person = comm.get('target_person') or 'Unspecified'
            if person not in grouped:
                grouped[person] = []
            grouped[person].append(comm)

        return {
            "success": True,
            "data": {
                "commitments_by_person": grouped,
                "total": total,
                "limit": limit,
                "offset": offset
            }
        }

    return {
        "success": True,
        "data": {
            "commitments": commitments,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    }


def get_commitment(commitment_id: str) -> Dict[str, Any]:
    """Get a specific commitment."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM commitments WHERE id = ?', (commitment_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": f"Commitment not found: {commitment_id}"}

    commitment = row_to_dict(row)

    # Add age info
    created_at = datetime.fromisoformat(commitment['created_at'])
    age = datetime.now() - created_at
    commitment['age_days'] = round(age.total_seconds() / 86400, 1)

    return {
        "success": True,
        "data": commitment
    }


def complete_commitment(commitment_id: str, notes: Optional[str] = None) -> Dict[str, Any]:
    """
    Mark a commitment as completed.

    Args:
        commitment_id: Commitment identifier
        notes: Optional completion notes

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    completed_at = datetime.now().isoformat()

    if notes:
        cursor.execute('''
            UPDATE commitments
            SET status = 'completed', completed_at = ?, notes = COALESCE(notes || ' | ', '') || ?
            WHERE id = ? AND status = 'active'
        ''', (completed_at, notes, commitment_id))
    else:
        cursor.execute('''
            UPDATE commitments
            SET status = 'completed', completed_at = ?
            WHERE id = ? AND status = 'active'
        ''', (completed_at, commitment_id))

    updated = cursor.rowcount
    conn.commit()
    conn.close()

    if updated == 0:
        return {"success": False, "error": f"Commitment not found or not active: {commitment_id}"}

    return {
        "success": True,
        "message": f"Commitment {commitment_id} marked as completed"
    }


def cancel_commitment(commitment_id: str, notes: Optional[str] = None) -> Dict[str, Any]:
    """
    Mark a commitment as cancelled.

    Args:
        commitment_id: Commitment identifier
        notes: Reason for cancellation

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    if notes:
        cursor.execute('''
            UPDATE commitments
            SET status = 'cancelled', notes = COALESCE(notes || ' | ', '') || ?
            WHERE id = ? AND status = 'active'
        ''', (notes, commitment_id))
    else:
        cursor.execute('''
            UPDATE commitments
            SET status = 'cancelled'
            WHERE id = ? AND status = 'active'
        ''', (commitment_id,))

    updated = cursor.rowcount
    conn.commit()
    conn.close()

    if updated == 0:
        return {"success": False, "error": f"Commitment not found or not active: {commitment_id}"}

    return {
        "success": True,
        "message": f"Commitment {commitment_id} cancelled"
    }


def get_due_soon(user_id: str, hours: int = 24) -> Dict[str, Any]:
    """
    Get commitments due within the specified hours.

    Args:
        user_id: User identifier
        hours: Number of hours to look ahead

    Returns:
        dict with commitments due soon
    """
    conn = get_connection()
    cursor = conn.cursor()

    cutoff = (datetime.now() + timedelta(hours=hours)).isoformat()

    cursor.execute('''
        SELECT * FROM commitments
        WHERE user_id = ?
          AND status = 'active'
          AND due_date IS NOT NULL
          AND due_date <= ?
        ORDER BY due_date ASC
    ''', (user_id, cutoff))

    commitments = [row_to_dict(row) for row in cursor.fetchall()]

    # Add time until due
    for comm in commitments:
        due = datetime.fromisoformat(comm['due_date'])
        time_left = due - datetime.now()
        comm['hours_until_due'] = round(time_left.total_seconds() / 3600, 1)
        comm['is_overdue'] = time_left.total_seconds() < 0

    conn.close()

    return {
        "success": True,
        "data": {
            "commitments": commitments,
            "count": len(commitments),
            "hours_ahead": hours
        }
    }


def get_overdue(user_id: str) -> Dict[str, Any]:
    """Get all overdue commitments for a user."""
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute('''
        SELECT * FROM commitments
        WHERE user_id = ?
          AND status = 'active'
          AND due_date IS NOT NULL
          AND due_date < ?
        ORDER BY due_date ASC
    ''', (user_id, now))

    commitments = [row_to_dict(row) for row in cursor.fetchall()]

    # Add overdue duration
    for comm in commitments:
        due = datetime.fromisoformat(comm['due_date'])
        overdue_time = datetime.now() - due
        comm['overdue_hours'] = round(overdue_time.total_seconds() / 3600, 1)
        comm['overdue_days'] = round(overdue_time.total_seconds() / 86400, 1)

    conn.close()

    return {
        "success": True,
        "data": {
            "commitments": commitments,
            "count": len(commitments)
        }
    }


def mark_reminder_sent(commitment_id: str) -> Dict[str, Any]:
    """Mark that a reminder was sent for this commitment."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE commitments
        SET reminder_sent = reminder_sent + 1
        WHERE id = ?
    ''', (commitment_id,))

    updated = cursor.rowcount
    conn.commit()
    conn.close()

    if updated == 0:
        return {"success": False, "error": f"Commitment not found: {commitment_id}"}

    return {
        "success": True,
        "message": f"Reminder count incremented for {commitment_id}"
    }


def extract_commitments_simple(text: str) -> List[Dict[str, Any]]:
    """
    Simple pattern-based commitment extraction.

    For more sophisticated extraction, use the hardprompt template with an LLM.
    This provides basic pattern matching for common commitment phrases.
    """
    commitments = []

    # Common commitment patterns
    patterns = [
        r"I(?:'ll| will) (.+?)(?:\.|$)",
        r"I(?:'m going to| am going to) (.+?)(?:\.|$)",
        r"(?:I )?promise(?:d)? (?:to )?(.+?)(?:\.|$)",
        r"(?:I'll )?(?:make sure|ensure) (?:to )?(.+?)(?:\.|$)",
        r"(?:I'll )?(?:get|send|email|call|text) (?:you )?(.+?)(?:\.|$)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Clean up the match
            content = match.strip()
            if len(content) > 5:  # Skip very short matches
                commitments.append({
                    "content": content,
                    "confidence": "low",  # Pattern-based extraction is low confidence
                    "pattern_matched": pattern
                })

    return commitments


def extract_commitments(user_id: str, text: str, source_channel: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract and optionally store commitments from text.

    This uses simple pattern matching. For LLM-based extraction,
    use the hardprompt template with your preferred LLM.

    Args:
        user_id: User identifier
        text: Text to extract commitments from
        source_channel: Source channel for context

    Returns:
        dict with extracted commitments
    """
    extracted = extract_commitments_simple(text)

    return {
        "success": True,
        "data": {
            "extracted_commitments": extracted,
            "count": len(extracted),
            "note": "These are pattern-based extractions with low confidence. Use hardprompts/memory/commitment_detection.md with an LLM for better results."
        }
    }


def get_hardprompt_template(text: str) -> Dict[str, Any]:
    """
    Get the commitment detection hardprompt filled with text.

    Args:
        text: Text to analyze for commitments

    Returns:
        dict with filled template ready for LLM
    """
    if HARDPROMPT_PATH.exists():
        with open(HARDPROMPT_PATH, 'r') as f:
            template = f.read()
    else:
        template = """Extract commitments from the following text.

A commitment is a promise to do something - explicit or implied.

Look for:
- "I'll..." / "I will..."
- "I'm going to..."
- "I promise..."
- "I'll make sure..."
- Implied promises to send, review, check, call, etc.

For each commitment, extract:
- content: What was promised
- target_person: Who it was promised to (if mentioned)
- due_date: When it's due (if mentioned)
- confidence: high/medium/low

Return as JSON array.

Text to analyze:
{{text}}
"""

    filled_template = template.replace('{{text}}', text)

    return {
        "success": True,
        "data": {
            "template": filled_template
        }
    }


def get_stats(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Get commitment statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    base_condition = 'user_id = ?' if user_id else '1=1'
    params = [user_id] if user_id else []

    # Total by status
    cursor.execute(f'''
        SELECT status, COUNT(*) as count
        FROM commitments
        WHERE {base_condition}
        GROUP BY status
    ''', params)
    by_status = {row['status']: row['count'] for row in cursor.fetchall()}

    # Active count
    active = by_status.get('active', 0)

    # Overdue count
    if user_id:
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM commitments
            WHERE user_id = ? AND status = 'active' AND due_date IS NOT NULL AND due_date < ?
        ''', (user_id, datetime.now().isoformat()))
    else:
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM commitments
            WHERE status = 'active' AND due_date IS NOT NULL AND due_date < ?
        ''', (datetime.now().isoformat(),))
    overdue = cursor.fetchone()['count']

    # Completion rate (last 30 days)
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute(f'''
        SELECT status, COUNT(*) as count
        FROM commitments
        WHERE {base_condition} AND created_at >= ?
        GROUP BY status
    ''', params + [thirty_days_ago])
    recent_by_status = {row['status']: row['count'] for row in cursor.fetchall()}

    recent_completed = recent_by_status.get('completed', 0)
    recent_total = sum(recent_by_status.values())
    completion_rate = round(recent_completed / recent_total * 100, 1) if recent_total > 0 else 0

    conn.close()

    return {
        "success": True,
        "stats": {
            "by_status": by_status,
            "active_commitments": active,
            "overdue_commitments": overdue,
            "completion_rate_30d": completion_rate
        }
    }


def cleanup_old_commitments(
    max_age_days: int = 30,
    status: str = 'active',
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Archive old unfulfilled commitments.

    Args:
        max_age_days: Archive commitments older than this
        status: Status to filter (default: active)
        dry_run: If True, just count without updating

    Returns:
        dict with archive count
    """
    conn = get_connection()
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()

    cursor.execute('''
        SELECT COUNT(*) as count
        FROM commitments
        WHERE status = ? AND created_at < ?
    ''', (status, cutoff))
    count = cursor.fetchone()['count']

    if dry_run:
        conn.close()
        return {
            "success": True,
            "message": f"Would archive {count} {status} commitments older than {max_age_days} days",
            "count": count,
            "dry_run": True
        }

    # Mark as cancelled with note
    cursor.execute('''
        UPDATE commitments
        SET status = 'cancelled', notes = COALESCE(notes || ' | ', '') || 'Auto-archived after ' || ? || ' days'
        WHERE status = ? AND created_at < ?
    ''', (max_age_days, status, cutoff))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Archived {count} {status} commitments older than {max_age_days} days",
        "count": count
    }


def main():
    parser = argparse.ArgumentParser(
        description='Commitments Tracker - Track promises so nothing falls through the cracks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Add a commitment
    %(prog)s --action add --user alice \\
        --content "Send Sarah the API docs" \\
        --target-person "Sarah" \\
        --due-date "2024-02-05"

    # List active commitments
    %(prog)s --action list --user alice --status active

    # Complete a commitment
    %(prog)s --action complete --id "comm_abc123"

    # Get commitments due soon
    %(prog)s --action due-soon --user alice --hours 24

    # Extract commitments from text
    %(prog)s --action extract --user alice \\
        --text "I'll send you the docs tomorrow"
        '''
    )

    parser.add_argument('--action', required=True,
                       choices=['add', 'list', 'get', 'complete', 'cancel',
                               'due-soon', 'overdue', 'extract', 'template',
                               'stats', 'cleanup', 'mark-reminded'],
                       help='Action to perform')

    # Common args
    parser.add_argument('--user', help='User ID')
    parser.add_argument('--id', help='Commitment ID')

    # Add action args
    parser.add_argument('--content', help='Commitment content')
    parser.add_argument('--target-person', help='Who the commitment is to')
    parser.add_argument('--due-date', help='Due date (various formats)')
    parser.add_argument('--source-channel', help='Source channel')
    parser.add_argument('--source-message-id', help='Source message ID')
    parser.add_argument('--notes', help='Additional notes')

    # List args
    parser.add_argument('--status', choices=VALID_STATUSES, help='Filter by status')
    parser.add_argument('--limit', type=int, default=50, help='Max results')
    parser.add_argument('--offset', type=int, default=0, help='Pagination offset')
    parser.add_argument('--group-by-person', action='store_true',
                       help='Group results by target person')

    # Due soon args
    parser.add_argument('--hours', type=int, default=24, help='Hours to look ahead')

    # Extract args
    parser.add_argument('--text', help='Text to extract commitments from')

    # Cleanup args
    parser.add_argument('--max-age-days', type=int, default=30,
                       help='Archive commitments older than this')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without doing it')

    args = parser.parse_args()
    result = None

    if args.action == 'add':
        if not args.user:
            print("Error: --user required for add")
            sys.exit(1)
        if not args.content:
            print("Error: --content required for add")
            sys.exit(1)

        result = add_commitment(
            user_id=args.user,
            content=args.content,
            target_person=args.target_person,
            due_date=args.due_date,
            source_message_id=args.source_message_id,
            source_channel=args.source_channel,
            notes=args.notes
        )

    elif args.action == 'list':
        if not args.user:
            print("Error: --user required for list")
            sys.exit(1)

        result = list_commitments(
            user_id=args.user,
            status=args.status,
            target_person=args.target_person,
            limit=args.limit,
            offset=args.offset,
            group_by_person=args.group_by_person
        )

    elif args.action == 'get':
        if not args.id:
            print("Error: --id required for get")
            sys.exit(1)

        result = get_commitment(args.id)

    elif args.action == 'complete':
        if not args.id:
            print("Error: --id required for complete")
            sys.exit(1)

        result = complete_commitment(args.id, notes=args.notes)

    elif args.action == 'cancel':
        if not args.id:
            print("Error: --id required for cancel")
            sys.exit(1)

        result = cancel_commitment(args.id, notes=args.notes)

    elif args.action == 'due-soon':
        if not args.user:
            print("Error: --user required for due-soon")
            sys.exit(1)

        result = get_due_soon(args.user, hours=args.hours)

    elif args.action == 'overdue':
        if not args.user:
            print("Error: --user required for overdue")
            sys.exit(1)

        result = get_overdue(args.user)

    elif args.action == 'extract':
        if not args.user:
            print("Error: --user required for extract")
            sys.exit(1)
        if not args.text:
            print("Error: --text required for extract")
            sys.exit(1)

        result = extract_commitments(
            user_id=args.user,
            text=args.text,
            source_channel=args.source_channel
        )

    elif args.action == 'template':
        if not args.text:
            print("Error: --text required for template")
            sys.exit(1)

        result = get_hardprompt_template(args.text)

    elif args.action == 'stats':
        result = get_stats(user_id=args.user)

    elif args.action == 'cleanup':
        result = cleanup_old_commitments(
            max_age_days=args.max_age_days,
            status=args.status or 'active',
            dry_run=args.dry_run
        )

    elif args.action == 'mark-reminded':
        if not args.id:
            print("Error: --id required for mark-reminded")
            sys.exit(1)

        result = mark_reminder_sent(args.id)

    if result:
        if result.get('success'):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
