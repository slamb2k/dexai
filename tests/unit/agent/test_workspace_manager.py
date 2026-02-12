"""Tests for tools/agent/workspace_manager.py

The WorkspaceManager provides a single isolated workspace with:
- Workspace creation with bootstrap files
- Size limits and restrictions
- Session end marking

Single-tenant: One workspace for the owner (no per-user isolation).
"""

import json
import shutil
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
        patch(
            "tools.agent.system_prompt.BOOTSTRAP_FILES", ["PERSONA.md", "IDENTITY.md", "USER.md"]
        ),
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

    def test_create_workspace_creates_directory(self, workspace_manager):
        """Creating a workspace should create the directory."""
        workspace = workspace_manager.create_workspace()

        assert workspace.exists()
        assert workspace.is_dir()

    def test_create_workspace_creates_metadata(self, workspace_manager):
        """Creating a workspace should create metadata file."""
        workspace = workspace_manager.create_workspace()

        metadata_path = workspace / ".metadata.json"
        assert metadata_path.exists()

        metadata = json.loads(metadata_path.read_text())
        assert "created_at" in metadata
        assert "last_accessed" in metadata
        assert metadata["scope"] == "permanent"

    def test_create_workspace_copies_bootstrap_files(self, workspace_manager):
        """Creating a workspace should copy bootstrap files."""
        workspace = workspace_manager.create_workspace()

        # Check PERSONA.md was copied
        persona = workspace / "PERSONA.md"
        assert persona.exists()
        assert "Dex" in persona.read_text()

    def test_create_workspace_is_idempotent(self, workspace_manager):
        """Creating workspace twice should return same path."""
        workspace1 = workspace_manager.create_workspace()
        workspace2 = workspace_manager.create_workspace()

        assert workspace1 == workspace2


class TestWorkspaceRetrieval:
    """Tests for getting existing workspaces."""

    def test_get_workspace_returns_existing(self, workspace_manager):
        """Getting an existing workspace should return the same path."""
        created = workspace_manager.create_workspace()
        retrieved = workspace_manager.get_workspace()

        assert created == retrieved

    def test_get_workspace_creates_if_missing(self, workspace_manager):
        """Getting a non-existent workspace should create it."""
        workspace = workspace_manager.get_workspace()

        assert workspace.exists()
        assert workspace.is_dir()

    def test_get_workspace_updates_last_accessed(self, workspace_manager):
        """Getting a workspace should update last_accessed timestamp."""
        workspace = workspace_manager.create_workspace()

        # Read original metadata
        metadata_path = workspace / ".metadata.json"
        original = json.loads(metadata_path.read_text())
        original_time = original["last_accessed"]

        # Wait a tiny bit and get again
        import time

        time.sleep(0.01)

        workspace_manager.get_workspace()

        # Check timestamp updated
        updated = json.loads(metadata_path.read_text())
        assert updated["last_accessed"] >= original_time


class TestWorkspaceDeletion:
    """Tests for workspace deletion."""

    def test_delete_workspace_removes_directory(self, workspace_manager):
        """Deleting a workspace should remove the directory."""
        workspace = workspace_manager.create_workspace()
        assert workspace.exists()

        result = workspace_manager.delete_workspace()

        assert result is True
        assert not workspace.exists()

    def test_delete_nonexistent_workspace_returns_false(self, workspace_manager):
        """Deleting a non-existent workspace should return False."""
        # Don't create a workspace first - just try to delete
        # Need to ensure the workspace path doesn't exist
        if workspace_manager.workspace_path.exists():
            shutil.rmtree(workspace_manager.workspace_path)

        result = workspace_manager.delete_workspace()

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Scope
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceScope:
    """Tests for workspace scope (single-tenant always permanent)."""

    def test_default_scope_is_permanent(self, workspace_manager):
        """Default scope should be permanent for single-tenant."""
        workspace = workspace_manager.create_workspace()

        metadata_path = workspace / ".metadata.json"
        metadata = json.loads(metadata_path.read_text())

        assert metadata["scope"] == "permanent"


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Limits
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceLimits:
    """Tests for workspace size limits."""

    def test_check_limits_within_bounds(self, workspace_manager):
        """Workspace within limits should pass check."""
        workspace_manager.create_workspace()

        limits = workspace_manager.check_workspace_limits()

        assert limits["within_limits"] is True
        assert limits["current_size_bytes"] > 0  # Has bootstrap files
        assert limits["usage_percent"] < 100

    def test_get_workspace_size(self, workspace_manager):
        """Should correctly calculate workspace size."""
        workspace = workspace_manager.create_workspace()

        # Add a file
        test_file = workspace / "test.txt"
        test_file.write_text("Hello, World!")

        size = workspace_manager.get_workspace_size()

        assert size > 0
        # Size should include the test file
        assert size >= len("Hello, World!")


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Listing
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceListing:
    """Tests for listing workspaces."""

    def test_list_workspaces_returns_workspace(self, workspace_manager):
        """Should list the single workspace."""
        workspace_manager.create_workspace()

        workspaces = workspace_manager.list_workspaces()

        assert len(workspaces) == 1

    def test_list_workspaces_includes_metadata(self, workspace_manager):
        """Listed workspace should include metadata."""
        workspace_manager.create_workspace()

        workspaces = workspace_manager.list_workspaces()

        assert len(workspaces) == 1
        ws = workspaces[0]
        assert "scope" in ws
        assert "size_bytes" in ws
        assert "created_at" in ws

    def test_list_workspaces_empty_when_none(self, workspace_manager):
        """Should return empty list when no workspace exists."""
        # Ensure no workspace
        if workspace_manager.workspace_path.exists():
            shutil.rmtree(workspace_manager.workspace_path)

        workspaces = workspace_manager.list_workspaces()
        assert len(workspaces) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Session End Marking
# ─────────────────────────────────────────────────────────────────────────────


class TestSessionEndMarking:
    """Tests for session end behavior."""

    def test_mark_session_end_updates_metadata(self, workspace_manager):
        """Marking session end should update workspace metadata."""
        workspace = workspace_manager.create_workspace()

        result = workspace_manager.mark_session_end()

        assert result is True
        assert workspace.exists()  # Permanent workspace not deleted

        # Check session_ended_at was added
        metadata_path = workspace / ".metadata.json"
        metadata = json.loads(metadata_path.read_text())
        assert "session_ended_at" in metadata

    def test_mark_session_end_with_channel(self, workspace_manager):
        """Marking session end with channel for logging."""
        workspace_manager.create_workspace()

        result = workspace_manager.mark_session_end(channel="telegram")

        assert result is True


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
        workspace = manager.get_workspace()

        assert workspace == PROJECT_ROOT
