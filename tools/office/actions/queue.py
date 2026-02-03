"""
Tool: Action Queue Manager
Purpose: Queue actions with undo windows for Level 4+ Managed Proxy integration

ADHD users benefit from undo windows that provide time to reconsider impulsive
actions. This tool manages the action queue, allowing actions to be queued,
cancelled, expedited, and tracked.

Usage:
    # List pending actions
    python queue.py --account-id <id> --list-pending

    # Cancel an action
    python queue.py --account-id <id> --cancel <action-id>

    # Expedite an action (execute immediately)
    python queue.py --account-id <id> --expedite <action-id>

    # Get queue statistics
    python queue.py --account-id <id> --stats

Dependencies:
    - uuid (ID generation)
    - sqlite3 (database)
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection
from tools.office.actions import ActionStatus, ActionType, Priority


async def queue_action(
    account_id: str,
    action_type: str,
    action_data: dict[str, Any],
    undo_window_seconds: int = 60,
    priority: str = "normal",
    require_confirmation: bool = False,
) -> dict[str, Any]:
    """
    Queue an action for execution after the undo window expires.

    Args:
        account_id: Office account ID
        action_type: Type of action (from ActionType enum)
        action_data: Action-specific data (recipients, subject, etc.)
        undo_window_seconds: Seconds before action executes (default 60)
        priority: Action priority (low, normal, high)
        require_confirmation: If True, action won't execute until confirmed

    Returns:
        {
            "success": bool,
            "action_id": str,
            "undo_deadline": str (ISO format),
            "status": str,
            "priority": str,
            "require_confirmation": bool,
        }
    """
    # Validate action type
    if not ActionType.is_valid(action_type):
        return {
            "success": False,
            "error": f"Invalid action type: {action_type}. Valid types: {ActionType.values()}",
        }

    # Validate priority
    if priority not in Priority.values():
        return {
            "success": False,
            "error": f"Invalid priority: {priority}. Valid values: {Priority.values()}",
        }

    conn = get_connection()
    cursor = conn.cursor()

    # Check if account exists and has Level 4+ access
    cursor.execute(
        "SELECT id, integration_level FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    account = cursor.fetchone()

    if not account:
        conn.close()
        return {"success": False, "error": f"Account not found: {account_id}"}

    # Verify account has Level 4+ access
    if account["integration_level"] < 4:
        conn.close()
        return {
            "success": False,
            "error": f"Action queue requires Level 4+. Current level: {account['integration_level']}",
        }

    # Generate action ID and calculate deadline
    action_id = str(uuid.uuid4())
    now = datetime.now()
    undo_deadline = now + timedelta(seconds=undo_window_seconds)

    # Store priority and confirmation requirement in action_data
    extended_data = {
        **action_data,
        "_priority": priority,
        "_require_confirmation": require_confirmation,
    }

    # Insert action into queue
    cursor.execute(
        """
        INSERT INTO office_actions (
            id, account_id, action_type, action_data,
            status, undo_deadline, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action_id,
            account_id,
            action_type,
            json.dumps(extended_data),
            ActionStatus.PENDING.value,
            undo_deadline.isoformat(),
            now.isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "action_id": action_id,
        "undo_deadline": undo_deadline.isoformat(),
        "status": ActionStatus.PENDING.value,
        "priority": priority,
        "require_confirmation": require_confirmation,
    }


async def get_pending_actions(
    account_id: str,
    action_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Get pending actions for an account.

    Args:
        account_id: Office account ID
        action_type: Optional filter by action type
        limit: Maximum number of actions to return

    Returns:
        {
            "success": bool,
            "actions": list[dict],
            "total": int,
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Build query
    query = """
        SELECT * FROM office_actions
        WHERE account_id = ? AND status = 'pending'
    """
    params: list[Any] = [account_id]

    if action_type:
        query += " AND action_type = ?"
        params.append(action_type)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # Get total count (without limit)
    count_query = """
        SELECT COUNT(*) FROM office_actions
        WHERE account_id = ? AND status = 'pending'
    """
    count_params: list[Any] = [account_id]
    if action_type:
        count_query += " AND action_type = ?"
        count_params.append(action_type)

    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]
    conn.close()

    actions = []
    for row in rows:
        action = dict(row)
        if action.get("action_data"):
            action["action_data"] = json.loads(action["action_data"])
        actions.append(action)

    return {
        "success": True,
        "actions": actions,
        "total": total,
    }


async def get_action(action_id: str) -> dict[str, Any]:
    """
    Get a single action by ID.

    Args:
        action_id: Action ID

    Returns:
        {
            "success": bool,
            "action": dict,
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM office_actions WHERE id = ?",
        (action_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": f"Action not found: {action_id}"}

    action = dict(row)
    if action.get("action_data"):
        action["action_data"] = json.loads(action["action_data"])

    return {"success": True, "action": action}


async def cancel_action(
    action_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """
    Cancel a pending action (undo before execution).

    Args:
        action_id: Action ID to cancel
        reason: Optional reason for cancellation

    Returns:
        {
            "success": bool,
            "status": str,
            "message": str,
        }
    """
    # Get action first
    result = await get_action(action_id)
    if not result.get("success"):
        return result

    action = result["action"]

    if action["status"] != "pending":
        return {
            "success": False,
            "error": f"Cannot cancel action with status: {action['status']}",
        }

    # Check if still within undo window
    undo_deadline = datetime.fromisoformat(action["undo_deadline"])
    if datetime.now() > undo_deadline:
        return {
            "success": False,
            "error": "Undo window has expired. Action may have already executed.",
        }

    conn = get_connection()
    cursor = conn.cursor()

    # Store reason in action_data if provided
    if reason:
        action_data = action.get("action_data", {})
        action_data["_cancel_reason"] = reason
        cursor.execute(
            """
            UPDATE office_actions
            SET status = ?, action_data = ?
            WHERE id = ?
            """,
            (ActionStatus.UNDONE.value, json.dumps(action_data), action_id),
        )
    else:
        cursor.execute(
            """
            UPDATE office_actions
            SET status = ?
            WHERE id = ?
            """,
            (ActionStatus.UNDONE.value, action_id),
        )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "status": ActionStatus.UNDONE.value,
        "message": f"Action {action_id} cancelled successfully",
    }


async def expedite_action(action_id: str) -> dict[str, Any]:
    """
    Expedite an action (execute immediately, bypassing undo window).

    This sets the undo_deadline to now, making the action eligible for
    immediate execution by the executor.

    Args:
        action_id: Action ID to expedite

    Returns:
        {
            "success": bool,
            "message": str,
            "action_id": str,
        }
    """
    # Get action first
    result = await get_action(action_id)
    if not result.get("success"):
        return result

    action = result["action"]

    if action["status"] != "pending":
        return {
            "success": False,
            "error": f"Cannot expedite action with status: {action['status']}",
        }

    conn = get_connection()
    cursor = conn.cursor()

    # Set undo deadline to now (makes it eligible for immediate execution)
    cursor.execute(
        """
        UPDATE office_actions
        SET undo_deadline = ?
        WHERE id = ?
        """,
        (datetime.now().isoformat(), action_id),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Action {action_id} expedited for immediate execution",
        "action_id": action_id,
    }


async def get_queue_stats(account_id: str) -> dict[str, Any]:
    """
    Get action queue statistics for an account.

    Args:
        account_id: Office account ID

    Returns:
        {
            "success": bool,
            "pending_count": int,
            "executed_today": int,
            "undone_today": int,
            "expired_today": int,
            "failed_today": int,
            "by_type": dict[str, int],
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Pending count
    cursor.execute(
        "SELECT COUNT(*) FROM office_actions WHERE account_id = ? AND status = 'pending'",
        (account_id,),
    )
    pending_count = cursor.fetchone()[0]

    # Executed today
    cursor.execute(
        """
        SELECT COUNT(*) FROM office_actions
        WHERE account_id = ? AND status = 'executed' AND executed_at >= ?
        """,
        (account_id, today_start.isoformat()),
    )
    executed_today = cursor.fetchone()[0]

    # Undone today
    cursor.execute(
        """
        SELECT COUNT(*) FROM office_actions
        WHERE account_id = ? AND status = 'undone' AND created_at >= ?
        """,
        (account_id, today_start.isoformat()),
    )
    undone_today = cursor.fetchone()[0]

    # Expired today
    cursor.execute(
        """
        SELECT COUNT(*) FROM office_actions
        WHERE account_id = ? AND status = 'expired' AND created_at >= ?
        """,
        (account_id, today_start.isoformat()),
    )
    expired_today = cursor.fetchone()[0]

    # Failed today
    cursor.execute(
        """
        SELECT COUNT(*) FROM office_actions
        WHERE account_id = ? AND status = 'failed' AND created_at >= ?
        """,
        (account_id, today_start.isoformat()),
    )
    failed_today = cursor.fetchone()[0]

    # By type (pending only)
    cursor.execute(
        """
        SELECT action_type, COUNT(*) as count
        FROM office_actions
        WHERE account_id = ? AND status = 'pending'
        GROUP BY action_type
        """,
        (account_id,),
    )
    by_type = {row["action_type"]: row["count"] for row in cursor.fetchall()}

    conn.close()

    return {
        "success": True,
        "pending_count": pending_count,
        "executed_today": executed_today,
        "undone_today": undone_today,
        "expired_today": expired_today,
        "failed_today": failed_today,
        "by_type": by_type,
    }


async def get_actions_ready_for_execution(limit: int = 100) -> dict[str, Any]:
    """
    Get all pending actions that have passed their undo deadline.

    This is used by the executor to find actions ready to execute.

    Args:
        limit: Maximum number of actions to return

    Returns:
        {
            "success": bool,
            "actions": list[dict],
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute(
        """
        SELECT * FROM office_actions
        WHERE status = 'pending' AND undo_deadline <= ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (now, limit),
    )
    rows = cursor.fetchall()
    conn.close()

    actions = []
    for row in rows:
        action = dict(row)
        if action.get("action_data"):
            action["action_data"] = json.loads(action["action_data"])
        actions.append(action)

    return {"success": True, "actions": actions}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Action Queue Manager for Level 4+ Office Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List pending actions
  python queue.py --account-id abc123 --list-pending

  # Cancel an action
  python queue.py --account-id abc123 --cancel action-id-here

  # Expedite an action
  python queue.py --account-id abc123 --expedite action-id-here

  # Get queue stats
  python queue.py --account-id abc123 --stats
        """,
    )

    parser.add_argument("--account-id", required=True, help="Office account ID")

    # Actions (mutually exclusive)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--list-pending", action="store_true", help="List pending actions"
    )
    actions.add_argument("--cancel", metavar="ACTION_ID", help="Cancel an action")
    actions.add_argument("--expedite", metavar="ACTION_ID", help="Expedite an action")
    actions.add_argument("--stats", action="store_true", help="Get queue statistics")
    actions.add_argument("--get", metavar="ACTION_ID", help="Get action details")

    # Optional filters
    parser.add_argument("--type", help="Filter by action type")
    parser.add_argument("--limit", type=int, default=50, help="Max results for list")
    parser.add_argument("--reason", default="", help="Reason for cancel")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    result = None

    if args.list_pending:
        result = asyncio.run(
            get_pending_actions(
                account_id=args.account_id,
                action_type=args.type,
                limit=args.limit,
            )
        )
    elif args.cancel:
        result = asyncio.run(
            cancel_action(
                action_id=args.cancel,
                reason=args.reason,
            )
        )
    elif args.expedite:
        result = asyncio.run(expedite_action(action_id=args.expedite))
    elif args.stats:
        result = asyncio.run(get_queue_stats(account_id=args.account_id))
    elif args.get:
        result = asyncio.run(get_action(action_id=args.get))

    if result:
        if result.get("success"):
            print("OK")
        else:
            print(f"ERROR: {result.get('error')}")
            sys.exit(1)

        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            # Human-readable output
            if args.list_pending:
                actions_list = result.get("actions", [])
                print(f"Pending actions: {result.get('total', len(actions_list))}")
                for action in actions_list:
                    deadline = action.get("undo_deadline", "N/A")
                    print(
                        f"  [{action['id'][:8]}] {action['action_type']} "
                        f"(deadline: {deadline})"
                    )
            elif args.stats:
                print(f"Pending: {result.get('pending_count', 0)}")
                print(f"Executed today: {result.get('executed_today', 0)}")
                print(f"Undone today: {result.get('undone_today', 0)}")
                print(f"Expired today: {result.get('expired_today', 0)}")
                print(f"Failed today: {result.get('failed_today', 0)}")
                if result.get("by_type"):
                    print("By type:")
                    for action_type, count in result["by_type"].items():
                        print(f"  {action_type}: {count}")
            else:
                print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
