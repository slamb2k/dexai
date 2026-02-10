"""
Heuristic Gate — Pre-filter for Memory Extraction

Runs on every conversation turn to decide whether it warrants memory extraction.
Uses fast regex-based signal detection (<1ms) to avoid unnecessary LLM calls.

Not every message deserves memory extraction. "ok", "thanks", "got it" have zero
memory value. This gate filters them out before they reach the extraction queue.

See: goals/memory_context_compaction_design.md §1.1

Usage:
    from tools.memory.extraction.gate import should_extract

    do_extract, score = should_extract(user_message, recent_context)
    if do_extract:
        await extraction_queue.enqueue(turn)
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Default gate threshold — at least one strong signal or two weak ones
DEFAULT_GATE_THRESHOLD = 0.3


# =============================================================================
# Signal Detection Patterns
# =============================================================================

# Commitment language: "I'll", "I promise", "remind me to", "don't forget"
_COMMITMENT_PATTERNS = [
    re.compile(r"\bi(?:'ll|'m going to|will)\b.*\b(?:send|do|finish|call|email|write|submit|review|check|prepare|schedule|book|pay)\b", re.I),
    re.compile(r"\b(?:remind me|don't forget|need to remember)\b", re.I),
    re.compile(r"\bi promise\b", re.I),
    re.compile(r"\b(?:by|before|until)\s+(?:tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week|end of (?:day|week))\b", re.I),
    re.compile(r"\b(?:deadline|due date|due by)\b", re.I),
]

# Preference statements: "I prefer", "I like", "I always", "I never"
_PREFERENCE_PATTERNS = [
    re.compile(r"\bi (?:prefer|like|love|hate|dislike|always|never|usually|tend to)\b", re.I),
    re.compile(r"\b(?:my (?:favorite|preferred|usual|default))\b", re.I),
    re.compile(r"\b(?:i(?:'m| am) (?:a|an)\s+\w+\s+person)\b", re.I),
    re.compile(r"\bdon't (?:like|want|need|use)\b", re.I),
]

# Temporal references: "tomorrow", "next week", "at 3pm"
_TEMPORAL_PATTERNS = [
    re.compile(r"\b(?:tomorrow|yesterday|next (?:week|month|year)|last (?:week|month|year))\b", re.I),
    re.compile(r"\b(?:at|by|before|after|around)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", re.I),
    re.compile(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I),
    re.compile(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b", re.I),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b"),
]

# Factual assertions: "I am", "I work at", "I live in"
_FACTUAL_PATTERNS = [
    re.compile(r"\bi (?:am|work (?:at|for|as)|live (?:in|at)|have (?:a|an)|own|manage|run|lead)\b", re.I),
    re.compile(r"\bmy (?:name|job|title|role|team|company|wife|husband|partner|kid|child|dog|cat|doctor|therapist|medication)\b", re.I),
    re.compile(r"\bi(?:'m| am)\s+(?:a|an|the)\s+\w+", re.I),
    re.compile(r"\bmy (?:phone|email|address|birthday) (?:is|number)\b", re.I),
]

# Emotional significance: "I'm worried", "I'm excited", "this is important"
_EMOTIONAL_PATTERNS = [
    re.compile(r"\bi(?:'m| am)\s+(?:worried|anxious|stressed|excited|happy|frustrated|overwhelmed|burned out|struggling)\b", re.I),
    re.compile(r"\bthis (?:is|feels) (?:important|critical|urgent|stressful)\b", re.I),
    re.compile(r"\bi (?:feel|felt)\s+(?:like|that|so)\b", re.I),
]

# Named entity indicators (lightweight — full NER is too expensive for a gate)
_ENTITY_PATTERNS = [
    re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b"),  # Multi-word proper nouns
    re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Prof)\.\s+[A-Z]\w+\b"),  # Titles
    re.compile(r"\b(?:@\w+)\b"),  # Mentions
    re.compile(r"(?:https?://\S+)"),  # URLs (notable references)
]


@dataclass
class GateResult:
    """Result of the heuristic gate evaluation."""
    should_extract: bool
    score: float
    signals: dict[str, float]


def has_commitment_language(text: str) -> bool:
    """Check if text contains commitment/promise language."""
    return any(p.search(text) for p in _COMMITMENT_PATTERNS)


def has_preference_statement(text: str) -> bool:
    """Check if text contains preference statements."""
    return any(p.search(text) for p in _PREFERENCE_PATTERNS)


def has_temporal_reference(text: str) -> bool:
    """Check if text contains temporal references."""
    return any(p.search(text) for p in _TEMPORAL_PATTERNS)


def has_factual_assertion(text: str) -> bool:
    """Check if text contains factual assertions about the user."""
    return any(p.search(text) for p in _FACTUAL_PATTERNS)


def has_emotional_significance(text: str) -> bool:
    """Check if text contains emotionally significant statements."""
    return any(p.search(text) for p in _EMOTIONAL_PATTERNS)


def has_named_entities(text: str) -> bool:
    """Check if text contains named entities (lightweight regex-based)."""
    return any(p.search(text) for p in _ENTITY_PATTERNS)


def calculate_entity_novelty(
    message: str,
    recent_context: list[str],
) -> float:
    """
    Calculate how many new entities appear in this message vs recent context.

    Returns a 0.0-1.0 novelty score. 1.0 = all entities are new.
    """
    if not recent_context:
        return 1.0

    # Extract simple entity-like tokens (capitalized words)
    def extract_caps(text: str) -> set[str]:
        return set(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text))

    msg_entities = extract_caps(message)
    if not msg_entities:
        return 0.0

    context_text = " ".join(recent_context[-5:])  # Last 5 messages
    ctx_entities = extract_caps(context_text)

    novel = msg_entities - ctx_entities
    return len(novel) / len(msg_entities) if msg_entities else 0.0


def should_extract(
    message: str,
    recent_context: list[str] | None = None,
    threshold: float = DEFAULT_GATE_THRESHOLD,
) -> tuple[bool, float]:
    """
    Decide whether a message warrants memory extraction.

    Runs regex-based signal detection (<1ms) to avoid unnecessary LLM calls.

    Args:
        message: User message text
        recent_context: Recent messages in the conversation (for novelty check)
        threshold: Score threshold for extraction (default: 0.3)

    Returns:
        Tuple of (should_extract, confidence_score)
    """
    result = evaluate_gate(message, recent_context, threshold)
    return result.should_extract, result.score


def evaluate_gate(
    message: str,
    recent_context: list[str] | None = None,
    threshold: float = DEFAULT_GATE_THRESHOLD,
) -> GateResult:
    """
    Full gate evaluation with detailed signal breakdown.

    Args:
        message: User message text
        recent_context: Recent messages for novelty check
        threshold: Score threshold

    Returns:
        GateResult with should_extract, score, and signal breakdown
    """
    if not message or len(message.strip()) < 5:
        return GateResult(should_extract=False, score=0.0, signals={})

    signals: dict[str, float] = {}
    score = 0.0

    # Fast regex signals (< 1ms total)
    if has_commitment_language(message):
        signals["commitment"] = 0.4
        score += 0.4

    if has_preference_statement(message):
        signals["preference"] = 0.3
        score += 0.3

    if has_temporal_reference(message):
        signals["temporal"] = 0.2
        score += 0.2

    if has_named_entities(message):
        signals["entities"] = 0.2
        score += 0.2

    if has_factual_assertion(message):
        signals["factual"] = 0.2
        score += 0.2

    if has_emotional_significance(message):
        signals["emotional"] = 0.1
        score += 0.1

    # Slightly more expensive: entity novelty (< 5ms)
    if score >= 0.2 and recent_context:
        novelty = calculate_entity_novelty(message, recent_context)
        novelty_score = novelty * 0.3
        if novelty_score > 0:
            signals["novelty"] = round(novelty_score, 3)
            score += novelty_score

    return GateResult(
        should_extract=score >= threshold,
        score=round(score, 3),
        signals=signals,
    )
