"""
Activity Route - Real-time Activity Feed

Provides endpoints for the activity feed:
- GET activity events with pagination and filters
- POST new activity events
"""

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from tools.dashboard.backend.database import count_events, get_events, log_event
from tools.dashboard.backend.models import (
    ActivityEvent,
    ActivityFeed,
    EventSeverity,
    EventType,
    NewActivityEvent,
)


router = APIRouter()


class ActivityCreatedResponse(BaseModel):
    """Response after creating an activity event."""

    success: bool
    event_id: int
    message: str


@router.get("", response_model=ActivityFeed)
async def get_activity(
    event_type: str | None = Query(None, description="Filter by event type"),
    severity: str | None = Query(None, description="Filter by severity"),
    channel: str | None = Query(None, description="Filter by channel"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    limit: int = Query(50, ge=1, le=200, description="Number of events to return"),
    cursor: str | None = Query(None, description="Cursor for pagination"),
):
    """
    Get activity feed with optional filters.

    Supports cursor-based pagination for efficient infinite scroll.
    The cursor is an event ID - events older than this ID are returned.
    """
    # Parse cursor (event ID for offset-based pagination)
    offset = 0
    if cursor:
        try:
            offset = int(cursor)
        except ValueError:
            offset = 0

    # Parse dates
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            pass

    # Get events
    events_data = get_events(
        event_type=event_type,
        severity=severity,
        channel=channel,
        limit=limit + 1,  # Fetch one extra to check for more
        offset=offset,
        start_date=start_dt,
        end_date=end_dt,
    )

    # Check if there are more events
    has_more = len(events_data) > limit
    if has_more:
        events_data = events_data[:limit]

    # Get total count
    total = count_events(
        event_type=event_type,
        severity=severity,
        channel=channel,
        start_date=start_dt,
        end_date=end_dt,
    )

    # Convert to ActivityEvent objects
    events = []
    for event_data in events_data:
        try:
            event_type_enum = EventType(event_data.get("event_type", "system"))
        except ValueError:
            event_type_enum = EventType.SYSTEM

        try:
            severity_enum = EventSeverity(event_data.get("severity", "info"))
        except ValueError:
            severity_enum = EventSeverity.INFO

        # Parse timestamp
        timestamp = datetime.now()
        if event_data.get("timestamp"):
            try:
                timestamp = datetime.fromisoformat(event_data["timestamp"])
            except (ValueError, TypeError):
                pass

        events.append(
            ActivityEvent(
                id=event_data["id"],
                event_type=event_type_enum,
                timestamp=timestamp,
                channel=event_data.get("channel"),
                user_id=event_data.get("user_id"),
                summary=event_data.get("summary", ""),
                details=event_data.get("details"),
                severity=severity_enum,
            )
        )

    # Next cursor
    next_cursor = None
    if has_more and events:
        next_cursor = str(offset + limit)

    return ActivityFeed(events=events, total=total, cursor=next_cursor, has_more=has_more)


@router.post("", response_model=ActivityCreatedResponse)
async def create_activity(event: NewActivityEvent):
    """
    Log a new activity event.

    This endpoint is called by internal systems to log events
    that will appear in the activity feed.
    """
    # Convert details dict if provided
    details_dict = None
    if event.details:
        details_dict = event.details

    # Log the event
    event_id = log_event(
        event_type=event.event_type.value,
        summary=event.summary,
        channel=event.channel,
        user_id=event.user_id,
        details=details_dict,
        severity=event.severity.value,
    )

    # Trigger WebSocket broadcast
    try:
        from tools.dashboard.backend.websocket import broadcast_activity

        await broadcast_activity(
            {
                "id": event_id,
                "event_type": event.event_type.value,
                "timestamp": datetime.now().isoformat(),
                "channel": event.channel,
                "user_id": event.user_id,
                "summary": event.summary,
                "severity": event.severity.value,
            }
        )
    except Exception:
        pass  # WebSocket broadcast is best-effort

    return ActivityCreatedResponse(success=True, event_id=event_id, message="Activity event logged")
