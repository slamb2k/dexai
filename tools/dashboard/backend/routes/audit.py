"""
Audit Routes for Dashboard

Provides security audit log endpoints for the dashboard.

Endpoints:
- GET /audit - Get audit events with filtering
- GET /audit/stats - Get audit statistics
"""

from datetime import datetime

from fastapi import APIRouter, Query

from tools.dashboard.backend.database import count_audit_events, get_audit_events


router = APIRouter(prefix="/audit")


@router.get("")
async def get_audit_log(
    event_type: str = Query(None, description="Filter by event type prefix (e.g., 'auth', 'permission')"),
    severity: str = Query(None, description="Filter by severity: info, warning, error, critical"),
    actor: str = Query(None, description="Filter by actor (user/system)"),
    limit: int = Query(50, ge=1, le=500, description="Number of events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    start_date: str = Query(None, description="Start date (ISO format)"),
    end_date: str = Query(None, description="End date (ISO format)"),
):
    """
    Get security audit events with optional filters.

    Event types follow the pattern:
    - auth.login, auth.logout, auth.failed
    - permission.check, permission.denied
    - config.changed, config.reset
    - data.access, data.export
    - security.rate_limit, security.blocked
    """
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
    events = get_audit_events(
        event_type=event_type,
        severity=severity,
        actor=actor,
        limit=limit,
        offset=offset,
        start_date=start_dt,
        end_date=end_dt,
    )

    # Get total count for pagination
    total = count_audit_events(
        event_type=event_type,
        severity=severity,
        actor=actor,
        start_date=start_dt,
        end_date=end_dt,
    )

    # Transform for frontend
    formatted_events = []
    for event in events:
        formatted_events.append({
            "id": str(event["id"]),
            "eventType": event["event_type"],
            "timestamp": event["timestamp"],
            "userId": event.get("actor"),
            "action": event["event_type"].split(".")[-1] if "." in event["event_type"] else event["event_type"],
            "resource": event.get("target"),
            "status": "failure" if event.get("severity") in ["error", "critical"] else "success",
            "details": event.get("details"),
            "ipAddress": event.get("ip_address"),
            "severity": event.get("severity", "info"),
        })

    return {
        "events": formatted_events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
async def get_audit_stats(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
):
    """
    Get audit event statistics for the specified period.
    """
    from datetime import timedelta

    from tools.dashboard.backend.database import get_db_connection

    start_date = datetime.now() - timedelta(days=days)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Total events
    cursor.execute(
        "SELECT COUNT(*) as count FROM audit_log WHERE timestamp >= ?",
        (start_date.isoformat(),),
    )
    total_events = cursor.fetchone()["count"]

    # Events by type
    cursor.execute(
        """
        SELECT event_type, COUNT(*) as count
        FROM audit_log
        WHERE timestamp >= ?
        GROUP BY event_type
        ORDER BY count DESC
        LIMIT 10
    """,
        (start_date.isoformat(),),
    )
    by_type = {row["event_type"]: row["count"] for row in cursor.fetchall()}

    # Events by severity
    cursor.execute(
        """
        SELECT severity, COUNT(*) as count
        FROM audit_log
        WHERE timestamp >= ?
        GROUP BY severity
    """,
        (start_date.isoformat(),),
    )
    by_severity = {row["severity"]: row["count"] for row in cursor.fetchall()}

    # Events per day
    cursor.execute(
        """
        SELECT DATE(timestamp) as day, COUNT(*) as count
        FROM audit_log
        WHERE timestamp >= ?
        GROUP BY DATE(timestamp)
        ORDER BY day
    """,
        (start_date.isoformat(),),
    )
    by_day = [{"day": row["day"], "count": row["count"]} for row in cursor.fetchall()]

    conn.close()

    return {
        "period_days": days,
        "total_events": total_events,
        "by_type": by_type,
        "by_severity": by_severity,
        "by_day": by_day,
    }
