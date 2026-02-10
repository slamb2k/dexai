"""Integration tests for multi-modal messaging flow (Phase 15a)

Tests the wiring between components:
- _build_media_context() in sdk_handler.py
- _format_response_for_channel() in sdk_handler.py
- Pending image state in channel_tools.py
"""

import pytest

from tools.channels.models import Attachment, MediaContent
from tools.channels.sdk_handler import _build_media_context, _format_response_for_channel
from tools.agent.mcp.channel_tools import (
    clear_pending_image,
    get_pending_image,
    set_pending_image,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_media(
    *,
    processed=True,
    vision_description=None,
    extracted_text=None,
    transcription=None,
    filename="file.jpg",
    type="image",
    page_count=None,
):
    """Factory for MediaContent with an embedded Attachment."""
    attachment = Attachment(
        id="att-1",
        type=type,
        filename=filename,
        mime_type="application/octet-stream",
        size_bytes=1024,
    )
    return MediaContent(
        attachment=attachment,
        processed=processed,
        vision_description=vision_description,
        extracted_text=extracted_text,
        transcription=transcription,
        page_count=page_count,
    )


# ─────────────────────────────────────────────────────────────────────────────
# _build_media_context() Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildMediaContext:
    """Tests for building AI context from processed media."""

    def test_empty_list_returns_empty_string(self):
        """Empty processed_media list returns empty string."""
        assert _build_media_context([]) == ""

    def test_single_image_with_vision_description(self):
        """Single image with vision_description includes description in context."""
        media = _make_media(vision_description="A cat sitting on a table")
        result = _build_media_context([media])

        assert "A cat sitting on a table" in result
        assert "[Attachment]" in result

    def test_single_document_with_extracted_text(self):
        """Single document with extracted_text includes text in context."""
        media = _make_media(
            type="document",
            filename="report.pdf",
            extracted_text="Quarterly revenue increased 20%",
            page_count=5,
        )
        result = _build_media_context([media])

        assert "Quarterly revenue increased 20%" in result
        assert "report.pdf" in result
        assert "5 pages" in result

    def test_multiple_attachments_adhd_summary(self):
        """Multiple attachments produce ADHD-style numbered summary."""
        media1 = _make_media(vision_description="A dog")
        media2 = _make_media(
            type="document",
            filename="notes.txt",
            extracted_text="Meeting notes from Monday",
        )
        result = _build_media_context([media1, media2])

        assert "[User sent 2 attachments]" in result
        assert "[Attachment 1]" in result
        assert "[Attachment 2]" in result
        assert "A dog" in result
        assert "Meeting notes from Monday" in result

    def test_unprocessed_media_excluded(self):
        """Unprocessed media items are excluded from context."""
        media_ok = _make_media(vision_description="A cat")
        media_fail = _make_media(processed=False)

        result = _build_media_context([media_ok, media_fail])

        # Only one successful, so no "User sent X attachments" prefix
        assert "[Attachment]" in result
        assert "A cat" in result


# ─────────────────────────────────────────────────────────────────────────────
# _format_response_for_channel() Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFormatResponseForChannel:
    """Tests for channel-specific response formatting."""

    def test_telegram_code_blocks_use_html(self):
        """Code blocks are formatted with HTML tags for Telegram."""
        response = "Here is code:\n```python\nprint('hi')\n```"
        result = _format_response_for_channel(response, "telegram")

        assert "<pre>" in result
        assert "<code" in result

    def test_discord_code_blocks_use_markdown(self):
        """Code blocks use markdown fences for Discord."""
        response = "Here is code:\n```python\nprint('hi')\n```"
        result = _format_response_for_channel(response, "discord")

        assert "```python" in result

    def test_plain_text_passes_through(self):
        """Plain text without code blocks passes through unchanged."""
        response = "Hello, how can I help you today?"
        result = _format_response_for_channel(response, "telegram")

        assert result == response


# ─────────────────────────────────────────────────────────────────────────────
# Pending Image State Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestPendingImageState:
    """Tests for thread-local pending image state in channel_tools."""

    def setup_method(self):
        """Clear state before each test."""
        clear_pending_image()

    def test_set_then_get_returns_url(self):
        """set_pending_image + get_pending_image returns the URL."""
        set_pending_image("https://example.com/image.png")

        assert get_pending_image() == "https://example.com/image.png"

    def test_clear_then_get_returns_none(self):
        """clear_pending_image makes subsequent get return None."""
        set_pending_image("https://example.com/image.png")
        clear_pending_image()

        assert get_pending_image() is None

    def test_default_state_is_none(self):
        """Without setting, get_pending_image returns None."""
        assert get_pending_image() is None
