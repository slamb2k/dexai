"""
Supersession Classifier — AUDN Pipeline

Classifies how new facts relate to existing memories using the AUDN framework:
  ADD       — Genuinely new, no overlap
  UPDATE    — Augments/refines existing (merge)
  SUPERSEDE — Contradicts existing (invalidate old, insert new)
  NOOP      — Duplicate or irrelevant (skip)

Draws from Mem0's AUDN pipeline and Zep's temporal invalidation patterns.
For the native provider, uses a cheap LLM call (Haiku) for classification.
External providers (Mem0, Zep) handle this automatically.

See: goals/memory_context_compaction_design.md §3.1

Usage:
    from tools.memory.extraction.classifier import classify_update, AUDNAction

    actions = await classify_update(new_fact, existing_memories)
    for action in actions:
        if action["action"] == AUDNAction.SUPERSEDE:
            await provider.supersede(action["memory_id"], new_fact)
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CLASSIFICATION_MODEL = "claude-haiku-4-5-20251001"


class AUDNAction(str, Enum):
    """AUDN classification actions."""
    ADD = "ADD"
    UPDATE = "UPDATE"
    SUPERSEDE = "SUPERSEDE"
    NOOP = "NOOP"


CLASSIFICATION_PROMPT = """Compare this new fact against existing memories and classify the relationship.

New fact: {new_fact}

Existing memories:
{existing_memories}

For each existing memory, classify the relationship:
- ADD: The new fact is genuinely new, no overlap with this memory
- UPDATE: The new fact augments or refines this memory (merge them)
- SUPERSEDE: The new fact contradicts this memory (invalidate old, keep new)
- NOOP: The new fact is a duplicate or subset of this memory (skip)

If the new fact has no meaningful relationship to ANY existing memory, return a single ADD.

Respond ONLY with a JSON array:
[{{"action": "ADD|UPDATE|SUPERSEDE|NOOP", "memory_id": "...", "reason": "brief explanation"}}]"""


async def classify_update(
    new_fact: str,
    existing_memories: list[Any],
    model: str = DEFAULT_CLASSIFICATION_MODEL,
) -> list[dict]:
    """
    Classify how a new fact relates to existing memories.

    Uses AUDN classification to determine whether to add, update, supersede, or skip.

    Args:
        new_fact: The new fact to classify
        existing_memories: List of MemoryEntry objects (or dicts with id/content)
        model: Model for classification LLM call

    Returns:
        List of {action, memory_id, reason} dicts
    """
    if not existing_memories:
        return [{"action": AUDNAction.ADD, "memory_id": None, "reason": "no existing memories"}]

    # Format existing memories for the prompt
    memory_lines = []
    for i, mem in enumerate(existing_memories[:10]):  # Top 10
        mem_id = getattr(mem, "id", None) or (mem.get("id") if isinstance(mem, dict) else str(i))
        content = getattr(mem, "content", None) or (mem.get("content", "") if isinstance(mem, dict) else str(mem))
        memory_lines.append(f"[{mem_id}] {content[:200]}")

    if not memory_lines:
        return [{"action": AUDNAction.ADD, "memory_id": None, "reason": "no existing memories"}]

    prompt = CLASSIFICATION_PROMPT.format(
        new_fact=new_fact[:500],
        existing_memories="\n".join(memory_lines),
    )

    try:
        raw_output = await _call_classification_llm(prompt, model)
        return _parse_classification_output(raw_output)
    except Exception as e:
        logger.warning(f"Classification failed, defaulting to ADD: {e}")
        return [{"action": AUDNAction.ADD, "memory_id": None, "reason": f"classification failed: {e}"}]


async def _call_classification_llm(prompt: str, model: str) -> str:
    """Call the LLM for AUDN classification."""
    try:
        import anthropic

        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else "[]"
    except ImportError:
        logger.warning("anthropic package not available for classification")
        return "[]"
    except Exception as e:
        logger.warning(f"Classification LLM call failed: {e}")
        return "[]"


def _parse_classification_output(raw_output: str) -> list[dict]:
    """Parse LLM classification output into action dicts."""
    text = raw_output.strip()

    # Strip markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return [{"action": AUDNAction.ADD, "memory_id": None, "reason": "unparseable output"}]

    json_str = text[start:end + 1]

    try:
        items = json.loads(json_str)
    except json.JSONDecodeError:
        return [{"action": AUDNAction.ADD, "memory_id": None, "reason": "invalid JSON"}]

    if not isinstance(items, list):
        return [{"action": AUDNAction.ADD, "memory_id": None, "reason": "expected array"}]

    valid_actions = {a.value for a in AUDNAction}
    results = []

    for item in items:
        if not isinstance(item, dict):
            continue

        action = item.get("action", "ADD").upper()
        if action not in valid_actions:
            action = "ADD"

        results.append({
            "action": AUDNAction(action),
            "memory_id": item.get("memory_id"),
            "reason": item.get("reason", ""),
        })

    return results if results else [{"action": AUDNAction.ADD, "memory_id": None, "reason": "empty classification"}]
