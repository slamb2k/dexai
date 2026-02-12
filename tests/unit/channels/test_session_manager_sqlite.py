"""Tests for SQLite session storage in tools/channels/session_manager.py"""

import json
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_db_path(tmp_path):
    return tmp_path / "sessions.db"


@pytest.fixture
def temp_json_path(tmp_path):
    return tmp_path / "sessions.json"


@pytest.fixture
def session_manager(temp_db_path, temp_json_path):
    with (
        patch("tools.channels.session_manager._DB_PATH", temp_db_path),
        patch("tools.channels.session_manager.SESSION_STORE_PATH", temp_json_path),
    ):
        from tools.channels.session_manager import SessionManager

        manager = SessionManager(persist=True, timeout_minutes=60)
        return manager


class TestGetConnection:
    def test_creates_table(self, temp_db_path):
        with patch("tools.channels.session_manager._DB_PATH", temp_db_path):
            from tools.channels.session_manager import get_connection

            conn = get_connection()
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            )
            assert cursor.fetchone() is not None
            conn.close()

    def test_creates_directory(self, tmp_path):
        db_path = tmp_path / "subdir" / "sessions.db"
        with patch("tools.channels.session_manager._DB_PATH", db_path):
            from tools.channels.session_manager import get_connection

            conn = get_connection()
            assert db_path.exists()
            conn.close()


class TestSQLiteSaveLoad:
    def test_save_and_load_session(self, temp_db_path, temp_json_path):
        with (
            patch("tools.channels.session_manager._DB_PATH", temp_db_path),
            patch("tools.channels.session_manager.SESSION_STORE_PATH", temp_json_path),
        ):
            from tools.channels.session_manager import SessionManager

            manager = SessionManager(persist=True)

            session = manager.get_session(channel="telegram", session_type="main")
            session._message_count = 5
            session._total_cost = 0.42
            session.sdk_session_id = "test-session-123"

            manager._save_sessions()

            manager2 = SessionManager(persist=True)
            assert "telegram" in manager2._sessions
            restored = manager2._sessions["telegram"]
            assert restored._message_count == 5
            assert restored._total_cost == 0.42
            assert restored.sdk_session_id == "test-session-123"

    def test_stale_sessions_cleaned_on_save(self, temp_db_path, temp_json_path):
        with (
            patch("tools.channels.session_manager._DB_PATH", temp_db_path),
            patch("tools.channels.session_manager.SESSION_STORE_PATH", temp_json_path),
        ):
            from tools.channels.session_manager import SessionManager

            manager = SessionManager(persist=True, timeout_minutes=1)
            session = manager.get_session(channel="discord")
            session._last_activity = datetime.now() - timedelta(hours=2)

            manager._save_sessions()

            conn = sqlite3.connect(str(temp_db_path))
            cursor = conn.execute("SELECT COUNT(*) FROM sessions WHERE session_key = 'discord'")
            count = cursor.fetchone()[0]
            conn.close()
            assert count == 0


class TestJSONMigration:
    def test_migrates_json_to_sqlite(self, temp_db_path, temp_json_path):
        json_data = {
            "telegram": {
                "channel": "telegram",
                "session_type": "main",
                "sdk_session_id": "sid-123",
                "workspace_path": None,
                "last_activity": datetime.now().isoformat(),
                "message_count": 10,
                "total_cost": 1.5,
                "created_at": datetime.now().isoformat(),
            }
        }
        temp_json_path.write_text(json.dumps(json_data))

        with (
            patch("tools.channels.session_manager._DB_PATH", temp_db_path),
            patch("tools.channels.session_manager.SESSION_STORE_PATH", temp_json_path),
        ):
            from tools.channels.session_manager import SessionManager

            manager = SessionManager(persist=True)

            assert "telegram" in manager._sessions
            assert manager._sessions["telegram"].sdk_session_id == "sid-123"

            migrated_path = temp_json_path.with_suffix(".json.migrated")
            assert migrated_path.exists()
            assert not temp_json_path.exists()

    def test_migration_skipped_if_no_json(self, temp_db_path, temp_json_path):
        with (
            patch("tools.channels.session_manager._DB_PATH", temp_db_path),
            patch("tools.channels.session_manager.SESSION_STORE_PATH", temp_json_path),
        ):
            from tools.channels.session_manager import SessionManager

            manager = SessionManager(persist=True)
            assert len(manager._sessions) == 0

    def test_empty_json_migrated(self, temp_db_path, temp_json_path):
        temp_json_path.write_text("{}")

        with (
            patch("tools.channels.session_manager._DB_PATH", temp_db_path),
            patch("tools.channels.session_manager.SESSION_STORE_PATH", temp_json_path),
        ):
            from tools.channels.session_manager import SessionManager

            manager = SessionManager(persist=True)
            assert len(manager._sessions) == 0
            migrated_path = temp_json_path.with_suffix(".json.migrated")
            assert migrated_path.exists()


class TestSessionPersistenceRoundTrip:
    def test_multiple_sessions_persist(self, temp_db_path, temp_json_path):
        with (
            patch("tools.channels.session_manager._DB_PATH", temp_db_path),
            patch("tools.channels.session_manager.SESSION_STORE_PATH", temp_json_path),
        ):
            from tools.channels.session_manager import SessionManager

            manager = SessionManager(persist=True)

            s1 = manager.get_session(channel="telegram")
            s1._message_count = 3
            s2 = manager.get_session(channel="discord")
            s2._message_count = 7

            manager._save_sessions()

            manager2 = SessionManager(persist=True)
            assert "telegram" in manager2._sessions
            assert "discord" in manager2._sessions
            assert manager2._sessions["telegram"]._message_count == 3
            assert manager2._sessions["discord"]._message_count == 7
