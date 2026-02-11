"""
Minimal Setup API Routes

Provides lightweight endpoints still consumed by the dashboard header
and settings page. The full setup wizard has been replaced by the
deterministic chat-based onboarding flow (see setup_flow.py).
"""

import logging
import sys
from pathlib import Path

import yaml
from fastapi import APIRouter
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)
router = APIRouter()


# ---- models ----------------------------------------------------------------

class SetupState(BaseModel):
    is_complete: bool = False
    current_step: str = ""
    completed_steps: list[str] = []
    progress_percent: int = 0
    primary_channel: str | None = None
    user_name: str | None = None
    started_at: str | None = None
    last_updated: str | None = None
    detected_timezone: str = "UTC"


class ApiKeyValidateRequest(BaseModel):
    api_key: str
    provider: str = "anthropic"


# ---- helpers ---------------------------------------------------------------

def _read_user_yaml() -> dict:
    user_yaml = PROJECT_ROOT / "args" / "user.yaml"
    if not user_yaml.exists():
        return {}
    try:
        with open(user_yaml) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# ---- endpoints -------------------------------------------------------------

@router.get("/state", response_model=SetupState)
async def get_setup_state():
    """Return lightweight setup state for the dashboard header."""
    data = _read_user_yaml()
    user = data.get("user", {})
    channels = data.get("channels", {})
    onboarding = data.get("onboarding", {})

    user_name = user.get("name")
    timezone = user.get("timezone", "UTC")
    primary_channel = channels.get("primary")
    is_complete = bool(user_name and timezone)

    return SetupState(
        is_complete=is_complete,
        current_step="complete" if is_complete else "user_name",
        completed_steps=["api_key", "user_name", "timezone"] if is_complete else [],
        progress_percent=100 if is_complete else 0,
        primary_channel=primary_channel,
        user_name=user_name,
        started_at=onboarding.get("completed_at"),
        last_updated=onboarding.get("completed_at"),
        detected_timezone=timezone,
    )


@router.post("/apikey/validate")
async def validate_api_key(request: ApiKeyValidateRequest):
    """Validate an API key by making a lightweight API call."""
    if request.provider == "anthropic":
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=request.api_key)
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        return {"success": False, "error": f"Unsupported provider: {request.provider}"}
