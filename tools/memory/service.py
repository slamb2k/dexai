"""
Memory Service Facade

Central service that manages memory providers and applies ADHD-safe transformations.
This is the main entry point for all memory operations - MCP tools and SDK client
should use this instead of accessing providers directly.

Features:
    - Provider lifecycle management (check deps, bootstrap, teardown)
    - Automatic fallback to native provider on failures
    - ADHD-safe language filtering on all responses
    - Forward-facing framing for commitments/context
    - Configuration-driven provider selection

Usage:
    from tools.memory.service import MemoryService

    # Initialize with default config
    service = MemoryService()
    await service.initialize()

    # Or with custom config
    service = MemoryService(config_path="args/memory.yaml")
    await service.initialize()

    # Use the service
    entry_id = await service.add("User prefers dark mode", type=MemoryType.PREFERENCE)
    results = await service.search("user preferences")

    # Cleanup
    await service.shutdown()
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .providers.base import (
    DependencyStatus,
    HealthStatus,
    MemoryEntry,
    MemoryProvider,
    MemorySource,
    MemoryType,
    SearchFilters,
)


logger = logging.getLogger(__name__)

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "args" / "memory.yaml"


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand environment variables in config values."""
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            return os.getenv(env_var, "")
        return value
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load and parse memory configuration."""
    path = config_path or CONFIG_PATH
    if not path.exists():
        logger.warning(f"Config file not found: {path}, using defaults")
        return {"provider": {"active": "native"}}

    with open(path) as f:
        config = yaml.safe_load(f) or {}

    return _expand_env_vars(config)


class MemoryService:
    """
    Facade for memory operations with automatic provider management.

    Handles:
        - Provider initialization and lifecycle
        - Automatic fallback on failures
        - ADHD-safe transformations
        - Configuration management
    """

    def __init__(self, config_path: Path | str | None = None):
        """
        Initialize the memory service.

        Args:
            config_path: Path to memory.yaml config file
        """
        if config_path:
            config_path = Path(config_path)
        self._config_path = config_path
        self._config: dict[str, Any] = {}
        self._provider: MemoryProvider | None = None
        self._fallback_provider: MemoryProvider | None = None
        self._initialized = False
        self._failure_count = 0
        self._using_fallback = False
        self._last_primary_attempt: datetime | None = None

    @property
    def provider(self) -> MemoryProvider:
        """Get the active provider."""
        if not self._initialized:
            raise RuntimeError("MemoryService not initialized. Call initialize() first.")
        if self._using_fallback and self._fallback_provider:
            return self._fallback_provider
        if self._provider is None:
            raise RuntimeError("No provider available")
        return self._provider

    @property
    def config(self) -> dict[str, Any]:
        """Get the current configuration."""
        return self._config

    @property
    def is_using_fallback(self) -> bool:
        """Check if currently using fallback provider."""
        return self._using_fallback

    async def initialize(self) -> bool:
        """
        Initialize the service and provider.

        Returns:
            True if initialization successful
        """
        # Load configuration
        self._config = load_config(self._config_path)

        # Get active provider name
        provider_config = self._config.get("provider", {})
        active_provider = provider_config.get("active", "native")

        logger.info(f"Initializing memory service with provider: {active_provider}")

        # Initialize primary provider
        try:
            self._provider = await self._create_provider(active_provider)

            # Check dependencies
            deps = await self._provider.check_dependencies()
            if not deps.ready:
                logger.warning(
                    f"Provider {active_provider} has missing dependencies: {deps.missing}"
                )
                if deps.instructions:
                    logger.info(f"Setup instructions: {deps.instructions}")

                # Try fallback if configured
                if self._should_use_fallback():
                    return await self._activate_fallback()

                return False

            # Bootstrap provider
            result = await self._provider.bootstrap()
            if not result.success:
                logger.error(f"Provider bootstrap failed: {result.message}")
                if self._should_use_fallback():
                    return await self._activate_fallback()
                return False

            self._initialized = True
            logger.info(f"Memory service initialized with {active_provider} provider")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize provider {active_provider}: {e}")
            if self._should_use_fallback():
                return await self._activate_fallback()
            return False

    async def _create_provider(self, name: str) -> MemoryProvider:
        """Create a provider instance by name."""
        provider_config = self._config.get("provider", {}).get(name, {})

        if name == "native":
            from .providers.native import NativeProvider

            return NativeProvider(provider_config)

        elif name == "mem0":
            from .providers.mem0_provider import Mem0Provider

            return Mem0Provider(provider_config)

        elif name == "zep":
            from .providers.zep_provider import ZepProvider

            return ZepProvider(provider_config)

        elif name == "simplemem":
            from .providers.simplemem_provider import SimpleMemProvider

            return SimpleMemProvider(provider_config)

        elif name == "claudemem":
            from .providers.claudemem_provider import ClaudeMemProvider

            return ClaudeMemProvider(provider_config)

        else:
            raise ValueError(f"Unknown provider: {name}")

    def _should_use_fallback(self) -> bool:
        """Check if fallback should be used."""
        fallback_config = self._config.get("fallback", {})
        return fallback_config.get("enabled", True)

    async def _activate_fallback(self) -> bool:
        """Activate the fallback provider."""
        fallback_config = self._config.get("fallback", {})
        fallback_name = fallback_config.get("provider", "native")

        if fallback_config.get("log_fallback", True):
            logger.warning(f"Activating fallback provider: {fallback_name}")

        try:
            self._fallback_provider = await self._create_provider(fallback_name)
            deps = await self._fallback_provider.check_dependencies()

            if not deps.ready:
                logger.error(f"Fallback provider {fallback_name} also not ready")
                return False

            await self._fallback_provider.bootstrap()
            self._using_fallback = True
            self._initialized = True
            self._last_primary_attempt = datetime.now()
            return True

        except Exception as e:
            logger.error(f"Failed to initialize fallback provider: {e}")
            return False

    async def _maybe_retry_primary(self) -> None:
        """Check if we should retry the primary provider."""
        if not self._using_fallback:
            return

        fallback_config = self._config.get("fallback", {})
        retry_after = fallback_config.get("retry_primary_after", 300)

        if self._last_primary_attempt:
            elapsed = (datetime.now() - self._last_primary_attempt).total_seconds()
            if elapsed >= retry_after:
                logger.info("Attempting to reconnect to primary provider")
                self._last_primary_attempt = datetime.now()

                try:
                    if self._provider:
                        health = await self._provider.health_check()
                        if health.healthy:
                            logger.info("Primary provider recovered, switching back")
                            self._using_fallback = False
                            self._failure_count = 0
                except Exception:
                    pass  # Stay on fallback

    async def _handle_failure(self, error: Exception) -> None:
        """Handle provider failure."""
        self._failure_count += 1
        fallback_config = self._config.get("fallback", {})
        max_failures = fallback_config.get("max_failures", 3)

        logger.warning(f"Provider failure ({self._failure_count}/{max_failures}): {error}")

        if self._failure_count >= max_failures and self._should_use_fallback():
            await self._activate_fallback()

    def _apply_adhd_filter(self, text: str) -> str:
        """Apply ADHD-safe language filtering."""
        adhd_config = self._config.get("adhd", {})
        if not adhd_config.get("language_filter", True):
            return text

        # Import the language filter if available
        try:
            from tools.adhd.language_filter import filter_text

            return filter_text(text)
        except ImportError:
            return text

    def _format_commitment_adhd_safe(self, commitment: dict[str, Any]) -> dict[str, Any]:
        """Format commitment with ADHD-safe framing."""
        adhd_config = self._config.get("adhd", {})
        if not adhd_config.get("forward_facing", True):
            return commitment

        # Add friendly description
        target = commitment.get("target_person", "someone")
        content = commitment.get("content", "")
        style = adhd_config.get("reminder_style", "gentle")

        if style == "gentle" and target:
            commitment["friendly_description"] = (
                f"{target} might appreciate hearing from you about: {content}"
            )
        elif style == "standard" and target:
            commitment["friendly_description"] = f"{target} is waiting on: {content}"
        elif style == "urgent" and target:
            commitment["friendly_description"] = f"The {content} for {target} is needed soon"
        else:
            commitment["friendly_description"] = f"You mentioned: {content}"

        return commitment

    async def shutdown(self) -> None:
        """Shutdown the service and cleanup providers."""
        if self._provider:
            try:
                await self._provider.teardown()
            except Exception as e:
                logger.error(f"Error during provider teardown: {e}")

        if self._fallback_provider:
            try:
                await self._fallback_provider.teardown()
            except Exception as e:
                logger.error(f"Error during fallback teardown: {e}")

        self._initialized = False

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
        await self._maybe_retry_primary()

        try:
            return await self.provider.add(
                content=content,
                type=type,
                importance=importance,
                source=source,
                tags=tags,
                metadata=metadata,
                user_id=user_id,
            )
        except Exception as e:
            await self._handle_failure(e)
            # Retry with potentially new provider
            return await self.provider.add(
                content=content,
                type=type,
                importance=importance,
                source=source,
                tags=tags,
                metadata=metadata,
                user_id=user_id,
            )

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: SearchFilters | None = None,
        search_type: str = "hybrid",
    ) -> list[MemoryEntry]:
        """Search memories."""
        await self._maybe_retry_primary()

        try:
            results = await self.provider.search(
                query=query,
                limit=limit,
                filters=filters,
                search_type=search_type,
            )

            # Apply ADHD filtering to content
            for entry in results:
                entry.content = self._apply_adhd_filter(entry.content)

            return results

        except Exception as e:
            await self._handle_failure(e)
            return await self.provider.search(
                query=query,
                limit=limit,
                filters=filters,
                search_type=search_type,
            )

    async def get(self, id: str) -> MemoryEntry | None:
        """Get a specific memory by ID."""
        await self._maybe_retry_primary()
        try:
            entry = await self.provider.get(id)
            if entry:
                entry.content = self._apply_adhd_filter(entry.content)
            return entry
        except Exception as e:
            await self._handle_failure(e)
            return await self.provider.get(id)

    async def update(
        self,
        id: str,
        content: str | None = None,
        importance: int | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update a memory entry."""
        await self._maybe_retry_primary()
        try:
            return await self.provider.update(
                id=id,
                content=content,
                importance=importance,
                tags=tags,
                metadata=metadata,
            )
        except Exception as e:
            await self._handle_failure(e)
            return await self.provider.update(
                id=id,
                content=content,
                importance=importance,
                tags=tags,
                metadata=metadata,
            )

    async def delete(self, id: str, hard: bool = False) -> bool:
        """Delete a memory entry."""
        await self._maybe_retry_primary()
        try:
            return await self.provider.delete(id, hard=hard)
        except Exception as e:
            await self._handle_failure(e)
            return await self.provider.delete(id, hard=hard)

    async def list(
        self,
        filters: SearchFilters | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """List memories with optional filtering."""
        await self._maybe_retry_primary()
        try:
            return await self.provider.list(
                filters=filters,
                limit=limit,
                offset=offset,
            )
        except Exception as e:
            await self._handle_failure(e)
            return await self.provider.list(
                filters=filters,
                limit=limit,
                offset=offset,
            )

    async def health_check(self) -> HealthStatus:
        """Check provider health."""
        try:
            return await self.provider.health_check()
        except Exception as e:
            return HealthStatus(
                healthy=False,
                provider=self.provider.name if self._provider else "unknown",
                latency_ms=-1,
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
        """Add a commitment/promise."""
        await self._maybe_retry_primary()
        try:
            return await self.provider.add_commitment(
                content=content,
                user_id=user_id,
                target_person=target_person,
                due_date=due_date,
                source_channel=source_channel,
                source_message_id=source_message_id,
            )
        except Exception as e:
            await self._handle_failure(e)
            return await self.provider.add_commitment(
                content=content,
                user_id=user_id,
                target_person=target_person,
                due_date=due_date,
                source_channel=source_channel,
                source_message_id=source_message_id,
            )

    async def list_commitments(
        self,
        user_id: str,
        status: str = "active",
        include_overdue: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List commitments with ADHD-safe framing."""
        await self._maybe_retry_primary()
        try:
            commitments = await self.provider.list_commitments(
                user_id=user_id,
                status=status,
                include_overdue=include_overdue,
                limit=limit,
            )

            # Apply ADHD-safe formatting
            return [self._format_commitment_adhd_safe(c) for c in commitments]

        except Exception as e:
            await self._handle_failure(e)
            commitments = await self.provider.list_commitments(
                user_id=user_id,
                status=status,
                include_overdue=include_overdue,
                limit=limit,
            )
            return [self._format_commitment_adhd_safe(c) for c in commitments]

    async def complete_commitment(self, id: str, notes: str | None = None) -> bool:
        """Mark a commitment as completed."""
        await self._maybe_retry_primary()
        try:
            return await self.provider.complete_commitment(id, notes=notes)
        except Exception as e:
            await self._handle_failure(e)
            return await self.provider.complete_commitment(id, notes=notes)

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
        """Capture current context snapshot."""
        await self._maybe_retry_primary()
        try:
            return await self.provider.capture_context(
                user_id=user_id,
                state=state,
                trigger=trigger,
                summary=summary,
            )
        except Exception as e:
            await self._handle_failure(e)
            return await self.provider.capture_context(
                user_id=user_id,
                state=state,
                trigger=trigger,
                summary=summary,
            )

    async def resume_context(
        self,
        user_id: str,
        snapshot_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get context for resumption with ADHD-friendly framing."""
        await self._maybe_retry_primary()
        try:
            context = await self.provider.resume_context(
                user_id=user_id,
                snapshot_id=snapshot_id,
            )

            if context:
                # Apply ADHD-safe filtering to any text content
                if "resumption_prompt" in context:
                    context["resumption_prompt"] = self._apply_adhd_filter(
                        context["resumption_prompt"]
                    )

            return context

        except Exception as e:
            await self._handle_failure(e)
            return await self.provider.resume_context(
                user_id=user_id,
                snapshot_id=snapshot_id,
            )

    async def list_contexts(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List available context snapshots."""
        await self._maybe_retry_primary()
        try:
            return await self.provider.list_contexts(user_id=user_id, limit=limit)
        except Exception as e:
            await self._handle_failure(e)
            return await self.provider.list_contexts(user_id=user_id, limit=limit)

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def get_stats(self, user_id: str | None = None) -> dict[str, Any]:
        """Get memory statistics."""
        try:
            stats = await self.provider.get_stats(user_id=user_id)
            stats["using_fallback"] = self._using_fallback
            stats["failure_count"] = self._failure_count
            return stats
        except Exception as e:
            return {
                "error": str(e),
                "using_fallback": self._using_fallback,
                "failure_count": self._failure_count,
            }

    async def check_dependencies(self) -> DependencyStatus:
        """Check provider dependencies."""
        if self._provider:
            return await self._provider.check_dependencies()
        return DependencyStatus(
            ready=False,
            dependencies={},
            missing=["provider"],
            instructions="Initialize the service first",
        )


# Singleton instance for easy access
_service_instance: MemoryService | None = None


async def get_memory_service() -> MemoryService:
    """Get or create the global memory service instance."""
    global _service_instance

    if _service_instance is None:
        _service_instance = MemoryService()
        await _service_instance.initialize()

    return _service_instance


async def shutdown_memory_service() -> None:
    """Shutdown the global memory service."""
    global _service_instance

    if _service_instance:
        await _service_instance.shutdown()
        _service_instance = None
