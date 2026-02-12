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
    import pytest_asyncio  # noqa: F401

    HAS_ASYNC = True
except ImportError:
    HAS_ASYNC = False

try:
    from fastapi.testclient import TestClient  # noqa: F401

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

try:
    from httpx import ASGITransport, AsyncClient  # noqa: F401

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
        import tools.dashboard.backend.main as main_module
        from tools.dashboard.backend.database import init_db
        from tools.dashboard.backend.main import app

        # Initialize the test database
        init_db()

        # Disable auth for tests (tests don't set up sessions)
        original_config = main_module.security_config
        main_module.security_config = {**original_config, "require_auth": False}

        yield app

        # Restore original config
        main_module.security_config = original_config


@pytest.fixture
@requires_fastapi
def test_client(dashboard_app, temp_dashboard_db):
    """Create a test client for the dashboard API.

    Clears any events created during app lifespan startup (e.g. channel
    adapter connection audit events) so tests start with a clean slate.
    """
    from fastapi.testclient import TestClient

    with TestClient(dashboard_app) as client:
        # Clear events created during lifespan startup
        conn = sqlite3.connect(str(temp_dashboard_db))
        conn.execute("DELETE FROM dashboard_events")
        conn.execute("DELETE FROM dashboard_metrics")
        conn.commit()
        conn.close()

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
def mock_inbox_module():
    """Mock the inbox module for message storage."""

    mock = MagicMock()
    mock.store_message = MagicMock()

    return mock


# ─────────────────────────────────────────────────────────────────────────────
# ADHD Pipeline Fixtures
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# install.sh Test Fixtures
# ─────────────────────────────────────────────────────────────────────────────

INSTALL_SCRIPT = PROJECT_ROOT / "install.sh"


@pytest.fixture
def install_dir(tmp_path: Path) -> Path:
    """Create a temp directory mimicking a cloned DexAI repo.

    Creates a .git/ dir and copies .env.example so that setup_repository()
    takes the 'exists' branch instead of attempting git clone.
    """
    dexai_dir = tmp_path / "dexai"
    dexai_dir.mkdir()
    (dexai_dir / ".git").mkdir()

    # Copy .env.example if it exists in the real repo
    env_example = PROJECT_ROOT / ".env.example"
    if env_example.exists():
        import shutil

        shutil.copy(env_example, dexai_dir / ".env.example")

    return dexai_dir


@pytest.fixture
def stubbed_env(tmp_path: Path, install_dir: Path) -> dict[str, str]:
    """Create stub executables for all prerequisites.

    Returns an env dict with PATH pointing ONLY to the stubs dir (plus
    symlinked basic utilities). This fully isolates the environment so
    removing a stub makes the command genuinely unavailable.
    """
    import shutil

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def _make_stub(name: str, script: str) -> None:
        stub = bin_dir / name
        stub.write_text(script)
        stub.chmod(0o755)

    # Symlink basic utilities that install.sh needs (sort, grep, mkdir, etc.)
    _basic_utils = [
        "bash",
        "sh",
        "sort",
        "grep",
        "mkdir",
        "chmod",
        "cp",
        "touch",
        "cat",
        "printf",
        "sed",
        "awk",
        "rm",
        "ls",
        "tr",
        "head",
        "tail",
        "tee",
        "wc",
        "basename",
        "dirname",
        "readlink",
        "id",
        "env",
        "od",
        "cut",
        "sleep",
    ]
    for util in _basic_utils:
        real = shutil.which(util)
        if real and not (bin_dir / util).exists():
            (bin_dir / util).symlink_to(real)

    # git — succeeds for any invocation
    _make_stub("git", "#!/bin/bash\nexit 0\n")

    # curl — succeeds; handles health-check probes (localhost)
    _make_stub(
        "curl",
        '#!/bin/bash\nif [[ "$*" == *"localhost"* ]]; then exit 0; fi\nexit 0\n',
    )

    # python3 — handles version check invocation
    _make_stub(
        "python3",
        "#!/bin/bash\n"
        'if [[ "$*" == *"sys.version_info"* ]]; then\n'
        '    echo "3.12"\n'
        "else\n"
        "    exit 0\n"
        "fi\n",
    )

    # uv — creates fake venv so `source .venv/bin/activate` works
    _make_stub(
        "uv",
        "#!/bin/bash\n"
        'if [[ "$1" == "venv" ]] && [[ -n "$2" ]]; then\n'
        '    mkdir -p "$2/bin"\n'
        '    echo "# fake activate" > "$2/bin/activate"\n'
        "fi\n"
        "exit 0\n",
    )

    # docker — compose-aware stub (required in default mode)
    _make_stub(
        "docker",
        "#!/bin/bash\n"
        'if [[ "$1" == "compose" ]]; then\n'
        '    if [[ "$2" == "version" ]]; then\n'
        '        echo "Docker Compose version v2.20.0"\n'
        "    fi\n"
        "    exit 0\n"
        "fi\n"
        'if [[ "$1" == "info" ]]; then exit 0; fi\n'
        'if [[ "$1" == "--version" ]]; then echo "Docker version 24.0.0, build abc123"; fi\n'
        "exit 0\n",
    )

    # node — returns v20
    _make_stub(
        "node",
        '#!/bin/bash\nif [[ "$1" == "--version" ]]; then echo "v20.0.0"; else echo "v20.0.0"; fi\n',
    )

    # npm — succeeds for any invocation
    _make_stub("npm", "#!/bin/bash\nexit 0\n")

    # openssl — returns deterministic hex for master key generation
    _make_stub(
        "openssl",
        '#!/bin/bash\necho "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"\n',
    )

    # uname — returns Linux
    _make_stub("uname", '#!/bin/bash\necho "Linux"\n')

    env = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path / "home"),
        "DEXAI_DIR": str(install_dir),
        "TERM": "dumb",
    }
    # Create HOME directory
    (tmp_path / "home").mkdir(exist_ok=True)

    return env


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
