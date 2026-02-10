"""Entity extraction from voice command transcripts.

Extracts structured entities (dates, durations, priorities, etc.)
from natural language voice input.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from tools.voice.models import Entity, EntityType, IntentType


def extract_entities(
    text: str,
    intent: IntentType = IntentType.UNKNOWN,
) -> list[Entity]:
    """Extract all entities from a voice transcript.

    Runs all extractors and returns combined results.
    """
    entities: list[Entity] = []
    text_lower = text.lower()

    entities.extend(extract_datetime_entities(text_lower))
    entities.extend(extract_duration_entities(text_lower))
    entities.extend(extract_priority_entity(text_lower))
    entities.extend(extract_energy_entity(text_lower))

    return entities


def extract_datetime_entities(text: str) -> list[Entity]:
    """Extract date/time references from text.

    Handles: "today", "tomorrow", "in 2 hours", "at 3pm",
    "this afternoon", "next monday", etc.
    """
    entities: list[Entity] = []
    now = datetime.now()

    # Relative day references
    day_patterns: list[tuple[str, Any]] = [
        (r"\btoday\b", now.strftime("%Y-%m-%d")),
        (r"\btomorrow\b", (now + timedelta(days=1)).strftime("%Y-%m-%d")),
        (r"\byesterday\b", (now - timedelta(days=1)).strftime("%Y-%m-%d")),
        (r"\bthis\s+(?:afternoon|evening)\b", now.strftime("%Y-%m-%d") + "T14:00"),
        (r"\btonight\b", now.strftime("%Y-%m-%d") + "T19:00"),
        (r"\bthis\s+morning\b", now.strftime("%Y-%m-%d") + "T09:00"),
    ]

    for pattern, value in day_patterns:
        match = re.search(pattern, text)
        if match:
            entities.append(Entity(
                type=EntityType.DATETIME,
                value=value,
                raw_text=match.group(),
            ))

    # "in X hours/minutes"
    relative_match = re.search(
        r"\bin\s+(\d+)\s+(hour|minute|min|hr)s?\b", text
    )
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        if unit in ("hour", "hr"):
            target = now + timedelta(hours=amount)
        else:
            target = now + timedelta(minutes=amount)
        entities.append(Entity(
            type=EntityType.DATETIME,
            value=target.strftime("%Y-%m-%dT%H:%M"),
            raw_text=relative_match.group(),
        ))

    # "at X:XX" or "at Xpm/am"
    time_match = re.search(
        r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b", text
    )
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = (time_match.group(3) or "").replace(".", "").lower()

        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)

        entities.append(Entity(
            type=EntityType.DATETIME,
            value=target.strftime("%Y-%m-%dT%H:%M"),
            raw_text=time_match.group(),
        ))

    # Day of week: "next monday", "on friday"
    days_of_week = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    dow_match = re.search(
        r"\b(?:next|on|this)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        text,
    )
    if dow_match:
        target_dow = days_of_week[dow_match.group(1)]
        current_dow = now.weekday()
        days_ahead = (target_dow - current_dow) % 7
        if days_ahead == 0:
            days_ahead = 7  # "next monday" when it's monday = next week
        target = now + timedelta(days=days_ahead)
        entities.append(Entity(
            type=EntityType.DATETIME,
            value=target.strftime("%Y-%m-%d"),
            raw_text=dow_match.group(),
        ))

    return entities


def extract_duration_entities(text: str) -> list[Entity]:
    """Extract duration references from text.

    Handles: "for 30 minutes", "2 hours", "half an hour", etc.
    """
    entities: list[Entity] = []

    # "for X minutes/hours"
    match = re.search(
        r"\b(?:for\s+)?(\d+)\s+(minute|min|hour|hr)s?\b", text
    )
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        minutes = amount * 60 if unit in ("hour", "hr") else amount
        entities.append(Entity(
            type=EntityType.DURATION,
            value=str(minutes),
            raw_text=match.group(),
        ))

    # "half an hour"
    if re.search(r"\bhalf\s+(?:an?\s+)?hour\b", text):
        entities.append(Entity(
            type=EntityType.DURATION,
            value="30",
            raw_text="half an hour",
        ))

    return entities


def extract_priority_entity(text: str) -> list[Entity]:
    """Extract priority from text.

    Handles: "high priority", "urgent", "low priority", etc.
    """
    entities: list[Entity] = []

    priority_map = {
        r"\b(?:urgent|critical|asap|immediately)\b": "high",
        r"\b(?:high|important)\s*(?:priority)?\b": "high",
        r"\b(?:medium|normal)\s*(?:priority)?\b": "medium",
        r"\b(?:low|whenever|no\s+rush)\s*(?:priority)?\b": "low",
    }

    for pattern, priority in priority_map.items():
        match = re.search(pattern, text)
        if match:
            entities.append(Entity(
                type=EntityType.PRIORITY,
                value=priority,
                raw_text=match.group(),
            ))
            break  # Only one priority per command

    return entities


def extract_energy_entity(text: str) -> list[Entity]:
    """Extract energy level from text.

    Handles: "low energy", "I'm tired", "feeling great", etc.
    """
    entities: list[Entity] = []

    energy_map = {
        r"\b(?:tired|exhausted|low\s+energy|drained|no\s+energy)\b": "low",
        r"\b(?:ok(?:ay)?|alright|medium\s+energy|so[\s-]so)\b": "medium",
        r"\b(?:great|energized|high\s+energy|pumped|ready|good)\b": "high",
    }

    for pattern, energy in energy_map.items():
        match = re.search(pattern, text)
        if match:
            entities.append(Entity(
                type=EntityType.ENERGY_LEVEL,
                value=energy,
                raw_text=match.group(),
            ))
            break

    return entities
