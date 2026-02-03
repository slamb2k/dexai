"""
Tool: Email Reader
Purpose: Unified interface for reading emails across providers

Provides a high-level interface for reading emails that works with
any configured provider (Google, Microsoft, or standalone IMAP).

Usage:
    python tools/office/email/reader.py --account-id <id> --list
    python tools/office/email/reader.py --account-id <id> --read <message-id>
    python tools/office/email/reader.py --account-id <id> --search "keyword"
    python tools/office/email/reader.py --account-id <id> --unread

Dependencies:
    - aiohttp (for Google/Microsoft providers)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection  # noqa: E402
from tools.office.models import Email, IntegrationLevel, OfficeAccount  # noqa: E402


def get_provider_for_account(account: OfficeAccount):
    """
    Get the appropriate provider instance for an account.

    Args:
        account: Office account

    Returns:
        Provider instance
    """
    if account.provider == "google":
        from tools.office.providers.google_workspace import GoogleWorkspaceProvider
        return GoogleWorkspaceProvider(account)
    elif account.provider == "microsoft":
        from tools.office.providers.microsoft_365 import Microsoft365Provider
        return Microsoft365Provider(account)
    elif account.provider == "standalone":
        from tools.office.providers.standalone_imap import StandaloneImapProvider
        return StandaloneImapProvider(account)
    else:
        raise ValueError(f"Unknown provider: {account.provider}")


def load_account(account_id: str) -> OfficeAccount | None:
    """
    Load an office account from database.

    Args:
        account_id: Account ID

    Returns:
        OfficeAccount or None if not found
    """
    from tools.office.oauth_manager import get_account

    result = get_account(account_id)
    if not result.get("success"):
        return None

    account_data = result["account"]

    return OfficeAccount(
        id=account_data["id"],
        user_id=account_data["user_id"],
        provider=account_data["provider"],
        integration_level=IntegrationLevel(account_data["integration_level"]),
        email_address=account_data.get("email_address", ""),
        access_token=account_data.get("access_token"),
        refresh_token=account_data.get("refresh_token"),
        scopes=account_data.get("scopes", []),
    )


async def list_emails(
    account_id: str,
    limit: int = 20,
    unread_only: bool = False,
    query: str | None = None,
) -> dict[str, Any]:
    """
    List emails from an account's inbox.

    Args:
        account_id: Account ID
        limit: Maximum emails to return
        unread_only: Only return unread emails
        query: Search query

    Returns:
        dict with list of emails
    """
    account = load_account(account_id)
    if not account:
        return {"success": False, "error": "Account not found"}

    if account.integration_level < IntegrationLevel.READ_ONLY:
        return {
            "success": False,
            "error": "Email reading requires Level 2+ integration",
        }

    provider = get_provider_for_account(account)

    # Authenticate first
    auth_result = await provider.authenticate()
    if not auth_result.get("success"):
        return auth_result

    # Get emails
    result = await provider.get_emails(
        limit=limit,
        unread_only=unread_only,
        query=query,
    )

    return result


async def read_email(
    account_id: str,
    message_id: str,
) -> dict[str, Any]:
    """
    Read a single email.

    Args:
        account_id: Account ID
        message_id: Message ID

    Returns:
        dict with email content
    """
    account = load_account(account_id)
    if not account:
        return {"success": False, "error": "Account not found"}

    if account.integration_level < IntegrationLevel.READ_ONLY:
        return {"success": False, "error": "Email reading requires Level 2+"}

    provider = get_provider_for_account(account)

    auth_result = await provider.authenticate()
    if not auth_result.get("success"):
        return auth_result

    return await provider.get_email(message_id)


async def read_thread(
    account_id: str,
    thread_id: str,
) -> dict[str, Any]:
    """
    Read all emails in a thread/conversation.

    Args:
        account_id: Account ID
        thread_id: Thread/conversation ID

    Returns:
        dict with list of emails in thread
    """
    account = load_account(account_id)
    if not account:
        return {"success": False, "error": "Account not found"}

    if account.integration_level < IntegrationLevel.READ_ONLY:
        return {"success": False, "error": "Email reading requires Level 2+"}

    provider = get_provider_for_account(account)

    auth_result = await provider.authenticate()
    if not auth_result.get("success"):
        return auth_result

    return await provider.get_thread(thread_id)


async def get_unread_count(account_id: str) -> dict[str, Any]:
    """
    Get count of unread emails.

    Args:
        account_id: Account ID

    Returns:
        dict with unread count
    """
    result = await list_emails(account_id, limit=100, unread_only=True)

    if not result.get("success"):
        return result

    emails = result.get("emails", [])
    return {
        "success": True,
        "unread_count": len(emails),
    }


async def search_emails(
    account_id: str,
    query: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Search emails.

    Args:
        account_id: Account ID
        query: Search query
        limit: Maximum results

    Returns:
        dict with matching emails
    """
    return await list_emails(account_id, limit=limit, query=query)


def format_email_summary(email_obj: Email) -> str:
    """
    Format an email for display.

    Args:
        email: Email object

    Returns:
        Formatted string
    """
    sender = str(email_obj.sender) if email_obj.sender else "Unknown"
    date = email_obj.received_at.strftime("%Y-%m-%d %H:%M") if email_obj.received_at else "Unknown"
    read_status = "" if email_obj.is_read else "[UNREAD] "
    star = "[*] " if email_obj.is_starred else ""

    return f"{star}{read_status}{date} | {sender}\n  Subject: {email_obj.subject}\n  {email_obj.snippet[:100]}..."


def main():
    parser = argparse.ArgumentParser(description="Email Reader")
    parser.add_argument("--account-id", required=True, help="Account ID")
    parser.add_argument("--list", action="store_true", help="List recent emails")
    parser.add_argument("--read", metavar="MESSAGE_ID", help="Read specific email")
    parser.add_argument("--thread", metavar="THREAD_ID", help="Read email thread")
    parser.add_argument("--search", metavar="QUERY", help="Search emails")
    parser.add_argument("--unread", action="store_true", help="Show unread only")
    parser.add_argument("--count", action="store_true", help="Show unread count only")
    parser.add_argument("--limit", type=int, default=20, help="Maximum results")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.count:
        result = asyncio.run(get_unread_count(args.account_id))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            print(f"Unread emails: {result['unread_count']}")
        else:
            print(f"Error: {result.get('error')}")

    elif args.read:
        result = asyncio.run(read_email(args.account_id, args.read))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            email_obj = result["email"]
            print(f"Subject: {email_obj.subject}")
            print(f"From: {email_obj.sender}")
            print(f"To: {', '.join(str(t) for t in email_obj.to)}")
            print(f"Date: {email_obj.received_at}")
            print(f"\n{'-' * 40}\n")
            print(email_obj.body_text or email_obj.snippet)
        else:
            print(f"Error: {result.get('error')}")

    elif args.thread:
        result = asyncio.run(read_thread(args.account_id, args.thread))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            for i, email_obj in enumerate(result["emails"], 1):
                print(f"\n--- Message {i} ---")
                print(format_email_summary(email_obj))
        else:
            print(f"Error: {result.get('error')}")

    elif args.search:
        result = asyncio.run(search_emails(args.account_id, args.search, args.limit))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            emails = result.get("emails", [])
            print(f"Found {len(emails)} matching emails:\n")
            for email_obj in emails:
                print(format_email_summary(email_obj))
                print()
        else:
            print(f"Error: {result.get('error')}")

    elif args.list:
        result = asyncio.run(list_emails(
            args.account_id,
            limit=args.limit,
            unread_only=args.unread,
        ))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            emails = result.get("emails", [])
            print(f"Showing {len(emails)} emails:\n")
            for email_obj in emails:
                print(format_email_summary(email_obj))
                print()
        else:
            print(f"Error: {result.get('error')}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
