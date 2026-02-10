"""
Discord Channel Renderer (Phase 15c)

Converts ContentBlocks into Discord-native message format with rich embed
support, message components (buttons), and reaction-based polls.

Discord limits:
- 2000 chars per message
- 10 embeds per message
- Components use action rows (type 1) containing buttons (type 2)

Usage:
    from tools.channels.renderers.discord_renderer import DiscordRenderer

    renderer = DiscordRenderer()
    messages = await renderer.render_blocks(blocks, context)
"""

from __future__ import annotations

import logging
from typing import Any

from tools.channels.content.markdown import MarkdownConverter
from tools.channels.content.splitter import ContentSplitter
from tools.channels.models import (
    BlockType,
    Button,
    ButtonGroup,
    ButtonStyle,
    ContentBlock,
    Poll,
    RenderedMessage,
    RenderContext,
)
from tools.channels.renderers import ChannelRenderer

logger = logging.getLogger(__name__)

# Discord blurple default embed color
DEFAULT_EMBED_COLOR = 0x5865F2

# Discord limits
MESSAGE_CHAR_LIMIT = 2000
FLUSH_THRESHOLD = 1900
MAX_EMBEDS_PER_MESSAGE = 10

# Button style mapping: ButtonStyle -> Discord button style int
BUTTON_STYLE_MAP = {
    ButtonStyle.DEFAULT: 2,   # Secondary (grey)
    ButtonStyle.PRIMARY: 1,   # Primary (blurple)
    ButtonStyle.DANGER: 4,    # Danger (red)
}
URL_BUTTON_STYLE = 5  # Link style


class DiscordRenderer(ChannelRenderer):
    """
    Render ContentBlocks into Discord-native message format.

    Supports:
    - Standard Discord markdown (bold, italic, code, etc.)
    - Rich embeds for images and structured content
    - Message components (buttons) via action rows
    - Reaction-based polls (Discord lacks native poll API)
    """

    def __init__(self) -> None:
        self._markdown = MarkdownConverter()
        self._splitter = ContentSplitter()

    @property
    def channel_name(self) -> str:
        """Return the channel name this renderer handles."""
        return "discord"

    async def render_blocks(
        self,
        blocks: list[ContentBlock],
        context: RenderContext,
    ) -> list[RenderedMessage]:
        """
        Render content blocks to Discord message format.

        Converts each block to Discord-flavored markdown or embeds,
        respecting the 2000-char message limit and 10-embed limit.

        Args:
            blocks: Parsed content blocks from AI response
            context: Rendering context with platform config

        Returns:
            List of RenderedMessage objects ready for Discord API
        """
        embed_color = self._get_embed_color(context)
        messages: list[RenderedMessage] = []
        current_text = ""
        current_embeds: list[dict[str, Any]] = []

        for block in blocks:
            if block.type == BlockType.TEXT:
                rendered = self._render_text(block)
                current_text, current_embeds, messages = self._accumulate(
                    current_text, rendered, current_embeds, messages,
                )

            elif block.type == BlockType.CODE:
                rendered = self._render_code(block)
                current_text, current_embeds, messages = self._accumulate(
                    current_text, rendered, current_embeds, messages,
                )

            elif block.type == BlockType.IMAGE:
                url = block.metadata.get("url", block.content)
                embed = {"image": {"url": url}, "color": embed_color}
                title = block.metadata.get("title")
                if title:
                    embed["title"] = title
                current_text, current_embeds, messages = self._accumulate_embed(
                    current_text, current_embeds, embed, messages,
                )

            elif block.type == BlockType.QUOTE:
                rendered = self._render_quote(block)
                current_text, current_embeds, messages = self._accumulate(
                    current_text, rendered, current_embeds, messages,
                )

            elif block.type == BlockType.LIST:
                rendered = self._render_list(block)
                current_text, current_embeds, messages = self._accumulate(
                    current_text, rendered, current_embeds, messages,
                )

            elif block.type == BlockType.DIVIDER:
                rendered = "---\n"
                current_text, current_embeds, messages = self._accumulate(
                    current_text, rendered, current_embeds, messages,
                )

            else:
                # Fallback: treat as text
                rendered = self._markdown.to_discord(block.content)
                current_text, current_embeds, messages = self._accumulate(
                    current_text, rendered, current_embeds, messages,
                )

        # Flush remaining content
        if current_text.strip() or current_embeds:
            messages.append(self._build_message(current_text, current_embeds))

        # Ensure at least one message
        if not messages:
            messages.append(RenderedMessage(channel="discord", content=""))

        return messages

    async def render_buttons(
        self,
        button_group: ButtonGroup,
        context: RenderContext,
    ) -> RenderedMessage | None:
        """
        Render interactive buttons as Discord message components.

        Discord buttons use action rows (type 1) containing button
        components (type 2). URL buttons use style 5 with a url field;
        callback buttons use custom_id for interaction handling.

        Args:
            button_group: Group of buttons to render
            context: Rendering context

        Returns:
            RenderedMessage with components metadata
        """
        if not button_group.buttons:
            return None

        discord_buttons: list[dict[str, Any]] = []

        for button in button_group.buttons:
            discord_btn = self._render_button(button)
            discord_buttons.append(discord_btn)

        components = [
            {
                "type": 1,  # Action Row
                "components": discord_buttons,
            }
        ]

        return RenderedMessage(
            channel="discord",
            content="",
            metadata={"components": components},
        )

    async def render_poll(
        self,
        poll: Poll,
        context: RenderContext,
    ) -> RenderedMessage | None:
        """
        Render a poll using embeds with numbered options.

        Discord does not have a native poll API, so polls are rendered
        as rich embeds with numbered options. Users react with number
        emoji to vote.

        Args:
            poll: Poll definition
            context: Rendering context

        Returns:
            RenderedMessage with poll embed in metadata
        """
        if not poll.options:
            return None

        embed_color = self._get_embed_color(context)
        number_emojis = [
            "\u0031\uFE0F\u20E3",  # 1
            "\u0032\uFE0F\u20E3",  # 2
            "\u0033\uFE0F\u20E3",  # 3
            "\u0034\uFE0F\u20E3",  # 4
            "\u0035\uFE0F\u20E3",  # 5
            "\u0036\uFE0F\u20E3",  # 6
            "\u0037\uFE0F\u20E3",  # 7
            "\u0038\uFE0F\u20E3",  # 8
            "\u0039\uFE0F\u20E3",  # 9
            "\U0001F51F",          # 10
        ]

        description_lines: list[str] = []
        reaction_emojis: list[str] = []

        for i, option in enumerate(poll.options):
            if i >= len(number_emojis):
                break
            emoji = number_emojis[i]
            description_lines.append(f"{emoji} {option.text}")
            reaction_emojis.append(emoji)

        description = "\n".join(description_lines)

        if poll.multiple_choice:
            description += "\n\n*You may select multiple options.*"

        embed = {
            "title": poll.question,
            "description": description,
            "color": embed_color,
            "footer": {"text": "React with the corresponding number to vote."},
        }

        return RenderedMessage(
            channel="discord",
            content="",
            metadata={
                "embeds": [embed],
                "poll_id": poll.id,
                "reaction_emojis": reaction_emojis,
            },
        )

    # =========================================================================
    # Block rendering helpers
    # =========================================================================

    def _render_text(self, block: ContentBlock) -> str:
        """Render a TEXT block to Discord markdown."""
        text = self._markdown.to_discord(block.content)
        if not text.endswith("\n"):
            text += "\n"
        return text

    def _render_code(self, block: ContentBlock) -> str:
        """Render a CODE block with triple backtick fences."""
        lang = block.metadata.get("language", "")
        code = block.content
        return f"```{lang}\n{code}\n```\n"

    def _render_quote(self, block: ContentBlock) -> str:
        """Render a QUOTE block with > prefix on each line."""
        lines = block.content.split("\n")
        quoted = "\n".join(f"> {line}" for line in lines)
        return quoted + "\n"

    def _render_list(self, block: ContentBlock) -> str:
        """Render a LIST block with - bullet points."""
        items = block.content.split("\n")
        rendered_items: list[str] = []
        for item in items:
            stripped = item.strip()
            if not stripped:
                continue
            # Remove existing bullet markers if present
            if stripped.startswith(("- ", "* ", "• ")):
                stripped = stripped[2:]
            rendered_items.append(f"- {stripped}")
        return "\n".join(rendered_items) + "\n"

    def _render_button(self, button: Button) -> dict[str, Any]:
        """Convert a Button model to a Discord button component dict."""
        if button.url:
            return {
                "type": 2,
                "style": URL_BUTTON_STYLE,
                "label": button.label,
                "url": button.url,
                "disabled": button.disabled,
            }

        style = BUTTON_STYLE_MAP.get(button.style, 2)
        discord_btn: dict[str, Any] = {
            "type": 2,
            "style": style,
            "label": button.label,
            "custom_id": button.action or button.id,
            "disabled": button.disabled,
        }
        return discord_btn

    # =========================================================================
    # Message accumulation helpers
    # =========================================================================

    def _accumulate(
        self,
        current_text: str,
        new_text: str,
        current_embeds: list[dict[str, Any]],
        messages: list[RenderedMessage],
    ) -> tuple[str, list[dict[str, Any]], list[RenderedMessage]]:
        """
        Accumulate text into the current message buffer.

        When the buffer approaches FLUSH_THRESHOLD (1900 chars),
        flush to a new RenderedMessage and start fresh.
        """
        if len(current_text) + len(new_text) > FLUSH_THRESHOLD and current_text.strip():
            messages.append(self._build_message(current_text, current_embeds))
            return new_text, [], messages

        current_text += new_text
        return current_text, current_embeds, messages

    def _accumulate_embed(
        self,
        current_text: str,
        current_embeds: list[dict[str, Any]],
        embed: dict[str, Any],
        messages: list[RenderedMessage],
    ) -> tuple[str, list[dict[str, Any]], list[RenderedMessage]]:
        """
        Accumulate an embed into the current message buffer.

        Flushes when reaching MAX_EMBEDS_PER_MESSAGE (10 embeds).
        """
        if len(current_embeds) >= MAX_EMBEDS_PER_MESSAGE:
            messages.append(self._build_message(current_text, current_embeds))
            return "", [embed], messages

        current_embeds.append(embed)
        return current_text, current_embeds, messages

    def _build_message(
        self,
        text: str,
        embeds: list[dict[str, Any]],
    ) -> RenderedMessage:
        """Build a RenderedMessage from accumulated text and embeds."""
        metadata: dict[str, Any] = {}
        if embeds:
            metadata["embeds"] = embeds

        # Truncate text to message limit as a safety net
        content = text.strip()
        if len(content) > MESSAGE_CHAR_LIMIT:
            content = content[: MESSAGE_CHAR_LIMIT - 3] + "..."
            logger.warning(
                "Discord message truncated to %d chars", MESSAGE_CHAR_LIMIT,
            )

        return RenderedMessage(
            channel="discord",
            content=content,
            metadata=metadata,
        )

    def _get_embed_color(self, context: RenderContext) -> int:
        """Get embed color from context config or use default blurple."""
        color = context.platform_config.get("embed_color")
        if color is not None:
            if isinstance(color, int):
                return color
            if isinstance(color, str):
                try:
                    return int(color, 0)
                except (ValueError, TypeError):
                    logger.warning("Invalid embed_color %r, using default", color)
        return DEFAULT_EMBED_COLOR
