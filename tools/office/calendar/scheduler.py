"""
Tool: Meeting Scheduler
Purpose: High-level interface for meeting scheduling with ADHD features

This tool provides the unified Layer 3 (Collaborative) interface for meeting
proposals. It creates proposals locally first, checks for conflicts, and
only creates actual calendar events when the user confirms.

Key ADHD Features:
- Full attendee list shown before confirmation
- Conflict checking before proposing
- Suggested meeting times with availability checking
- No auto-scheduling (user must explicitly confirm)

Usage:
    # Propose a meeting
    python scheduler.py --account-id <id> --propose --title "Team Sync" --start "2026-02-05T10:00:00" --duration 30

    # List pending proposals
    python scheduler.py --account-id <id> --list-pending

    # Confirm a meeting (creates actual calendar event)
    python scheduler.py --account-id <id> --confirm <proposal-id>

    # Suggest meeting times
    python scheduler.py --account-id <id> --suggest --duration 30 --days 7

    # Cancel a proposal
    python scheduler.py --account-id <id> --cancel <proposal-id>

Dependencies:
    - aiohttp (for provider API calls)
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
        access_token=account.get("access_token_encrypted"),
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


async def _check_conflicts(
    provider,
    start_time: datetime,
    end_time: datetime,
) -> list[dict]:
    """Check for calendar conflicts in the given time range."""
    conflicts = []

    try:
        result = await provider.get_events(
            start_date=start_time - timedelta(minutes=15),
            end_date=end_time + timedelta(minutes=15),
        )

        if result.get("success"):
            for event in result.get("events", []):
                event_start = event.start_time
                event_end = event.end_time

                # Check for overlap
                if event_start < end_time and event_end > start_time:
                    conflicts.append({
                        "event_id": event.event_id,
                        "title": event.title,
                        "start_time": event_start.isoformat(),
                        "end_time": event_end.isoformat(),
                    })

    except Exception as e:
        print(f"Warning: Could not check conflicts: {e}")

    return conflicts


async def propose_meeting(
    account_id: str,
    title: str,
    start_time: datetime,
    end_time: datetime | None = None,
    duration_minutes: int = 30,
    attendees: list[str] | None = None,
    description: str = "",
    location: str = "",
    timezone: str = "UTC",
    check_availability: bool = True,
) -> dict[str, Any]:
    """
    Propose a new meeting (does NOT create calendar event yet).

    Creates a local proposal that must be confirmed before the actual
    calendar event is created.

    Args:
        account_id: Office account ID
        title: Meeting title
        start_time: Meeting start time
        end_time: Meeting end time (optional, calculated from duration if not provided)
        duration_minutes: Meeting duration in minutes (default 30)
        attendees: List of attendee email addresses
        description: Meeting description
        location: Meeting location
        timezone: Timezone for the meeting
        check_availability: Whether to check for conflicts

    Returns:
        {
            "success": bool,
            "proposal_id": str,
            "conflicts": list,
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
            "error": f"Meeting scheduling requires Level 3+. Current level: {account['integration_level']}",
        }

    # Calculate end time if not provided
    if end_time is None:
        end_time = start_time + timedelta(minutes=duration_minutes)

    # Check for conflicts
    conflicts = []
    if check_availability:
        try:
            provider = _get_provider(account)
            conflicts = await _check_conflicts(provider, start_time, end_time)
        except Exception as e:
            print(f"Warning: Could not check availability: {e}")

    # Create proposal in database
    proposal_id = str(uuid.uuid4())
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO office_meeting_drafts (
            id, account_id, title, description, location,
            start_time, end_time, timezone, attendees, organizer_email,
            status, conflicts, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            proposal_id,
            account_id,
            title,
            description,
            location,
            start_time.isoformat(),
            end_time.isoformat(),
            timezone,
            json.dumps(attendees) if attendees else None,
            account.get("email_address"),
            "proposed",
            json.dumps(conflicts) if conflicts else None,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "proposal_id": proposal_id,
        "conflicts": conflicts,
        "has_conflicts": len(conflicts) > 0,
    }


async def get_pending_proposals(
    account_id: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Get list of pending meeting proposals.

    Args:
        account_id: Office account ID
        limit: Maximum number of proposals to return

    Returns:
        {
            "success": bool,
            "proposals": list,
            "total": int,
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM office_meeting_drafts
        WHERE account_id = ? AND status = 'proposed'
        ORDER BY start_time ASC
        LIMIT ?
        """,
        (account_id, limit),
    )
    rows = cursor.fetchall()

    # Get total count
    cursor.execute(
        "SELECT COUNT(*) FROM office_meeting_drafts WHERE account_id = ? AND status = 'proposed'",
        (account_id,),
    )
    total = cursor.fetchone()[0]
    conn.close()

    proposals = []
    for row in rows:
        proposal = dict(row)
        # Parse JSON fields
        if proposal.get("attendees"):
            proposal["attendees"] = json.loads(proposal["attendees"])
        if proposal.get("conflicts"):
            proposal["conflicts"] = json.loads(proposal["conflicts"])
        proposals.append(proposal)

    return {
        "success": True,
        "proposals": proposals,
        "total": total,
    }


async def get_proposal(proposal_id: str) -> dict[str, Any]:
    """
    Get details of a specific proposal.

    Args:
        proposal_id: Proposal ID

    Returns:
        {
            "success": bool,
            "proposal": dict,
        }
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM office_meeting_drafts WHERE id = ?",
        (proposal_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": f"Proposal not found: {proposal_id}"}

    proposal = dict(row)
    # Parse JSON fields
    if proposal.get("attendees"):
        proposal["attendees"] = json.loads(proposal["attendees"])
    if proposal.get("conflicts"):
        proposal["conflicts"] = json.loads(proposal["conflicts"])

    return {"success": True, "proposal": proposal}


async def confirm_meeting(proposal_id: str) -> dict[str, Any]:
    """
    Confirm a meeting proposal and create the actual calendar event.

    This sends invites to all attendees.

    Args:
        proposal_id: Proposal ID

    Returns:
        {
            "success": bool,
            "event_id": str,  # Provider's event ID
        }
    """
    # Get proposal
    result = await get_proposal(proposal_id)
    if not result.get("success"):
        return result

    proposal = result["proposal"]

    # Only proposed meetings can be confirmed
    if proposal["status"] != "proposed":
        return {"success": False, "error": f"Cannot confirm proposal with status: {proposal['status']}"}

    # Get account
    account = _get_account(proposal["account_id"])
    if not account:
        return {"success": False, "error": "Account not found"}

    # Create event via provider
    try:
        provider = _get_provider(account)

        # Parse times
        start_time = datetime.fromisoformat(proposal["start_time"])
        end_time = datetime.fromisoformat(proposal["end_time"])

        result = await provider.create_event(
            title=proposal["title"],
            start_time=start_time,
            end_time=end_time,
            description=proposal.get("description", ""),
            location=proposal.get("location", ""),
            attendees=proposal.get("attendees"),
        )

        if not result.get("success"):
            return result

        event_id = result.get("event_id")

    except Exception as e:
        return {"success": False, "error": f"Provider error: {e!s}"}

    # Update proposal status
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE office_meeting_drafts
        SET status = 'confirmed', provider_event_id = ?, confirmed_at = ?
        WHERE id = ?
        """,
        (event_id, datetime.now().isoformat(), proposal_id),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "event_id": event_id,
        "status": "confirmed",
    }


async def cancel_proposal(proposal_id: str) -> dict[str, Any]:
    """
    Cancel a meeting proposal.

    Args:
        proposal_id: Proposal ID

    Returns:
        {
            "success": bool,
        }
    """
    # Get proposal
    result = await get_proposal(proposal_id)
    if not result.get("success"):
        return result

    proposal = result["proposal"]

    # If already confirmed, need to delete the calendar event too
    if proposal["status"] == "confirmed" and proposal.get("provider_event_id"):
        account = _get_account(proposal["account_id"])
        if account and account["integration_level"] >= 4:
            try:
                provider = _get_provider(account)
                await provider.delete_event(proposal["provider_event_id"])
            except Exception as e:
                print(f"Warning: Could not delete calendar event: {e}")

    # Update status
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE office_meeting_drafts SET status = 'cancelled' WHERE id = ?",
        (proposal_id,),
    )
    conn.commit()
    conn.close()

    return {"success": True}


async def suggest_meeting_times(
    account_id: str,
    duration_minutes: int = 30,
    attendee_emails: list[str] | None = None,
    days_ahead: int = 7,
    preferred_hours_start: int = 9,
    preferred_hours_end: int = 17,
) -> dict[str, Any]:
    """
    Suggest available meeting times based on calendar availability.

    Args:
        account_id: Office account ID
        duration_minutes: Meeting duration in minutes
        attendee_emails: Optional list of attendee emails to check (requires FreeBusy API)
        days_ahead: Number of days to look ahead
        preferred_hours_start: Start of preferred meeting hours (0-23)
        preferred_hours_end: End of preferred meeting hours (0-23)

    Returns:
        {
            "success": bool,
            "suggestions": list[{
                "start": str,
                "end": str,
                "score": float,  # 0-1, higher is better
                "reason": str,
            }],
        }
    """
    # Get account
    account = _get_account(account_id)
    if not account:
        return {"success": False, "error": f"Account not found: {account_id}"}

    # Get existing events
    try:
        provider = _get_provider(account)
        now = datetime.now()
        end_date = now + timedelta(days=days_ahead)

        result = await provider.get_events(
            start_date=now,
            end_date=end_date,
        )

        if not result.get("success"):
            return result

        existing_events = result.get("events", [])

    except Exception as e:
        return {"success": False, "error": f"Could not fetch calendar: {e!s}"}

    # Build busy periods
    busy_periods = []
    for event in existing_events:
        busy_periods.append((event.start_time, event.end_time))

    # Sort by start time
    busy_periods.sort(key=lambda x: x[0])

    # Find free slots
    suggestions = []
    current = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    while current < end_date and len(suggestions) < 10:
        # Skip non-preferred hours
        if current.hour < preferred_hours_start or current.hour >= preferred_hours_end:
            current = current.replace(hour=preferred_hours_start) + timedelta(days=1 if current.hour >= preferred_hours_end else 0)
            continue

        # Skip weekends (simple heuristic)
        if current.weekday() >= 5:  # Saturday=5, Sunday=6
            current = current + timedelta(days=(7 - current.weekday()))
            continue

        slot_end = current + timedelta(minutes=duration_minutes)

        # Check if slot overlaps with any busy period
        is_free = True
        for busy_start, busy_end in busy_periods:
            if current < busy_end and slot_end > busy_start:
                is_free = False
                # Skip to end of this busy period
                current = busy_end
                break

        if is_free:
            # Score the slot
            # Morning slots score higher (ADHD-friendly - more energy)
            # Mid-week scores higher than Monday/Friday
            hour_score = 1.0 if 9 <= current.hour <= 11 else (0.8 if current.hour < 14 else 0.6)
            day_score = 1.0 if current.weekday() in [1, 2, 3] else 0.8  # Tue-Thu best

            score = (hour_score + day_score) / 2

            reason = []
            if current.hour < 12:
                reason.append("morning slot")
            if current.weekday() in [1, 2, 3]:
                reason.append("mid-week")

            suggestions.append({
                "start": current.isoformat(),
                "end": slot_end.isoformat(),
                "score": round(score, 2),
                "reason": ", ".join(reason) if reason else "available",
            })

            current = slot_end
        else:
            current = current + timedelta(minutes=30)

    # Sort by score
    suggestions.sort(key=lambda x: x["score"], reverse=True)

    return {
        "success": True,
        "suggestions": suggestions[:10],  # Top 10
        "duration_minutes": duration_minutes,
        "days_searched": days_ahead,
    }


async def update_proposal(
    proposal_id: str,
    title: str | None = None,
    description: str | None = None,
    location: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    """
    Update an existing proposal.

    Args:
        proposal_id: Proposal ID
        title: New title (optional)
        description: New description (optional)
        location: New location (optional)
        start_time: New start time (optional)
        end_time: New end time (optional)
        attendees: New attendees (optional)

    Returns:
        {
            "success": bool,
            "proposal": dict,
        }
    """
    # Get existing proposal
    result = await get_proposal(proposal_id)
    if not result.get("success"):
        return result

    proposal = result["proposal"]

    # Only proposed meetings can be updated
    if proposal["status"] != "proposed":
        return {"success": False, "error": f"Cannot update proposal with status: {proposal['status']}"}

    # Build updates
    updates = []
    params = []

    if title is not None:
        updates.append("title = ?")
        params.append(title)

    if description is not None:
        updates.append("description = ?")
        params.append(description)

    if location is not None:
        updates.append("location = ?")
        params.append(location)

    if start_time is not None:
        updates.append("start_time = ?")
        params.append(start_time.isoformat())

    if end_time is not None:
        updates.append("end_time = ?")
        params.append(end_time.isoformat())

    if attendees is not None:
        updates.append("attendees = ?")
        params.append(json.dumps(attendees))

    if not updates:
        return {"success": True, "proposal": proposal, "message": "No changes"}

    params.append(proposal_id)

    # Update database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE office_meeting_drafts SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    conn.close()

    # Return updated proposal
    return await get_proposal(proposal_id)


def main():
    parser = argparse.ArgumentParser(
        description="Meeting Scheduler for Level 3 Office Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Propose a meeting
  python scheduler.py --account-id abc123 --propose --title "Team Sync" --start "2026-02-05T10:00:00" --duration 30

  # List pending proposals
  python scheduler.py --account-id abc123 --list-pending

  # Confirm a meeting
  python scheduler.py --account-id abc123 --confirm proposal-id-123

  # Suggest times
  python scheduler.py --account-id abc123 --suggest --duration 30 --days 7

  # Cancel a proposal
  python scheduler.py --account-id abc123 --cancel proposal-id-123
        """,
    )

    parser.add_argument("--account-id", required=True, help="Office account ID")

    # Actions (mutually exclusive)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--propose", action="store_true", help="Propose a new meeting")
    actions.add_argument("--list-pending", action="store_true", help="List pending proposals")
    actions.add_argument("--get", metavar="PROPOSAL_ID", help="Get proposal details")
    actions.add_argument("--confirm", metavar="PROPOSAL_ID", help="Confirm a proposal")
    actions.add_argument("--cancel", metavar="PROPOSAL_ID", help="Cancel a proposal")
    actions.add_argument("--suggest", action="store_true", help="Suggest meeting times")

    # Propose arguments
    parser.add_argument("--title", help="Meeting title")
    parser.add_argument("--start", help="Start time (ISO format)")
    parser.add_argument("--duration", type=int, default=30, help="Duration in minutes")
    parser.add_argument("--description", default="", help="Meeting description")
    parser.add_argument("--location", default="", help="Meeting location")
    parser.add_argument("--attendees", help="Attendee emails (comma-separated)")
    parser.add_argument("--no-check", action="store_true", help="Skip conflict checking")

    # Suggest arguments
    parser.add_argument("--days", type=int, default=7, help="Days to look ahead")

    # List arguments
    parser.add_argument("--limit", type=int, default=20, help="Max results")

    args = parser.parse_args()

    result = None

    if args.propose:
        if not all([args.title, args.start]):
            print("Error: --title and --start are required for propose")
            sys.exit(1)

        start_time = datetime.fromisoformat(args.start)
        attendee_list = [x.strip() for x in args.attendees.split(",")] if args.attendees else None

        result = asyncio.run(propose_meeting(
            account_id=args.account_id,
            title=args.title,
            start_time=start_time,
            duration_minutes=args.duration,
            attendees=attendee_list,
            description=args.description,
            location=args.location,
            check_availability=not args.no_check,
        ))

    elif args.list_pending:
        result = asyncio.run(get_pending_proposals(
            account_id=args.account_id,
            limit=args.limit,
        ))

    elif args.get:
        result = asyncio.run(get_proposal(args.get))

    elif args.confirm:
        result = asyncio.run(confirm_meeting(args.confirm))

    elif args.cancel:
        result = asyncio.run(cancel_proposal(args.cancel))

    elif args.suggest:
        result = asyncio.run(suggest_meeting_times(
            account_id=args.account_id,
            duration_minutes=args.duration,
            days_ahead=args.days,
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
