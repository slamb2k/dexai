"""
Tool: Office Audit Logger
Purpose: Permanent, immutable log of all office actions

Provides a complete audit trail for Level 4+ (Managed Proxy) integration.
All actions taken on behalf of the user are logged with full context.

Key Features:
- Immutable audit entries (append-only)
- Human-readable action summaries
- Full JSON action data storage
- Configurable data retention with optional field redaction
- Export to CSV for compliance/review

Usage:
    python audit_logger.py --account-id <id> --list --limit 50
    python audit_logger.py --account-id <id> --export csv --output audit.csv
    python audit_logger.py --account-id <id> --summary week

Dependencies:
    - sqlite3 (standard library)
"""

import argparse
import asyncio
import csv
import json
import sys
import uuid
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection


# Valid result statuses
VALID_RESULTS = ["success", "failed", "undone"]

# Action types for categorization
ACTION_TYPES = [
    "email_send",
    "email_delete",
    "email_archive",
    "email_draft",
    "meeting_schedule",
    "meeting_cancel",
    "meeting_update",
    "calendar_create",
    "calendar_delete",
    "action_undo",
    "policy_trigger",
    "other",
]


def _ensure_audit_columns() -> None:
    """
    Ensure the audit log table has the related_action_id column.

    This handles schema migration for existing databases.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if related_action_id column exists
    cursor.execute("PRAGMA table_info(office_audit_log)")
    columns = [row[1] for row in cursor.fetchall()]

    if "related_action_id" not in columns:
        cursor.execute("""
            ALTER TABLE office_audit_log
            ADD COLUMN related_action_id TEXT
        """)
        conn.commit()

    conn.close()


async def log_action(
    account_id: str,
    action_type: str,
    action_summary: str,
    action_data: dict[str, Any],
    result: str,
    related_action_id: str | None = None,
) -> dict[str, Any]:
    """
    Log an action to the permanent audit trail.

    This creates an immutable record of the action. Entries cannot be
    modified or deleted (only the result can be updated to "undone").

    Args:
        account_id: Office account ID
        action_type: Type of action (e.g., "email_send", "meeting_schedule")
        action_summary: Human-readable summary (e.g., "Sent email to john@example.com: 'Meeting follow-up'")
        action_data: Full JSON data of the action
        result: Action result - "success", "failed", or "undone"
        related_action_id: Optional ID of related action (e.g., original action when logging undo)

    Returns:
        {
            "success": bool,
            "log_id": str,
        }
    """
    if result not in VALID_RESULTS:
        return {
            "success": False,
            "error": f"Invalid result: {result}. Must be one of {VALID_RESULTS}",
        }

    # Ensure schema is up to date
    _ensure_audit_columns()

    log_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO office_audit_log (
            id, account_id, action_type, action_summary, action_data, result, created_at, related_action_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log_id,
            account_id,
            action_type,
            action_summary,
            json.dumps(action_data),
            result,
            created_at,
            related_action_id,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "log_id": log_id,
    }


async def get_audit_log(
    account_id: str,
    action_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    result: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Retrieve audit log entries with optional filtering.

    Args:
        account_id: Office account ID
        action_type: Filter by action type (optional)
        start_date: Filter by start date (ISO format, optional)
        end_date: Filter by end date (ISO format, optional)
        result: Filter by result status (optional)
        limit: Maximum number of entries to return
        offset: Offset for pagination

    Returns:
        {
            "success": bool,
            "entries": list[dict],
            "total": int,
        }
    """
    # Ensure schema is up to date
    _ensure_audit_columns()

    conn = get_connection()
    cursor = conn.cursor()

    # Build query with filters
    query = "SELECT * FROM office_audit_log WHERE account_id = ?"
    count_query = "SELECT COUNT(*) FROM office_audit_log WHERE account_id = ?"
    params: list[Any] = [account_id]

    if action_type:
        query += " AND action_type = ?"
        count_query += " AND action_type = ?"
        params.append(action_type)

    if start_date:
        query += " AND created_at >= ?"
        count_query += " AND created_at >= ?"
        params.append(start_date)

    if end_date:
        query += " AND created_at <= ?"
        count_query += " AND created_at <= ?"
        params.append(end_date)

    if result:
        if result not in VALID_RESULTS:
            conn.close()
            return {
                "success": False,
                "error": f"Invalid result filter: {result}. Must be one of {VALID_RESULTS}",
            }
        query += " AND result = ?"
        count_query += " AND result = ?"
        params.append(result)

    # Get total count
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    # Add ordering and pagination
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    entries = []
    for row in rows:
        entry = dict(row)
        # Parse action_data JSON
        if entry.get("action_data"):
            entry["action_data"] = json.loads(entry["action_data"])
        entries.append(entry)

    return {
        "success": True,
        "entries": entries,
        "total": total,
    }


async def export_audit_log(
    account_id: str,
    format: str = "csv",
    start_date: str | None = None,
    end_date: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Export audit log to a file.

    Args:
        account_id: Office account ID
        format: Export format ("csv" or "json")
        start_date: Filter by start date (ISO format, optional)
        end_date: Filter by end date (ISO format, optional)
        output_path: Output file path (optional, generates default if not provided)

    Returns:
        {
            "success": bool,
            "file_path": str,
            "entries": int,
        }
    """
    # Get all entries (no pagination for export)
    result = await get_audit_log(
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        limit=100000,  # Large limit for export
        offset=0,
    )

    if not result.get("success"):
        return result

    entries = result["entries"]

    if not entries:
        return {
            "success": False,
            "error": "No entries found for export",
        }

    # Generate output path if not provided
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(PROJECT_ROOT / "data" / f"audit_export_{account_id}_{timestamp}.{format}")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if format == "csv":
        with open(output_path, "w", newline="") as f:
            fieldnames = [
                "id",
                "account_id",
                "action_type",
                "action_summary",
                "action_data",
                "result",
                "created_at",
                "related_action_id",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for entry in entries:
                # Convert action_data back to JSON string for CSV
                row = entry.copy()
                if row.get("action_data"):
                    row["action_data"] = json.dumps(row["action_data"])
                writer.writerow(row)

    elif format == "json":
        with open(output_path, "w") as f:
            json.dump(entries, f, indent=2, default=str)

    else:
        return {
            "success": False,
            "error": f"Unsupported export format: {format}. Use 'csv' or 'json'.",
        }

    return {
        "success": True,
        "file_path": output_path,
        "entries": len(entries),
    }


async def get_audit_summary(
    account_id: str,
    period: str = "day",
) -> dict[str, Any]:
    """
    Get a summary of audit log activity for a time period.

    Args:
        account_id: Office account ID
        period: Time period - "day", "week", or "month"

    Returns:
        {
            "success": bool,
            "summary": {
                "period": str,
                "start_date": str,
                "end_date": str,
                "total_actions": int,
                "by_type": dict,
                "by_result": dict,
                "undone_count": int,
            }
        }
    """
    # Calculate date range based on period
    now = datetime.now()
    if period == "day":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        # Start from Monday of current week
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return {
            "success": False,
            "error": f"Invalid period: {period}. Use 'day', 'week', or 'month'.",
        }

    end_date = now

    conn = get_connection()
    cursor = conn.cursor()

    # Get counts by action type
    cursor.execute(
        """
        SELECT action_type, COUNT(*) as count
        FROM office_audit_log
        WHERE account_id = ? AND created_at >= ? AND created_at <= ?
        GROUP BY action_type
        """,
        (account_id, start_date.isoformat(), end_date.isoformat()),
    )
    by_type = {row["action_type"]: row["count"] for row in cursor.fetchall()}

    # Get counts by result
    cursor.execute(
        """
        SELECT result, COUNT(*) as count
        FROM office_audit_log
        WHERE account_id = ? AND created_at >= ? AND created_at <= ?
        GROUP BY result
        """,
        (account_id, start_date.isoformat(), end_date.isoformat()),
    )
    by_result = {row["result"]: row["count"] for row in cursor.fetchall()}

    # Get total
    cursor.execute(
        """
        SELECT COUNT(*) FROM office_audit_log
        WHERE account_id = ? AND created_at >= ? AND created_at <= ?
        """,
        (account_id, start_date.isoformat(), end_date.isoformat()),
    )
    total = cursor.fetchone()[0]

    conn.close()

    return {
        "success": True,
        "summary": {
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_actions": total,
            "by_type": by_type,
            "by_result": by_result,
            "undone_count": by_result.get("undone", 0),
        },
    }


async def mark_as_undone(
    log_id: str,
    undo_summary: str | None = None,
) -> dict[str, Any]:
    """
    Mark an audit log entry as undone.

    This is the only modification allowed to audit entries - marking
    the result as "undone" when a user reverses an action.

    Args:
        log_id: Audit log entry ID
        undo_summary: Optional additional summary for the undo

    Returns:
        {
            "success": bool,
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get existing entry
    cursor.execute(
        "SELECT * FROM office_audit_log WHERE id = ?",
        (log_id,),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"success": False, "error": f"Audit log entry not found: {log_id}"}

    # Update result to undone
    cursor.execute(
        "UPDATE office_audit_log SET result = 'undone' WHERE id = ?",
        (log_id,),
    )
    conn.commit()

    # Log the undo action itself
    entry = dict(row)
    account_id = entry["account_id"]

    await log_action(
        account_id=account_id,
        action_type="action_undo",
        action_summary=undo_summary or f"Undid action: {entry['action_summary']}",
        action_data={
            "original_action_id": log_id,
            "original_action_type": entry["action_type"],
            "original_action_summary": entry["action_summary"],
        },
        result="success",
        related_action_id=log_id,
    )

    conn.close()

    return {"success": True}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Office Audit Logger for Level 4+ Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List recent audit entries
  python audit_logger.py --account-id abc123 --list --limit 50

  # List entries for a specific action type
  python audit_logger.py --account-id abc123 --list --action-type email_send

  # Export audit log to CSV
  python audit_logger.py --account-id abc123 --export csv --output audit.csv

  # Get summary for the current week
  python audit_logger.py --account-id abc123 --summary week
        """,
    )

    parser.add_argument("--account-id", required=True, help="Office account ID")

    # Actions (mutually exclusive)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--list", action="store_true", help="List audit entries")
    actions.add_argument("--export", metavar="FORMAT", help="Export to format (csv or json)")
    actions.add_argument("--summary", metavar="PERIOD", help="Get summary for period (day, week, month)")
    actions.add_argument("--log", action="store_true", help="Log a new action (for testing)")

    # Filter arguments
    parser.add_argument("--action-type", help="Filter by action type")
    parser.add_argument("--start-date", help="Filter by start date (ISO format)")
    parser.add_argument("--end-date", help="Filter by end date (ISO format)")
    parser.add_argument("--result", help="Filter by result (success, failed, undone)")
    parser.add_argument("--limit", type=int, default=100, help="Max results for list")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--output", help="Output file path for export")

    # Log arguments (for testing)
    parser.add_argument("--type", help="Action type for --log")
    parser.add_argument("--summary-text", help="Action summary for --log")

    args = parser.parse_args()

    result = None

    if args.list:
        result = asyncio.run(
            get_audit_log(
                account_id=args.account_id,
                action_type=args.action_type,
                start_date=args.start_date,
                end_date=args.end_date,
                result=args.result,
                limit=args.limit,
                offset=args.offset,
            )
        )

    elif args.export:
        result = asyncio.run(
            export_audit_log(
                account_id=args.account_id,
                format=args.export,
                start_date=args.start_date,
                end_date=args.end_date,
                output_path=args.output,
            )
        )

    elif args.summary:
        result = asyncio.run(
            get_audit_summary(
                account_id=args.account_id,
                period=args.summary,
            )
        )

    elif args.log:
        if not args.type or not args.summary_text:
            print("Error: --type and --summary-text required for --log")
            sys.exit(1)

        result = asyncio.run(
            log_action(
                account_id=args.account_id,
                action_type=args.type,
                action_summary=args.summary_text,
                action_data={"test": True},
                result="success",
            )
        )

    if result:
        if result.get("success"):
            print("OK")
        else:
            print(f"ERROR: {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
