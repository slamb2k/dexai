"""
Voice API Routes (Phase 11a)

Provides endpoints for voice interface:
- GET  /api/voice/status      - Check voice config and availability
- POST /api/voice/command      - Submit transcript, parse intent, execute
- GET  /api/voice/preferences  - Get user voice preferences
- PUT  /api/voice/preferences  - Update voice preferences
- GET  /api/voice/history      - Get voice command history
- GET  /api/voice/commands     - List available voice commands
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from tools.voice.models import TranscriptionResult
from tools.voice.parser.intent_parser import parse_command, AVAILABLE_COMMANDS
from tools.voice.parser.command_router import create_default_router
from tools.voice.preferences.user_preferences import (
    get_command_history,
    get_preferences,
    update_preferences,
)
from tools.voice.recognition.web_speech_config import (
    WebSpeechConfig,
    process_web_speech_result,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Shared router instance
_command_router = None


def _get_router():
    global _command_router
    if _command_router is None:
        _command_router = create_default_router()
    return _command_router


# =============================================================================
# Request/Response Models
# =============================================================================


class VoiceCommandRequest(BaseModel):
    """Request model for processing a voice command."""

    transcript: str = Field(..., min_length=1, max_length=2000)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = Field(default="web_speech")
    language: str = Field(default="en-US")
    duration_ms: int = Field(default=0, ge=0)
    alternatives: list[str] = Field(default_factory=list)


class VoiceCommandResponse(BaseModel):
    """Response model for voice command execution."""

    success: bool
    message: str
    intent: str
    data: dict[str, Any] = Field(default_factory=dict)
    follow_up_prompt: Optional[str] = None
    undo_available: bool = False
    error: Optional[str] = None
    parsed: dict[str, Any] = Field(default_factory=dict)


class VoicePreferencesUpdate(BaseModel):
    """Request model for updating voice preferences."""

    enabled: Optional[bool] = None
    preferred_source: Optional[str] = None
    language: Optional[str] = None
    audio_feedback_enabled: Optional[bool] = None
    visual_feedback_enabled: Optional[bool] = None
    confirmation_verbosity: Optional[str] = None
    auto_execute_high_confidence: Optional[bool] = None
    confidence_threshold: Optional[float] = None
    repeat_on_low_confidence: Optional[bool] = None


class VoiceStatusResponse(BaseModel):
    """Response model for voice status check."""

    enabled: bool
    web_speech_config: dict[str, Any]
    available_sources: list[str]
    user_preferences: dict[str, Any]


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/status")
async def get_voice_status(user_id: str = Query(default="default")) -> VoiceStatusResponse:
    """Check voice interface status and configuration."""
    prefs = get_preferences(user_id)
    user_prefs = prefs.get("data", {})

    config = WebSpeechConfig(
        language=user_prefs.get("language", "en-US"),
    )

    available_sources = ["web_speech"]

    return VoiceStatusResponse(
        enabled=user_prefs.get("enabled", True),
        web_speech_config=config.to_dict(),
        available_sources=available_sources,
        user_preferences=user_prefs,
    )


@router.post("/command")
async def process_voice_command(
    request: VoiceCommandRequest,
    user_id: str = Query(default="default"),
) -> VoiceCommandResponse:
    """Receive a voice transcript, parse the intent, execute the command."""
    # Process the Web Speech result
    transcription = process_web_speech_result({
        "transcript": request.transcript,
        "confidence": request.confidence,
        "isFinal": True,
        "alternatives": request.alternatives,
        "language": request.language,
        "durationMs": request.duration_ms,
    })

    # Parse the command
    parsed = parse_command(transcription.transcript)

    # Check if confirmation is needed (frontend handles confirmation UI)
    prefs = get_preferences(user_id).get("data", {})
    auto_execute = prefs.get("auto_execute_high_confidence", True)
    threshold = prefs.get("confidence_threshold", 0.85)

    if parsed.requires_confirmation and (
        not auto_execute or parsed.confidence < threshold
    ):
        return VoiceCommandResponse(
            success=True,
            message=f'Did you mean: "{parsed.intent.value.replace("_", " ")}"?',
            intent=parsed.intent.value,
            parsed=parsed.to_dict(),
            data={"requires_confirmation": True},
        )

    # Execute the command
    cmd_router = _get_router()
    result = await cmd_router.route_command(parsed, user_id)

    return VoiceCommandResponse(
        success=result.success,
        message=result.message,
        intent=result.intent.value,
        data=result.data,
        follow_up_prompt=result.follow_up_prompt,
        undo_available=result.undo_available,
        error=result.error,
        parsed=parsed.to_dict(),
    )


@router.get("/preferences")
async def get_voice_preferences(
    user_id: str = Query(default="default"),
) -> dict[str, Any]:
    """Get voice preferences for the current user."""
    result = get_preferences(user_id)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to load preferences")
    return result


@router.put("/preferences")
async def update_voice_preferences(
    request: VoicePreferencesUpdate,
    user_id: str = Query(default="default"),
) -> dict[str, Any]:
    """Update voice preferences."""
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = update_preferences(user_id, updates)
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Update failed"),
        )
    return result


@router.get("/history")
async def get_voice_history(
    user_id: str = Query(default="default"),
    limit: int = Query(default=50, ge=1, le=200),
    intent: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """Get voice command history."""
    result = get_command_history(user_id, limit=limit, intent=intent)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to load history")
    return result


@router.get("/commands")
async def list_voice_commands() -> dict[str, Any]:
    """List all available voice commands."""
    return {
        "success": True,
        "data": {
            "commands": AVAILABLE_COMMANDS,
            "total": sum(len(v) for v in AVAILABLE_COMMANDS.values()),
        },
    }
