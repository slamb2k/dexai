"""
Tool: Inbox Processor
Purpose: Process incoming emails against policies for Level 5 (Autonomous) integration

This module processes incoming emails against user-defined policies, executing
matching actions automatically. It supports batch processing and a background
watcher for real-time processing.

ADHD Philosophy:
    Inbox processing removes the cognitive burden of email triage. Users define
    policies once, and Dex handles routine emails automatically. VIP contacts
    always break through, and emergency pause stops everything instantly.

Processing Flow:
    1. New email arrives (via polling or webhook)
    2. Check emergency pause status
    3. Check if sender is VIP (special handling)
    4. Evaluate inbox policies
    5. Execute matching actions via action queue
    6. Log policy execution

Usage:
    from tools.office.automation.inbox_processor import (
        process_email,
        process_inbox_batch,
        start_inbox_watcher,
        stop_inbox_watcher,
    )

    # Process a single email
    result = await process_email("account-123", email_data)

    # Process batch of emails
    result = await process_inbox_batch("account-123", since=yesterday, limit=100)

    # Start background watcher
    await start_inbox_watcher("account-123")

CLI:
    python tools/office/automation/inbox_processor.py process <account-id> --email-id <id>
    python tools/office/automation/inbox_processor.py batch <account-id> --limit 50
    python tools/office/automation/inbox_processor.py start-watcher <account-id>
    python tools/office/automation/inbox_processor.py stop-watcher <account-id>
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
from tools.office.automation.emergency import check_pause_status
from tools.office.models import Email, IntegrationLevel
from tools.office.policies import (
    ActionType,
    Policy,
    PolicyAction,
    PolicyType,
    ensure_policy_tables,
)
from tools.office.policies.matcher import (
    match_all_conditions,
    prepare_email_event_data,
)

# Global registry for active inbox watchers
_active_watchers: dict[str, asyncio.Task] = {}


def _ensure_tables() -> None:
    """Ensure all required tables exist."""
    ensure_policy_tables()


def _get_account(account_id: str) -> dict | None:
    """Get account details from database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def _get_enabled_policies(account_id: str, policy_type: str) -> list[Policy]:
    """
    Get enabled policies for an account, sorted by priority.

    Args:
        account_id: Account ID
        policy_type: Type of policies to retrieve

    Returns:
        List of Policy objects, sorted by priority (highest first)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM office_policies
        WHERE account_id = ? AND policy_type = ? AND enabled = TRUE
        ORDER BY priority DESC, created_at ASC
        """,
        (account_id, policy_type),
    )
    rows = cursor.fetchall()
    conn.close()

    policies = []
    for row in rows:
        try:
            policy_data = dict(row)
            policy = Policy.from_dict(policy_data)
            policies.append(policy)
        except Exception:
            # Skip malformed policies
            continue

    return policies


def _is_vip(account_id: str, email_address: str) -> dict[str, Any] | None:
    """
    Check if an email address is a VIP contact.

    Args:
        account_id: Account ID
        email_address: Email address to check

    Returns:
        VIP contact data if VIP, None otherwise
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM office_vip_contacts
        WHERE account_id = ? AND LOWER(email) = LOWER(?)
        """,
        (account_id, email_address),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def _log_policy_execution(
    account_id: str,
    policy_id: str,
    trigger_type: str,
    trigger_data: dict[str, Any],
    actions_taken: list[dict[str, Any]],
    result: str = "success",
) -> str:
    """
    Log a policy execution event.

    Args:
        account_id: Account ID
        policy_id: Policy that was executed
        trigger_type: Type of trigger (email, calendar, etc.)
        trigger_data: Data that triggered the policy
        actions_taken: List of actions that were taken
        result: Execution result (success, failed, skipped)

    Returns:
        Execution log ID
    """
    _ensure_tables()
    conn = get_connection()
    cursor = conn.cursor()

    execution_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO office_policy_executions
        (id, account_id, policy_id, trigger_type, trigger_data, actions_taken, result)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            execution_id,
            account_id,
            policy_id,
            trigger_type,
            json.dumps(trigger_data),
            json.dumps(actions_taken),
            result,
        ),
    )
    conn.commit()
    conn.close()

    return execution_id


async def _execute_email_action(
    account_id: str,
    action: PolicyAction,
    email_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute a single policy action on an email.

    Args:
        account_id: Account ID
        action: Action to execute
        email_data: Email data dictionary

    Returns:
        Execution result
    """
    # Import here to avoid circular imports
    from tools.office.actions.queue import queue_action

    action_type = action.action_type
    message_id = email_data.get("message_id", email_data.get("id"))

    if action_type == ActionType.ARCHIVE:
        return await queue_action(
            account_id=account_id,
            action_type="archive_email",
            action_data={"message_id": message_id},
            undo_window_seconds=60,
        )

    if action_type == ActionType.DELETE:
        return await queue_action(
            account_id=account_id,
            action_type="delete_email",
            action_data={"message_id": message_id, "permanent": False},
            undo_window_seconds=60,
        )

    if action_type == ActionType.MARK_READ:
        return await queue_action(
            account_id=account_id,
            action_type="mark_read",
            action_data={"message_id": message_id},
            undo_window_seconds=30,
        )

    if action_type == ActionType.STAR:
        return await queue_action(
            account_id=account_id,
            action_type="star_email",
            action_data={"message_id": message_id},
            undo_window_seconds=30,
        )

    if action_type == ActionType.LABEL:
        label = action.parameters.get("label", "")
        return await queue_action(
            account_id=account_id,
            action_type="label_email",
            action_data={"message_id": message_id, "label": label},
            undo_window_seconds=30,
        )

    if action_type == ActionType.FORWARD:
        forward_to = action.parameters.get("to", "")
        return await queue_action(
            account_id=account_id,
            action_type="forward_email",
            action_data={
                "message_id": message_id,
                "forward_to": forward_to,
            },
            undo_window_seconds=60,
        )

    if action_type == ActionType.AUTO_REPLY:
        template_id = action.parameters.get("template_id")
        return await queue_action(
            account_id=account_id,
            action_type="auto_reply",
            action_data={
                "message_id": message_id,
                "template_id": template_id,
                "reply_to": email_data.get("from_address"),
            },
            undo_window_seconds=60,
        )

    if action_type == ActionType.NOTIFY_IMMEDIATELY:
        # This would trigger immediate notification through notification system
        return {"success": True, "action": "notify_immediately", "queued": False}

    if action_type == ActionType.NOTIFY_DIGEST:
        # This would add to daily digest
        return {"success": True, "action": "notify_digest", "queued": False}

    if action_type == ActionType.SUPPRESS_NOTIFICATION:
        # This suppresses notifications for this email
        return {"success": True, "action": "suppress_notification", "queued": False}

    if action_type == ActionType.IGNORE_FLOW_STATE:
        # This is a modifier action, not an executable action
        return {"success": True, "action": "ignore_flow_state", "queued": False}

    if action_type == ActionType.ESCALATE_TO_USER:
        # This escalates to user for manual handling
        return {"success": True, "action": "escalate", "queued": False}

    return {"success": False, "error": f"Unknown action type: {action_type}"}


async def process_email(
    account_id: str,
    email: dict[str, Any] | Email,
) -> dict[str, Any]:
    """
    Process an incoming email against policies.

    This is the main entry point for email processing. It evaluates all
    applicable policies and executes matching actions.

    Args:
        account_id: Office account ID
        email: Email data (dict or Email object)

    Returns:
        {
            "processed": bool,
            "actions_taken": list,
            "policy_id": str | None,
            "is_vip": bool,
            "skipped_reason": str | None,
        }
    """
    # Check emergency pause
    if check_pause_status(account_id):
        return {
            "processed": False,
            "actions_taken": [],
            "policy_id": None,
            "is_vip": False,
            "skipped_reason": "Automation paused",
        }

    # Get account and verify level
    account = _get_account(account_id)
    if not account:
        return {
            "processed": False,
            "actions_taken": [],
            "policy_id": None,
            "is_vip": False,
            "skipped_reason": "Account not found",
        }

    if account["integration_level"] < IntegrationLevel.AUTONOMOUS.value:
        return {
            "processed": False,
            "actions_taken": [],
            "policy_id": None,
            "is_vip": False,
            "skipped_reason": f"Requires Level 5. Current: {account['integration_level']}",
        }

    # Convert to dict if Email object
    if isinstance(email, Email):
        email_data = email.to_dict()
    else:
        email_data = email

    # Prepare event data for matching
    event_data = prepare_email_event_data(email_data)

    # Check VIP status
    sender_address = event_data.get("from_address", "")
    vip_info = _is_vip(account_id, sender_address)
    is_vip = vip_info is not None

    if is_vip:
        # VIP emails get special handling
        actions_taken = []

        if vip_info.get("always_notify", True):
            actions_taken.append({
                "action": "notify_immediately",
                "reason": "VIP contact",
            })

        # Log the VIP handling
        _log_policy_execution(
            account_id=account_id,
            policy_id="vip_handler",
            trigger_type="email",
            trigger_data={"message_id": email_data.get("message_id"), "sender": sender_address},
            actions_taken=actions_taken,
            result="success",
        )

        return {
            "processed": True,
            "actions_taken": actions_taken,
            "policy_id": "vip_handler",
            "is_vip": True,
            "skipped_reason": None,
        }

    # Get applicable policies
    policies = _get_enabled_policies(account_id, PolicyType.INBOX.value)

    if not policies:
        return {
            "processed": False,
            "actions_taken": [],
            "policy_id": None,
            "is_vip": False,
            "skipped_reason": "No matching policies",
        }

    # Evaluate policies in priority order
    matched_policy: Policy | None = None
    for policy in policies:
        if match_all_conditions(policy.conditions, event_data, account_id):
            matched_policy = policy
            break

    if not matched_policy:
        return {
            "processed": False,
            "actions_taken": [],
            "policy_id": None,
            "is_vip": False,
            "skipped_reason": "No policy conditions matched",
        }

    # Execute actions
    actions_taken = []
    for action in matched_policy.actions:
        result = await _execute_email_action(account_id, action, email_data)
        actions_taken.append({
            "action": action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type),
            "success": result.get("success", False),
            "action_id": result.get("action_id"),
            "error": result.get("error"),
        })

    # Log the execution
    _log_policy_execution(
        account_id=account_id,
        policy_id=matched_policy.id,
        trigger_type="email",
        trigger_data={"message_id": email_data.get("message_id"), "subject": email_data.get("subject")},
        actions_taken=actions_taken,
        result="success" if all(a.get("success") for a in actions_taken) else "partial",
    )

    return {
        "processed": True,
        "actions_taken": actions_taken,
        "policy_id": matched_policy.id,
        "is_vip": False,
        "skipped_reason": None,
    }


async def process_inbox_batch(
    account_id: str,
    since: datetime | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Process a batch of emails from the inbox.

    Args:
        account_id: Office account ID
        since: Only process emails received after this time (default: 24 hours ago)
        limit: Maximum number of emails to process

    Returns:
        {
            "processed": int,
            "actions": int,
            "skipped": int,
            "errors": int,
            "details": list,
        }
    """
    # Import email reader
    from tools.office.email.reader import list_emails

    # Check emergency pause
    if check_pause_status(account_id):
        return {
            "processed": 0,
            "actions": 0,
            "skipped": limit,
            "errors": 0,
            "details": [],
            "error": "Automation paused",
        }

    # Get account
    account = _get_account(account_id)
    if not account:
        return {
            "processed": 0,
            "actions": 0,
            "skipped": 0,
            "errors": 1,
            "details": [],
            "error": "Account not found",
        }

    if account["integration_level"] < IntegrationLevel.AUTONOMOUS.value:
        return {
            "processed": 0,
            "actions": 0,
            "skipped": 0,
            "errors": 1,
            "details": [],
            "error": f"Requires Level 5. Current: {account['integration_level']}",
        }

    # Default to last 24 hours
    if since is None:
        since = datetime.now() - timedelta(hours=24)

    # Get emails
    emails_result = await list_emails(account_id, limit=limit, unread_only=True)

    if not emails_result.get("success"):
        return {
            "processed": 0,
            "actions": 0,
            "skipped": 0,
            "errors": 1,
            "details": [],
            "error": emails_result.get("error", "Failed to fetch emails"),
        }

    emails = emails_result.get("emails", [])

    # Process each email
    processed = 0
    total_actions = 0
    skipped = 0
    errors = 0
    details = []

    for email in emails:
        # Filter by time
        received_at = email.received_at if isinstance(email, Email) else email.get("received_at")
        if isinstance(received_at, str):
            received_at = datetime.fromisoformat(received_at)

        if received_at and received_at < since:
            skipped += 1
            continue

        # Process the email
        result = await process_email(account_id, email)

        if result.get("processed"):
            processed += 1
            total_actions += len(result.get("actions_taken", []))
        elif result.get("skipped_reason"):
            skipped += 1
        else:
            errors += 1

        details.append({
            "message_id": email.message_id if isinstance(email, Email) else email.get("message_id"),
            "result": result,
        })

        # Check pause status periodically
        if (processed + skipped) % 10 == 0:
            if check_pause_status(account_id):
                break

    return {
        "processed": processed,
        "actions": total_actions,
        "skipped": skipped,
        "errors": errors,
        "details": details,
    }


async def _inbox_watcher_loop(account_id: str, poll_interval: int = 60) -> None:
    """
    Background loop for watching inbox.

    Args:
        account_id: Account ID to watch
        poll_interval: Seconds between polls
    """
    last_check = datetime.now()

    while True:
        # Check if we should stop
        if account_id not in _active_watchers:
            break

        # Check emergency pause
        if check_pause_status(account_id):
            await asyncio.sleep(poll_interval)
            continue

        # Process new emails since last check
        result = await process_inbox_batch(
            account_id=account_id,
            since=last_check,
            limit=50,
        )

        last_check = datetime.now()

        # Log activity if any processing happened
        if result.get("processed", 0) > 0:
            # Could log to activity system here
            pass

        # Wait for next poll
        await asyncio.sleep(poll_interval)


async def start_inbox_watcher(account_id: str, poll_interval: int = 60) -> None:
    """
    Start a background inbox watcher for an account.

    The watcher polls for new emails and processes them automatically.
    Only one watcher can be active per account.

    Args:
        account_id: Account ID to watch
        poll_interval: Seconds between polls (default: 60)
    """
    # Stop existing watcher if any
    await stop_inbox_watcher(account_id)

    # Start new watcher
    task = asyncio.create_task(_inbox_watcher_loop(account_id, poll_interval))
    _active_watchers[account_id] = task


async def stop_inbox_watcher(account_id: str) -> None:
    """
    Stop the inbox watcher for an account.

    Args:
        account_id: Account ID to stop watching
    """
    if account_id in _active_watchers:
        task = _active_watchers.pop(account_id)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def is_watcher_active(account_id: str) -> bool:
    """
    Check if an inbox watcher is active for an account.

    Args:
        account_id: Account ID to check

    Returns:
        True if watcher is active
    """
    if account_id not in _active_watchers:
        return False
    return not _active_watchers[account_id].done()


def main() -> None:
    """CLI entry point for inbox processor."""
    parser = argparse.ArgumentParser(
        description="Inbox Processor for Level 5 Office Integration"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # process command
    process_parser = subparsers.add_parser("process", help="Process a single email")
    process_parser.add_argument("account_id", help="Account ID")
    process_parser.add_argument("--email-id", required=True, help="Email message ID")

    # batch command
    batch_parser = subparsers.add_parser("batch", help="Process batch of emails")
    batch_parser.add_argument("account_id", help="Account ID")
    batch_parser.add_argument("--limit", type=int, default=100, help="Maximum emails")
    batch_parser.add_argument("--hours", type=int, default=24, help="Hours to look back")

    # start-watcher command
    start_parser = subparsers.add_parser("start-watcher", help="Start inbox watcher")
    start_parser.add_argument("account_id", help="Account ID")
    start_parser.add_argument("--interval", type=int, default=60, help="Poll interval (seconds)")

    # stop-watcher command
    stop_parser = subparsers.add_parser("stop-watcher", help="Stop inbox watcher")
    stop_parser.add_argument("account_id", help="Account ID")

    # status command
    status_parser = subparsers.add_parser("status", help="Check watcher status")
    status_parser.add_argument("account_id", help="Account ID")

    args = parser.parse_args()

    if args.command == "process":
        # Need to fetch the email first
        from tools.office.email.reader import read_email

        email_result = asyncio.run(read_email(args.account_id, args.email_id))
        if not email_result.get("success"):
            print(f"Error: {email_result.get('error')}")
            sys.exit(1)

        result = asyncio.run(process_email(args.account_id, email_result["email"]))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "batch":
        since = datetime.now() - timedelta(hours=args.hours)
        result = asyncio.run(process_inbox_batch(
            args.account_id,
            since=since,
            limit=args.limit,
        ))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "start-watcher":
        print(f"Starting inbox watcher for {args.account_id}...")
        asyncio.run(start_inbox_watcher(args.account_id, args.interval))
        print("Watcher started. Press Ctrl+C to stop.")
        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            asyncio.run(stop_inbox_watcher(args.account_id))
            print("Watcher stopped.")

    elif args.command == "stop-watcher":
        asyncio.run(stop_inbox_watcher(args.account_id))
        print(f"Stopped watcher for {args.account_id}")

    elif args.command == "status":
        active = is_watcher_active(args.account_id)
        print(json.dumps({
            "account_id": args.account_id,
            "watcher_active": active,
        }, indent=2))


if __name__ == "__main__":
    main()
