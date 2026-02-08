"""Tests for tools/agent/workspace_manager.py

The WorkspaceManager provides per-user isolated workspaces with:
- Workspace creation with bootstrap files
- Scope-based lifecycle (SESSION, PERSISTENT, PERMANENT)
- Access control (RO, RW, NONE)
- Size limits and restrictions
- Stale workspace cleanup

These tests ensure workspace isolation works correctly.
"""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

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
    (templates / "USER.md").write_text("# User\n{{user_name}}")

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
                    "cleanup_on_startup": False,  # Disable for tests
                },
            },
            "templates": {
                "path": str(temp_templates_dir),
                "bootstrap_files": ["PERSONA.md", "IDENTITY.md", "USER.md"],
            },
            "access": {
                "default": "rw",
            },
            "restrictions": {
                "max_file_size_bytes": 1048576,  # 1MB
                "max_workspace_size_bytes": 10485760,  # 10MB
                "blocked_extensions": [".exe", ".dll"],
            },
        }
    }


@pytest.fixture
def workspace_manager(workspace_config: dict, temp_workspace_base: Path, temp_templates_dir: Path):
    """Create a WorkspaceManager with test configuration."""
    # Patch bootstrap files constant
    with (
        patch("tools.agent.system_prompt.TEMPLATES_PATH", temp_templates_dir),
        patch("tools.agent.system_prompt.BOOTSTRAP_FILES", ["PERSONA.md", "IDENTITY.md", "USER.md"]),
    ):
        from tools.agent.workspace_manager import WorkspaceManager

        manager = WorkspaceManager(config=workspace_config)
        yield manager

        # Cleanup: remove all workspaces
        if temp_workspace_base.exists():
            shutil.rmtree(temp_workspace_base)


# ─────────────────────────────────────────────────────────────────────────────
# Basic Workspace Operations
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceCreation:
    """Tests for workspace creation."""

    def test_create_workspace_creates_directory(self, workspace_manager, temp_workspace_base):
        """Creating a workspace should create the directory."""
        workspace = workspace_manager.create_workspace("alice", "telegram")

        assert workspace.exists()
        assert workspace.is_dir()
        assert workspace.parent == temp_workspace_base

    def test_create_workspace_creates_metadata(self, workspace_manager):
        """Creating a workspace should create metadata file."""
        workspace = workspace_manager.create_workspace("bob", "discord")

        metadata_path = workspace / ".metadata.json"
        assert metadata_path.exists()

        metadata = json.loads(metadata_path.read_text())
        assert metadata["user_id"] == "bob"
        assert metadata["channel"] == "discord"
        assert "created_at" in metadata
        assert "last_accessed" in metadata

    def test_create_workspace_copies_bootstrap_files(self, workspace_manager, temp_templates_dir):
        """Creating a workspace should copy bootstrap files."""
        workspace = workspace_manager.create_workspace("charlie", "slack")

        # Check PERSONA.md was copied
        persona = workspace / "PERSONA.md"
        assert persona.exists()
        assert "Dex" in persona.read_text()

    def test_workspace_key_sanitization(self, workspace_manager, temp_workspace_base):
        """Workspace keys should be filesystem-safe."""
        # Test with special characters
        workspace = workspace_manager.create_workspace("alice@example.com", "telegram:123")

        # The directory should exist and be safely named
        assert workspace.exists()
        assert "@" not in workspace.name or ":" not in workspace.name


class TestWorkspaceRetrieval:
    """Tests for getting existing workspaces."""

    def test_get_workspace_returns_existing(self, workspace_manager):
        """Getting an existing workspace should return the same path."""
        created = workspace_manager.create_workspace("alice", "telegram")
        retrieved = workspace_manager.get_workspace("alice", "telegram")

        assert created == retrieved

    def test_get_workspace_creates_if_missing(self, workspace_manager):
        """Getting a non-existent workspace should create it."""
        workspace = workspace_manager.get_workspace("newuser", "cli")

        assert workspace.exists()
        assert workspace.is_dir()

    def test_get_workspace_updates_last_accessed(self, workspace_manager):
        """Getting a workspace should update last_accessed timestamp."""
        workspace = workspace_manager.create_workspace("alice", "telegram")

        # Read original metadata
        metadata_path = workspace / ".metadata.json"
        original = json.loads(metadata_path.read_text())
        original_time = original["last_accessed"]

        # Wait a tiny bit and get again
        import time
        time.sleep(0.01)

        workspace_manager.get_workspace("alice", "telegram")

        # Check timestamp updated
        updated = json.loads(metadata_path.read_text())
        assert updated["last_accessed"] >= original_time


class TestWorkspaceDeletion:
    """Tests for workspace deletion."""

    def test_delete_workspace_removes_directory(self, workspace_manager):
        """Deleting a workspace should remove the directory."""
        workspace = workspace_manager.create_workspace("alice", "telegram")
        assert workspace.exists()

        result = workspace_manager.delete_workspace("alice", "telegram")

        assert result is True
        assert not workspace.exists()

    def test_delete_nonexistent_workspace_returns_false(self, workspace_manager):
        """Deleting a non-existent workspace should return False."""
        result = workspace_manager.delete_workspace("nobody", "nowhere")

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Scopes
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceScopes:
    """Tests for workspace scope handling."""

    def test_default_scope_is_persistent(self, workspace_manager):
        """Default scope should be persistent."""
        workspace = workspace_manager.create_workspace("alice", "telegram")

        metadata_path = workspace / ".metadata.json"
        metadata = json.loads(metadata_path.read_text())

        assert metadata["scope"] == "persistent"

    def test_session_scope_can_be_specified(self, workspace_manager):
        """Session scope should be settable."""
        from tools.agent.workspace_manager import WorkspaceScope

        workspace = workspace_manager.create_workspace(
            "bob", "discord", scope=WorkspaceScope.SESSION
        )

        metadata_path = workspace / ".metadata.json"
        metadata = json.loads(metadata_path.read_text())

        assert metadata["scope"] == "session"

    def test_permanent_scope_can_be_specified(self, workspace_manager):
        """Permanent scope should be settable."""
        from tools.agent.workspace_manager import WorkspaceScope

        workspace = workspace_manager.create_workspace(
            "charlie", "slack", scope=WorkspaceScope.PERMANENT
        )

        metadata_path = workspace / ".metadata.json"
        metadata = json.loads(metadata_path.read_text())

        assert metadata["scope"] == "permanent"


# ─────────────────────────────────────────────────────────────────────────────
# Stale Workspace Cleanup
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceCleanup:
    """Tests for stale workspace cleanup."""

    def test_cleanup_removes_session_workspaces(self, workspace_manager):
        """Cleanup should remove session-scoped workspaces."""
        from tools.agent.workspace_manager import WorkspaceScope

        # Create a session workspace
        workspace = workspace_manager.create_workspace(
            "alice", "telegram", scope=WorkspaceScope.SESSION
        )
        assert workspace.exists()

        # Run cleanup
        cleaned = workspace_manager.cleanup_stale_workspaces()

        # Session workspaces are always cleaned
        assert cleaned == 1
        assert not workspace.exists()

    def test_cleanup_preserves_permanent_workspaces(self, workspace_manager):
        """Cleanup should never remove permanent workspaces."""
        from tools.agent.workspace_manager import WorkspaceScope

        workspace = workspace_manager.create_workspace(
            "admin", "cli", scope=WorkspaceScope.PERMANENT
        )

        # Run cleanup
        cleaned = workspace_manager.cleanup_stale_workspaces()

        assert cleaned == 0
        assert workspace.exists()

    def test_cleanup_removes_stale_persistent_workspaces(self, workspace_manager):
        """Cleanup should remove persistent workspaces older than stale_days."""
        from tools.agent.workspace_manager import WorkspaceScope

        workspace = workspace_manager.create_workspace(
            "alice", "telegram", scope=WorkspaceScope.PERSISTENT
        )

        # Manually set last_accessed to 60 days ago
        metadata_path = workspace / ".metadata.json"
        metadata = json.loads(metadata_path.read_text())
        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        metadata["last_accessed"] = old_date
        metadata_path.write_text(json.dumps(metadata))

        # Run cleanup
        cleaned = workspace_manager.cleanup_stale_workspaces()

        assert cleaned == 1
        assert not workspace.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Limits
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceLimits:
    """Tests for workspace size limits."""

    def test_check_limits_within_bounds(self, workspace_manager):
        """Workspace within limits should pass check."""
        workspace_manager.create_workspace("alice", "telegram")

        limits = workspace_manager.check_workspace_limits("alice", "telegram")

        assert limits["within_limits"] is True
        assert limits["current_size_bytes"] > 0  # Has bootstrap files
        assert limits["usage_percent"] < 100

    def test_get_workspace_size(self, workspace_manager):
        """Should correctly calculate workspace size."""
        workspace = workspace_manager.create_workspace("alice", "telegram")

        # Add a file
        test_file = workspace / "test.txt"
        test_file.write_text("Hello, World!")

        size = workspace_manager.get_workspace_size("alice", "telegram")

        assert size > 0
        # Size should include the test file
        assert size >= len("Hello, World!")


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Listing
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceListing:
    """Tests for listing workspaces."""

    def test_list_workspaces_returns_all(self, workspace_manager):
        """Should list all created workspaces."""
        workspace_manager.create_workspace("alice", "telegram")
        workspace_manager.create_workspace("bob", "discord")
        workspace_manager.create_workspace("charlie", "slack")

        workspaces = workspace_manager.list_workspaces()

        assert len(workspaces) == 3
        users = {w["user_id"] for w in workspaces}
        assert users == {"alice", "bob", "charlie"}

    def test_list_workspaces_includes_metadata(self, workspace_manager):
        """Listed workspaces should include metadata."""
        workspace_manager.create_workspace("alice", "telegram")

        workspaces = workspace_manager.list_workspaces()

        assert len(workspaces) == 1
        ws = workspaces[0]
        assert "user_id" in ws
        assert "channel" in ws
        assert "scope" in ws
        assert "size_bytes" in ws
        assert "created_at" in ws


# ─────────────────────────────────────────────────────────────────────────────
# Session End Marking
# ─────────────────────────────────────────────────────────────────────────────


class TestSessionEndMarking:
    """Tests for session end behavior."""

    def test_mark_session_end_deletes_session_workspace(self, workspace_manager):
        """Marking session end should delete SESSION scoped workspaces."""
        from tools.agent.workspace_manager import WorkspaceScope

        workspace = workspace_manager.create_workspace(
            "alice", "telegram", scope=WorkspaceScope.SESSION
        )
        assert workspace.exists()

        result = workspace_manager.mark_session_end("alice", "telegram")

        assert result is True
        assert not workspace.exists()

    def test_mark_session_end_updates_persistent_workspace(self, workspace_manager):
        """Marking session end should update persistent workspace metadata."""
        from tools.agent.workspace_manager import WorkspaceScope

        workspace = workspace_manager.create_workspace(
            "bob", "discord", scope=WorkspaceScope.PERSISTENT
        )

        result = workspace_manager.mark_session_end("bob", "discord")

        assert result is True
        assert workspace.exists()  # Not deleted

        # Check session_ended_at was added
        metadata_path = workspace / ".metadata.json"
        metadata = json.loads(metadata_path.read_text())
        assert "session_ended_at" in metadata


# ─────────────────────────────────────────────────────────────────────────────
# Disabled Workspaces
# ─────────────────────────────────────────────────────────────────────────────


class TestDisabledWorkspaces:
    """Tests for when workspace isolation is disabled."""

    def test_disabled_returns_project_root(self, temp_workspace_base):
        """When disabled, get_workspace should return PROJECT_ROOT."""
        config = {
            "workspace": {
                "enabled": False,
                "base_path": str(temp_workspace_base),
            }
        }

        from tools.agent.workspace_manager import PROJECT_ROOT, WorkspaceManager

        manager = WorkspaceManager(config=config)
        workspace = manager.get_workspace("alice", "telegram")

        assert workspace == PROJECT_ROOT
