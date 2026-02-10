"""
L1 Memory Block Builder

Builds the condensed memory context block that gets injected into the
system prompt (L1 hot memory). Combines user profile, relevant memories,
active commitments, and session state into a ~1000 token block.

See: goals/memory_context_compaction_design.md §8

Usage:
    from tools.memory.l1_builder import build_l1_memory_block

    block = await build_l1_memory_block(user_id="alice", current_query="voice UX")
    # Returns formatted string ready for system prompt injection
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Token budget allocations
MAX_TOTAL_TOKENS = 1000
PROFILE_TOKEN_BUDGET = 150
MEMORIES_TOKEN_BUDGET = 500
COMMITMENTS_TOKEN_BUDGET = 200
SESSION_TOKEN_BUDGET = 150

# Approximate chars per token (conservative estimate)
CHARS_PER_TOKEN = 4


async def build_l1_memory_block(
    user_id: str,
    current_query: str | None = None,
    max_tokens: int = MAX_TOTAL_TOKENS,
    provider: Any = None,
) -> str:
    """
    Build a condensed memory block for L1 injection.

    Combines user profile, relevant memories, and active commitments
    into a concise block that fits within the token budget.

    Args:
        user_id: User identifier
        current_query: Optional current query for relevance scoring
        max_tokens: Maximum token budget
        provider: Optional memory provider (auto-initializes if None)

    Returns:
        Formatted memory block string, or empty string if no relevant memories
    """
    if provider is None:
        provider = await _get_provider()

    if provider is None:
        return ""

    sections: list[str] = []

    # 1. User profile summary
    profile = await _build_profile_section(user_id, provider)
    if profile:
        sections.append(profile)

    # 2. Relevant memories (based on current query)
    memories = await _build_memories_section(
        user_id, current_query, provider
    )
    if memories:
        sections.append(memories)

    # 3. Active commitments
    commitments = await _build_commitments_section(user_id, provider)
    if commitments:
        sections.append(commitments)

    if not sections:
        return ""

    block = "[Memory Context]\n\n" + "\n\n".join(sections)

    # Enforce token budget
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(block) > max_chars:
        block = block[:max_chars - 3] + "..."

    return block


async def _get_provider() -> Any:
    """Get the memory provider instance."""
    try:
        from tools.memory.service import MemoryService

        service = MemoryService()
        await service.initialize()
        return service
    except Exception as e:
        logger.debug(f"Failed to initialize memory provider: {e}")
        return None


async def _build_profile_section(
    user_id: str,
    provider: Any,
) -> str:
    """
    Build user profile section from stored preferences and facts.

    Budget: ~150 tokens
    """
    try:
        from tools.memory.providers.base import SearchFilters, MemoryType

        filters = SearchFilters(
            types=[MemoryType.PREFERENCE, MemoryType.FACT],
            user_id=user_id,
            min_importance=6,
        )
        results = await provider.search(
            query="user profile preferences facts",
            limit=5,
            filters=filters,
        )

        if not results:
            return ""

        max_chars = PROFILE_TOKEN_BUDGET * CHARS_PER_TOKEN
        lines = []
        total_chars = 0

        for r in results:
            line = f"- {r.content[:150]}"
            if total_chars + len(line) > max_chars:
                break
            lines.append(line)
            total_chars += len(line)

        if not lines:
            return ""

        return "User:\n" + "\n".join(lines)

    except Exception as e:
        logger.debug(f"Failed to build profile section: {e}")
        return ""


async def _build_memories_section(
    user_id: str,
    current_query: str | None,
    provider: Any,
) -> str:
    """
    Build relevant memories section based on current query.

    Budget: ~500 tokens
    """
    try:
        query = current_query or "recent context and relevant information"

        results = await provider.search(
            query=query,
            limit=10,
        )

        if not results:
            return ""

        # Filter by relevance
        relevant = [r for r in results if hasattr(r, 'score') and r.score and r.score >= 0.5]
        if not relevant:
            # Fall back to unscored results (provider may not set scores)
            relevant = results[:5]

        max_chars = MEMORIES_TOKEN_BUDGET * CHARS_PER_TOKEN
        lines = []
        total_chars = 0

        for r in relevant[:5]:
            content = r.content[:200]
            # Add age hint for context
            if hasattr(r, 'created_at') and r.created_at:
                age = _format_age(r.created_at)
                line = f"- {content} ({age})"
            else:
                line = f"- {content}"

            if total_chars + len(line) > max_chars:
                break
            lines.append(line)
            total_chars += len(line)

        if not lines:
            return ""

        return "Recent relevant:\n" + "\n".join(lines)

    except Exception as e:
        logger.debug(f"Failed to build memories section: {e}")
        return ""


async def _build_commitments_section(
    user_id: str,
    provider: Any,
) -> str:
    """
    Build active commitments section with ADHD-safe framing.

    Budget: ~200 tokens
    Framing: Forward-facing opportunities, not guilt-inducing obligations.
    """
    try:
        commitments = []
        if hasattr(provider, "list_commitments"):
            commitments = await provider.list_commitments(
                user_id=user_id,
                status="active",
                limit=3,
            )

        if not commitments:
            return ""

        max_chars = COMMITMENTS_TOKEN_BUDGET * CHARS_PER_TOKEN
        lines = []
        total_chars = 0

        for c in commitments:
            content = c.get("content", "")[:150]
            target = c.get("target_person", "")
            due = c.get("due_date", "")

            parts = [f"- {content}"]
            if target:
                parts.append(f"(for {target})")
            if due:
                parts.append(f"(due: {due})")

            line = " ".join(parts)
            if total_chars + len(line) > max_chars:
                break
            lines.append(line)
            total_chars += len(line)

        if not lines:
            return ""

        return "Active commitments:\n" + "\n".join(lines)

    except Exception as e:
        logger.debug(f"Failed to build commitments section: {e}")
        return ""


def _format_age(created_at: datetime) -> str:
    """Format a datetime as a human-readable age string."""
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except (ValueError, TypeError):
            return ""

    now = datetime.now()
    delta = now - created_at

    if delta.days > 30:
        return f"{delta.days // 30} months ago"
    elif delta.days > 1:
        return f"{delta.days} days ago"
    elif delta.days == 1:
        return "yesterday"
    elif delta.seconds > 3600:
        return f"{delta.seconds // 3600}h ago"
    elif delta.seconds > 60:
        return f"{delta.seconds // 60}min ago"
    else:
        return "just now"
