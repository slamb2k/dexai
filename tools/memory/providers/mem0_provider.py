"""
Mem0 Memory Provider

Memory provider using Mem0 (https://mem0.ai) for graph-based memory.
Supports both cloud-hosted and self-hosted deployments.

Features:
    - Graph-based memory with relationships
    - Automatic memory organization
    - Multi-user support
    - Cloud or self-hosted options

Deployment Modes:
    - CLOUD: API-key based, no infrastructure (default)
    - SELF_HOSTED: Requires Qdrant or compatible vector store

Documentation: https://docs.mem0.ai
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
import uuid
from datetime import datetime
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


class Mem0Provider(MemoryProvider):
    """
    Mem0 memory provider.

    Mem0 provides graph-based memory with automatic organization.
    Supports cloud (API key) or self-hosted (Qdrant) deployments.

    Configuration:
        - mode: 'cloud' or 'self_hosted'
        - api_key: Mem0 API key (cloud mode)
        - org_id, project_id: Mem0 organization/project (cloud mode)
        - base_url: Self-hosted API URL (self-hosted mode)
        - vector_store: Vector store config for self-hosted
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize Mem0 provider.

        Args:
            config: Provider configuration from args/memory.yaml
        """
        config = config or {}
        self._config = config

        # Deployment mode
        mode = config.get("mode", "cloud")
        if mode == "cloud":
            self._deployment_mode = DeploymentMode.CLOUD
        else:
            self._deployment_mode = DeploymentMode.SELF_HOSTED

        # Cloud configuration
        self._api_key = config.get("api_key") or os.getenv("MEM0_API_KEY")
        self._org_id = config.get("org_id") or os.getenv("MEM0_ORG_ID")
        self._project_id = config.get("project_id") or os.getenv("MEM0_PROJECT_ID")

        # Self-hosted configuration
        self._base_url = config.get("base_url") or os.getenv("MEM0_BASE_URL")
        self._vector_store_config = config.get("vector_store", {})

        # Mem0 client (lazy init)
        self._client = None
        self._default_user_id = config.get("user_id", "default")

    @property
    def name(self) -> str:
        return "mem0"

    @property
    def deployment_mode(self) -> DeploymentMode:
        return self._deployment_mode

    @property
    def supports_cloud(self) -> bool:
        return True

    @property
    def supports_self_hosted(self) -> bool:
        return True

    @property
    def supports_local(self) -> bool:
        return False

    def _get_client(self):
        """Get or create Mem0 client."""
        if self._client is not None:
            return self._client

        try:
            from mem0 import Memory, MemoryClient

            if self._deployment_mode == DeploymentMode.CLOUD:
                # Cloud mode - use MemoryClient
                if not self._api_key:
                    raise ValueError("MEM0_API_KEY required for cloud mode")

                self._client = MemoryClient(api_key=self._api_key)
            else:
                # Self-hosted mode - use Memory with config
                config = {
                    "version": "v1.1",
                }

                # Configure vector store
                if self._vector_store_config:
                    vs_provider = self._vector_store_config.get("provider", "qdrant")
                    vs_config = self._vector_store_config.get("config", {})

                    config["vector_store"] = {
                        "provider": vs_provider,
                        "config": vs_config,
                    }

                # Configure embedder (default to OpenAI)
                embedder_config = self._config.get("embedder", {})
                if embedder_config:
                    config["embedder"] = embedder_config
                else:
                    openai_key = os.getenv("OPENAI_API_KEY")
                    if openai_key:
                        config["embedder"] = {
                            "provider": "openai",
                            "config": {
                                "model": "text-embedding-3-small",
                            },
                        }

                self._client = Memory.from_config(config)

            return self._client

        except ImportError as e:
            raise ImportError(
                "Mem0 requires mem0ai package. Install with: pip install dexai[mem0]"
            ) from e

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    async def check_dependencies(self) -> DependencyStatus:
        """Check Mem0 dependencies."""
        deps = {}
        missing = []

        # Check for mem0 package
        import importlib.util
        if importlib.util.find_spec("mem0") is not None:
            deps["mem0"] = True
        else:
            deps["mem0"] = False
            missing.append("mem0ai")

        if self._deployment_mode == DeploymentMode.CLOUD:
            # Cloud mode - check API key
            if self._api_key:
                deps["api_key"] = True
            else:
                deps["api_key"] = False
                missing.append("MEM0_API_KEY")
        else:
            # Self-hosted - check vector store
            vs_provider = self._vector_store_config.get("provider", "qdrant")

            if vs_provider == "qdrant":
                # Check Qdrant connectivity
                qdrant_url = self._vector_store_config.get("config", {}).get("url", "http://localhost:6333")

                # Sync check (can't use async in property)
                import urllib.request
                try:
                    with urllib.request.urlopen(f"{qdrant_url}/health", timeout=5) as resp:
                        deps["qdrant"] = resp.status == 200
                except Exception:
                    deps["qdrant"] = False
                    missing.append("qdrant")

            # Check OpenAI for embeddings
            openai_key = os.getenv("OPENAI_API_KEY")
            deps["openai"] = bool(openai_key)
            if not openai_key:
                missing.append("OPENAI_API_KEY")

        instructions = None
        if missing:
            if "mem0ai" in missing:
                instructions = "Install Mem0: pip install dexai[mem0]"
            elif "MEM0_API_KEY" in missing:
                instructions = (
                    "Mem0 cloud requires an API key. Get one at https://mem0.ai\n"
                    "Then set: export MEM0_API_KEY=your-key"
                )
            elif "qdrant" in missing:
                instructions = (
                    "Mem0 self-hosted requires Qdrant.\n"
                    "Run: docker run -p 6333:6333 qdrant/qdrant"
                )

        return DependencyStatus(
            ready=len(missing) == 0,
            dependencies=deps,
            missing=missing,
            instructions=instructions,
        )

    async def bootstrap(self) -> BootstrapResult:
        """Initialize Mem0 (auto-creates collections)."""
        try:
            self._get_client()
            return BootstrapResult(
                success=True,
                message=f"Mem0 initialized ({self._deployment_mode.value} mode)",
                created=["collection:memories"],
            )
        except Exception as e:
            return BootstrapResult(
                success=False,
                message=f"Mem0 bootstrap failed: {e}",
                created=[],
            )

    async def deploy_local(self) -> DeployResult:
        """Deploy local Qdrant for self-hosted mode."""
        if self._deployment_mode == DeploymentMode.CLOUD:
            return DeployResult(
                success=True,
                message="Mem0 cloud mode - no local deployment needed",
                services={},
            )

        try:
            import subprocess

            # Check if Qdrant is already running
            qdrant_url = self._vector_store_config.get("config", {}).get("url", "http://localhost:6333")

            import urllib.request
            try:
                with urllib.request.urlopen(f"{qdrant_url}/health", timeout=5) as resp:
                    if resp.status == 200:
                        return DeployResult(
                            success=True,
                            message="Qdrant already running",
                            services={"qdrant": qdrant_url},
                        )
            except Exception:
                pass

            # Start Qdrant container
            result = subprocess.run(
                [
                    "docker", "run", "-d",
                    "--name", "dexai-qdrant",
                    "-p", "6333:6333",
                    "-p", "6334:6334",
                    "qdrant/qdrant",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # Wait for Qdrant to be ready
                import time
                for _ in range(30):
                    try:
                        with urllib.request.urlopen(f"{qdrant_url}/health", timeout=2):
                            return DeployResult(
                                success=True,
                                message="Qdrant started",
                                services={"qdrant": qdrant_url},
                            )
                    except Exception:
                        time.sleep(1)

            return DeployResult(
                success=False,
                message=f"Failed to start Qdrant: {result.stderr}",
                services={},
            )

        except Exception as e:
            return DeployResult(
                success=False,
                message=f"Qdrant deployment failed: {e}",
                services={},
            )

    async def teardown(self) -> bool:
        """Clean up Mem0 client."""
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
        """Add a memory to Mem0."""
        client = self._get_client()
        user_id = user_id or self._default_user_id

        # Build metadata for Mem0
        mem_metadata = {
            "type": type.value if isinstance(type, MemoryType) else type,
            "source": source.value if isinstance(source, MemorySource) else source,
            "importance": importance,
            "tags": tags or [],
            **(metadata or {}),
        }

        # Add memory
        result = client.add(
            messages=[{"role": "user", "content": content}],
            user_id=user_id,
            metadata=mem_metadata,
        )

        # Extract memory ID from result
        if isinstance(result, dict):
            memories = result.get("results", [])
            if memories:
                return memories[0].get("id", str(uuid.uuid4()))
        elif isinstance(result, list) and result:
            return result[0].get("id", str(uuid.uuid4()))

        return str(uuid.uuid4())

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: SearchFilters | None = None,
        search_type: str = "hybrid",
    ) -> list[MemoryEntry]:
        """Search memories using Mem0."""
        client = self._get_client()
        user_id = (filters.user_id if filters else None) or self._default_user_id

        # Search memories
        results = client.search(
            query=query,
            user_id=user_id,
            limit=limit,
        )

        entries = []
        memories = results.get("results", []) if isinstance(results, dict) else results

        for item in memories:
            metadata = item.get("metadata", {})

            # Parse type
            type_str = metadata.get("type", "fact")
            try:
                memory_type = MemoryType(type_str)
            except ValueError:
                memory_type = MemoryType.FACT

            # Parse source
            source_str = metadata.get("source", "session")
            try:
                memory_source = MemorySource(source_str)
            except ValueError:
                memory_source = MemorySource.SESSION

            # Apply filters if specified
            if filters and filters.types:
                filter_types = [
                    t.value if isinstance(t, MemoryType) else t
                    for t in filters.types
                ]
                if memory_type.value not in filter_types:
                    continue

            if filters and filters.min_importance and metadata.get("importance", 5) < filters.min_importance:
                continue

            entry = MemoryEntry(
                id=item.get("id", ""),
                content=item.get("memory", item.get("text", "")),
                type=memory_type,
                source=memory_source,
                importance=metadata.get("importance", 5),
                tags=metadata.get("tags", []),
                metadata=metadata,
                score=item.get("score", 0.0),
                score_breakdown={"semantic": item.get("score", 0.0)},
            )
            entries.append(entry)

        return entries[:limit]

    async def get(self, id: str) -> MemoryEntry | None:
        """Get a specific memory by ID."""
        client = self._get_client()

        try:
            result = client.get(id)

            if not result:
                return None

            metadata = result.get("metadata", {})

            type_str = metadata.get("type", "fact")
            try:
                memory_type = MemoryType(type_str)
            except ValueError:
                memory_type = MemoryType.FACT

            source_str = metadata.get("source", "session")
            try:
                memory_source = MemorySource(source_str)
            except ValueError:
                memory_source = MemorySource.SESSION

            created_at = datetime.utcnow()
            if result.get("created_at"):
                with contextlib.suppress(ValueError, TypeError):
                    created_at = datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))

            return MemoryEntry(
                id=result.get("id", id),
                content=result.get("memory", result.get("text", "")),
                type=memory_type,
                source=memory_source,
                importance=metadata.get("importance", 5),
                tags=metadata.get("tags", []),
                metadata=metadata,
                created_at=created_at,
            )

        except Exception as e:
            logger.debug(f"Mem0 get failed for {id}: {e}")
            return None

    async def update(
        self,
        id: str,
        content: str | None = None,
        importance: int | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update a memory entry."""
        client = self._get_client()

        try:
            # Get existing memory
            existing = await self.get(id)
            if not existing:
                return False

            # Build updated metadata
            new_metadata = dict(existing.metadata)
            if importance is not None:
                new_metadata["importance"] = importance
            if tags is not None:
                new_metadata["tags"] = tags
            if metadata is not None:
                new_metadata.update(metadata)

            # Update in Mem0
            client.update(
                memory_id=id,
                data=content or existing.content,
                metadata=new_metadata,
            )
            return True

        except Exception as e:
            logger.error(f"Mem0 update failed for {id}: {e}")
            return False

    async def delete(self, id: str, hard: bool = False) -> bool:
        """Delete a memory entry."""
        client = self._get_client()

        try:
            client.delete(memory_id=id)
            return True
        except Exception as e:
            logger.error(f"Mem0 delete failed for {id}: {e}")
            return False

    async def list(
        self,
        filters: SearchFilters | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """List memories with optional filtering."""
        client = self._get_client()
        user_id = (filters.user_id if filters else None) or self._default_user_id

        try:
            results = client.get_all(user_id=user_id)

            memories = results.get("results", []) if isinstance(results, dict) else results

            entries = []
            for item in memories[offset:offset + limit]:
                metadata = item.get("metadata", {})

                type_str = metadata.get("type", "fact")
                try:
                    memory_type = MemoryType(type_str)
                except ValueError:
                    memory_type = MemoryType.FACT

                source_str = metadata.get("source", "session")
                try:
                    memory_source = MemorySource(source_str)
                except ValueError:
                    memory_source = MemorySource.SESSION

                # Apply filters
                if filters and filters.types:
                    filter_types = [
                        t.value if isinstance(t, MemoryType) else t
                        for t in filters.types
                    ]
                    if memory_type.value not in filter_types:
                        continue

                if filters and filters.min_importance and metadata.get("importance", 5) < filters.min_importance:
                    continue

                entry = MemoryEntry(
                    id=item.get("id", ""),
                    content=item.get("memory", item.get("text", "")),
                    type=memory_type,
                    source=memory_source,
                    importance=metadata.get("importance", 5),
                    tags=metadata.get("tags", []),
                    metadata=metadata,
                )
                entries.append(entry)

            return entries

        except Exception as e:
            logger.warning(f"Mem0 list failed: {e}")
            return []

    async def health_check(self) -> HealthStatus:
        """Check Mem0 health."""
        start = time.time()

        try:
            client = self._get_client()

            # Try a simple operation
            client.get_all(user_id="__health_check__", limit=1)
            latency = (time.time() - start) * 1000

            return HealthStatus(
                healthy=True,
                provider="mem0",
                latency_ms=latency,
                details={
                    "mode": self._deployment_mode.value,
                },
            )

        except Exception as e:
            return HealthStatus(
                healthy=False,
                provider="mem0",
                latency_ms=(time.time() - start) * 1000,
                details={"error": str(e)},
            )

    # =========================================================================
    # Commitment Operations
    # =========================================================================
    # Mem0 doesn't have native commitment support, so we store them
    # as memories with special metadata.

    async def add_commitment(
        self,
        content: str,
        user_id: str,
        target_person: str | None = None,
        due_date: datetime | None = None,
        source_channel: str | None = None,
        source_message_id: str | None = None,
    ) -> str:
        """Add a commitment (stored as a memory)."""
        commitment_id = str(uuid.uuid4())

        metadata = {
            "is_commitment": True,
            "commitment_id": commitment_id,
            "target_person": target_person,
            "due_date": due_date.isoformat() if due_date else None,
            "source_channel": source_channel,
            "source_message_id": source_message_id,
            "status": "active",
        }

        await self.add(
            content=f"COMMITMENT: {content}",
            type=MemoryType.TASK,
            importance=8,
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
        """List commitments."""
        # Search for commitment memories
        entries = await self.list(
            filters=SearchFilters(
                types=[MemoryType.TASK],
                user_id=user_id,
            ),
            limit=limit * 2,
        )

        commitments = []
        for entry in entries:
            if not entry.metadata.get("is_commitment"):
                continue

            entry_status = entry.metadata.get("status", "active")
            if status != "all" and entry_status != status:
                continue

            # Clean up content
            content = entry.content
            if content.startswith("COMMITMENT: "):
                content = content[12:]

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
        entries = await self.list(limit=1000)

        for entry in entries:
            if entry.metadata.get("commitment_id") == id:
                new_metadata = dict(entry.metadata)
                new_metadata["status"] = "completed"
                new_metadata["completed_at"] = datetime.utcnow().isoformat()
                if notes:
                    new_metadata["completion_notes"] = notes

                return await self.update(entry.id, metadata=new_metadata)

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

                return await self.update(entry.id, metadata=new_metadata)

        return False

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
        """Capture context snapshot (stored as a memory)."""
        import json
        context_id = str(uuid.uuid4())

        # Build content summary
        content_parts = ["CONTEXT SNAPSHOT"]
        if summary:
            content_parts.append(f": {summary}")
        if state.get("next_step"):
            content_parts.append(f" | Next: {state['next_step']}")

        content = "".join(content_parts)

        metadata = {
            "is_context": True,
            "context_id": context_id,
            "trigger": trigger,
            "state": json.dumps(state),
            "summary": summary,
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
        import json

        entries = await self.list(
            filters=SearchFilters(
                types=[MemoryType.EVENT],
                user_id=user_id,
            ),
            limit=100,
        )

        for entry in entries:
            if not entry.metadata.get("is_context"):
                continue

            if snapshot_id and entry.metadata.get("context_id") != snapshot_id:
                continue

            # Parse state
            state = {}
            state_str = entry.metadata.get("state")
            if state_str:
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    state = json.loads(state_str)

            return {
                "id": entry.metadata.get("context_id"),
                "state": state,
                "summary": entry.metadata.get("summary"),
                "trigger": entry.metadata.get("trigger"),
                "captured_at": entry.metadata.get("captured_at"),
                "next_step": state.get("next_step"),
                "active_file": state.get("active_file"),
            }

        return None

    async def list_contexts(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List context snapshots."""
        entries = await self.list(
            filters=SearchFilters(
                types=[MemoryType.EVENT],
                user_id=user_id,
            ),
            limit=limit * 2,
        )

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

        return False
