"""
Session Note Extractor

Uses a lightweight LLM call (Haiku) to extract structured memory entries from
conversation turns. Produces typed, importance-rated facts for storage in L2.

See: goals/memory_context_compaction_design.md §1.2

Usage:
    from tools.memory.extraction.extractor import extract_session_notes

    notes = await extract_session_notes(user_msg, assistant_msg, session_id)
    for note in notes:
        await provider.add_session_note(note.content, session_id, note.importance)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default model for extraction — cheapest available
DEFAULT_EXTRACTION_MODEL = "claude-haiku-4-5-20251001"

# Extraction prompt template
EXTRACTION_PROMPT = """Given this conversation turn, extract any facts worth remembering long-term.
For each fact, classify it and rate its importance (1-10).

Categories: FACT, PREFERENCE, EVENT, INSIGHT, RELATIONSHIP, COMMITMENT

Rules:
- Only extract genuinely new or updated information
- Skip greetings, acknowledgments, and filler
- Commitments must include: what, who (if mentioned), when (if mentioned)
- Rate importance: 1-3 mundane, 4-6 useful, 7-9 significant, 10 critical
- Return valid JSON array. If nothing memorable, return []

User message: {user_message}
Assistant response: {assistant_response}

Respond ONLY with a JSON array:
[{{"content": "...", "type": "FACT|PREFERENCE|EVENT|INSIGHT|RELATIONSHIP|COMMITMENT", "importance": 1-10}}]"""


@dataclass
class ExtractedNote:
    """A memory note extracted from a conversation turn."""
    content: str
    note_type: str  # FACT, PREFERENCE, EVENT, INSIGHT, RELATIONSHIP, COMMITMENT
    importance: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)


async def extract_session_notes(
    user_message: str,
    assistant_response: str,
    session_id: str | None = None,
    model: str = DEFAULT_EXTRACTION_MODEL,
) -> list[ExtractedNote]:
    """
    Extract structured session notes from a conversation turn.

    Uses a cheap LLM call to identify facts, preferences, events, etc.
    This runs asynchronously after the response is delivered to the user.

    Args:
        user_message: The user's message
        assistant_response: The assistant's response
        session_id: Optional session ID for metadata
        model: Model to use for extraction

    Returns:
        List of ExtractedNote objects (may be empty)
    """
    if not user_message or len(user_message.strip()) < 10:
        return []

    # Truncate to avoid excessive cost
    user_msg = user_message[:2000]
    assist_msg = (assistant_response or "")[:2000]

    prompt = EXTRACTION_PROMPT.format(
        user_message=user_msg,
        assistant_response=assist_msg,
    )

    try:
        raw_output = await _call_extraction_llm(prompt, model)
        return _parse_extraction_output(raw_output, session_id)
    except Exception as e:
        logger.warning(f"Extraction failed: {e}")
        return []


async def _call_extraction_llm(prompt: str, model: str) -> str:
    """
    Call the LLM for extraction. Uses Anthropic API directly for speed.

    Args:
        prompt: The extraction prompt
        model: Model ID

    Returns:
        Raw text output from the model
    """
    try:
        import anthropic

        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else "[]"
    except ImportError:
        logger.warning("anthropic package not available for extraction")
        return "[]"
    except Exception as e:
        logger.warning(f"LLM extraction call failed: {e}")
        return "[]"


def _parse_extraction_output(
    raw_output: str,
    session_id: str | None = None,
) -> list[ExtractedNote]:
    """
    Parse LLM extraction output into ExtractedNote objects.

    Handles common JSON formatting issues (markdown code blocks, trailing text).

    Args:
        raw_output: Raw text from the LLM
        session_id: Optional session ID for metadata

    Returns:
        List of ExtractedNote objects
    """
    text = raw_output.strip()

    # Strip markdown code block if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Try to find JSON array in the text
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []

    json_str = text[start:end + 1]

    try:
        items = json.loads(json_str)
    except json.JSONDecodeError:
        logger.debug(f"Failed to parse extraction JSON: {json_str[:200]}")
        return []

    if not isinstance(items, list):
        return []

    notes = []
    valid_types = {"FACT", "PREFERENCE", "EVENT", "INSIGHT", "RELATIONSHIP", "COMMITMENT"}

    for item in items:
        if not isinstance(item, dict):
            continue

        content = item.get("content", "").strip()
        if not content:
            continue

        note_type = item.get("type", "FACT").upper()
        if note_type not in valid_types:
            note_type = "FACT"

        importance = item.get("importance", 5)
        if not isinstance(importance, int) or importance < 1:
            importance = 5
        importance = min(importance, 10)

        metadata = {}
        if session_id:
            metadata["session_id"] = session_id

        notes.append(ExtractedNote(
            content=content,
            note_type=note_type,
            importance=importance,
            metadata=metadata,
        ))

    return notes
