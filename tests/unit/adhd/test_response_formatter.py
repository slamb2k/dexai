"""Tests for tools/adhd/response_formatter.py

The response formatter ensures AI responses are ADHD-friendly:
- Short by default (1-2 sentences)
- No filler/preamble
- One thing at a time
- Depth on demand

Key behaviors:
- Strip preambles like "Sure!" and "That's a great question!"
- Truncate to max sentences
- Detect expansion requests ("more", "details")
- Extract single actionable item from lists
"""

from tools.adhd.response_formatter import (
    expand_response,
    extract_one_thing,
    format_response,
    is_one_thing_trigger,
    should_expand,
    split_sentences,
    strip_preamble,
    truncate_to_sentences,
)


# ─────────────────────────────────────────────────────────────────────────────
# Preamble Stripping Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestStripPreamble:
    """Tests for removing filler phrases from responses."""

    def test_strips_sure(self):
        """Should strip 'Sure!' preamble."""
        content = "Sure! Here's the answer."
        result = strip_preamble(content)
        assert not result.lower().startswith("sure")

    def test_strips_of_course(self):
        """Should strip 'Of course!' preamble."""
        content = "Of course! I'd be happy to help. Here's the info."
        result = strip_preamble(content)
        assert not result.lower().startswith("of course")

    def test_strips_great_question(self):
        """Should strip 'Great question!' preamble."""
        content = "That's a great question! The answer is..."
        result = strip_preamble(content)
        assert "great question" not in result.lower()

    def test_strips_multiple_preambles(self):
        """Should strip chained preambles."""
        content = "Sure! Of course! Here's what you need."
        result = strip_preamble(content)
        assert not result.lower().startswith("sure")
        assert not result.lower().startswith("of course")

    def test_preserves_content_without_preamble(self):
        """Should not modify content without preamble."""
        content = "Here's the direct answer."
        result = strip_preamble(content)
        assert result == content

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert strip_preamble("") == ""

    def test_case_insensitive(self):
        """Should strip regardless of case."""
        content = "SURE! The answer is here."
        result = strip_preamble(content)
        assert not result.upper().startswith("SURE")


# ─────────────────────────────────────────────────────────────────────────────
# Sentence Splitting Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSplitSentences:
    """Tests for sentence splitting."""

    def test_splits_on_period(self):
        """Should split on periods."""
        content = "First sentence. Second sentence. Third sentence."
        sentences = split_sentences(content)
        assert len(sentences) == 3

    def test_splits_on_question_mark(self):
        """Should split on question marks."""
        content = "Is this right? I think so."
        sentences = split_sentences(content)
        assert len(sentences) == 2

    def test_splits_on_exclamation(self):
        """Should split on exclamation marks."""
        content = "Do this now! Then do that."
        sentences = split_sentences(content)
        assert len(sentences) == 2

    def test_handles_abbreviations(self):
        """Should not split on abbreviations."""
        content = "Dr. Smith works here. Mr. Jones does too."
        sentences = split_sentences(content)
        assert len(sentences) == 2

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert split_sentences("") == []


# ─────────────────────────────────────────────────────────────────────────────
# Truncation Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTruncateToSentences:
    """Tests for sentence truncation."""

    def test_truncates_to_limit(self):
        """Should truncate to max sentences."""
        content = "One. Two. Three. Four. Five."
        result = truncate_to_sentences(content, max_sentences=2)
        sentences = split_sentences(result)
        assert len(sentences) <= 2

    def test_preserves_short_content(self):
        """Should not truncate content under limit."""
        content = "One sentence only."
        result = truncate_to_sentences(content, max_sentences=5)
        assert result == content

    def test_adds_ending_punctuation(self):
        """Should ensure proper ending punctuation."""
        content = "First sentence. Second sentence"
        result = truncate_to_sentences(content, max_sentences=1)
        assert result.endswith(".")


# ─────────────────────────────────────────────────────────────────────────────
# Format Response Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFormatResponse:
    """Tests for the main format_response function."""

    def test_returns_correct_structure(self):
        """Should return expected result structure."""
        result = format_response("Hello world.")

        assert "success" in result
        assert "original" in result
        assert "formatted" in result
        assert "was_truncated" in result

    def test_strips_preamble(self):
        """Should strip preamble from response."""
        content = "Sure! Here's a detailed explanation about the topic."
        result = format_response(content, add_more_hint=False)

        assert "sure" not in result["formatted"].lower()

    def test_truncates_long_response(self):
        """Should truncate long responses."""
        content = "One. Two. Three. Four. Five. Six. Seven."
        result = format_response(content, max_sentences=2, add_more_hint=False)

        assert result["was_truncated"] is True
        assert result["kept_sentences"] <= 2

    def test_adds_more_hint_when_truncated(self):
        """Should add 'more' hint when content is truncated."""
        content = "One. Two. Three. Four. Five."
        result = format_response(content, max_sentences=2, add_more_hint=True)

        assert "'more'" in result["formatted"].lower()

    def test_no_hint_when_not_truncated(self):
        """Should not add hint when content fits."""
        content = "Short response."
        result = format_response(content, max_sentences=5, add_more_hint=True)

        # Short content shouldn't be truncated
        if not result["was_truncated"]:
            assert "'more'" not in result["formatted"].lower()

    def test_respects_char_limit(self):
        """Should respect character limit."""
        content = "A" * 500
        result = format_response(content, max_chars=100, add_more_hint=False)

        # Should be truncated (allowing some margin for ellipsis)
        assert len(result["formatted"]) <= 110


# ─────────────────────────────────────────────────────────────────────────────
# Expand Response Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestExpandResponse:
    """Tests for expand_response function."""

    def test_returns_full_content(self):
        """Should return full content on expansion."""
        content = "This is a longer explanation with many details."
        result = expand_response(content, user="alice")

        assert result["success"] is True
        assert "expanded" in result

    def test_still_strips_preamble(self):
        """Should still strip preamble on expansion."""
        content = "Sure! Here's the full explanation."
        result = expand_response(content, user="alice")

        assert "sure" not in result["expanded"].lower()

    def test_tracks_user(self):
        """Should track which user requested expansion."""
        result = expand_response("Content", user="alice")
        assert result["user"] == "alice"


# ─────────────────────────────────────────────────────────────────────────────
# Should Expand Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestShouldExpand:
    """Tests for should_expand function."""

    def test_detects_more_keyword(self):
        """Should detect 'more' as expansion request."""
        result = should_expand("alice", "tell me more")
        assert result["should_expand"] is True
        assert result["matched_keyword"] == "more"

    def test_detects_details_keyword(self):
        """Should detect 'details' as expansion request."""
        result = should_expand("alice", "give me the details")
        assert result["should_expand"] is True

    def test_detects_explain_keyword(self):
        """Should detect 'explain' as expansion request."""
        result = should_expand("alice", "can you explain?")
        assert result["should_expand"] is True

    def test_detects_why_keyword(self):
        """Should detect 'why' as expansion request."""
        result = should_expand("alice", "why is that?")
        assert result["should_expand"] is True

    def test_rejects_non_expansion(self):
        """Should not trigger on normal messages."""
        # Use a fresh user ID to avoid cross-test state from expand_response tests
        result = should_expand("bob_fresh_user", "thanks")
        assert result["should_expand"] is False

    def test_case_insensitive(self):
        """Should be case insensitive."""
        result = should_expand("alice", "TELL ME MORE")
        assert result["should_expand"] is True


# ─────────────────────────────────────────────────────────────────────────────
# One Thing Extraction Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractOneThing:
    """Tests for extract_one_thing function."""

    def test_extracts_from_numbered_list(self):
        """Should extract one item from numbered list."""
        content = "1. Send invoice 2. Review PR 3. Call Sarah"
        result = extract_one_thing(content)

        assert result["success"] is True
        assert result["one_thing"]  # Not empty
        assert result["total_found"] == 3
        assert result["alternatives_available"] is True

    def test_extracts_from_bulleted_list(self):
        """Should extract from bullet list."""
        content = "- First task\n- Second task\n- Third task"
        result = extract_one_thing(content)

        assert result["success"] is True
        assert result["total_found"] >= 1

    def test_extracts_from_comma_separated(self):
        """Should extract from comma-separated items."""
        content = "send email, review code, call client"
        result = extract_one_thing(content)

        assert result["success"] is True

    def test_adds_alternatives_hint(self):
        """Should add hint about alternatives when multiple items."""
        content = "1. Option A 2. Option B"
        result = extract_one_thing(content)

        if result["alternatives_available"]:
            assert "something else" in result["one_thing"].lower()

    def test_handles_single_item(self):
        """Should handle content with single item."""
        content = "Just do this one thing."
        result = extract_one_thing(content)

        assert result["success"] is True
        assert result["one_thing"]

    def test_handles_empty_content(self):
        """Should handle content with no extractable items."""
        result = extract_one_thing("")

        assert result["success"] is True
        # Should provide helpful fallback message


# ─────────────────────────────────────────────────────────────────────────────
# One Thing Trigger Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestIsOneThingTrigger:
    """Tests for is_one_thing_trigger function."""

    def test_detects_what_should_i_do(self):
        """Should detect 'what should I do' as trigger."""
        result = is_one_thing_trigger("what should I do?")
        assert result["is_trigger"] is True

    def test_detects_whats_next(self):
        """Should detect "what's next" as trigger."""
        result = is_one_thing_trigger("what's next?")
        assert result["is_trigger"] is True

    def test_detects_im_stuck(self):
        """Should detect "I'm stuck" as trigger."""
        result = is_one_thing_trigger("I'm stuck on this task")
        assert result["is_trigger"] is True

    def test_detects_overwhelmed(self):
        """Should detect 'overwhelmed' as trigger."""
        result = is_one_thing_trigger("I'm overwhelmed with tasks")
        assert result["is_trigger"] is True

    def test_rejects_non_trigger(self):
        """Should not trigger on normal questions."""
        result = is_one_thing_trigger("how do I configure this?")
        assert result["is_trigger"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_handles_unicode(self):
        """Should handle unicode content."""
        content = "Sure! Here's how to handle 日本語 text."
        result = format_response(content, add_more_hint=False)
        assert result["success"] is True
        assert "日本語" in result["formatted"]

    def test_handles_very_long_response(self):
        """Should handle very long responses."""
        content = "A sentence here. " * 100
        result = format_response(content, max_sentences=2)
        assert result["success"] is True
        assert result["was_truncated"] is True

    def test_handles_no_sentences(self):
        """Should handle content without sentence structure."""
        content = "no punctuation at all"
        result = format_response(content, add_more_hint=False)
        assert result["success"] is True

    def test_preserves_meaning(self):
        """Formatted content should preserve key meaning."""
        content = "Sure! The API key is stored in config.json. You need to set it first."
        result = format_response(content, max_sentences=2, add_more_hint=False)

        # Key information should be preserved
        assert "config.json" in result["formatted"] or "API" in result["formatted"]


# ─────────────────────────────────────────────────────────────────────────────
# ADHD-Friendly Output Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestAdhdFriendlyOutput:
    """Tests to ensure output is ADHD-friendly."""

    def test_output_is_concise(self):
        """Formatted output should be concise."""
        long_content = "Let me explain. " * 20
        result = format_response(long_content, max_sentences=2, add_more_hint=False)

        # Should be significantly shorter
        assert len(result["formatted"]) < len(long_content)

    def test_no_filler_in_output(self):
        """Output should not contain filler phrases."""
        content = "Sure! Of course! I'd be happy to help. Here's the answer."
        result = format_response(content, add_more_hint=False)

        filler_phrases = ["sure!", "of course!", "i'd be happy to"]
        output_lower = result["formatted"].lower()

        for filler in filler_phrases:
            assert filler not in output_lower

    def test_one_thing_is_actionable(self):
        """Extracted one thing should be actionable."""
        content = "Tasks: 1. Send the email to John 2. Review the PR 3. Call Sarah"
        result = extract_one_thing(content)

        # Should contain an action verb
        action_verbs = ["send", "call", "review", "email", "write", "check"]
        one_thing_lower = result["one_thing"].lower()

        has_action = any(verb in one_thing_lower for verb in action_verbs)
        # Either has action verb or is the fallback message
        assert has_action or "figure out" in one_thing_lower
