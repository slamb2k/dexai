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

# Default workspace base path
DEFAULT_BASE_PATH = DATA_DIR / "workspaces"


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

        Args:
            config: Optional config override (default: load from file)
        """
        self.config = config or load_config()
        self._workspace_config = self.config.get("workspace", DEFAULT_CONFIG["workspace"])

        # Resolve base path
        base_path_str = self._workspace_config.get("base_path", "data/workspaces")
        if not Path(base_path_str).is_absolute():
            self.base_path = PROJECT_ROOT / base_path_str
        else:
            self.base_path = Path(base_path_str)

        # Ensure base directory exists
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Run startup cleanup if configured
        if self._workspace_config.get("scope", {}).get("cleanup", {}).get("cleanup_on_startup", True):
            try:
                self.cleanup_stale_workspaces()
            except Exception as e:
                logger.warning(f"Startup cleanup failed: {e}")

    @property
    def enabled(self) -> bool:
        """Check if workspace isolation is enabled."""
        return self._workspace_config.get("enabled", True)

    def _workspace_key(self, user_id: str, channel: str) -> str:
        """
        Generate workspace directory name from user and channel.

        Args:
            user_id: User identifier
            channel: Communication channel

        Returns:
            Safe directory name
        """
        # Sanitize for filesystem safety
        safe_user = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
        safe_channel = "".join(c if c.isalnum() or c in "-_" else "_" for c in channel)
        return f"{safe_user}_{safe_channel}"

    def _metadata_path(self, workspace: Path) -> Path:
        """Get metadata file path for a workspace."""
        return workspace / ".metadata.json"

    def _read_metadata(self, workspace: Path) -> dict:
        """Read workspace metadata."""
        metadata_path = self._metadata_path(workspace)
        if metadata_path.exists():
            try:
                with open(metadata_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _write_metadata(self, workspace: Path, metadata: dict) -> None:
        """Write workspace metadata."""
        metadata_path = self._metadata_path(workspace)
        try:
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to write metadata: {e}")

    def get_workspace(
        self,
        user_id: str,
        channel: str,
        scope: Optional[WorkspaceScope] = None,
        access: Optional[WorkspaceAccess] = None,
    ) -> Path:
        """
        Get or create a workspace for a user.

        If the workspace exists, returns it (updating last_accessed).
        If not, creates a new workspace with bootstrap files.

        Args:
            user_id: User identifier
            channel: Communication channel
            scope: Workspace scope (default from config)
            access: Access level (default from config)

        Returns:
            Path to workspace directory
        """
        if not self.enabled:
            # Return project root if workspaces disabled
            return PROJECT_ROOT

        workspace_key = self._workspace_key(user_id, channel)
        workspace_path = self.base_path / workspace_key

        if workspace_path.exists():
            # Update last accessed time
            metadata = self._read_metadata(workspace_path)
            metadata["last_accessed"] = datetime.now().isoformat()
            self._write_metadata(workspace_path, metadata)
            return workspace_path

        # Create new workspace
        return self.create_workspace(user_id, channel, scope, access)

    def create_workspace(
        self,
        user_id: str,
        channel: str,
        scope: Optional[WorkspaceScope] = None,
        access: Optional[WorkspaceAccess] = None,
    ) -> Path:
        """
        Create a new workspace with bootstrap files.

        Args:
            user_id: User identifier
            channel: Communication channel
            scope: Workspace scope (default from config)
            access: Access level (default from config)

        Returns:
            Path to created workspace directory
        """
        workspace_key = self._workspace_key(user_id, channel)
        workspace_path = self.base_path / workspace_key

        # Determine scope and access
        if scope is None:
            scope_str = self._workspace_config.get("scope", {}).get("default", "persistent")
            scope = WorkspaceScope(scope_str)

        if access is None:
            access_str = self._workspace_config.get("access", {}).get("default", "rw")
            access = WorkspaceAccess(access_str)

        # Create workspace directory
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Bootstrap with template files
        bootstrap_result = _bootstrap_files(workspace_path)
        if not bootstrap_result.get("success"):
            logger.warning(f"Bootstrap partially failed: {bootstrap_result.get('errors', [])}")

        # Write metadata
        metadata = {
            "user_id": user_id,
            "channel": channel,
            "scope": scope.value,
            "access": access.value,
            "created_at": datetime.now().isoformat(),
            "last_accessed": datetime.now().isoformat(),
            "bootstrap_files": bootstrap_result.get("created", []),
        }
        self._write_metadata(workspace_path, metadata)

        logger.info(f"Created workspace for {user_id}:{channel} at {workspace_path}")
        return workspace_path

    def delete_workspace(self, user_id: str, channel: str) -> bool:
        """
        Delete a workspace.

        Args:
            user_id: User identifier
            channel: Communication channel

        Returns:
            True if deleted, False if not found
        """
        workspace_key = self._workspace_key(user_id, channel)
        workspace_path = self.base_path / workspace_key

        if not workspace_path.exists():
            return False

        try:
            shutil.rmtree(workspace_path)
            logger.info(f"Deleted workspace for {user_id}:{channel}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete workspace: {e}")
            return False

    def cleanup_stale_workspaces(self) -> int:
        """
        Clean up stale workspaces based on scope and age.

        - SESSION scoped workspaces are always deleted
        - PERSISTENT workspaces are deleted after stale_days
        - PERMANENT workspaces are never deleted

        Returns:
            Number of workspaces cleaned up
        """
        stale_days = self._workspace_config.get("scope", {}).get("cleanup", {}).get("stale_days", 30)
        stale_threshold = datetime.now() - timedelta(days=stale_days)
        cleaned = 0

        if not self.base_path.exists():
            return 0

        for workspace_dir in self.base_path.iterdir():
            if not workspace_dir.is_dir():
                continue

            metadata = self._read_metadata(workspace_dir)
            scope = metadata.get("scope", "persistent")

            # Check if should be cleaned
            should_clean = False

            if scope == WorkspaceScope.SESSION.value:
                # Session scoped - always clean
                should_clean = True
            elif scope == WorkspaceScope.PERSISTENT.value:
                # Check age
                last_accessed = metadata.get("last_accessed")
                if last_accessed:
                    try:
                        last_dt = datetime.fromisoformat(last_accessed)
                        if last_dt < stale_threshold:
                            should_clean = True
                    except ValueError:
                        pass
            # PERMANENT scope - never clean

            if should_clean:
                try:
                    shutil.rmtree(workspace_dir)
                    cleaned += 1
                    logger.info(f"Cleaned stale workspace: {workspace_dir.name}")
                except Exception as e:
                    logger.warning(f"Failed to clean workspace {workspace_dir.name}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} stale workspaces")

        return cleaned

    def list_workspaces(self) -> list[dict]:
        """
        List all workspaces with metadata.

        Returns:
            List of workspace info dicts
        """
        workspaces = []

        if not self.base_path.exists():
            return workspaces

        for workspace_dir in self.base_path.iterdir():
            if not workspace_dir.is_dir():
                continue

            metadata = self._read_metadata(workspace_dir)

            # Calculate size
            size_bytes = sum(
                f.stat().st_size for f in workspace_dir.rglob("*") if f.is_file()
            )

            workspaces.append({
                "path": str(workspace_dir),
                "name": workspace_dir.name,
                "user_id": metadata.get("user_id", "unknown"),
                "channel": metadata.get("channel", "unknown"),
                "scope": metadata.get("scope", "persistent"),
                "access": metadata.get("access", "rw"),
                "created_at": metadata.get("created_at"),
                "last_accessed": metadata.get("last_accessed"),
                "size_bytes": size_bytes,
                "bootstrap_files": metadata.get("bootstrap_files", []),
            })

        return sorted(workspaces, key=lambda w: w.get("last_accessed") or "", reverse=True)

    def get_workspace_size(self, user_id: str, channel: str) -> int:
        """
        Get the total size of a workspace in bytes.

        Args:
            user_id: User identifier
            channel: Communication channel

        Returns:
            Size in bytes, or 0 if not found
        """
        workspace_key = self._workspace_key(user_id, channel)
        workspace_path = self.base_path / workspace_key

        if not workspace_path.exists():
            return 0

        return sum(f.stat().st_size for f in workspace_path.rglob("*") if f.is_file())

    def check_workspace_limits(self, user_id: str, channel: str) -> dict[str, Any]:
        """
        Check if workspace is within size limits.

        Args:
            user_id: User identifier
            channel: Communication channel

        Returns:
            Dict with 'within_limits', 'current_size', 'max_size'
        """
        restrictions = self._workspace_config.get("restrictions", {})
        max_size = restrictions.get("max_workspace_size_bytes", 104857600)

        current_size = self.get_workspace_size(user_id, channel)

        return {
            "within_limits": current_size < max_size,
            "current_size_bytes": current_size,
            "max_size_bytes": max_size,
            "usage_percent": (current_size / max_size * 100) if max_size > 0 else 0,
        }

    def mark_session_end(self, user_id: str, channel: str) -> bool:
        """
        Mark a session as ended (for SESSION scoped workspaces).

        If the workspace has SESSION scope, schedules it for cleanup.

        Args:
            user_id: User identifier
            channel: Communication channel

        Returns:
            True if marked/cleaned, False if not applicable
        """
        workspace_key = self._workspace_key(user_id, channel)
        workspace_path = self.base_path / workspace_key

        if not workspace_path.exists():
            return False

        metadata = self._read_metadata(workspace_path)
        scope = metadata.get("scope", "persistent")

        if scope == WorkspaceScope.SESSION.value:
            # Clean up session workspace immediately
            return self.delete_workspace(user_id, channel)

        # Update last accessed for non-session workspaces
        metadata["last_accessed"] = datetime.now().isoformat()
        metadata["session_ended_at"] = datetime.now().isoformat()
        self._write_metadata(workspace_path, metadata)
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
    parser.add_argument("--list", action="store_true", help="List all workspaces")
    parser.add_argument("--create", nargs=2, metavar=("USER", "CHANNEL"), help="Create workspace")
    parser.add_argument("--delete", nargs=2, metavar=("USER", "CHANNEL"), help="Delete workspace")
    parser.add_argument("--cleanup", action="store_true", help="Cleanup stale workspaces")
    parser.add_argument("--scope", choices=["session", "persistent", "permanent"],
                        help="Scope for new workspace")
    parser.add_argument("--test", action="store_true", help="Run self-test")
    parser.add_argument("--check", nargs=2, metavar=("USER", "CHANNEL"),
                        help="Check workspace limits")

    args = parser.parse_args()
    manager = get_workspace_manager()

    if args.list:
        workspaces = manager.list_workspaces()
        if workspaces:
            print(f"Found {len(workspaces)} workspaces:\n")
            for ws in workspaces:
                size_mb = ws["size_bytes"] / (1024 * 1024)
                print(f"  {ws['name']}:")
                print(f"    User: {ws['user_id']}, Channel: {ws['channel']}")
                print(f"    Scope: {ws['scope']}, Access: {ws['access']}")
                print(f"    Size: {size_mb:.2f} MB")
                print(f"    Created: {ws['created_at']}")
                print(f"    Last accessed: {ws['last_accessed']}")
                print()
        else:
            print("No workspaces found.")

    elif args.create:
        user_id, channel = args.create
        scope = WorkspaceScope(args.scope) if args.scope else None
        workspace = manager.create_workspace(user_id, channel, scope)
        print(f"Created workspace: {workspace}")

    elif args.delete:
        user_id, channel = args.delete
        if manager.delete_workspace(user_id, channel):
            print(f"Deleted workspace for {user_id}:{channel}")
        else:
            print(f"Workspace not found for {user_id}:{channel}")

    elif args.cleanup:
        cleaned = manager.cleanup_stale_workspaces()
        print(f"Cleaned {cleaned} stale workspaces")

    elif args.check:
        user_id, channel = args.check
        limits = manager.check_workspace_limits(user_id, channel)
        print(f"Workspace limits for {user_id}:{channel}:")
        print(f"  Within limits: {limits['within_limits']}")
        print(f"  Current size: {limits['current_size_bytes'] / (1024 * 1024):.2f} MB")
        print(f"  Max size: {limits['max_size_bytes'] / (1024 * 1024):.2f} MB")
        print(f"  Usage: {limits['usage_percent']:.1f}%")

    elif args.test:
        print("Running self-test...")

        # Test create
        test_user = "test_user"
        test_channel = "test_cli"
        workspace = manager.create_workspace(test_user, test_channel, WorkspaceScope.SESSION)
        print(f"  Created: {workspace}")
        assert workspace.exists(), "Workspace should exist"

        # Test get (should return same path)
        same_workspace = manager.get_workspace(test_user, test_channel)
        assert same_workspace == workspace, "get_workspace should return existing"
        print("  Get returned same workspace")

        # Test list
        workspaces = manager.list_workspaces()
        assert any(w["user_id"] == test_user for w in workspaces), "Should be in list"
        print(f"  Listed {len(workspaces)} workspaces")

        # Test limits
        limits = manager.check_workspace_limits(test_user, test_channel)
        assert limits["within_limits"], "Should be within limits"
        print(f"  Limits check passed")

        # Test delete
        deleted = manager.delete_workspace(test_user, test_channel)
        assert deleted, "Should delete successfully"
        assert not workspace.exists(), "Workspace should be gone"
        print("  Deleted successfully")

        print("\nAll tests passed!")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
