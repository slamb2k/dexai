"""
Tool: Action Executor
Purpose: Execute queued office actions after undo window expires

Processes pending actions whose undo deadline has passed, executing them
via the appropriate provider (Google Workspace or Microsoft 365).

Usage:
    from tools.office.actions.executor import (
        execute_action,
        process_expired_actions,
        retry_failed_action,
        action_worker,
    )

    # Execute a specific action
    result = await execute_action("action-123")

    # Process all expired actions
    result = await process_expired_actions()

    # Run background worker
    await action_worker()

CLI:
    python tools/office/actions/executor.py --process-expired
    python tools/office/actions/executor.py --execute <action-id>
    python tools/office/actions/executor.py --retry <action-id>
"""

import argparse
import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from tools.office import get_connection
from tools.office.models import IntegrationLevel, OfficeAccount, OfficeAction

# Worker configuration
WORKER_INTERVAL_SECONDS = 5
MAX_RETRY_ATTEMPTS = 3


async def get_provider_for_account(account: OfficeAccount):
    """
    Get the appropriate provider instance for an account.

    Args:
        account: Office account to get provider for

    Returns:
        Provider instance (GoogleWorkspaceProvider or Microsoft365Provider)
    """
    if account.provider == "google":
        from tools.office.providers.google_workspace import GoogleWorkspaceProvider

        return GoogleWorkspaceProvider(account)

    if account.provider == "microsoft":
        from tools.office.providers.microsoft_365 import Microsoft365Provider

        return Microsoft365Provider(account)

    return None


def get_account_by_id(account_id: str) -> OfficeAccount | None:
    """
    Retrieve an office account by ID.

    Args:
        account_id: Account ID to look up

    Returns:
        OfficeAccount or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    row = cursor.fetchone()

    if not row:
        return None

    return OfficeAccount.from_dict(dict(row))


def log_to_audit_trail(
    account_id: str,
    action_type: str,
    action_summary: str,
    action_data: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """
    Log an action to the audit trail.

    Args:
        account_id: Account that performed the action
        action_type: Type of action
        action_summary: Human-readable summary
        action_data: Full action data
        result: Execution result
    """
    conn = get_connection()
    cursor = conn.cursor()

    audit_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO office_audit_log (id, account_id, action_type, action_summary, action_data, result)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            audit_id,
            account_id,
            action_type,
            action_summary,
            json.dumps(action_data),
            json.dumps(result),
        ),
    )
    conn.commit()


async def execute_action(action_id: str) -> dict[str, Any]:
    """
    Execute a single queued action.

    Verifies the action is still pending and the undo deadline has passed
    before executing via the provider.

    Args:
        action_id: ID of the action to execute

    Returns:
        dict with success status and result
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

    # Verify action is still pending
    if action.status != "pending":
        return {
            "success": False,
            "error": f"Action is not pending - status is '{action.status}'",
        }

    # Verify undo deadline has passed
    if action.undo_deadline and datetime.now() < action.undo_deadline:
        remaining = (action.undo_deadline - datetime.now()).total_seconds()
        return {
            "success": False,
            "error": f"Undo window has not expired ({int(remaining)}s remaining)",
        }

    # Get the account
    account = get_account_by_id(action.account_id)
    if not account:
        _mark_action_failed(cursor, conn, action_id, "Account not found")
        return {"success": False, "error": "Account not found"}

    # Verify account has appropriate permissions
    if account.integration_level < IntegrationLevel.MANAGED_PROXY:
        _mark_action_failed(
            cursor, conn, action_id, "Account integration level too low"
        )
        return {
            "success": False,
            "error": f"Account requires Level 4+ (current: {account.integration_level.value})",
        }

    # Get the provider
    provider = await get_provider_for_account(account)
    if not provider:
        _mark_action_failed(cursor, conn, action_id, f"Unknown provider: {account.provider}")
        return {"success": False, "error": f"Unknown provider: {account.provider}"}

    # Authenticate
    auth_result = await provider.authenticate()
    if not auth_result.get("success"):
        _mark_action_failed(cursor, conn, action_id, f"Authentication failed: {auth_result.get('error')}")
        return {
            "success": False,
            "error": f"Authentication failed: {auth_result.get('error')}",
        }

    # Execute the action based on type
    result = await _execute_action_by_type(provider, action)

    # Update action status
    now = datetime.now().isoformat()
    if result.get("success"):
        cursor.execute(
            "UPDATE office_actions SET status = 'executed', executed_at = ? WHERE id = ?",
            (now, action_id),
        )
    else:
        cursor.execute(
            "UPDATE office_actions SET status = 'failed' WHERE id = ?",
            (action_id,),
        )

    conn.commit()

    # Log to audit trail
    summary = _create_action_summary(action)
    log_to_audit_trail(
        account_id=action.account_id,
        action_type=action.action_type,
        action_summary=summary,
        action_data=action.action_data,
        result=result,
    )

    return result


def _mark_action_failed(cursor, conn, action_id: str, error: str) -> None:
    """Mark an action as failed in the database."""
    cursor.execute(
        "UPDATE office_actions SET status = 'failed' WHERE id = ?",
        (action_id,),
    )
    conn.commit()


async def _execute_action_by_type(provider, action: OfficeAction) -> dict[str, Any]:
    """
    Execute an action based on its type.

    Args:
        provider: Office provider instance
        action: Action to execute

    Returns:
        dict with success status and result
    """
    data = action.action_data
    action_type = action.action_type

    # Email actions
    if action_type == "send_email":
        return await provider.send_email(
            to=data.get("to", []),
            subject=data.get("subject", ""),
            body=data.get("body", ""),
            cc=data.get("cc"),
            bcc=data.get("bcc"),
            reply_to_message_id=data.get("reply_to_message_id"),
        )

    if action_type == "delete_email":
        message_id = data.get("message_id")
        if not message_id:
            return {"success": False, "error": "Missing message_id"}
        # Delete via provider (archive to trash)
        return await provider._make_request(
            "DELETE",
            f"{provider._get_delete_url(message_id)}",
        )

    if action_type == "archive_email":
        message_id = data.get("message_id")
        if not message_id:
            return {"success": False, "error": "Missing message_id"}
        # Archive implementation depends on provider
        if provider.provider_name == "google":
            # Gmail: Remove INBOX label
            return await provider._make_request(
                "POST",
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
                data={"removeLabelIds": ["INBOX"]},
            )
        # Microsoft: Move to archive folder
        return await provider._make_request(
            "POST",
            f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move",
            data={"destinationId": "archive"},
        )

    # Calendar actions
    if action_type == "schedule_meeting":
        return await provider.create_event(
            title=data.get("title", ""),
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            description=data.get("description", ""),
            location=data.get("location", ""),
            attendees=data.get("attendees"),
            calendar_id=data.get("calendar_id", "primary"),
        )

    if action_type == "cancel_meeting":
        event_id = data.get("event_id")
        if not event_id:
            return {"success": False, "error": "Missing event_id"}
        return await provider.delete_event(
            event_id=event_id,
            calendar_id=data.get("calendar_id", "primary"),
        )

    if action_type == "update_meeting":
        event_id = data.get("event_id")
        if not event_id:
            return {"success": False, "error": "Missing event_id"}
        start_time = None
        end_time = None
        if data.get("start_time"):
            start_time = datetime.fromisoformat(data["start_time"])
        if data.get("end_time"):
            end_time = datetime.fromisoformat(data["end_time"])
        return await provider.update_event(
            event_id=event_id,
            title=data.get("title"),
            start_time=start_time,
            end_time=end_time,
            description=data.get("description"),
            location=data.get("location"),
            attendees=data.get("attendees"),
            calendar_id=data.get("calendar_id", "primary"),
        )

    if action_type in ("accept_meeting", "decline_meeting", "tentative_meeting"):
        event_id = data.get("event_id")
        if not event_id:
            return {"success": False, "error": "Missing event_id"}
        response_map = {
            "accept_meeting": "accepted",
            "decline_meeting": "declined",
            "tentative_meeting": "tentative",
        }
        return await provider.respond_to_event(
            event_id=event_id,
            response=response_map[action_type],
            calendar_id=data.get("calendar_id", "primary"),
        )

    return {"success": False, "error": f"Unknown action type: {action_type}"}


def _create_action_summary(action: OfficeAction) -> str:
    """Create a human-readable summary of an action for the audit log."""
    data = action.action_data
    action_type = action.action_type

    if action_type == "send_email":
        to = data.get("to", [])
        if isinstance(to, list):
            to = ", ".join(to[:2])
        subject = data.get("subject", "")[:50]
        return f"Sent email to {to}: {subject}"

    if action_type == "delete_email":
        return f"Deleted email: {data.get('subject', 'Unknown')[:50]}"

    if action_type == "archive_email":
        return f"Archived email: {data.get('subject', 'Unknown')[:50]}"

    if action_type == "schedule_meeting":
        return f"Scheduled meeting: {data.get('title', '')[:30]} at {data.get('start_time', '')}"

    if action_type == "cancel_meeting":
        return f"Cancelled meeting: {data.get('title', 'Unknown')[:30]}"

    if action_type == "update_meeting":
        return f"Updated meeting: {data.get('title', 'Unknown')[:30]}"

    if action_type in ("accept_meeting", "decline_meeting", "tentative_meeting"):
        response = action_type.replace("_meeting", "")
        return f"{response.capitalize()} meeting: {data.get('title', 'Unknown')[:30]}"

    return f"Executed {action_type}"


async def process_expired_actions() -> dict[str, Any]:
    """
    Process all pending actions whose undo window has expired.

    Returns:
        dict with counts of processed, succeeded, and failed actions
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # Find all expired pending actions
    cursor.execute(
        """
        SELECT id FROM office_actions
        WHERE status = 'pending'
          AND undo_deadline <= ?
        ORDER BY created_at ASC
        """,
        (now,),
    )
    rows = cursor.fetchall()

    processed = 0
    succeeded = 0
    failed = 0

    for row in rows:
        action_id = row["id"]
        result = await execute_action(action_id)
        processed += 1

        if result.get("success"):
            succeeded += 1
        else:
            failed += 1

    return {
        "success": True,
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "timestamp": now,
    }


async def retry_failed_action(action_id: str) -> dict[str, Any]:
    """
    Retry a failed action.

    Resets the action status to pending and attempts execution again.

    Args:
        action_id: ID of the failed action to retry

    Returns:
        dict with success status and result
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

    # Only retry failed actions
    if action.status != "failed":
        return {
            "success": False,
            "error": f"Can only retry failed actions - status is '{action.status}'",
        }

    # Reset to pending with no undo window (execute immediately)
    cursor.execute(
        """
        UPDATE office_actions
        SET status = 'pending', undo_deadline = ?
        WHERE id = ?
        """,
        (datetime.now().isoformat(), action_id),
    )
    conn.commit()

    # Execute immediately
    return await execute_action(action_id)


async def action_worker() -> None:
    """
    Background worker that processes expired actions.

    Runs every 5 seconds to check for and execute expired actions.
    """
    print(f"Action worker started (interval: {WORKER_INTERVAL_SECONDS}s)")

    while True:
        result = await process_expired_actions()
        if result.get("processed", 0) > 0:
            print(
                f"Processed {result['processed']} actions: "
                f"{result['succeeded']} succeeded, {result['failed']} failed"
            )
        await asyncio.sleep(WORKER_INTERVAL_SECONDS)


async def get_pending_actions_count() -> int:
    """Get count of pending actions waiting for execution."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) as count FROM office_actions WHERE status = 'pending'"
    )
    row = cursor.fetchone()
    return row["count"] if row else 0


async def get_action_stats() -> dict[str, Any]:
    """Get statistics about actions in the queue."""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    # Count by status
    cursor.execute(
        """
        SELECT status, COUNT(*) as count
        FROM office_actions
        GROUP BY status
        """
    )
    stats["by_status"] = {row["status"]: row["count"] for row in cursor.fetchall()}

    # Count by type
    cursor.execute(
        """
        SELECT action_type, COUNT(*) as count
        FROM office_actions
        GROUP BY action_type
        """
    )
    stats["by_type"] = {row["action_type"]: row["count"] for row in cursor.fetchall()}

    # Expired but not processed
    now = datetime.now().isoformat()
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM office_actions
        WHERE status = 'pending' AND undo_deadline <= ?
        """,
        (now,),
    )
    row = cursor.fetchone()
    stats["expired_pending"] = row["count"] if row else 0

    return {"success": True, "stats": stats}


def main() -> None:
    """CLI entry point for the action executor."""
    parser = argparse.ArgumentParser(description="Office Action Executor")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--process-expired",
        action="store_true",
        help="Process all expired pending actions",
    )
    group.add_argument(
        "--execute",
        metavar="ACTION_ID",
        help="Execute a specific action",
    )
    group.add_argument(
        "--retry",
        metavar="ACTION_ID",
        help="Retry a failed action",
    )
    group.add_argument(
        "--stats",
        action="store_true",
        help="Show action queue statistics",
    )
    group.add_argument(
        "--worker",
        action="store_true",
        help="Run background worker",
    )

    args = parser.parse_args()

    if args.process_expired:
        result = asyncio.run(process_expired_actions())
        print(json.dumps(result, indent=2))

    elif args.execute:
        result = asyncio.run(execute_action(args.execute))
        print(json.dumps(result, indent=2))

    elif args.retry:
        result = asyncio.run(retry_failed_action(args.retry))
        print(json.dumps(result, indent=2))

    elif args.stats:
        result = asyncio.run(get_action_stats())
        print(json.dumps(result, indent=2))

    elif args.worker:
        print("Starting action worker (Ctrl+C to stop)...")
        asyncio.run(action_worker())


if __name__ == "__main__":
    main()
