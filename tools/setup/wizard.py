"""
Tool: Setup Wizard Core
Purpose: State management and configuration for DexAI installation

Handles:
- Setup state persistence (save/load progress)
- Channel connection validation
- Configuration file generation
- Credential storage via vault

Usage:
    python tools/setup/wizard.py --status
    python tools/setup/wizard.py --reset
    python tools/setup/wizard.py --complete

Dependencies:
    - pyyaml (pip install pyyaml)
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.setup import CONFIG_PATH, DATA_PATH, SETUP_COMPLETE_FLAG, SETUP_STATE_PATH  # noqa: E402


class SetupStep(Enum):
    """Wizard steps in order."""

    WELCOME = "welcome"
    CHANNEL = "channel"
    PREFERENCES = "preferences"
    SECURITY = "security"
    API_KEY = "api_key"
    TEST = "test"
    COMPLETE = "complete"

    @classmethod
    def order(cls) -> list["SetupStep"]:
        """Return steps in display order."""
        return [
            cls.WELCOME,
            cls.CHANNEL,
            cls.PREFERENCES,
            cls.SECURITY,
            cls.API_KEY,
            cls.TEST,
            cls.COMPLETE,
        ]

    def next(self) -> Optional["SetupStep"]:
        """Get next step in sequence."""
        order = self.order()
        try:
            idx = order.index(self)
            if idx < len(order) - 1:
                return order[idx + 1]
        except ValueError:
            pass
        return None

    def previous(self) -> Optional["SetupStep"]:
        """Get previous step in sequence."""
        order = self.order()
        try:
            idx = order.index(self)
            if idx > 0:
                return order[idx - 1]
        except ValueError:
            pass
        return None


@dataclass
class SetupState:
    """
    Persistent setup wizard state.

    Tracks progress through the wizard and stores user choices.
    Can be saved/loaded to allow interrupting and resuming setup.
    """

    # Progress tracking
    current_step: SetupStep = SetupStep.WELCOME
    completed_steps: list[SetupStep] = field(default_factory=list)
    started_at: str | None = None
    last_updated: str | None = None

    # Channel configuration
    primary_channel: str | None = None  # telegram, discord, slack, or None
    channel_config: dict[str, Any] = field(default_factory=dict)
    channel_verified: bool = False

    # User preferences
    user_name: str | None = None
    timezone: str = "UTC"
    active_hours_start: str = "09:00"
    active_hours_end: str = "22:00"

    # Security
    master_password_set: bool = False

    # API key
    api_key_set: bool = False
    api_key_verified: bool = False
    api_key_skipped: bool = False

    # Test results
    test_message_sent: bool = False
    test_message_received: bool = False

    def __post_init__(self):
        """Handle enum conversion after loading."""
        if isinstance(self.current_step, str):
            self.current_step = SetupStep(self.current_step)
        if self.completed_steps and isinstance(self.completed_steps[0], str):
            self.completed_steps = [SetupStep(s) for s in self.completed_steps]

    def mark_step_complete(self, step: SetupStep) -> None:
        """Mark a step as completed and advance."""
        if step not in self.completed_steps:
            self.completed_steps.append(step)

        next_step = step.next()
        if next_step:
            self.current_step = next_step

        self.last_updated = datetime.now().isoformat()

    def can_proceed_to(self, step: SetupStep) -> bool:
        """Check if we can navigate to a step."""
        # Can always go to welcome
        if step == SetupStep.WELCOME:
            return True

        # Can go to any completed step
        if step in self.completed_steps:
            return True

        # Can only go to next step if previous is complete
        prev = step.previous()
        if prev and prev in self.completed_steps:
            return True

        # Current step is always accessible
        return step == self.current_step

    def get_progress_percent(self) -> int:
        """Get setup progress as percentage."""
        total_steps = len(SetupStep.order()) - 1  # Exclude COMPLETE
        completed = len(self.completed_steps)
        return min(100, int((completed / total_steps) * 100))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert enums to strings
        data["current_step"] = self.current_step.value
        data["completed_steps"] = [s.value for s in self.completed_steps]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SetupState":
        """Create from dictionary."""
        # Handle enum conversion
        if "current_step" in data:
            data["current_step"] = SetupStep(data["current_step"])
        if "completed_steps" in data:
            data["completed_steps"] = [SetupStep(s) for s in data["completed_steps"]]
        return cls(**data)

    def save(self, path: Path | None = None) -> dict[str, Any]:
        """
        Save setup state to disk.

        Args:
            path: Override default save path

        Returns:
            dict with success status
        """
        save_path = path or SETUP_STATE_PATH
        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(save_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            return {"success": True, "path": str(save_path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def load(cls, path: Path | None = None) -> "SetupState":
        """
        Load setup state from disk.

        Args:
            path: Override default load path

        Returns:
            SetupState instance (new or loaded)
        """
        load_path = path or SETUP_STATE_PATH

        if load_path.exists():
            try:
                with open(load_path) as f:
                    data = json.load(f)
                return cls.from_dict(data)
            except Exception:
                pass

        # Return fresh state
        state = cls()
        state.started_at = datetime.now().isoformat()
        return state


# =============================================================================
# Channel Validation
# =============================================================================


async def validate_telegram_token(token: str) -> dict[str, Any]:
    """
    Validate a Telegram bot token.

    Args:
        token: Telegram bot token from BotFather

    Returns:
        dict with success status and bot info
    """
    try:
        from telegram import Bot

        bot = Bot(token)
        me = await bot.get_me()
        return {
            "success": True,
            "bot_id": me.id,
            "bot_username": me.username,
            "bot_name": me.first_name,
        }
    except ImportError:
        return {
            "success": False,
            "error": "python-telegram-bot not installed. Run: pip install python-telegram-bot",
        }
    except Exception as e:
        error_msg = str(e)
        if "Unauthorized" in error_msg or "Invalid token" in error_msg.lower():
            return {"success": False, "error": "Invalid token. Please check and try again."}
        return {"success": False, "error": f"Connection failed: {error_msg}"}


async def validate_discord_token(token: str) -> dict[str, Any]:
    """
    Validate a Discord bot token.

    Args:
        token: Discord bot token

    Returns:
        dict with success status and bot info
    """
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bot {token}"}
            async with session.get(
                "https://discord.com/api/v10/users/@me", headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "success": True,
                        "bot_id": data.get("id"),
                        "bot_username": data.get("username"),
                        "bot_name": data.get("username"),
                    }
                elif resp.status == 401:
                    return {"success": False, "error": "Invalid token. Please check and try again."}
                else:
                    return {"success": False, "error": f"Discord API error: {resp.status}"}
    except ImportError:
        return {"success": False, "error": "aiohttp not installed. Run: pip install aiohttp"}
    except Exception as e:
        return {"success": False, "error": f"Connection failed: {e!s}"}


async def validate_slack_tokens(bot_token: str, app_token: str) -> dict[str, Any]:
    """
    Validate Slack tokens.

    Args:
        bot_token: Slack bot token (xoxb-...)
        app_token: Slack app token (xapp-...)

    Returns:
        dict with success status and bot info
    """
    try:
        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=bot_token)
        response = await client.auth_test()

        if response.get("ok"):
            return {
                "success": True,
                "bot_id": response.get("bot_id"),
                "bot_username": response.get("user"),
                "team_name": response.get("team"),
            }
        else:
            return {"success": False, "error": response.get("error", "Unknown error")}
    except ImportError:
        return {"success": False, "error": "slack-sdk not installed. Run: pip install slack-sdk"}
    except Exception as e:
        error_msg = str(e)
        if "invalid_auth" in error_msg.lower():
            return {"success": False, "error": "Invalid token. Please check and try again."}
        return {"success": False, "error": f"Connection failed: {error_msg}"}


async def validate_channel(channel: str, config: dict[str, str]) -> dict[str, Any]:
    """
    Validate channel connection.

    Args:
        channel: Channel name (telegram, discord, slack)
        config: Channel-specific configuration

    Returns:
        dict with validation result
    """
    if channel == "telegram":
        token = config.get("token", "")
        if not token:
            return {"success": False, "error": "No token provided"}
        return await validate_telegram_token(token)

    elif channel == "discord":
        token = config.get("token", "")
        if not token:
            return {"success": False, "error": "No token provided"}
        return await validate_discord_token(token)

    elif channel == "slack":
        bot_token = config.get("bot_token", "")
        app_token = config.get("app_token", "")
        if not bot_token or not app_token:
            return {"success": False, "error": "Both bot token and app token required"}
        return await validate_slack_tokens(bot_token, app_token)

    else:
        return {"success": False, "error": f"Unknown channel: {channel}"}


# =============================================================================
# Test Message Sending
# =============================================================================


async def send_test_message(channel: str, config: dict[str, str]) -> dict[str, Any]:
    """
    Send a test message to the configured channel.

    Args:
        channel: Channel name (telegram, discord, slack)
        config: Channel-specific configuration including chat/channel ID

    Returns:
        dict with send result and message ID
    """
    if channel == "telegram":
        return await send_telegram_test_message(
            config.get("token", ""),
            config.get("chat_id"),
        )
    elif channel == "discord":
        return await send_discord_test_message(
            config.get("token", ""),
            config.get("channel_id"),
        )
    elif channel == "slack":
        return await send_slack_test_message(
            config.get("bot_token", ""),
            config.get("channel_id"),
        )
    else:
        return {"success": False, "error": f"Unknown channel: {channel}"}


async def send_telegram_test_message(
    token: str, chat_id: str | None
) -> dict[str, Any]:
    """
    Send a test message via Telegram.

    Args:
        token: Telegram bot token
        chat_id: Chat ID to send to (optional, bot must have received a message first)

    Returns:
        dict with send result
    """
    if not token:
        return {"success": False, "error": "No token provided"}

    try:
        from telegram import Bot

        bot = Bot(token)

        # If no chat_id provided, we can't send a message yet
        if not chat_id:
            # Try to get updates to find a chat
            updates = await bot.get_updates(limit=1, timeout=1)
            if updates:
                chat_id = str(updates[0].message.chat.id)
            else:
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


async def send_discord_test_message(
    token: str, channel_id: str | None
) -> dict[str, Any]:
    """
    Send a test message via Discord.

    Args:
        token: Discord bot token
        channel_id: Channel ID to send to

    Returns:
        dict with send result
    """
    if not token:
        return {"success": False, "error": "No token provided"}

    if not channel_id:
        return {"success": False, "error": "No channel ID provided"}

    try:
        import aiohttp

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


async def send_slack_test_message(
    bot_token: str, channel_id: str | None
) -> dict[str, Any]:
    """
    Send a test message via Slack.

    Args:
        bot_token: Slack bot token
        channel_id: Channel ID to send to

    Returns:
        dict with send result
    """
    if not bot_token:
        return {"success": False, "error": "No bot token provided"}

    if not channel_id:
        return {"success": False, "error": "No channel ID provided"}

    try:
        from slack_sdk.web.async_client import AsyncWebClient

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


# =============================================================================
# API Key Validation
# =============================================================================


async def validate_anthropic_key(api_key: str) -> dict[str, Any]:
    """
    Validate an Anthropic API key.

    Args:
        api_key: Anthropic API key (sk-ant-...)

    Returns:
        dict with validation result
    """
    try:
        import anthropic

        # Use async client for proper async context
        client = anthropic.AsyncAnthropic(api_key=api_key)

        # Make a minimal API call to validate using current model
        await client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}],
        )

        return {"success": True, "message": "API key is valid"}
    except ImportError:
        return {
            "success": False,
            "error": "anthropic package not installed. Run: pip install anthropic",
        }
    except Exception as e:
        error_msg = str(e)
        if "invalid_api_key" in error_msg.lower() or "401" in error_msg:
            return {"success": False, "error": "Invalid API key. Please check and try again."}
        if "credit" in error_msg.lower() or "billing" in error_msg.lower():
            return {
                "success": False,
                "error": "API key valid but no credits. Set up billing at console.anthropic.com",
            }
        if "could not find" in error_msg.lower() or "model" in error_msg.lower():
            return {"success": False, "error": f"Model error: {error_msg}"}
        return {"success": False, "error": f"Validation failed: {error_msg}"}


# =============================================================================
# Configuration Generation
# =============================================================================


def apply_configuration(state: SetupState) -> dict[str, Any]:
    """
    Apply setup configuration to the system.

    Creates/updates:
    - args/user.yaml (user preferences)
    - args/channels.yaml (channel settings)
    - Vault secrets (tokens)
    - setup_complete.flag

    Args:
        state: Completed setup state

    Returns:
        dict with success status and created files
    """
    created_files = []
    errors = []

    # Ensure directories exist
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    DATA_PATH.mkdir(parents=True, exist_ok=True)

    # 1. Create args/user.yaml
    try:
        user_config = {
            "user": {"name": state.user_name or "User", "timezone": state.timezone},
            "active_hours": {
                "start": state.active_hours_start,
                "end": state.active_hours_end,
                "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
            },
            "preferences": {"notification_style": "gentle", "brevity_default": True},
        }

        import yaml

        user_path = CONFIG_PATH / "user.yaml"
        with open(user_path, "w") as f:
            yaml.dump(user_config, f, default_flow_style=False, sort_keys=False)
        created_files.append(str(user_path))
    except Exception as e:
        errors.append(f"Failed to create user.yaml: {e}")

    # 2. Update channels.yaml with primary channel
    if state.primary_channel:
        try:
            channels_path = CONFIG_PATH / "channels.yaml"

            # Load existing
            if channels_path.exists():
                with open(channels_path) as f:
                    channels_config = yaml.safe_load(f) or {}
            else:
                channels_config = {"channels": {}}

            # Ensure channels key exists
            if "channels" not in channels_config:
                channels_config["channels"] = {}

            # Set primary channel
            for ch in ["telegram", "discord", "slack"]:
                if ch in channels_config["channels"]:
                    channels_config["channels"][ch]["enabled"] = ch == state.primary_channel
                    channels_config["channels"][ch]["primary"] = ch == state.primary_channel

            with open(channels_path, "w") as f:
                yaml.dump(channels_config, f, default_flow_style=False, sort_keys=False)
            created_files.append(str(channels_path))
        except Exception as e:
            errors.append(f"Failed to update channels.yaml: {e}")

    # 3. Store channel credentials in vault
    if state.primary_channel and state.channel_config:
        try:
            from tools.security import vault

            if state.primary_channel == "telegram":
                token = state.channel_config.get("token")
                if token:
                    vault.set_secret("TELEGRAM_BOT_TOKEN", token, namespace="channels")

            elif state.primary_channel == "discord":
                token = state.channel_config.get("token")
                if token:
                    vault.set_secret("DISCORD_BOT_TOKEN", token, namespace="channels")

            elif state.primary_channel == "slack":
                bot_token = state.channel_config.get("bot_token")
                app_token = state.channel_config.get("app_token")
                if bot_token:
                    vault.set_secret("SLACK_BOT_TOKEN", bot_token, namespace="channels")
                if app_token:
                    vault.set_secret("SLACK_APP_TOKEN", app_token, namespace="channels")
        except Exception as e:
            errors.append(f"Failed to store channel credentials: {e}")

    # 4. Store API key in vault (if set)
    if state.api_key_set and state.channel_config.get("anthropic_api_key"):
        try:
            from tools.security import vault

            vault.set_secret(
                "ANTHROPIC_API_KEY",
                state.channel_config.get("anthropic_api_key"),
                namespace="default",
            )
        except Exception as e:
            errors.append(f"Failed to store API key: {e}")

    # 5. Create setup complete flag
    try:
        SETUP_COMPLETE_FLAG.touch()
        created_files.append(str(SETUP_COMPLETE_FLAG))
    except Exception as e:
        errors.append(f"Failed to create completion flag: {e}")

    return {"success": len(errors) == 0, "created_files": created_files, "errors": errors}


def is_setup_complete() -> bool:
    """Check if setup has been completed."""
    return SETUP_COMPLETE_FLAG.exists()


def reset_setup() -> dict[str, Any]:
    """
    Reset setup state (start fresh).

    Removes:
    - setup_state.json
    - setup_complete.flag

    Does NOT remove:
    - Credentials in vault
    - Configuration files

    Returns:
        dict with success status
    """
    removed = []

    if SETUP_STATE_PATH.exists():
        SETUP_STATE_PATH.unlink()
        removed.append(str(SETUP_STATE_PATH))

    if SETUP_COMPLETE_FLAG.exists():
        SETUP_COMPLETE_FLAG.unlink()
        removed.append(str(SETUP_COMPLETE_FLAG))

    return {"success": True, "removed": removed}


def get_setup_status() -> dict[str, Any]:
    """
    Get current setup status.

    Returns:
        dict with setup status information
    """
    state = SetupState.load()

    return {
        "is_complete": is_setup_complete(),
        "current_step": state.current_step.value,
        "completed_steps": [s.value for s in state.completed_steps],
        "progress_percent": state.get_progress_percent(),
        "primary_channel": state.primary_channel,
        "user_name": state.user_name,
        "started_at": state.started_at,
        "last_updated": state.last_updated,
    }


# =============================================================================
# Dynamic Missing Fields Detection
# =============================================================================


def get_missing_setup_fields() -> list[dict[str, Any]]:
    """
    Check which setup fields are still missing or using defaults.

    Inspects args/user.yaml, vault secrets, and environment to determine
    what configuration is incomplete. Returns field definitions that can
    be injected into the system prompt or used by the setup flow.

    Returns:
        List of field dicts: [{"field": str, "label": str, "type": str, ...}]
    """
    missing: list[dict[str, Any]] = []

    # --- Required fields ---

    # 1. API key (most critical)
    import os

    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not has_api_key:
        try:
            from tools.security import vault

            has_api_key = bool(vault.get_secret("ANTHROPIC_API_KEY", namespace="default"))
        except Exception:
            pass

    if not has_api_key:
        missing.append(
            {
                "field": "anthropic_api_key",
                "label": "Anthropic API Key",
                "type": "secure_input",
                "required": True,
                "description": "Required to power all AI features",
                "placeholder": "sk-ant-...",
            }
        )

    # 2. User name
    user_name = _get_user_yaml_value("user", "name")
    if not user_name or user_name == "User":
        missing.append(
            {
                "field": "user_name",
                "label": "Your Name",
                "type": "text_input",
                "required": True,
                "description": "So I know what to call you",
                "placeholder": "e.g. Alex",
            }
        )

    # 3. Timezone
    timezone = _get_user_yaml_value("user", "timezone")
    if not timezone or timezone == "UTC":
        # Detect as default
        detected_tz = detect_timezone()
        common_timezones = [
            {"value": "America/New_York", "label": "Eastern (US)", "description": "UTC-5"},
            {"value": "America/Chicago", "label": "Central (US)", "description": "UTC-6"},
            {"value": "America/Denver", "label": "Mountain (US)", "description": "UTC-7"},
            {"value": "America/Los_Angeles", "label": "Pacific (US)", "description": "UTC-8"},
            {"value": "Europe/London", "label": "London", "description": "UTC+0"},
            {"value": "Europe/Paris", "label": "Paris / Berlin", "description": "UTC+1"},
            {"value": "Asia/Tokyo", "label": "Tokyo", "description": "UTC+9"},
            {"value": "Australia/Sydney", "label": "Sydney", "description": "UTC+11"},
        ]
        missing.append(
            {
                "field": "timezone",
                "label": "Your Timezone",
                "type": "select",
                "required": True,
                "description": "For scheduling and time-aware features",
                "default_value": detected_tz if detected_tz != "UTC" else "",
                "options": common_timezones,
            }
        )

    return missing


def _get_user_yaml_value(*keys: str) -> Any:
    """Read a nested value from args/user.yaml."""
    try:
        import yaml

        user_yaml_path = CONFIG_PATH / "user.yaml"
        if not user_yaml_path.exists():
            return None
        with open(user_yaml_path) as f:
            data = yaml.safe_load(f) or {}
        for key in keys:
            if not isinstance(data, dict):
                return None
            data = data.get(key)
        return data
    except Exception:
        return None


def populate_workspace_files(workspace_path: Path, field: str, value: str) -> None:
    """
    Update workspace file templates with a setup value.

    Called by dexai_save_setup_value when values are persisted.

    Args:
        workspace_path: Path to workspace (usually .claude/)
        field: Field name (e.g. "user_name", "timezone")
        value: Value to write
    """
    field_to_file: dict[str, tuple[str, str, str]] = {
        "user_name": ("USER.md", "- **Name:**", f"- **Name:** {value}"),
        "timezone": ("USER.md", "- **Timezone:**", f"- **Timezone:** {value}"),
    }

    if field not in field_to_file:
        return

    filename, old_pattern, new_line = field_to_file[field]
    filepath = workspace_path / filename

    if not filepath.exists():
        return

    try:
        content = filepath.read_text()
        # Replace the line that starts with old_pattern
        lines = content.splitlines()
        new_lines = []
        for line in lines:
            if line.strip().startswith(old_pattern.strip()):
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        filepath.write_text("\n".join(new_lines) + "\n")
    except Exception:
        pass


# =============================================================================
# Timezone Detection
# =============================================================================


def detect_timezone() -> str:
    """
    Attempt to detect the user's timezone.

    Returns:
        Timezone string (e.g., "America/New_York") or "UTC"
    """
    try:
        # Try to get from system
        import time

        if hasattr(time, "tzname") and time.tzname[0]:
            # This gives abbreviation like "EST", not full name
            # Try to map common ones
            tz_map = {
                "EST": "America/New_York",
                "EDT": "America/New_York",
                "CST": "America/Chicago",
                "CDT": "America/Chicago",
                "MST": "America/Denver",
                "MDT": "America/Denver",
                "PST": "America/Los_Angeles",
                "PDT": "America/Los_Angeles",
                "GMT": "Europe/London",
                "BST": "Europe/London",
                "CET": "Europe/Paris",
                "CEST": "Europe/Paris",
                "JST": "Asia/Tokyo",
                "AEST": "Australia/Sydney",
                "AEDT": "Australia/Sydney",
            }
            abbrev = time.tzname[0]
            if abbrev in tz_map:
                return tz_map[abbrev]
    except Exception:
        pass

    try:
        # Try /etc/timezone (Linux)
        tz_file = Path("/etc/timezone")
        if tz_file.exists():
            return tz_file.read_text().strip()
    except Exception:
        pass

    try:
        # Try timedatectl (systemd)
        import subprocess

        result = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    return "UTC"


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="DexAI Setup Wizard")
    parser.add_argument("--status", action="store_true", help="Show setup status")
    parser.add_argument("--reset", action="store_true", help="Reset setup state")
    parser.add_argument("--complete", action="store_true", help="Mark setup as complete")
    parser.add_argument("--detect-tz", action="store_true", help="Detect timezone")

    args = parser.parse_args()

    if args.status:
        status = get_setup_status()
        print(json.dumps(status, indent=2))

    elif args.reset:
        result = reset_setup()
        print("Setup state reset." if result["success"] else f"Error: {result}")
        if result.get("removed"):
            print(f"Removed: {', '.join(result['removed'])}")

    elif args.complete:
        state = SetupState.load()
        result = apply_configuration(state)
        if result["success"]:
            print("Setup completed successfully!")
            print(f"Created files: {', '.join(result['created_files'])}")
        else:
            print(f"Errors: {result['errors']}")

    elif args.detect_tz:
        tz = detect_timezone()
        print(f"Detected timezone: {tz}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
