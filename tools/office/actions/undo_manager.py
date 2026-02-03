"""
Tool: Undo Manager
Purpose: Manage undo windows and handle undo requests for office actions

Provides undo functionality for Level 4+ (Managed Proxy) operations.
Actions are queued with configurable undo windows based on action type
and sentiment analysis.

Usage:
    from tools.office.actions.undo_manager import (
        undo_action,
        extend_undo_window,
        get_undoable_actions,
        calculate_undo_deadline,
    )

    # Calculate deadline for new action
    deadline = await calculate_undo_deadline("send_email", sentiment_score=0.8)

    # Undo an action
    result = await undo_action("action-123")

    # Extend undo window
    result = await extend_undo_window("action-123", additional_seconds=30)
"""

import argparse
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from tools.office import get_connection
from tools.office.models import OfficeAction

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "args"

# Default undo windows (seconds) - can be overridden by config
DEFAULT_UNDO_WINDOWS = {
    "send_email": 60,
    "send_email_high_sentiment": 300,
    "delete_email": 30,
    "archive_email": 15,
    "schedule_meeting": 60,
    "cancel_meeting": 60,
    "update_meeting": 60,
    "create_draft": 30,
    "update_draft": 30,
    "delete_draft": 15,
    "mark_read": 10,
    "mark_unread": 10,
    "star_email": 10,
    "unstar_email": 10,
}

# Sentiment threshold for extended undo window
HIGH_SENTIMENT_THRESHOLD = 0.7


def load_undo_config() -> dict[str, int]:
    """
    Load undo window configuration from args/office_integration.yaml.

    Returns:
        dict mapping action types to undo window seconds
    """
    config_file = CONFIG_PATH / "office_integration.yaml"

    if not config_file.exists():
        return DEFAULT_UNDO_WINDOWS.copy()

    with open(config_file) as f:
        config = yaml.safe_load(f)

    # Get undo windows from config, falling back to defaults
    undo_config = DEFAULT_UNDO_WINDOWS.copy()

    office_config = config.get("office_integration", {})
    adhd_config = office_config.get("adhd", {})

    # Override default undo window if specified
    default_window = adhd_config.get("undo_window_seconds")
    if default_window:
        undo_config["send_email"] = default_window
        undo_config["schedule_meeting"] = default_window
        undo_config["cancel_meeting"] = default_window

    return undo_config


async def calculate_undo_deadline(
    action_type: str,
    sentiment_score: float | None = None,
) -> datetime:
    """
    Calculate the undo deadline for an action.

    Uses configurable windows based on action type and sentiment analysis.
    High sentiment (>0.7) emails get extended windows for impulsivity protection.

    Args:
        action_type: Type of action (send_email, delete_email, etc.)
        sentiment_score: Optional sentiment score (0.0-1.0) from analysis

    Returns:
        datetime when the undo window expires
    """
    undo_config = load_undo_config()

    # Determine appropriate window
    if action_type == "send_email" and sentiment_score is not None:
        if sentiment_score > HIGH_SENTIMENT_THRESHOLD:
            window_seconds = undo_config.get(
                "send_email_high_sentiment",
                DEFAULT_UNDO_WINDOWS["send_email_high_sentiment"],
            )
        else:
            window_seconds = undo_config.get(
                action_type,
                DEFAULT_UNDO_WINDOWS.get(action_type, 60),
            )
    else:
        window_seconds = undo_config.get(
            action_type,
            DEFAULT_UNDO_WINDOWS.get(action_type, 60),
        )

    return datetime.now() + timedelta(seconds=window_seconds)


async def undo_action(action_id: str) -> dict[str, Any]:
    """
    Undo a queued action if still within the undo window.

    Args:
        action_id: ID of the action to undo

    Returns:
        dict with success status and updated status
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get the action
    cursor.execute(
        "SELECT * FROM office_actions WHERE id = ?",
        (action_id,),
    )
    row = cursor.fetchone()

    if not row:
        return {"success": False, "error": f"Action {action_id} not found"}

    action = OfficeAction.from_dict(dict(row))

    # Check if action can be undone
    if action.status != "pending":
        return {
            "success": False,
            "error": f"Action cannot be undone - status is '{action.status}'",
        }

    if not action.can_undo():
        return {
            "success": False,
            "error": "Undo window has expired",
        }

    # Mark as undone
    cursor.execute(
        "UPDATE office_actions SET status = ? WHERE id = ?",
        ("undone", action_id),
    )
    conn.commit()

    # Log the undo to audit trail
    audit_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO office_audit_log (id, account_id, action_type, action_summary, action_data, result)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            audit_id,
            action.account_id,
            f"undo_{action.action_type}",
            f"Undid {action.action_type} action",
            json.dumps(action.action_data),
            json.dumps({"status": "undone", "original_action_id": action_id}),
        ),
    )
    conn.commit()

    return {
        "success": True,
        "status": "undone",
        "action_id": action_id,
        "action_type": action.action_type,
    }


async def extend_undo_window(
    action_id: str,
    additional_seconds: int = 30,
) -> dict[str, Any]:
    """
    Extend the undo window for an action.

    Allows users more time to decide on an action. Useful for
    cases where they need more time to think.

    Args:
        action_id: ID of the action to extend
        additional_seconds: Seconds to add to the undo window (default 30)

    Returns:
        dict with success status and new deadline
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get the action
    cursor.execute(
        "SELECT * FROM office_actions WHERE id = ?",
        (action_id,),
    )
    row = cursor.fetchone()

    if not row:
        return {"success": False, "error": f"Action {action_id} not found"}

    action = OfficeAction.from_dict(dict(row))

    # Check if action can be extended
    if action.status != "pending":
        return {
            "success": False,
            "error": f"Cannot extend - action status is '{action.status}'",
        }

    if not action.undo_deadline:
        return {
            "success": False,
            "error": "Action has no undo deadline",
        }

    # Calculate new deadline
    new_deadline = action.undo_deadline + timedelta(seconds=additional_seconds)

    # Update the deadline
    cursor.execute(
        "UPDATE office_actions SET undo_deadline = ? WHERE id = ?",
        (new_deadline.isoformat(), action_id),
    )
    conn.commit()

    return {
        "success": True,
        "action_id": action_id,
        "new_deadline": new_deadline.isoformat(),
        "extended_by_seconds": additional_seconds,
    }


async def get_undoable_actions(account_id: str) -> dict[str, Any]:
    """
    Get all actions that are still within their undo window.

    Args:
        account_id: Account ID to filter by

    Returns:
        dict with list of undoable actions and count
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute(
        """
        SELECT * FROM office_actions
        WHERE account_id = ?
          AND status = 'pending'
          AND undo_deadline > ?
        ORDER BY created_at DESC
        """,
        (account_id, now),
    )
    rows = cursor.fetchall()

    actions = []
    for row in rows:
        action = OfficeAction.from_dict(dict(row))
        remaining = (action.undo_deadline - datetime.now()).total_seconds()
        actions.append({
            "id": action.id,
            "action_type": action.action_type,
            "created_at": action.created_at.isoformat(),
            "undo_deadline": action.undo_deadline.isoformat(),
            "remaining_seconds": max(0, int(remaining)),
            "action_summary": _summarize_action(action),
        })

    return {
        "success": True,
        "actions": actions,
        "count": len(actions),
    }


def _summarize_action(action: OfficeAction) -> str:
    """Create a human-readable summary of an action."""
    data = action.action_data

    if action.action_type == "send_email":
        to = data.get("to", [])
        subject = data.get("subject", "")
        if isinstance(to, list):
            to = ", ".join(to[:2])
            if len(data.get("to", [])) > 2:
                to += f" +{len(data['to']) - 2} more"
        return f"Send email to {to}: {subject[:50]}"

    if action.action_type == "delete_email":
        return f"Delete email: {data.get('subject', 'Unknown')[:50]}"

    if action.action_type == "archive_email":
        return f"Archive email: {data.get('subject', 'Unknown')[:50]}"

    if action.action_type == "schedule_meeting":
        title = data.get("title", "Untitled")
        start = data.get("start_time", "")
        return f"Schedule meeting: {title[:30]} at {start}"

    if action.action_type == "cancel_meeting":
        return f"Cancel meeting: {data.get('title', 'Unknown')[:30]}"

    return f"{action.action_type}: {str(data)[:50]}"


async def create_action(
    account_id: str,
    action_type: str,
    action_data: dict[str, Any],
    sentiment_score: float | None = None,
) -> dict[str, Any]:
    """
    Create a new queued action with an undo window.

    Args:
        account_id: Account ID for the action
        action_type: Type of action (send_email, delete_email, etc.)
        action_data: Data needed to execute the action
        sentiment_score: Optional sentiment score for email actions

    Returns:
        dict with action ID and undo deadline
    """
    action_id = str(uuid.uuid4())
    undo_deadline = await calculate_undo_deadline(action_type, sentiment_score)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO office_actions (id, account_id, action_type, action_data, status, undo_deadline)
        VALUES (?, ?, ?, ?, 'pending', ?)
        """,
        (
            action_id,
            account_id,
            action_type,
            json.dumps(action_data),
            undo_deadline.isoformat(),
        ),
    )
    conn.commit()

    return {
        "success": True,
        "action_id": action_id,
        "undo_deadline": undo_deadline.isoformat(),
        "window_seconds": int((undo_deadline - datetime.now()).total_seconds()),
    }


def main() -> None:
    """CLI entry point for testing undo manager."""
    parser = argparse.ArgumentParser(description="Undo Manager for Office Actions")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # undo command
    undo_parser = subparsers.add_parser("undo", help="Undo an action")
    undo_parser.add_argument("action_id", help="Action ID to undo")

    # extend command
    extend_parser = subparsers.add_parser("extend", help="Extend undo window")
    extend_parser.add_argument("action_id", help="Action ID to extend")
    extend_parser.add_argument(
        "--seconds",
        type=int,
        default=30,
        help="Additional seconds (default: 30)",
    )

    # list command
    list_parser = subparsers.add_parser("list", help="List undoable actions")
    list_parser.add_argument("account_id", help="Account ID to list actions for")

    # create command (for testing)
    create_parser = subparsers.add_parser("create", help="Create a test action")
    create_parser.add_argument("account_id", help="Account ID")
    create_parser.add_argument("action_type", help="Action type")
    create_parser.add_argument(
        "--data",
        type=str,
        default="{}",
        help="Action data as JSON",
    )
    create_parser.add_argument(
        "--sentiment",
        type=float,
        help="Sentiment score (0.0-1.0)",
    )

    args = parser.parse_args()

    if args.command == "undo":
        result = asyncio.run(undo_action(args.action_id))
        print(json.dumps(result, indent=2))

    elif args.command == "extend":
        result = asyncio.run(extend_undo_window(args.action_id, args.seconds))
        print(json.dumps(result, indent=2))

    elif args.command == "list":
        result = asyncio.run(get_undoable_actions(args.account_id))
        print(json.dumps(result, indent=2))

    elif args.command == "create":
        data = json.loads(args.data)
        result = asyncio.run(
            create_action(args.account_id, args.action_type, data, args.sentiment)
        )
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
