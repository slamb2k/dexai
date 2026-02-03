"""
Tool: Email Draft Manager
Purpose: High-level interface for draft management with ADHD features

This tool provides the unified Layer 3 (Collaborative) interface for email drafts.
It coordinates between the provider-level create_draft and the local database
tracking, adding sentiment analysis and user confirmation flows.

Key ADHD Features:
- Sentiment analysis before saving drafts
- Full preview before any action
- No auto-send (Level 3 only creates drafts)
- User must explicitly approve drafts

Usage:
    # Create a new draft
    python draft_manager.py --account-id <id> --create --to "user@example.com" --subject "Hello" --body "Message"

    # List pending drafts
    python draft_manager.py --account-id <id> --list-pending

    # Get draft details
    python draft_manager.py --account-id <id> --get <draft-id>

    # Approve a draft (marks as approved, user sends from email client)
    python draft_manager.py --account-id <id> --approve <draft-id>

    # Delete a draft
    python draft_manager.py --account-id <id> --delete <draft-id>

Dependencies:
    - aiohttp (for provider API calls)
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection
from tools.office.email.sentiment import analyze_email_sentiment


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


def _get_provider(account: dict):
    """Get the appropriate provider for an account."""
    from tools.office.models import IntegrationLevel, OfficeAccount

    # Build OfficeAccount object
    office_account = OfficeAccount(
        id=account["id"],
        user_id=account["user_id"],
        provider=account["provider"],
        integration_level=IntegrationLevel(account["integration_level"]),
        email_address=account.get("email_address", ""),
        access_token=account.get("access_token_encrypted"),  # Would be decrypted
        refresh_token=account.get("refresh_token_encrypted"),
    )

    if account["provider"] == "google":
        from tools.office.providers.google_workspace import GoogleWorkspaceProvider
        return GoogleWorkspaceProvider(office_account)
    elif account["provider"] == "microsoft":
        from tools.office.providers.microsoft_365 import Microsoft365Provider
        return Microsoft365Provider(office_account)
    else:
        raise ValueError(f"Unknown provider: {account['provider']}")


async def create_draft(
    account_id: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to_message_id: str | None = None,
    check_sentiment: bool = True,
) -> dict[str, Any]:
    """
    Create an email draft with local tracking and sentiment analysis.

    This creates a draft in the user's email provider AND tracks it locally
    in the office_drafts table for the confirmation flow.

    Args:
        account_id: Office account ID
        to: List of recipient email addresses
        subject: Email subject
        body: Email body (plain text)
        cc: Optional CC recipients
        bcc: Optional BCC recipients
        reply_to_message_id: Optional message ID to reply to
        check_sentiment: Whether to run sentiment analysis

    Returns:
        {
            "success": bool,
            "draft_id": str,            # Local draft ID
            "provider_draft_id": str,   # Provider's draft ID
            "sentiment_analysis": dict, # If check_sentiment=True
        }
    """
    # Get account
    account = _get_account(account_id)
    if not account:
        return {"success": False, "error": f"Account not found: {account_id}"}

    # Check integration level
    if account["integration_level"] < 3:
        return {
            "success": False,
            "error": f"Draft creation requires Level 3+. Current level: {account['integration_level']}",
        }

    # Run sentiment analysis if requested
    sentiment_result = None
    if check_sentiment:
        sentiment_result = analyze_email_sentiment(subject, body)

    # Create draft via provider
    try:
        provider = _get_provider(account)
        result = await provider.create_draft(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            reply_to_message_id=reply_to_message_id,
        )

        if not result.get("success"):
            return result

        provider_draft_id = result.get("draft_id")

    except Exception as e:
        return {"success": False, "error": f"Provider error: {e!s}"}

    # Store in local database
    draft_id = str(uuid.uuid4())
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO office_drafts (
            id, account_id, provider_draft_id, subject, recipients,
            cc, bcc, body_text, reply_to_message_id, status,
            sentiment_score, sentiment_flags, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft_id,
            account_id,
            provider_draft_id,
            subject,
            json.dumps(to),
            json.dumps(cc) if cc else None,
            json.dumps(bcc) if bcc else None,
            body,
            reply_to_message_id,
            "pending",
            sentiment_result["score"] if sentiment_result else None,
            json.dumps(sentiment_result["flags"]) if sentiment_result else None,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "draft_id": draft_id,
        "provider_draft_id": provider_draft_id,
        "sentiment_analysis": sentiment_result,
    }


async def get_pending_drafts(
    account_id: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Get list of pending drafts for an account.

    Args:
        account_id: Office account ID
        limit: Maximum number of drafts to return

    Returns:
        {
            "success": bool,
            "drafts": list,
            "total": int,
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM office_drafts
        WHERE account_id = ? AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (account_id, limit),
    )
    rows = cursor.fetchall()

    # Get total count
    cursor.execute(
        "SELECT COUNT(*) FROM office_drafts WHERE account_id = ? AND status = 'pending'",
        (account_id,),
    )
    total = cursor.fetchone()[0]
    conn.close()

    drafts = []
    for row in rows:
        draft = dict(row)
        # Parse JSON fields
        if draft.get("recipients"):
            draft["recipients"] = json.loads(draft["recipients"])
        if draft.get("cc"):
            draft["cc"] = json.loads(draft["cc"])
        if draft.get("bcc"):
            draft["bcc"] = json.loads(draft["bcc"])
        if draft.get("sentiment_flags"):
            draft["sentiment_flags"] = json.loads(draft["sentiment_flags"])
        drafts.append(draft)

    return {
        "success": True,
        "drafts": drafts,
        "total": total,
    }


async def get_draft(draft_id: str) -> dict[str, Any]:
    """
    Get details of a specific draft.

    Args:
        draft_id: Local draft ID

    Returns:
        {
            "success": bool,
            "draft": dict,
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM office_drafts WHERE id = ?",
        (draft_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": f"Draft not found: {draft_id}"}

    draft = dict(row)
    # Parse JSON fields
    if draft.get("recipients"):
        draft["recipients"] = json.loads(draft["recipients"])
    if draft.get("cc"):
        draft["cc"] = json.loads(draft["cc"])
    if draft.get("bcc"):
        draft["bcc"] = json.loads(draft["bcc"])
    if draft.get("sentiment_flags"):
        draft["sentiment_flags"] = json.loads(draft["sentiment_flags"])

    return {"success": True, "draft": draft}


async def approve_draft(
    draft_id: str,
    send_immediately: bool = False,
) -> dict[str, Any]:
    """
    Approve a draft for sending.

    In Level 3 (Collaborative), this marks the draft as approved.
    The user must then send it from their email client.

    In Level 4+ (Managed Proxy), send_immediately can trigger actual sending.

    Args:
        draft_id: Local draft ID
        send_immediately: Whether to send (Level 4+ only)

    Returns:
        {
            "success": bool,
            "status": "approved" | "sent",
        }
    """
    # Get draft
    result = await get_draft(draft_id)
    if not result.get("success"):
        return result

    draft = result["draft"]

    # Get account to check level
    account = _get_account(draft["account_id"])
    if not account:
        return {"success": False, "error": "Account not found"}

    conn = get_connection()
    cursor = conn.cursor()

    if send_immediately and account["integration_level"] >= 4:
        # Level 4+: Actually send the draft
        try:
            provider = _get_provider(account)
            send_result = await provider.send_draft(draft["provider_draft_id"])

            if send_result.get("success"):
                cursor.execute(
                    """
                    UPDATE office_drafts
                    SET status = 'sent', approved_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (datetime.now().isoformat(), datetime.now().isoformat(), draft_id),
                )
                conn.commit()
                conn.close()
                return {"success": True, "status": "sent"}
            else:
                conn.close()
                return send_result

        except Exception as e:
            conn.close()
            return {"success": False, "error": f"Send failed: {e!s}"}
    else:
        # Level 3: Just mark as approved
        cursor.execute(
            """
            UPDATE office_drafts
            SET status = 'approved', approved_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (datetime.now().isoformat(), datetime.now().isoformat(), draft_id),
        )
        conn.commit()
        conn.close()

        return {"success": True, "status": "approved"}


async def update_draft(
    draft_id: str,
    subject: str | None = None,
    body: str | None = None,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> dict[str, Any]:
    """
    Update an existing draft.

    Args:
        draft_id: Local draft ID
        subject: New subject (optional)
        body: New body (optional)
        to: New recipients (optional)
        cc: New CC (optional)
        bcc: New BCC (optional)

    Returns:
        {
            "success": bool,
            "draft": dict,
            "sentiment_analysis": dict,  # If body changed
        }
    """
    # Get existing draft
    result = await get_draft(draft_id)
    if not result.get("success"):
        return result

    draft = result["draft"]

    # Only pending drafts can be updated
    if draft["status"] != "pending":
        return {"success": False, "error": f"Cannot update draft with status: {draft['status']}"}

    # Build updates
    updates = []
    params = []

    if subject is not None:
        updates.append("subject = ?")
        params.append(subject)

    if body is not None:
        updates.append("body_text = ?")
        params.append(body)

    if to is not None:
        updates.append("recipients = ?")
        params.append(json.dumps(to))

    if cc is not None:
        updates.append("cc = ?")
        params.append(json.dumps(cc))

    if bcc is not None:
        updates.append("bcc = ?")
        params.append(json.dumps(bcc))

    if not updates:
        return {"success": True, "draft": draft, "message": "No changes"}

    # Re-run sentiment analysis if content changed
    sentiment_result = None
    if subject is not None or body is not None:
        new_subject = subject if subject is not None else draft["subject"]
        new_body = body if body is not None else draft["body_text"]
        sentiment_result = analyze_email_sentiment(new_subject, new_body)

        updates.append("sentiment_score = ?")
        params.append(sentiment_result["score"])
        updates.append("sentiment_flags = ?")
        params.append(json.dumps(sentiment_result["flags"]))

    updates.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.append(draft_id)

    # Update database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE office_drafts SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    conn.close()

    # Get updated draft
    result = await get_draft(draft_id)
    result["sentiment_analysis"] = sentiment_result

    return result


async def delete_draft(draft_id: str) -> dict[str, Any]:
    """
    Delete a draft from both local database and provider.

    Args:
        draft_id: Local draft ID

    Returns:
        {
            "success": bool,
        }
    """
    # Get draft
    result = await get_draft(draft_id)
    if not result.get("success"):
        return result

    draft = result["draft"]

    # Get account and provider
    account = _get_account(draft["account_id"])
    if account and draft.get("provider_draft_id"):
        try:
            provider = _get_provider(account)
            await provider.delete_draft(draft["provider_draft_id"])
        except Exception as e:
            # Log but don't fail - provider draft may already be gone
            print(f"Warning: Could not delete provider draft: {e}")

    # Delete from local database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE office_drafts SET status = 'deleted', updated_at = ? WHERE id = ?",
        (datetime.now().isoformat(), draft_id),
    )
    conn.commit()
    conn.close()

    return {"success": True}


def main():
    parser = argparse.ArgumentParser(
        description="Email Draft Manager for Level 3 Office Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a draft
  python draft_manager.py --account-id abc123 --create --to "user@example.com" --subject "Hello" --body "Message"

  # List pending drafts
  python draft_manager.py --account-id abc123 --list-pending

  # Get draft details
  python draft_manager.py --account-id abc123 --get draft-id-123

  # Approve a draft
  python draft_manager.py --account-id abc123 --approve draft-id-123

  # Delete a draft
  python draft_manager.py --account-id abc123 --delete draft-id-123
        """,
    )

    parser.add_argument("--account-id", required=True, help="Office account ID")

    # Actions (mutually exclusive)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--create", action="store_true", help="Create a new draft")
    actions.add_argument("--list-pending", action="store_true", help="List pending drafts")
    actions.add_argument("--get", metavar="DRAFT_ID", help="Get draft details")
    actions.add_argument("--approve", metavar="DRAFT_ID", help="Approve a draft")
    actions.add_argument("--delete", metavar="DRAFT_ID", help="Delete a draft")

    # Create arguments
    parser.add_argument("--to", help="Recipient email (comma-separated for multiple)")
    parser.add_argument("--subject", help="Email subject")
    parser.add_argument("--body", help="Email body")
    parser.add_argument("--cc", help="CC recipients (comma-separated)")
    parser.add_argument("--bcc", help="BCC recipients (comma-separated)")
    parser.add_argument("--no-sentiment", action="store_true", help="Skip sentiment analysis")

    # List arguments
    parser.add_argument("--limit", type=int, default=20, help="Max results for list")

    args = parser.parse_args()

    result = None

    if args.create:
        if not all([args.to, args.subject, args.body]):
            print("Error: --to, --subject, and --body are required for create")
            sys.exit(1)

        to_list = [x.strip() for x in args.to.split(",")]
        cc_list = [x.strip() for x in args.cc.split(",")] if args.cc else None
        bcc_list = [x.strip() for x in args.bcc.split(",")] if args.bcc else None

        result = asyncio.run(create_draft(
            account_id=args.account_id,
            to=to_list,
            subject=args.subject,
            body=args.body,
            cc=cc_list,
            bcc=bcc_list,
            check_sentiment=not args.no_sentiment,
        ))

    elif args.list_pending:
        result = asyncio.run(get_pending_drafts(
            account_id=args.account_id,
            limit=args.limit,
        ))

    elif args.get:
        result = asyncio.run(get_draft(args.get))

    elif args.approve:
        result = asyncio.run(approve_draft(args.approve))

    elif args.delete:
        result = asyncio.run(delete_draft(args.delete))

    if result:
        if result.get("success"):
            print("OK")
        else:
            print(f"ERROR: {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
