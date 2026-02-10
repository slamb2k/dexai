"""
Auto-Recall — L2 → L1 Memory Injection

Searches L2 warm memory for relevant memories and injects them into the
conversation context (L1). Runs on every incoming user message within the
hot path (<200ms latency budget).

Includes topic continuity detection to avoid noise: if the user's message
is a clear continuation of the current topic, memory injection is skipped.

See: goals/memory_context_compaction_design.md §6

Usage:
    from tools.memory.auto_recall import auto_recall

    memory_block = await auto_recall(
        user_message="Tell me about the voice UX meeting",
        user_id="alice",
        conversation_context=["working on phase 11", "voice button component"],
    )
    if memory_block:
        # Inject into system prompt
        system_prompt += f"\n\n{memory_block}"
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_MAX_MEMORIES = 5
DEFAULT_MAX_TOKENS = 800
DEFAULT_RELEVANCE_THRESHOLD = 0.6
CHARS_PER_TOKEN = 4


async def auto_recall(
    user_message: str,
    user_id: str,
    conversation_context: list[str] | None = None,
    max_memories: int = DEFAULT_MAX_MEMORIES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
    skip_on_continuation: bool = True,
    provider: Any = None,
) -> str | None:
    """
    Search L2 for relevant memories and format for L1 injection.

    Called before LLM generation, within the hot path. Must complete
    within 200ms latency budget.

    Args:
        user_message: Current user message
        user_id: User identifier
        conversation_context: Recent messages in the conversation
        max_memories: Maximum memories to inject
        max_tokens: Token budget for the memory block
        relevance_threshold: Minimum relevance score for injection
        skip_on_continuation: Skip injection on clear topic continuations
        provider: Memory provider (auto-initializes if None)

    Returns:
        Formatted memory block for injection, or None if no relevant memories
    """
    if not user_message or len(user_message.strip()) < 5:
        return None

    # Check if this message likely needs memory context
    if skip_on_continuation and conversation_context:
        needs_context = quick_context_check(user_message, conversation_context)
        if not needs_context:
            return None

    # Get provider
    if provider is None:
        provider = await _get_provider()
    if provider is None:
        return None

    try:
        # Fast L2 search
        results = await provider.search(
            query=user_message,
            limit=max_memories * 2,  # Over-fetch, then filter
        )

        if not results:
            return None

        # Filter by relevance threshold
        relevant = []
        for r in results:
            score = getattr(r, "score", None)
            if score is not None and score >= relevance_threshold:
                relevant.append(r)
            elif score is None:
                # Provider doesn't set scores — include cautiously
                relevant.append(r)

        if not relevant:
            return None

        # Deduplicate against current conversation context
        if conversation_context:
            novel = [
                r for r in relevant
                if not _already_in_context(r, conversation_context)
            ]
            if not novel:
                return None
            relevant = novel

        # Format for injection (respecting token budget)
        return _format_memory_block(relevant[:max_memories], max_tokens)

    except Exception as e:
        logger.debug(f"Auto-recall failed: {e}")
        return None


def quick_context_check(
    message: str,
    recent_messages: list[str],
) -> bool:
    """
    Should we search memory for this message?

    Returns False for clear continuations (no memory search needed).
    Returns True for topic shifts, cold starts, or personal references.

    Args:
        message: Current user message
        recent_messages: Recent messages in conversation

    Returns:
        True if memory search is warranted
    """
    # Cold start — always search
    if len(recent_messages) < 2:
        return True

    # Personal references — always search
    if _has_personal_reference(message):
        return True

    # Named entities not in recent context — search
    entities = _extract_entities_fast(message)
    if entities:
        recent_text = " ".join(recent_messages[-3:])
        recent_entities = _extract_entities_fast(recent_text)
        if entities - recent_entities:  # New entities
            return True

    # Short messages are likely continuations
    if len(message.strip()) < 30:
        return False

    # Questions about past events/facts — always search
    if re.search(r"\b(?:remember|recall|last time|previously|before|earlier|when did|what was)\b", message, re.I):
        return True

    # Default: skip for likely continuations
    return False


def _has_personal_reference(message: str) -> bool:
    """Check if message contains personal references that need memory context."""
    patterns = [
        r"\bmy (?:doctor|therapist|boss|manager|wife|husband|partner|kid|child)\b",
        r"\b(?:Sarah|Mike|John|Lisa)\b",  # Proper names (would be better with NER)
        r"\b(?:remember (?:when|that)|did I (?:say|mention|tell))\b",
        r"\bmy (?:appointment|meeting|deadline|project|task)\b",
    ]
    return any(re.search(p, message, re.I) for p in patterns)


def _extract_entities_fast(text: str) -> set[str]:
    """Extract simple entity-like tokens (capitalized words)."""
    return set(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text))


def _already_in_context(
    memory: Any,
    conversation_context: list[str],
) -> bool:
    """
    Check if a memory's content is already present in the conversation.

    Uses simple substring matching to avoid injecting redundant information.
    """
    content = getattr(memory, "content", str(memory))
    # Normalize for comparison
    content_lower = content.lower()[:100]
    context_text = " ".join(conversation_context[-5:]).lower()

    # Check if key phrases from the memory appear in recent context
    words = content_lower.split()
    if len(words) < 3:
        return content_lower in context_text

    # Check for 3-gram overlap
    for i in range(len(words) - 2):
        trigram = " ".join(words[i:i + 3])
        if trigram in context_text:
            return True

    return False


def _format_memory_block(
    memories: list[Any],
    max_tokens: int,
) -> str:
    """
    Format memories into a concise injection block.

    Respects ADHD design principles:
    - Max 5 memories
    - Concise, scannable format
    - No guilt language
    - Forward-facing framing
    """
    if not memories:
        return ""

    max_chars = max_tokens * CHARS_PER_TOKEN
    lines = []
    total_chars = 0

    for mem in memories:
        content = getattr(mem, "content", str(mem))
        # Truncate long memories
        if len(content) > 200:
            content = content[:197] + "..."

        line = f"- {content}"
        if total_chars + len(line) > max_chars:
            break

        lines.append(line)
        total_chars += len(line)

    if not lines:
        return ""

    return "[Relevant memories]\n" + "\n".join(lines)


async def _get_provider() -> Any:
    """Get the memory provider instance."""
    try:
        from tools.memory.service import MemoryService

        service = MemoryService()
        await service.initialize()
        return service
    except Exception as e:
        logger.debug(f"Failed to initialize memory provider for auto-recall: {e}")
        return None
