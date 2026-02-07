"""
Native Memory Provider

Local SQLite-based memory provider with hybrid BM25 + semantic search.
This wraps the existing DexAI memory implementation to conform to the
MemoryProvider interface.

Features:
    - Local SQLite storage (no external dependencies)
    - Hybrid search (BM25 keyword + OpenAI embeddings)
    - Commitment tracking
    - Context capture/resume
    - Full backward compatibility with existing memory tools

Deployment Mode: LOCAL only
"""

import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .base import (
    BootstrapResult,
    DependencyStatus,
    DeploymentMode,
    DeployResult,
    HealthStatus,
    MemoryEntry,
    MemoryProvider,
    MemorySource,
    MemoryType,
    SearchFilters,
)


logger = logging.getLogger(__name__)

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class NativeProvider(MemoryProvider):
    """
    Native memory provider using local SQLite and hybrid search.

    This provider wraps the existing memory implementation in
    tools/memory/ to provide the MemoryProvider interface.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the native provider.

        Args:
            config: Provider configuration from args/memory.yaml
        """
        config = config or {}
        self._config = config

        # Database paths
        db_path = config.get("database_path", "data/memory.db")
        context_db_path = config.get("context_database_path", "data/context.db")

        self._db_path = PROJECT_ROOT / db_path
        self._context_db_path = PROJECT_ROOT / context_db_path

        # Ensure directories exist
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._context_db_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "native"

    @property
    def deployment_mode(self) -> DeploymentMode:
        return DeploymentMode.LOCAL

    @property
    def supports_cloud(self) -> bool:
        return False

    @property
    def supports_self_hosted(self) -> bool:
        return False

    @property
    def supports_local(self) -> bool:
        return True

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    async def check_dependencies(self) -> DependencyStatus:
        """Check if SQLite and optional OpenAI are available."""
        deps = {}
        missing = []

        # SQLite is always available (stdlib)
        deps["sqlite"] = True

        # Check for OpenAI API key (optional, for embeddings)
        import os

        openai_key = os.getenv("OPENAI_API_KEY")
        deps["openai"] = bool(openai_key)
        if not openai_key:
            # Not blocking - hybrid search still works with keyword-only
            logger.info("OPENAI_API_KEY not set - semantic search disabled")

        return DependencyStatus(
            ready=True,  # Native provider always ready (SQLite is built-in)
            dependencies=deps,
            missing=missing,
            instructions=None,
        )

    async def bootstrap(self) -> BootstrapResult:
        """Initialize database tables."""
        created = []

        try:
            # Import to trigger table creation
            from tools.memory import memory_db

            memory_db.get_connection().close()
            created.append("table:memory_entries")
            created.append("table:daily_logs")
            created.append("table:memory_access_log")

            # Context database
            from tools.memory import context_capture

            context_capture.get_connection().close()
            created.append("table:context_snapshots")

            # Commitments
            from tools.memory import commitments

            commitments.get_connection().close()
            created.append("table:commitments")

            return BootstrapResult(
                success=True,
                message="Native provider initialized",
                created=created,
            )

        except Exception as e:
            return BootstrapResult(
                success=False,
                message=f"Bootstrap failed: {e}",
                created=created,
            )

    async def deploy_local(self) -> DeployResult:
        """Native provider doesn't need deployment."""
        return DeployResult(
            success=True,
            message="Native provider uses local SQLite - no deployment needed",
            services={},
        )

    async def teardown(self) -> bool:
        """Cleanup resources."""
        # SQLite connections are managed per-call, nothing to cleanup
        return True

    # =========================================================================
    # Core Memory Operations
    # =========================================================================

    async def add(
        self,
        content: str,
        type: MemoryType = MemoryType.FACT,
        importance: int = 5,
        source: MemorySource = MemorySource.USER,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> str:
        """Add a memory entry."""
        from tools.memory import memory_db

        # Map enum to string
        type_str = type.value if isinstance(type, MemoryType) else type
        source_str = source.value if isinstance(source, MemorySource) else source

        # Build context from metadata
        context = None
        if metadata:
            import json

            context = json.dumps(metadata)

        result = memory_db.add_entry(
            content=content,
            entry_type=type_str,
            source=source_str,
            importance=importance,
            tags=tags,
            context=context,
        )

        if result.get("success"):
            entry = result.get("entry", {})
            return str(entry.get("id", ""))
        else:
            raise ValueError(result.get("error", "Failed to add entry"))

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: SearchFilters | None = None,
        search_type: str = "hybrid",
    ) -> list[MemoryEntry]:
        """Search memories using hybrid search."""
        from tools.memory import hybrid_search

        # Determine search mode
        semantic_only = search_type == "semantic"
        keyword_only = search_type == "keyword"

        # Get entry type filter
        entry_type = None
        if filters and filters.types and len(filters.types) == 1:
            entry_type = filters.types[0].value if isinstance(filters.types[0], MemoryType) else filters.types[0]

        result = hybrid_search.hybrid_search(
            query=query,
            entry_type=entry_type,
            limit=limit,
            semantic_only=semantic_only,
            keyword_only=keyword_only,
        )

        entries = []
        for r in result.get("results", []):
            entry = MemoryEntry(
                id=str(r.get("id", "")),
                content=r.get("content", ""),
                type=MemoryType(r.get("type", "fact")),
                source=MemorySource.SESSION,  # Default
                importance=r.get("importance", 5),
                score=r.get("score"),
                score_breakdown={
                    "bm25": r.get("bm25_score"),
                    "semantic": r.get("semantic_score"),
                },
            )
            entries.append(entry)

        return entries

    async def get(self, id: str) -> MemoryEntry | None:
        """Get a specific memory by ID."""
        from tools.memory import memory_db

        result = memory_db.get_entry(int(id))

        if not result.get("success"):
            return None

        entry_data = result.get("entry", {})
        return self._dict_to_entry(entry_data)

    async def update(
        self,
        id: str,
        content: str | None = None,
        importance: int | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update a memory entry."""
        from tools.memory import memory_db

        kwargs = {}
        if content is not None:
            kwargs["content"] = content
        if importance is not None:
            kwargs["importance"] = importance
        if tags is not None:
            kwargs["tags"] = tags
        if metadata is not None:
            import json

            kwargs["context"] = json.dumps(metadata)

        if not kwargs:
            return True  # Nothing to update

        result = memory_db.update_entry(int(id), **kwargs)
        return result.get("success", False)

    async def delete(self, id: str, hard: bool = False) -> bool:
        """Delete a memory entry."""
        from tools.memory import memory_db

        result = memory_db.delete_entry(int(id), soft_delete=not hard)
        return result.get("success", False)

    async def list(
        self,
        filters: SearchFilters | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """List memories with optional filtering."""
        from tools.memory import memory_db

        # Build filter parameters
        entry_type = None
        source = None
        min_importance = 1

        if filters:
            if filters.types and len(filters.types) == 1:
                entry_type = filters.types[0].value if isinstance(filters.types[0], MemoryType) else filters.types[0]
            if filters.sources and len(filters.sources) == 1:
                source = filters.sources[0].value if isinstance(filters.sources[0], MemorySource) else filters.sources[0]
            if filters.min_importance:
                min_importance = filters.min_importance

        result = memory_db.list_entries(
            entry_type=entry_type,
            source=source,
            limit=limit,
            offset=offset,
            min_importance=min_importance,
            active_only=not (filters and filters.include_inactive),
        )

        entries = []
        for entry_data in result.get("entries", []):
            entries.append(self._dict_to_entry(entry_data))

        return entries

    async def health_check(self) -> HealthStatus:
        """Check provider health."""
        start = time.time()

        try:
            # Try to query the database
            from tools.memory import memory_db

            result = memory_db.get_stats()
            latency = (time.time() - start) * 1000

            return HealthStatus(
                healthy=result.get("success", False),
                provider="native",
                latency_ms=latency,
                details=result.get("stats", {}),
            )

        except Exception as e:
            return HealthStatus(
                healthy=False,
                provider="native",
                latency_ms=(time.time() - start) * 1000,
                details={"error": str(e)},
            )

    # =========================================================================
    # Commitment Operations
    # =========================================================================

    async def add_commitment(
        self,
        content: str,
        user_id: str,
        target_person: str | None = None,
        due_date: datetime | None = None,
        source_channel: str | None = None,
        source_message_id: str | None = None,
    ) -> str:
        """Add a commitment."""
        from tools.memory import commitments

        due_date_str = due_date.isoformat() if due_date else None

        result = commitments.add_commitment(
            user_id=user_id,
            content=content,
            target_person=target_person,
            due_date=due_date_str,
            source_channel=source_channel,
            source_message_id=source_message_id,
        )

        if result.get("success"):
            return result.get("data", {}).get("id", "")
        else:
            raise ValueError(result.get("error", "Failed to add commitment"))

    async def list_commitments(
        self,
        user_id: str,
        status: str = "active",
        include_overdue: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List commitments."""
        from tools.memory import commitments

        if status == "all":
            result = commitments.list_commitments(user_id=user_id, limit=limit)
        else:
            result = commitments.list_commitments(user_id=user_id, status=status, limit=limit)

        if result.get("success"):
            data = result.get("data", {})
            return data.get("commitments", [])
        return []

    async def complete_commitment(self, id: str, notes: str | None = None) -> bool:
        """Mark a commitment as completed."""
        from tools.memory import commitments

        result = commitments.complete_commitment(id, notes=notes)
        return result.get("success", False)

    async def cancel_commitment(self, id: str, reason: str | None = None) -> bool:
        """Cancel a commitment."""
        from tools.memory import commitments

        result = commitments.cancel_commitment(id, notes=reason)
        return result.get("success", False)

    # =========================================================================
    # Context Operations
    # =========================================================================

    async def capture_context(
        self,
        user_id: str,
        state: dict[str, Any],
        trigger: str = "manual",
        summary: str | None = None,
    ) -> str:
        """Capture context snapshot."""
        from tools.memory import context_capture

        result = context_capture.capture_context(
            user_id=user_id,
            trigger=trigger,
            active_file=state.get("active_file"),
            last_action=state.get("last_action"),
            next_step=state.get("next_step"),
            channel=state.get("channel"),
            metadata=state.get("metadata"),
            summary=summary,
        )

        if result.get("success"):
            return result.get("data", {}).get("id", "")
        else:
            raise ValueError(result.get("error", "Failed to capture context"))

    async def resume_context(
        self,
        user_id: str,
        snapshot_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get context for resumption."""
        from tools.memory import context_resume

        result = context_resume.resume_context(
            user_id=user_id,
            snapshot_id=snapshot_id,
        )

        if result.get("success"):
            return result.get("data")
        return None

    async def list_contexts(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List context snapshots."""
        from tools.memory import context_capture

        result = context_capture.list_snapshots(
            user_id=user_id,
            limit=limit,
        )

        if result.get("success"):
            return result.get("data", {}).get("snapshots", [])
        return []

    async def delete_context(self, snapshot_id: str) -> bool:
        """Delete a context snapshot."""
        from tools.memory import context_capture

        result = context_capture.delete_snapshot(snapshot_id)
        return result.get("success", False)

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_stats(self, user_id: str | None = None) -> dict[str, Any]:
        """Get memory statistics."""
        from tools.memory import memory_db

        result = memory_db.get_stats()
        stats = result.get("stats", {})
        stats["provider"] = "native"
        stats["deployment_mode"] = "local"
        return stats

    async def cleanup(
        self,
        max_age_days: int = 30,
        status: str = "active",
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Clean up old entries."""
        from tools.memory import commitments

        result = commitments.cleanup_old_commitments(
            max_age_days=max_age_days,
            status=status,
            dry_run=dry_run,
        )

        return {
            "success": result.get("success", False),
            "count": result.get("count", 0),
            "dry_run": dry_run,
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _dict_to_entry(self, data: dict[str, Any]) -> MemoryEntry:
        """Convert database row dict to MemoryEntry."""
        import json

        # Parse tags
        tags = []
        if data.get("tags"):
            try:
                tags = json.loads(data["tags"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse metadata from context
        metadata = {}
        if data.get("context"):
            try:
                metadata = json.loads(data["context"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse dates
        created_at = datetime.now()
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                pass

        updated_at = None
        if data.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(data["updated_at"])
            except (ValueError, TypeError):
                pass

        return MemoryEntry(
            id=str(data.get("id", "")),
            content=data.get("content", ""),
            type=MemoryType(data.get("type", "fact")),
            source=MemorySource(data.get("source", "session")),
            importance=data.get("importance", 5),
            confidence=data.get("confidence", 1.0),
            tags=tags,
            metadata=metadata,
            created_at=created_at,
            updated_at=updated_at,
        )
