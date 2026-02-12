"""
Workspace Manager for DexAI

Manages per-user isolated workspaces for DexAI sessions.

Each user gets a dedicated workspace directory with bootstrap files
(PERSONA.md, IDENTITY.md, etc.) that define agent context. The SDK's
`cwd` parameter provides isolation, with existing security hooks enforcing boundaries.

Security Model (Defense in Depth):
- Layer 1: SDK Sandbox - Container isolation, cwd enforcement
- Layer 2: PreToolUse Hooks - Block dangerous bash, protected paths
- Layer 3: RBAC System - Tool permissions per user role
- Layer 4: Workspace Isolation - Per-user directories, scope policies

Usage:
    from tools.agent.workspace_manager import WorkspaceManager, WorkspaceScope

    # Get or create a workspace
    manager = WorkspaceManager()
    workspace = manager.get_workspace(user_id="alice", channel="telegram")

    # Create with specific scope
    workspace = manager.create_workspace(
        user_id="alice",
        channel="telegram",
        scope=WorkspaceScope.SESSION,  # Ephemeral
    )

    # Cleanup stale workspaces
    cleaned = manager.cleanup_stale_workspaces()
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml

from tools.agent import PROJECT_ROOT, DATA_DIR, ARGS_DIR
from tools.agent.system_prompt import bootstrap_workspace as _bootstrap_files, BOOTSTRAP_FILES

logger = logging.getLogger(__name__)

# Configuration path
CONFIG_PATH = ARGS_DIR / "workspace.yaml"

# Single workspace path (single-tenant: one workspace for the owner)
DEFAULT_WORKSPACE_PATH = DATA_DIR / "workspace"


class WorkspaceScope(Enum):
    """
    Workspace lifecycle scope.

    Determines when workspace is automatically cleaned up.
    """

    SESSION = "session"  # Deleted on session end
    PERSISTENT = "persistent"  # Default, deleted after stale_days
    PERMANENT = "permanent"  # Never auto-deleted


class WorkspaceAccess(Enum):
    """
    Workspace access level.

    Controls what operations are allowed in the workspace.
    """

    NONE = "none"  # No access (disabled)
    RO = "ro"  # Read-only
    RW = "rw"  # Read-write (default)


# Default configuration
DEFAULT_CONFIG = {
    "workspace": {
        "enabled": True,
        "base_path": "data/workspaces",
        "scope": {
            "default": "persistent",
            "cleanup": {
                "stale_days": 30,
                "cleanup_on_startup": True,
            },
        },
        "templates": {
            "path": "docs/templates",
            "bootstrap_files": BOOTSTRAP_FILES,
        },
        "access": {
            "default": "rw",
        },
        "restrictions": {
            "max_file_size_bytes": 10485760,  # 10MB
            "max_workspace_size_bytes": 104857600,  # 100MB
            "blocked_extensions": [".exe", ".dll", ".so", ".dylib"],
        },
    }
}


def load_config() -> dict:
    """Load workspace configuration from YAML file."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                config = yaml.safe_load(f) or {}
                return config
        except Exception as e:
            logger.warning(f"Failed to load workspace config: {e}")
    return DEFAULT_CONFIG


class WorkspaceManager:
    """
    Manages per-user isolated workspaces.

    Provides:
    - Workspace creation with bootstrap files
    - Workspace lifecycle management (scope-based cleanup)
    - Metadata tracking (timestamps, access, scope)
    - Size enforcement and restrictions
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize workspace manager.

        Single-tenant: manages a single shared workspace directory.

        Args:
            config: Optional config override (default: load from file)
        """
        self.config = config or load_config()
        self._workspace_config = self.config.get("workspace", DEFAULT_CONFIG["workspace"])

        # Single workspace path — use config base_path if provided, otherwise default
        base_path = self._workspace_config.get("base_path")
        if base_path:
            self.workspace_path = Path(base_path) / "workspace"
        else:
            self.workspace_path = DEFAULT_WORKSPACE_PATH

        # Ensure workspace directory exists
        self.workspace_path.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        """Check if workspace isolation is enabled."""
        return self._workspace_config.get("enabled", True)

    def _metadata_path(self) -> Path:
        """Get metadata file path for the workspace."""
        return self.workspace_path / ".metadata.json"

    def _read_metadata(self) -> dict:
        """Read workspace metadata."""
        metadata_path = self._metadata_path()
        if metadata_path.exists():
            try:
                with open(metadata_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _write_metadata(self, metadata: dict) -> None:
        """Write workspace metadata."""
        metadata_path = self._metadata_path()
        try:
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to write metadata: {e}")

    def get_workspace(self, **kwargs) -> Path:
        """
        Get or create the single workspace.

        Returns:
            Path to workspace directory
        """
        if not self.enabled:
            return PROJECT_ROOT

        if self.workspace_path.exists() and (self.workspace_path / ".metadata.json").exists():
            # Update last accessed time
            metadata = self._read_metadata()
            metadata["last_accessed"] = datetime.now().isoformat()
            self._write_metadata(metadata)
            return self.workspace_path

        # Bootstrap workspace
        return self.create_workspace()

    def create_workspace(self, **kwargs) -> Path:
        """
        Create or bootstrap the single workspace with template files.

        Returns:
            Path to workspace directory
        """
        self.workspace_path.mkdir(parents=True, exist_ok=True)

        # Bootstrap with template files
        bootstrap_result = _bootstrap_files(self.workspace_path)
        if not bootstrap_result.get("success"):
            logger.warning(f"Bootstrap partially failed: {bootstrap_result.get('errors', [])}")

        # Populate workspace files with existing user.yaml values
        self._populate_from_user_yaml(self.workspace_path)

        # Write metadata
        metadata = {
            "scope": "permanent",
            "access": "rw",
            "created_at": datetime.now().isoformat(),
            "last_accessed": datetime.now().isoformat(),
            "bootstrap_files": bootstrap_result.get("created", []),
        }
        self._write_metadata(metadata)

        logger.info(f"Created workspace at {self.workspace_path}")
        return self.workspace_path

    def _populate_from_user_yaml(self, workspace_path: Path) -> None:
        """Populate workspace files with existing values from args/user.yaml.

        Called after bootstrap so that workspaces created *after* onboarding
        already contain the user's name, timezone, and ADHD context.
        """
        try:
            from tools.setup.wizard import populate_workspace_files

            user_yaml_path = ARGS_DIR / "user.yaml"
            if not user_yaml_path.exists():
                return

            with open(user_yaml_path) as f:
                data = yaml.safe_load(f) or {}

            field_values = {
                "user_name": data.get("user", {}).get("name"),
                "timezone": data.get("user", {}).get("timezone"),
                "energy_pattern": data.get("preferences", {}).get("energy_pattern"),
                "adhd_challenges": data.get("preferences", {}).get("adhd_challenges"),
                "work_focus_areas": data.get("preferences", {}).get("work_focus_areas"),
            }

            for field, value in field_values.items():
                if value:
                    display = ", ".join(value) if isinstance(value, list) else str(value)
                    populate_workspace_files(workspace_path, field, display)
        except Exception as e:
            logger.warning(f"Could not populate workspace from user.yaml: {e}")

    def delete_workspace(self) -> bool:
        """
        Delete the workspace.

        Returns:
            True if deleted, False if not found
        """
        if not self.workspace_path.exists():
            return False

        try:
            shutil.rmtree(self.workspace_path)
            logger.info(f"Deleted workspace at {self.workspace_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete workspace: {e}")
            return False

    def get_workspace_size(self) -> int:
        """
        Get the total size of the workspace in bytes.

        Returns:
            Size in bytes, or 0 if not found
        """
        if not self.workspace_path.exists():
            return 0

        return sum(f.stat().st_size for f in self.workspace_path.rglob("*") if f.is_file())

    def check_workspace_limits(self) -> dict[str, Any]:
        """
        Check if workspace is within size limits.

        Returns:
            Dict with 'within_limits', 'current_size', 'max_size'
        """
        restrictions = self._workspace_config.get("restrictions", {})
        max_size = restrictions.get("max_workspace_size_bytes", 104857600)

        current_size = self.get_workspace_size()

        return {
            "within_limits": current_size < max_size,
            "current_size_bytes": current_size,
            "max_size_bytes": max_size,
            "usage_percent": (current_size / max_size * 100) if max_size > 0 else 0,
        }

    def list_workspaces(self) -> list[dict]:
        """
        List the workspace with metadata.

        Returns:
            List with single workspace info dict (or empty if not created)
        """
        if not self.workspace_path.exists():
            return []

        metadata = self._read_metadata()
        size_bytes = self.get_workspace_size()

        return [{
            "path": str(self.workspace_path),
            "name": self.workspace_path.name,
            "scope": metadata.get("scope", "permanent"),
            "access": metadata.get("access", "rw"),
            "created_at": metadata.get("created_at"),
            "last_accessed": metadata.get("last_accessed"),
            "size_bytes": size_bytes,
            "bootstrap_files": metadata.get("bootstrap_files", []),
        }]

    def mark_session_end(self, channel: str = "") -> bool:
        """
        Mark a session as ended.

        Updates last accessed time on the workspace.

        Args:
            channel: Communication channel (for logging)

        Returns:
            True if updated
        """
        if not self.workspace_path.exists():
            return False

        metadata = self._read_metadata()
        metadata["last_accessed"] = datetime.now().isoformat()
        metadata["session_ended_at"] = datetime.now().isoformat()
        self._write_metadata(metadata)
        return True


# =============================================================================
# Global Instance
# =============================================================================

_manager: Optional[WorkspaceManager] = None


def get_workspace_manager() -> WorkspaceManager:
    """
    Get the global workspace manager instance.

    Returns:
        WorkspaceManager singleton
    """
    global _manager
    if _manager is None:
        _manager = WorkspaceManager()
    return _manager


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing workspace manager."""
    import argparse

    parser = argparse.ArgumentParser(description="Workspace Manager")
    parser.add_argument("--list", action="store_true", help="List workspace")
    parser.add_argument("--create", action="store_true", help="Create/bootstrap workspace")
    parser.add_argument("--delete", action="store_true", help="Delete workspace")
    parser.add_argument("--check", action="store_true", help="Check workspace limits")
    parser.add_argument("--test", action="store_true", help="Run self-test")

    args = parser.parse_args()
    manager = get_workspace_manager()

    if args.list:
        workspaces = manager.list_workspaces()
        if workspaces:
            ws = workspaces[0]
            size_mb = ws["size_bytes"] / (1024 * 1024)
            print(f"Workspace: {ws['name']}")
            print(f"  Scope: {ws['scope']}, Access: {ws['access']}")
            print(f"  Size: {size_mb:.2f} MB")
            print(f"  Created: {ws['created_at']}")
            print(f"  Last accessed: {ws['last_accessed']}")
        else:
            print("No workspace found.")

    elif args.create:
        workspace = manager.create_workspace()
        print(f"Created workspace: {workspace}")

    elif args.delete:
        if manager.delete_workspace():
            print("Deleted workspace")
        else:
            print("Workspace not found")

    elif args.check:
        limits = manager.check_workspace_limits()
        print(f"Workspace limits:")
        print(f"  Within limits: {limits['within_limits']}")
        print(f"  Current size: {limits['current_size_bytes'] / (1024 * 1024):.2f} MB")
        print(f"  Max size: {limits['max_size_bytes'] / (1024 * 1024):.2f} MB")
        print(f"  Usage: {limits['usage_percent']:.1f}%")

    elif args.test:
        print("Running self-test...")

        workspace = manager.create_workspace()
        print(f"  Created: {workspace}")
        assert workspace.exists(), "Workspace should exist"

        same_workspace = manager.get_workspace()
        assert same_workspace == workspace, "get_workspace should return existing"
        print("  Get returned same workspace")

        workspaces = manager.list_workspaces()
        assert len(workspaces) == 1, "Should have one workspace"
        print(f"  Listed {len(workspaces)} workspaces")

        limits = manager.check_workspace_limits()
        assert limits["within_limits"], "Should be within limits"
        print("  Limits check passed")

        print("\nAll tests passed!")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
