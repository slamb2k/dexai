"""
ClaudeMem Memory Provider

Local-only memory provider inspired by claude-mem (https://github.com/thedotmack/claude-mem).
Uses progressive disclosure for memory retrieval - surfacing the most relevant memories
first and providing more context as needed.

Features:
    - Local SQLite storage (no external dependencies)
    - Progressive disclosure (most relevant first)
    - Local embeddings via sentence-transformers or OpenAI
    - ADHD-optimized retrieval (prevents overwhelm)

Deployment Mode: LOCAL only

Based on: https://github.com/thedotmack/claude-mem
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime
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


class ClaudeMemProvider(MemoryProvider):
    """
    ClaudeMem local memory provider.

    Uses progressive disclosure to prevent ADHD overwhelm:
    - First retrieval: Just the most relevant 3 memories
    - Expand on request: More details from same context
    - Full history: Available but not default

    Stores everything in local SQLite with optional embeddings.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize ClaudeMem provider.

        Args:
            config: Provider configuration from args/memory.yaml
                - database_path: Path to SQLite database
                - embedding_model: 'openai' or 'local' (sentence-transformers)
                - max_initial_memories: How many to show first (default: 3)
                - progressive_threshold: Relevance threshold for expansion
        """
        config = config or {}
        self._config = config

        # Database path
        db_path = config.get("database_path", "data/claudemem.db")
        self._db_path = PROJECT_ROOT / db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Progressive disclosure settings
        self._max_initial = config.get("max_initial_memories", 3)
        self._progressive_threshold = config.get("progressive_threshold", 0.6)

        # Embedding configuration
        self._embedding_model = config.get("embedding_model", "openai")
        self._embedder = None

        # Connection (lazy init)
        self._conn: sqlite3.Connection | None = None

    @property
    def name(self) -> str:
        return "claudemem"

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

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._init_tables()
        return self._conn

    def _init_tables(self) -> None:
        """Initialize database tables."""
        conn = self._conn
        if conn is None:
            return

        conn.executescript("""
            -- Main memories table
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT DEFAULT 'fact',
                source TEXT DEFAULT 'user',
                importance INTEGER DEFAULT 5,
                confidence REAL DEFAULT 1.0,
                tags TEXT,  -- JSON array
                metadata TEXT,  -- JSON object
                user_id TEXT DEFAULT 'default',
                embedding BLOB,  -- Vector embedding
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );

            -- Commitments table
            CREATE TABLE IF NOT EXISTS commitments (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                target_person TEXT,
                due_date TIMESTAMP,
                status TEXT DEFAULT 'active',
                source_channel TEXT,
                source_message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                notes TEXT
            );

            -- Context snapshots table
            CREATE TABLE IF NOT EXISTS context_snapshots (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                state TEXT NOT NULL,  -- JSON
                trigger TEXT DEFAULT 'manual',
                summary TEXT,
                captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            );

            -- Access log for progressive disclosure
            CREATE TABLE IF NOT EXISTS memory_access (
                memory_id TEXT,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                context TEXT,
                expanded INTEGER DEFAULT 0
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
            CREATE INDEX IF NOT EXISTS idx_memories_active ON memories(is_active);
            CREATE INDEX IF NOT EXISTS idx_commitments_user ON commitments(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_context_user ON context_snapshots(user_id);
        """)
        conn.commit()

    async def _get_embedding(self, text: str) -> list[float] | None:
        """Generate embedding for text."""
        if self._embedding_model == "openai":
            return await self._get_openai_embedding(text)
        else:
            return self._get_local_embedding(text)

    async def _get_openai_embedding(self, text: str) -> list[float] | None:
        """Get embedding via OpenAI API."""
        try:
            import httpx

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return None

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "text-embedding-3-small",
                        "input": text,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                return data["data"][0]["embedding"]

        except Exception as e:
            logger.debug(f"OpenAI embedding failed: {e}")
            return None

    def _get_local_embedding(self, text: str) -> list[float] | None:
        """Get embedding via local sentence-transformers."""
        try:
            if self._embedder is None:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")

            embedding = self._embedder.encode(text)
            return embedding.tolist()

        except ImportError:
            logger.debug("sentence-transformers not installed, skipping embeddings")
            return None
        except Exception as e:
            logger.debug(f"Local embedding failed: {e}")
            return None

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    async def check_dependencies(self) -> DependencyStatus:
        """Check SQLite and optional embeddings."""
        deps = {}
        missing = []

        # SQLite always available
        deps["sqlite"] = True

        # Check for OpenAI key (optional)
        if self._embedding_model == "openai":
            openai_key = os.getenv("OPENAI_API_KEY")
            deps["openai"] = bool(openai_key)
            if not openai_key:
                logger.info("OPENAI_API_KEY not set - using keyword search only")
        else:
            # Check for sentence-transformers (optional)
            import importlib.util
            if importlib.util.find_spec("sentence_transformers") is not None:
                deps["sentence_transformers"] = True
            else:
                deps["sentence_transformers"] = False
                logger.info("sentence-transformers not installed - using keyword search only")

        return DependencyStatus(
            ready=True,  # ClaudeMem always works (embeddings are optional)
            dependencies=deps,
            missing=missing,
            instructions=None,
        )

    async def bootstrap(self) -> BootstrapResult:
        """Initialize database tables."""
        try:
            self._get_connection()
            return BootstrapResult(
                success=True,
                message="ClaudeMem database initialized",
                created=[
                    "table:memories",
                    "table:commitments",
                    "table:context_snapshots",
                    "table:memory_access",
                ],
            )
        except Exception as e:
            return BootstrapResult(
                success=False,
                message=f"Bootstrap failed: {e}",
                created=[],
            )

    async def deploy_local(self) -> DeployResult:
        """ClaudeMem is local-only, no deployment needed."""
        return DeployResult(
            success=True,
            message="ClaudeMem uses local SQLite - no deployment needed",
            services={},
        )

    async def teardown(self) -> bool:
        """Clean up database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
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
        conn = self._get_connection()
        memory_id = str(uuid.uuid4())
        user_id = user_id or "default"

        # Generate embedding
        embedding = await self._get_embedding(content)
        embedding_blob = None
        if embedding:
            embedding_blob = json.dumps(embedding).encode()

        type_str = type.value if isinstance(type, MemoryType) else type
        source_str = source.value if isinstance(source, MemorySource) else source

        conn.execute(
            """
            INSERT INTO memories (id, content, type, source, importance, tags, metadata, user_id, embedding, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                content,
                type_str,
                source_str,
                importance,
                json.dumps(tags or []),
                json.dumps(metadata or {}),
                user_id,
                embedding_blob,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()

        return memory_id

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: SearchFilters | None = None,
        search_type: str = "hybrid",
    ) -> list[MemoryEntry]:
        """
        Search memories with progressive disclosure.

        ClaudeMem's signature feature: returns a limited set initially
        to prevent ADHD overwhelm. Use expand=True for more context.
        """
        conn = self._get_connection()

        # Get query embedding for semantic search
        query_embedding = await self._get_embedding(query) if search_type != "keyword" else None

        # Build SQL query
        sql = "SELECT * FROM memories WHERE is_active = 1"
        params: list[Any] = []

        if filters:
            if filters.user_id:
                sql += " AND user_id = ?"
                params.append(filters.user_id)

            if filters.types:
                placeholders = ",".join("?" * len(filters.types))
                sql += f" AND type IN ({placeholders})"
                params.extend(
                    t.value if isinstance(t, MemoryType) else t
                    for t in filters.types
                )

            if filters.min_importance:
                sql += " AND importance >= ?"
                params.append(filters.min_importance)

        sql += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        params.append(limit * 3)  # Fetch more for scoring

        rows = conn.execute(sql, params).fetchall()

        entries = []
        for row in rows:
            # Calculate score
            score = row["importance"] / 10.0  # Base score from importance

            # Add semantic similarity if available
            if query_embedding and row["embedding"]:
                try:
                    stored_embedding = json.loads(row["embedding"])
                    similarity = self._cosine_similarity(query_embedding, stored_embedding)
                    score = (score * 0.3) + (similarity * 0.7)  # Weight semantic higher
                except (json.JSONDecodeError, TypeError):
                    pass

            # Keyword matching boost
            query_lower = query.lower()
            content_lower = row["content"].lower()
            if query_lower in content_lower:
                score += 0.2

            # Parse stored data
            tags = []
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                tags = json.loads(row["tags"]) if row["tags"] else []

            metadata = {}
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}

            created_at = datetime.utcnow()
            if row["created_at"]:
                with contextlib.suppress(ValueError, TypeError):
                    created_at = datetime.fromisoformat(row["created_at"])

            entry = MemoryEntry(
                id=row["id"],
                content=row["content"],
                type=MemoryType(row["type"]) if row["type"] else MemoryType.FACT,
                source=MemorySource(row["source"]) if row["source"] else MemorySource.SESSION,
                importance=row["importance"],
                confidence=row["confidence"] or 1.0,
                tags=tags,
                metadata=metadata,
                created_at=created_at,
                score=score,
                score_breakdown={
                    "importance": row["importance"] / 10.0,
                    "semantic": score,
                },
            )
            entries.append(entry)

        # Sort by score and apply progressive disclosure
        entries.sort(key=lambda e: e.score or 0, reverse=True)

        # Progressive disclosure: limit initial results
        if len(entries) > self._max_initial and limit <= self._max_initial:
            entries = entries[:self._max_initial]
        else:
            entries = entries[:limit]

        # Log access for progressive disclosure tracking
        for entry in entries:
            conn.execute(
                "INSERT INTO memory_access (memory_id, context) VALUES (?, ?)",
                (entry.id, query),
            )
        conn.commit()

        return entries

    async def get(self, id: str) -> MemoryEntry | None:
        """Get a specific memory by ID (only returns active entries)."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ? AND is_active = 1",
            (id,),
        ).fetchone()

        if not row:
            return None

        tags = []
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            tags = json.loads(row["tags"]) if row["tags"] else []

        metadata = {}
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}

        created_at = datetime.utcnow()
        if row["created_at"]:
            with contextlib.suppress(ValueError, TypeError):
                created_at = datetime.fromisoformat(row["created_at"])

        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            type=MemoryType(row["type"]) if row["type"] else MemoryType.FACT,
            source=MemorySource(row["source"]) if row["source"] else MemorySource.SESSION,
            importance=row["importance"],
            confidence=row["confidence"] or 1.0,
            tags=tags,
            metadata=metadata,
            created_at=created_at,
        )

    async def update(
        self,
        id: str,
        content: str | None = None,
        importance: int | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update a memory entry."""
        conn = self._get_connection()

        updates = []
        params: list[Any] = []

        if content is not None:
            updates.append("content = ?")
            params.append(content)

            # Update embedding if content changed
            embedding = await self._get_embedding(content)
            if embedding:
                updates.append("embedding = ?")
                params.append(json.dumps(embedding).encode())

        if importance is not None:
            updates.append("importance = ?")
            params.append(importance)

        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags))

        if metadata is not None:
            # Merge with existing
            existing = await self.get(id)
            if existing:
                merged = {**existing.metadata, **metadata}
                updates.append("metadata = ?")
                params.append(json.dumps(merged))

        if not updates:
            return True  # Nothing to update

        updates.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())

        params.append(id)

        conn.execute(
            f"UPDATE memories SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()

        return True

    async def delete(self, id: str, hard: bool = False) -> bool:
        """Delete a memory entry."""
        conn = self._get_connection()

        if hard:
            conn.execute("DELETE FROM memories WHERE id = ?", (id,))
        else:
            conn.execute(
                "UPDATE memories SET is_active = 0, updated_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), id),
            )

        conn.commit()
        return True

    async def list(
        self,
        filters: SearchFilters | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """List memories with optional filtering."""
        conn = self._get_connection()

        sql = "SELECT * FROM memories WHERE is_active = 1"
        params: list[Any] = []

        if filters:
            if filters.user_id:
                sql += " AND user_id = ?"
                params.append(filters.user_id)

            if filters.types:
                placeholders = ",".join("?" * len(filters.types))
                sql += f" AND type IN ({placeholders})"
                params.extend(
                    t.value if isinstance(t, MemoryType) else t
                    for t in filters.types
                )

            if filters.min_importance:
                sql += " AND importance >= ?"
                params.append(filters.min_importance)

            if not filters.include_inactive:
                sql += " AND is_active = 1"

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(sql, params).fetchall()

        entries = []
        for row in rows:
            tags = []
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                tags = json.loads(row["tags"]) if row["tags"] else []

            metadata = {}
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}

            created_at = datetime.utcnow()
            if row["created_at"]:
                with contextlib.suppress(ValueError, TypeError):
                    created_at = datetime.fromisoformat(row["created_at"])

            entry = MemoryEntry(
                id=row["id"],
                content=row["content"],
                type=MemoryType(row["type"]) if row["type"] else MemoryType.FACT,
                source=MemorySource(row["source"]) if row["source"] else MemorySource.SESSION,
                importance=row["importance"],
                confidence=row["confidence"] or 1.0,
                tags=tags,
                metadata=metadata,
                created_at=created_at,
            )
            entries.append(entry)

        return entries

    async def health_check(self) -> HealthStatus:
        """Check database health."""
        start = time.time()

        try:
            conn = self._get_connection()
            conn.execute("SELECT 1").fetchone()
            latency = (time.time() - start) * 1000

            # Get stats
            row = conn.execute("SELECT COUNT(*) as count FROM memories WHERE is_active = 1").fetchone()
            memory_count = row["count"] if row else 0

            return HealthStatus(
                healthy=True,
                provider="claudemem",
                latency_ms=latency,
                details={
                    "database": str(self._db_path),
                    "memory_count": memory_count,
                    "embedding_model": self._embedding_model,
                },
            )

        except Exception as e:
            return HealthStatus(
                healthy=False,
                provider="claudemem",
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
        conn = self._get_connection()
        commitment_id = str(uuid.uuid4())

        conn.execute(
            """
            INSERT INTO commitments (id, user_id, content, target_person, due_date, source_channel, source_message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                commitment_id,
                user_id,
                content,
                target_person,
                due_date.isoformat() if due_date else None,
                source_channel,
                source_message_id,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()

        return commitment_id

    async def list_commitments(
        self,
        user_id: str,
        status: str = "active",
        include_overdue: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List commitments."""
        conn = self._get_connection()

        sql = "SELECT * FROM commitments WHERE user_id = ?"
        params: list[Any] = [user_id]

        if status != "all":
            sql += " AND status = ?"
            params.append(status)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "target_person": row["target_person"],
                "due_date": row["due_date"],
                "status": row["status"],
                "source_channel": row["source_channel"],
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
                "notes": row["notes"],
            }
            for row in rows
        ]

    async def complete_commitment(self, id: str, notes: str | None = None) -> bool:
        """Mark a commitment as completed."""
        conn = self._get_connection()

        conn.execute(
            """
            UPDATE commitments
            SET status = 'completed', completed_at = ?, notes = ?
            WHERE id = ?
            """,
            (datetime.utcnow().isoformat(), notes, id),
        )
        conn.commit()

        return True

    async def cancel_commitment(self, id: str, reason: str | None = None) -> bool:
        """Cancel a commitment."""
        conn = self._get_connection()

        conn.execute(
            """
            UPDATE commitments
            SET status = 'cancelled', completed_at = ?, notes = ?
            WHERE id = ?
            """,
            (datetime.utcnow().isoformat(), f"Cancelled: {reason}" if reason else "Cancelled", id),
        )
        conn.commit()

        return True

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
        conn = self._get_connection()
        snapshot_id = str(uuid.uuid4())

        conn.execute(
            """
            INSERT INTO context_snapshots (id, user_id, state, trigger, summary, captured_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                user_id,
                json.dumps(state),
                trigger,
                summary,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()

        return snapshot_id

    async def resume_context(
        self,
        user_id: str,
        snapshot_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get context for resumption."""
        conn = self._get_connection()

        if snapshot_id:
            row = conn.execute(
                "SELECT * FROM context_snapshots WHERE id = ? AND user_id = ?",
                (snapshot_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM context_snapshots WHERE user_id = ? ORDER BY captured_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()

        if not row:
            return None

        state = {}
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            state = json.loads(row["state"]) if row["state"] else {}

        return {
            "id": row["id"],
            "state": state,
            "summary": row["summary"],
            "trigger": row["trigger"],
            "captured_at": row["captured_at"],
            "next_step": state.get("next_step"),
            "active_file": state.get("active_file"),
        }

    async def list_contexts(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List context snapshots."""
        conn = self._get_connection()

        rows = conn.execute(
            "SELECT * FROM context_snapshots WHERE user_id = ? ORDER BY captured_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()

        return [
            {
                "id": row["id"],
                "summary": row["summary"],
                "trigger": row["trigger"],
                "captured_at": row["captured_at"],
            }
            for row in rows
        ]

    async def delete_context(self, snapshot_id: str) -> bool:
        """Delete a context snapshot."""
        conn = self._get_connection()
        conn.execute("DELETE FROM context_snapshots WHERE id = ?", (snapshot_id,))
        conn.commit()
        return True

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_stats(self, user_id: str | None = None) -> dict[str, Any]:
        """Get memory statistics."""
        conn = self._get_connection()

        sql = "SELECT type, COUNT(*) as count FROM memories WHERE is_active = 1"
        params: list[Any] = []

        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)

        sql += " GROUP BY type"

        rows = conn.execute(sql, params).fetchall()

        by_type = {row["type"]: row["count"] for row in rows}
        total = sum(by_type.values())

        # Get commitment count
        commit_sql = "SELECT COUNT(*) as count FROM commitments WHERE status = 'active'"
        commit_params: list[Any] = []
        if user_id:
            commit_sql += " AND user_id = ?"
            commit_params.append(user_id)

        commit_row = conn.execute(commit_sql, commit_params).fetchone()
        active_commitments = commit_row["count"] if commit_row else 0

        return {
            "total": total,
            "by_type": by_type,
            "active_commitments": active_commitments,
            "provider": "claudemem",
            "deployment_mode": "local",
            "database": str(self._db_path),
        }

    async def cleanup(
        self,
        max_age_days: int = 30,
        status: str = "active",
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Clean up old entries."""
        conn = self._get_connection()

        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat()

        # Count entries to clean
        count_sql = """
            SELECT COUNT(*) as count FROM memories
            WHERE is_active = 1 AND created_at < ? AND importance < 5
        """
        row = conn.execute(count_sql, (cutoff,)).fetchone()
        count = row["count"] if row else 0

        if not dry_run and count > 0:
            conn.execute(
                """
                UPDATE memories
                SET is_active = 0, updated_at = ?
                WHERE is_active = 1 AND created_at < ? AND importance < 5
                """,
                (datetime.utcnow().isoformat(), cutoff),
            )
            conn.commit()

        return {
            "success": True,
            "count": count,
            "dry_run": dry_run,
            "cutoff_date": cutoff,
        }
