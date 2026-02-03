"""
Tool: Email Sender
Purpose: Send emails through the action queue system with undo window

This tool provides Level 4 (Managed Proxy) email sending with ADHD-safe features:
- All sends go through the action queue with configurable undo windows
- Sentiment analysis extends undo window for emotional emails
- Bulk operations for efficiency
- Full audit trail of all actions

Key ADHD Features:
- Extended undo window (60s default, 5 min for high-sentiment emails)
- Sentiment gating warns about emotional content
- One-click undo for "oops" moments
- Clear confirmation before permanent actions

Usage:
    # Send an email
    python tools/office/email/sender.py --account-id <id> --send --to "user@example.com" --subject "Test" --body "Hello"

    # Send a draft
    python tools/office/email/sender.py --account-id <id> --send-draft <draft-id>

    # Delete an email
    python tools/office/email/sender.py --account-id <id> --delete <message-id>

    # Archive an email
    python tools/office/email/sender.py --account-id <id> --archive <message-id>

    # Bulk action
    python tools/office/email/sender.py --account-id <id> --bulk archive --message-ids "id1,id2,id3"

Dependencies:
    - aiohttp (for provider API calls)
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection
from tools.office.actions.queue import queue_action
from tools.office.actions.undo_manager import calculate_undo_deadline
from tools.office.actions.validator import check_rate_limits, validate_action
from tools.office.email.sentiment import analyze_email_sentiment
from tools.office.models import IntegrationLevel, OfficeAccount


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


def _get_draft(draft_id: str) -> dict | None:
    """Get draft details from database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM office_drafts WHERE id = ?",
        (draft_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        draft = dict(row)
        if draft.get("recipients"):
            draft["recipients"] = json.loads(draft["recipients"])
        if draft.get("cc"):
            draft["cc"] = json.loads(draft["cc"])
        if draft.get("bcc"):
            draft["bcc"] = json.loads(draft["bcc"])
        return draft
    return None


async def send_email(
    account_id: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to_message_id: str | None = None,
    attachments: list[dict] | None = None,
    skip_sentiment_check: bool = False,
) -> dict[str, Any]:
    """
    Queue an email for sending with undo window.

    This function validates the request, runs sentiment analysis (unless skipped),
    and queues the email for sending. The email will be sent after the undo window
    expires unless the user cancels the action.

    Args:
        account_id: Office account ID
        to: List of recipient email addresses
        subject: Email subject
        body: Email body (plain text)
        cc: Optional CC recipients
        bcc: Optional BCC recipients
        reply_to_message_id: Optional message ID to reply to
        attachments: Optional list of attachment dicts
        skip_sentiment_check: Skip sentiment analysis (default False)

    Returns:
        {
            "success": bool,
            "action_id": str,
            "undo_deadline": str,
            "sentiment_analysis": dict | None,
            "warnings": list[str],
        }
    """
    # Get account
    account = _get_account(account_id)
    if not account:
        return {"success": False, "error": f"Account not found: {account_id}"}

    # Validate action
    action_data = {
        "to": to,
        "subject": subject,
        "body": body,
        "cc": cc,
        "bcc": bcc,
        "reply_to_message_id": reply_to_message_id,
        "attachments": attachments,
    }

    validation = validate_action(account_id, "send_email", action_data)
    if not validation["valid"]:
        return {
            "success": False,
            "error": "; ".join(validation["errors"]),
            "warnings": validation["warnings"],
        }

    # Run sentiment analysis unless skipped
    sentiment_result = None
    sentiment_score = None

    if not skip_sentiment_check:
        sentiment_result = analyze_email_sentiment(subject, body)
        sentiment_score = sentiment_result["score"]

        # Add sentiment warning if high
        if not sentiment_result["safe_to_send"]:
            validation["warnings"].append(
                f"High emotional content detected (score: {sentiment_score:.2f}). "
                f"{sentiment_result.get('suggestion', 'Consider reviewing before sending.')}"
            )

    # Calculate undo deadline based on sentiment
    undo_deadline = await calculate_undo_deadline("send_email", sentiment_score)
    undo_window_seconds = int((undo_deadline - datetime.now()).total_seconds())

    # Queue the action
    result = await queue_action(
        account_id=account_id,
        action_type="send_email",
        action_data=action_data,
        undo_window_seconds=undo_window_seconds,
    )

    if not result.get("success"):
        return result

    return {
        "success": True,
        "action_id": result["action_id"],
        "undo_deadline": result["undo_deadline"],
        "sentiment_analysis": sentiment_result,
        "warnings": validation["warnings"],
    }


async def send_draft(
    draft_id: str,
    skip_undo: bool = False,
) -> dict[str, Any]:
    """
    Convert an existing draft to a send action.

    Args:
        draft_id: Local draft ID
        skip_undo: If True, execute immediately without undo window

    Returns:
        {
            "success": bool,
            "action_id": str,
            "undo_deadline": str | None,
        }
    """
    # Get draft
    draft = _get_draft(draft_id)
    if not draft:
        return {"success": False, "error": f"Draft not found: {draft_id}"}

    if draft["status"] != "pending" and draft["status"] != "approved":
        return {
            "success": False,
            "error": f"Cannot send draft with status: {draft['status']}",
        }

    account_id = draft["account_id"]

    # Get account
    account = _get_account(account_id)
    if not account:
        return {"success": False, "error": f"Account not found: {account_id}"}

    # Check integration level
    if account["integration_level"] < IntegrationLevel.MANAGED_PROXY.value:
        return {
            "success": False,
            "error": f"Sending requires Level 4+. Current level: {account['integration_level']}",
        }

    # Build action data from draft
    action_data = {
        "to": draft.get("recipients", []),
        "subject": draft.get("subject", ""),
        "body": draft.get("body_text", ""),
        "cc": draft.get("cc"),
        "bcc": draft.get("bcc"),
        "reply_to_message_id": draft.get("reply_to_message_id"),
        "provider_draft_id": draft.get("provider_draft_id"),
        "draft_id": draft_id,
    }

    # Calculate undo window from existing sentiment score
    sentiment_score = draft.get("sentiment_score")
    undo_deadline = await calculate_undo_deadline("send_email", sentiment_score)
    undo_window_seconds = int((undo_deadline - datetime.now()).total_seconds())

    if skip_undo:
        undo_window_seconds = 0

    # Queue the action
    result = await queue_action(
        account_id=account_id,
        action_type="send_email",
        action_data=action_data,
        undo_window_seconds=undo_window_seconds,
    )

    if not result.get("success"):
        return result

    # Update draft status
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE office_drafts
        SET status = 'sending', updated_at = ?
        WHERE id = ?
        """,
        (datetime.now().isoformat(), draft_id),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "action_id": result["action_id"],
        "undo_deadline": result["undo_deadline"] if not skip_undo else None,
    }


async def delete_email(
    account_id: str,
    message_id: str,
    permanent: bool = False,
) -> dict[str, Any]:
    """
    Queue an email deletion.

    By default, moves to trash. If permanent=True, deletes permanently
    (this requires explicit confirmation).

    Args:
        account_id: Office account ID
        message_id: Provider message ID to delete
        permanent: If True, permanently delete (not just trash)

    Returns:
        {
            "success": bool,
            "action_id": str,
            "undo_deadline": str,
        }
    """
    # Get account
    account = _get_account(account_id)
    if not account:
        return {"success": False, "error": f"Account not found: {account_id}"}

    # Validate action
    validation = validate_action(account_id, "delete_email", {"message_id": message_id})
    if not validation["valid"]:
        return {
            "success": False,
            "error": "; ".join(validation["errors"]),
        }

    action_data = {
        "message_id": message_id,
        "permanent": permanent,
    }

    # Permanent deletion requires confirmation flag
    require_confirmation = permanent

    # Calculate undo deadline
    undo_deadline = await calculate_undo_deadline("delete_email")
    undo_window_seconds = int((undo_deadline - datetime.now()).total_seconds())

    # Queue the action
    result = await queue_action(
        account_id=account_id,
        action_type="delete_email",
        action_data=action_data,
        undo_window_seconds=undo_window_seconds,
        require_confirmation=require_confirmation,
    )

    return result


async def archive_email(
    account_id: str,
    message_id: str,
) -> dict[str, Any]:
    """
    Queue an email archive action.

    Args:
        account_id: Office account ID
        message_id: Provider message ID to archive

    Returns:
        {
            "success": bool,
            "action_id": str,
            "undo_deadline": str,
        }
    """
    # Get account
    account = _get_account(account_id)
    if not account:
        return {"success": False, "error": f"Account not found: {account_id}"}

    # Validate action
    validation = validate_action(account_id, "archive_email", {"message_id": message_id})
    if not validation["valid"]:
        return {
            "success": False,
            "error": "; ".join(validation["errors"]),
        }

    action_data = {
        "message_id": message_id,
    }

    # Calculate undo deadline
    undo_deadline = await calculate_undo_deadline("archive_email")
    undo_window_seconds = int((undo_deadline - datetime.now()).total_seconds())

    # Queue the action
    result = await queue_action(
        account_id=account_id,
        action_type="archive_email",
        action_data=action_data,
        undo_window_seconds=undo_window_seconds,
    )

    return result


async def bulk_action(
    account_id: str,
    message_ids: list[str],
    action: str,
) -> dict[str, Any]:
    """
    Queue a bulk action on multiple emails.

    Supported actions: archive, delete, mark_read

    Args:
        account_id: Office account ID
        message_ids: List of provider message IDs
        action: Action to perform (archive, delete, mark_read)

    Returns:
        {
            "success": bool,
            "action_id": str,
            "undo_deadline": str,
            "count": int,
        }
    """
    valid_actions = {"archive", "delete", "mark_read"}
    if action not in valid_actions:
        return {
            "success": False,
            "error": f"Invalid bulk action: {action}. Must be one of: {', '.join(valid_actions)}",
        }

    # Get account
    account = _get_account(account_id)
    if not account:
        return {"success": False, "error": f"Account not found: {account_id}"}

    # Map action to action_type
    action_type_map = {
        "archive": "archive_email",
        "delete": "delete_email",
        "mark_read": "mark_read",
    }
    action_type = action_type_map[action]

    # Validate action
    validation = validate_action(account_id, action_type, {"message_ids": message_ids})
    if not validation["valid"]:
        return {
            "success": False,
            "error": "; ".join(validation["errors"]),
        }

    action_data = {
        "message_ids": message_ids,
        "bulk_action": action,
        "count": len(message_ids),
    }

    # Calculate undo deadline for bulk action
    undo_deadline = await calculate_undo_deadline("bulk_action")
    undo_window_seconds = int((undo_deadline - datetime.now()).total_seconds())

    # Queue as a single bulk action
    result = await queue_action(
        account_id=account_id,
        action_type=f"bulk_{action}",
        action_data=action_data,
        undo_window_seconds=undo_window_seconds,
    )

    if not result.get("success"):
        return result

    return {
        "success": True,
        "action_id": result["action_id"],
        "undo_deadline": result["undo_deadline"],
        "count": len(message_ids),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Email Sender for Level 4 Office Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send an email
  python sender.py --account-id abc123 --send --to "user@example.com" --subject "Hello" --body "Hi there"

  # Send with CC
  python sender.py --account-id abc123 --send --to "user@example.com" --cc "cc@example.com" --subject "Hello" --body "Hi"

  # Send a draft
  python sender.py --account-id abc123 --send-draft draft-id-123

  # Delete an email (to trash)
  python sender.py --account-id abc123 --delete message-id-123

  # Permanently delete an email
  python sender.py --account-id abc123 --delete message-id-123 --permanent

  # Archive an email
  python sender.py --account-id abc123 --archive message-id-123

  # Bulk archive
  python sender.py --account-id abc123 --bulk archive --message-ids "id1,id2,id3"
        """,
    )

    parser.add_argument("--account-id", required=True, help="Office account ID")

    # Actions (mutually exclusive)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--send", action="store_true", help="Send a new email")
    actions.add_argument("--send-draft", metavar="DRAFT_ID", help="Send an existing draft")
    actions.add_argument("--delete", metavar="MESSAGE_ID", help="Delete an email")
    actions.add_argument("--archive", metavar="MESSAGE_ID", help="Archive an email")
    actions.add_argument("--bulk", metavar="ACTION", help="Bulk action (archive, delete, mark_read)")

    # Send arguments
    parser.add_argument("--to", help="Recipient email (comma-separated for multiple)")
    parser.add_argument("--subject", help="Email subject")
    parser.add_argument("--body", help="Email body")
    parser.add_argument("--cc", help="CC recipients (comma-separated)")
    parser.add_argument("--bcc", help="BCC recipients (comma-separated)")
    parser.add_argument("--no-sentiment", action="store_true", help="Skip sentiment analysis")

    # Delete arguments
    parser.add_argument("--permanent", action="store_true", help="Permanently delete (not trash)")

    # Bulk arguments
    parser.add_argument("--message-ids", help="Message IDs (comma-separated)")

    # Send draft arguments
    parser.add_argument("--skip-undo", action="store_true", help="Skip undo window for draft send")

    args = parser.parse_args()

    result = None

    if args.send:
        if not all([args.to, args.subject, args.body]):
            print("Error: --to, --subject, and --body are required for send")
            sys.exit(1)

        to_list = [x.strip() for x in args.to.split(",")]
        cc_list = [x.strip() for x in args.cc.split(",")] if args.cc else None
        bcc_list = [x.strip() for x in args.bcc.split(",")] if args.bcc else None

        result = asyncio.run(send_email(
            account_id=args.account_id,
            to=to_list,
            subject=args.subject,
            body=args.body,
            cc=cc_list,
            bcc=bcc_list,
            skip_sentiment_check=args.no_sentiment,
        ))

    elif args.send_draft:
        result = asyncio.run(send_draft(
            draft_id=args.send_draft,
            skip_undo=args.skip_undo,
        ))

    elif args.delete:
        result = asyncio.run(delete_email(
            account_id=args.account_id,
            message_id=args.delete,
            permanent=args.permanent,
        ))

    elif args.archive:
        result = asyncio.run(archive_email(
            account_id=args.account_id,
            message_id=args.archive,
        ))

    elif args.bulk:
        if not args.message_ids:
            print("Error: --message-ids is required for bulk actions")
            sys.exit(1)

        message_ids = [x.strip() for x in args.message_ids.split(",")]

        result = asyncio.run(bulk_action(
            account_id=args.account_id,
            message_ids=message_ids,
            action=args.bulk,
        ))

    if result:
        if result.get("success"):
            print("OK")
        else:
            print(f"ERROR: {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
