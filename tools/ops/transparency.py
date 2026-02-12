"""
"Show Your Work" Transparency Mode

Per-conversation toggle that accumulates a transparency log of tool usage,
memory access, and routing decisions the agent makes during a conversation.

Allows users to see what happened behind the scenes.

Usage:
    from tools.ops.transparency import transparency

    # Enable for a conversation
    transparency.enable("conv-123")

    # Log events
    transparency.log_tool_use("conv-123", "Read", 12.5, "Read file.py (200 lines)")
    transparency.log_memory_access("conv-123", "project setup", 3)
    transparency.log_routing_decision("conv-123", "moderate", "claude-sonnet-4.5", "Score=5")

    # Retrieve log
    log = transparency.get_log("conv-123")

    # Disable
    transparency.disable("conv-123")

Dependencies:
    - threading (stdlib)
    - time (stdlib)
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Maximum entries per conversation to prevent unbounded memory growth
MAX_LOG_ENTRIES = 500


class TransparencyLogger:
    """Per-conversation transparency logger for "show your work" mode.

    Tracks tool usage, memory access, and routing decisions so users
    can understand what the agent did behind the scenes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._logs: dict[str, list[dict[str, Any]]] = {}
        self._enabled: set[str] = set()

    def is_enabled(self, conversation_id: str) -> bool:
        """Check if transparency logging is enabled for a conversation.

        Args:
            conversation_id: Unique conversation identifier.

        Returns:
            True if transparency is enabled.
        """
        with self._lock:
            return conversation_id in self._enabled

    def enable(self, conversation_id: str) -> None:
        """Enable transparency logging for a conversation.

        Args:
            conversation_id: Unique conversation identifier.
        """
        with self._lock:
            self._enabled.add(conversation_id)
            if conversation_id not in self._logs:
                self._logs[conversation_id] = []
        logger.info(f"Transparency enabled for conversation {conversation_id}")

    def disable(self, conversation_id: str) -> None:
        """Disable transparency logging for a conversation.

        The log is preserved until explicitly cleared.

        Args:
            conversation_id: Unique conversation identifier.
        """
        with self._lock:
            self._enabled.discard(conversation_id)
        logger.info(f"Transparency disabled for conversation {conversation_id}")

    def _append(self, conversation_id: str, entry: dict[str, Any]) -> None:
        """Append an entry to the conversation log. Must check is_enabled first."""
        with self._lock:
            if conversation_id not in self._logs:
                self._logs[conversation_id] = []
            log = self._logs[conversation_id]
            # Enforce max entries to prevent unbounded growth
            if len(log) >= MAX_LOG_ENTRIES:
                log.pop(0)
            log.append(entry)

    def log_tool_use(
        self,
        conversation_id: str,
        tool_name: str,
        duration_ms: float,
        result_summary: str,
    ) -> None:
        """Log a tool use event.

        Args:
            conversation_id: Unique conversation identifier.
            tool_name: Name of the tool used.
            duration_ms: How long the tool took in milliseconds.
            result_summary: Brief summary of the result.
        """
        if not self.is_enabled(conversation_id):
            return

        self._append(conversation_id, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "tool_use",
            "details": {
                "tool_name": tool_name,
                "duration_ms": round(duration_ms, 2),
                "result_summary": result_summary[:500],
            },
        })

    def log_memory_access(
        self,
        conversation_id: str,
        query: str,
        results_count: int,
    ) -> None:
        """Log a memory access event.

        Args:
            conversation_id: Unique conversation identifier.
            query: The memory query string.
            results_count: Number of results returned.
        """
        if not self.is_enabled(conversation_id):
            return

        self._append(conversation_id, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "memory",
            "details": {
                "query": query[:200],
                "results_count": results_count,
            },
        })

    def log_routing_decision(
        self,
        conversation_id: str,
        complexity: str,
        model: str,
        reason: str,
    ) -> None:
        """Log a model routing decision.

        Args:
            conversation_id: Unique conversation identifier.
            complexity: Classified complexity level.
            model: Selected model name/ID.
            reason: Human-readable reason for the decision.
        """
        if not self.is_enabled(conversation_id):
            return

        self._append(conversation_id, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "routing",
            "details": {
                "complexity": complexity,
                "model": model,
                "reason": reason[:500],
            },
        })

    def get_log(self, conversation_id: str) -> list[dict[str, Any]]:
        """Get the transparency log for a conversation.

        Args:
            conversation_id: Unique conversation identifier.

        Returns:
            List of log entries, or empty list if none exist.
        """
        with self._lock:
            return list(self._logs.get(conversation_id, []))

    def clear_log(self, conversation_id: str) -> None:
        """Clear the transparency log for a conversation.

        Args:
            conversation_id: Unique conversation identifier.
        """
        with self._lock:
            self._logs.pop(conversation_id, None)
        logger.info(f"Transparency log cleared for conversation {conversation_id}")

    def get_summary(self, conversation_id: str) -> dict[str, Any]:
        """Get a summary of the transparency log.

        Args:
            conversation_id: Unique conversation identifier.

        Returns:
            Dict with counts by type and total entries.
        """
        log = self.get_log(conversation_id)
        type_counts: dict[str, int] = {}
        for entry in log:
            entry_type = entry.get("type", "unknown")
            type_counts[entry_type] = type_counts.get(entry_type, 0) + 1

        return {
            "conversation_id": conversation_id,
            "enabled": self.is_enabled(conversation_id),
            "total_entries": len(log),
            "by_type": type_counts,
        }


# Module-level singleton
transparency = TransparencyLogger()
