"""
Settings Route - Configuration Management

Provides endpoints for managing user and system settings:
- GET current settings
- PATCH update settings
"""

from datetime import datetime
from pathlib import Path

import yaml
from fastapi import APIRouter
from pydantic import BaseModel

from tools.dashboard.backend.database import get_preferences, set_preferences
from tools.dashboard.backend.models import (
    DashboardSettings,
    NotificationSettings,
    PrivacySettings,
    SettingsUpdate,
)


router = APIRouter()

# Configuration paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "args"


class SettingsResponse(BaseModel):
    """Response with current settings and metadata."""

    settings: DashboardSettings
    updated_at: datetime | None = None


class UpdateResponse(BaseModel):
    """Response after updating settings."""

    success: bool
    settings: DashboardSettings
    message: str


def load_yaml_config(filename: str) -> dict:
    """Load a YAML config file."""
    config_file = CONFIG_PATH / filename
    if config_file.exists():
        with open(config_file) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_yaml_config(filename: str, config: dict) -> bool:
    """
    Save a YAML config file atomically.

    Uses write-to-temp + rename pattern to prevent corruption.

    Args:
        filename: Config filename (e.g., 'smart_notifications.yaml')
        config: Configuration dict to save

    Returns:
        True if successful, False otherwise
    """
    import os
    import tempfile

    config_file = CONFIG_PATH / filename

    try:
        # Ensure the args directory exists
        CONFIG_PATH.mkdir(parents=True, exist_ok=True)

        # Write to temporary file first
        fd, temp_path = tempfile.mkstemp(
            suffix=".yaml",
            prefix=filename.replace(".yaml", "_"),
            dir=CONFIG_PATH,
        )
        try:
            with os.fdopen(fd, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            # Atomic rename
            os.replace(temp_path, config_file)
            return True
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Failed to save config {filename}: {e}")
        return False


def get_system_settings() -> dict:
    """Load system settings from various config files."""
    settings = {}

    # Load smart_notifications config
    notif_config = load_yaml_config("smart_notifications.yaml")
    if notif_config:
        settings["notifications"] = notif_config.get("smart_notifications", {})

    # Load ADHD mode config
    adhd_config = load_yaml_config("adhd_mode.yaml")
    if adhd_config:
        settings["adhd"] = adhd_config.get("adhd_mode", {})

    # Load system config
    system_config = load_yaml_config("system.yaml")
    if system_config:
        settings["system"] = system_config.get("system", {})

    return settings


@router.get("", response_model=SettingsResponse)
async def get_settings(user_id: str = "default"):
    """
    Get current dashboard settings.

    Returns combined user preferences and system settings.
    The user_id parameter defaults to "default" for single-user mode.
    """
    # Get user preferences from database
    prefs = get_preferences(user_id)

    # Get system settings from config files
    system_settings = get_system_settings()

    # Build notification settings
    notif_config = system_settings.get("notifications", {})
    active_hours = notif_config.get("active_hours", {})

    notification_settings = NotificationSettings(
        enabled=notif_config.get("enabled", True),
        quiet_hours_start=active_hours.get("start"),
        quiet_hours_end=active_hours.get("end"),
        channels=list(notif_config.get("channels", {}).keys()),
    )

    # Build privacy settings
    privacy_settings = PrivacySettings(
        remember_conversations=True,  # From memory config
        log_activity=True,
        data_retention_days=90,
    )

    # Build complete settings object
    settings = DashboardSettings(
        display_name=prefs.get("display_name", "User"),
        timezone=prefs.get("timezone", "UTC"),
        language=prefs.get("language", "en"),
        notifications=notification_settings,
        privacy=privacy_settings,
        theme=prefs.get("theme", "dark"),
        sidebar_collapsed=bool(prefs.get("sidebar_collapsed", False)),
    )

    # Get updated timestamp
    updated_at = None
    if prefs.get("updated_at"):
        try:
            updated_at = datetime.fromisoformat(prefs["updated_at"])
        except (ValueError, TypeError):
            pass

    return SettingsResponse(settings=settings, updated_at=updated_at)


@router.patch("", response_model=UpdateResponse)
async def update_settings(updates: SettingsUpdate, user_id: str = "default"):
    """
    Update dashboard settings.

    Only provided fields will be updated (partial update).
    Changes are automatically saved and take effect immediately.
    """
    # Build update dict with only non-None values
    update_dict = {}

    if updates.display_name is not None:
        update_dict["display_name"] = updates.display_name

    if updates.timezone is not None:
        update_dict["timezone"] = updates.timezone

    if updates.language is not None:
        update_dict["language"] = updates.language

    if updates.theme is not None:
        update_dict["theme"] = updates.theme

    if updates.sidebar_collapsed is not None:
        update_dict["sidebar_collapsed"] = updates.sidebar_collapsed

    # Save to database
    if update_dict:
        set_preferences(user_id, update_dict)

    # Handle notification settings updates
    if updates.notifications is not None:
        notif = updates.notifications

        # Load current config
        config = load_yaml_config("smart_notifications.yaml")
        if "smart_notifications" not in config:
            config["smart_notifications"] = {}

        sn = config["smart_notifications"]

        # Update enabled status
        if notif.enabled is not None:
            sn["enabled"] = notif.enabled

        # Update quiet hours
        if notif.quiet_hours_start is not None or notif.quiet_hours_end is not None:
            if "active_hours" not in sn:
                sn["active_hours"] = {}
            if notif.quiet_hours_start is not None:
                sn["active_hours"]["start"] = notif.quiet_hours_start
            if notif.quiet_hours_end is not None:
                sn["active_hours"]["end"] = notif.quiet_hours_end

        # Save updated config
        save_yaml_config("smart_notifications.yaml", config)

    # Handle privacy settings updates
    if updates.privacy is not None:
        priv = updates.privacy

        # Load or create privacy config
        config = load_yaml_config("privacy.yaml")
        if "privacy" not in config:
            config["privacy"] = {}

        pc = config["privacy"]

        # Update settings
        if priv.remember_conversations is not None:
            pc["remember_conversations"] = priv.remember_conversations
        if priv.log_activity is not None:
            pc["log_activity"] = priv.log_activity
        if priv.data_retention_days is not None:
            pc["data_retention_days"] = priv.data_retention_days

        # Save updated config
        save_yaml_config("privacy.yaml", config)

    # Get updated settings
    result = await get_settings(user_id)

    # Log settings change to audit
    try:
        from tools.dashboard.backend.database import log_audit

        changed_fields = list(update_dict.keys())
        if updates.notifications is not None:
            changed_fields.append("notifications")
        if updates.privacy is not None:
            changed_fields.append("privacy")

        log_audit(
            event_type="config.changed",
            severity="info",
            actor=user_id,
            target="settings",
            details={"changed_fields": changed_fields},
        )
    except Exception:
        pass

    return UpdateResponse(
        success=True, settings=result.settings, message="Settings updated successfully"
    )


@router.get("/channels")
async def get_channel_settings():
    """
    Get settings for all configured channels.

    Returns list of channels with their enabled status and settings.
    """
    channels_config = load_yaml_config("channels.yaml")

    channels = []
    for name, config in channels_config.get("channels", {}).items():
        channels.append(
            {
                "name": name,
                "enabled": config.get("enabled", False),
                "settings": {k: v for k, v in config.items() if k != "enabled"},
            }
        )

    return {"channels": channels, "total": len(channels)}


@router.get("/notifications")
async def get_notification_settings():
    """
    Get detailed notification settings.

    Returns full notification configuration including active hours,
    tier settings, and channel-specific options.
    """
    config = load_yaml_config("smart_notifications.yaml")
    notif_config = config.get("smart_notifications", {})

    return {
        "enabled": notif_config.get("enabled", True),
        "active_hours": notif_config.get("active_hours", {}),
        "tiers": notif_config.get("tiers", {}),
        "channels": notif_config.get("channels", {}),
        "hyperfocus": notif_config.get("hyperfocus", {}),
        "flow_detection": notif_config.get("flow_detection", {}),
    }


@router.get("/feature-flags")
async def get_feature_flags():
    """
    Get current feature flag settings.

    Returns status of all feature flags from dashboard configuration.
    """
    config = load_yaml_config("dashboard.yaml")
    dashboard_config = config.get("dashboard", {})
    features = dashboard_config.get("features", {})

    return {"flags": features, "defaults": dashboard_config.get("defaults", {})}


# =============================================================================
# Channel Token Management
# =============================================================================


def _mask_token(token: str | None) -> str:
    """Mask a token for display, showing only first 4 and last 4 chars."""
    if not token:
        return ""
    if len(token) <= 12:
        return "*" * len(token)
    return f"{token[:4]}{'*' * (len(token) - 8)}{token[-4:]}"


def _read_env_file() -> dict[str, str]:
    """Read the .env file and return key-value pairs."""
    env_file = PROJECT_ROOT / ".env"
    env_vars: dict[str, str] = {}
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    return env_vars


def _write_env_file(updates: dict[str, str]) -> bool:
    """
    Update specific keys in the .env file, preserving comments and structure.

    Args:
        updates: Dict of key-value pairs to update/add

    Returns:
        True if successful
    """
    import os
    import tempfile

    env_file = PROJECT_ROOT / ".env"
    lines: list[str] = []
    updated_keys: set[str] = set()

    # Read existing file
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                original_line = line
                stripped = line.strip()

                # Check if this line has a key we want to update
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _, _ = stripped.partition("=")
                    key = key.strip()
                    if key in updates:
                        # Replace the value
                        lines.append(f"{key}={updates[key]}\n")
                        updated_keys.add(key)
                        continue

                lines.append(original_line)

    # Add any new keys that weren't in the file
    for key, value in updates.items():
        if key not in updated_keys:
            lines.append(f"{key}={value}\n")

    # Write atomically
    try:
        fd, temp_path = tempfile.mkstemp(suffix=".env", dir=PROJECT_ROOT)
        try:
            with os.fdopen(fd, "w") as f:
                f.writelines(lines)
            os.replace(temp_path, env_file)
            return True
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Failed to update .env: {e}")
        return False


@router.get("/tokens")
async def get_channel_tokens():
    """
    Get channel token status (masked for security).

    Returns whether tokens are configured and their masked values.
    Does NOT return actual token values for security.
    """
    import os

    # First check environment variables (runtime)
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    discord_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    slack_bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    slack_app_token = os.environ.get("SLACK_APP_TOKEN", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    google_key = os.environ.get("GOOGLE_API_KEY", "")

    # If not in env, check .env file
    env_vars = _read_env_file()
    telegram_token = telegram_token or env_vars.get("TELEGRAM_BOT_TOKEN", "")
    discord_token = discord_token or env_vars.get("DISCORD_BOT_TOKEN", "")
    slack_bot_token = slack_bot_token or env_vars.get("SLACK_BOT_TOKEN", "")
    slack_app_token = slack_app_token or env_vars.get("SLACK_APP_TOKEN", "")
    anthropic_key = anthropic_key or env_vars.get("ANTHROPIC_API_KEY", "")
    openrouter_key = openrouter_key or env_vars.get("OPENROUTER_API_KEY", "")
    openai_key = openai_key or env_vars.get("OPENAI_API_KEY", "")
    google_key = google_key or env_vars.get("GOOGLE_API_KEY", "")

    return {
        "telegram": {
            "configured": bool(telegram_token),
            "masked_token": _mask_token(telegram_token),
        },
        "discord": {
            "configured": bool(discord_token),
            "masked_token": _mask_token(discord_token),
        },
        "slack": {
            "configured": bool(slack_bot_token),
            "masked_bot_token": _mask_token(slack_bot_token),
            "masked_app_token": _mask_token(slack_app_token),
        },
        "anthropic": {
            "configured": bool(anthropic_key),
            "masked_key": _mask_token(anthropic_key),
        },
        "openrouter": {
            "configured": bool(openrouter_key),
            "masked_key": _mask_token(openrouter_key),
        },
        "openai": {
            "configured": bool(openai_key),
            "masked_key": _mask_token(openai_key),
        },
        "google": {
            "configured": bool(google_key),
            "masked_key": _mask_token(google_key),
        },
    }


class TokenUpdateRequest(BaseModel):
    """Request to update channel tokens."""

    telegram_token: str | None = None
    discord_token: str | None = None
    slack_bot_token: str | None = None
    slack_app_token: str | None = None
    anthropic_key: str | None = None
    openrouter_key: str | None = None
    openai_key: str | None = None
    google_key: str | None = None


# =============================================================================
# Energy Level Management
# =============================================================================


class EnergyUpdateRequest(BaseModel):
    """Request to update energy level."""

    level: str  # low, medium, high


@router.get("/energy")
async def get_energy_level(user_id: str = "default"):
    """
    Get the current energy level setting.

    Energy level affects task matching and recommendations.
    """
    prefs = get_preferences(user_id) or {}
    activity_filters = prefs.get("activity_filters") or {}

    if isinstance(activity_filters, str):
        import json
        try:
            activity_filters = json.loads(activity_filters)
        except Exception:
            activity_filters = {}

    if not isinstance(activity_filters, dict):
        activity_filters = {}

    energy_level = activity_filters.get("energy_level", "medium")

    return {
        "level": energy_level,
        "options": ["low", "medium", "high"],
    }


@router.post("/energy")
async def set_energy_level(request: EnergyUpdateRequest, user_id: str = "default"):
    """
    Set the current energy level.

    This affects which tasks are recommended and how responses are formatted.
    """
    valid_levels = ["low", "medium", "high"]
    if request.level not in valid_levels:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Invalid energy level. Must be one of: {valid_levels}"
        )

    # Get current preferences
    prefs = get_preferences(user_id) or {}
    activity_filters = prefs.get("activity_filters") or {}

    if isinstance(activity_filters, str):
        import json
        try:
            activity_filters = json.loads(activity_filters)
        except Exception:
            activity_filters = {}

    if not isinstance(activity_filters, dict):
        activity_filters = {}

    # Update energy level
    activity_filters["energy_level"] = request.level

    # Save back
    set_preferences(user_id, {"activity_filters": activity_filters})

    # Also try to update the energy tracker if available
    try:
        from tools.learning.energy_tracker import set_current_energy
        set_current_energy(user_id=user_id, level=request.level, source="dashboard")
    except ImportError:
        pass
    except Exception:
        pass

    return {
        "success": True,
        "level": request.level,
        "message": f"Energy level set to {request.level}",
    }


@router.put("/tokens")
async def update_channel_tokens(request: TokenUpdateRequest):
    """
    Update channel tokens in the .env file.

    Only updates tokens that are provided (non-None and non-empty).
    Empty strings are ignored to prevent accidental deletion.
    """
    updates: dict[str, str] = {}

    if request.telegram_token:
        updates["TELEGRAM_BOT_TOKEN"] = request.telegram_token

    if request.discord_token:
        updates["DISCORD_BOT_TOKEN"] = request.discord_token

    if request.slack_bot_token:
        updates["SLACK_BOT_TOKEN"] = request.slack_bot_token

    if request.slack_app_token:
        updates["SLACK_APP_TOKEN"] = request.slack_app_token

    if request.anthropic_key:
        updates["ANTHROPIC_API_KEY"] = request.anthropic_key

    if request.openrouter_key:
        updates["OPENROUTER_API_KEY"] = request.openrouter_key

    if request.openai_key:
        updates["OPENAI_API_KEY"] = request.openai_key

    if request.google_key:
        updates["GOOGLE_API_KEY"] = request.google_key

    if not updates:
        return {"success": True, "message": "No tokens to update", "updated": []}

    success = _write_env_file(updates)

    # Log token update to audit (security-sensitive operation)
    try:
        from tools.dashboard.backend.database import log_audit

        # Map env var names to provider names for clearer logging
        provider_map = {
            "TELEGRAM_BOT_TOKEN": "telegram",
            "DISCORD_BOT_TOKEN": "discord",
            "SLACK_BOT_TOKEN": "slack",
            "SLACK_APP_TOKEN": "slack",
            "ANTHROPIC_API_KEY": "anthropic",
            "OPENROUTER_API_KEY": "openrouter",
            "OPENAI_API_KEY": "openai",
            "GOOGLE_API_KEY": "google",
        }
        providers_updated = list({provider_map.get(k, k) for k in updates.keys()})

        log_audit(
            event_type="config.tokens_updated",
            severity="warning",  # Token changes are security-relevant
            actor="system",
            target="tokens",
            details={
                "providers": providers_updated,
                "success": success,
            },
        )
    except Exception:
        pass

    if success:
        return {
            "success": True,
            "message": "Tokens updated. Restart services to apply changes.",
            "updated": list(updates.keys()),
        }
    else:
        return {
            "success": False,
            "error": "Failed to update .env file",
            "updated": [],
        }
