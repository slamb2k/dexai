"""Integration tests for workspace isolation with sessions.

These tests verify that:
- Sessions correctly integrate with workspaces
- Workspace paths are passed to SDK client
- Session cleanup handles workspaces correctly

Single-tenant: Sessions use channel-only keys with a single workspace.
"""

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_workspace_base(tmp_path: Path) -> Path:
    """Create a temporary base path for workspaces."""
    workspace_base = tmp_path / "workspaces"
    workspace_base.mkdir(parents=True, exist_ok=True)
    return workspace_base


@pytest.fixture
def temp_templates_dir(tmp_path: Path) -> Path:
    """Create temporary template files for bootstrapping."""
    templates = tmp_path / "templates"
    templates.mkdir(parents=True, exist_ok=True)

    # Create minimal template files
    (templates / "PERSONA.md").write_text("# Persona\nYou are Dex.")
    (templates / "IDENTITY.md").write_text("# Identity\nDex is an ADHD assistant.")

    return templates


@pytest.fixture
def workspace_config(temp_workspace_base: Path, temp_templates_dir: Path) -> dict:
    """Create test workspace configuration."""
    return {
        "workspace": {
            "enabled": True,
            "base_path": str(temp_workspace_base),
            "scope": {
                "default": "persistent",
                "cleanup": {
                    "stale_days": 30,
                    "cleanup_on_startup": False,
                },
            },
            "templates": {
                "path": str(temp_templates_dir),
                "bootstrap_files": ["PERSONA.md", "IDENTITY.md"],
            },
            "access": {"default": "rw"},
            "restrictions": {
                "max_file_size_bytes": 1048576,
                "max_workspace_size_bytes": 10485760,
                "blocked_extensions": [".exe"],
            },
        }
    }


@pytest.fixture
def mock_workspace_manager(
    workspace_config: dict, temp_workspace_base: Path, temp_templates_dir: Path
):
    """Create a mocked WorkspaceManager."""
    with (
        patch("tools.agent.system_prompt.TEMPLATES_PATH", temp_templates_dir),
        patch("tools.agent.system_prompt.BOOTSTRAP_FILES", ["PERSONA.md", "IDENTITY.md"]),
    ):
        from tools.agent.workspace_manager import WorkspaceManager

        manager = WorkspaceManager(config=workspace_config)
        yield manager

        # Cleanup
        if temp_workspace_base.exists():
            shutil.rmtree(temp_workspace_base)


# ─────────────────────────────────────────────────────────────────────────────
# Session-Workspace Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSessionWorkspaceIntegration:
    """Tests for Session class workspace integration."""

    @pytest.mark.asyncio
    async def test_session_creates_workspace_on_init(
        self, mock_workspace_manager, temp_workspace_base
    ):
        """Session should create workspace when ensuring client."""
        from tools.channels.session_manager import Session

        # Patch the workspace manager singleton
        with patch(
            "tools.agent.workspace_manager.get_workspace_manager",
            return_value=mock_workspace_manager,
        ):
            session = Session(channel="telegram")

            # Before client init, workspace_path is None
            assert session.workspace_path is None

            # Mock the SDK client initialization
            with patch("tools.agent.sdk_client.DexAIClient") as mock_dexai_client:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_dexai_client.return_value = mock_client

                await session._ensure_client()

                # After init, workspace should be set
                assert session.workspace_path is not None
                assert session.workspace_path.exists()

            await session.close()

    @pytest.mark.asyncio
    async def test_session_passes_workspace_to_client(
        self, mock_workspace_manager, temp_workspace_base
    ):
        """Session should pass workspace_path to DexAIClient."""
        from tools.channels.session_manager import Session

        with patch(
            "tools.agent.workspace_manager.get_workspace_manager",
            return_value=mock_workspace_manager,
        ):
            session = Session(channel="discord")

            with patch("tools.agent.sdk_client.DexAIClient") as mock_dexai_client:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_dexai_client.return_value = mock_client

                await session._ensure_client()

                # Check DexAIClient was called with working_dir
                mock_dexai_client.assert_called_once()
                call_kwargs = mock_dexai_client.call_args.kwargs
                assert "working_dir" in call_kwargs
                assert str(temp_workspace_base) in call_kwargs["working_dir"]

            await session.close()

    @pytest.mark.asyncio
    async def test_session_close_marks_workspace_end(
        self, mock_workspace_manager, temp_workspace_base
    ):
        """Session close should mark workspace session end."""
        from tools.channels.session_manager import Session

        # Create workspace
        workspace = mock_workspace_manager.create_workspace()
        assert workspace.exists()

        with patch(
            "tools.agent.workspace_manager.get_workspace_manager",
            return_value=mock_workspace_manager,
        ):
            session = Session(
                channel="slack",
                workspace_path=workspace,
            )

            with patch("tools.agent.sdk_client.DexAIClient") as mock_dexai_client:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_dexai_client.return_value = mock_client

                await session._ensure_client()
                await session.close()

            # Permanent workspace should still exist
            assert workspace.exists()


class TestSessionSerialization:
    """Tests for session serialization with workspace paths."""

    def test_session_to_dict_includes_workspace(self, mock_workspace_manager):
        """Session serialization should include workspace_path."""
        from tools.channels.session_manager import Session

        workspace = mock_workspace_manager.create_workspace()

        session = Session(
            channel="telegram",
            workspace_path=workspace,
        )

        data = session.to_dict()

        assert "workspace_path" in data
        assert data["workspace_path"] == str(workspace)

    def test_session_from_dict_restores_workspace(self, mock_workspace_manager):
        """Session deserialization should restore workspace_path."""
        from tools.channels.session_manager import Session

        workspace = mock_workspace_manager.create_workspace()

        # Create and serialize a session
        original = Session(
            channel="telegram",
            workspace_path=workspace,
        )
        data = original.to_dict()

        # Restore from dict
        restored = Session.from_dict(data)

        assert restored.workspace_path is not None
        assert restored.workspace_path == workspace


# ─────────────────────────────────────────────────────────────────────────────
# SessionManager Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSessionManagerWorkspaceIntegration:
    """Tests for SessionManager workspace handling."""

    def test_get_session_creates_with_workspace(self, mock_workspace_manager):
        """SessionManager.get_session should create session with workspace support."""
        from tools.channels.session_manager import SessionManager

        with patch(
            "tools.agent.workspace_manager.get_workspace_manager",
            return_value=mock_workspace_manager,
        ):
            manager = SessionManager(persist=False)

            session = manager.get_session("telegram")

            assert session is not None
            assert session.channel == "telegram"
            # workspace_path is set lazily on first _ensure_client

    @pytest.mark.asyncio
    async def test_clear_session_handles_workspace(self, mock_workspace_manager):
        """Clearing a session should properly handle workspace cleanup."""
        from tools.channels.session_manager import SessionManager

        # Create workspace
        workspace = mock_workspace_manager.create_workspace()

        with patch(
            "tools.agent.workspace_manager.get_workspace_manager",
            return_value=mock_workspace_manager,
        ):
            manager = SessionManager(persist=False)

            session = manager.get_session("telegram")
            session.workspace_path = workspace

            # Clear the session
            result = await manager.clear_session("telegram")

            assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# SDK Client Workspace Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDexAIClientWorkspace:
    """Tests for DexAIClient workspace handling."""

    def test_client_uses_working_dir_as_cwd(self, tmp_path: Path):
        """DexAIClient should use working_dir as SDK cwd parameter."""
        from tools.agent.sdk_client import DexAIClient

        workspace = tmp_path / "test_workspace"
        workspace.mkdir()

        client = DexAIClient(
            working_dir=str(workspace),
        )

        assert client.working_dir == str(workspace)

    def test_system_prompt_uses_workspace_root(self, tmp_path: Path):
        """System prompt should be built from workspace root files."""
        from tools.agent.sdk_client import build_system_prompt

        workspace = tmp_path / "test_workspace"
        workspace.mkdir()

        # Create a PERSONA.md in the workspace
        (workspace / "PERSONA.md").write_text("# Custom Persona\nI am a test agent.")

        config = {
            "system_prompt": {
                "base": "Base prompt.",
                "include_memory": False,
                "include_commitments": False,
                "include_energy": False,
            }
        }

        # Patch SystemPromptBuilder to use workspace
        with patch("tools.agent.client_factory.SystemPromptBuilder") as mock_builder_class:
            mock_builder = MagicMock()
            mock_builder.build.return_value = "Built prompt"
            mock_builder_class.return_value = mock_builder

            build_system_prompt(
                config=config,
                workspace_root=workspace,
            )

            # Builder should have been called with the workspace root
            mock_builder_class.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# End-to-End Workflow Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceWorkflows:
    """End-to-end workflow tests for workspace isolation."""

    @pytest.mark.asyncio
    async def test_complete_session_lifecycle(self, mock_workspace_manager, temp_workspace_base):
        """Test complete session lifecycle with workspace."""
        from tools.channels.session_manager import Session

        with patch(
            "tools.agent.workspace_manager.get_workspace_manager",
            return_value=mock_workspace_manager,
        ):
            # 1. Create session
            session = Session(channel="test")

            # 2. Initialize client (creates workspace)
            with patch("tools.agent.sdk_client.DexAIClient") as mock_dexai_client:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_dexai_client.return_value = mock_client

                await session._ensure_client()

            # 3. Verify workspace exists
            assert session.workspace_path is not None
            assert session.workspace_path.exists()
            workspace = session.workspace_path

            # 4. Serialize session
            data = session.to_dict()
            assert data["workspace_path"] == str(workspace)

            # 5. Close session
            await session.close()

            # 6. Workspace should still exist (permanent scope)
            assert workspace.exists()

            # 7. Verify can restore from serialized data
            restored = Session.from_dict(data)
            assert restored.workspace_path == workspace
