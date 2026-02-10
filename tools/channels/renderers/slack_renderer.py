"""
Slack Block Kit Renderer (Phase 15c)

Converts ContentBlocks into Slack Block Kit format for native rendering
in Slack channels. Supports sections, images, dividers, actions (buttons),
and polls using Slack's block structure.

Usage:
    from tools.channels.renderers.slack_renderer import SlackRenderer
    from tools.channels.renderers import register_renderer

    renderer = SlackRenderer()
    messages = await renderer.render_blocks(blocks, context)
"""

from __future__ import annotations

import logging
from typing import Any

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
from tools.channels.content.markdown import MarkdownConverter
from tools.channels.content.splitter import ContentSplitter

logger = logging.getLogger(__name__)

# Slack Block Kit limits
MAX_BLOCKS_PER_MESSAGE = 50
MAX_MRKDWN_LENGTH = 3000


class SlackRenderer(ChannelRenderer):
    """
    Render content blocks to Slack Block Kit format.

    Converts ContentBlocks into Slack-native block structures including
    sections (mrkdwn), images, dividers, and actions. Handles message
    splitting when block count or text length exceeds Slack limits.
    """

    def __init__(self) -> None:
        self._converter = MarkdownConverter()
        self._splitter = ContentSplitter()

    @property
    def channel_name(self) -> str:
        """Return the channel name this renderer handles."""
        return "slack"

    async def render_blocks(
        self,
        blocks: list[ContentBlock],
        context: RenderContext,
    ) -> list[RenderedMessage]:
        """
        Render content blocks to Slack Block Kit messages.

        Converts each ContentBlock into the appropriate Slack block type
        and groups them into messages respecting the 50-block limit.
        Long mrkdwn sections are split at the 3000-character boundary.

        Args:
            blocks: Parsed content blocks from AI response
            context: Rendering context (channel, user, thread info)

        Returns:
            List of RenderedMessage with Block Kit content dicts
        """
        slack_blocks: list[dict[str, Any]] = []
        fallback_parts: list[str] = []

        for block in blocks:
            rendered, fallback = self._render_block(block)
            slack_blocks.extend(rendered)
            if fallback:
                fallback_parts.append(fallback)

        fallback_text = "\n".join(fallback_parts) if fallback_parts else ""

        # Split into messages if we exceed the block limit
        messages: list[RenderedMessage] = []
        for i in range(0, len(slack_blocks), MAX_BLOCKS_PER_MESSAGE):
            chunk = slack_blocks[i : i + MAX_BLOCKS_PER_MESSAGE]
            messages.append(
                RenderedMessage(
                    channel="slack",
                    content={"blocks": chunk},
                    metadata={"text": fallback_text},
                )
            )

        if not messages:
            messages.append(
                RenderedMessage(
                    channel="slack",
                    content={"blocks": []},
                    metadata={"text": ""},
                )
            )

        return messages

    async def render_buttons(
        self,
        button_group: ButtonGroup,
        context: RenderContext,
    ) -> RenderedMessage | None:
        """
        Render interactive buttons as Slack Block Kit actions.

        Converts a ButtonGroup into a Slack actions block with button
        elements. Supports primary/danger styles and URL buttons.

        Args:
            button_group: Group of buttons to render
            context: Rendering context

        Returns:
            RenderedMessage with Block Kit actions content
        """
        elements: list[dict[str, Any]] = []

        for button in button_group.buttons:
            element = self._render_button_element(button)
            elements.append(element)

        action_block: dict[str, Any] = {
            "type": "actions",
            "elements": elements,
        }

        labels = [b.label for b in button_group.buttons]
        fallback_text = "Actions: " + ", ".join(labels)

        return RenderedMessage(
            channel="slack",
            content={"blocks": [action_block]},
            metadata={"text": fallback_text},
        )

    async def render_poll(
        self,
        poll: Poll,
        context: RenderContext,
    ) -> RenderedMessage | None:
        """
        Render a poll as Slack Block Kit with action buttons.

        Creates a header section with the poll question followed by
        an actions block with one button per poll option.

        Args:
            poll: Poll definition with question and options
            context: Rendering context

        Returns:
            RenderedMessage with Block Kit poll content
        """
        # Header section with the question
        header_block: dict[str, Any] = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{poll.question}*",
            },
        }

        # Option buttons
        option_elements: list[dict[str, Any]] = []
        for option in poll.options:
            option_elements.append({
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": option.text,
                },
                "action_id": f"poll_{poll.id}_option_{option.id}",
            })

        actions_block: dict[str, Any] = {
            "type": "actions",
            "elements": option_elements,
        }

        fallback_text = (
            f"Poll: {poll.question} — "
            + ", ".join(o.text for o in poll.options)
        )

        return RenderedMessage(
            channel="slack",
            content={"blocks": [header_block, actions_block]},
            metadata={"text": fallback_text},
        )

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _render_block(
        self, block: ContentBlock
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Render a single ContentBlock into Slack block(s).

        Returns:
            Tuple of (list of slack blocks, fallback text)
        """
        if block.type == BlockType.TEXT:
            return self._render_text_block(block)
        elif block.type == BlockType.CODE:
            return self._render_code_block(block)
        elif block.type == BlockType.IMAGE:
            return self._render_image_block(block)
        elif block.type == BlockType.QUOTE:
            return self._render_quote_block(block)
        elif block.type == BlockType.LIST:
            return self._render_list_block(block)
        elif block.type == BlockType.DIVIDER:
            return self._render_divider_block(block)
        else:
            # Fallback: render as plain text section
            logger.warning(
                "Unknown block type %s, rendering as text", block.type
            )
            return self._render_text_block(block)

    def _render_text_block(
        self, block: ContentBlock
    ) -> tuple[list[dict[str, Any]], str]:
        """Render a TEXT block as one or more mrkdwn sections."""
        converted = self._converter.to_slack(block.content)
        sections = self._split_mrkdwn(converted)

        slack_blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": section},
            }
            for section in sections
        ]

        return slack_blocks, block.content

    def _render_code_block(
        self, block: ContentBlock
    ) -> tuple[list[dict[str, Any]], str]:
        """Render a CODE block wrapped in triple backticks."""
        code_text = f"```{block.content}```"
        sections = self._split_mrkdwn(code_text)

        slack_blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": section},
            }
            for section in sections
        ]

        return slack_blocks, block.content

    def _render_image_block(
        self, block: ContentBlock
    ) -> tuple[list[dict[str, Any]], str]:
        """Render an IMAGE block as a Slack image block."""
        url = block.content
        alt_text = block.metadata.get("alt", "Image")

        image_block: dict[str, Any] = {
            "type": "image",
            "image_url": url,
            "alt_text": alt_text,
        }

        return [image_block], f"[Image: {alt_text}]"

    def _render_quote_block(
        self, block: ContentBlock
    ) -> tuple[list[dict[str, Any]], str]:
        """Render a QUOTE block with > prefixed lines in mrkdwn."""
        converted = self._converter.to_slack(block.content)
        # Prefix each line with >
        quoted_lines = [
            f">{line}" if line.strip() else ">"
            for line in converted.split("\n")
        ]
        quoted_text = "\n".join(quoted_lines)
        sections = self._split_mrkdwn(quoted_text)

        slack_blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": section},
            }
            for section in sections
        ]

        return slack_blocks, block.content

    def _render_list_block(
        self, block: ContentBlock
    ) -> tuple[list[dict[str, Any]], str]:
        """Render a LIST block with bullet points in mrkdwn."""
        converted = self._converter.to_slack(block.content)
        # Ensure each line starts with a bullet
        lines = converted.split("\n")
        bullet_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # If not already a bullet, add one
            if not stripped.startswith("•") and not stripped.startswith("-"):
                bullet_lines.append(f"• {stripped}")
            else:
                bullet_lines.append(stripped)

        list_text = "\n".join(bullet_lines)
        sections = self._split_mrkdwn(list_text)

        slack_blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": section},
            }
            for section in sections
        ]

        return slack_blocks, block.content

    def _render_divider_block(
        self, block: ContentBlock
    ) -> tuple[list[dict[str, Any]], str]:
        """Render a DIVIDER block."""
        return [{"type": "divider"}], "---"

    def _split_mrkdwn(self, text: str) -> list[str]:
        """
        Split mrkdwn text into chunks respecting the 3000-char limit.

        Uses ContentSplitter logic to find natural split points
        (paragraphs, sentences, words) within the mrkdwn limit.
        """
        if len(text) <= MAX_MRKDWN_LENGTH:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= MAX_MRKDWN_LENGTH:
                chunks.append(remaining)
                break

            split_point = self._find_split_point(remaining, MAX_MRKDWN_LENGTH)
            chunks.append(remaining[:split_point].rstrip())
            remaining = remaining[split_point:].lstrip()

        return chunks if chunks else [text]

    @staticmethod
    def _find_split_point(text: str, limit: int) -> int:
        """Find the best point to split text within the limit."""
        if len(text) <= limit:
            return len(text)

        # Try paragraph boundary
        paragraph_break = text[:limit].rfind("\n\n")
        if paragraph_break > limit // 3:
            return paragraph_break + 2

        # Try line boundary
        line_break = text[:limit].rfind("\n")
        if line_break > limit // 3:
            return line_break + 1

        # Try sentence boundary
        sentence_end = text[:limit].rfind(". ")
        if sentence_end > limit // 3:
            return sentence_end + 2

        # Try word boundary
        word_break = text[:limit].rfind(" ")
        if word_break > limit // 3:
            return word_break + 1

        # Hard split at limit
        return limit

    def _render_button_element(self, button: Button) -> dict[str, Any]:
        """Convert a Button model into a Slack button element."""
        element: dict[str, Any] = {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": button.label,
            },
        }

        # URL buttons use the url field
        if button.url:
            element["url"] = button.url
        else:
            # Action buttons use action_id
            element["action_id"] = button.action or button.id

        # Apply style (only primary and danger are valid Slack styles)
        if button.style == ButtonStyle.PRIMARY:
            element["style"] = "primary"
        elif button.style == ButtonStyle.DANGER:
            element["style"] = "danger"
        # DEFAULT style: omit the style key entirely

        return element
