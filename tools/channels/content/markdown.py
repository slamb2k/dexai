"""
Platform-Specific Markdown Converter (Phase 15c)

Converts standard markdown to platform-specific formatting:
- Telegram: HTML tags (parse_mode=HTML)
- Discord: Discord-flavored markdown
- Slack: Slack mrkdwn format

Usage:
    from tools.channels.content.markdown import MarkdownConverter

    converter = MarkdownConverter()
    html = converter.to_telegram("**bold** and _italic_")
    mrkdwn = converter.to_slack("**bold** and _italic_")
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)


class MarkdownConverter:
    """
    Convert standard markdown to platform-specific formats.

    Handles bold, italic, strikethrough, code, links, and lists.
    Each platform has unique escaping and formatting requirements.
    """

    # Telegram HTML special characters that need escaping
    TELEGRAM_HTML_ESCAPE = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
    }

    def to_telegram(self, text: str) -> str:
        """
        Convert markdown to Telegram HTML format.

        Uses parse_mode=HTML which supports:
        <b>, <i>, <u>, <s>, <code>, <pre>, <a href="">

        Args:
            text: Standard markdown text

        Returns:
            Telegram HTML formatted text
        """
        result = text

        # Escape HTML special chars first (but not in existing HTML tags)
        result = self._escape_html(result)

        # Bold: **text** or __text__ -> <b>text</b>
        result = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', result)
        result = re.sub(r'__(.+?)__', r'<b>\1</b>', result)

        # Italic: *text* or _text_ -> <i>text</i>
        result = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', result)
        result = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<i>\1</i>', result)

        # Strikethrough: ~~text~~ -> <s>text</s>
        result = re.sub(r'~~(.+?)~~', r'<s>\1</s>', result)

        # Inline code: `code` -> <code>code</code>
        result = re.sub(r'`([^`]+)`', r'<code>\1</code>', result)

        # Links: [text](url) -> <a href="url">text</a>
        result = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', result)

        # Headers: # text -> <b>text</b> (Telegram has no headers)
        result = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', result, flags=re.MULTILINE)

        # Bullet lists: - item -> • item
        result = re.sub(r'^[-*]\s+', '• ', result, flags=re.MULTILINE)

        # Numbered lists: keep as-is (Telegram handles fine)

        return result

    def to_discord(self, text: str) -> str:
        """
        Convert markdown to Discord format.

        Discord supports standard markdown with some extras:
        **bold**, *italic*, ~~strikethrough~~, `code`, ```code blocks```
        __underline__, ||spoiler||

        Args:
            text: Standard markdown text

        Returns:
            Discord-formatted text
        """
        # Discord uses standard markdown, so minimal conversion needed
        # Just ensure compatibility

        result = text

        # Discord doesn't support # headers well in messages
        # Convert to **bold** for visual emphasis
        result = re.sub(r'^#{1,6}\s+(.+)$', r'**\1**', result, flags=re.MULTILINE)

        return result

    def to_slack(self, text: str) -> str:
        """
        Convert markdown to Slack mrkdwn format.

        Slack uses its own format:
        *bold*, _italic_, ~strikethrough~, `code`, ```code blocks```
        <url|text> for links

        Args:
            text: Standard markdown text

        Returns:
            Slack mrkdwn formatted text
        """
        result = text

        # Bold: **text** -> *text* (Slack uses single asterisk)
        result = re.sub(r'\*\*(.+?)\*\*', r'*\1*', result)

        # Italic: *text* or _text_ -> _text_ (Slack uses underscore)
        # Only convert non-bold asterisks
        result = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'_\1_', result)

        # Strikethrough: ~~text~~ -> ~text~ (Slack uses single tilde)
        result = re.sub(r'~~(.+?)~~', r'~\1~', result)

        # Links: [text](url) -> <url|text>
        result = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<\2|\1>', result)

        # Headers: # text -> *text* (bold, since Slack has no headers)
        result = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', result, flags=re.MULTILINE)

        # Bullet lists: - item -> • item
        result = re.sub(r'^[-*]\s+', '• ', result, flags=re.MULTILINE)

        return result

    def convert(self, text: str, channel: str) -> str:
        """
        Convert markdown for a specific channel.

        Args:
            text: Standard markdown text
            channel: Target channel (telegram, discord, slack)

        Returns:
            Platform-formatted text
        """
        converters = {
            "telegram": self.to_telegram,
            "discord": self.to_discord,
            "slack": self.to_slack,
        }

        converter = converters.get(channel)
        if converter:
            return converter(text)

        return text  # No conversion for unknown channels

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        for char, escape in self.TELEGRAM_HTML_ESCAPE.items():
            text = text.replace(char, escape)
        return text

    @staticmethod
    def strip_markdown(text: str) -> str:
        """
        Remove all markdown formatting, leaving plain text.

        Useful for character counting before rendering.
        """
        result = text

        # Remove bold/italic markers
        result = re.sub(r'\*\*(.+?)\*\*', r'\1', result)
        result = re.sub(r'__(.+?)__', r'\1', result)
        result = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', result)
        result = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'\1', result)

        # Remove strikethrough
        result = re.sub(r'~~(.+?)~~', r'\1', result)

        # Remove inline code backticks
        result = re.sub(r'`([^`]+)`', r'\1', result)

        # Convert links to just text
        result = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', result)

        # Remove header markers
        result = re.sub(r'^#{1,6}\s+', '', result, flags=re.MULTILINE)

        return result
