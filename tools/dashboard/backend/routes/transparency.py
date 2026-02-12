"""
Transparency Route - "Show Your Work" Mode (OBS-P2-11/TRANS-3)

Provides endpoints for per-conversation transparency logging:
- GET /transparency/{conversation_id} - Get transparency log
- POST /transparency/{conversation_id}/toggle - Enable/disable transparency
"""

import logging

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class TransparencyToggleRequest(BaseModel):
    """Request body for toggling transparency mode."""
    enabled: bool


class TransparencyToggleResponse(BaseModel):
    """Response for transparency toggle."""
    success: bool
    conversation_id: str
    enabled: bool
    message: str


class TransparencyLogResponse(BaseModel):
    """Response for transparency log retrieval."""
    success: bool
    conversation_id: str
    enabled: bool
    total_entries: int
    entries: list[dict]


class TransparencySummaryResponse(BaseModel):
    """Response for transparency summary."""
    success: bool
    conversation_id: str
    enabled: bool
    total_entries: int
    by_type: dict[str, int]


@router.get(
    "/{conversation_id}",
    response_model=TransparencyLogResponse,
    summary="Get transparency log for a conversation",
)
async def get_transparency_log(
    conversation_id: str = Path(..., description="Conversation identifier"),
    limit: int = Query(100, description="Maximum entries to return", ge=1, le=500),
    offset: int = Query(0, description="Offset for pagination", ge=0),
):
    """Retrieve the transparency log for a given conversation.

    Returns all tool usage, memory access, and routing decision events
    logged for the conversation when transparency mode was enabled.
    """
    try:
        from tools.ops.transparency import transparency

        log = transparency.get_log(conversation_id)
        enabled = transparency.is_enabled(conversation_id)

        # Apply pagination
        paginated = log[offset:offset + limit]

        return TransparencyLogResponse(
            success=True,
            conversation_id=conversation_id,
            enabled=enabled,
            total_entries=len(log),
            entries=paginated,
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Transparency module not available",
        )
    except Exception as e:
        logger.error(f"Error getting transparency log: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve transparency log: {e}",
        )


@router.post(
    "/{conversation_id}/toggle",
    response_model=TransparencyToggleResponse,
    summary="Toggle transparency mode for a conversation",
)
async def toggle_transparency(
    conversation_id: str = Path(..., description="Conversation identifier"),
    body: TransparencyToggleRequest | None = None,
):
    """Enable or disable transparency logging for a conversation.

    When enabled, tool usage, memory access, and routing decisions
    will be logged for the conversation.
    """
    try:
        from tools.ops.transparency import transparency

        # If body is provided, use it; otherwise toggle
        if body is not None:
            enabled = body.enabled
        else:
            enabled = not transparency.is_enabled(conversation_id)

        if enabled:
            transparency.enable(conversation_id)
        else:
            transparency.disable(conversation_id)

        return TransparencyToggleResponse(
            success=True,
            conversation_id=conversation_id,
            enabled=enabled,
            message=f"Transparency {'enabled' if enabled else 'disabled'} for {conversation_id}",
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Transparency module not available",
        )
    except Exception as e:
        logger.error(f"Error toggling transparency: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle transparency: {e}",
        )


@router.get(
    "/{conversation_id}/summary",
    response_model=TransparencySummaryResponse,
    summary="Get transparency log summary",
)
async def get_transparency_summary(
    conversation_id: str = Path(..., description="Conversation identifier"),
):
    """Get a summary of the transparency log (counts by event type)."""
    try:
        from tools.ops.transparency import transparency

        summary = transparency.get_summary(conversation_id)

        return TransparencySummaryResponse(
            success=True,
            conversation_id=summary["conversation_id"],
            enabled=summary["enabled"],
            total_entries=summary["total_entries"],
            by_type=summary["by_type"],
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Transparency module not available",
        )
    except Exception as e:
        logger.error(f"Error getting transparency summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get transparency summary: {e}",
        )


@router.delete(
    "/{conversation_id}",
    summary="Clear transparency log for a conversation",
)
async def clear_transparency_log(
    conversation_id: str = Path(..., description="Conversation identifier"),
):
    """Clear the transparency log for a conversation."""
    try:
        from tools.ops.transparency import transparency

        transparency.clear_log(conversation_id)

        return {
            "success": True,
            "conversation_id": conversation_id,
            "message": f"Transparency log cleared for {conversation_id}",
        }
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Transparency module not available",
        )
    except Exception as e:
        logger.error(f"Error clearing transparency log: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear transparency log: {e}",
        )
