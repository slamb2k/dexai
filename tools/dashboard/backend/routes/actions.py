"""
Action Queue Management Routes - Level 4 Managed Proxy Integration

Provides endpoints for managing the action queue with ADHD-safe features:
- List and manage pending actions
- Undo, expedite, and extend actions
- Full audit trail access
- Daily digest generation and delivery
- Email send/delete/archive operations through the queue

All actions go through the queue system with configurable undo windows,
giving users time to reconsider impulsive actions.
"""

from datetime import datetime
from io import StringIO
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from tools.office import get_connection
from tools.office.actions.audit_logger import (
    export_audit_log,
    get_audit_log,
    get_audit_summary,
)
from tools.office.actions.digest import generate_digest, send_digest
from tools.office.actions.executor import execute_action
from tools.office.actions.queue import (
    cancel_action,
    expedite_action,
    get_action,
    get_pending_actions,
    get_queue_stats,
)
from tools.office.actions.undo_manager import extend_undo_window, undo_action
from tools.office.email.sender import (
    archive_email,
    bulk_action,
    delete_email,
    send_email,
)


router = APIRouter()


# =============================================================================
# Request Models
# =============================================================================


class SendEmailRequest(BaseModel):
    """Request to queue an email for sending."""

    account_id: str = Field(..., description="Office account ID")
    to: list[str] = Field(..., description="Recipient email addresses")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body (plain text)")
    cc: list[str] | None = Field(None, description="CC recipients")
    bcc: list[str] | None = Field(None, description="BCC recipients")
    reply_to_message_id: str | None = Field(None, description="Message ID to reply to")
    skip_sentiment_check: bool = Field(False, description="Skip sentiment analysis")


class DeleteEmailRequest(BaseModel):
    """Request to queue an email deletion."""

    account_id: str = Field(..., description="Office account ID")
    message_id: str = Field(..., description="Provider message ID to delete")
    permanent: bool = Field(False, description="Permanently delete (not just trash)")


class BulkActionRequest(BaseModel):
    """Request for bulk email actions."""

    account_id: str = Field(..., description="Office account ID")
    message_ids: list[str] = Field(..., description="List of message IDs")
    action: str = Field(..., description="Action: archive, delete, or mark_read")


class ExtendUndoRequest(BaseModel):
    """Request to extend an action's undo window."""

    additional_seconds: int = Field(30, ge=5, le=300, description="Seconds to add")


# =============================================================================
# Response Models
# =============================================================================


class ActionResponse(BaseModel):
    """Single action response."""

    id: str
    account_id: str
    action_type: str
    status: str
    undo_deadline: str | None
    created_at: str
    action_data: dict[str, Any] | None = None
    executed_at: str | None = None


class ActionListResponse(BaseModel):
    """List of actions response."""

    actions: list[dict[str, Any]]
    total: int
    pending_count: int


class AuditEntryResponse(BaseModel):
    """Single audit log entry."""

    id: str
    action_type: str
    action_summary: str
    result: str
    created_at: str
    action_data: dict[str, Any] | None = None


class AuditListResponse(BaseModel):
    """List of audit entries response."""

    entries: list[dict[str, Any]]
    total: int


class DigestResponse(BaseModel):
    """Daily digest response."""

    date: str
    emails_sent: int
    emails_deleted: int
    emails_archived: int
    meetings_scheduled: int
    actions_undone: int
    highlights: list[str]
    warnings: list[str]
    formatted: str | None = None


class QueueStatsResponse(BaseModel):
    """Queue statistics response."""

    pending: int
    executed_today: int
    undone_today: int
    expired_today: int
    failed_today: int
    by_type: dict[str, int]


# =============================================================================
# Action Queue Endpoints
# =============================================================================


@router.get("/actions", response_model=ActionListResponse)
async def list_actions(
    account_id: str = Query(..., description="Office account ID"),
    action_type: str | None = Query(None, description="Filter by action type"),
    status: str = Query("pending", description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
):
    """
    List actions in the queue.

    Returns pending actions by default. Use status filter to see other states.
    """
    result = await get_pending_actions(
        account_id=account_id,
        action_type=action_type,
        limit=limit,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to list actions"))

    # Get pending count for response
    stats = await get_queue_stats(account_id)
    pending_count = stats.get("pending_count", 0) if stats.get("success") else 0

    return ActionListResponse(
        actions=result.get("actions", []),
        total=result.get("total", 0),
        pending_count=pending_count,
    )


@router.get("/actions/stats", response_model=QueueStatsResponse)
async def get_action_stats(
    account_id: str = Query(..., description="Office account ID"),
):
    """
    Get action queue statistics.

    Returns counts of pending, executed, undone, and failed actions.
    """
    result = await get_queue_stats(account_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to get stats"))

    return QueueStatsResponse(
        pending=result.get("pending_count", 0),
        executed_today=result.get("executed_today", 0),
        undone_today=result.get("undone_today", 0),
        expired_today=result.get("expired_today", 0),
        failed_today=result.get("failed_today", 0),
        by_type=result.get("by_type", {}),
    )


@router.get("/actions/{action_id}", response_model=ActionResponse)
async def get_action_details(action_id: str):
    """Get details of a specific action."""
    result = await get_action(action_id)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Action not found"))

    action = result["action"]
    return ActionResponse(
        id=action["id"],
        account_id=action["account_id"],
        action_type=action["action_type"],
        status=action["status"],
        undo_deadline=action.get("undo_deadline"),
        created_at=action["created_at"],
        action_data=action.get("action_data"),
        executed_at=action.get("executed_at"),
    )


@router.post("/actions/{action_id}/undo")
async def undo_action_endpoint(action_id: str):
    """
    Undo a pending action.

    Only works if the action is still within its undo window.
    This is a key ADHD-safe feature allowing users to reconsider impulsive actions.
    """
    result = await undo_action(action_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to undo action"))

    return result


@router.post("/actions/{action_id}/expedite")
async def expedite_action_endpoint(action_id: str):
    """
    Execute an action immediately, bypassing the undo window.

    Use when you're certain you want the action to proceed without waiting.
    """
    # First expedite (sets undo_deadline to now)
    expedite_result = await expedite_action(action_id)

    if not expedite_result.get("success"):
        raise HTTPException(
            status_code=400, detail=expedite_result.get("error", "Failed to expedite action")
        )

    # Then execute immediately
    exec_result = await execute_action(action_id)

    if not exec_result.get("success"):
        raise HTTPException(
            status_code=400, detail=exec_result.get("error", "Failed to execute action")
        )

    return {
        "success": True,
        "action_id": action_id,
        "message": "Action executed immediately",
        "result": exec_result,
    }


@router.post("/actions/{action_id}/extend")
async def extend_action_undo_window(action_id: str, request: ExtendUndoRequest):
    """
    Extend the undo window for an action.

    Gives you more time to decide on an action. Useful when you need
    more time to think about whether to proceed.
    """
    result = await extend_undo_window(action_id, request.additional_seconds)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to extend window"))

    return result


# =============================================================================
# Audit Log Endpoints
# =============================================================================


@router.get("/audit", response_model=AuditListResponse)
async def get_audit_entries(
    account_id: str = Query(..., description="Office account ID"),
    action_type: str | None = Query(None, description="Filter by action type"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    result_filter: str | None = Query(None, alias="result", description="Filter by result"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get audit log entries.

    Returns a permanent, immutable record of all actions taken.
    """
    result = await get_audit_log(
        account_id=account_id,
        action_type=action_type,
        start_date=start_date,
        end_date=end_date,
        result=result_filter,
        limit=limit,
        offset=offset,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to get audit log"))

    return AuditListResponse(
        entries=result.get("entries", []),
        total=result.get("total", 0),
    )


@router.get("/audit/export")
async def export_audit_entries(
    account_id: str = Query(..., description="Office account ID"),
    format: str = Query("csv", description="Export format (csv or json)"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
):
    """
    Export audit log to a file.

    Returns a downloadable CSV or JSON file containing the audit trail.
    """
    result = await export_audit_log(
        account_id=account_id,
        format=format,
        start_date=start_date,
        end_date=end_date,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to export"))

    # Read the exported file and return as streaming response
    file_path = result.get("file_path")
    if not file_path:
        raise HTTPException(status_code=500, detail="Export file path not returned")

    # Determine content type
    content_type = "text/csv" if format == "csv" else "application/json"
    filename = f"audit_export_{account_id}_{datetime.now().strftime('%Y%m%d')}.{format}"

    def file_iterator():
        with open(file_path, "rb") as f:
            yield from f

    return StreamingResponse(
        file_iterator(),
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/audit/summary")
async def get_audit_summary_endpoint(
    account_id: str = Query(..., description="Office account ID"),
    period: str = Query("day", description="Period: day, week, or month"),
):
    """
    Get a summary of audit log activity.

    Returns aggregated counts by action type and result for the specified period.
    """
    result = await get_audit_summary(account_id=account_id, period=period)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to get summary"))

    return result


# =============================================================================
# Email Action Endpoints
# =============================================================================


@router.post("/email/send")
async def queue_email_send(request: SendEmailRequest):
    """
    Queue an email for sending.

    The email will be sent after the undo window expires (60s default,
    5 minutes for high-sentiment emails). You can undo within this window.
    """
    result = await send_email(
        account_id=request.account_id,
        to=request.to,
        subject=request.subject,
        body=request.body,
        cc=request.cc,
        bcc=request.bcc,
        reply_to_message_id=request.reply_to_message_id,
        skip_sentiment_check=request.skip_sentiment_check,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to queue email"))

    return result


@router.post("/email/{message_id}/delete")
async def queue_email_delete(
    message_id: str,
    account_id: str = Query(..., description="Office account ID"),
    permanent: bool = Query(False, description="Permanently delete"),
):
    """
    Queue an email for deletion.

    By default moves to trash. Set permanent=true for permanent deletion.
    """
    result = await delete_email(
        account_id=account_id,
        message_id=message_id,
        permanent=permanent,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to queue deletion"))

    return result


@router.post("/email/{message_id}/archive")
async def queue_email_archive(
    message_id: str,
    account_id: str = Query(..., description="Office account ID"),
):
    """
    Queue an email for archiving.

    Moves the email out of the inbox without deleting it.
    """
    result = await archive_email(account_id=account_id, message_id=message_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to queue archive"))

    return result


@router.post("/email/bulk")
async def queue_bulk_email_action(request: BulkActionRequest):
    """
    Queue a bulk action on multiple emails.

    Supported actions: archive, delete, mark_read
    All messages are processed as a single action with one undo window.
    """
    result = await bulk_action(
        account_id=request.account_id,
        message_ids=request.message_ids,
        action=request.action,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to queue bulk action")
        )

    return result


# =============================================================================
# Digest Endpoints
# =============================================================================


@router.get("/digest/preview", response_model=DigestResponse)
async def preview_digest(
    account_id: str = Query(..., description="Office account ID"),
    date: str | None = Query(None, description="Date (ISO format, defaults to today)"),
):
    """
    Preview today's daily digest.

    Shows an ADHD-friendly summary of all actions taken by Dex.
    """
    result = await generate_digest(account_id=account_id, date=date)

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to generate digest")
        )

    digest = result.get("digest", {})

    return DigestResponse(
        date=digest.get("date", datetime.now().isoformat()),
        emails_sent=digest.get("emails_sent", 0),
        emails_deleted=digest.get("emails_deleted", 0),
        emails_archived=digest.get("emails_archived", 0),
        meetings_scheduled=digest.get("meetings_scheduled", 0),
        actions_undone=digest.get("actions_undone", 0),
        highlights=digest.get("highlights", []),
        warnings=digest.get("warnings", []),
        formatted=result.get("formatted"),
    )


@router.post("/digest/send")
async def send_digest_now(
    account_id: str = Query(..., description="Office account ID"),
    channel: str = Query("primary", description="Delivery channel"),
):
    """
    Generate and send the daily digest immediately.

    Useful for testing or getting an immediate summary.
    """
    result = await send_digest(account_id=account_id, channel=channel)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to send digest"))

    return result
