"""
Integration test fixtures for DexAI.

Provides fixtures specific to integration testing:
- FastAPI test clients
- Database isolation for dashboard
- Mock channel adapters
- Task decomposition fixtures
"""

import os
import sqlite3
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Handle optional dependencies gracefully
try:
    import pytest_asyncio

    HAS_ASYNC = True
except ImportError:
    HAS_ASYNC = False

try:
    from fastapi.testclient import TestClient

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

try:
    from httpx import ASGITransport, AsyncClient

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


# Skip markers for tests requiring optional dependencies
requires_fastapi = pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")
requires_async = pytest.mark.skipif(not HAS_ASYNC, reason="pytest-asyncio not installed")
requires_httpx = pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")


# ─────────────────────────────────────────────────────────────────────────────
# Path Constants
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard API Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_dashboard_db() -> Generator[Path, None, None]:
    """Create a temporary dashboard database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        os.unlink(db_path)


@pytest.fixture
def temp_activity_db() -> Generator[Path, None, None]:
    """Create a temporary activity database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Initialize activity database schema
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            source TEXT,
            request TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            summary TEXT
        )
    """)
    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    if db_path.exists():
        os.unlink(db_path)


@pytest.fixture
@requires_fastapi
def dashboard_app(temp_dashboard_db, temp_activity_db):
    """Create a test FastAPI app with isolated database."""
    # Patch database paths before importing the app
    with (
        patch("tools.dashboard.backend.database.DB_PATH", temp_dashboard_db),
        patch("tools.dashboard.backend.routes.tasks.ACTIVITY_DB", temp_activity_db),
    ):
        # Import app after patching
        from tools.dashboard.backend.database import init_db
        from tools.dashboard.backend.main import app

        # Initialize the test database
        init_db()

        yield app


@pytest.fixture
@requires_fastapi
def test_client(dashboard_app):
    """Create a test client for the dashboard API."""
    from fastapi.testclient import TestClient

    with TestClient(dashboard_app) as client:
        yield client


@pytest.fixture
@requires_fastapi
@requires_httpx
@requires_async
async def async_test_client(dashboard_app) -> AsyncGenerator:
    """Create an async test client for the dashboard API."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=dashboard_app), base_url="http://test"
    ) as client:
        yield client


# ─────────────────────────────────────────────────────────────────────────────
# Channel Router Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_channel_adapter():
    """Create a mock channel adapter for testing."""
    from tools.channels.models import UnifiedMessage
    from tools.channels.router import ChannelAdapter

    class MockAdapter(ChannelAdapter):
        def __init__(self, name: str = "mock"):
            self._name = name
            self._connected = False
            self.sent_messages: list[UnifiedMessage] = []
            self.received_messages: list[UnifiedMessage] = []

        @property
        def name(self) -> str:
            return self._name

        async def connect(self) -> None:
            self._connected = True

        async def disconnect(self) -> None:
            self._connected = False

        async def send_message(self, message: UnifiedMessage) -> dict:
            self.sent_messages.append(message)
            return {"success": True, "message_id": f"mock_{message.id}"}

        def to_unified(self, raw_message) -> UnifiedMessage:
            return UnifiedMessage(
                id=raw_message.get("id", "test_id"),
                channel=self._name,
                channel_message_id=raw_message.get("message_id", "test_msg_id"),
                channel_user_id=raw_message.get("user_id", "test_user"),
                direction="inbound",
                content=raw_message.get("content", ""),
            )

        def from_unified(self, message: UnifiedMessage):
            return {
                "id": message.id,
                "content": message.content,
                "user_id": message.channel_user_id,
            }

    return MockAdapter


@pytest.fixture
def message_router(mock_channel_adapter):
    """Create a fresh MessageRouter instance with mock adapter."""
    from tools.channels.router import MessageRouter

    router = MessageRouter()
    adapter = mock_channel_adapter("test_channel")
    router.register_adapter(adapter)

    return router, adapter


@pytest.fixture
def sample_unified_message():
    """Create a sample unified message for testing."""
    from tools.channels.models import UnifiedMessage

    def _create_message(
        content: str = "Hello, world!",
        channel: str = "test_channel",
        user_id: str = "test_user",
        channel_user_id: str = "channel_test_user",
    ) -> UnifiedMessage:
        return UnifiedMessage(
            id=UnifiedMessage.generate_id(),
            channel=channel,
            channel_message_id="msg_123",
            channel_user_id=channel_user_id,
            user_id=user_id,
            direction="inbound",
            content=content,
        )

    return _create_message


# ─────────────────────────────────────────────────────────────────────────────
# Task Flow Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def task_databases(temp_db):
    """Patch all task-related database paths to use temp database."""
    with (
        patch("tools.tasks.manager.DB_PATH", temp_db),
        patch("tools.tasks.DB_PATH", temp_db),
        patch("tools.tasks.decompose.PROJECT_ROOT", PROJECT_ROOT),
    ):
        from tools.tasks import manager

        # Initialize database
        conn = manager.get_connection()
        conn.close()

        yield manager


@pytest.fixture
def commitment_database():
    """Create a temporary commitment database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    with patch("tools.memory.commitments.DB_PATH", db_path):
        from tools.memory import commitments

        # Initialize database by getting connection
        conn = commitments.get_connection()
        conn.close()

        yield commitments, db_path

    # Cleanup
    if db_path.exists():
        os.unlink(db_path)


# ─────────────────────────────────────────────────────────────────────────────
# Security Pipeline Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_paired_user():
    """Create a mock user that is paired."""
    from tools.channels.models import ChannelUser

    return ChannelUser(
        id="test_user_123",
        channel="test_channel",
        channel_user_id="channel_test_user",
        display_name="Test User",
        is_paired=True,
    )


@pytest.fixture
def mock_unpaired_user():
    """Create a mock user that is not paired."""
    from tools.channels.models import ChannelUser

    return ChannelUser(
        id="unpaired_user",
        channel="test_channel",
        channel_user_id="channel_unpaired_user",
        display_name="Unpaired User",
        is_paired=False,
    )


@pytest.fixture
def mock_inbox_module(mock_paired_user):
    """Mock the inbox module for user lookups."""

    def get_user_by_channel(channel: str, channel_user_id: str):
        if channel_user_id == "channel_test_user":
            return mock_paired_user
        return None

    mock = MagicMock()
    mock.get_user_by_channel = get_user_by_channel
    mock.create_or_update_user = MagicMock()
    mock.store_message = MagicMock()
    mock.get_preferred_channel = MagicMock(return_value="test_channel")

    return mock


# ─────────────────────────────────────────────────────────────────────────────
# ADHD Pipeline Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def rsd_trigger_messages():
    """Messages that should trigger RSD language filtering."""
    return [
        "You still haven't sent the report",
        "The deadline is overdue by 3 days",
        "You forgot to call the client",
        "You failed to complete the task",
        "You never finished the project",
    ]


@pytest.fixture
def safe_messages():
    """Messages that should pass through RSD filter unchanged."""
    return [
        "Ready when you are to send the report",
        "Want to tackle the deadline now?",
        "Let's revisit calling the client",
        "Here's your next step",
    ]


@pytest.fixture
def long_response():
    """A long response that should be truncated by the formatter."""
    return """Sure! That's a great question. I'd be happy to help you with that.

    First, you should gather all your documents. Make sure you have your ID,
    your tax returns from last year, and any relevant receipts.

    Second, you'll want to log into the portal. The URL is example.com/login.
    You might need to reset your password if you haven't logged in recently.

    Third, once you're logged in, navigate to the "Submit Documents" section.
    This is usually found in the left sidebar under "My Account".

    Fourth, upload each document one at a time. The system supports PDF, JPG,
    and PNG formats. Maximum file size is 10MB per document.

    Finally, click the "Submit" button to complete the process. You should
    receive a confirmation email within 24 hours."""
