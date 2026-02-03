"""
Office Integration Routes - Draft and Meeting Management

Provides endpoints for Level 3 (Collaborative) office integration:
- GET/POST/PUT/DELETE /api/office/drafts
- GET/POST/PUT/DELETE /api/office/meetings
- GET /api/office/accounts
- GET /api/office/availability
- GET /api/office/suggest-times
"""

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from tools.office import get_connection
from tools.office.email.draft_manager import (
    approve_draft,
    create_draft,
    delete_draft,
    get_draft,
    get_pending_drafts,
    update_draft,
)
from tools.office.calendar.scheduler import (
    cancel_proposal,
    confirm_meeting,
    get_pending_proposals,
    get_proposal,
    propose_meeting,
    suggest_meeting_times,
    update_proposal,
)


router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class DraftCreateRequest(BaseModel):
    """Request to create a new email draft."""

    account_id: str = Field(..., description="Office account ID")
    to: list[str] = Field(..., description="Recipient email addresses")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body (plain text)")
    cc: list[str] | None = Field(None, description="CC recipients")
    bcc: list[str] | None = Field(None, description="BCC recipients")
    reply_to_message_id: str | None = Field(None, description="Message ID to reply to")
    check_sentiment: bool = Field(True, description="Run sentiment analysis")


class DraftUpdateRequest(BaseModel):
    """Request to update a draft."""

    subject: str | None = Field(None, description="New subject")
    body: str | None = Field(None, description="New body")
    to: list[str] | None = Field(None, description="New recipients")
    cc: list[str] | None = Field(None, description="New CC")
    bcc: list[str] | None = Field(None, description="New BCC")


class DraftResponse(BaseModel):
    """Email draft response."""

    id: str
    account_id: str
    provider_draft_id: str | None
    subject: str | None
    recipients: list[str]
    cc: list[str] | None
    bcc: list[str] | None
    body_preview: str | None
    status: str
    sentiment_score: float | None
    sentiment_flags: list[str] | None
    created_at: str
    updated_at: str


class MeetingProposalRequest(BaseModel):
    """Request to propose a new meeting."""

    account_id: str = Field(..., description="Office account ID")
    title: str = Field(..., description="Meeting title")
    start_time: str = Field(..., description="Start time (ISO format)")
    end_time: str | None = Field(None, description="End time (optional)")
    duration_minutes: int = Field(30, description="Duration in minutes")
    attendees: list[str] | None = Field(None, description="Attendee emails")
    description: str = Field("", description="Meeting description")
    location: str = Field("", description="Meeting location")
    timezone: str = Field("UTC", description="Timezone")
    check_availability: bool = Field(True, description="Check for conflicts")


class MeetingUpdateRequest(BaseModel):
    """Request to update a meeting proposal."""

    title: str | None = None
    description: str | None = None
    location: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    attendees: list[str] | None = None


class MeetingProposalResponse(BaseModel):
    """Meeting proposal response."""

    id: str
    account_id: str
    provider_event_id: str | None
    title: str
    description: str | None
    location: str | None
    start_time: str
    end_time: str
    timezone: str | None
    attendees: list[str] | None
    organizer_email: str | None
    status: str
    conflicts: list[dict] | None
    created_at: str


class AccountResponse(BaseModel):
    """Office account response."""

    id: str
    provider: str
    email_address: str
    integration_level: int
    integration_level_name: str
    is_active: bool
    last_sync: str | None
    created_at: str


class SuggestionResponse(BaseModel):
    """Meeting time suggestion."""

    start: str
    end: str
    score: float
    reason: str


# =============================================================================
# Account Endpoints
# =============================================================================


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(user_id: str = Query("default", description="User ID")):
    """
    List connected office accounts.

    Returns all office accounts for the user with their integration levels.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, provider, email_address, integration_level, is_active,
               last_sync, created_at
        FROM office_accounts
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    level_names = {
        1: "Sandboxed",
        2: "Read-Only",
        3: "Collaborative",
        4: "Managed Proxy",
        5: "Autonomous",
    }

    accounts = []
    for row in rows:
        account = dict(row)
        account["integration_level_name"] = level_names.get(
            account["integration_level"], "Unknown"
        )
        accounts.append(AccountResponse(**account))

    return accounts


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(account_id: str):
    """Get details of a specific account."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, provider, email_address, integration_level, is_active,
               last_sync, created_at
        FROM office_accounts WHERE id = ?
        """,
        (account_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Account not found")

    account = dict(row)
    level_names = {1: "Sandboxed", 2: "Read-Only", 3: "Collaborative", 4: "Managed Proxy", 5: "Autonomous"}
    account["integration_level_name"] = level_names.get(account["integration_level"], "Unknown")

    return AccountResponse(**account)


@router.put("/accounts/{account_id}/level")
async def update_integration_level(account_id: str, level: int = Query(..., ge=1, le=5)):
    """
    Update the integration level for an account.

    Level changes may require re-authentication to get new scopes.
    """
    if level < 1 or level > 5:
        raise HTTPException(status_code=400, detail="Level must be between 1 and 5")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE office_accounts SET integration_level = ?, updated_at = ? WHERE id = ?",
        (level, datetime.now().isoformat(), account_id),
    )

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")

    conn.commit()
    conn.close()

    return {"success": True, "integration_level": level}


# =============================================================================
# Draft Endpoints
# =============================================================================


@router.get("/drafts")
async def list_drafts(
    account_id: str = Query(..., description="Office account ID"),
    status: str = Query("pending", description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    List email drafts.

    Returns drafts with sentiment analysis results for review.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM office_drafts
        WHERE account_id = ? AND status = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (account_id, status, limit),
    )
    rows = cursor.fetchall()

    cursor.execute(
        "SELECT COUNT(*) FROM office_drafts WHERE account_id = ? AND status = ?",
        (account_id, status),
    )
    total = cursor.fetchone()[0]
    conn.close()

    drafts = []
    for row in rows:
        draft = dict(row)
        # Parse JSON fields
        if draft.get("recipients"):
            draft["recipients"] = json.loads(draft["recipients"])
        else:
            draft["recipients"] = []
        if draft.get("cc"):
            draft["cc"] = json.loads(draft["cc"])
        if draft.get("bcc"):
            draft["bcc"] = json.loads(draft["bcc"])
        if draft.get("sentiment_flags"):
            draft["sentiment_flags"] = json.loads(draft["sentiment_flags"])

        # Create preview
        draft["body_preview"] = (draft.get("body_text") or "")[:200]

        drafts.append(draft)

    return {"drafts": drafts, "total": total}


@router.get("/drafts/{draft_id}")
async def get_draft_details(draft_id: str):
    """Get full details of a draft including body."""
    result = await get_draft(draft_id)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Draft not found"))

    return result["draft"]


@router.post("/drafts")
async def create_new_draft(request: DraftCreateRequest):
    """
    Create a new email draft.

    Creates draft in provider AND local database for tracking.
    Includes sentiment analysis to warn about emotional content.
    """
    result = await create_draft(
        account_id=request.account_id,
        to=request.to,
        subject=request.subject,
        body=request.body,
        cc=request.cc,
        bcc=request.bcc,
        reply_to_message_id=request.reply_to_message_id,
        check_sentiment=request.check_sentiment,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to create draft"))

    return result


@router.put("/drafts/{draft_id}")
async def update_draft_details(draft_id: str, request: DraftUpdateRequest):
    """Update an existing draft."""
    result = await update_draft(
        draft_id=draft_id,
        subject=request.subject,
        body=request.body,
        to=request.to,
        cc=request.cc,
        bcc=request.bcc,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to update draft"))

    return result


@router.delete("/drafts/{draft_id}")
async def delete_draft_endpoint(draft_id: str):
    """Delete a draft from both local and provider."""
    result = await delete_draft(draft_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to delete draft"))

    return result


@router.post("/drafts/{draft_id}/approve")
async def approve_draft_endpoint(draft_id: str, send_immediately: bool = False):
    """
    Approve a draft for sending.

    In Level 3, this marks the draft as approved - user sends from email client.
    In Level 4+, setting send_immediately=True will send the email.
    """
    result = await approve_draft(draft_id, send_immediately=send_immediately)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to approve draft"))

    return result


# =============================================================================
# Meeting Endpoints
# =============================================================================


@router.get("/meetings")
async def list_meetings(
    account_id: str = Query(..., description="Office account ID"),
    status: str = Query("proposed", description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    List meeting proposals.

    Returns proposals with conflict information for review.
    """
    if status == "proposed":
        result = await get_pending_proposals(account_id=account_id, limit=limit)
    else:
        # Query for other statuses
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM office_meeting_drafts
            WHERE account_id = ? AND status = ?
            ORDER BY start_time ASC
            LIMIT ?
            """,
            (account_id, status, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        proposals = []
        for row in rows:
            proposal = dict(row)
            if proposal.get("attendees"):
                proposal["attendees"] = json.loads(proposal["attendees"])
            if proposal.get("conflicts"):
                proposal["conflicts"] = json.loads(proposal["conflicts"])
            proposals.append(proposal)

        result = {"success": True, "proposals": proposals, "total": len(proposals)}

    return result


@router.get("/meetings/{proposal_id}")
async def get_meeting_details(proposal_id: str):
    """Get full details of a meeting proposal."""
    result = await get_proposal(proposal_id)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Proposal not found"))

    return result["proposal"]


@router.post("/meetings")
async def create_meeting_proposal(request: MeetingProposalRequest):
    """
    Propose a new meeting.

    Creates a proposal - does NOT create calendar event yet.
    User must confirm before invites are sent.
    """
    start_time = datetime.fromisoformat(request.start_time)
    end_time = datetime.fromisoformat(request.end_time) if request.end_time else None

    result = await propose_meeting(
        account_id=request.account_id,
        title=request.title,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=request.duration_minutes,
        attendees=request.attendees,
        description=request.description,
        location=request.location,
        timezone=request.timezone,
        check_availability=request.check_availability,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to create proposal"))

    return result


@router.put("/meetings/{proposal_id}")
async def update_meeting_proposal(proposal_id: str, request: MeetingUpdateRequest):
    """Update an existing meeting proposal."""
    start_time = datetime.fromisoformat(request.start_time) if request.start_time else None
    end_time = datetime.fromisoformat(request.end_time) if request.end_time else None

    result = await update_proposal(
        proposal_id=proposal_id,
        title=request.title,
        description=request.description,
        location=request.location,
        start_time=start_time,
        end_time=end_time,
        attendees=request.attendees,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to update proposal"))

    return result


@router.delete("/meetings/{proposal_id}")
async def cancel_meeting_proposal(proposal_id: str):
    """Cancel a meeting proposal."""
    result = await cancel_proposal(proposal_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to cancel proposal"))

    return result


@router.post("/meetings/{proposal_id}/confirm")
async def confirm_meeting_endpoint(proposal_id: str):
    """
    Confirm a meeting proposal.

    Creates the actual calendar event and sends invites to attendees.
    This action cannot be undone in Level 3.
    """
    result = await confirm_meeting(proposal_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to confirm meeting"))

    return result


# =============================================================================
# Availability Endpoints
# =============================================================================


@router.get("/availability")
async def check_availability(
    account_id: str = Query(..., description="Office account ID"),
    start_time: str = Query(..., description="Start time (ISO format)"),
    end_time: str = Query(..., description="End time (ISO format)"),
):
    """
    Check calendar availability for a time range.

    Returns list of events/conflicts in the specified time range.
    """
    from tools.office.calendar.scheduler import _get_account, _get_provider, _check_conflicts

    account = _get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    start = datetime.fromisoformat(start_time)
    end = datetime.fromisoformat(end_time)

    try:
        provider = _get_provider(account)
        conflicts = await _check_conflicts(provider, start, end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check availability: {e}")

    return {
        "available": len(conflicts) == 0,
        "conflicts": conflicts,
        "start_time": start_time,
        "end_time": end_time,
    }


@router.get("/suggest-times", response_model=list[SuggestionResponse])
async def get_time_suggestions(
    account_id: str = Query(..., description="Office account ID"),
    duration_minutes: int = Query(30, description="Meeting duration"),
    days_ahead: int = Query(7, ge=1, le=30, description="Days to search"),
):
    """
    Suggest available meeting times.

    Returns scored suggestions based on availability and ADHD-friendly heuristics.
    """
    result = await suggest_meeting_times(
        account_id=account_id,
        duration_minutes=duration_minutes,
        days_ahead=days_ahead,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to suggest times"))

    return [SuggestionResponse(**s) for s in result.get("suggestions", [])]
