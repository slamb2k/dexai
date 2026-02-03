"""
Tool: Calendar Reader
Purpose: Unified interface for reading calendar events across providers

Provides a high-level interface for reading calendar events that works
with any configured provider (Google Calendar or Microsoft Calendar).

Usage:
    python tools/office/calendar/reader.py --account-id <id> --today
    python tools/office/calendar/reader.py --account-id <id> --week
    python tools/office/calendar/reader.py --account-id <id> --event <event-id>
    python tools/office/calendar/reader.py --account-id <id> --availability

Dependencies:
    - aiohttp (for API calls to providers)
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office.email.reader import get_provider_for_account, load_account  # noqa: E402
from tools.office.models import CalendarEvent, IntegrationLevel  # noqa: E402


async def get_events(
    account_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    max_results: int = 50,
) -> dict[str, Any]:
    """
    Get calendar events in a date range.

    Args:
        account_id: Account ID
        start_date: Start of range (default: now)
        end_date: End of range (default: 7 days from now)
        max_results: Maximum events to return

    Returns:
        dict with list of events
    """
    account = load_account(account_id)
    if not account:
        return {"success": False, "error": "Account not found"}

    if account.integration_level < IntegrationLevel.READ_ONLY:
        return {"success": False, "error": "Calendar reading requires Level 2+"}

    provider = get_provider_for_account(account)

    auth_result = await provider.authenticate()
    if not auth_result.get("success"):
        return auth_result

    return await provider.get_events(
        start_date=start_date,
        end_date=end_date,
        max_results=max_results,
    )


async def get_today(account_id: str) -> dict[str, Any]:
    """
    Get today's calendar events.

    Args:
        account_id: Account ID

    Returns:
        dict with today's events
    """
    account = load_account(account_id)
    if not account:
        return {"success": False, "error": "Account not found"}

    if account.integration_level < IntegrationLevel.READ_ONLY:
        return {"success": False, "error": "Calendar reading requires Level 2+"}

    provider = get_provider_for_account(account)

    auth_result = await provider.authenticate()
    if not auth_result.get("success"):
        return auth_result

    result = await provider.get_today_schedule()

    if result.get("success"):
        events = result.get("events", [])
        result["summary"] = generate_day_summary(events)

    return result


async def get_this_week(account_id: str) -> dict[str, Any]:
    """
    Get this week's calendar events.

    Args:
        account_id: Account ID

    Returns:
        dict with this week's events
    """
    now = datetime.now()
    # Start of week (Monday)
    start = now - timedelta(days=now.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    # End of week (Sunday)
    end = start + timedelta(days=7)

    result = await get_events(account_id, start_date=start, end_date=end)

    if result.get("success"):
        events = result.get("events", [])
        result["summary"] = generate_week_summary(events)

    return result


async def get_event(
    account_id: str,
    event_id: str,
) -> dict[str, Any]:
    """
    Get a single calendar event.

    Args:
        account_id: Account ID
        event_id: Event ID

    Returns:
        dict with event details
    """
    account = load_account(account_id)
    if not account:
        return {"success": False, "error": "Account not found"}

    if account.integration_level < IntegrationLevel.READ_ONLY:
        return {"success": False, "error": "Calendar reading requires Level 2+"}

    provider = get_provider_for_account(account)

    auth_result = await provider.authenticate()
    if not auth_result.get("success"):
        return auth_result

    return await provider.get_event(event_id)


async def check_availability(
    account_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, Any]:
    """
    Check free/busy availability.

    Args:
        account_id: Account ID
        start_date: Start of range
        end_date: End of range

    Returns:
        dict with busy periods and free time
    """
    account = load_account(account_id)
    if not account:
        return {"success": False, "error": "Account not found"}

    if account.integration_level < IntegrationLevel.READ_ONLY:
        return {"success": False, "error": "Calendar reading requires Level 2+"}

    provider = get_provider_for_account(account)

    auth_result = await provider.authenticate()
    if not auth_result.get("success"):
        return auth_result

    return await provider.get_availability(start_date, end_date)


async def find_free_slots(
    account_id: str,
    duration_minutes: int = 30,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    working_hours_start: int = 9,
    working_hours_end: int = 17,
) -> dict[str, Any]:
    """
    Find available time slots.

    Args:
        account_id: Account ID
        duration_minutes: Minimum slot duration
        start_date: Start looking from (default: now)
        end_date: Stop looking at (default: 7 days)
        working_hours_start: Start of working day (hour)
        working_hours_end: End of working day (hour)

    Returns:
        dict with available slots
    """
    if not start_date:
        start_date = datetime.now()
    if not end_date:
        end_date = start_date + timedelta(days=7)

    # Get events
    events_result = await get_events(
        account_id,
        start_date=start_date,
        end_date=end_date,
    )

    if not events_result.get("success"):
        return events_result

    events: list[CalendarEvent] = events_result.get("events", [])

    # Build list of busy periods
    busy = []
    for event in events:
        if event.busy_status != "free":
            busy.append((event.start_time, event.end_time))

    # Sort by start time
    busy.sort(key=lambda x: x[0])

    # Find free slots
    free_slots = []
    current_day = start_date.date()
    end_day = end_date.date()

    while current_day <= end_day:
        # Working hours for this day
        day_start = datetime.combine(current_day, datetime.min.time().replace(hour=working_hours_start))
        day_end = datetime.combine(current_day, datetime.min.time().replace(hour=working_hours_end))

        # Skip if in the past
        if day_end < datetime.now():
            current_day += timedelta(days=1)
            continue

        # Find free time in working hours
        slot_start = max(day_start, datetime.now())  # Don't suggest past times

        for busy_start, busy_end in busy:
            if busy_start.date() != current_day:
                continue

            if slot_start < busy_start:
                slot_end = min(busy_start, day_end)
                slot_duration = (slot_end - slot_start).total_seconds() / 60

                if slot_duration >= duration_minutes:
                    free_slots.append({
                        "start": slot_start.isoformat(),
                        "end": slot_end.isoformat(),
                        "duration_minutes": int(slot_duration),
                    })

            slot_start = max(slot_start, busy_end)

        # Check for free time after last meeting
        if slot_start < day_end:
            slot_duration = (day_end - slot_start).total_seconds() / 60
            if slot_duration >= duration_minutes:
                free_slots.append({
                    "start": slot_start.isoformat(),
                    "end": day_end.isoformat(),
                    "duration_minutes": int(slot_duration),
                })

        current_day += timedelta(days=1)

    return {
        "success": True,
        "free_slots": free_slots[:10],  # Return top 10
        "total_slots": len(free_slots),
        "search_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
    }


async def get_next_event(account_id: str) -> dict[str, Any]:
    """
    Get the next upcoming event.

    ADHD-friendly: What's next on my calendar?

    Args:
        account_id: Account ID

    Returns:
        dict with next event
    """
    now = datetime.now()
    result = await get_events(
        account_id,
        start_date=now,
        end_date=now + timedelta(days=1),
        max_results=5,
    )

    if not result.get("success"):
        return result

    events = result.get("events", [])

    # Filter to only upcoming events
    upcoming = [e for e in events if e.start_time > now]

    if not upcoming:
        return {
            "success": True,
            "message": "No more events today!",
            "next_event": None,
        }

    next_event = upcoming[0]
    time_until = next_event.start_time - now
    minutes_until = int(time_until.total_seconds() / 60)

    return {
        "success": True,
        "message": f"Next: {next_event.title} in {minutes_until} minutes",
        "next_event": {
            "title": next_event.title,
            "start": next_event.start_time.isoformat(),
            "end": next_event.end_time.isoformat(),
            "location": next_event.location,
            "meeting_link": next_event.meeting_link,
            "minutes_until": minutes_until,
        },
    }


def generate_day_summary(events: list[CalendarEvent]) -> str:
    """
    Generate a summary of a day's events.

    Args:
        events: List of events

    Returns:
        Summary string
    """
    if not events:
        return "No events scheduled for today."

    lines = [f"**Today: {len(events)} events**\n"]

    for event in events:
        time_str = event.start_time.strftime("%H:%M")
        duration = event.duration_minutes

        if event.all_day:
            lines.append(f"  All Day: {event.title}")
        else:
            lines.append(f"  {time_str} ({duration}min): {event.title}")

        if event.location:
            lines.append(f"           @ {event.location}")

    return "\n".join(lines)


def generate_week_summary(events: list[CalendarEvent]) -> str:
    """
    Generate a summary of a week's events.

    Args:
        events: List of events

    Returns:
        Summary string
    """
    if not events:
        return "No events scheduled for this week."

    # Group by day
    by_day: dict[str, list[CalendarEvent]] = {}
    for event in events:
        day_key = event.start_time.strftime("%A, %b %d")
        if day_key not in by_day:
            by_day[day_key] = []
        by_day[day_key].append(event)

    lines = [f"**This Week: {len(events)} events**\n"]

    for day, day_events in by_day.items():
        lines.append(f"**{day}** ({len(day_events)} events)")
        for event in day_events[:3]:  # Max 3 per day in summary
            time_str = event.start_time.strftime("%H:%M")
            lines.append(f"  {time_str}: {event.title}")
        if len(day_events) > 3:
            lines.append(f"  ...and {len(day_events) - 3} more")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Calendar Reader")
    parser.add_argument("--account-id", required=True, help="Account ID")
    parser.add_argument("--today", action="store_true", help="Show today's events")
    parser.add_argument("--week", action="store_true", help="Show this week's events")
    parser.add_argument("--next", action="store_true", help="Show next event")
    parser.add_argument("--event", metavar="EVENT_ID", help="Show specific event")
    parser.add_argument("--availability", action="store_true", help="Check availability")
    parser.add_argument("--free-slots", action="store_true", help="Find free time slots")
    parser.add_argument("--duration", type=int, default=30, help="Slot duration (minutes)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.today:
        result = asyncio.run(get_today(args.account_id))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            print(result.get("summary", ""))
        else:
            print(f"Error: {result.get('error')}")

    elif args.week:
        result = asyncio.run(get_this_week(args.account_id))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            print(result.get("summary", ""))
        else:
            print(f"Error: {result.get('error')}")

    elif args.next:
        result = asyncio.run(get_next_event(args.account_id))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            print(result.get("message"))
            if result.get("next_event"):
                evt = result["next_event"]
                if evt.get("location"):
                    print(f"  Location: {evt['location']}")
                if evt.get("meeting_link"):
                    print(f"  Join: {evt['meeting_link']}")
        else:
            print(f"Error: {result.get('error')}")

    elif args.event:
        result = asyncio.run(get_event(args.account_id, args.event))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            event = result["event"]
            print(f"Title: {event.title}")
            print(f"When: {event.start_time} - {event.end_time}")
            if event.location:
                print(f"Where: {event.location}")
            if event.description:
                print(f"\n{event.description}")
        else:
            print(f"Error: {result.get('error')}")

    elif args.free_slots:
        result = asyncio.run(find_free_slots(
            args.account_id,
            duration_minutes=args.duration,
        ))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            slots = result.get("free_slots", [])
            print(f"Found {len(slots)} available slots ({args.duration}+ minutes):\n")
            for slot in slots:
                start = datetime.fromisoformat(slot["start"])
                print(f"  {start.strftime('%a %b %d %H:%M')} ({slot['duration_minutes']} min)")
        else:
            print(f"Error: {result.get('error')}")

    elif args.availability:
        now = datetime.now()
        result = asyncio.run(check_availability(
            args.account_id,
            start_date=now,
            end_date=now + timedelta(days=7),
        ))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            busy = result.get("busy_periods", [])
            print(f"Busy periods in next 7 days: {len(busy)}")
            for period in busy[:10]:
                print(f"  {period['start']} - {period.get('title', 'Busy')}")
        else:
            print(f"Error: {result.get('error')}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
