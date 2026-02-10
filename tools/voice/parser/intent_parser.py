"""Intent parsing for voice commands.

Uses priority-sorted regex patterns to detect command intent from transcribed text.
Falls back to UNKNOWN with helpful suggestions for unrecognized input.
"""

from __future__ import annotations

import re
from typing import Any

from tools.voice.models import EntityType, IntentType, Entity, ParsedCommand
from tools.voice.parser.entity_extractor import extract_entities

# Intent patterns: (pattern, intent, priority, requires_confirmation)
# Higher priority = matched first. Groups capture entity text.
INTENT_PATTERNS: list[tuple[str, IntentType, int, bool]] = [
    # Cancel / undo (highest priority — always escape hatch)
    (r"^(?:cancel|never\s*mind|stop|abort)$", IntentType.CANCEL, 100, False),
    (r"^undo(?:\s+(?:that|last))?$", IntentType.UNDO, 99, True),

    # Task operations
    (r"(?:add|create|new)\s+(?:a\s+)?task[:\s]+(.+)", IntentType.ADD_TASK, 90, False),
    (r"(?:i\s+need\s+to|remind\s+me\s+to|don'?t\s+(?:let\s+me\s+)?forget\s+to)\s+(.+)", IntentType.ADD_TASK, 85, False),
    (r"(?:task|todo)[:\s]+(.+)", IntentType.ADD_TASK, 80, False),
    (r"(?:done|finished|complete|completed|mark\s+(?:as\s+)?(?:done|complete))", IntentType.COMPLETE_TASK, 70, True),
    (r"(?:skip|next\s+task|move\s+on|pass)", IntentType.SKIP_TASK, 65, True),
    (r"(?:break\s+(?:down|apart)|decompose|split)\s+(?:this\s+)?(?:task)?", IntentType.DECOMPOSE_TASK, 60, False),

    # Reminders
    (r"(?:remind\s+me|set\s+(?:a\s+)?reminder)\s+(?:to\s+)?(.+)", IntentType.SET_REMINDER, 88, False),
    (r"(?:snooze|later|not\s+now)(?:\s+(?:for\s+)?(.+))?", IntentType.SNOOZE_REMINDER, 55, False),
    (r"(?:cancel|remove|delete)\s+(?:the\s+)?reminder", IntentType.CANCEL_REMINDER, 50, True),

    # Queries
    (r"(?:what(?:'s| is)\s+(?:my\s+)?next(?:\s+task)?|next\s+step|what\s+should\s+i\s+do)", IntentType.QUERY_NEXT_TASK, 75, False),
    (r"(?:what(?:'s| is)\s+(?:on\s+)?(?:my\s+)?(?:calendar|schedule|agenda)|(?:today|tomorrow)(?:'s)?\s+(?:calendar|schedule))", IntentType.QUERY_SCHEDULE, 74, False),
    (r"(?:how\s+am\s+i\s+doing|(?:my\s+)?(?:progress|status|summary))", IntentType.QUERY_STATUS, 73, False),
    (r"(?:search|find|look\s+(?:for|up))\s+(.+)", IntentType.QUERY_SEARCH, 72, False),

    # Focus control
    (r"(?:start|enter|begin)\s+(?:focus|deep\s+work|flow)(?:\s+mode)?", IntentType.START_FOCUS, 68, False),
    (r"(?:do\s+not\s+disturb|dnd|quiet\s+mode)", IntentType.START_FOCUS, 67, False),
    (r"(?:end|stop|exit|leave)\s+(?:focus|deep\s+work|flow)(?:\s+mode)?", IntentType.END_FOCUS, 66, False),
    (r"(?:resume|i'?m\s+(?:back|done\s+focusing))", IntentType.END_FOCUS, 64, False),
    (r"(?:pause|mute|silence)\s+(?:notifications?|alerts?)", IntentType.PAUSE_NOTIFICATIONS, 63, False),

    # Help
    (r"(?:help|what\s+can\s+(?:i\s+say|you\s+do)|commands?|options?)", IntentType.HELP, 40, False),
]

# Compiled pattern cache
_compiled_patterns: list[tuple[re.Pattern, IntentType, int, bool]] | None = None


def _get_patterns() -> list[tuple[re.Pattern, IntentType, int, bool]]:
    """Get compiled patterns sorted by priority (highest first)."""
    global _compiled_patterns
    if _compiled_patterns is None:
        _compiled_patterns = sorted(
            [
                (re.compile(p, re.IGNORECASE), intent, pri, confirm)
                for p, intent, pri, confirm in INTENT_PATTERNS
            ],
            key=lambda x: x[2],
            reverse=True,
        )
    return _compiled_patterns


def parse_intent(
    text: str,
) -> tuple[IntentType, float, list[str]]:
    """Extract intent from transcribed text.

    Returns:
        (intent_type, confidence, captured_groups)
    """
    text = text.strip()
    if not text:
        return IntentType.UNKNOWN, 0.0, []

    for pattern, intent, priority, _confirm in _get_patterns():
        match = pattern.search(text)
        if match:
            groups = [g for g in match.groups() if g]
            # Higher priority patterns get higher confidence
            confidence = min(0.95, 0.6 + (priority / 200))
            return intent, confidence, groups

    return IntentType.UNKNOWN, 0.0, []


def parse_command(text: str) -> ParsedCommand:
    """Parse a voice transcript into a full command with entities.

    This is the main entry point for the voice command pipeline.
    """
    intent, confidence, groups = parse_intent(text)

    # Extract entities from the full text
    entities = extract_entities(text, intent)

    # If we captured a task description from regex groups, add it
    if groups and intent in (IntentType.ADD_TASK, IntentType.SET_REMINDER, IntentType.QUERY_SEARCH):
        entity_type = {
            IntentType.ADD_TASK: EntityType.TASK_DESCRIPTION,
            IntentType.SET_REMINDER: EntityType.TASK_DESCRIPTION,
            IntentType.QUERY_SEARCH: EntityType.SEARCH_QUERY,
        }[intent]

        # Only add if not already extracted
        existing_types = {e.type for e in entities}
        if entity_type not in existing_types:
            entities.insert(0, Entity(
                type=entity_type,
                value=groups[0].strip(),
                raw_text=groups[0],
            ))

    # Determine if confirmation is needed
    requires_confirmation = False
    for pattern, p_intent, _pri, confirm in _get_patterns():
        if p_intent == intent:
            requires_confirmation = confirm
            break

    # Generate suggestion for unknown intents
    suggestion = None
    if intent == IntentType.UNKNOWN and text:
        suggestion = _suggest_closest(text)

    return ParsedCommand(
        intent=intent,
        confidence=confidence,
        entities=entities,
        raw_transcript=text,
        requires_confirmation=requires_confirmation,
        suggestion=suggestion,
    )


def _suggest_closest(text: str) -> str:
    """Suggest what the user might have meant."""
    text_lower = text.lower()

    # Check for partial matches
    if any(w in text_lower for w in ("task", "todo", "do", "need")):
        return 'Try: "add task [description]" or "what\'s my next task?"'
    if any(w in text_lower for w in ("remind", "alarm", "timer")):
        return 'Try: "remind me to [action] [time]"'
    if any(w in text_lower for w in ("focus", "quiet", "disturb")):
        return 'Try: "start focus mode" or "do not disturb"'
    if any(w in text_lower for w in ("calendar", "schedule", "meeting")):
        return 'Try: "what\'s on my calendar?" or "today\'s schedule"'
    if any(w in text_lower for w in ("how", "status", "progress")):
        return 'Try: "how am I doing?" or "my status"'

    return 'Say "help" to see available commands'


# Available commands for the help response
AVAILABLE_COMMANDS: dict[str, list[dict[str, str]]] = {
    "Tasks": [
        {"command": "Add task: [description]", "example": "Add task: buy groceries"},
        {"command": "Done / Finished", "example": "Mark current task as complete"},
        {"command": "Skip / Next task", "example": "Move to next task"},
        {"command": "Break down this task", "example": "Decompose current task"},
    ],
    "Reminders": [
        {"command": "Remind me to [action] [time]", "example": "Remind me to call mom tomorrow"},
        {"command": "Snooze / Later", "example": "Snooze current reminder"},
    ],
    "Queries": [
        {"command": "What's my next task?", "example": "Get next task based on energy"},
        {"command": "What's on my calendar?", "example": "Today's schedule"},
        {"command": "How am I doing?", "example": "Progress summary"},
        {"command": "Search for [keyword]", "example": "Search for groceries"},
    ],
    "Focus": [
        {"command": "Start focus mode", "example": "Enter deep work mode"},
        {"command": "End focus mode", "example": "Resume normal mode"},
        {"command": "Pause notifications", "example": "Silence alerts"},
    ],
    "Control": [
        {"command": "Help", "example": "Show available commands"},
        {"command": "Cancel", "example": "Cancel current action"},
        {"command": "Undo", "example": "Undo last action"},
    ],
}
