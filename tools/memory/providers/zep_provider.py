"""
Zep Memory Provider

Memory provider using Zep (https://www.getzep.com) for temporal knowledge graph.
Supports both cloud-hosted and self-hosted deployments.

Features:
    - Temporal knowledge graph (bi-temporal modeling)
    - Relationship-aware memory
    - Entity extraction
    - Automatic fact organization

Deployment Modes:
    - CLOUD: API-key based, no infrastructure (zep-cloud package)
    - SELF_HOSTED: Requires Neo4j 5.26+ (zep-python package)

Documentation: https://docs.getzep.com
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


class ZepProvider(MemoryProvider):
    """
    Zep memory provider.

    Zep provides temporal knowledge graph with automatic fact extraction.
    Supports cloud (API key) or self-hosted (Neo4j) deployments.

    Configuration:
        - mode: 'cloud' or 'self_hosted'
        - api_key: Zep API key (required for both modes)
        - api_url: Zep API URL (self-hosted mode)
        - project_id: Zep project ID (cloud mode)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize Zep provider.

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

        # API configuration
        self._api_key = config.get("api_key") or os.getenv("ZEP_API_KEY")
        self._api_url = config.get("api_url") or os.getenv("ZEP_API_URL")
        self._project_id = config.get("project_id") or os.getenv("ZEP_PROJECT_ID")

        # Zep client (lazy init)
        self._client = None
        self._default_user_id = config.get("user_id", "default")

    @property
    def name(self) -> str:
        return "zep"

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
        """Get or create Zep client."""
        if self._client is not None:
            return self._client

        try:
            if self._deployment_mode == DeploymentMode.CLOUD:
                # Cloud mode - use zep-cloud
                try:
                    from zep_cloud.client import Zep
                    if not self._api_key:
                        raise ValueError("ZEP_API_KEY required for cloud mode")
                    self._client = Zep(api_key=self._api_key)
                except ImportError:
                    raise ImportError(
                        "Zep cloud requires zep-cloud package. Install with: pip install zep-cloud"
                    )
            else:
                # Self-hosted mode - use zep-python
                try:
                    from zep_python import ZepClient
                    if not self._api_url:
                        self._api_url = "http://localhost:8000"
                    self._client = ZepClient(
                        base_url=self._api_url,
                        api_key=self._api_key,
                    )
                except ImportError:
                    raise ImportError(
                        "Zep self-hosted requires zep-python package. Install with: pip install dexai[zep]"
                    )

            return self._client

        except ImportError as e:
            raise ImportError(
                "Zep requires zep-python or zep-cloud package. Install with: pip install dexai[zep]"
            ) from e

    def _get_session_id(self, user_id: str) -> str:
        """Get or create a session ID for a user."""
        # Use a consistent session ID per user for memory persistence
        return f"dexai_{user_id}"

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    async def check_dependencies(self) -> DependencyStatus:
        """Check Zep dependencies."""
        deps = {}
        missing = []

        # Check for zep package
        import importlib.util
        if self._deployment_mode == DeploymentMode.CLOUD:
            if importlib.util.find_spec("zep_cloud") is not None:
                deps["zep_cloud"] = True
            else:
                deps["zep_cloud"] = False
                missing.append("zep-cloud")
        else:
            if importlib.util.find_spec("zep_python") is not None:
                deps["zep_python"] = True
            else:
                deps["zep_python"] = False
                missing.append("zep-python")

        # Check API key
        if self._api_key:
            deps["api_key"] = True
        else:
            deps["api_key"] = False
            missing.append("ZEP_API_KEY")

        # For self-hosted, check API connectivity
        if self._deployment_mode == DeploymentMode.SELF_HOSTED and "ZEP_API_KEY" not in missing:
            try:
                import urllib.request
                api_url = self._api_url or "http://localhost:8000"
                with urllib.request.urlopen(f"{api_url}/healthz", timeout=5) as resp:
                    deps["api_connectivity"] = resp.status == 200
            except Exception:
                deps["api_connectivity"] = False
                missing.append("zep_api_connectivity")

        instructions = None
        if missing:
            if "zep-cloud" in missing:
                instructions = "Install Zep cloud: pip install zep-cloud"
            elif "zep-python" in missing:
                instructions = "Install Zep: pip install dexai[zep]"
            elif "ZEP_API_KEY" in missing:
                instructions = (
                    "Zep requires an API key. Get one at https://getzep.com\n"
                    "Then set: export ZEP_API_KEY=your-key"
                )
            elif "zep_api_connectivity" in missing:
                instructions = (
                    "Zep self-hosted API is not reachable.\n"
                    "Ensure Zep is running at: " + (self._api_url or "http://localhost:8000")
                )

        return DependencyStatus(
            ready=len(missing) == 0,
            dependencies=deps,
            missing=missing,
            instructions=instructions,
        )

    async def bootstrap(self) -> BootstrapResult:
        """Initialize Zep (auto-creates sessions)."""
        try:
            self._get_client()
            return BootstrapResult(
                success=True,
                message=f"Zep initialized ({self._deployment_mode.value} mode)",
                created=["session:default"],
            )
        except Exception as e:
            return BootstrapResult(
                success=False,
                message=f"Zep bootstrap failed: {e}",
                created=[],
            )

    async def deploy_local(self) -> DeployResult:
        """Zep self-hosted requires manual Neo4j setup."""
        if self._deployment_mode == DeploymentMode.CLOUD:
            return DeployResult(
                success=True,
                message="Zep cloud mode - no local deployment needed",
                services={},
            )

        # Self-hosted requires Neo4j
        return DeployResult(
            success=False,
            message=(
                "Zep self-hosted requires Neo4j 5.26+.\n"
                "Follow setup instructions at: https://docs.getzep.com/self-hosting"
            ),
            services={},
        )

    async def teardown(self) -> bool:
        """Clean up Zep client."""
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
        """Add a memory to Zep."""
        client = self._get_client()
        user_id = user_id or self._default_user_id
        session_id = self._get_session_id(user_id)

        # Build metadata
        mem_metadata = {
            "type": type.value if isinstance(type, MemoryType) else type,
            "source": source.value if isinstance(source, MemorySource) else source,
            "importance": importance,
            "tags": tags or [],
            **(metadata or {}),
        }

        memory_id = str(uuid.uuid4())

        try:
            if self._deployment_mode == DeploymentMode.CLOUD:
                # Zep Cloud API
                from zep_cloud.types import Message

                # Ensure user exists
                try:
                    client.user.get(user_id)
                except Exception:
                    client.user.add(user_id=user_id)

                # Add message to memory
                client.memory.add(
                    session_id=session_id,
                    messages=[
                        Message(
                            role="user" if source == MemorySource.USER else "assistant",
                            content=content,
                            metadata=mem_metadata,
                        )
                    ],
                )
            else:
                # Zep self-hosted API
                from zep_python import Message, Session

                # Ensure session exists
                try:
                    client.memory.get_session(session_id)
                except Exception:
                    client.memory.add_session(Session(session_id=session_id, user_id=user_id))

                # Add message
                client.memory.add_memory(
                    session_id=session_id,
                    memory_messages=[
                        Message(
                            role="user" if source == MemorySource.USER else "assistant",
                            content=content,
                            metadata=mem_metadata,
                        )
                    ],
                )

            return memory_id

        except Exception as e:
            logger.error(f"Zep add failed: {e}")
            raise ValueError(f"Zep add failed: {e}") from e

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: SearchFilters | None = None,
        search_type: str = "hybrid",
    ) -> list[MemoryEntry]:
        """Search memories using Zep."""
        client = self._get_client()
        user_id = (filters.user_id if filters else None) or self._default_user_id
        session_id = self._get_session_id(user_id)

        try:
            if self._deployment_mode == DeploymentMode.CLOUD:
                # Zep Cloud search
                results = client.memory.search(
                    session_id=session_id,
                    text=query,
                    limit=limit,
                    search_type="similarity",
                )
            else:
                # Zep self-hosted search
                from zep_python import SearchPayload

                results = client.memory.search_memory(
                    session_id=session_id,
                    search_payload=SearchPayload(
                        text=query,
                        search_type="similarity",
                    ),
                    limit=limit,
                )

            entries = []
            result_list = results if isinstance(results, list) else (results.results if hasattr(results, 'results') else [])

            for item in result_list:
                # Extract message from result
                message = getattr(item, 'message', item)
                metadata = getattr(message, 'metadata', {}) or {}

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

                content = getattr(message, 'content', str(message))
                score = getattr(item, 'score', 0.0) or getattr(item, 'dist', 0.0)

                entry = MemoryEntry(
                    id=getattr(message, 'uuid', str(uuid.uuid4())),
                    content=content,
                    type=memory_type,
                    source=memory_source,
                    importance=metadata.get("importance", 5),
                    tags=metadata.get("tags", []),
                    metadata=metadata,
                    score=float(score) if score else 0.0,
                    score_breakdown={"semantic": float(score) if score else 0.0},
                )
                entries.append(entry)

            return entries[:limit]

        except Exception as e:
            logger.warning(f"Zep search failed: {e}")
            return []

    async def get(self, id: str) -> MemoryEntry | None:
        """Get a specific memory by ID."""
        # Zep doesn't have a direct get-by-id for messages
        # Search across all memories is expensive, return None
        logger.debug(f"Zep get by ID not directly supported: {id}")
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
        # Zep doesn't support direct updates to messages
        logger.debug(f"Zep update not directly supported: {id}")
        return False

    async def delete(self, id: str, hard: bool = False) -> bool:
        """Delete a memory entry."""
        # Zep supports session deletion but not individual message deletion
        logger.debug(f"Zep individual delete not supported: {id}")
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
        session_id = self._get_session_id(user_id)

        try:
            if self._deployment_mode == DeploymentMode.CLOUD:
                # Zep Cloud - get session memory
                memory = client.memory.get(session_id=session_id)
                messages = memory.messages if hasattr(memory, 'messages') else []
            else:
                # Zep self-hosted
                memory = client.memory.get_memory(session_id=session_id)
                messages = memory.messages if hasattr(memory, 'messages') else []

            entries = []
            for message in messages[offset:offset + limit]:
                metadata = getattr(message, 'metadata', {}) or {}

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
                    id=getattr(message, 'uuid', str(uuid.uuid4())),
                    content=getattr(message, 'content', str(message)),
                    type=memory_type,
                    source=memory_source,
                    importance=metadata.get("importance", 5),
                    tags=metadata.get("tags", []),
                    metadata=metadata,
                )
                entries.append(entry)

            return entries

        except Exception as e:
            logger.warning(f"Zep list failed: {e}")
            return []

    async def health_check(self) -> HealthStatus:
        """Check Zep health."""
        start = time.time()

        try:
            client = self._get_client()

            # Try a simple operation
            if self._deployment_mode == DeploymentMode.CLOUD:
                # Cloud mode - check user (not found is OK)
                with contextlib.suppress(Exception):
                    client.user.get("__health_check__")
            else:
                # Self-hosted - check sessions (not found is OK)
                with contextlib.suppress(Exception):
                    client.memory.get_session("__health_check__")

            latency = (time.time() - start) * 1000

            return HealthStatus(
                healthy=True,
                provider="zep",
                latency_ms=latency,
                details={
                    "mode": self._deployment_mode.value,
                },
            )

        except Exception as e:
            return HealthStatus(
                healthy=False,
                provider="zep",
                latency_ms=(time.time() - start) * 1000,
                details={"error": str(e)},
            )

    # =========================================================================
    # Commitment Operations
    # =========================================================================
    # Zep doesn't have native commitment support, so we store them
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
        # Zep doesn't support updates, so we can't complete commitments
        logger.warning(f"Zep commitment complete not fully supported: {id}")
        return False

    async def cancel_commitment(self, id: str, reason: str | None = None) -> bool:
        """Cancel a commitment."""
        logger.warning(f"Zep commitment cancel not fully supported: {id}")
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
        # Zep doesn't support individual message deletion
        logger.warning(f"Zep context delete not supported: {snapshot_id}")
        return False
