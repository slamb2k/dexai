"""
Memory Provider Base Classes

Abstract base class and data structures for the pluggable memory provider architecture.
All memory providers (native, Mem0, Zep, etc.) implement this interface.

Design Principles:
- Async-first for compatibility with external APIs
- ADHD-safe: providers handle commitment/context storage natively
- Graceful degradation: all methods have sensible defaults
- Provider-agnostic data structures for easy migration
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class MemoryType(StrEnum):
    """Universal memory types mapped to provider-specific types."""

    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    INSIGHT = "insight"
    TASK = "task"
    RELATIONSHIP = "relationship"


class MemorySource(StrEnum):
    """Origin of memory entry."""

    USER = "user"
    INFERRED = "inferred"
    SESSION = "session"
    EXTERNAL = "external"
    SYSTEM = "system"
    AGENT = "agent"


class DeploymentMode(StrEnum):
    """
    Provider deployment mode.

    Determines whether the provider uses a cloud-hosted API or requires
    self-hosted infrastructure.
    """

    CLOUD = "cloud"  # API-key based, no infrastructure needed
    SELF_HOSTED = "self_hosted"  # Requires running your own infrastructure
    LOCAL = "local"  # Runs entirely locally (e.g., SQLite, local embeddings)


@dataclass
class MemoryEntry:
    """
    Universal memory entry format.

    This is the common data structure returned by all providers, ensuring
    consistent handling regardless of backend.
    """

    id: str
    content: str
    type: MemoryType
    source: MemorySource = MemorySource.USER
    importance: int = 5  # 1-10 scale
    confidence: float = 1.0  # 0-1 scale
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    # Search result fields (populated during retrieval)
    score: float | None = None
    score_breakdown: dict[str, float] | None = None  # e.g., {"semantic": 0.8, "keyword": 0.6}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "type": self.type.value if isinstance(self.type, MemoryType) else self.type,
            "source": self.source.value if isinstance(self.source, MemorySource) else self.source,
            "importance": self.importance,
            "confidence": self.confidence,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "score": self.score,
            "score_breakdown": self.score_breakdown,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        """Create from dictionary."""
        # Handle type conversion
        memory_type = data.get("type", "fact")
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)

        source = data.get("source", "user")
        if isinstance(source, str):
            source = MemorySource(source)

        # Handle datetime conversion
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.utcnow()

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            id=data["id"],
            content=data["content"],
            type=memory_type,
            source=source,
            importance=data.get("importance", 5),
            confidence=data.get("confidence", 1.0),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at,
            score=data.get("score"),
            score_breakdown=data.get("score_breakdown"),
        )


@dataclass
class SearchFilters:
    """Universal search filter options."""

    types: list[MemoryType] | None = None
    sources: list[MemorySource] | None = None
    min_importance: int | None = None
    max_importance: int | None = None
    tags: list[str] | None = None
    tags_match_all: bool = False  # True = AND, False = OR
    created_after: datetime | None = None
    created_before: datetime | None = None
    user_id: str | None = None
    include_inactive: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {}
        if self.types:
            result["types"] = [t.value if isinstance(t, MemoryType) else t for t in self.types]
        if self.sources:
            result["sources"] = [
                s.value if isinstance(s, MemorySource) else s for s in self.sources
            ]
        if self.min_importance is not None:
            result["min_importance"] = self.min_importance
        if self.max_importance is not None:
            result["max_importance"] = self.max_importance
        if self.tags:
            result["tags"] = self.tags
            result["tags_match_all"] = self.tags_match_all
        if self.created_after:
            result["created_after"] = self.created_after.isoformat()
        if self.created_before:
            result["created_before"] = self.created_before.isoformat()
        if self.user_id:
            result["user_id"] = self.user_id
        if self.include_inactive:
            result["include_inactive"] = self.include_inactive
        return result


@dataclass
class HealthStatus:
    """Provider health check result."""

    healthy: bool
    provider: str
    latency_ms: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "healthy": self.healthy,
            "provider": self.provider,
            "latency_ms": self.latency_ms,
            "details": self.details,
        }


@dataclass
class DependencyStatus:
    """Status of provider dependencies."""

    ready: bool  # All dependencies available
    dependencies: dict[str, bool]  # e.g., {"qdrant": True, "openai": True}
    missing: list[str]  # List of missing dependencies
    instructions: str | None = None  # Setup instructions if not ready

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ready": self.ready,
            "dependencies": self.dependencies,
            "missing": self.missing,
            "instructions": self.instructions,
        }


@dataclass
class BootstrapResult:
    """Result of bootstrap operation."""

    success: bool
    message: str
    created: list[str] = field(default_factory=list)  # e.g., ["collection:memories", "index:embeddings"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "message": self.message,
            "created": self.created,
        }


@dataclass
class DeployResult:
    """Result of local deployment."""

    success: bool
    message: str
    services: dict[str, str] = field(default_factory=dict)  # e.g., {"qdrant": "localhost:6333"}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "message": self.message,
            "services": self.services,
        }


@dataclass
class Commitment:
    """
    Universal commitment/promise entry.

    Tracks promises made during conversations to prevent relationship damage
    through forgetting (critical for ADHD users).
    """

    id: str
    user_id: str
    content: str
    target_person: str | None = None
    due_date: datetime | None = None
    status: str = "active"  # active, completed, cancelled
    source_channel: str | None = None
    source_message_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "content": self.content,
            "target_person": self.target_person,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "status": self.status,
            "source_channel": self.source_channel,
            "source_message_id": self.source_message_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "notes": self.notes,
        }


@dataclass
class ContextSnapshot:
    """
    Universal context snapshot for resumption.

    Captures the user's working context when they switch tasks, enabling
    "you were here..." prompts that reduce re-orientation cost.
    """

    id: str
    user_id: str
    state: dict[str, Any]
    trigger: str = "manual"  # switch, timeout, manual
    summary: str | None = None
    captured_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "state": self.state,
            "trigger": self.trigger,
            "summary": self.summary,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class MemoryProvider(ABC):
    """
    Abstract base class for memory providers.

    All memory backends (native SQLite, Mem0, Zep, etc.) implement this interface.
    The MemoryService facade uses this to delegate operations.

    Deployment Modes:
        - CLOUD: API-key based, no infrastructure needed (e.g., Mem0 Cloud, Zep Cloud)
        - SELF_HOSTED: Requires running your own infrastructure (e.g., Qdrant, Neo4j)
        - LOCAL: Runs entirely locally with no external dependencies (e.g., native SQLite)

    Lifecycle:
        1. check_dependencies() - Verify external services are available
        2. bootstrap() - Initialize collections/indexes (optional, most auto-init)
        3. [ready for use]
        4. teardown() - Clean up on shutdown
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'native', 'mem0', 'zep')."""
        pass

    @property
    @abstractmethod
    def deployment_mode(self) -> DeploymentMode:
        """
        Deployment mode for this provider instance.

        Returns:
            DeploymentMode indicating cloud, self_hosted, or local deployment.
        """
        pass

    @property
    def supports_cloud(self) -> bool:
        """Whether this provider supports cloud deployment."""
        return False

    @property
    def supports_self_hosted(self) -> bool:
        """Whether this provider supports self-hosted deployment."""
        return False

    @property
    def supports_local(self) -> bool:
        """Whether this provider supports local deployment."""
        return False

    @property
    def requires_api_key(self) -> bool:
        """Whether this provider requires an API key (typically cloud mode)."""
        return self.deployment_mode == DeploymentMode.CLOUD

    @property
    def requires_infrastructure(self) -> bool:
        """Whether this provider requires infrastructure setup (typically self-hosted)."""
        return self.deployment_mode == DeploymentMode.SELF_HOSTED

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    @abstractmethod
    async def check_dependencies(self) -> DependencyStatus:
        """
        Check if all required external services are available.

        Returns status of each dependency (vector store, graph DB, LLM, etc.)
        This should be a quick check, not a full health test.
        """
        pass

    async def bootstrap(self) -> BootstrapResult:
        """
        Initialize provider resources (collections, indexes, schemas).

        Called once during setup. Default: no-op (most providers auto-init).
        Override if provider requires explicit initialization.
        """
        return BootstrapResult(success=True, message="No bootstrap required")

    async def deploy_local(self) -> DeployResult:
        """
        Deploy local development dependencies (e.g., start Qdrant container).

        Optional - only implemented by providers that support local deployment.
        Raises NotImplementedError if provider requires manual setup.
        """
        raise NotImplementedError(
            f"{self.name} does not support automatic local deployment. "
            f"See setup instructions in documentation."
        )

    @abstractmethod
    async def teardown(self) -> bool:
        """
        Clean up provider resources. Called during shutdown.

        Returns True if cleanup successful.
        """
        pass

    # =========================================================================
    # Core Memory Operations
    # =========================================================================

    @abstractmethod
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
        """
        Add a memory entry.

        Args:
            content: The memory content to store
            type: Classification of the memory
            importance: Priority 1-10 (higher = more important)
            source: Where this memory came from
            tags: Optional categorization tags
            metadata: Additional provider-specific data
            user_id: User this memory belongs to (for multi-user)

        Returns:
            Entry ID as string
        """
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: SearchFilters | None = None,
        search_type: str = "hybrid",  # "semantic", "keyword", "hybrid"
    ) -> list[MemoryEntry]:
        """
        Search memories.

        Args:
            query: Natural language search query
            limit: Maximum results to return
            filters: Optional filters to narrow results
            search_type: Search method - hybrid recommended for best results

        Returns:
            List of MemoryEntry objects with scores populated
        """
        pass

    @abstractmethod
    async def get(self, id: str) -> MemoryEntry | None:
        """
        Get a specific memory by ID.

        Args:
            id: Memory entry ID

        Returns:
            MemoryEntry if found, None otherwise
        """
        pass

    @abstractmethod
    async def update(
        self,
        id: str,
        content: str | None = None,
        importance: int | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Update a memory entry.

        Only non-None values will be updated.

        Args:
            id: Memory entry ID
            content: New content (if changing)
            importance: New importance (if changing)
            tags: New tags (replaces existing if provided)
            metadata: New metadata (merged with existing)

        Returns:
            True if update successful
        """
        pass

    @abstractmethod
    async def delete(self, id: str, hard: bool = False) -> bool:
        """
        Delete a memory entry.

        Args:
            id: Memory entry ID
            hard: If True, permanently delete. If False, soft delete (mark inactive).

        Returns:
            True if deletion successful
        """
        pass

    @abstractmethod
    async def list(
        self,
        filters: SearchFilters | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """
        List memories with optional filtering.

        Args:
            filters: Optional filters
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of MemoryEntry objects
        """
        pass

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """
        Check provider health and connectivity.

        Returns full health status including latency measurement.
        """
        pass

    # =========================================================================
    # Batch Operations (with default implementations)
    # =========================================================================

    async def bulk_add(self, entries: list[dict[str, Any]]) -> list[str]:
        """
        Bulk add entries.

        Default: sequential adds. Override for batch-optimized implementation.

        Args:
            entries: List of dicts matching add() parameters

        Returns:
            List of created entry IDs
        """
        ids = []
        for entry in entries:
            entry_id = await self.add(**entry)
            ids.append(entry_id)
        return ids

    async def similar(self, id: str, limit: int = 5) -> list[MemoryEntry]:
        """
        Find entries similar to a given entry.

        Default: fetch entry and do semantic search. Override for optimization.

        Args:
            id: Entry ID to find similar entries for
            limit: Maximum results

        Returns:
            List of similar MemoryEntry objects
        """
        entry = await self.get(id)
        if entry:
            return await self.search(entry.content, limit=limit, search_type="semantic")
        return []

    # =========================================================================
    # Commitment Tracking (ADHD-critical)
    # =========================================================================

    @abstractmethod
    async def add_commitment(
        self,
        content: str,
        user_id: str,
        target_person: str | None = None,
        due_date: datetime | None = None,
        source_channel: str | None = None,
        source_message_id: str | None = None,
    ) -> str:
        """
        Add a commitment/promise.

        ADHD users often damage relationships through forgetting, not lack of caring.
        This tracks promises so nothing falls through the cracks.

        Args:
            content: What was promised
            user_id: User making the commitment
            target_person: Who it was promised to
            due_date: When it's due
            source_channel: Where the promise was made
            source_message_id: Message ID containing the promise

        Returns:
            Commitment ID
        """
        pass

    @abstractmethod
    async def list_commitments(
        self,
        user_id: str,
        status: str = "active",  # active, completed, cancelled, all
        include_overdue: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List commitments with ADHD-safe framing.

        Returns commitments with forward-facing language:
        "Sarah's waiting on those docs" not "You still haven't sent docs (3 days overdue)"

        Args:
            user_id: User whose commitments to list
            status: Filter by status
            include_overdue: Include overdue commitments
            limit: Maximum results

        Returns:
            List of commitment dicts with ADHD-friendly framing
        """
        pass

    @abstractmethod
    async def complete_commitment(self, id: str, notes: str | None = None) -> bool:
        """
        Mark a commitment as completed.

        Args:
            id: Commitment ID
            notes: Optional completion notes

        Returns:
            True if successful
        """
        pass

    async def cancel_commitment(self, id: str, reason: str | None = None) -> bool:
        """
        Cancel a commitment.

        Default: delegates to complete_commitment with cancelled status.
        Override if provider has specific cancellation logic.

        Args:
            id: Commitment ID
            reason: Reason for cancellation

        Returns:
            True if successful
        """
        # Default implementation - override if provider has specific logic
        return await self.complete_commitment(id, notes=f"Cancelled: {reason}" if reason else "Cancelled")

    # =========================================================================
    # Context Capture/Resume (ADHD-critical)
    # =========================================================================

    @abstractmethod
    async def capture_context(
        self,
        user_id: str,
        state: dict[str, Any],
        trigger: str = "manual",  # switch, timeout, manual
        summary: str | None = None,
    ) -> str:
        """
        Capture current context snapshot.

        Context switching costs ADHD brains 20-45 minutes to re-orient.
        This captures where the user was so they can pick up instantly.

        Args:
            user_id: User whose context to capture
            state: Context state dict (active_file, last_action, next_step, etc.)
            trigger: What triggered the capture
            summary: Optional human-readable summary

        Returns:
            Snapshot ID
        """
        pass

    @abstractmethod
    async def resume_context(
        self,
        user_id: str,
        snapshot_id: str | None = None,  # None = most recent
    ) -> dict[str, Any] | None:
        """
        Get context for resumption with ADHD-friendly framing.

        Uses forward-facing language like "Ready to pick up..." not "You abandoned..."

        Args:
            user_id: User whose context to resume
            snapshot_id: Specific snapshot to resume (default: most recent)

        Returns:
            Dict with resumption data or None if no snapshot found
        """
        pass

    @abstractmethod
    async def list_contexts(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        List available context snapshots.

        Args:
            user_id: User whose snapshots to list
            limit: Maximum results

        Returns:
            List of snapshot summary dicts
        """
        pass

    async def delete_context(self, snapshot_id: str) -> bool:
        """
        Delete a context snapshot.

        Default: Not implemented. Override if provider supports deletion.

        Args:
            snapshot_id: Snapshot ID to delete

        Returns:
            True if successful
        """
        raise NotImplementedError(f"{self.name} does not support context deletion")

    # =========================================================================
    # Statistics and Maintenance
    # =========================================================================

    async def get_stats(self, user_id: str | None = None) -> dict[str, Any]:
        """
        Get memory statistics.

        Default: basic counts via list(). Override for optimized implementation.

        Args:
            user_id: Optional user filter

        Returns:
            Statistics dict
        """
        filters = SearchFilters(user_id=user_id) if user_id else None
        entries = await self.list(filters=filters, limit=10000)

        # Count by type
        by_type: dict[str, int] = {}
        for entry in entries:
            type_str = entry.type.value if isinstance(entry.type, MemoryType) else entry.type
            by_type[type_str] = by_type.get(type_str, 0) + 1

        return {
            "total": len(entries),
            "by_type": by_type,
            "provider": self.name,
        }

    async def cleanup(
        self,
        max_age_days: int = 30,
        status: str = "active",
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """
        Clean up old entries.

        Default: Not implemented. Override if provider supports cleanup.

        Args:
            max_age_days: Archive entries older than this
            status: Status to filter
            dry_run: If True, just count without deleting

        Returns:
            Cleanup results
        """
        raise NotImplementedError(f"{self.name} does not support cleanup")

    # =========================================================================
    # Supersession Methods (Phase C)
    # =========================================================================

    async def supersede(
        self,
        old_id: str,
        new_content: str,
        reason: str = "updated",
    ) -> str:
        """
        Mark old memory as superseded and create replacement.

        The old memory is invalidated (not deleted) to preserve temporal queries.
        The new memory is created with a reference to the superseded entry.

        Args:
            old_id: ID of the memory being superseded
            new_content: Content for the replacement memory
            reason: Why the old memory was superseded

        Returns:
            ID of the new memory
        """
        raise NotImplementedError(f"{self.name} does not support supersession")

    async def classify_update(
        self,
        new_fact: str,
        existing_memories: list["MemoryEntry"],
    ) -> list[dict[str, Any]]:
        """
        Classify how new_fact relates to existing memories (AUDN).

        Actions:
            ADD       — Genuinely new, no overlap
            UPDATE    — Augments/refines existing (merge)
            SUPERSEDE — Contradicts existing (invalidate old)
            NOOP      — Duplicate or irrelevant (skip)

        Default implementation uses LLM-based classification.
        External providers (Mem0, Zep) may override with built-in pipelines.

        Args:
            new_fact: The new fact to classify
            existing_memories: Similar existing memories to compare against

        Returns:
            List of {action: str, memory_id: str, reason: str}
        """
        from tools.memory.extraction.classifier import classify_update
        return await classify_update(new_fact, existing_memories)

    # =========================================================================
    # Tiered Storage Methods (Phase C)
    # =========================================================================

    async def promote(self, entry_id: str, target_tier: str) -> bool:
        """
        Move memory from current tier to target (e.g., L2 → L3).

        Args:
            entry_id: Memory entry ID
            target_tier: Target tier ("L2" or "L3")

        Returns:
            True if promoted successfully
        """
        raise NotImplementedError(f"{self.name} does not support tier promotion")

    async def consolidate(
        self,
        memory_ids: list[str],
        summary: str,
    ) -> str:
        """
        Merge multiple memories into a consolidated entry.
        Original memories are marked as superseded.

        Args:
            memory_ids: IDs of memories to consolidate
            summary: LLM-generated summary of the cluster

        Returns:
            ID of the consolidated memory
        """
        raise NotImplementedError(f"{self.name} does not support consolidation")

    # =========================================================================
    # Session Note Methods (Phase A)
    # =========================================================================

    async def add_session_note(
        self,
        content: str,
        session_id: str,
        importance: int = 5,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Store a session-scoped note for later consolidation.

        Session notes are temporary L2 entries extracted from conversation
        turns. They are consumed by consolidation and cleaned up after 7 days.

        Args:
            content: Note content
            session_id: Session identifier
            importance: Importance score (1-10)
            metadata: Optional metadata (type, user_id, channel, etc.)

        Returns:
            ID of the stored note
        """
        # Default: store as a regular memory entry with session tag
        return await self.add(
            content=content,
            type=MemoryType.INSIGHT,
            importance=importance,
            source=MemorySource.SESSION,
            tags=["session_note", f"session:{session_id}"],
            metadata=metadata or {},
        )

    async def get_session_notes(
        self,
        session_id: str,
    ) -> list["MemoryEntry"]:
        """
        Retrieve all notes for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of MemoryEntry objects
        """
        # Default: search by session tag
        return await self.search(
            query=f"session:{session_id}",
            limit=100,
        )

    # =========================================================================
    # L1 Context Building (Phase B)
    # =========================================================================

    async def build_context_block(
        self,
        user_id: str,
        current_query: str | None = None,
        max_tokens: int = 1000,
    ) -> str:
        """
        Build a condensed memory block for L1 injection.
        Combines user profile, relevant memories, and active commitments.

        Args:
            user_id: User identifier
            current_query: Optional current query for relevance
            max_tokens: Maximum token budget

        Returns:
            Formatted memory block string
        """
        from tools.memory.l1_builder import build_l1_memory_block
        return await build_l1_memory_block(
            user_id=user_id,
            current_query=current_query,
            max_tokens=max_tokens,
            provider=self,
        )
