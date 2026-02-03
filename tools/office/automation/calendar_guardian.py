"""
Tool: Calendar Guardian
Purpose: Protect calendar and auto-respond to meeting requests for Level 5 (Autonomous)

This module protects the user's calendar by automatically handling meeting requests,
defending focus blocks, and suggesting alternative times when declining.

ADHD Philosophy:
    Calendar management is a constant source of context-switching and decision fatigue.
    Calendar Guardian automates routine meeting decisions while protecting precious
    focus time. VIP contacts can always break through, and users maintain full control
    through policies and emergency pause.

Key Features:
    - Auto-accept/decline based on policies
    - Focus block protection
    - VIP override support
    - Smart alternative time suggestions
    - Meeting response messages

Usage:
    from tools.office.automation.calendar_guardian import (
        process_meeting_request,
        protect_focus_blocks,
        suggest_meeting_alternatives,
        auto_respond_to_meeting,
    )

    # Process a meeting request
    result = await process_meeting_request("account-123", event_data)

    # Check and protect focus blocks
    result = await protect_focus_blocks("account-123")

    # Get alternative times for a declined meeting
    result = await suggest_meeting_alternatives("account-123", declined_event)

CLI:
    python tools/office/automation/calendar_guardian.py process <account-id> --event-id <id>
    python tools/office/automation/calendar_guardian.py protect <account-id>
    python tools/office/automation/calendar_guardian.py suggest <account-id> --event-id <id>
    python tools/office/automation/calendar_guardian.py respond <account-id> --event-id <id> --response accept
"""

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection
from tools.office.automation.emergency import check_pause_status
from tools.office.models import CalendarEvent, IntegrationLevel
from tools.office.policies import (
    ActionType,
    Policy,
    PolicyAction,
    PolicyType,
    ensure_policy_tables,
)
from tools.office.policies.matcher import (
    match_all_conditions,
    prepare_calendar_event_data,
)


@dataclass
class TimeSlot:
    """A suggested meeting time slot."""

    start: datetime
    end: datetime
    score: float  # 0-1 preference score
    reason: str  # Why this slot is good

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "score": self.score,
            "reason": self.reason,
        }


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
    """Log a policy execution event."""
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


def _get_focus_blocks(account_id: str, start_date: datetime, end_date: datetime) -> list[dict]:
    """
    Get focus blocks from calendar.

    Focus blocks are identified by:
    - Events with "focus" in the title (case-insensitive)
    - Events marked as "busy" with no attendees
    - Events tagged with focus label

    Args:
        account_id: Account ID
        start_date: Start of range
        end_date: End of range

    Returns:
        List of focus block events
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get events from cache that look like focus blocks
    cursor.execute(
        """
        SELECT * FROM office_calendar_cache
        WHERE account_id = ?
          AND start_time >= ?
          AND start_time <= ?
          AND (
            LOWER(title) LIKE '%focus%'
            OR LOWER(title) LIKE '%deep work%'
            OR LOWER(title) LIKE '%no meetings%'
            OR (attendees IS NULL OR attendees = '[]')
          )
        ORDER BY start_time ASC
        """,
        (account_id, start_date.isoformat(), end_date.isoformat()),
    )
    rows = cursor.fetchall()
    conn.close()

    focus_blocks = []
    for row in rows:
        event = dict(row)
        # Only include events that are likely focus blocks
        title_lower = (event.get("title") or "").lower()
        if "focus" in title_lower or "deep work" in title_lower or "no meetings" in title_lower:
            focus_blocks.append(event)

    return focus_blocks


def _check_conflicts(
    account_id: str,
    start_time: datetime,
    end_time: datetime,
    exclude_event_id: str | None = None,
) -> list[dict]:
    """
    Check for conflicting events.

    Args:
        account_id: Account ID
        start_time: Start of time range
        end_time: End of time range
        exclude_event_id: Event ID to exclude from conflict check

    Returns:
        List of conflicting events
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT * FROM office_calendar_cache
        WHERE account_id = ?
          AND NOT (end_time <= ? OR start_time >= ?)
          AND status != 'cancelled'
    """
    params = [account_id, start_time.isoformat(), end_time.isoformat()]

    if exclude_event_id:
        query += " AND event_id != ?"
        params.append(exclude_event_id)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


async def process_meeting_request(
    account_id: str,
    event: dict[str, Any] | CalendarEvent,
) -> dict[str, Any]:
    """
    Process an incoming meeting request against policies.

    This evaluates calendar policies and determines whether to accept,
    decline, mark as tentative, or prompt the user.

    Args:
        account_id: Office account ID
        event: Calendar event data (dict or CalendarEvent object)

    Returns:
        {
            "action": "accept" | "decline" | "tentative" | "prompt",
            "reason": str,
            "policy_id": str | None,
            "is_vip": bool,
            "alternatives": list[TimeSlot] | None,  # If declining
        }
    """
    # Check emergency pause
    if check_pause_status(account_id):
        return {
            "action": "prompt",
            "reason": "Automation paused - manual decision required",
            "policy_id": None,
            "is_vip": False,
            "alternatives": None,
        }

    # Get account and verify level
    account = _get_account(account_id)
    if not account:
        return {
            "action": "prompt",
            "reason": "Account not found",
            "policy_id": None,
            "is_vip": False,
            "alternatives": None,
        }

    if account["integration_level"] < IntegrationLevel.AUTONOMOUS.value:
        return {
            "action": "prompt",
            "reason": f"Requires Level 5. Current: {account['integration_level']}",
            "policy_id": None,
            "is_vip": False,
            "alternatives": None,
        }

    # Convert to dict if CalendarEvent object
    if isinstance(event, CalendarEvent):
        event_data = event.to_dict()
    else:
        event_data = event

    # Prepare event data for matching
    prepared_data = prepare_calendar_event_data(event_data)

    # Get organizer email
    organizer = prepared_data.get("organizer", "")
    if isinstance(organizer, dict):
        organizer = organizer.get("email", "")

    # Check VIP status
    vip_info = _is_vip(account_id, organizer)
    is_vip = vip_info is not None

    if is_vip:
        # VIP meetings are always accepted (unless no conflicts)
        if vip_info.get("bypass_focus", True):
            _log_policy_execution(
                account_id=account_id,
                policy_id="vip_handler",
                trigger_type="calendar",
                trigger_data={"event_id": event_data.get("event_id"), "organizer": organizer},
                actions_taken=[{"action": "accept", "reason": "VIP contact"}],
                result="success",
            )

            return {
                "action": "accept",
                "reason": f"VIP contact: {vip_info.get('name', organizer)}",
                "policy_id": "vip_handler",
                "is_vip": True,
                "alternatives": None,
            }

    # Check for focus block conflicts
    start_time = prepared_data.get("start_time")
    end_time = prepared_data.get("end_time")

    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)

    if start_time and end_time:
        focus_blocks = _get_focus_blocks(account_id, start_time - timedelta(hours=1), end_time + timedelta(hours=1))

        for block in focus_blocks:
            block_start = datetime.fromisoformat(block["start_time"])
            block_end = datetime.fromisoformat(block["end_time"])

            # Check for overlap
            if not (end_time <= block_start or start_time >= block_end):
                prepared_data["conflicts_with_focus"] = True
                prepared_data["conflicting_focus_block"] = block.get("title", "Focus Time")
                break

    # Get applicable policies
    policies = _get_enabled_policies(account_id, PolicyType.CALENDAR.value)

    # Evaluate policies in priority order
    matched_policy: Policy | None = None
    for policy in policies:
        if match_all_conditions(policy.conditions, prepared_data, account_id):
            matched_policy = policy
            break

    if not matched_policy:
        # No matching policy - prompt user
        return {
            "action": "prompt",
            "reason": "No matching policy - manual decision required",
            "policy_id": None,
            "is_vip": False,
            "alternatives": None,
        }

    # Determine action from policy
    action = "prompt"
    reason = "Policy matched"
    alternatives = None

    for policy_action in matched_policy.actions:
        action_type = policy_action.action_type

        if action_type == ActionType.ACCEPT:
            action = "accept"
            reason = f"Policy: {matched_policy.name}"
            break

        if action_type == ActionType.DECLINE:
            action = "decline"
            reason = f"Policy: {matched_policy.name}"

            # Get alternative suggestions if declining
            if start_time and end_time:
                duration = int((end_time - start_time).total_seconds() / 60)
                alt_result = await suggest_meeting_alternatives(
                    account_id, event_data, days_ahead=7
                )
                if alt_result.get("alternatives"):
                    alternatives = alt_result["alternatives"][:3]
            break

        if action_type == ActionType.TENTATIVE:
            action = "tentative"
            reason = f"Policy: {matched_policy.name}"
            break

        if action_type == ActionType.SUGGEST_ALTERNATIVE:
            action = "decline"
            reason = f"Policy: {matched_policy.name} - suggesting alternatives"
            if start_time and end_time:
                alt_result = await suggest_meeting_alternatives(
                    account_id, event_data, days_ahead=7
                )
                if alt_result.get("alternatives"):
                    alternatives = alt_result["alternatives"][:3]
            break

    # Log the execution
    _log_policy_execution(
        account_id=account_id,
        policy_id=matched_policy.id,
        trigger_type="calendar",
        trigger_data={"event_id": event_data.get("event_id"), "title": event_data.get("title")},
        actions_taken=[{"action": action, "reason": reason}],
        result="success",
    )

    return {
        "action": action,
        "reason": reason,
        "policy_id": matched_policy.id,
        "is_vip": is_vip,
        "alternatives": [a.to_dict() if isinstance(a, TimeSlot) else a for a in alternatives] if alternatives else None,
    }


async def protect_focus_blocks(account_id: str) -> dict[str, Any]:
    """
    Scan calendar for conflicts with focus blocks and suggest resolutions.

    This proactively identifies meetings that conflict with focus time
    and suggests what to do about them.

    Args:
        account_id: Office account ID

    Returns:
        {
            "conflicts": list[{event, focus_block, suggestion}],
            "suggestions": list[str],
            "protected_blocks": int,
        }
    """
    # Check emergency pause
    if check_pause_status(account_id):
        return {
            "conflicts": [],
            "suggestions": [],
            "protected_blocks": 0,
            "error": "Automation paused",
        }

    # Get account
    account = _get_account(account_id)
    if not account:
        return {
            "conflicts": [],
            "suggestions": [],
            "protected_blocks": 0,
            "error": "Account not found",
        }

    # Look ahead 7 days
    now = datetime.now()
    end_date = now + timedelta(days=7)

    # Get focus blocks
    focus_blocks = _get_focus_blocks(account_id, now, end_date)

    if not focus_blocks:
        return {
            "conflicts": [],
            "suggestions": ["No focus blocks found. Consider scheduling dedicated focus time."],
            "protected_blocks": 0,
        }

    conflicts = []
    suggestions = []

    for block in focus_blocks:
        block_start = datetime.fromisoformat(block["start_time"])
        block_end = datetime.fromisoformat(block["end_time"])

        # Find conflicts
        conflicting_events = _check_conflicts(
            account_id, block_start, block_end, exclude_event_id=block.get("event_id")
        )

        for event in conflicting_events:
            event_title = event.get("title", "Unnamed event")
            block_title = block.get("title", "Focus Time")

            # Check if organizer is VIP
            organizer = event.get("organizer") or ""
            if isinstance(organizer, str) and organizer:
                vip_info = _is_vip(account_id, organizer)
                if vip_info:
                    suggestion = f"VIP meeting '{event_title}' conflicts with {block_title} - consider accepting"
                else:
                    suggestion = f"Consider declining '{event_title}' or moving {block_title}"
            else:
                suggestion = f"Consider declining '{event_title}' or moving {block_title}"

            conflicts.append({
                "event": {
                    "id": event.get("event_id"),
                    "title": event_title,
                    "start": event.get("start_time"),
                    "end": event.get("end_time"),
                },
                "focus_block": {
                    "id": block.get("event_id"),
                    "title": block_title,
                    "start": block.get("start_time"),
                    "end": block.get("end_time"),
                },
                "suggestion": suggestion,
            })

    if conflicts:
        suggestions.append(f"Found {len(conflicts)} conflicts with focus time.")
        suggestions.append("Consider declining non-essential meetings or rescheduling focus blocks.")
    else:
        suggestions.append("All focus blocks are protected!")

    return {
        "conflicts": conflicts,
        "suggestions": suggestions,
        "protected_blocks": len(focus_blocks),
    }


async def suggest_meeting_alternatives(
    account_id: str,
    declined_event: dict[str, Any] | CalendarEvent,
    days_ahead: int = 7,
) -> dict[str, Any]:
    """
    Find alternative times when declining a meeting.

    This looks at the user's calendar and suggests good times
    for the meeting to be rescheduled.

    Args:
        account_id: Office account ID
        declined_event: The event being declined
        days_ahead: How many days ahead to look for alternatives

    Returns:
        {
            "alternatives": list[TimeSlot],
            "original_duration": int,  # minutes
        }
    """
    # Import calendar reader
    from tools.office.calendar.reader import find_free_slots

    # Convert to dict if CalendarEvent object
    if isinstance(declined_event, CalendarEvent):
        event_data = declined_event.to_dict()
    else:
        event_data = declined_event

    # Calculate duration
    start_time = event_data.get("start_time")
    end_time = event_data.get("end_time")

    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)

    if start_time and end_time:
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
    else:
        duration_minutes = 30  # Default to 30 minutes

    # Find free slots
    free_result = await find_free_slots(
        account_id=account_id,
        duration_minutes=duration_minutes,
        start_date=datetime.now(),
        end_date=datetime.now() + timedelta(days=days_ahead),
    )

    if not free_result.get("success"):
        return {
            "alternatives": [],
            "original_duration": duration_minutes,
            "error": free_result.get("error", "Failed to find free slots"),
        }

    free_slots = free_result.get("free_slots", [])

    # Score and convert slots to TimeSlot objects
    alternatives = []
    for slot in free_slots[:10]:  # Limit to top 10
        slot_start = datetime.fromisoformat(slot["start"])
        slot_end = datetime.fromisoformat(slot["end"])

        # Score based on various factors
        score = 1.0

        # Prefer morning slots (less context-switching later in day)
        hour = slot_start.hour
        if 9 <= hour <= 11:
            score *= 1.2
            reason = "Morning slot - good for collaboration"
        elif 14 <= hour <= 16:
            score *= 1.1
            reason = "Afternoon slot - post-lunch energy"
        elif hour < 9:
            score *= 0.8
            reason = "Early morning - may conflict with routines"
        elif hour > 17:
            score *= 0.7
            reason = "Late day - may run into personal time"
        else:
            reason = "Available time slot"

        # Prefer slots not too far in the future
        days_out = (slot_start.date() - datetime.now().date()).days
        if days_out == 0:
            score *= 1.3
            reason = "Same day availability"
        elif days_out == 1:
            score *= 1.2
            reason = "Tomorrow"
        elif days_out > 5:
            score *= 0.9

        # Cap score at 1.0
        score = min(score, 1.0)

        alternatives.append(TimeSlot(
            start=slot_start,
            end=min(slot_end, slot_start + timedelta(minutes=duration_minutes)),
            score=round(score, 2),
            reason=reason,
        ))

    # Sort by score descending
    alternatives.sort(key=lambda x: x.score, reverse=True)

    return {
        "alternatives": [a.to_dict() for a in alternatives],
        "original_duration": duration_minutes,
    }


async def auto_respond_to_meeting(
    account_id: str,
    event_id: str,
    response: str,
    message: str | None = None,
) -> dict[str, Any]:
    """
    Send an automatic response to a meeting request.

    Args:
        account_id: Office account ID
        event_id: Provider event ID
        response: Response type ("accept", "decline", "tentative")
        message: Optional message to include with response

    Returns:
        {
            "success": bool,
            "action_id": str | None,
            "response": str,
        }
    """
    valid_responses = {"accept", "decline", "tentative"}
    if response not in valid_responses:
        return {
            "success": False,
            "error": f"Invalid response: {response}. Must be one of: {', '.join(valid_responses)}",
        }

    # Check emergency pause
    if check_pause_status(account_id):
        return {
            "success": False,
            "error": "Automation paused",
        }

    # Get account
    account = _get_account(account_id)
    if not account:
        return {
            "success": False,
            "error": "Account not found",
        }

    if account["integration_level"] < IntegrationLevel.AUTONOMOUS.value:
        return {
            "success": False,
            "error": f"Requires Level 5. Current: {account['integration_level']}",
        }

    # Import action queue
    from tools.office.actions.queue import queue_action

    # Map response to action type
    action_type_map = {
        "accept": "accept_meeting",
        "decline": "decline_meeting",
        "tentative": "tentative_meeting",
    }

    action_data = {
        "event_id": event_id,
        "response": response,
        "message": message,
    }

    # Queue the action
    result = await queue_action(
        account_id=account_id,
        action_type=action_type_map[response],
        action_data=action_data,
        undo_window_seconds=60,
    )

    if not result.get("success"):
        return result

    return {
        "success": True,
        "action_id": result.get("action_id"),
        "response": response,
    }


def main() -> None:
    """CLI entry point for calendar guardian."""
    parser = argparse.ArgumentParser(
        description="Calendar Guardian for Level 5 Office Integration"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # process command
    process_parser = subparsers.add_parser("process", help="Process a meeting request")
    process_parser.add_argument("account_id", help="Account ID")
    process_parser.add_argument("--event-id", required=True, help="Event ID")

    # protect command
    protect_parser = subparsers.add_parser("protect", help="Check focus block protection")
    protect_parser.add_argument("account_id", help="Account ID")

    # suggest command
    suggest_parser = subparsers.add_parser("suggest", help="Suggest alternative times")
    suggest_parser.add_argument("account_id", help="Account ID")
    suggest_parser.add_argument("--event-id", required=True, help="Event ID")
    suggest_parser.add_argument("--days", type=int, default=7, help="Days to look ahead")

    # respond command
    respond_parser = subparsers.add_parser("respond", help="Auto-respond to meeting")
    respond_parser.add_argument("account_id", help="Account ID")
    respond_parser.add_argument("--event-id", required=True, help="Event ID")
    respond_parser.add_argument("--response", required=True, choices=["accept", "decline", "tentative"])
    respond_parser.add_argument("--message", help="Optional response message")

    args = parser.parse_args()

    if args.command == "process":
        # Need to fetch the event first
        from tools.office.calendar.reader import get_event

        event_result = asyncio.run(get_event(args.account_id, args.event_id))
        if not event_result.get("success"):
            print(f"Error: {event_result.get('error')}")
            sys.exit(1)

        result = asyncio.run(process_meeting_request(args.account_id, event_result["event"]))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "protect":
        result = asyncio.run(protect_focus_blocks(args.account_id))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "suggest":
        # Need to fetch the event first
        from tools.office.calendar.reader import get_event

        event_result = asyncio.run(get_event(args.account_id, args.event_id))
        if not event_result.get("success"):
            print(f"Error: {event_result.get('error')}")
            sys.exit(1)

        result = asyncio.run(suggest_meeting_alternatives(
            args.account_id, event_result["event"], days_ahead=args.days
        ))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "respond":
        result = asyncio.run(auto_respond_to_meeting(
            args.account_id,
            args.event_id,
            args.response,
            message=args.message,
        ))
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
