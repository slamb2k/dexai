"""Tests for tools/adhd/language_filter.py

The language filter is critical for emotional safety of ADHD users with RSD
(Rejection Sensitive Dysphoria). It detects guilt-inducing phrases and reframes
them to forward-facing alternatives.

Key behaviors:
- Detect phrases like "overdue", "you haven't", "you forgot"
- Reframe to positive alternatives like "ready when you are"
- Preserve meaning while removing emotional harm
"""

from tools.adhd.language_filter import (
    batch_filter,
    check_content,
    detect_blocked_phrases,
    filter_content,
    list_blocked_phrases,
    reframe_content,
)


# ─────────────────────────────────────────────────────────────────────────────
# Phrase Detection Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectBlockedPhrases:
    """Tests for detecting RSD-triggering phrases."""

    def test_detects_overdue(self):
        """Should detect 'overdue' as guilt-inducing."""
        content = "The task is overdue by 3 days"
        detections = detect_blocked_phrases(content)

        assert len(detections) >= 1
        assert any(d["phrase"].lower() == "overdue" for d in detections)

    def test_detects_you_havent(self):
        """Should detect 'you haven't' variations."""
        test_cases = [
            "You haven't sent the email",
            "You still haven't replied",
        ]

        for content in test_cases:
            detections = detect_blocked_phrases(content)
            assert len(detections) >= 1, f"Failed to detect in: {content}"

    def test_detects_you_forgot(self):
        """Should detect 'you forgot' as guilt-inducing."""
        content = "You forgot to call Sarah"
        detections = detect_blocked_phrases(content)

        assert len(detections) >= 1

    def test_detects_failed_to(self):
        """Should detect 'failed to' as guilt-inducing."""
        content = "You failed to complete the assignment"
        detections = detect_blocked_phrases(content)

        assert len(detections) >= 1

    def test_detects_should_have(self):
        """Should detect 'should have' as guilt-inducing."""
        content = "You should have done this yesterday"
        detections = detect_blocked_phrases(content)

        assert len(detections) >= 1

    def test_case_insensitive(self):
        """Detection should be case insensitive."""
        detections_lower = detect_blocked_phrases("you forgot to call")
        detections_upper = detect_blocked_phrases("YOU FORGOT TO CALL")
        detections_mixed = detect_blocked_phrases("You Forgot To Call")

        assert len(detections_lower) >= 1
        assert len(detections_upper) >= 1
        assert len(detections_mixed) >= 1

    def test_safe_text_no_detection(self, safe_input):
        """Safe text should not trigger detection."""
        detections = detect_blocked_phrases(safe_input)
        assert len(detections) == 0

    def test_positive_text_no_detection(self):
        """Positive/forward-facing text should not trigger."""
        positive_texts = [
            "Ready when you are to send the email",
            "Let's revisit calling Sarah",
            "Want to tackle this now?",
            "Here's your next step",
        ]

        for text in positive_texts:
            detections = detect_blocked_phrases(text)
            assert len(detections) == 0, f"False positive for: {text}"


# ─────────────────────────────────────────────────────────────────────────────
# Reframing Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestReframeContent:
    """Tests for reframing guilt-inducing language."""

    def test_reframes_overdue(self):
        """Should reframe 'overdue' to positive alternative."""
        content = "The task is overdue"
        result, changes = reframe_content(content)

        assert "overdue" not in result.lower()
        assert len(changes) >= 1

    def test_reframes_you_still_havent(self):
        """Should reframe 'you still haven't' appropriately."""
        content = "You still haven't sent the invoice"
        result, _changes = reframe_content(content)

        assert "still haven't" not in result.lower()
        assert "invoice" in result.lower()  # Preserve the subject

    def test_preserves_case(self):
        """Should match capitalization of original."""
        # Sentence start should capitalize replacement
        content = "You forgot to send the file"
        result, _changes = reframe_content(content)

        # First character of reframe should be capitalized
        assert result[0].isupper() or result.startswith("Let's") or result.startswith("Ready")

    def test_preserves_unaffected_text(self):
        """Should not modify text without blocked phrases."""
        content = "Hello, here's your task for today"
        result, changes = reframe_content(content)

        assert result == content
        assert len(changes) == 0

    def test_handles_multiple_phrases(self):
        """Should reframe multiple blocked phrases in same text."""
        content = "You forgot to send the overdue invoice"
        result, changes = reframe_content(content)

        assert "forgot" not in result.lower()
        assert "overdue" not in result.lower()
        assert len(changes) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# Filter Content Tests (Full Pipeline)
# ─────────────────────────────────────────────────────────────────────────────


class TestFilterContent:
    """Tests for the complete filter pipeline."""

    def test_returns_correct_structure(self):
        """Should return expected result structure."""
        result = filter_content("Hello world")

        assert "success" in result
        assert "original" in result
        assert "filtered" in result
        assert "changes" in result
        assert "was_modified" in result

    def test_filters_guilt_phrase(self, guilt_phrases):
        """Should filter known guilt phrases."""
        for phrase in guilt_phrases:
            result = filter_content(phrase)
            assert result["success"] is True
            assert result["was_modified"] is True

    def test_preserves_safe_content(self, safe_input):
        """Should not modify safe content."""
        result = filter_content(safe_input)

        assert result["success"] is True
        assert result["filtered"] == safe_input
        assert result["was_modified"] is False

    def test_original_preserved(self):
        """Should preserve original in result."""
        content = "You forgot to call"
        result = filter_content(content)

        assert result["original"] == content

    def test_changes_recorded(self):
        """Should record what was changed."""
        content = "The task is overdue"
        result = filter_content(content)

        assert len(result["changes"]) >= 1
        change = result["changes"][0]
        assert "original" in change
        assert "replacement" in change


# ─────────────────────────────────────────────────────────────────────────────
# Check Content Tests (Detection Only)
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckContent:
    """Tests for check_content (detection without modification)."""

    def test_marks_safe_content_as_safe(self, safe_input):
        """Safe content should be marked as safe."""
        result = check_content(safe_input)

        assert result["success"] is True
        assert result["is_safe"] is True
        assert result["phrase_count"] == 0

    def test_marks_unsafe_content(self):
        """Content with blocked phrases should be marked unsafe."""
        result = check_content("You still haven't sent the email")

        assert result["success"] is True
        assert result["is_safe"] is False
        assert result["phrase_count"] >= 1

    def test_includes_detections(self):
        """Should include detection details."""
        result = check_content("The task is overdue")

        assert "detections" in result
        assert len(result["detections"]) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Batch Filter Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestBatchFilter:
    """Tests for batch filtering multiple pieces of content."""

    def test_filters_multiple_items(self):
        """Should filter all items in batch."""
        contents = [
            "You forgot to call Sarah",
            "Hello, how are you?",
            "The task is overdue",
        ]

        result = batch_filter(contents)

        assert result["success"] is True
        assert result["total_items"] == 3
        assert len(result["results"]) == 3

    def test_tracks_total_changes(self):
        """Should track total changes across batch."""
        contents = [
            "You forgot to call",
            "You still haven't replied",
        ]

        result = batch_filter(contents)

        assert result["total_changes"] >= 2


# ─────────────────────────────────────────────────────────────────────────────
# List Blocked Phrases Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestListBlockedPhrases:
    """Tests for listing blocked phrases."""

    def test_returns_blocked_phrases(self):
        """Should return list of blocked phrases."""
        result = list_blocked_phrases()

        assert result["success"] is True
        assert "blocked_phrases" in result
        assert len(result["blocked_phrases"]) > 0

    def test_includes_reframe_patterns(self):
        """Should include reframe patterns."""
        result = list_blocked_phrases()

        assert "reframe_patterns" in result

    def test_has_common_phrases(self):
        """Should include common guilt phrases."""
        result = list_blocked_phrases()
        phrases_lower = [p.lower() for p in result["blocked_phrases"]]

        assert "overdue" in phrases_lower
        # Check for some variation of "you haven't"
        assert any("haven't" in p for p in phrases_lower)


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_string(self):
        """Should handle empty string."""
        result = filter_content("")
        assert result["success"] is True
        assert result["filtered"] == ""

    def test_very_long_text(self):
        """Should handle very long text."""
        long_text = "Hello world " * 1000 + "You forgot to call " + "more text " * 1000
        result = filter_content(long_text)
        assert result["success"] is True
        assert result["was_modified"] is True

    def test_unicode_content(self):
        """Should handle unicode content."""
        content = "You forgot to send 世界 the file"
        result = filter_content(content)
        assert result["success"] is True
        assert "世界" in result["filtered"]

    def test_phrase_at_end(self):
        """Should detect phrase at end of text."""
        content = "The deadline is overdue"
        detections = detect_blocked_phrases(content)
        assert len(detections) >= 1

    def test_phrase_at_start(self):
        """Should detect phrase at start of text."""
        content = "Overdue tasks need attention"
        detections = detect_blocked_phrases(content)
        assert len(detections) >= 1

    def test_multiple_occurrences(self):
        """Should handle multiple occurrences of same phrase."""
        content = "You forgot this and you forgot that"
        detections = detect_blocked_phrases(content)
        # Should detect both occurrences
        forgot_detections = [d for d in detections if "forgot" in d["phrase"].lower()]
        assert len(forgot_detections) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# RSD Safety Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestRsdSafety:
    """Tests to ensure output is RSD-safe."""

    def test_no_guilt_in_output(self, guilt_phrases):
        """Filtered output should not contain guilt triggers."""
        guilt_words = ["overdue", "forgot", "failed", "behind", "neglected"]

        for phrase in guilt_phrases:
            result = filter_content(phrase)
            filtered_lower = result["filtered"].lower()

            for word in guilt_words:
                assert word not in filtered_lower, (
                    f"Output still contains '{word}': {result['filtered']}"
                )

    def test_forward_facing_language(self):
        """Output should use forward-facing language."""
        # Filter some common guilt phrases
        inputs = [
            "You still haven't sent the invoice",
            "The task is overdue",
            "You forgot to call Sarah",
        ]

        forward_indicators = ["ready", "let's", "want to", "revisit"]

        for content in inputs:
            result = filter_content(content)
            filtered_lower = result["filtered"].lower()

            # At least one forward-facing indicator should be present
            has_forward = any(ind in filtered_lower for ind in forward_indicators)
            # Or the original doesn't need reframing
            if result["was_modified"]:
                assert has_forward or "ready" in filtered_lower, (
                    f"No forward language in: {result['filtered']}"
                )
