"""
Platform-Specific Renderers (Phase 15c)

Provides ChannelRenderer abstraction and registry for platform-native
rendering of content blocks to Telegram, Discord, and Slack formats.

Usage:
    from tools.channels.renderers import get_renderer, RenderContext

    renderer = get_renderer("telegram")
    messages = await renderer.render_blocks(blocks, context)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from tools.channels.models import (
    BlockType,
    Button,
    ButtonGroup,
    ContentBlock,
    MediaContent,
    Poll,
    RenderedMessage,
    RenderContext,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ChannelRenderer(ABC):
    """
    Base class for channel-specific rendering.

    Each platform implements this to convert ContentBlocks into
    platform-native message formats (HTML, embeds, Block Kit, etc.).
    """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Return the channel name this renderer handles."""
        ...

    @abstractmethod
    async def render_blocks(
        self,
        blocks: list[ContentBlock],
        context: RenderContext,
    ) -> list[RenderedMessage]:
        """
        Render content blocks to platform-native format.

        Args:
            blocks: Parsed content blocks from AI response
            context: Rendering context (channel, user, thread info)

        Returns:
            List of platform-ready messages to send
        """
        ...

    async def render_buttons(
        self,
        button_group: ButtonGroup,
        context: RenderContext,
    ) -> RenderedMessage | None:
        """
        Render interactive buttons for the platform.

        Default implementation returns None (unsupported).
        Override in platform renderers that support buttons.
        """
        return None

    async def render_poll(
        self,
        poll: Poll,
        context: RenderContext,
    ) -> RenderedMessage | None:
        """
        Render a poll for the platform.

        Default implementation returns None (unsupported).
        Override in platform renderers that support polls.
        """
        return None

    def escape_text(self, text: str) -> str:
        """
        Escape text for this platform's formatting.

        Default implementation returns text unchanged.
        Override for platforms needing escaping (e.g., Telegram MarkdownV2).
        """
        return text

    def get_message_limit(self) -> int:
        """Get the character limit for messages on this platform."""
        limits = {
            "telegram": 4096,
            "discord": 2000,
            "slack": 40000,
        }
        return limits.get(self.channel_name, 2000)


# =============================================================================
# Renderer Registry
# =============================================================================

_renderers: dict[str, ChannelRenderer] = {}


def register_renderer(renderer: ChannelRenderer) -> None:
    """
    Register a channel renderer.

    Args:
        renderer: ChannelRenderer instance to register
    """
    _renderers[renderer.channel_name] = renderer
    logger.debug(f"Registered renderer: {renderer.channel_name}")


def get_renderer(channel: str) -> ChannelRenderer | None:
    """
    Get renderer for a channel.

    Args:
        channel: Channel name (telegram, discord, slack)

    Returns:
        ChannelRenderer instance or None if not registered
    """
    return _renderers.get(channel)


def list_renderers() -> list[str]:
    """List all registered renderer channel names."""
    return list(_renderers.keys())


def _auto_register() -> None:
    """Auto-register all platform renderers."""
    try:
        from tools.channels.renderers.telegram_renderer import TelegramRenderer
        register_renderer(TelegramRenderer())
    except ImportError:
        logger.debug("Telegram renderer not available")

    try:
        from tools.channels.renderers.discord_renderer import DiscordRenderer
        register_renderer(DiscordRenderer())
    except ImportError:
        logger.debug("Discord renderer not available")

    try:
        from tools.channels.renderers.slack_renderer import SlackRenderer
        register_renderer(SlackRenderer())
    except ImportError:
        logger.debug("Slack renderer not available")


# Auto-register on import
_auto_register()

# Re-export key types
__all__ = [
    "ChannelRenderer",
    "RenderContext",
    "RenderedMessage",
    "register_renderer",
    "get_renderer",
    "list_renderers",
]
