"""Tests for tools/security/audit.py

The audit logger provides an append-only security event log for:
- Forensics and incident investigation
- Compliance requirements
- Detecting suspicious patterns

These tests ensure events are properly logged and queryable.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Setup: Patch DB_PATH to use temp database
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def audit_temp_db(temp_db):
    """Patch audit module to use temporary database."""
    with patch("tools.security.audit.DB_PATH", temp_db):
        # Import after patching to get fresh module state
        from tools.security import audit

        # Force table creation
        conn = audit.get_connection()
        conn.close()

        yield audit


# ─────────────────────────────────────────────────────────────────────────────
# Event Logging Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestLogEvent:
    """Tests for the log_event function."""

    def test_logs_basic_event(self, audit_temp_db):
        """Should log a basic event successfully."""
        result = audit_temp_db.log_event(
            event_type="auth",
            action="login",
            user_id="alice",
            status="success",
        )

        assert result["success"] is True
        assert "event_id" in result

    def test_logs_event_with_all_fields(self, audit_temp_db):
        """Should log event with all optional fields."""
        result = audit_temp_db.log_event(
            event_type="command",
            action="memory:write",
            user_id="alice",
            session_id="sess_123",
            channel="discord",
            resource="memory/context.md",
            status="success",
            details={"content_length": 500},
            ip_address="192.168.1.1",
            user_agent="DexAI/1.0",
        )

        assert result["success"] is True

    def test_rejects_invalid_event_type(self, audit_temp_db):
        """Should reject invalid event types."""
        result = audit_temp_db.log_event(
            event_type="invalid_type",  # Not in VALID_TYPES
            action="test",
        )

        assert result["success"] is False
        assert "Invalid event type" in result["error"]

    def test_rejects_invalid_status(self, audit_temp_db):
        """Should reject invalid status values."""
        result = audit_temp_db.log_event(
            event_type="auth",
            action="login",
            status="maybe",  # Not in VALID_STATUSES
        )

        assert result["success"] is False
        assert "Invalid status" in result["error"]

    def test_auto_increments_event_id(self, audit_temp_db):
        """Event IDs should auto-increment."""
        result1 = audit_temp_db.log_event(event_type="auth", action="login")
        result2 = audit_temp_db.log_event(event_type="auth", action="login")

        assert result2["event_id"] > result1["event_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Query Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestQueryEvents:
    """Tests for querying audit events."""

    def test_queries_by_user(self, audit_temp_db):
        """Should filter events by user."""
        # Log events for different users
        audit_temp_db.log_event(event_type="auth", action="login", user_id="alice")
        audit_temp_db.log_event(event_type="auth", action="login", user_id="bob")
        audit_temp_db.log_event(event_type="auth", action="logout", user_id="alice")

        result = audit_temp_db.query_events(user_id="alice")

        assert result["success"] is True
        assert len(result["events"]) == 2
        assert all(e["user_id"] == "alice" for e in result["events"])

    def test_queries_by_event_type(self, audit_temp_db):
        """Should filter events by type."""
        audit_temp_db.log_event(event_type="auth", action="login", user_id="alice")
        audit_temp_db.log_event(event_type="command", action="memory:read", user_id="alice")

        result = audit_temp_db.query_events(event_type="auth")

        assert result["success"] is True
        assert all(e["event_type"] == "auth" for e in result["events"])

    def test_queries_by_status(self, audit_temp_db):
        """Should filter events by status."""
        audit_temp_db.log_event(
            event_type="auth", action="login", user_id="alice", status="success"
        )
        audit_temp_db.log_event(event_type="auth", action="login", user_id="bob", status="failure")

        result = audit_temp_db.query_events(status="failure")

        assert result["success"] is True
        assert all(e["status"] == "failure" for e in result["events"])

    def test_queries_with_duration_since(self, audit_temp_db):
        """Should filter events by relative time duration."""
        audit_temp_db.log_event(event_type="auth", action="login", user_id="alice")

        result = audit_temp_db.query_events(since="24h")

        assert result["success"] is True
        # Event we just logged should be included

    def test_respects_limit(self, audit_temp_db):
        """Should respect the limit parameter."""
        for _ in range(10):
            audit_temp_db.log_event(event_type="auth", action="login", user_id="alice")

        result = audit_temp_db.query_events(limit=5)

        assert result["success"] is True
        assert len(result["events"]) == 5
        assert result["total"] == 10  # Total count should still be accurate

    def test_pagination_with_offset(self, audit_temp_db):
        """Should support pagination with offset."""
        for i in range(10):
            audit_temp_db.log_event(event_type="auth", action=f"action_{i}", user_id="alice")

        page1 = audit_temp_db.query_events(limit=5, offset=0)
        page2 = audit_temp_db.query_events(limit=5, offset=5)

        assert len(page1["events"]) == 5
        assert len(page2["events"]) == 5
        # Pages should have different events
        page1_ids = {e["id"] for e in page1["events"]}
        page2_ids = {e["id"] for e in page2["events"]}
        assert page1_ids.isdisjoint(page2_ids)


# ─────────────────────────────────────────────────────────────────────────────
# Statistics Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetStats:
    """Tests for audit statistics."""

    def test_returns_stats_structure(self, audit_temp_db):
        """Should return expected stats structure."""
        audit_temp_db.log_event(event_type="auth", action="login", status="success")

        result = audit_temp_db.get_stats()

        assert result["success"] is True
        assert "stats" in result
        stats = result["stats"]
        assert "total_events" in stats
        assert "events_24h" in stats
        assert "failures_24h" in stats
        assert "by_type" in stats
        assert "by_status" in stats

    def test_counts_by_type(self, audit_temp_db):
        """Should count events by type."""
        audit_temp_db.log_event(event_type="auth", action="login")
        audit_temp_db.log_event(event_type="auth", action="logout")
        audit_temp_db.log_event(event_type="command", action="test")

        result = audit_temp_db.get_stats()

        assert result["stats"]["by_type"]["auth"] == 2
        assert result["stats"]["by_type"]["command"] == 1

    def test_counts_failures(self, audit_temp_db):
        """Should track failure count."""
        audit_temp_db.log_event(event_type="auth", action="login", status="success")
        audit_temp_db.log_event(event_type="auth", action="login", status="failure")
        audit_temp_db.log_event(event_type="auth", action="login", status="failure")

        result = audit_temp_db.get_stats()

        assert result["stats"]["failures_24h"] >= 2


# ─────────────────────────────────────────────────────────────────────────────
# Export Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestExportEvents:
    """Tests for event export."""

    def test_exports_as_json(self, audit_temp_db):
        """Should export events as JSON."""
        audit_temp_db.log_event(event_type="auth", action="login", user_id="alice")

        result = audit_temp_db.export_events(format="json")

        assert result["success"] is True
        assert result["format"] == "json"
        assert len(result["data"]) >= 1

    def test_exports_as_csv(self, audit_temp_db):
        """Should export events as CSV."""
        audit_temp_db.log_event(event_type="auth", action="login", user_id="alice")

        result = audit_temp_db.export_events(format="csv")

        assert result["success"] is True
        assert result["format"] == "csv"
        assert "id,timestamp,event_type" in result["data"]


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCleanupOldEvents:
    """Tests for event retention/cleanup."""

    def test_dry_run_does_not_delete(self, audit_temp_db):
        """Dry run should report but not delete."""
        audit_temp_db.log_event(event_type="auth", action="login")

        result = audit_temp_db.cleanup_old_events(retention_days=0, dry_run=True)

        assert result["success"] is True
        assert result["dry_run"] is True

        # Event should still exist
        query_result = audit_temp_db.query_events()
        assert len(query_result["events"]) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Duration Parsing Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestParseDuration:
    """Tests for duration string parsing."""

    def test_parses_minutes(self, audit_temp_db):
        """Should parse minute duration."""
        result = audit_temp_db.parse_duration("30m")
        assert result == timedelta(minutes=30)

    def test_parses_hours(self, audit_temp_db):
        """Should parse hour duration."""
        result = audit_temp_db.parse_duration("24h")
        assert result == timedelta(hours=24)

    def test_parses_days(self, audit_temp_db):
        """Should parse day duration."""
        result = audit_temp_db.parse_duration("7d")
        assert result == timedelta(days=7)

    def test_parses_weeks(self, audit_temp_db):
        """Should parse week duration."""
        result = audit_temp_db.parse_duration("2w")
        assert result == timedelta(weeks=2)

    def test_returns_none_for_invalid(self, audit_temp_db):
        """Should return None for invalid format."""
        assert audit_temp_db.parse_duration("invalid") is None
        assert audit_temp_db.parse_duration("") is None


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_handles_special_characters_in_details(self, audit_temp_db):
        """Should handle special characters in details JSON."""
        result = audit_temp_db.log_event(
            event_type="auth",
            action="login",
            details={"message": "Hello 'world' \"quoted\" & special <chars>"},
        )

        assert result["success"] is True

        # Query and verify details are preserved
        query = audit_temp_db.query_events()
        event = query["events"][0]
        assert "world" in str(event["details"])

    def test_handles_null_fields(self, audit_temp_db):
        """Should handle null/None fields gracefully."""
        result = audit_temp_db.log_event(
            event_type="auth",
            action="login",
            user_id=None,
            session_id=None,
        )

        assert result["success"] is True
