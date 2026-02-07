"""
SimpleMem Memory Provider

Cloud-only memory provider using SimpleMem's semantic compression API.
SimpleMem uses a 3-stage pipeline for memory compression and intent-aware retrieval.

Features:
    - Cloud-hosted (no infrastructure needed)
    - Semantic compression (reduces token usage)
    - Intent-aware retrieval
    - Simple API (store + query)

Deployment Mode: CLOUD only

API Documentation: https://docs.simplemem.io
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any

import httpx

from .base import (
    BootstrapResult,
    DependencyStatus,
    DeploymentMode,
    HealthStatus,
    MemoryEntry,
    MemoryProvider,
    MemorySource,
    MemoryType,
    SearchFilters,
)


logger = logging.getLogger(__name__)

# SimpleMem API endpoints
SIMPLEMEM_API_BASE = "https://api.simplemem.io/v1"


class SimpleMemProvider(MemoryProvider):
    """
    SimpleMem cloud memory provider.

    SimpleMem uses semantic compression to store memories efficiently
    and intent-aware retrieval to surface the most relevant context.

    Cloud-only: requires SIMPLEMEM_API_KEY environment variable.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize SimpleMem provider.

        Args:
            config: Provider configuration from args/memory.yaml
                - api_key: SimpleMem API key (or use SIMPLEMEM_API_KEY env)
                - api_base: Override API base URL (for testing)
                - user_id: Default user ID for operations
                - compression_level: 'low', 'medium', 'high' (default: medium)
        """
        config = config or {}
        self._config = config

        # API configuration
        self._api_key = config.get("api_key") or os.getenv("SIMPLEMEM_API_KEY")
        self._api_base = config.get("api_base") or os.getenv("SIMPLEMEM_API_BASE") or SIMPLEMEM_API_BASE
        self._default_user_id = config.get("user_id") or "default"
        self._compression_level = config.get("compression_level", "medium")

        # HTTP client (lazy init)
        self._client: httpx.AsyncClient | None = None

        # Local cache for commitments/contexts (SimpleMem doesn't natively support these)
        # We store these as regular memories with special metadata
        self._commitment_prefix = "commitment:"
        self._context_prefix = "context:"

    @property
    def name(self) -> str:
        return "simplemem"

    @property
    def deployment_mode(self) -> DeploymentMode:
        return DeploymentMode.CLOUD

    @property
    def supports_cloud(self) -> bool:
        return True

    @property
    def supports_self_hosted(self) -> bool:
        return False

    @property
    def supports_local(self) -> bool:
        return False

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._api_base,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make API request with error handling."""
        client = await self._get_client()

        try:
            if method.upper() == "GET":
                response = await client.get(endpoint, params=data)
            elif method.upper() == "POST":
                response = await client.post(endpoint, json=data)
            elif method.upper() == "PUT":
                response = await client.put(endpoint, json=data)
            elif method.upper() == "DELETE":
                response = await client.delete(endpoint)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json() if response.content else {}

        except httpx.HTTPStatusError as e:
            logger.error(f"SimpleMem API error: {e.response.status_code} - {e.response.text}")
            raise ValueError(f"SimpleMem API error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error(f"SimpleMem request error: {e}")
            raise ValueError(f"SimpleMem request error: {e}") from e

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    async def check_dependencies(self) -> DependencyStatus:
        """Check if SimpleMem API is accessible."""
        deps = {}
        missing = []

        # Check API key
        if self._api_key:
            deps["api_key"] = True
        else:
            deps["api_key"] = False
            missing.append("SIMPLEMEM_API_KEY")

        # Check API connectivity (only if we have a key)
        if self._api_key:
            try:
                await self.health_check()
                deps["api_connectivity"] = True
            except Exception as e:
                deps["api_connectivity"] = False
                missing.append("api_connectivity")
                logger.warning(f"SimpleMem API connectivity check failed: {e}")

        instructions = None
        if missing:
            if "SIMPLEMEM_API_KEY" in missing:
                instructions = (
                    "SimpleMem requires an API key. Get one at https://simplemem.io\n"
                    "Then set: export SIMPLEMEM_API_KEY=your-key"
                )
            else:
                instructions = "SimpleMem API is not responding. Check your network connection."

        return DependencyStatus(
            ready=len(missing) == 0,
            dependencies=deps,
            missing=missing,
            instructions=instructions,
        )

    async def bootstrap(self) -> BootstrapResult:
        """SimpleMem cloud is always ready - no bootstrap needed."""
        return BootstrapResult(
            success=True,
            message="SimpleMem cloud is always ready",
            created=[],
        )

    async def teardown(self) -> bool:
        """Clean up HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
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
        """Add a memory to SimpleMem."""
        user_id = user_id or self._default_user_id

        # Build metadata for SimpleMem
        mem_metadata = {
            "type": type.value if isinstance(type, MemoryType) else type,
            "source": source.value if isinstance(source, MemorySource) else source,
            "importance": importance,
            "tags": tags or [],
            **(metadata or {}),
        }

        data = {
            "content": content,
            "user_id": user_id,
            "metadata": mem_metadata,
            "compression_level": self._compression_level,
        }

        result = await self._make_request("POST", "/memories", data)
        return result.get("id", str(uuid.uuid4()))

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: SearchFilters | None = None,
        search_type: str = "hybrid",
    ) -> list[MemoryEntry]:
        """Search memories using SimpleMem's intent-aware retrieval."""
        user_id = (filters.user_id if filters else None) or self._default_user_id

        data = {
            "query": query,
            "user_id": user_id,
            "limit": limit,
            "intent_aware": True,  # SimpleMem's signature feature
        }

        # Add type filter if specified
        if filters and filters.types:
            data["types"] = [
                t.value if isinstance(t, MemoryType) else t
                for t in filters.types
            ]

        if filters and filters.min_importance:
            data["min_importance"] = filters.min_importance

        try:
            result = await self._make_request("POST", "/search", data)
        except Exception as e:
            logger.warning(f"SimpleMem search failed: {e}")
            return []

        entries = []
        for item in result.get("results", []):
            metadata = item.get("metadata", {})

            # Parse type
            type_str = metadata.get("type", "fact")
            try:
                memory_type = MemoryType(type_str)
            except ValueError:
                memory_type = MemoryType.FACT

            # Parse source
            source_str = metadata.get("source", "user")
            try:
                memory_source = MemorySource(source_str)
            except ValueError:
                memory_source = MemorySource.SESSION

            entry = MemoryEntry(
                id=item.get("id", ""),
                content=item.get("content", ""),
                type=memory_type,
                source=memory_source,
                importance=metadata.get("importance", 5),
                tags=metadata.get("tags", []),
                metadata=metadata,
                score=item.get("score", 0.0),
                score_breakdown={"semantic": item.get("score", 0.0)},
            )
            entries.append(entry)

        return entries

    async def get(self, id: str) -> MemoryEntry | None:
        """Get a specific memory by ID."""
        try:
            result = await self._make_request("GET", f"/memories/{id}")
        except Exception as e:
            logger.debug(f"SimpleMem get failed for {id}: {e}")
            return None

        if not result:
            return None

        metadata = result.get("metadata", {})

        # Parse type
        type_str = metadata.get("type", "fact")
        try:
            memory_type = MemoryType(type_str)
        except ValueError:
            memory_type = MemoryType.FACT

        # Parse source
        source_str = metadata.get("source", "user")
        try:
            memory_source = MemorySource(source_str)
        except ValueError:
            memory_source = MemorySource.SESSION

        # Parse dates
        created_at = datetime.utcnow()
        if result.get("created_at"):
            with contextlib.suppress(ValueError, TypeError):
                created_at = datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))

        return MemoryEntry(
            id=result.get("id", ""),
            content=result.get("content", ""),
            type=memory_type,
            source=memory_source,
            importance=metadata.get("importance", 5),
            tags=metadata.get("tags", []),
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
        data: dict[str, Any] = {}

        if content is not None:
            data["content"] = content

        if importance is not None or tags is not None or metadata is not None:
            # Need to merge with existing metadata
            existing = await self.get(id)
            if existing:
                new_metadata = dict(existing.metadata)
                if importance is not None:
                    new_metadata["importance"] = importance
                if tags is not None:
                    new_metadata["tags"] = tags
                if metadata is not None:
                    new_metadata.update(metadata)
                data["metadata"] = new_metadata

        if not data:
            return True  # Nothing to update

        try:
            await self._make_request("PUT", f"/memories/{id}", data)
            return True
        except Exception as e:
            logger.error(f"SimpleMem update failed for {id}: {e}")
            return False

    async def delete(self, id: str, hard: bool = False) -> bool:
        """Delete a memory entry."""
        try:
            await self._make_request("DELETE", f"/memories/{id}")
            return True
        except Exception as e:
            logger.error(f"SimpleMem delete failed for {id}: {e}")
            return False

    async def list(
        self,
        filters: SearchFilters | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """List memories with optional filtering."""
        user_id = (filters.user_id if filters else None) or self._default_user_id

        data = {
            "user_id": user_id,
            "limit": limit,
            "offset": offset,
        }

        if filters and filters.types:
            data["types"] = [
                t.value if isinstance(t, MemoryType) else t
                for t in filters.types
            ]

        try:
            result = await self._make_request("GET", "/memories", data)
        except Exception as e:
            logger.warning(f"SimpleMem list failed: {e}")
            return []

        entries = []
        for item in result.get("memories", []):
            metadata = item.get("metadata", {})

            # Parse type
            type_str = metadata.get("type", "fact")
            try:
                memory_type = MemoryType(type_str)
            except ValueError:
                memory_type = MemoryType.FACT

            # Parse source
            source_str = metadata.get("source", "user")
            try:
                memory_source = MemorySource(source_str)
            except ValueError:
                memory_source = MemorySource.SESSION

            entry = MemoryEntry(
                id=item.get("id", ""),
                content=item.get("content", ""),
                type=memory_type,
                source=memory_source,
                importance=metadata.get("importance", 5),
                tags=metadata.get("tags", []),
                metadata=metadata,
            )
            entries.append(entry)

        return entries

    async def health_check(self) -> HealthStatus:
        """Check SimpleMem API health."""
        start = time.time()

        try:
            result = await self._make_request("GET", "/health")
            latency = (time.time() - start) * 1000

            return HealthStatus(
                healthy=result.get("status") == "ok",
                provider="simplemem",
                latency_ms=latency,
                details=result,
            )

        except Exception as e:
            return HealthStatus(
                healthy=False,
                provider="simplemem",
                latency_ms=(time.time() - start) * 1000,
                details={"error": str(e)},
            )

    # =========================================================================
    # Commitment Operations
    # =========================================================================
    # SimpleMem doesn't have native commitment support, so we store them
    # as regular memories with a special prefix and metadata.

    async def add_commitment(
        self,
        content: str,
        user_id: str,
        target_person: str | None = None,
        due_date: datetime | None = None,
        source_channel: str | None = None,
        source_message_id: str | None = None,
    ) -> str:
        """Add a commitment (stored as a memory with special metadata)."""
        commitment_id = str(uuid.uuid4())

        metadata = {
            "commitment_id": commitment_id,
            "target_person": target_person,
            "due_date": due_date.isoformat() if due_date else None,
            "source_channel": source_channel,
            "source_message_id": source_message_id,
            "status": "active",
            "is_commitment": True,
        }

        await self.add(
            content=f"{self._commitment_prefix}{content}",
            type=MemoryType.TASK,
            importance=8,  # Commitments are high importance
            source=MemorySource.USER,
            metadata=metadata,
            user_id=user_id,
        )

        return commitment_id

    async def list_commitments(
        self,
        user_id: str,
        status: str = "active",
        include_overdue: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List commitments from memory."""
        # Search for commitment memories
        filters = SearchFilters(
            types=[MemoryType.TASK],
            user_id=user_id,
        )

        entries = await self.list(filters=filters, limit=limit * 2)

        commitments = []
        for entry in entries:
            if not entry.metadata.get("is_commitment"):
                continue

            entry_status = entry.metadata.get("status", "active")
            if status != "all" and entry_status != status:
                continue

            # Remove prefix from content
            content = entry.content
            if content.startswith(self._commitment_prefix):
                content = content[len(self._commitment_prefix):]

            commitment = {
                "id": entry.metadata.get("commitment_id", entry.id),
                "content": content,
                "target_person": entry.metadata.get("target_person"),
                "due_date": entry.metadata.get("due_date"),
                "status": entry_status,
                "source_channel": entry.metadata.get("source_channel"),
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
            commitments.append(commitment)

            if len(commitments) >= limit:
                break

        return commitments

    async def complete_commitment(self, id: str, notes: str | None = None) -> bool:
        """Mark a commitment as completed."""
        # Search for the commitment
        entries = await self.list(limit=1000)

        for entry in entries:
            if entry.metadata.get("commitment_id") == id:
                # Update metadata
                new_metadata = dict(entry.metadata)
                new_metadata["status"] = "completed"
                new_metadata["completed_at"] = datetime.utcnow().isoformat()
                if notes:
                    new_metadata["completion_notes"] = notes

                return await self.update(
                    entry.id,
                    metadata=new_metadata,
                )

        logger.warning(f"Commitment {id} not found")
        return False

    async def cancel_commitment(self, id: str, reason: str | None = None) -> bool:
        """Cancel a commitment."""
        entries = await self.list(limit=1000)

        for entry in entries:
            if entry.metadata.get("commitment_id") == id:
                new_metadata = dict(entry.metadata)
                new_metadata["status"] = "cancelled"
                new_metadata["cancelled_at"] = datetime.utcnow().isoformat()
                if reason:
                    new_metadata["cancel_reason"] = reason

                return await self.update(
                    entry.id,
                    metadata=new_metadata,
                )

        logger.warning(f"Commitment {id} not found")
        return False

    # =========================================================================
    # Context Operations
    # =========================================================================
    # SimpleMem doesn't have native context support, so we store them
    # as regular memories with a special prefix and metadata.

    async def capture_context(
        self,
        user_id: str,
        state: dict[str, Any],
        trigger: str = "manual",
        summary: str | None = None,
    ) -> str:
        """Capture context snapshot (stored as a memory)."""
        context_id = str(uuid.uuid4())

        # Build content summary
        content_parts = [f"{self._context_prefix}Context snapshot"]
        if summary:
            content_parts.append(f": {summary}")
        if state.get("next_step"):
            content_parts.append(f" | Next: {state['next_step']}")
        if state.get("active_file"):
            content_parts.append(f" | File: {state['active_file']}")

        content = "".join(content_parts)

        metadata = {
            "context_id": context_id,
            "trigger": trigger,
            "state": state,
            "summary": summary,
            "is_context": True,
            "captured_at": datetime.utcnow().isoformat(),
        }

        await self.add(
            content=content,
            type=MemoryType.EVENT,
            importance=6,
            source=MemorySource.SYSTEM,
            metadata=metadata,
            user_id=user_id,
        )

        return context_id

    async def resume_context(
        self,
        user_id: str,
        snapshot_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get context for resumption."""
        filters = SearchFilters(
            types=[MemoryType.EVENT],
            user_id=user_id,
        )

        entries = await self.list(filters=filters, limit=100)

        # Find context entries
        for entry in entries:
            if not entry.metadata.get("is_context"):
                continue

            if snapshot_id and entry.metadata.get("context_id") != snapshot_id:
                continue

            # Found a context snapshot
            return {
                "id": entry.metadata.get("context_id"),
                "state": entry.metadata.get("state", {}),
                "summary": entry.metadata.get("summary"),
                "trigger": entry.metadata.get("trigger"),
                "captured_at": entry.metadata.get("captured_at"),
                "next_step": entry.metadata.get("state", {}).get("next_step"),
                "active_file": entry.metadata.get("state", {}).get("active_file"),
            }

        return None

    async def list_contexts(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List context snapshots."""
        filters = SearchFilters(
            types=[MemoryType.EVENT],
            user_id=user_id,
        )

        entries = await self.list(filters=filters, limit=limit * 2)

        contexts = []
        for entry in entries:
            if not entry.metadata.get("is_context"):
                continue

            contexts.append({
                "id": entry.metadata.get("context_id"),
                "summary": entry.metadata.get("summary"),
                "trigger": entry.metadata.get("trigger"),
                "captured_at": entry.metadata.get("captured_at"),
            })

            if len(contexts) >= limit:
                break

        return contexts

    async def delete_context(self, snapshot_id: str) -> bool:
        """Delete a context snapshot."""
        entries = await self.list(limit=1000)

        for entry in entries:
            if entry.metadata.get("context_id") == snapshot_id:
                return await self.delete(entry.id)

        logger.warning(f"Context {snapshot_id} not found")
        return False
