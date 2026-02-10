"""
Storage Cleanup for Multi-Modal Messaging (Phase 15d)

Handles scheduled cleanup of temporary media files and stale database entries:
- Removes expired temp files from dexai_media_* directories
- Cleans up stale interactive_state entries from media.db
- Reports storage usage statistics

Usage:
    from tools.channels.media.storage_cleanup import get_storage_cleanup, run_cleanup

    cleanup = get_storage_cleanup()
    result = await cleanup.cleanup()

    # Or use the convenience function
    result = await run_cleanup()
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "multimodal.yaml"

# Default data directory for databases
DATA_DIR = PROJECT_ROOT / "data"

# Default temp directory pattern
TEMP_DIR_PREFIX = "dexai_media_"


def _load_config() -> dict[str, Any]:
    """Load multimodal configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


class StorageCleanup:
    """
    Manage cleanup of temporary media files and stale DB entries.

    Phase 15d: Provides scheduled and on-demand cleanup of temporary
    files created during media processing, as well as expired database
    entries from interactive sessions.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize storage cleanup manager.

        Loads retention settings from args/multimodal.yaml under the
        'storage' section.

        Args:
            config: Optional config override (defaults to args/multimodal.yaml).
        """
        self.config = config or _load_config()
        storage_config = self.config.get("storage", {})
        self.temp_retention_hours: float = storage_config.get(
            "temp_retention_hours", 1.0
        )
        self.cleanup_enabled: bool = storage_config.get("cleanup_enabled", True)
        self._temp_base_dir = Path(tempfile.gettempdir())

    async def cleanup(self) -> dict[str, Any]:
        """
        Remove expired temporary media files.

        Walks the system temp directory for directories and files matching
        the dexai_media_* pattern and removes any that are older than
        the configured retention period.

        Returns:
            Dict with keys: success, files_removed, bytes_freed.
        """
        if not self.cleanup_enabled:
            logger.info("Storage cleanup is disabled in config")
            return {
                "success": True,
                "files_removed": 0,
                "bytes_freed": 0,
            }

        files_removed = 0
        bytes_freed = 0
        errors: list[str] = []
        cutoff_time = time.time() - (self.temp_retention_hours * 3600)

        try:
            # Find all dexai_media_* entries in the temp directory
            for entry in self._temp_base_dir.iterdir():
                if not entry.name.startswith(TEMP_DIR_PREFIX):
                    continue

                try:
                    if entry.is_dir():
                        removed, freed = self._cleanup_directory(entry, cutoff_time)
                        files_removed += removed
                        bytes_freed += freed

                        # Remove the directory itself if empty
                        try:
                            if not any(entry.iterdir()):
                                entry.rmdir()
                                logger.debug(f"Removed empty dir: {entry}")
                        except OSError:
                            pass

                    elif entry.is_file():
                        stat = entry.stat()
                        if stat.st_mtime < cutoff_time:
                            size = stat.st_size
                            entry.unlink()
                            files_removed += 1
                            bytes_freed += size
                            logger.debug(f"Removed expired file: {entry}")

                except PermissionError as e:
                    errors.append(f"Permission denied: {entry.name}")
                    logger.warning(f"Cannot clean {entry}: {e}")
                except Exception as e:
                    errors.append(f"Error with {entry.name}: {str(e)[:100]}")
                    logger.warning(f"Cleanup error for {entry}: {e}")

        except Exception as e:
            logger.error(f"Storage cleanup failed: {e}")
            return {
                "success": False,
                "files_removed": files_removed,
                "bytes_freed": bytes_freed,
                "error": str(e)[:200],
            }

        logger.info(
            f"Storage cleanup complete: {files_removed} files removed, "
            f"{bytes_freed / 1024:.1f} KB freed"
        )

        result: dict[str, Any] = {
            "success": True,
            "files_removed": files_removed,
            "bytes_freed": bytes_freed,
        }
        if errors:
            result["warnings"] = errors[:10]  # Cap at 10 warnings

        return result

    def _cleanup_directory(
        self, directory: Path, cutoff_time: float
    ) -> tuple[int, int]:
        """
        Recursively clean up expired files in a directory.

        Args:
            directory: Directory to clean.
            cutoff_time: Unix timestamp; files modified before this are removed.

        Returns:
            Tuple of (files_removed, bytes_freed).
        """
        files_removed = 0
        bytes_freed = 0

        try:
            for item in directory.rglob("*"):
                if not item.is_file():
                    continue

                try:
                    stat = item.stat()
                    if stat.st_mtime < cutoff_time:
                        size = stat.st_size
                        item.unlink()
                        files_removed += 1
                        bytes_freed += size
                        logger.debug(f"Removed expired file: {item}")
                except (PermissionError, OSError) as e:
                    logger.debug(f"Cannot remove {item}: {e}")

        except Exception as e:
            logger.warning(f"Error walking directory {directory}: {e}")

        return files_removed, bytes_freed

    async def cleanup_db_entries(
        self, db_path: str | None = None
    ) -> dict[str, Any]:
        """
        Remove expired interactive_state entries from media.db.

        Cleans up stale database entries that track interactive media
        sessions (e.g., image generation with follow-up edits).

        Args:
            db_path: Optional path to media.db. Defaults to data/media.db.

        Returns:
            Dict with keys: success, entries_removed.
        """
        if db_path is None:
            db_path = str(DATA_DIR / "media.db")

        if not Path(db_path).exists():
            logger.debug(f"Media database not found at {db_path}, skipping")
            return {
                "success": True,
                "entries_removed": 0,
            }

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check if interactive_state table exists
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='interactive_state'"
            )
            if not cursor.fetchone():
                conn.close()
                return {
                    "success": True,
                    "entries_removed": 0,
                }

            # Calculate cutoff timestamp
            cutoff_seconds = self.temp_retention_hours * 3600
            cutoff_sql = f"datetime('now', '-{int(cutoff_seconds)} seconds')"

            # Count entries to remove
            cursor.execute(
                f"SELECT COUNT(*) FROM interactive_state "
                f"WHERE created_at < {cutoff_sql}"
            )
            count = cursor.fetchone()[0]

            if count > 0:
                cursor.execute(
                    f"DELETE FROM interactive_state "
                    f"WHERE created_at < {cutoff_sql}"
                )
                conn.commit()
                logger.info(f"Removed {count} expired interactive_state entries")

            conn.close()

            return {
                "success": True,
                "entries_removed": count,
            }

        except Exception as e:
            logger.error(f"Database cleanup failed: {e}")
            return {
                "success": False,
                "entries_removed": 0,
                "error": str(e)[:200],
            }

    def get_stats(self) -> dict[str, Any]:
        """
        Get current storage usage statistics.

        Scans temp directories for dexai_media_* entries and reports
        total file count and disk usage.

        Returns:
            Dict with keys: total_files, total_bytes, total_mb,
            directories, oldest_file_age_hours.
        """
        total_files = 0
        total_bytes = 0
        directories = 0
        oldest_mtime: float | None = None
        now = time.time()

        try:
            for entry in self._temp_base_dir.iterdir():
                if not entry.name.startswith(TEMP_DIR_PREFIX):
                    continue

                if entry.is_dir():
                    directories += 1
                    for item in entry.rglob("*"):
                        if item.is_file():
                            try:
                                stat = item.stat()
                                total_files += 1
                                total_bytes += stat.st_size
                                if oldest_mtime is None or stat.st_mtime < oldest_mtime:
                                    oldest_mtime = stat.st_mtime
                            except OSError:
                                pass

                elif entry.is_file():
                    try:
                        stat = entry.stat()
                        total_files += 1
                        total_bytes += stat.st_size
                        if oldest_mtime is None or stat.st_mtime < oldest_mtime:
                            oldest_mtime = stat.st_mtime
                    except OSError:
                        pass

        except Exception as e:
            logger.warning(f"Error getting storage stats: {e}")

        oldest_age_hours = (
            (now - oldest_mtime) / 3600.0 if oldest_mtime is not None else 0.0
        )

        return {
            "total_files": total_files,
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
            "directories": directories,
            "oldest_file_age_hours": round(oldest_age_hours, 2),
        }


# =============================================================================
# Singleton Factory
# =============================================================================

_instance: StorageCleanup | None = None


def get_storage_cleanup(config: dict[str, Any] | None = None) -> StorageCleanup:
    """
    Get or create the global StorageCleanup instance.

    Args:
        config: Optional config override for first initialization.

    Returns:
        The singleton StorageCleanup instance.
    """
    global _instance
    if _instance is None:
        _instance = StorageCleanup(config=config)
    return _instance


async def run_cleanup(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Convenience function to run a full cleanup cycle.

    Performs both file cleanup and database entry cleanup, then returns
    combined results.

    Args:
        config: Optional config override.

    Returns:
        Dict with keys: success, files_removed, bytes_freed,
        db_entries_removed.
    """
    cleanup = get_storage_cleanup(config=config)

    file_result = await cleanup.cleanup()
    db_result = await cleanup.cleanup_db_entries()

    return {
        "success": file_result.get("success", False)
        and db_result.get("success", False),
        "files_removed": file_result.get("files_removed", 0),
        "bytes_freed": file_result.get("bytes_freed", 0),
        "db_entries_removed": db_result.get("entries_removed", 0),
    }
