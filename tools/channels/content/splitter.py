"""
Content Splitter (Phase 15c)

Splits content blocks into message-sized chunks for channel limits.
Preserves code block integrity and splits at natural boundaries.

Usage:
    from tools.channels.content.splitter import ContentSplitter

    splitter = ContentSplitter()
    chunks = splitter.split_blocks(blocks, channel="telegram")
"""

from __future__ import annotations

import logging
import re
from typing import Any

from tools.channels.models import BlockType, ContentBlock

logger = logging.getLogger(__name__)

# Channel message character limits
CHANNEL_LIMITS = {
    "telegram": 4096,
    "discord": 2000,
    "slack": 4000,  # Practical limit (API allows 40000)
    "cli": 100000,
    "api": 100000,
}

DEFAULT_LIMIT = 2000


class ContentSplitter:
    """
    Split content blocks into message-sized chunks.

    Respects channel limits and avoids breaking code blocks,
    splitting at natural boundaries (paragraphs, sentences, words).
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def get_limit(self, channel: str) -> int:
        """Get character limit for a channel."""
        custom_limits = self.config.get("channel_limits", {})
        return custom_limits.get(channel) or CHANNEL_LIMITS.get(channel, DEFAULT_LIMIT)

    def split_blocks(
        self,
        blocks: list[ContentBlock],
        channel: str,
    ) -> list[list[ContentBlock]]:
        """
        Split blocks into message-sized groups.

        Each group represents one message to send. Attempts to keep
        related content together while respecting size limits.

        Args:
            blocks: Content blocks to split
            channel: Target channel name

        Returns:
            List of block groups (each group is one message)
        """
        limit = self.get_limit(channel)
        groups: list[list[ContentBlock]] = []
        current_group: list[ContentBlock] = []
        current_size = 0

        for block in blocks:
            block_size = self._estimate_block_size(block, channel)

            # If single block exceeds limit, split the block itself
            if block_size > limit:
                # Flush current group first
                if current_group:
                    groups.append(current_group)
                    current_group = []
                    current_size = 0

                # Split oversized block
                split_blocks = self._split_block(block, limit, channel)
                for sb in split_blocks:
                    groups.append([sb])
                continue

            # If adding this block would exceed limit, start new group
            if current_size + block_size > limit and current_group:
                groups.append(current_group)
                current_group = []
                current_size = 0

            current_group.append(block)
            current_size += block_size

        # Flush remaining
        if current_group:
            groups.append(current_group)

        return groups if groups else [[ContentBlock(type=BlockType.TEXT, content="")]]

    def split_text(self, text: str, channel: str) -> list[str]:
        """
        Split plain text for channel limits.

        Args:
            text: Text to split
            channel: Target channel

        Returns:
            List of text chunks
        """
        limit = self.get_limit(channel)

        if len(text) <= limit:
            return [text]

        chunks = []
        remaining = text

        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break

            split_point = self._find_split_point(remaining, limit)
            chunks.append(remaining[:split_point].rstrip())
            remaining = remaining[split_point:].lstrip()

        return chunks

    def _estimate_block_size(self, block: ContentBlock, channel: str) -> int:
        """Estimate rendered size of a block for a channel."""
        content_len = len(block.content)

        if block.type == BlockType.CODE:
            lang = block.metadata.get("language", "")
            if channel == "telegram":
                # <pre><code class="language-x">...</code></pre>
                overhead = len(f'<pre><code class="language-{lang}"></code></pre>') + 2
            elif channel == "discord":
                # ```lang\n...\n```
                overhead = len(f"```{lang}\n\n```") + 2
            elif channel == "slack":
                # ```...```
                overhead = 8
            else:
                overhead = len(f"```{lang}\n\n```") + 2
            return content_len + overhead

        if block.type == BlockType.QUOTE:
            # Each line gets "> " prefix
            lines = block.content.count("\n") + 1
            return content_len + lines * 2

        if block.type == BlockType.DIVIDER:
            return 4  # "---\n"

        return content_len + 2  # +2 for trailing newline

    def _split_block(
        self,
        block: ContentBlock,
        limit: int,
        channel: str,
    ) -> list[ContentBlock]:
        """Split an oversized block into smaller blocks."""
        if block.type == BlockType.CODE:
            return self._split_code_block(block, limit, channel)
        else:
            return self._split_text_block(block, limit)

    def _split_code_block(
        self,
        block: ContentBlock,
        limit: int,
        channel: str,
    ) -> list[ContentBlock]:
        """Split a code block into multiple code blocks."""
        lang = block.metadata.get("language", "")
        overhead = self._estimate_block_size(
            ContentBlock(type=BlockType.CODE, content="", metadata=block.metadata), channel
        )
        available = limit - overhead - 20  # Safety margin

        if available <= 0:
            available = limit // 2

        lines = block.content.split("\n")
        chunks: list[ContentBlock] = []
        current_lines: list[str] = []
        current_size = 0

        for line in lines:
            line_size = len(line) + 1  # +1 for newline

            if current_size + line_size > available and current_lines:
                chunks.append(ContentBlock(
                    type=BlockType.CODE,
                    content="\n".join(current_lines),
                    metadata={"language": lang, "continued": True},
                ))
                current_lines = []
                current_size = 0

            current_lines.append(line)
            current_size += line_size

        if current_lines:
            chunks.append(ContentBlock(
                type=BlockType.CODE,
                content="\n".join(current_lines),
                metadata={"language": lang},
            ))

        return chunks

    def _split_text_block(
        self,
        block: ContentBlock,
        limit: int,
    ) -> list[ContentBlock]:
        """Split a text block at natural boundaries."""
        chunks = self.split_text(block.content, "default")
        return [
            ContentBlock(type=block.type, content=chunk, metadata=block.metadata)
            for chunk in chunks
            if chunk.strip()
        ]

    def _find_split_point(self, text: str, limit: int) -> int:
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
