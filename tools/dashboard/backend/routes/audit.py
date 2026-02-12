"""
Audit Routes for Dashboard

Queries the canonical security audit DB (tools/security/audit.py) instead of
the dashboard-local audit_log table that was removed in OBS-P1-4.

Endpoints:
- GET /audit - Get audit events with filtering
- GET /audit/stats - Get audit statistics
"""


from fastapi import APIRouter, Query


router = APIRouter(prefix="/audit")


@router.get("")
async def get_audit_log(
    event_type: str = Query(None, description="Filter by event type"),
    status: str = Query(None, description="Filter by status: success, failure, blocked"),
    user_id: str = Query(None, description="Filter by user ID"),
    limit: int = Query(50, ge=1, le=500, description="Number of events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    start_date: str = Query(None, description="Start date (ISO format)"),
    end_date: str = Query(None, description="End date (ISO format)"),
):
    from tools.security.audit import query_events

    result = query_events(
        event_type=event_type,
        user_id=user_id,
        status=status,
        since=start_date,
        until=end_date,
        limit=limit,
        offset=offset,
    )

    if not result.get("success"):
        return {"events": [], "total": 0, "limit": limit, "offset": offset}

    formatted_events = []
    for event in result.get("events", []):
        formatted_events.append({
            "id": str(event["id"]),
            "eventType": event.get("event_type"),
            "timestamp": event.get("timestamp"),
            "userId": event.get("user_id"),
            "action": event.get("action"),
            "resource": event.get("resource"),
            "status": event.get("status"),
            "details": event.get("details"),
            "ipAddress": event.get("ip_address"),
            "traceId": event.get("trace_id"),
        })

    return {
        "events": formatted_events,
        "total": result.get("total", 0),
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
async def get_audit_stats(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
):
    from tools.security.audit import get_stats

    result = get_stats()
    if not result.get("success"):
        return {"period_days": days, "total_events": 0, "by_type": {}, "by_status": {}}

    stats = result.get("stats", {})
    return {
        "period_days": days,
        "total_events": stats.get("total_events", 0),
        "by_type": stats.get("by_type", {}),
        "by_status": stats.get("by_status", {}),
        "events_24h": stats.get("events_24h", 0),
        "failures_24h": stats.get("failures_24h", 0),
    }
