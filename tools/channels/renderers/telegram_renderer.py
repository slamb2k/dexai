"""
Telegram Renderer (Phase 15c)

Converts ContentBlocks into Telegram HTML format with media group support.
Handles message splitting at the 4096 character limit, code block formatting,
inline keyboards for buttons, and native polls.

Usage:
    from tools.channels.renderers.telegram_renderer import TelegramRenderer

    renderer = TelegramRenderer()
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
    MediaContent,
    Poll,
    RenderedMessage,
    RenderContext,
)
from tools.channels.renderers import ChannelRenderer

logger = logging.getLogger(__name__)

# Telegram message character limit
TELEGRAM_MESSAGE_LIMIT = 4096

# Flush threshold: leave room for trailing markup/whitespace
TELEGRAM_FLUSH_THRESHOLD = 4000

# Maximum images in a single Telegram media group
TELEGRAM_MEDIA_GROUP_MAX = 10


class TelegramRenderer(ChannelRenderer):
    """
    Render ContentBlocks to Telegram HTML format.

    Produces RenderedMessage objects with parse_mode=HTML metadata.
    Handles text formatting, code blocks, image media groups,
    blockquotes, lists, dividers, inline keyboards, and native polls.
    """

    def __init__(self) -> None:
        self._markdown = MarkdownConverter()
        self._splitter = ContentSplitter()

    # ------------------------------------------------------------------
    # ChannelRenderer interface
    # ------------------------------------------------------------------

    @property
    def channel_name(self) -> str:
        """Return the channel name this renderer handles."""
        return "telegram"

    def escape_text(self, text: str) -> str:
        """Escape HTML special characters for Telegram HTML parse mode."""
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        return text

    async def render_blocks(
        self,
        blocks: list[ContentBlock],
        context: RenderContext,
    ) -> list[RenderedMessage]:
        """
        Render content blocks to Telegram HTML messages.

        Converts each block type to appropriate HTML, accumulates text
        until the flush threshold (~4000 chars), then emits a new
        RenderedMessage.  IMAGE blocks are collected into media groups
        (max 10 per group).

        Args:
            blocks: Parsed content blocks from AI response.
            context: Rendering context (channel, user, thread info).

        Returns:
            List of RenderedMessage objects ready for the Telegram adapter.
        """
        messages: list[RenderedMessage] = []
        accumulated_html: list[str] = []
        accumulated_len = 0
        pending_images: list[str] = []

        def _flush_text() -> None:
            """Flush accumulated text into a RenderedMessage."""
            nonlocal accumulated_html, accumulated_len
            if not accumulated_html:
                return
            content = "\n".join(accumulated_html).strip()
            if content:
                messages.append(RenderedMessage(
                    channel="telegram",
                    content=content,
                    metadata={"parse_mode": "HTML"},
                ))
            accumulated_html = []
            accumulated_len = 0

        def _flush_images() -> None:
            """Flush pending images into media group messages."""
            nonlocal pending_images
            if not pending_images:
                return
            # Split into groups of TELEGRAM_MEDIA_GROUP_MAX
            for i in range(0, len(pending_images), TELEGRAM_MEDIA_GROUP_MAX):
                group = pending_images[i : i + TELEGRAM_MEDIA_GROUP_MAX]
                messages.append(self._create_media_group_message(group))
            pending_images = []

        for block in blocks:
            # ----- TEXT -----
            if block.type == BlockType.TEXT:
                html = self._markdown.to_telegram(block.content)
                segment_len = len(html)
                if accumulated_len + segment_len > TELEGRAM_FLUSH_THRESHOLD:
                    _flush_text()
                accumulated_html.append(html)
                accumulated_len += segment_len

            # ----- CODE -----
            elif block.type == BlockType.CODE:
                lang = block.metadata.get("language", "")
                escaped_code = self.escape_text(block.content)
                if lang:
                    html = (
                        f'<pre><code class="language-{lang}">'
                        f"{escaped_code}</code></pre>"
                    )
                else:
                    html = f"<pre><code>{escaped_code}</code></pre>"
                segment_len = len(html)
                if accumulated_len + segment_len > TELEGRAM_FLUSH_THRESHOLD:
                    _flush_text()
                accumulated_html.append(html)
                accumulated_len += segment_len

            # ----- IMAGE -----
            elif block.type == BlockType.IMAGE:
                # Flush any accumulated text first so ordering is preserved
                _flush_text()
                url_or_path = block.content or block.metadata.get("url", "")
                if url_or_path:
                    pending_images.append(url_or_path)
                # If we've hit the media group limit, flush immediately
                if len(pending_images) >= TELEGRAM_MEDIA_GROUP_MAX:
                    _flush_images()

            # ----- QUOTE -----
            elif block.type == BlockType.QUOTE:
                escaped = self.escape_text(block.content)
                # Use vertical bar prefix for blockquote appearance
                lines = escaped.split("\n")
                quoted = "\n".join(f"\u258e {line}" for line in lines)
                segment_len = len(quoted)
                if accumulated_len + segment_len > TELEGRAM_FLUSH_THRESHOLD:
                    _flush_text()
                accumulated_html.append(quoted)
                accumulated_len += segment_len

            # ----- LIST -----
            elif block.type == BlockType.LIST:
                items = block.content.split("\n")
                formatted_items: list[str] = []
                for item in items:
                    stripped = item.strip()
                    if not stripped:
                        continue
                    # Remove existing bullet/dash prefix if present
                    if stripped.startswith(("- ", "* ", "• ")):
                        stripped = stripped[2:]
                    formatted_items.append(f"\u2022 {self.escape_text(stripped)}")
                list_html = "\n".join(formatted_items)
                segment_len = len(list_html)
                if accumulated_len + segment_len > TELEGRAM_FLUSH_THRESHOLD:
                    _flush_text()
                accumulated_html.append(list_html)
                accumulated_len += segment_len

            # ----- DIVIDER -----
            elif block.type == BlockType.DIVIDER:
                divider = "\u2014" * 3  # em-dash line
                segment_len = len(divider)
                if accumulated_len + segment_len > TELEGRAM_FLUSH_THRESHOLD:
                    _flush_text()
                accumulated_html.append(divider)
                accumulated_len += segment_len

            # ----- AUDIO / VIDEO / FILE (pass through as text note) -----
            else:
                note = self.escape_text(block.content or f"[{block.type.value}]")
                if accumulated_len + len(note) > TELEGRAM_FLUSH_THRESHOLD:
                    _flush_text()
                accumulated_html.append(note)
                accumulated_len += len(note)

        # Final flush
        _flush_text()
        _flush_images()

        # Guarantee at least one message
        if not messages:
            messages.append(RenderedMessage(
                channel="telegram",
                content="",
                metadata={"parse_mode": "HTML"},
            ))

        return messages

    async def render_buttons(
        self,
        button_group: ButtonGroup,
        context: RenderContext,
    ) -> RenderedMessage | None:
        """
        Render a ButtonGroup as a Telegram inline keyboard.

        Returns a RenderedMessage whose metadata contains an
        ``inline_keyboard`` list suitable for the Telegram Bot API
        ``reply_markup`` parameter.

        Args:
            button_group: Group of buttons to render.
            context: Rendering context.

        Returns:
            RenderedMessage with inline_keyboard metadata, or None if empty.
        """
        if not button_group.buttons:
            return None

        keyboard_row: list[dict[str, str]] = []
        for button in button_group.buttons:
            if button.url:
                keyboard_row.append({
                    "text": button.label,
                    "url": button.url,
                })
            else:
                keyboard_row.append({
                    "text": button.label,
                    "callback_data": button.action or button.id,
                })

        return RenderedMessage(
            channel="telegram",
            content="",
            metadata={
                "parse_mode": "HTML",
                "inline_keyboard": [keyboard_row],
            },
        )

    async def render_poll(
        self,
        poll: Poll,
        context: RenderContext,
    ) -> RenderedMessage | None:
        """
        Render a Poll as a Telegram native poll.

        Returns a RenderedMessage whose metadata contains the fields
        required by the Telegram ``sendPoll`` API method.

        Args:
            poll: Poll definition.
            context: Rendering context.

        Returns:
            RenderedMessage with poll metadata, or None if invalid.
        """
        if not poll.options:
            return None

        return RenderedMessage(
            channel="telegram",
            content="",
            metadata={
                "poll": {
                    "question": poll.question,
                    "options": [opt.text for opt in poll.options],
                    "is_anonymous": poll.anonymous,
                    "allows_multiple_answers": poll.multiple_choice,
                },
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_media_group_message(
        self,
        image_urls: list[str],
    ) -> RenderedMessage:
        """
        Create a RenderedMessage representing a Telegram media group.

        Args:
            image_urls: List of image URLs or local file paths.

        Returns:
            RenderedMessage with ``media_group`` and ``parse_mode`` in metadata.
        """
        return RenderedMessage(
            channel="telegram",
            content="",
            attachments=list(image_urls),
            metadata={
                "media_group": list(image_urls),
                "parse_mode": "HTML",
            },
        )
