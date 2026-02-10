"""
Setup Wizard API Routes

Provides endpoints for the web-based setup wizard:
- GET /setup/state - Get current setup state
- POST /setup/channel/validate - Validate channel credentials
- POST /setup/channel/test - Send test message to channel
- POST /setup/apikey/validate - Validate Anthropic API key
- POST /setup/complete - Finalize setup and apply configuration
- POST /setup/reset - Reset setup state
"""

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel


# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.setup.wizard import (  # noqa: E402
    SetupState,
    SetupStep,
    apply_configuration,
    detect_timezone,
    get_setup_status,
    reset_setup,
    validate_anthropic_key,
    validate_channel,
)


router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class SetupStateResponse(BaseModel):
    """Current setup state."""

    is_complete: bool
    current_step: str
    completed_steps: list[str]
    progress_percent: int
    primary_channel: str | None
    user_name: str | None
    started_at: str | None
    last_updated: str | None
    detected_timezone: str


class ChannelValidateRequest(BaseModel):
    """Channel validation request."""

    channel: str  # telegram, discord, slack
    token: str | None = None
    bot_token: str | None = None  # For Slack
    app_token: str | None = None  # For Slack


class ChannelValidateResponse(BaseModel):
    """Channel validation response."""

    success: bool
    bot_id: str | None = None
    bot_username: str | None = None
    bot_name: str | None = None
    team_name: str | None = None  # For Slack
    error: str | None = None


class ChannelTestRequest(BaseModel):
    """Send test message request."""

    channel: str
    token: str | None = None
    bot_token: str | None = None
    app_token: str | None = None
    chat_id: str | None = None  # For Telegram
    channel_id: str | None = None  # For Discord/Slack


class ChannelTestResponse(BaseModel):
    """Test message response."""

    success: bool
    message_id: str | None = None
    error: str | None = None


class ApiKeyValidateRequest(BaseModel):
    """API key validation request."""

    api_key: str
    provider: str = "anthropic"  # anthropic, openrouter, openai, google


class ApiKeyValidateResponse(BaseModel):
    """API key validation response."""

    success: bool
    error: str | None = None


class PreferencesRequest(BaseModel):
    """User preferences."""

    user_name: str | None = None
    timezone: str = "UTC"
    active_hours_start: str = "09:00"
    active_hours_end: str = "22:00"


class CompleteSetupRequest(BaseModel):
    """Complete setup request with all configuration."""

    channel: str | None = None
    channel_config: dict[str, str] | None = None
    preferences: PreferencesRequest | None = None
    api_key: str | None = None
    skip_api_key: bool = False


class SetupResponse(BaseModel):
    """Generic setup response."""

    success: bool
    message: str | None = None
    error: str | None = None
    created_files: list[str] | None = None


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/state", response_model=SetupStateResponse)
async def get_state():
    """Get current setup wizard state."""
    status = get_setup_status()
    return SetupStateResponse(
        is_complete=status["is_complete"],
        current_step=status["current_step"],
        completed_steps=status["completed_steps"],
        progress_percent=status["progress_percent"],
        primary_channel=status["primary_channel"],
        user_name=status["user_name"],
        started_at=status["started_at"],
        last_updated=status["last_updated"],
        detected_timezone=detect_timezone(),
    )


@router.post("/channel/validate", response_model=ChannelValidateResponse)
async def validate_channel_endpoint(request: ChannelValidateRequest):
    """Validate channel credentials without sending a message."""
    # Build config based on channel type
    if request.channel == "slack":
        config = {
            "bot_token": request.bot_token or "",
            "app_token": request.app_token or "",
        }
    else:
        config = {"token": request.token or ""}

    result = await validate_channel(request.channel, config)

    return ChannelValidateResponse(
        success=result.get("success", False),
        bot_id=result.get("bot_id"),
        bot_username=result.get("bot_username"),
        bot_name=result.get("bot_name"),
        team_name=result.get("team_name"),
        error=result.get("error"),
    )


@router.post("/channel/test", response_model=ChannelTestResponse)
async def send_test_message(request: ChannelTestRequest):
    """Send a test message to the configured channel."""
    try:
        if request.channel == "telegram":
            result = await _send_telegram_test(request.token, request.chat_id)
        elif request.channel == "discord":
            result = await _send_discord_test(request.token, request.channel_id)
        elif request.channel == "slack":
            result = await _send_slack_test(
                request.bot_token, request.app_token, request.channel_id
            )
        else:
            return ChannelTestResponse(
                success=False, error=f"Unknown channel: {request.channel}"
            )

        return ChannelTestResponse(
            success=result.get("success", False),
            message_id=result.get("message_id"),
            error=result.get("error"),
        )
    except Exception as e:
        return ChannelTestResponse(success=False, error=str(e))


@router.post("/apikey/validate", response_model=ApiKeyValidateResponse)
async def validate_api_key(request: ApiKeyValidateRequest):
    """Validate API key for the specified provider."""
    provider = request.provider.lower()

    if provider == "anthropic":
        result = await validate_anthropic_key(request.api_key)
    elif provider == "openrouter":
        result = await _validate_openrouter_key(request.api_key)
    elif provider == "openai":
        result = await _validate_openai_key(request.api_key)
    elif provider == "google":
        result = await _validate_google_key(request.api_key)
    else:
        return ApiKeyValidateResponse(
            success=False,
            error=f"Unknown provider: {provider}",
        )

    return ApiKeyValidateResponse(
        success=result.get("success", False),
        error=result.get("error"),
    )


async def _validate_openrouter_key(api_key: str) -> dict[str, Any]:
    """Validate OpenRouter API key by checking models endpoint."""
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {api_key}"}
            async with session.get(
                "https://openrouter.ai/api/v1/models",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return {"success": True}
                elif resp.status == 401:
                    return {"success": False, "error": "Invalid API key"}
                else:
                    error_text = await resp.text()
                    return {"success": False, "error": f"API error: {error_text}"}
    except ImportError:
        return {"success": False, "error": "aiohttp not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _validate_openai_key(api_key: str) -> dict[str, Any]:
    """Validate OpenAI API key by checking models endpoint."""
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {api_key}"}
            async with session.get(
                "https://api.openai.com/v1/models",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return {"success": True}
                elif resp.status == 401:
                    return {"success": False, "error": "Invalid API key"}
                else:
                    error_text = await resp.text()
                    return {"success": False, "error": f"API error: {error_text}"}
    except ImportError:
        return {"success": False, "error": "aiohttp not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _validate_google_key(api_key: str) -> dict[str, Any]:
    """Validate Google API key by checking Gemini models endpoint."""
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            # Google uses query parameter for API key
            url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return {"success": True}
                elif resp.status == 400 or resp.status == 403:
                    return {"success": False, "error": "Invalid API key"}
                else:
                    error_text = await resp.text()
                    return {"success": False, "error": f"API error: {error_text}"}
    except ImportError:
        return {"success": False, "error": "aiohttp not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/preferences")
async def save_preferences(request: PreferencesRequest):
    """Save user preferences to setup state."""
    state = SetupState.load()

    state.user_name = request.user_name
    state.timezone = request.timezone
    state.active_hours_start = request.active_hours_start
    state.active_hours_end = request.active_hours_end

    state.mark_step_complete(SetupStep.PREFERENCES)
    state.save()

    return {"success": True, "message": "Preferences saved"}


@router.post("/complete", response_model=SetupResponse)
async def complete_setup(request: CompleteSetupRequest):
    """Finalize setup and apply all configuration."""
    state = SetupState.load()

    # Apply channel config
    if request.channel:
        state.primary_channel = request.channel
        if request.channel_config:
            state.channel_config = request.channel_config
            state.channel_verified = True
        state.mark_step_complete(SetupStep.CHANNEL)

    # Apply preferences
    if request.preferences:
        state.user_name = request.preferences.user_name
        state.timezone = request.preferences.timezone
        state.active_hours_start = request.preferences.active_hours_start
        state.active_hours_end = request.preferences.active_hours_end
        state.mark_step_complete(SetupStep.PREFERENCES)

    # Mark security as complete (simplified for now)
    state.mark_step_complete(SetupStep.SECURITY)

    # Apply API key
    if request.api_key:
        state.api_key_set = True
        state.api_key_verified = True
        state.channel_config["anthropic_api_key"] = request.api_key
    elif request.skip_api_key:
        state.api_key_skipped = True

    state.mark_step_complete(SetupStep.API_KEY)
    state.mark_step_complete(SetupStep.TEST)
    state.mark_step_complete(SetupStep.COMPLETE)

    # Persist state to disk before applying configuration
    state.save()

    # Apply configuration to files
    result = apply_configuration(state)

    if result["success"]:
        return SetupResponse(
            success=True,
            message="Setup completed successfully",
            created_files=result.get("created_files", []),
        )
    else:
        return SetupResponse(
            success=False,
            error="; ".join(result.get("errors", ["Unknown error"])),
        )


@router.post("/reset", response_model=SetupResponse)
async def reset_setup_endpoint():
    """Reset setup state to start fresh."""
    result = reset_setup()
    return SetupResponse(
        success=result["success"],
        message="Setup state reset" if result["success"] else "Reset failed",
    )


# =============================================================================
# Test Message Helpers
# =============================================================================


async def _send_telegram_test(
    token: str | None, chat_id: str | None
) -> dict[str, Any]:
    """Send test message via Telegram."""
    if not token:
        return {"success": False, "error": "No token provided"}

    try:
        from telegram import Bot

        bot = Bot(token)

        # If no chat_id provided, we can't send a message yet
        # The user needs to message the bot first
        if not chat_id:
            return {
                "success": False,
                "error": "Please send a message to your bot first, then try again",
            }

        message = await bot.send_message(
            chat_id=chat_id,
            text="Hello from DexAI! Your setup is working correctly.",
        )
        return {"success": True, "message_id": str(message.message_id)}

    except ImportError:
        return {"success": False, "error": "python-telegram-bot not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _send_discord_test(
    token: str | None, channel_id: str | None
) -> dict[str, Any]:
    """Send test message via Discord."""
    if not token:
        return {"success": False, "error": "No token provided"}

    try:
        import aiohttp

        if not channel_id:
            return {"success": False, "error": "No channel ID provided"}

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bot {token}"}
            payload = {"content": "Hello from DexAI! Your setup is working correctly."}

            async with session.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"success": True, "message_id": data.get("id")}
                else:
                    error = await resp.text()
                    return {"success": False, "error": f"Discord API error: {error}"}

    except ImportError:
        return {"success": False, "error": "aiohttp not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _send_slack_test(
    bot_token: str | None, app_token: str | None, channel_id: str | None
) -> dict[str, Any]:
    """Send test message via Slack."""
    if not bot_token:
        return {"success": False, "error": "No bot token provided"}

    try:
        from slack_sdk.web.async_client import AsyncWebClient

        if not channel_id:
            return {"success": False, "error": "No channel ID provided"}

        client = AsyncWebClient(token=bot_token)
        response = await client.chat_postMessage(
            channel=channel_id,
            text="Hello from DexAI! Your setup is working correctly.",
        )

        if response.get("ok"):
            return {"success": True, "message_id": response.get("ts")}
        else:
            return {"success": False, "error": response.get("error", "Unknown error")}

    except ImportError:
        return {"success": False, "error": "slack-sdk not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}
