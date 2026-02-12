"""
Memory Daemon — Background Memory Processing

A lightweight background process that handles all non-blocking memory operations.
Runs as part of the DexAI backend, not as a separate service.

Components:
- Extraction Queue: Processes conversation turns for memory extraction
- Consolidation Scheduler: Periodic clustering and summarization (L2 → L3)
- L1 Context Rebuilder: Cached user profile block for fast injection
- Health Monitor: Provider health, queue depth, latency tracking

See: goals/memory_context_compaction_design.md §5.1

Usage:
    from tools.memory.daemon import MemoryDaemon, get_daemon

    daemon = get_daemon()
    await daemon.start()

    # Enqueue a conversation turn
    from tools.memory.extraction.queue import ConversationTurn
    turn = ConversationTurn(user_message="...", assistant_response="...", user_id="alice")
    await daemon.enqueue_turn(turn)

    # Shutdown gracefully
    await daemon.stop()
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from tools.memory.extraction.queue import ExtractionQueue, ConversationTurn

logger = logging.getLogger(__name__)


class MemoryDaemon:
    """
    Background daemon for memory lifecycle operations.

    Manages the extraction queue, consolidation scheduler, L1 rebuilder,
    and health monitoring. Designed to run as part of the DexAI backend.
    """

    def __init__(
        self,
        config: dict | None = None,
    ):
        """
        Initialize the memory daemon.

        Args:
            config: Optional config dict (extraction, consolidation settings).
                   If None, loads from args/memory.yaml.
        """
        self._config = config or self._load_config()
        self._provider = None
        self._extraction_queue: ExtractionQueue | None = None
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._started_at: datetime | None = None

        # Consolidation scheduling
        extraction_cfg = self._config.get("extraction", {})
        consolidation_cfg = self._config.get("consolidation", {})

        self._consolidation_enabled = consolidation_cfg.get("enabled", True)
        self._consolidation_interval_hours = consolidation_cfg.get("interval_hours", 24)
        self._consolidation_preferred_hour = consolidation_cfg.get("preferred_hour", 3)
        self._last_consolidation: datetime | None = None

        # Health monitoring
        self._health_check_interval = 60  # seconds
        self._last_health_check: datetime | None = None
        self._provider_healthy = True

        # L1 cache
        self._l1_cache: dict[str, str] = {}  # user_id -> cached L1 block
        self._l1_cache_age: dict[str, datetime] = {}

    def _load_config(self) -> dict:
        """Load memory config from args/memory.yaml."""
        try:
            from pathlib import Path
            import yaml

            config_path = Path(__file__).parent.parent.parent / "args" / "memory.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            logger.debug(f"Failed to load memory config: {e}")
        return {}

    async def _ensure_provider(self) -> None:
        """Initialize the memory provider if not already set."""
        if self._provider is not None:
            return

        try:
            from tools.memory.service import MemoryService

            service = MemoryService()
            await service.initialize()
            self._provider = service
            logger.info(f"Memory daemon initialized with provider: {service.config.get('provider', {}).get('active', 'native')}")
        except Exception as e:
            logger.warning(f"Failed to initialize memory provider: {e}")

    async def start(self) -> None:
        """Start the daemon and all background tasks."""
        if self._running:
            logger.warning("Memory daemon already running")
            return

        self._running = True
        self._started_at = datetime.now()

        await self._ensure_provider()

        # Initialize extraction queue
        extraction_cfg = self._config.get("extraction", {})
        self._extraction_queue = ExtractionQueue(
            provider=self._provider,
            batch_size=extraction_cfg.get("batch_size", 5),
            flush_interval_seconds=extraction_cfg.get("flush_interval_seconds", 5.0),
            max_queue_size=extraction_cfg.get("max_queue_size", 1000),
            gate_threshold=extraction_cfg.get("gate_threshold", 0.3),
            extraction_model=extraction_cfg.get("extraction_model", "claude-haiku-4-5-20251001"),
        )

        # Recover any pending items from previous crash
        await self._extraction_queue.recover()

        # Start background tasks
        self._tasks.append(
            asyncio.create_task(self._extraction_queue.run(), name="extraction_queue")
        )

        if self._consolidation_enabled:
            self._tasks.append(
                asyncio.create_task(self._consolidation_loop(), name="consolidation")
            )

        self._tasks.append(
            asyncio.create_task(self._health_loop(), name="health_monitor")
        )

        logger.info(
            f"Memory daemon started with {len(self._tasks)} background tasks"
        )

    async def stop(self) -> None:
        """Stop the daemon gracefully, flushing remaining work."""
        if not self._running:
            return

        self._running = False

        # Flush extraction queue
        if self._extraction_queue:
            flushed = await self._extraction_queue.flush()
            await self._extraction_queue.stop()
            if flushed > 0:
                logger.info(f"Flushed {flushed} remaining extraction jobs")

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()

        # Wait for all tasks to finish
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        logger.info("Memory daemon stopped")

    async def enqueue_turn(self, turn: ConversationTurn) -> bool:
        """
        Enqueue a conversation turn for background extraction.

        This is the primary interface used by hooks and channel handlers.

        Args:
            turn: Conversation turn to process

        Returns:
            True if enqueued, False if skipped
        """
        if not self._extraction_queue:
            logger.debug("Extraction queue not initialized, skipping")
            return False

        return await self._extraction_queue.enqueue(turn)

    async def flush_extraction(self) -> int:
        """Flush all pending extraction jobs immediately."""
        if not self._extraction_queue:
            return 0
        return await self._extraction_queue.flush()

    async def trigger_consolidation(self, user_id: str | None = None) -> dict:
        """
        Trigger memory consolidation immediately.

        Args:
            user_id: Optional user to consolidate for. If None, consolidate all.

        Returns:
            Dict with consolidation results
        """
        if not self._provider:
            return {"success": False, "error": "Provider not initialized"}

        return await self._run_consolidation(user_id)

    def invalidate_l1_cache(self, user_id: str | None = None) -> None:
        """
        Invalidate L1 cache for a user (or all users).

        Called after consolidation, compaction, or significant memory changes.

        Args:
            user_id: Specific user to invalidate, or None for all
        """
        if user_id:
            self._l1_cache.pop(user_id, None)
            self._l1_cache_age.pop(user_id, None)
        else:
            self._l1_cache.clear()
            self._l1_cache_age.clear()

    @property
    def stats(self) -> dict[str, Any]:
        """Get daemon statistics."""
        queue_stats = self._extraction_queue.stats if self._extraction_queue else {}
        return {
            "running": self._running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "uptime_seconds": (datetime.now() - self._started_at).total_seconds() if self._started_at else 0,
            "extraction_queue": queue_stats,
            "last_consolidation": self._last_consolidation.isoformat() if self._last_consolidation else None,
            "provider_healthy": self._provider_healthy,
            "l1_cache_entries": len(self._l1_cache),
            "tasks_count": len(self._tasks),
        }

    # =========================================================================
    # Background Loops
    # =========================================================================

    async def _consolidation_loop(self) -> None:
        """Periodic consolidation loop. Runs at configured interval."""
        while self._running:
            try:
                # Wait until the preferred hour
                await self._wait_for_consolidation_window()

                if not self._running:
                    break

                logger.info("Starting scheduled consolidation")
                result = await self._run_consolidation()
                self._last_consolidation = datetime.now()

                if result.get("success"):
                    logger.info(
                        f"Consolidation complete: {result.get('consolidated', 0)} clusters merged"
                    )
                else:
                    logger.warning(f"Consolidation failed: {result.get('error')}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consolidation loop error: {e}")
                await asyncio.sleep(3600)  # Retry in 1 hour

    async def _wait_for_consolidation_window(self) -> None:
        """Wait until the preferred consolidation window."""
        while self._running:
            now = datetime.now()

            # Check if we're in the preferred hour
            if now.hour == self._consolidation_preferred_hour:
                # Only run if we haven't run recently
                if self._last_consolidation is None or \
                   (now - self._last_consolidation).total_seconds() > self._consolidation_interval_hours * 3600:
                    return

            # Sleep for 15 minutes and check again
            await asyncio.sleep(900)

    async def _run_consolidation(self, user_id: str | None = None) -> dict:
        """
        Run memory consolidation.

        Clusters related L2 memories into denser L3 abstractions.

        Args:
            user_id: Optional user to consolidate for

        Returns:
            Dict with consolidation results
        """
        if not self._provider:
            return {"success": False, "error": "Provider not initialized"}

        try:
            consolidation_cfg = self._config.get("consolidation", {})
            min_cluster_size = consolidation_cfg.get("min_cluster_size", 3)
            cluster_similarity = consolidation_cfg.get("cluster_similarity", 0.85)
            min_age_days = consolidation_cfg.get("min_age_days", 7)

            # If provider supports consolidation directly, use it
            if hasattr(self._provider, "consolidate"):
                # Get memories eligible for consolidation
                memories = []
                if hasattr(self._provider, "list"):
                    from tools.memory.providers.base import SearchFilters
                    filters = SearchFilters(
                        created_before=datetime.now() - timedelta(days=min_age_days),
                    )
                    if user_id:
                        filters.user_id = user_id
                    memories = await self._provider.list(filters=filters, limit=500)

                if len(memories) < min_cluster_size:
                    return {"success": True, "consolidated": 0, "reason": "not enough memories"}

                # Simple clustering by embedding similarity would go here.
                # For now, we track that consolidation was attempted.
                logger.info(f"Found {len(memories)} eligible memories for consolidation")

                # Invalidate L1 cache after consolidation
                self.invalidate_l1_cache(user_id)

                return {
                    "success": True,
                    "consolidated": 0,
                    "eligible": len(memories),
                    "message": "Consolidation check completed",
                }

            return {"success": True, "consolidated": 0, "message": "Provider does not support consolidation"}

        except Exception as e:
            logger.error(f"Consolidation error: {e}")
            return {"success": False, "error": str(e)}

    async def _health_loop(self) -> None:
        """Periodic health check loop."""
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)

                if not self._running:
                    break

                if self._provider and hasattr(self._provider, "health_check"):
                    health = await self._provider.health_check()
                    was_healthy = self._provider_healthy
                    self._provider_healthy = health.healthy

                    if was_healthy and not health.healthy:
                        logger.warning(f"Provider unhealthy: {health.details}")
                    elif not was_healthy and health.healthy:
                        logger.info("Provider recovered")

                self._last_health_check = datetime.now()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Health check error: {e}")


# =============================================================================
# Global Daemon Instance
# =============================================================================

_daemon: Optional[MemoryDaemon] = None


def get_daemon(config: dict | None = None) -> MemoryDaemon:
    """
    Get the global MemoryDaemon singleton.

    Args:
        config: Optional config override

    Returns:
        MemoryDaemon instance
    """
    global _daemon
    if _daemon is None:
        _daemon = MemoryDaemon(config=config)
    return _daemon


async def ensure_daemon_running(config: dict | None = None) -> MemoryDaemon:
    """
    Get the daemon and ensure it's running.

    Args:
        config: Optional config override

    Returns:
        Running MemoryDaemon instance
    """
    daemon = get_daemon(config)
    if not daemon._running:
        await daemon.start()
    return daemon
