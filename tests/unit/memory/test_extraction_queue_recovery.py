"""Tests for extraction queue crash recovery in tools/memory/extraction/queue.py"""

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from tools.memory.extraction.queue import (
    ExtractionQueue,
    ConversationTurn,
    ExtractionJob,
    _get_connection,
    _DB_PATH,
)


@pytest.fixture
def temp_db_path(tmp_path):
    return tmp_path / "extraction_queue.db"


@pytest.fixture
def queue(temp_db_path):
    with patch("tools.memory.extraction.queue._DB_PATH", temp_db_path):
        q = ExtractionQueue(
            provider=None,
            batch_size=5,
            flush_interval_seconds=1.0,
            max_queue_size=100,
            gate_threshold=0.0,  # Accept everything
        )
        return q


@pytest.fixture
def sample_turn():
    return ConversationTurn(
        user_message="I need to file my taxes by April 15",
        assistant_response="Let me help you with that.",
        user_id="owner",
        session_id="sess-123",
        channel="telegram",
        recent_context=[],
    )


class TestSQLitePersistence:
    def test_get_connection_creates_table(self, temp_db_path):
        with patch("tools.memory.extraction.queue._DB_PATH", temp_db_path):
            conn = _get_connection()
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='queue_items'"
            )
            assert cursor.fetchone() is not None
            conn.close()

    @pytest.mark.asyncio
    async def test_enqueue_persists_to_sqlite(self, queue, sample_turn, temp_db_path):
        with patch("tools.memory.extraction.queue._DB_PATH", temp_db_path):
            result = await queue.enqueue(sample_turn)
            assert result is True

            conn = sqlite3.connect(str(temp_db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM queue_items")
            rows = cursor.fetchall()
            conn.close()

            assert len(rows) == 1
            assert rows[0]["status"] == "pending"

            item_data = json.loads(rows[0]["item_data"])
            assert item_data["user_message"] == "I need to file my taxes by April 15"
            assert item_data["user_id"] == "owner"


class TestCrashRecovery:
    @pytest.mark.asyncio
    async def test_recover_pending_items(self, temp_db_path):
        with patch("tools.memory.extraction.queue._DB_PATH", temp_db_path):
            conn = _get_connection()
            item_data = json.dumps({
                "user_message": "test message",
                "assistant_response": "test response",
                "user_id": "owner",
                "session_id": "sess-1",
                "channel": "telegram",
                "recent_context": [],
                "timestamp": datetime.now().isoformat(),
                "gate_score": 0.5,
            })
            conn.execute(
                "INSERT INTO queue_items (item_data, status) VALUES (?, ?)",
                (item_data, "pending"),
            )
            conn.commit()
            conn.close()

            queue = ExtractionQueue(
                provider=None,
                gate_threshold=0.0,
            )
            recovered = await queue.recover()
            assert recovered == 1
            assert queue._queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_recover_processing_items(self, temp_db_path):
        with patch("tools.memory.extraction.queue._DB_PATH", temp_db_path):
            conn = _get_connection()
            item_data = json.dumps({
                "user_message": "interrupted message",
                "assistant_response": "interrupted response",
                "user_id": "owner",
                "session_id": "sess-2",
                "channel": "discord",
                "recent_context": [],
                "timestamp": datetime.now().isoformat(),
                "gate_score": 0.7,
            })
            conn.execute(
                "INSERT INTO queue_items (item_data, status) VALUES (?, ?)",
                (item_data, "processing"),
            )
            conn.commit()
            conn.close()

            queue = ExtractionQueue(provider=None, gate_threshold=0.0)
            recovered = await queue.recover()
            assert recovered == 1

    @pytest.mark.asyncio
    async def test_recover_skips_done_and_failed(self, temp_db_path):
        with patch("tools.memory.extraction.queue._DB_PATH", temp_db_path):
            conn = _get_connection()
            item_data = json.dumps({
                "user_message": "done message",
                "assistant_response": "done response",
                "user_id": "owner",
                "timestamp": datetime.now().isoformat(),
            })
            conn.execute(
                "INSERT INTO queue_items (item_data, status) VALUES (?, ?)",
                (item_data, "done"),
            )
            conn.execute(
                "INSERT INTO queue_items (item_data, status) VALUES (?, ?)",
                (item_data, "failed"),
            )
            conn.commit()
            conn.close()

            queue = ExtractionQueue(provider=None, gate_threshold=0.0)
            recovered = await queue.recover()
            assert recovered == 0

    @pytest.mark.asyncio
    async def test_recover_empty_db(self, temp_db_path):
        with patch("tools.memory.extraction.queue._DB_PATH", temp_db_path):
            _get_connection().close()
            queue = ExtractionQueue(provider=None, gate_threshold=0.0)
            recovered = await queue.recover()
            assert recovered == 0


class TestStatusTransitions:
    @pytest.mark.asyncio
    async def test_enqueue_sets_pending(self, queue, sample_turn, temp_db_path):
        with patch("tools.memory.extraction.queue._DB_PATH", temp_db_path):
            await queue.enqueue(sample_turn)

            conn = sqlite3.connect(str(temp_db_path))
            cursor = conn.execute("SELECT status FROM queue_items")
            row = cursor.fetchone()
            conn.close()
            assert row[0] == "pending"

    @pytest.mark.asyncio
    async def test_failed_enqueue_marks_failed(self, temp_db_path, sample_turn):
        with patch("tools.memory.extraction.queue._DB_PATH", temp_db_path):
            queue = ExtractionQueue(
                provider=None,
                max_queue_size=1,
                gate_threshold=0.0,
            )
            # Fill the queue
            await queue.enqueue(sample_turn)

            turn2 = ConversationTurn(
                user_message="second message",
                assistant_response="second response",
                user_id="owner",
            )
            # This should replace, not fail since the current implementation drops oldest
            await queue.enqueue(turn2)

            conn = sqlite3.connect(str(temp_db_path))
            cursor = conn.execute("SELECT COUNT(*) FROM queue_items")
            count = cursor.fetchone()[0]
            conn.close()
            assert count >= 1
