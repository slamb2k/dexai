"""Voice interface data models.

Defines intents, entities, and result types for the voice command pipeline:
    Transcript → ParsedCommand → CommandResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    """Voice command intent types."""

    # Task operations
    ADD_TASK = "add_task"
    COMPLETE_TASK = "complete_task"
    SKIP_TASK = "skip_task"
    DECOMPOSE_TASK = "decompose_task"

    # Reminders
    SET_REMINDER = "set_reminder"
    SNOOZE_REMINDER = "snooze_reminder"
    CANCEL_REMINDER = "cancel_reminder"

    # Queries
    QUERY_NEXT_TASK = "query_next_task"
    QUERY_SCHEDULE = "query_schedule"
    QUERY_STATUS = "query_status"
    QUERY_SEARCH = "query_search"

    # Focus & control
    START_FOCUS = "start_focus"
    END_FOCUS = "end_focus"
    PAUSE_NOTIFICATIONS = "pause_notifications"

    # Meta
    HELP = "help"
    CANCEL = "cancel"
    UNDO = "undo"
    UNKNOWN = "unknown"


class EntityType(str, Enum):
    """Voice command entity types."""

    TASK_DESCRIPTION = "task_description"
    DATETIME = "datetime"
    DURATION = "duration"
    PERSON = "person"
    PRIORITY = "priority"
    ENERGY_LEVEL = "energy_level"
    TASK_REFERENCE = "task_reference"
    SEARCH_QUERY = "search_query"


@dataclass
class Entity:
    """An extracted entity from a voice command."""

    type: EntityType
    value: str
    raw_text: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "value": self.value,
            "raw_text": self.raw_text,
            "confidence": self.confidence,
        }


@dataclass
class TranscriptionResult:
    """Result from speech recognition."""

    transcript: str
    confidence: float = 0.0
    source: str = "web_speech"
    language: str = "en-US"
    duration_ms: int = 0
    is_final: bool = True
    alternatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript": self.transcript,
            "confidence": self.confidence,
            "source": self.source,
            "language": self.language,
            "duration_ms": self.duration_ms,
            "is_final": self.is_final,
            "alternatives": self.alternatives,
        }


@dataclass
class ParsedCommand:
    """A parsed voice command with intent and entities."""

    intent: IntentType
    confidence: float = 0.0
    entities: list[Entity] = field(default_factory=list)
    raw_transcript: str = ""
    requires_confirmation: bool = False
    suggestion: str | None = None

    def get_entity(self, entity_type: EntityType) -> Entity | None:
        """Get first entity of a given type."""
        for entity in self.entities:
            if entity.type == entity_type:
                return entity
        return None

    def get_entities(self, entity_type: EntityType) -> list[Entity]:
        """Get all entities of a given type."""
        return [e for e in self.entities if e.type == entity_type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "entities": [e.to_dict() for e in self.entities],
            "raw_transcript": self.raw_transcript,
            "requires_confirmation": self.requires_confirmation,
            "suggestion": self.suggestion,
        }


@dataclass
class CommandResult:
    """Result from executing a voice command."""

    success: bool
    message: str
    intent: IntentType = IntentType.UNKNOWN
    data: dict[str, Any] = field(default_factory=dict)
    follow_up_prompt: str | None = None
    undo_available: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "intent": self.intent.value,
            "data": self.data,
            "follow_up_prompt": self.follow_up_prompt,
            "undo_available": self.undo_available,
            "error": self.error,
        }
