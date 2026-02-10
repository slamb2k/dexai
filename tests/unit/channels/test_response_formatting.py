"""Tests for response formatting functions in tools/channels/media_processor.py

Tests the three content formatting functions:
- parse_response_blocks: Parse AI response into text/code blocks
- format_blocks_for_channel: Apply channel-specific formatting
- split_for_channel: Split content respecting channel message limits
"""

from tools.channels.media_processor import (
    format_blocks_for_channel,
    parse_response_blocks,
    split_for_channel,
)


# ─────────────────────────────────────────────────────────────────────────────
# parse_response_blocks Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestParseResponseBlocks:
    """Tests for parsing AI responses into content blocks."""

    def test_plain_text_returns_single_text_block(self):
        """Plain text with no code fences returns a single text block."""
        result = parse_response_blocks("Hello world")

        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert result[0]["content"] == "Hello world"
        assert result[0]["metadata"] == {}

    def test_single_code_block_with_language(self):
        """A code block with language hint is parsed correctly."""
        text = "Here is some code:\n```python\nprint('hello')\n```"
        result = parse_response_blocks(text)

        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert "Here is some code:" in result[0]["content"]
        assert result[1]["type"] == "code"
        assert "print('hello')" in result[1]["content"]
        assert result[1]["metadata"]["language"] == "python"

    def test_text_code_text_interleaved(self):
        """Text + code + text produces 3 blocks in order."""
        text = "Before\n```js\nconsole.log('hi')\n```\nAfter"
        result = parse_response_blocks(text)

        assert len(result) == 3
        assert result[0]["type"] == "text"
        assert result[0]["content"] == "Before"
        assert result[1]["type"] == "code"
        assert "console.log" in result[1]["content"]
        assert result[2]["type"] == "text"
        assert result[2]["content"] == "After"

    def test_multiple_code_blocks(self):
        """Multiple code blocks are ordered correctly."""
        text = "```python\na = 1\n```\n\n```bash\necho hi\n```"
        result = parse_response_blocks(text)

        code_blocks = [b for b in result if b["type"] == "code"]
        assert len(code_blocks) == 2
        assert code_blocks[0]["metadata"]["language"] == "python"
        assert code_blocks[1]["metadata"]["language"] == "bash"

    def test_code_block_without_language_defaults_to_text(self):
        """Code block with no language hint defaults to 'text'."""
        text = "```\nsome content\n```"
        result = parse_response_blocks(text)

        code_blocks = [b for b in result if b["type"] == "code"]
        assert len(code_blocks) == 1
        assert code_blocks[0]["metadata"]["language"] == "text"

    def test_empty_string_returns_single_text_block(self):
        """Empty string returns a single text block with empty content."""
        result = parse_response_blocks("")

        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert result[0]["content"] == ""

    def test_special_characters_in_code_preserved(self):
        """Special characters (<, >, &) in code blocks are preserved unescaped."""
        text = '```html\n<div class="test">&amp;</div>\n```'
        result = parse_response_blocks(text)

        code_blocks = [b for b in result if b["type"] == "code"]
        assert len(code_blocks) == 1
        assert "<div" in code_blocks[0]["content"]
        assert "&amp;" in code_blocks[0]["content"]


# ─────────────────────────────────────────────────────────────────────────────
# format_blocks_for_channel Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFormatBlocksForChannel:
    """Tests for channel-specific block formatting."""

    def test_telegram_uses_html_pre_code(self):
        """Telegram code blocks use HTML <pre><code> tags."""
        blocks = [
            {"type": "code", "content": "print('hi')", "metadata": {"language": "python"}},
        ]
        result = format_blocks_for_channel(blocks, "telegram")

        assert '<pre><code class="language-python">' in result
        assert "</code></pre>" in result
        assert "print(&#x27;hi&#x27;)" in result or "print('hi')" in result

    def test_telegram_escapes_html_entities(self):
        """Telegram formatting escapes &, <, > in code blocks."""
        blocks = [
            {"type": "code", "content": "a < b && c > d", "metadata": {"language": "text"}},
        ]
        result = format_blocks_for_channel(blocks, "telegram")

        assert "&amp;" in result
        assert "&lt;" in result
        assert "&gt;" in result

    def test_discord_uses_markdown_fences(self):
        """Discord code blocks use markdown triple-backtick with language."""
        blocks = [
            {"type": "code", "content": "x = 1\n", "metadata": {"language": "python"}},
        ]
        result = format_blocks_for_channel(blocks, "discord")

        assert "```python" in result
        assert "x = 1" in result
        assert result.rstrip().endswith("```")

    def test_slack_uses_plain_fences(self):
        """Slack code blocks use triple-backtick without language hint."""
        blocks = [
            {"type": "code", "content": "echo hello", "metadata": {"language": "bash"}},
        ]
        result = format_blocks_for_channel(blocks, "slack")

        # Slack format: ```content``` (no language hint)
        assert "```echo hello```" in result

    def test_unknown_channel_uses_default_markdown(self):
        """Unknown channel falls back to markdown fences with language."""
        blocks = [
            {"type": "code", "content": "code\n", "metadata": {"language": "ruby"}},
        ]
        result = format_blocks_for_channel(blocks, "unknown_channel")

        assert "```ruby" in result

    def test_text_blocks_pass_through_unchanged(self):
        """Text blocks are included as-is regardless of channel."""
        blocks = [
            {"type": "text", "content": "Hello world", "metadata": {}},
        ]
        result_tg = format_blocks_for_channel(blocks, "telegram")
        result_dc = format_blocks_for_channel(blocks, "discord")

        assert result_tg == "Hello world"
        assert result_dc == "Hello world"


# ─────────────────────────────────────────────────────────────────────────────
# split_for_channel Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSplitForChannel:
    """Tests for splitting content to respect channel message limits."""

    def _config_with_limits(self, **limits):
        """Helper to create a config with specific channel limits."""
        return {"formatting": {"channel_limits": limits}}

    def test_short_content_returns_single_chunk(self):
        """Content under the limit is returned as a single-element list."""
        config = self._config_with_limits(telegram=4096)
        result = split_for_channel("Short message", "telegram", config=config)

        assert result == ["Short message"]

    def test_splits_at_paragraph_boundary(self):
        """Long content splits at \\n\\n paragraph boundary when possible."""
        paragraph1 = "A" * 1500
        paragraph2 = "B" * 1500
        content = f"{paragraph1}\n\n{paragraph2}"
        config = self._config_with_limits(discord=2000)

        result = split_for_channel(content, "discord", config=config)

        assert len(result) == 2
        assert result[0].strip() == paragraph1
        assert result[1].strip() == paragraph2

    def test_splits_at_sentence_boundary(self):
        """When no paragraph break, splits at sentence boundary."""
        # Build content that exceeds limit without paragraph breaks
        sentence1 = "A" * 1200 + "."
        sentence2 = " " + "B" * 1200
        content = sentence1 + sentence2
        config = self._config_with_limits(discord=2000)

        result = split_for_channel(content, "discord", config=config)

        assert len(result) >= 2

    def test_splits_at_space_as_fallback(self):
        """When no sentence boundary, splits at space."""
        # Words that exceed limit
        words = " ".join(["word"] * 500)
        config = self._config_with_limits(discord=2000)

        result = split_for_channel(words, "discord", config=config)

        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 2000

    def test_telegram_limit_respected(self):
        """Telegram's 4096 character limit is respected."""
        content = "X" * 8000
        config = self._config_with_limits(telegram=4096)

        result = split_for_channel(content, "telegram", config=config)

        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 4096

    def test_discord_limit_respected(self):
        """Discord's 2000 character limit is respected."""
        content = "Y" * 5000
        config = self._config_with_limits(discord=2000)

        result = split_for_channel(content, "discord", config=config)

        assert len(result) >= 3
        for chunk in result:
            assert len(chunk) <= 2000
