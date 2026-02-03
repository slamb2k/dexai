"""
Tool: VIP Contact Manager
Purpose: Manage contacts who bypass normal automation policies

VIP contacts receive special treatment - their messages always reach the user
regardless of focus mode, scheduling policies, or automation rules.

Usage:
    from tools.office.automation.contact_manager import (
        add_vip,
        remove_vip,
        list_vips,
        is_vip,
        get_vip_settings,
        update_vip,
        suggest_vips,
    )

    # Add a VIP contact
    result = await add_vip("account-123", "boss@company.com", name="My Boss", priority="critical")

    # Check if contact is VIP
    is_vip_contact = await is_vip("account-123", "boss@company.com")

    # List all VIPs
    result = await list_vips("account-123")

Priority Levels:
    - critical: Always interrupt, even in Do Not Disturb
    - high: Bypass flow state, immediate notify
    - normal: Just starred/labeled specially

CLI:
    python tools/office/automation/contact_manager.py --account-id <id> --add-vip "boss@company.com" --name "My Boss" --priority critical
    python tools/office/automation/contact_manager.py --account-id <id> --remove-vip "old@example.com"
    python tools/office/automation/contact_manager.py --account-id <id> --list-vips
    python tools/office/automation/contact_manager.py --account-id <id> --check-vip "someone@example.com"
    python tools/office/automation/contact_manager.py --account-id <id> --suggest-vips
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


# Valid priority levels
PRIORITY_LEVELS = ("critical", "high", "normal")


def _ensure_vip_tables() -> None:
    """Create VIP contact tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Check if old schema exists and migrate if needed
    cursor.execute("PRAGMA table_info(office_vip_contacts)")
    columns = {row[1] for row in cursor.fetchall()}

    if columns and "updated_at" not in columns:
        # Old schema exists - migrate by dropping and recreating
        # This is safe for development; production would need proper migration
        cursor.execute("DROP TABLE IF EXISTS office_vip_contacts")
        conn.commit()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_vip_contacts (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            email TEXT NOT NULL,
            name TEXT,
            priority TEXT DEFAULT 'high',
            always_notify BOOLEAN DEFAULT TRUE,
            bypass_focus BOOLEAN DEFAULT TRUE,
            notes TEXT,
            interaction_count INTEGER DEFAULT 0,
            last_interaction DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, email),
            FOREIGN KEY (account_id) REFERENCES office_accounts(id)
        )
    """)

    # Index for quick VIP lookups
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_vip_account_email "
        "ON office_vip_contacts(account_id, email)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_vip_account_priority "
        "ON office_vip_contacts(account_id, priority)"
    )

    conn.commit()


async def add_vip(
    account_id: str,
    email: str,
    name: str | None = None,
    priority: str = "high",
    always_notify: bool = True,
    bypass_focus: bool = True,
    notes: str | None = None,
) -> dict[str, Any]:
    """
    Add a VIP contact.

    Args:
        account_id: Account to add VIP for
        email: Email address of the VIP contact
        name: Display name (optional)
        priority: Priority level (critical, high, normal)
        always_notify: Whether to always notify for this contact
        bypass_focus: Whether this contact bypasses focus mode
        notes: Additional notes about the contact

    Returns:
        dict with success status and VIP details
    """
    _ensure_vip_tables()

    if priority not in PRIORITY_LEVELS:
        return {
            "success": False,
            "error": f"Invalid priority. Must be one of: {', '.join(PRIORITY_LEVELS)}",
        }

    email = email.lower().strip()

    conn = get_connection()
    cursor = conn.cursor()

    # Check if already exists
    cursor.execute(
        "SELECT id FROM office_vip_contacts WHERE account_id = ? AND email = ?",
        (account_id, email),
    )

    if cursor.fetchone():
        return {
            "success": False,
            "error": f"VIP contact {email} already exists",
        }

    vip_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    cursor.execute(
        """
        INSERT INTO office_vip_contacts
        (id, account_id, email, name, priority, always_notify, bypass_focus, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            vip_id,
            account_id,
            email,
            name,
            priority,
            always_notify,
            bypass_focus,
            notes,
            now,
            now,
        ),
    )
    conn.commit()

    return {
        "success": True,
        "vip_id": vip_id,
        "account_id": account_id,
        "email": email,
        "name": name,
        "priority": priority,
        "always_notify": always_notify,
        "bypass_focus": bypass_focus,
        "notes": notes,
    }


async def remove_vip(account_id: str, email: str) -> dict[str, Any]:
    """
    Remove a VIP contact.

    Args:
        account_id: Account to remove VIP from
        email: Email address to remove

    Returns:
        dict with success status
    """
    _ensure_vip_tables()

    email = email.lower().strip()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name FROM office_vip_contacts WHERE account_id = ? AND email = ?",
        (account_id, email),
    )
    row = cursor.fetchone()

    if not row:
        return {
            "success": False,
            "error": f"VIP contact {email} not found",
        }

    cursor.execute(
        "DELETE FROM office_vip_contacts WHERE account_id = ? AND email = ?",
        (account_id, email),
    )
    conn.commit()

    return {
        "success": True,
        "account_id": account_id,
        "email": email,
        "name": row["name"],
        "message": f"Removed {email} from VIP list",
    }


async def list_vips(account_id: str) -> dict[str, Any]:
    """
    List all VIP contacts for an account.

    Args:
        account_id: Account to list VIPs for

    Returns:
        dict with list of VIP contacts
    """
    _ensure_vip_tables()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM office_vip_contacts
        WHERE account_id = ?
        ORDER BY
            CASE priority
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'normal' THEN 2
            END,
            name, email
        """,
        (account_id,),
    )
    rows = cursor.fetchall()

    vips = [dict(row) for row in rows]

    # Group by priority for easier reading
    by_priority = {
        "critical": [],
        "high": [],
        "normal": [],
    }

    for vip in vips:
        priority = vip.get("priority", "high")
        by_priority[priority].append(vip)

    return {
        "success": True,
        "account_id": account_id,
        "vips": vips,
        "by_priority": by_priority,
        "count": len(vips),
    }


async def is_vip(account_id: str, email: str) -> bool:
    """
    Check if an email is in the VIP list.

    Args:
        account_id: Account to check
        email: Email address to check

    Returns:
        True if email is a VIP, False otherwise
    """
    _ensure_vip_tables()

    email = email.lower().strip()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM office_vip_contacts WHERE account_id = ? AND email = ?",
        (account_id, email),
    )

    return cursor.fetchone() is not None


async def get_vip_settings(account_id: str, email: str) -> dict[str, Any]:
    """
    Get VIP settings for a specific contact.

    Args:
        account_id: Account to check
        email: Email address to get settings for

    Returns:
        dict with VIP settings or error if not found
    """
    _ensure_vip_tables()

    email = email.lower().strip()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM office_vip_contacts WHERE account_id = ? AND email = ?",
        (account_id, email),
    )
    row = cursor.fetchone()

    if not row:
        return {
            "success": False,
            "is_vip": False,
            "error": f"{email} is not a VIP contact",
        }

    return {
        "success": True,
        "is_vip": True,
        **dict(row),
    }


async def update_vip(
    account_id: str,
    email: str,
    **updates: Any,
) -> dict[str, Any]:
    """
    Update VIP settings for a contact.

    Args:
        account_id: Account to update VIP in
        email: Email address to update
        **updates: Fields to update (name, priority, always_notify, bypass_focus, notes)

    Returns:
        dict with updated VIP settings
    """
    _ensure_vip_tables()

    email = email.lower().strip()

    # Validate priority if provided
    if "priority" in updates and updates["priority"] not in PRIORITY_LEVELS:
        return {
            "success": False,
            "error": f"Invalid priority. Must be one of: {', '.join(PRIORITY_LEVELS)}",
        }

    conn = get_connection()
    cursor = conn.cursor()

    # Check if exists
    cursor.execute(
        "SELECT id FROM office_vip_contacts WHERE account_id = ? AND email = ?",
        (account_id, email),
    )

    if not cursor.fetchone():
        return {
            "success": False,
            "error": f"VIP contact {email} not found",
        }

    # Build update query
    allowed_fields = {"name", "priority", "always_notify", "bypass_focus", "notes"}
    update_fields = {k: v for k, v in updates.items() if k in allowed_fields}

    if not update_fields:
        return {
            "success": False,
            "error": "No valid fields to update",
        }

    update_fields["updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in update_fields)
    values = list(update_fields.values()) + [account_id, email]

    cursor.execute(
        f"UPDATE office_vip_contacts SET {set_clause} WHERE account_id = ? AND email = ?",
        values,
    )
    conn.commit()

    # Return updated settings
    return await get_vip_settings(account_id, email)


async def suggest_vips(account_id: str, limit: int = 10) -> dict[str, Any]:
    """
    Analyze email history and suggest frequent/important contacts.

    Looks at email cache to find contacts with high interaction counts
    that aren't already VIPs.

    Args:
        account_id: Account to analyze
        limit: Maximum number of suggestions

    Returns:
        dict with list of suggested contacts
    """
    _ensure_vip_tables()

    conn = get_connection()
    cursor = conn.cursor()

    # Get existing VIPs to exclude
    cursor.execute(
        "SELECT email FROM office_vip_contacts WHERE account_id = ?",
        (account_id,),
    )
    existing_vips = {row["email"].lower() for row in cursor.fetchall()}

    # Analyze email cache for frequent senders
    cursor.execute(
        """
        SELECT
            sender,
            COUNT(*) as interaction_count,
            MAX(received_at) as last_interaction,
            COUNT(CASE WHEN is_starred THEN 1 END) as starred_count
        FROM office_email_cache
        WHERE account_id = ?
        GROUP BY sender
        ORDER BY interaction_count DESC, starred_count DESC
        LIMIT ?
        """,
        (account_id, limit * 3),
    )
    rows = cursor.fetchall()

    suggestions = []
    for row in rows:
        sender = row["sender"]

        # Extract email from "Name <email>" format if needed
        email = sender
        if "<" in sender and ">" in sender:
            email = sender.split("<")[1].split(">")[0]

        email = email.lower().strip()

        # Skip if already a VIP
        if email in existing_vips:
            continue

        # Determine suggested reason
        interaction_count = row["interaction_count"]
        starred_count = row["starred_count"] or 0
        reasons = []

        if interaction_count >= 20:
            reasons.append(f"{interaction_count} emails")
        if starred_count >= 3:
            reasons.append(f"{starred_count} starred")

        if not reasons:
            reasons.append(f"{interaction_count} emails")

        suggestions.append({
            "email": email,
            "sender_display": sender,
            "interaction_count": interaction_count,
            "starred_count": starred_count,
            "last_interaction": row["last_interaction"],
            "reason": ", ".join(reasons),
        })

        if len(suggestions) >= limit:
            break

    return {
        "success": True,
        "account_id": account_id,
        "suggestions": suggestions,
        "count": len(suggestions),
    }


async def record_interaction(account_id: str, email: str) -> dict[str, Any]:
    """
    Record an interaction with a VIP contact.

    Updates interaction count and last interaction time.

    Args:
        account_id: Account ID
        email: VIP email address

    Returns:
        dict with updated interaction info
    """
    _ensure_vip_tables()

    email = email.lower().strip()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, interaction_count FROM office_vip_contacts WHERE account_id = ? AND email = ?",
        (account_id, email),
    )
    row = cursor.fetchone()

    if not row:
        return {
            "success": False,
            "error": f"{email} is not a VIP contact",
        }

    new_count = (row["interaction_count"] or 0) + 1
    now = datetime.now().isoformat()

    cursor.execute(
        """
        UPDATE office_vip_contacts
        SET interaction_count = ?,
            last_interaction = ?,
            updated_at = ?
        WHERE account_id = ? AND email = ?
        """,
        (new_count, now, now, account_id, email),
    )
    conn.commit()

    return {
        "success": True,
        "email": email,
        "interaction_count": new_count,
        "last_interaction": now,
    }


def main() -> None:
    """CLI entry point for VIP contact management."""
    parser = argparse.ArgumentParser(
        description="VIP Contact Manager for Office Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add a VIP contact
  python contact_manager.py --account-id <id> --add-vip "boss@company.com" --name "My Boss" --priority critical

  # Remove a VIP contact
  python contact_manager.py --account-id <id> --remove-vip "old@example.com"

  # List all VIP contacts
  python contact_manager.py --account-id <id> --list-vips

  # Check if someone is a VIP
  python contact_manager.py --account-id <id> --check-vip "someone@example.com"

  # Get VIP suggestions based on email history
  python contact_manager.py --account-id <id> --suggest-vips
        """,
    )

    parser.add_argument("--account-id", required=True, help="Account ID")

    # Actions (mutually exclusive)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--add-vip", metavar="EMAIL", help="Add a VIP contact")
    actions.add_argument("--remove-vip", metavar="EMAIL", help="Remove a VIP contact")
    actions.add_argument("--list-vips", action="store_true", help="List all VIP contacts")
    actions.add_argument("--check-vip", metavar="EMAIL", help="Check if email is a VIP")
    actions.add_argument(
        "--suggest-vips", action="store_true", help="Suggest VIPs based on email history"
    )
    actions.add_argument("--update-vip", metavar="EMAIL", help="Update VIP settings")

    # VIP options
    parser.add_argument("--name", help="Display name for VIP")
    parser.add_argument(
        "--priority",
        choices=PRIORITY_LEVELS,
        default="high",
        help="Priority level (default: high)",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Disable always-notify",
    )
    parser.add_argument(
        "--no-bypass-focus",
        action="store_true",
        help="Don't bypass focus mode",
    )
    parser.add_argument("--notes", help="Additional notes about the VIP")
    parser.add_argument(
        "--limit", type=int, default=10, help="Max suggestions (for --suggest-vips)"
    )

    args = parser.parse_args()
    result = None

    if args.add_vip:
        result = asyncio.run(
            add_vip(
                args.account_id,
                args.add_vip,
                name=args.name,
                priority=args.priority,
                always_notify=not args.no_notify,
                bypass_focus=not args.no_bypass_focus,
                notes=args.notes,
            )
        )

    elif args.remove_vip:
        result = asyncio.run(remove_vip(args.account_id, args.remove_vip))

    elif args.list_vips:
        result = asyncio.run(list_vips(args.account_id))

    elif args.check_vip:
        result = asyncio.run(get_vip_settings(args.account_id, args.check_vip))

    elif args.suggest_vips:
        result = asyncio.run(suggest_vips(args.account_id, limit=args.limit))

    elif args.update_vip:
        updates = {}
        if args.name:
            updates["name"] = args.name
        if args.priority and args.priority != "high":
            updates["priority"] = args.priority
        if args.notes:
            updates["notes"] = args.notes
        if args.no_notify:
            updates["always_notify"] = False
        if args.no_bypass_focus:
            updates["bypass_focus"] = False

        result = asyncio.run(update_vip(args.account_id, args.update_vip, **updates))

    if result:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
