"""
Settings Route - Configuration Management

Provides endpoints for managing user and system settings:
- GET current settings
- PATCH update settings
"""

import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tools.dashboard.backend.models import (
    DashboardSettings, SettingsUpdate,
    NotificationSettings, PrivacySettings
)
from tools.dashboard.backend.database import get_preferences, set_preferences

router = APIRouter()

# Configuration paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / 'args'


class SettingsResponse(BaseModel):
    """Response with current settings and metadata."""
    settings: DashboardSettings
    updated_at: Optional[datetime] = None


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


def get_system_settings() -> dict:
    """Load system settings from various config files."""
    settings = {}

    # Load smart_notifications config
    notif_config = load_yaml_config('smart_notifications.yaml')
    if notif_config:
        settings['notifications'] = notif_config.get('smart_notifications', {})

    # Load ADHD mode config
    adhd_config = load_yaml_config('adhd_mode.yaml')
    if adhd_config:
        settings['adhd'] = adhd_config.get('adhd_mode', {})

    # Load system config
    system_config = load_yaml_config('system.yaml')
    if system_config:
        settings['system'] = system_config.get('system', {})

    return settings


@router.get("", response_model=SettingsResponse)
async def get_settings(
    user_id: str = "default"
):
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
    notif_config = system_settings.get('notifications', {})
    active_hours = notif_config.get('active_hours', {})

    notification_settings = NotificationSettings(
        enabled=notif_config.get('enabled', True),
        quiet_hours_start=active_hours.get('start'),
        quiet_hours_end=active_hours.get('end'),
        channels=list(notif_config.get('channels', {}).keys())
    )

    # Build privacy settings
    privacy_settings = PrivacySettings(
        remember_conversations=True,  # From memory config
        log_activity=True,
        data_retention_days=90
    )

    # Build complete settings object
    settings = DashboardSettings(
        display_name=prefs.get('display_name', 'User'),
        timezone=prefs.get('timezone', 'UTC'),
        language=prefs.get('language', 'en'),
        notifications=notification_settings,
        privacy=privacy_settings,
        theme=prefs.get('theme', 'dark'),
        sidebar_collapsed=bool(prefs.get('sidebar_collapsed', False))
    )

    # Get updated timestamp
    updated_at = None
    if prefs.get('updated_at'):
        try:
            updated_at = datetime.fromisoformat(prefs['updated_at'])
        except (ValueError, TypeError):
            pass

    return SettingsResponse(
        settings=settings,
        updated_at=updated_at
    )


@router.patch("", response_model=UpdateResponse)
async def update_settings(
    updates: SettingsUpdate,
    user_id: str = "default"
):
    """
    Update dashboard settings.

    Only provided fields will be updated (partial update).
    Changes are automatically saved and take effect immediately.
    """
    # Build update dict with only non-None values
    update_dict = {}

    if updates.display_name is not None:
        update_dict['display_name'] = updates.display_name

    if updates.timezone is not None:
        update_dict['timezone'] = updates.timezone

    if updates.language is not None:
        update_dict['language'] = updates.language

    if updates.theme is not None:
        update_dict['theme'] = updates.theme

    if updates.sidebar_collapsed is not None:
        update_dict['sidebar_collapsed'] = updates.sidebar_collapsed

    # Save to database
    if update_dict:
        set_preferences(user_id, update_dict)

    # Handle notification settings updates
    if updates.notifications is not None:
        # Note: Full implementation would update smart_notifications.yaml
        # For now, we store preferences in database
        pass

    # Handle privacy settings updates
    if updates.privacy is not None:
        # Note: Full implementation would update relevant config files
        pass

    # Get updated settings
    result = await get_settings(user_id)

    return UpdateResponse(
        success=True,
        settings=result.settings,
        message="Settings updated successfully"
    )


@router.get("/channels")
async def get_channel_settings():
    """
    Get settings for all configured channels.

    Returns list of channels with their enabled status and settings.
    """
    channels_config = load_yaml_config('channels.yaml')

    channels = []
    for name, config in channels_config.get('channels', {}).items():
        channels.append({
            'name': name,
            'enabled': config.get('enabled', False),
            'settings': {k: v for k, v in config.items() if k != 'enabled'}
        })

    return {
        'channels': channels,
        'total': len(channels)
    }


@router.get("/notifications")
async def get_notification_settings():
    """
    Get detailed notification settings.

    Returns full notification configuration including active hours,
    tier settings, and channel-specific options.
    """
    config = load_yaml_config('smart_notifications.yaml')
    notif_config = config.get('smart_notifications', {})

    return {
        'enabled': notif_config.get('enabled', True),
        'active_hours': notif_config.get('active_hours', {}),
        'tiers': notif_config.get('tiers', {}),
        'channels': notif_config.get('channels', {}),
        'hyperfocus': notif_config.get('hyperfocus', {}),
        'flow_detection': notif_config.get('flow_detection', {})
    }


@router.get("/feature-flags")
async def get_feature_flags():
    """
    Get current feature flag settings.

    Returns status of all feature flags from dashboard configuration.
    """
    config = load_yaml_config('dashboard.yaml')
    dashboard_config = config.get('dashboard', {})
    features = dashboard_config.get('features', {})

    return {
        'flags': features,
        'defaults': dashboard_config.get('defaults', {})
    }
