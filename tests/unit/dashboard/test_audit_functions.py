"""Tests for dashboard audit functions: record_tool_use() and log_audit()."""
import json
import sqlite3
from unittest.mock import patch

import pytest


@pytest.fixture
def dashboard_temp_db(tmp_path):
    """Create a temporary dashboard database."""
    db_path = tmp_path / "dashboard.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            channel TEXT,
            user_id TEXT,
            summary TEXT NOT NULL,
            details TEXT,
            severity TEXT DEFAULT 'info'
        )
    """)
    conn.commit()
    conn.close()
    return db_path


class TestRecordToolUse:
    """Tests for record_tool_use()."""

    def test_records_basic_tool_use(self, dashboard_temp_db):
        with patch("tools.dashboard.backend.database.DB_PATH", dashboard_temp_db):
            from tools.dashboard.backend.database import record_tool_use
            event_id = record_tool_use(
                tool_name="bash",
                tool_use_id="tu_123",
                success=True,
            )
            assert event_id > 0

            conn = sqlite3.connect(str(dashboard_temp_db))
            row = conn.execute("SELECT * FROM dashboard_events WHERE id = ?", (event_id,)).fetchone()
            conn.close()
            assert row is not None
            assert row[1] == "tool_use"  # event_type
            data = json.loads(row[6])  # details
            assert data["tool_name"] == "bash"
            assert data["success"] is True

    def test_records_with_user_and_duration(self, dashboard_temp_db):
        with patch("tools.dashboard.backend.database.DB_PATH", dashboard_temp_db):
            from tools.dashboard.backend.database import record_tool_use
            event_id = record_tool_use(
                tool_name="read",
                tool_use_id="tu_456",
                success=True,
                user_id="user1",
                duration_ms=150.5,
            )
            conn = sqlite3.connect(str(dashboard_temp_db))
            row = conn.execute("SELECT * FROM dashboard_events WHERE id = ?", (event_id,)).fetchone()
            conn.close()
            data = json.loads(row[6])  # details
            assert data["duration_ms"] == 150.5
            assert row[4] == "user1"  # user_id


class TestLogAudit:
    """Tests for log_audit()."""

    def test_logs_security_event(self, dashboard_temp_db):
        with patch("tools.dashboard.backend.database.DB_PATH", dashboard_temp_db):
            from tools.dashboard.backend.database import log_audit
            event_id = log_audit(
                event_type="auth",
                severity="info",
                actor="user1",
                target="/api/chat",
            )
            assert event_id > 0

            conn = sqlite3.connect(str(dashboard_temp_db))
            row = conn.execute("SELECT * FROM dashboard_events WHERE id = ?", (event_id,)).fetchone()
            conn.close()
            assert row[1] == "auth"  # event_type
            data = json.loads(row[6])  # details
            assert data["severity"] == "info"
            assert data["target"] == "/api/chat"

    def test_stores_details_as_json(self, dashboard_temp_db):
        with patch("tools.dashboard.backend.database.DB_PATH", dashboard_temp_db):
            from tools.dashboard.backend.database import log_audit
            event_id = log_audit(
                event_type="security",
                details={"reason": "rate_limit_exceeded", "count": 42},
            )
            conn = sqlite3.connect(str(dashboard_temp_db))
            row = conn.execute("SELECT * FROM dashboard_events WHERE id = ?", (event_id,)).fetchone()
            conn.close()
            data = json.loads(row[6])  # details
            assert data["reason"] == "rate_limit_exceeded"
            assert data["count"] == 42
