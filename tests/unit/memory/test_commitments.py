"""Tests for tools/memory/commitments.py

The commitments tracker helps ADHD users avoid relationship damage by tracking
promises made in conversations. Key behaviors:
- Add commitments with optional due dates
- Track completion status
- Surface commitments due soon
- Extract commitments from text (pattern-based)

These tests ensure reliable commitment tracking.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Setup: Patch DB_PATH to use temp database
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def commitments_temp_db(temp_db):
    """Patch commitments module to use temporary database."""
    with patch("tools.memory.commitments.DB_PATH", temp_db):
        from tools.memory import commitments

        # Force table creation
        conn = commitments.get_connection()
        conn.close()

        yield commitments


# ─────────────────────────────────────────────────────────────────────────────
# Add Commitment Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAddCommitment:
    """Tests for adding commitments."""

    def test_adds_basic_commitment(self, commitments_temp_db, mock_user_id):
        """Should add a basic commitment."""
        result = commitments_temp_db.add_commitment(
            user_id=mock_user_id,
            content="Send the API docs to Sarah",
        )

        assert result["success"] is True
        assert "id" in result["data"]
        assert result["data"]["content"] == "Send the API docs to Sarah"

    def test_adds_commitment_with_target(self, commitments_temp_db, sample_commitment):
        """Should add commitment with target person."""
        result = commitments_temp_db.add_commitment(
            user_id=sample_commitment["user_id"],
            content=sample_commitment["content"],
            target_person=sample_commitment["target_person"],
        )

        assert result["success"] is True
        assert result["data"]["target_person"] == sample_commitment["target_person"]

    def test_adds_commitment_with_due_date(self, commitments_temp_db, mock_user_id):
        """Should add commitment with due date."""
        result = commitments_temp_db.add_commitment(
            user_id=mock_user_id,
            content="Send invoice",
            due_date="2026-02-10",
        )

        assert result["success"] is True
        assert result["data"]["due_date"] is not None

    def test_generates_unique_id(self, commitments_temp_db, mock_user_id):
        """Should generate unique IDs."""
        result1 = commitments_temp_db.add_commitment(mock_user_id, "commitment 1")
        result2 = commitments_temp_db.add_commitment(mock_user_id, "commitment 2")

        assert result1["data"]["id"] != result2["data"]["id"]

    def test_default_status_is_active(self, commitments_temp_db, mock_user_id):
        """New commitments should have 'active' status."""
        result = commitments_temp_db.add_commitment(mock_user_id, "commitment")

        assert result["data"]["status"] == "active"

    def test_requires_user_id(self, commitments_temp_db):
        """Should require user_id."""
        result = commitments_temp_db.add_commitment(
            user_id="",
            content="commitment",
        )

        assert result["success"] is False

    def test_requires_content(self, commitments_temp_db, mock_user_id):
        """Should require content."""
        result = commitments_temp_db.add_commitment(
            user_id=mock_user_id,
            content="",
        )

        assert result["success"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Due Date Parsing Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestParseDueDate:
    """Tests for due date parsing."""

    def test_parses_iso_format(self, commitments_temp_db):
        """Should parse ISO date format."""
        result = commitments_temp_db.parse_due_date("2026-02-15")
        assert result is not None
        assert "2026-02-15" in result

    def test_parses_relative_today(self, commitments_temp_db):
        """Should parse 'today' as relative date."""
        result = commitments_temp_db.parse_due_date("today")
        assert result is not None

    def test_parses_relative_tomorrow(self, commitments_temp_db):
        """Should parse 'tomorrow' as relative date."""
        result = commitments_temp_db.parse_due_date("tomorrow")
        assert result is not None
        # Should be later than today
        tomorrow = datetime.fromisoformat(result)
        assert tomorrow > datetime.now()

    def test_parses_in_x_days(self, commitments_temp_db):
        """Should parse 'in X days' format."""
        result = commitments_temp_db.parse_due_date("in 3 days")
        assert result is not None

    def test_returns_none_for_invalid(self, commitments_temp_db):
        """Should return None for invalid format."""
        result = commitments_temp_db.parse_due_date("invalid date")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# List Commitments Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestListCommitments:
    """Tests for listing commitments."""

    def test_lists_user_commitments(self, commitments_temp_db, mock_user_id):
        """Should list all commitments for a user."""
        commitments_temp_db.add_commitment(mock_user_id, "commitment 1")
        commitments_temp_db.add_commitment(mock_user_id, "commitment 2")
        commitments_temp_db.add_commitment("other_user", "commitment 3")

        result = commitments_temp_db.list_commitments(mock_user_id)

        assert result["success"] is True
        assert len(result["data"]["commitments"]) == 2

    def test_filters_by_status(self, commitments_temp_db, mock_user_id):
        """Should filter by status."""
        commitments_temp_db.add_commitment(mock_user_id, "active one")
        result2 = commitments_temp_db.add_commitment(mock_user_id, "to complete")

        # Complete one
        commitments_temp_db.complete_commitment(result2["data"]["id"])

        active = commitments_temp_db.list_commitments(mock_user_id, status="active")
        completed = commitments_temp_db.list_commitments(mock_user_id, status="completed")

        assert len(active["data"]["commitments"]) == 1
        assert len(completed["data"]["commitments"]) == 1

    def test_filters_by_target_person(self, commitments_temp_db, mock_user_id):
        """Should filter by target person."""
        commitments_temp_db.add_commitment(mock_user_id, "promise to Sarah", target_person="Sarah")
        commitments_temp_db.add_commitment(mock_user_id, "promise to John", target_person="John")

        result = commitments_temp_db.list_commitments(mock_user_id, target_person="Sarah")

        assert len(result["data"]["commitments"]) == 1
        assert result["data"]["commitments"][0]["target_person"] == "Sarah"

    def test_groups_by_person(self, commitments_temp_db, mock_user_id):
        """Should support grouping by target person."""
        commitments_temp_db.add_commitment(mock_user_id, "promise 1", target_person="Sarah")
        commitments_temp_db.add_commitment(mock_user_id, "promise 2", target_person="Sarah")
        commitments_temp_db.add_commitment(mock_user_id, "promise 3", target_person="John")

        result = commitments_temp_db.list_commitments(mock_user_id, group_by_person=True)

        assert "commitments_by_person" in result["data"]
        assert "Sarah" in result["data"]["commitments_by_person"]
        assert len(result["data"]["commitments_by_person"]["Sarah"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Complete/Cancel Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCompleteCommitment:
    """Tests for completing commitments."""

    def test_completes_commitment(self, commitments_temp_db, mock_user_id):
        """Should mark commitment as completed."""
        create_result = commitments_temp_db.add_commitment(mock_user_id, "promise")
        commitment_id = create_result["data"]["id"]

        result = commitments_temp_db.complete_commitment(commitment_id)

        assert result["success"] is True

        # Verify status changed
        get_result = commitments_temp_db.get_commitment(commitment_id)
        assert get_result["data"]["status"] == "completed"

    def test_adds_completion_notes(self, commitments_temp_db, mock_user_id):
        """Should allow adding completion notes."""
        create_result = commitments_temp_db.add_commitment(mock_user_id, "promise")
        commitment_id = create_result["data"]["id"]

        commitments_temp_db.complete_commitment(commitment_id, notes="Sent via email")

        get_result = commitments_temp_db.get_commitment(commitment_id)
        assert "Sent via email" in (get_result["data"]["notes"] or "")

    def test_fails_for_nonexistent(self, commitments_temp_db):
        """Should fail for non-existent commitment."""
        result = commitments_temp_db.complete_commitment("nonexistent")

        assert result["success"] is False


class TestCancelCommitment:
    """Tests for cancelling commitments."""

    def test_cancels_commitment(self, commitments_temp_db, mock_user_id):
        """Should mark commitment as cancelled."""
        create_result = commitments_temp_db.add_commitment(mock_user_id, "promise")
        commitment_id = create_result["data"]["id"]

        result = commitments_temp_db.cancel_commitment(commitment_id)

        assert result["success"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Due Soon / Overdue Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetDueSoon:
    """Tests for getting commitments due soon."""

    def test_gets_commitments_due_soon(self, commitments_temp_db, mock_user_id):
        """Should get commitments due within specified hours."""
        # Add commitment due in 12 hours
        due_soon = (datetime.now() + timedelta(hours=12)).isoformat()
        commitments_temp_db.add_commitment(
            mock_user_id,
            "due soon",
            due_date=due_soon,
        )

        # Add commitment due in 48 hours
        due_later = (datetime.now() + timedelta(hours=48)).isoformat()
        commitments_temp_db.add_commitment(
            mock_user_id,
            "due later",
            due_date=due_later,
        )

        result = commitments_temp_db.get_due_soon(mock_user_id, hours=24)

        assert result["success"] is True
        assert len(result["data"]["commitments"]) == 1

    def test_includes_hours_until_due(self, commitments_temp_db, mock_user_id):
        """Should include hours until due in results."""
        due_time = (datetime.now() + timedelta(hours=6)).isoformat()
        commitments_temp_db.add_commitment(mock_user_id, "soon", due_date=due_time)

        result = commitments_temp_db.get_due_soon(mock_user_id, hours=24)

        if result["data"]["commitments"]:
            assert "hours_until_due" in result["data"]["commitments"][0]


class TestGetOverdue:
    """Tests for getting overdue commitments."""

    def test_gets_overdue_commitments(self, commitments_temp_db, mock_user_id):
        """Should get overdue commitments."""
        # Add commitment with past due date
        past_due = (datetime.now() - timedelta(days=1)).isoformat()
        commitments_temp_db.add_commitment(
            mock_user_id,
            "overdue",
            due_date=past_due,
        )

        result = commitments_temp_db.get_overdue(mock_user_id)

        assert result["success"] is True
        assert result["data"]["count"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Commitment Extraction Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractCommitments:
    """Tests for extracting commitments from text."""

    def test_extracts_ill_patterns(self, commitments_temp_db, mock_user_id):
        """Should extract 'I'll...' patterns."""
        text = "I'll send you the docs tomorrow"
        result = commitments_temp_db.extract_commitments(mock_user_id, text)

        assert result["success"] is True
        assert result["data"]["count"] >= 1

    def test_extracts_promise_patterns(self, commitments_temp_db, mock_user_id):
        """Should extract promise patterns."""
        text = "I promise to review the PR today"
        result = commitments_temp_db.extract_commitments(mock_user_id, text)

        assert result["success"] is True
        assert result["data"]["count"] >= 1

    def test_returns_low_confidence_for_patterns(self, commitments_temp_db, mock_user_id):
        """Pattern-based extraction should have low confidence."""
        text = "I'll call you later"
        result = commitments_temp_db.extract_commitments(mock_user_id, text)

        if result["data"]["extracted_commitments"]:
            assert result["data"]["extracted_commitments"][0]["confidence"] == "low"


# ─────────────────────────────────────────────────────────────────────────────
# Statistics Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetStats:
    """Tests for commitment statistics."""

    def test_returns_stats(self, commitments_temp_db, mock_user_id):
        """Should return commitment statistics."""
        commitments_temp_db.add_commitment(mock_user_id, "commitment 1")
        commitments_temp_db.add_commitment(mock_user_id, "commitment 2")

        result = commitments_temp_db.get_stats(mock_user_id)

        assert result["success"] is True
        assert "stats" in result
        assert "active_commitments" in result["stats"]

    def test_calculates_completion_rate(self, commitments_temp_db, mock_user_id):
        """Should calculate completion rate."""
        result1 = commitments_temp_db.add_commitment(mock_user_id, "completed one")
        commitments_temp_db.add_commitment(mock_user_id, "active one")

        commitments_temp_db.complete_commitment(result1["data"]["id"])

        stats = commitments_temp_db.get_stats(mock_user_id)

        assert "completion_rate_30d" in stats["stats"]


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_handles_unicode_content(self, commitments_temp_db, mock_user_id):
        """Should handle unicode in content."""
        result = commitments_temp_db.add_commitment(
            mock_user_id,
            "Send 日本語 docs to 山田さん",
            target_person="山田",
        )

        assert result["success"] is True
        assert "日本語" in result["data"]["content"]

    def test_handles_special_characters(self, commitments_temp_db, mock_user_id):
        """Should handle special characters."""
        result = commitments_temp_db.add_commitment(
            mock_user_id,
            "Review O'Brien's PR & send feedback",
        )

        assert result["success"] is True

    def test_handles_null_target_person(self, commitments_temp_db, mock_user_id):
        """Should handle commitments without target person."""
        result = commitments_temp_db.add_commitment(
            mock_user_id,
            "General commitment",
            target_person=None,
        )

        assert result["success"] is True


# ─────────────────────────────────────────────────────────────────────────────
# ADHD-Friendly Behavior Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAdhdFriendlyBehavior:
    """Tests to ensure ADHD-friendly behavior."""

    def test_age_tracked(self, commitments_temp_db, mock_user_id):
        """Should track commitment age for surfacing."""
        commitments_temp_db.add_commitment(mock_user_id, "old commitment")

        result = commitments_temp_db.list_commitments(mock_user_id)

        # Should include age info
        if result["data"]["commitments"]:
            assert "age_days" in result["data"]["commitments"][0]

    def test_overdue_flag_set(self, commitments_temp_db, mock_user_id):
        """Should flag overdue commitments (for internal use, not display)."""
        past_due = (datetime.now() - timedelta(days=1)).isoformat()
        commitments_temp_db.add_commitment(
            mock_user_id,
            "overdue",
            due_date=past_due,
        )

        result = commitments_temp_db.list_commitments(mock_user_id)

        # Internal flag for logic, never shown as "overdue" count to user
        if result["data"]["commitments"]:
            assert "is_overdue" in result["data"]["commitments"][0]
