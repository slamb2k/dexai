# Phase 11: Voice Interface — Tactical Implementation Guide

**Status:** Planned
**Depends on:** Phase 0 (Security), Phase 5 (Task Engine), Phase 7 (Dashboard), Phase 10 (Mobile Push)
**Last Updated:** 2026-02-04

---

## Overview

Phase 11 adds voice interaction capabilities to DexAI, enabling hands-free task capture, queries, and control. For ADHD users, voice input dramatically reduces the friction between having a thought and capturing it — no app switching, no typing, no losing the thought while fumbling with a keyboard.

**Key Philosophy:** Voice is not a replacement for text; it's a **low-friction capture mechanism** for moments when typing isn't practical. The goal is to get thoughts out of the ADHD brain and into the system before they evaporate.

**ADHD-Specific Design:**
- **Quick capture when hands are busy:** "Dex, remind me to call mom tomorrow"
- **Reduce friction:** Voice is faster than typing for ADHD brains in motion
- **Confirmation without interruption:** Gentle audio feedback, no screen required
- **Ambient listening opt-in only:** Respect privacy, default to push-to-talk

---

## Architecture Decision: Progressive Enhancement

Rather than building a complex voice system immediately, we use a **progressive enhancement** approach:

| Phase | Approach | Features | Cost |
|-------|----------|----------|------|
| **11a** | Web Speech API | Browser-based STT, push-to-talk | Free |
| **11b** | Whisper Integration | Higher accuracy, offline option | API credits |
| **11c** | Advanced Features | Wake word, TTS, mobile integration | Medium |

**Rationale:** Web Speech API provides a zero-cost MVP that works in Chrome, Edge, and Safari. Whisper API adds accuracy for users who need it. Wake word detection and TTS are power-user features added last.

---

## Sub-Phases

| Sub-Phase | Focus | Status |
|-----------|-------|--------|
| **11a** | Browser Voice + Push-to-Talk | Planned |
| **11b** | Whisper API Integration | Planned |
| **11c** | Advanced Features (Wake Word, TTS, Mobile) | Planned |

---

## Phase 11a: Browser Voice + Push-to-Talk

### Objective

Implement voice input in the dashboard using the Web Speech API, providing zero-cost voice capture for Chrome, Edge, and Safari users with a simple push-to-talk interface.

### Directory Structure

```
tools/voice/
├── __init__.py                     # Path constants, DB connection, shared utilities
├── models.py                       # VoiceCommand, Intent, Entity, TranscriptionResult
│
├── recognition/
│   ├── __init__.py
│   ├── base.py                     # Abstract Transcriber interface
│   ├── web_speech.py               # Web Speech API wrapper (browser-side)
│   └── transcriber.py              # Server-side transcription coordinator
│
├── parser/
│   ├── __init__.py
│   ├── intent_parser.py            # Extract intents from transcribed text
│   ├── entity_extractor.py         # Extract entities (dates, tasks, people, etc.)
│   └── command_router.py           # Route parsed commands to handlers
│
├── commands/
│   ├── __init__.py
│   ├── task_commands.py            # Task-related voice commands
│   ├── reminder_commands.py        # Reminder commands
│   ├── query_commands.py           # Questions about tasks, schedule, status
│   └── control_commands.py         # System control (focus mode, navigation)
│
├── preferences/
│   ├── __init__.py
│   └── user_preferences.py         # Voice settings per user
│
└── feedback/
    ├── __init__.py
    └── audio_feedback.py           # Confirmation sounds, TTS responses (11c)
```

### Database Schema

```sql
-- Voice command history (for learning and debugging)
CREATE TABLE IF NOT EXISTS voice_commands (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,

    -- Transcription
    transcript TEXT NOT NULL,
    confidence REAL,                  -- Recognition confidence (0-1)
    source TEXT DEFAULT 'web_speech', -- 'web_speech', 'whisper_api', 'whisper_local'
    audio_duration_ms INTEGER,

    -- Parsing
    intent TEXT,                      -- Detected intent (add_task, query_next, etc.)
    entities TEXT,                    -- JSON: extracted entities
    parsed_successfully BOOLEAN DEFAULT TRUE,

    -- Execution
    handler TEXT,                     -- Which command handler processed it
    result TEXT,                      -- JSON: command result
    executed_successfully BOOLEAN,
    error_message TEXT,

    -- Timing
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    transcription_time_ms INTEGER,
    parsing_time_ms INTEGER,
    execution_time_ms INTEGER
);

-- Voice preferences per user
CREATE TABLE IF NOT EXISTS voice_preferences (
    user_id TEXT PRIMARY KEY,

    -- Recognition settings
    enabled BOOLEAN DEFAULT TRUE,
    preferred_source TEXT DEFAULT 'web_speech', -- 'web_speech', 'whisper_api', 'whisper_local'
    language TEXT DEFAULT 'en-US',
    continuous_listening BOOLEAN DEFAULT FALSE,  -- Phase 11c
    wake_word_enabled BOOLEAN DEFAULT FALSE,     -- Phase 11c

    -- Feedback settings
    audio_feedback_enabled BOOLEAN DEFAULT TRUE,
    visual_feedback_enabled BOOLEAN DEFAULT TRUE,
    confirmation_verbosity TEXT DEFAULT 'brief', -- 'silent', 'brief', 'verbose'
    tts_enabled BOOLEAN DEFAULT FALSE,           -- Phase 11c
    tts_voice TEXT DEFAULT 'default',
    tts_speed REAL DEFAULT 1.0,

    -- ADHD settings
    auto_execute_high_confidence BOOLEAN DEFAULT TRUE, -- Execute without confirmation if confidence > threshold
    confidence_threshold REAL DEFAULT 0.85,
    repeat_on_low_confidence BOOLEAN DEFAULT TRUE,

    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Voice command templates (for learning patterns)
CREATE TABLE IF NOT EXISTS voice_command_templates (
    id TEXT PRIMARY KEY,
    intent TEXT NOT NULL,
    template_pattern TEXT NOT NULL,  -- Pattern with entity placeholders
    example_phrases TEXT,            -- JSON array of example phrases
    priority INTEGER DEFAULT 5,      -- Higher priority = checked first
    user_id TEXT,                    -- NULL = global, otherwise user-specific
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_voice_commands_user ON voice_commands(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_voice_commands_intent ON voice_commands(intent);
CREATE INDEX IF NOT EXISTS idx_voice_templates_intent ON voice_command_templates(intent, priority);
```

### Tool Specifications

#### 1. `tools/voice/__init__.py`

```python
"""Voice Interface — Hands-free task capture for DexAI

Philosophy:
    Voice is a low-friction capture mechanism for ADHD brains in motion.
    The goal is to get thoughts out of the brain and into the system
    before they evaporate. Voice is not a replacement for text —
    it's a fast-path for moments when typing isn't practical.

Design Principles:
    1. Quick Capture — Sub-second from thought to stored task
    2. Low Friction — Push-to-talk by default, no complex setup
    3. Graceful Fallback — If recognition fails, never lose the thought
    4. Privacy First — No ambient listening unless explicitly enabled
    5. Confirmation Without Interruption — Gentle audio feedback

Components:
    recognition/: Speech-to-text providers (Web Speech, Whisper)
    parser/: Intent and entity extraction from transcripts
    commands/: Command handlers for different intents
    preferences/: User voice settings
    feedback/: Audio confirmation and TTS (Phase 11c)

Database: data/voice.db
    - voice_commands: Command history for learning and debugging
    - voice_preferences: Per-user voice settings
    - voice_command_templates: Pattern templates for intent matching
"""

import sqlite3
from pathlib import Path


# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "args"
DATA_PATH = PROJECT_ROOT / "data"
DB_PATH = DATA_PATH / "voice.db"


def get_connection() -> sqlite3.Connection:
    """
    Get database connection, creating tables if needed.

    Returns:
        SQLite connection with row_factory set
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Voice command history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_commands (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            transcript TEXT NOT NULL,
            confidence REAL,
            source TEXT DEFAULT 'web_speech',
            audio_duration_ms INTEGER,
            intent TEXT,
            entities TEXT,
            parsed_successfully BOOLEAN DEFAULT TRUE,
            handler TEXT,
            result TEXT,
            executed_successfully BOOLEAN,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            transcription_time_ms INTEGER,
            parsing_time_ms INTEGER,
            execution_time_ms INTEGER
        )
    """)

    # Voice preferences
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_preferences (
            user_id TEXT PRIMARY KEY,
            enabled BOOLEAN DEFAULT TRUE,
            preferred_source TEXT DEFAULT 'web_speech',
            language TEXT DEFAULT 'en-US',
            continuous_listening BOOLEAN DEFAULT FALSE,
            wake_word_enabled BOOLEAN DEFAULT FALSE,
            audio_feedback_enabled BOOLEAN DEFAULT TRUE,
            visual_feedback_enabled BOOLEAN DEFAULT TRUE,
            confirmation_verbosity TEXT DEFAULT 'brief',
            tts_enabled BOOLEAN DEFAULT FALSE,
            tts_voice TEXT DEFAULT 'default',
            tts_speed REAL DEFAULT 1.0,
            auto_execute_high_confidence BOOLEAN DEFAULT TRUE,
            confidence_threshold REAL DEFAULT 0.85,
            repeat_on_low_confidence BOOLEAN DEFAULT TRUE,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Voice command templates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_command_templates (
            id TEXT PRIMARY KEY,
            intent TEXT NOT NULL,
            template_pattern TEXT NOT NULL,
            example_phrases TEXT,
            priority INTEGER DEFAULT 5,
            user_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_commands_user "
        "ON voice_commands(user_id, created_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_commands_intent "
        "ON voice_commands(intent)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_templates_intent "
        "ON voice_command_templates(intent, priority)"
    )

    conn.commit()
    return conn


def seed_default_templates() -> None:
    """Seed default voice command templates."""
    from tools.voice.parser.intent_parser import seed_default_templates as seed
    seed()
```

#### 2. `tools/voice/models.py`

```python
"""Voice Interface Data Models"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class IntentType(Enum):
    """Recognized voice command intents."""
    # Task commands
    ADD_TASK = "add_task"
    COMPLETE_TASK = "complete_task"
    SKIP_TASK = "skip_task"
    DECOMPOSE_TASK = "decompose_task"

    # Reminder commands
    SET_REMINDER = "set_reminder"
    CANCEL_REMINDER = "cancel_reminder"
    SNOOZE_REMINDER = "snooze_reminder"

    # Query commands
    QUERY_NEXT_TASK = "query_next_task"
    QUERY_SCHEDULE = "query_schedule"
    QUERY_STATUS = "query_status"
    QUERY_SEARCH = "query_search"

    # Control commands
    START_FOCUS = "start_focus"
    END_FOCUS = "end_focus"
    PAUSE_NOTIFICATIONS = "pause_notifications"

    # Meta commands
    HELP = "help"
    REPEAT = "repeat"
    CANCEL = "cancel"
    UNDO = "undo"

    # Unknown
    UNKNOWN = "unknown"


class EntityType(Enum):
    """Recognized entity types."""
    TASK_DESCRIPTION = "task_description"
    DATETIME = "datetime"
    DURATION = "duration"
    PERSON = "person"
    PRIORITY = "priority"
    ENERGY_LEVEL = "energy_level"
    TASK_REFERENCE = "task_reference"  # "this task", "the last one"


@dataclass
class Entity:
    """Extracted entity from voice command."""
    entity_type: EntityType
    value: Any
    raw_text: str
    start_position: int
    end_position: int
    confidence: float = 1.0


@dataclass
class TranscriptionResult:
    """Result from speech-to-text transcription."""
    transcript: str
    confidence: float
    source: str  # 'web_speech', 'whisper_api', 'whisper_local'
    language: str
    duration_ms: int
    is_final: bool = True
    alternatives: list[str] = field(default_factory=list)


@dataclass
class ParsedCommand:
    """Fully parsed voice command."""
    intent: IntentType
    entities: list[Entity]
    original_transcript: str
    confidence: float  # Combined confidence from transcription + parsing
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None


@dataclass
class CommandResult:
    """Result of executing a voice command."""
    success: bool
    message: str
    data: dict | None = None
    follow_up_prompt: str | None = None  # Suggest next action
    undo_available: bool = False
    undo_command_id: str | None = None


@dataclass
class VoiceCommand:
    """Complete voice command record for database."""
    id: str
    user_id: str
    transcript: str
    confidence: float
    source: str
    audio_duration_ms: int
    intent: IntentType | None
    entities: list[Entity]
    parsed_successfully: bool
    handler: str | None
    result: CommandResult | None
    executed_successfully: bool | None
    error_message: str | None
    created_at: datetime
    transcription_time_ms: int
    parsing_time_ms: int
    execution_time_ms: int | None
```

#### 3. `tools/voice/recognition/base.py`

```python
"""Abstract base class for speech-to-text providers."""

from abc import ABC, abstractmethod
from tools.voice.models import TranscriptionResult


class BaseTranscriber(ABC):
    """Abstract interface for speech-to-text providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging and preference storage."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available in the current environment."""
        pass

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether this provider supports streaming transcription."""
        pass

    @abstractmethod
    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "en-US",
        **kwargs
    ) -> TranscriptionResult:
        """
        Transcribe audio data to text.

        Args:
            audio_data: Audio bytes (WAV format preferred)
            language: BCP-47 language code
            **kwargs: Provider-specific options

        Returns:
            TranscriptionResult with transcript and confidence
        """
        pass

    @abstractmethod
    async def transcribe_stream(
        self,
        audio_stream,
        language: str = "en-US",
        **kwargs
    ):
        """
        Transcribe streaming audio, yielding interim results.

        Args:
            audio_stream: Async iterator of audio chunks
            language: BCP-47 language code
            **kwargs: Provider-specific options

        Yields:
            TranscriptionResult (interim results have is_final=False)
        """
        pass
```

#### 4. `tools/voice/recognition/web_speech.py`

```python
"""Web Speech API integration (browser-side).

This module provides the client-side JavaScript interface definition
and server-side result processing. The actual Web Speech API calls
happen in the browser; this module handles the server-side coordination.
"""

from dataclasses import dataclass
from tools.voice.models import TranscriptionResult


@dataclass
class WebSpeechConfig:
    """Configuration for Web Speech API."""
    language: str = "en-US"
    continuous: bool = False
    interim_results: bool = True
    max_alternatives: int = 3


def get_client_script(config: WebSpeechConfig | None = None) -> str:
    """
    Get JavaScript code for Web Speech API integration.

    This script is injected into the dashboard frontend to handle
    voice recognition directly in the browser.

    Returns:
        JavaScript code as string
    """
    config = config or WebSpeechConfig()

    return f'''
    class DexVoiceRecognition {{
        constructor(options = {{}}) {{
            this.recognition = null;
            this.isListening = false;
            this.onResult = options.onResult || (() => {{}});
            this.onError = options.onError || (() => {{}});
            this.onStart = options.onStart || (() => {{}});
            this.onEnd = options.onEnd || (() => {{}});

            this.config = {{
                language: '{config.language}',
                continuous: {str(config.continuous).lower()},
                interimResults: {str(config.interim_results).lower()},
                maxAlternatives: {config.max_alternatives}
            }};

            this.init();
        }}

        init() {{
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

            if (!SpeechRecognition) {{
                console.error('Web Speech API not supported');
                return;
            }}

            this.recognition = new SpeechRecognition();
            this.recognition.lang = this.config.language;
            this.recognition.continuous = this.config.continuous;
            this.recognition.interimResults = this.config.interimResults;
            this.recognition.maxAlternatives = this.config.maxAlternatives;

            this.recognition.onresult = (event) => {{
                const result = event.results[event.results.length - 1];
                const transcript = result[0].transcript;
                const confidence = result[0].confidence;
                const isFinal = result.isFinal;

                const alternatives = [];
                for (let i = 1; i < result.length; i++) {{
                    alternatives.push(result[i].transcript);
                }}

                this.onResult({{
                    transcript,
                    confidence,
                    isFinal,
                    alternatives,
                    source: 'web_speech'
                }});
            }};

            this.recognition.onerror = (event) => {{
                this.onError(event.error);
                this.isListening = false;
            }};

            this.recognition.onstart = () => {{
                this.isListening = true;
                this.onStart();
            }};

            this.recognition.onend = () => {{
                this.isListening = false;
                this.onEnd();
            }};
        }}

        start() {{
            if (this.recognition && !this.isListening) {{
                this.recognition.start();
            }}
        }}

        stop() {{
            if (this.recognition && this.isListening) {{
                this.recognition.stop();
            }}
        }}

        isSupported() {{
            return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
        }}
    }}

    // Export for use in React components
    window.DexVoiceRecognition = DexVoiceRecognition;
    '''


def process_web_speech_result(result: dict) -> TranscriptionResult:
    """
    Process a result from the Web Speech API client.

    Args:
        result: Dictionary from client-side onResult callback

    Returns:
        TranscriptionResult
    """
    return TranscriptionResult(
        transcript=result.get("transcript", ""),
        confidence=result.get("confidence", 0.0),
        source="web_speech",
        language=result.get("language", "en-US"),
        duration_ms=result.get("duration_ms", 0),
        is_final=result.get("isFinal", True),
        alternatives=result.get("alternatives", [])
    )
```

#### 5. `tools/voice/parser/intent_parser.py`

```python
"""Parse voice command transcripts to extract intent."""

import re
import json
from typing import Tuple
from tools.voice import get_connection
from tools.voice.models import IntentType, ParsedCommand, Entity


# Intent patterns with priority (higher = matched first)
INTENT_PATTERNS: list[Tuple[IntentType, list[str], int]] = [
    # Task commands
    (IntentType.ADD_TASK, [
        r"^add (?:a )?task[:\s]+(.+)$",
        r"^create (?:a )?task[:\s]+(.+)$",
        r"^new task[:\s]+(.+)$",
        r"^remind me to (.+)$",
        r"^i need to (.+)$",
        r"^don't forget to (.+)$",
    ], 10),

    (IntentType.COMPLETE_TASK, [
        r"^(?:mark|set) (?:task |it )?(?:as )?(?:done|complete|finished)$",
        r"^(?:i )?finished (?:the |this |my )?(?:task)?$",
        r"^done(?: with (?:this|it|the task))?$",
        r"^complete(?: (?:this|current))? ?(?:task)?$",
    ], 9),

    (IntentType.SKIP_TASK, [
        r"^skip (?:this |the |current )?task$",
        r"^skip it$",
        r"^move on$",
        r"^next task$",
    ], 9),

    # Reminder commands
    (IntentType.SET_REMINDER, [
        r"^(?:set (?:a )?)?reminder[:\s]+(.+)$",
        r"^remind me (?:to |about )?(.+)$",
    ], 8),

    (IntentType.SNOOZE_REMINDER, [
        r"^snooze(?: (?:for )?(\d+) (?:minutes?|mins?))?$",
        r"^remind me (?:again )?later$",
        r"^not now$",
    ], 8),

    # Query commands
    (IntentType.QUERY_NEXT_TASK, [
        r"^what(?:'s| is) (?:my )?next(?: task)?$",
        r"^what should i (?:do|work on)(?: next)?$",
        r"^next$",
        r"^what(?:'s| is) up$",
    ], 8),

    (IntentType.QUERY_SCHEDULE, [
        r"^what(?:'s| is) (?:on )?my (?:schedule|calendar)(?: (?:for )?today)?$",
        r"^what do i have (?:today|tomorrow|this week)$",
        r"^(?:show|list) (?:my )?(?:schedule|calendar|agenda)$",
    ], 7),

    (IntentType.QUERY_STATUS, [
        r"^(?:how am i doing|status|how(?:'s| is) it going)$",
        r"^(?:give me a )?(?:status|progress) (?:update|report)$",
    ], 6),

    (IntentType.QUERY_SEARCH, [
        r"^(?:search|find|look for)[:\s]+(.+)$",
        r"^where(?:'s| is) (?:the |my )?(.+)$",
    ], 7),

    # Control commands
    (IntentType.START_FOCUS, [
        r"^start (?:focus|deep work)(?: mode)?$",
        r"^focus mode$",
        r"^i(?:'m| am) focusing$",
        r"^do not disturb$",
    ], 9),

    (IntentType.END_FOCUS, [
        r"^(?:end|stop|exit) (?:focus|deep work)(?: mode)?$",
        r"^i(?:'m| am) done focusing$",
        r"^resume notifications$",
    ], 9),

    (IntentType.PAUSE_NOTIFICATIONS, [
        r"^(?:pause|mute|silence) (?:notifications|alerts)(?: for (\d+) (?:minutes?|mins?|hours?))?$",
        r"^quiet(?: mode)?$",
    ], 8),

    # Meta commands
    (IntentType.HELP, [
        r"^help$",
        r"^what can (?:you|i) (?:do|say)$",
        r"^(?:show )?commands$",
    ], 5),

    (IntentType.REPEAT, [
        r"^(?:say that again|repeat|what(?:'d| did) you say)$",
        r"^pardon$",
    ], 5),

    (IntentType.CANCEL, [
        r"^(?:cancel|never ?mind|forget it)$",
        r"^stop$",
    ], 10),

    (IntentType.UNDO, [
        r"^undo$",
        r"^undo (?:that|last (?:action|command))$",
    ], 10),
]


def parse_intent(transcript: str) -> Tuple[IntentType, float, list[str]]:
    """
    Parse transcript to extract intent.

    Args:
        transcript: Transcribed voice command

    Returns:
        Tuple of (IntentType, confidence, captured_groups)
    """
    normalized = transcript.lower().strip()

    # Sort patterns by priority (descending)
    sorted_patterns = sorted(
        [(intent, patterns, priority) for intent, patterns, priority in INTENT_PATTERNS],
        key=lambda x: -x[2]
    )

    for intent, patterns, priority in sorted_patterns:
        for pattern in patterns:
            match = re.match(pattern, normalized, re.IGNORECASE)
            if match:
                # Confidence based on priority and match quality
                confidence = min(0.95, 0.6 + (priority / 20))
                groups = list(match.groups()) if match.groups() else []
                return intent, confidence, groups

    return IntentType.UNKNOWN, 0.3, []


def parse_command(
    transcript: str,
    transcription_confidence: float = 1.0
) -> ParsedCommand:
    """
    Parse a voice command transcript into a structured command.

    Args:
        transcript: Transcribed voice command
        transcription_confidence: Confidence from speech recognition

    Returns:
        ParsedCommand with intent and entities
    """
    from tools.voice.parser.entity_extractor import extract_entities

    intent, intent_confidence, groups = parse_intent(transcript)
    entities = extract_entities(transcript, intent, groups)

    # Combined confidence
    combined_confidence = transcription_confidence * intent_confidence

    # Determine if confirmation is needed
    requires_confirmation = (
        combined_confidence < 0.7 or
        intent in [IntentType.COMPLETE_TASK, IntentType.UNDO]
    )

    confirmation_prompt = None
    if requires_confirmation and intent != IntentType.UNKNOWN:
        confirmation_prompt = _generate_confirmation_prompt(intent, entities)

    return ParsedCommand(
        intent=intent,
        entities=entities,
        original_transcript=transcript,
        confidence=combined_confidence,
        requires_confirmation=requires_confirmation,
        confirmation_prompt=confirmation_prompt
    )


def _generate_confirmation_prompt(intent: IntentType, entities: list[Entity]) -> str:
    """Generate a natural confirmation prompt for the user."""

    prompts = {
        IntentType.ADD_TASK: "Add task: '{}'?",
        IntentType.COMPLETE_TASK: "Mark current task as done?",
        IntentType.SKIP_TASK: "Skip this task and move to the next one?",
        IntentType.SET_REMINDER: "Set reminder: '{}'?",
        IntentType.START_FOCUS: "Start focus mode?",
        IntentType.END_FOCUS: "End focus mode?",
        IntentType.UNDO: "Undo the last action?",
    }

    template = prompts.get(intent, "Did you mean: {}?")

    # Fill in entity values
    from tools.voice.models import EntityType
    task_desc = next(
        (e.value for e in entities if e.entity_type == EntityType.TASK_DESCRIPTION),
        ""
    )

    if task_desc:
        return template.format(task_desc)
    return template.format(intent.value.replace("_", " "))


def seed_default_templates() -> None:
    """Seed default voice command templates into the database."""
    import uuid

    conn = get_connection()
    cursor = conn.cursor()

    templates = [
        # Task templates
        ("add_task", "add task {task_description}",
         '["add task buy groceries", "add task call doctor", "create task finish report"]'),
        ("complete_task", "done",
         '["done", "finished", "complete", "mark as done"]'),

        # Reminder templates
        ("set_reminder", "remind me to {task_description} {datetime}",
         '["remind me to call mom tomorrow", "remind me to take medicine at 3pm"]'),

        # Query templates
        ("query_next_task", "what is my next task",
         '["what\'s next", "what should I do", "next task"]'),
        ("query_schedule", "what is on my schedule {datetime}",
         '["what\'s on my calendar today", "show my schedule"]'),

        # Control templates
        ("start_focus", "start focus mode",
         '["focus mode", "do not disturb", "I\'m focusing"]'),
    ]

    for intent, pattern, examples in templates:
        cursor.execute("""
            INSERT OR IGNORE INTO voice_command_templates
            (id, intent, template_pattern, example_phrases, priority)
            VALUES (?, ?, ?, ?, 5)
        """, (str(uuid.uuid4()), intent, pattern, examples))

    conn.commit()
    conn.close()
```

#### 6. `tools/voice/parser/entity_extractor.py`

```python
"""Extract entities (dates, tasks, people, etc.) from voice commands."""

import re
from datetime import datetime, timedelta
from typing import Any
from tools.voice.models import Entity, EntityType, IntentType


def extract_entities(
    transcript: str,
    intent: IntentType,
    captured_groups: list[str]
) -> list[Entity]:
    """
    Extract entities from a voice command transcript.

    Args:
        transcript: Original transcript
        intent: Detected intent
        captured_groups: Regex capture groups from intent matching

    Returns:
        List of extracted entities
    """
    entities = []

    # Extract task description from captured groups
    if captured_groups and intent in [
        IntentType.ADD_TASK,
        IntentType.SET_REMINDER,
        IntentType.QUERY_SEARCH
    ]:
        task_desc = captured_groups[0].strip()
        if task_desc:
            # Find position in original transcript
            pos = transcript.lower().find(task_desc.lower())
            entities.append(Entity(
                entity_type=EntityType.TASK_DESCRIPTION,
                value=task_desc,
                raw_text=task_desc,
                start_position=pos if pos >= 0 else 0,
                end_position=pos + len(task_desc) if pos >= 0 else len(task_desc),
                confidence=0.9
            ))

    # Extract datetime entities
    datetime_entities = extract_datetime_entities(transcript)
    entities.extend(datetime_entities)

    # Extract duration entities
    duration_entities = extract_duration_entities(transcript)
    entities.extend(duration_entities)

    # Extract priority entities
    priority_entity = extract_priority_entity(transcript)
    if priority_entity:
        entities.append(priority_entity)

    # Extract energy level entities
    energy_entity = extract_energy_entity(transcript)
    if energy_entity:
        entities.append(energy_entity)

    return entities


def extract_datetime_entities(transcript: str) -> list[Entity]:
    """Extract datetime references from transcript."""
    entities = []
    normalized = transcript.lower()

    # Relative date patterns
    patterns = [
        (r"\btoday\b", lambda: datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)),
        (r"\btomorrow\b", lambda: (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)),
        (r"\bthis evening\b", lambda: datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)),
        (r"\btonight\b", lambda: datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)),
        (r"\bthis afternoon\b", lambda: datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)),
        (r"\bthis morning\b", lambda: datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)),
        (r"\bnext week\b", lambda: datetime.now() + timedelta(days=7)),
        (r"\bin an hour\b", lambda: datetime.now() + timedelta(hours=1)),
        (r"\bin (\d+) hours?\b", lambda m: datetime.now() + timedelta(hours=int(m.group(1)))),
        (r"\bin (\d+) minutes?\b", lambda m: datetime.now() + timedelta(minutes=int(m.group(1)))),
        (r"\bin (\d+) days?\b", lambda m: datetime.now() + timedelta(days=int(m.group(1)))),
    ]

    # Time patterns (e.g., "at 3pm", "at 15:00")
    time_patterns = [
        (r"\bat (\d{1,2})(:\d{2})?\s*(am|pm)?\b", _parse_time),
    ]

    for pattern, resolver in patterns:
        match = re.search(pattern, normalized)
        if match:
            try:
                if callable(resolver):
                    if hasattr(resolver, '__code__') and resolver.__code__.co_argcount > 0:
                        value = resolver(match)
                    else:
                        value = resolver()
                else:
                    value = resolver

                entities.append(Entity(
                    entity_type=EntityType.DATETIME,
                    value=value,
                    raw_text=match.group(0),
                    start_position=match.start(),
                    end_position=match.end(),
                    confidence=0.85
                ))
            except Exception:
                pass

    return entities


def _parse_time(match) -> datetime:
    """Parse a time match into a datetime."""
    hour = int(match.group(1))
    minutes = match.group(2)
    ampm = match.group(3)

    if minutes:
        minutes = int(minutes[1:])  # Remove colon
    else:
        minutes = 0

    if ampm:
        if ampm.lower() == 'pm' and hour != 12:
            hour += 12
        elif ampm.lower() == 'am' and hour == 12:
            hour = 0

    now = datetime.now()
    result = now.replace(hour=hour, minute=minutes, second=0, microsecond=0)

    # If time has passed today, assume tomorrow
    if result < now:
        result += timedelta(days=1)

    return result


def extract_duration_entities(transcript: str) -> list[Entity]:
    """Extract duration references from transcript."""
    entities = []
    normalized = transcript.lower()

    patterns = [
        (r"\bfor (\d+) minutes?\b", lambda m: timedelta(minutes=int(m.group(1)))),
        (r"\bfor (\d+) hours?\b", lambda m: timedelta(hours=int(m.group(1)))),
        (r"\bfor (\d+) days?\b", lambda m: timedelta(days=int(m.group(1)))),
    ]

    for pattern, resolver in patterns:
        match = re.search(pattern, normalized)
        if match:
            entities.append(Entity(
                entity_type=EntityType.DURATION,
                value=resolver(match),
                raw_text=match.group(0),
                start_position=match.start(),
                end_position=match.end(),
                confidence=0.9
            ))

    return entities


def extract_priority_entity(transcript: str) -> Entity | None:
    """Extract priority level from transcript."""
    normalized = transcript.lower()

    patterns = [
        (r"\b(urgent|asap|immediately|critical)\b", "critical"),
        (r"\b(high priority|important)\b", "high"),
        (r"\b(low priority|whenever|no rush)\b", "low"),
    ]

    for pattern, priority in patterns:
        match = re.search(pattern, normalized)
        if match:
            return Entity(
                entity_type=EntityType.PRIORITY,
                value=priority,
                raw_text=match.group(0),
                start_position=match.start(),
                end_position=match.end(),
                confidence=0.9
            )

    return None


def extract_energy_entity(transcript: str) -> Entity | None:
    """Extract energy level references from transcript."""
    normalized = transcript.lower()

    patterns = [
        (r"\b(high energy|energetic|pumped)\b", "high"),
        (r"\b(low energy|tired|exhausted|drained)\b", "low"),
        (r"\b(medium energy|okay|fine)\b", "medium"),
    ]

    for pattern, energy in patterns:
        match = re.search(pattern, normalized)
        if match:
            return Entity(
                entity_type=EntityType.ENERGY_LEVEL,
                value=energy,
                raw_text=match.group(0),
                start_position=match.start(),
                end_position=match.end(),
                confidence=0.85
            )

    return None
```

#### 7. `tools/voice/parser/command_router.py`

```python
"""Route parsed voice commands to appropriate handlers."""

import time
import uuid
import json
from datetime import datetime
from tools.voice import get_connection
from tools.voice.models import (
    ParsedCommand,
    CommandResult,
    VoiceCommand,
    IntentType
)


class CommandRouter:
    """Routes parsed commands to handlers and manages execution."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.handlers: dict[IntentType, callable] = {}
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register default command handlers."""
        from tools.voice.commands.task_commands import TaskCommandHandler
        from tools.voice.commands.reminder_commands import ReminderCommandHandler
        from tools.voice.commands.query_commands import QueryCommandHandler
        from tools.voice.commands.control_commands import ControlCommandHandler

        task_handler = TaskCommandHandler(self.user_id)
        reminder_handler = ReminderCommandHandler(self.user_id)
        query_handler = QueryCommandHandler(self.user_id)
        control_handler = ControlCommandHandler(self.user_id)

        # Task commands
        self.handlers[IntentType.ADD_TASK] = task_handler.add_task
        self.handlers[IntentType.COMPLETE_TASK] = task_handler.complete_task
        self.handlers[IntentType.SKIP_TASK] = task_handler.skip_task
        self.handlers[IntentType.DECOMPOSE_TASK] = task_handler.decompose_task

        # Reminder commands
        self.handlers[IntentType.SET_REMINDER] = reminder_handler.set_reminder
        self.handlers[IntentType.CANCEL_REMINDER] = reminder_handler.cancel_reminder
        self.handlers[IntentType.SNOOZE_REMINDER] = reminder_handler.snooze_reminder

        # Query commands
        self.handlers[IntentType.QUERY_NEXT_TASK] = query_handler.query_next_task
        self.handlers[IntentType.QUERY_SCHEDULE] = query_handler.query_schedule
        self.handlers[IntentType.QUERY_STATUS] = query_handler.query_status
        self.handlers[IntentType.QUERY_SEARCH] = query_handler.query_search

        # Control commands
        self.handlers[IntentType.START_FOCUS] = control_handler.start_focus
        self.handlers[IntentType.END_FOCUS] = control_handler.end_focus
        self.handlers[IntentType.PAUSE_NOTIFICATIONS] = control_handler.pause_notifications

        # Meta commands
        self.handlers[IntentType.HELP] = self._handle_help
        self.handlers[IntentType.CANCEL] = self._handle_cancel
        self.handlers[IntentType.UNDO] = self._handle_undo

    async def route(
        self,
        command: ParsedCommand,
        source: str = "web_speech",
        audio_duration_ms: int = 0,
        transcription_time_ms: int = 0,
        parsing_time_ms: int = 0
    ) -> CommandResult:
        """
        Route a parsed command to its handler.

        Args:
            command: Parsed voice command
            source: Recognition source
            audio_duration_ms: Audio duration
            transcription_time_ms: Time to transcribe
            parsing_time_ms: Time to parse

        Returns:
            CommandResult from handler
        """
        start_time = time.time()
        command_id = str(uuid.uuid4())

        handler = self.handlers.get(command.intent)

        if not handler:
            result = CommandResult(
                success=False,
                message="I didn't understand that command. Try saying 'help' for available commands.",
                data={"intent": command.intent.value}
            )
        else:
            try:
                result = await handler(command)
            except Exception as e:
                result = CommandResult(
                    success=False,
                    message=f"Something went wrong: {str(e)}",
                    data={"error": str(e)}
                )

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Log to database
        self._log_command(
            command_id=command_id,
            command=command,
            result=result,
            source=source,
            audio_duration_ms=audio_duration_ms,
            transcription_time_ms=transcription_time_ms,
            parsing_time_ms=parsing_time_ms,
            execution_time_ms=execution_time_ms
        )

        return result

    def _log_command(
        self,
        command_id: str,
        command: ParsedCommand,
        result: CommandResult,
        source: str,
        audio_duration_ms: int,
        transcription_time_ms: int,
        parsing_time_ms: int,
        execution_time_ms: int
    ):
        """Log voice command to database."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO voice_commands (
                id, user_id, transcript, confidence, source, audio_duration_ms,
                intent, entities, parsed_successfully, handler, result,
                executed_successfully, error_message, transcription_time_ms,
                parsing_time_ms, execution_time_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            command_id,
            self.user_id,
            command.original_transcript,
            command.confidence,
            source,
            audio_duration_ms,
            command.intent.value,
            json.dumps([{
                "type": e.entity_type.value,
                "value": str(e.value),
                "raw": e.raw_text
            } for e in command.entities]),
            command.intent != IntentType.UNKNOWN,
            command.intent.value,
            json.dumps({"success": result.success, "message": result.message}),
            result.success,
            None if result.success else result.message,
            transcription_time_ms,
            parsing_time_ms,
            execution_time_ms
        ))

        conn.commit()
        conn.close()

    async def _handle_help(self, command: ParsedCommand) -> CommandResult:
        """Handle help command."""
        help_text = """
Here are some things you can say:

**Tasks:**
- "Add task: [description]"
- "Done" or "Complete task"
- "Skip task" or "Next task"

**Reminders:**
- "Remind me to [action] [when]"
- "Snooze" or "Snooze for 10 minutes"

**Questions:**
- "What's my next task?"
- "What's on my schedule today?"
- "Search for [keyword]"

**Control:**
- "Start focus mode"
- "End focus mode"
- "Pause notifications"

**Other:**
- "Help" - Show this message
- "Cancel" - Cancel current action
- "Undo" - Undo last action
"""
        return CommandResult(
            success=True,
            message=help_text.strip(),
            data={"type": "help"}
        )

    async def _handle_cancel(self, command: ParsedCommand) -> CommandResult:
        """Handle cancel command."""
        return CommandResult(
            success=True,
            message="Cancelled.",
            data={"type": "cancel"}
        )

    async def _handle_undo(self, command: ParsedCommand) -> CommandResult:
        """Handle undo command."""
        # Get last successful command
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, intent, result FROM voice_commands
            WHERE user_id = ? AND executed_successfully = TRUE
            ORDER BY created_at DESC
            LIMIT 1
        """, (self.user_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return CommandResult(
                success=False,
                message="Nothing to undo.",
                data={"type": "undo"}
            )

        # TODO: Implement actual undo logic for each command type
        return CommandResult(
            success=True,
            message=f"Undid: {row['intent']}",
            data={"type": "undo", "undone_command_id": row['id']},
            undo_available=False
        )
```

#### 8. `tools/voice/commands/task_commands.py`

```python
"""Task-related voice command handlers."""

from tools.voice.models import ParsedCommand, CommandResult, EntityType


class TaskCommandHandler:
    """Handles task-related voice commands."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def add_task(self, command: ParsedCommand) -> CommandResult:
        """Handle 'add task' command."""
        from tools.tasks.manager import create_task

        # Extract task description
        task_desc = None
        for entity in command.entities:
            if entity.entity_type == EntityType.TASK_DESCRIPTION:
                task_desc = entity.value
                break

        if not task_desc:
            return CommandResult(
                success=False,
                message="What task would you like to add?",
                follow_up_prompt="Tell me the task description."
            )

        # Extract optional entities
        due_date = None
        priority = "medium"

        for entity in command.entities:
            if entity.entity_type == EntityType.DATETIME:
                due_date = entity.value
            elif entity.entity_type == EntityType.PRIORITY:
                priority = entity.value

        # Create the task
        try:
            result = await create_task(
                user_id=self.user_id,
                title=task_desc,
                due_at=due_date,
                priority=priority,
                source="voice"
            )

            if result.get("success"):
                message = f"Added: {task_desc}"
                if due_date:
                    message += f" (due {due_date.strftime('%b %d')})"

                return CommandResult(
                    success=True,
                    message=message,
                    data={"task_id": result.get("task_id")},
                    undo_available=True,
                    undo_command_id=result.get("task_id")
                )
            else:
                return CommandResult(
                    success=False,
                    message="Couldn't add that task. Try again?",
                    data={"error": result.get("error")}
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error adding task: {str(e)}"
            )

    async def complete_task(self, command: ParsedCommand) -> CommandResult:
        """Handle 'complete task' command."""
        from tools.tasks.current_step import get_current_task, complete_current_step

        try:
            # Get current task
            current = await get_current_task(self.user_id)

            if not current:
                return CommandResult(
                    success=False,
                    message="You don't have a current task.",
                    follow_up_prompt="Would you like to see what's next?"
                )

            # Complete current step (or whole task if no steps)
            result = await complete_current_step(self.user_id)

            if result.get("success"):
                task_title = current.get("title", "task")

                if result.get("task_completed"):
                    return CommandResult(
                        success=True,
                        message=f"Nice work! Completed: {task_title}",
                        data={"task_id": current.get("id"), "completed": True},
                        follow_up_prompt="What's next?",
                        undo_available=True
                    )
                else:
                    next_step = result.get("next_step", "next step")
                    return CommandResult(
                        success=True,
                        message=f"Step done. Next: {next_step}",
                        data={"task_id": current.get("id"), "step_completed": True}
                    )
            else:
                return CommandResult(
                    success=False,
                    message="Couldn't mark that complete. Try again?"
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    async def skip_task(self, command: ParsedCommand) -> CommandResult:
        """Handle 'skip task' command."""
        from tools.tasks.current_step import get_current_task, skip_current_task

        try:
            current = await get_current_task(self.user_id)

            if not current:
                return CommandResult(
                    success=False,
                    message="No task to skip.",
                    follow_up_prompt="Would you like to see what's available?"
                )

            result = await skip_current_task(self.user_id)

            if result.get("success"):
                next_task = result.get("next_task")
                if next_task:
                    return CommandResult(
                        success=True,
                        message=f"Skipped. Now: {next_task.get('title')}",
                        data={"skipped_id": current.get("id"), "new_task_id": next_task.get("id")}
                    )
                else:
                    return CommandResult(
                        success=True,
                        message="Skipped. No more tasks for now.",
                        data={"skipped_id": current.get("id")}
                    )
            else:
                return CommandResult(
                    success=False,
                    message="Couldn't skip. Try again?"
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    async def decompose_task(self, command: ParsedCommand) -> CommandResult:
        """Handle 'break down task' command."""
        from tools.tasks.decompose import decompose_task as decompose
        from tools.tasks.current_step import get_current_task

        try:
            current = await get_current_task(self.user_id)

            if not current:
                return CommandResult(
                    success=False,
                    message="No task to break down."
                )

            result = await decompose(current.get("id"))

            if result.get("success"):
                steps = result.get("steps", [])
                first_step = steps[0] if steps else "first step"

                return CommandResult(
                    success=True,
                    message=f"Broke it into {len(steps)} steps. Start with: {first_step}",
                    data={"task_id": current.get("id"), "steps": steps}
                )
            else:
                return CommandResult(
                    success=False,
                    message="Couldn't break that down."
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error: {str(e)}"
            )
```

#### 9. `tools/voice/commands/reminder_commands.py`

```python
"""Reminder-related voice command handlers."""

from datetime import datetime, timedelta
from tools.voice.models import ParsedCommand, CommandResult, EntityType


class ReminderCommandHandler:
    """Handles reminder-related voice commands."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def set_reminder(self, command: ParsedCommand) -> CommandResult:
        """Handle 'set reminder' command."""
        from tools.automation.notify import schedule_notification

        # Extract description
        description = None
        remind_at = None

        for entity in command.entities:
            if entity.entity_type == EntityType.TASK_DESCRIPTION:
                description = entity.value
            elif entity.entity_type == EntityType.DATETIME:
                remind_at = entity.value

        if not description:
            return CommandResult(
                success=False,
                message="What should I remind you about?",
                follow_up_prompt="Tell me what to remind you."
            )

        # Default to 1 hour if no time specified
        if not remind_at:
            remind_at = datetime.now() + timedelta(hours=1)

        try:
            result = await schedule_notification(
                user_id=self.user_id,
                title="Reminder",
                body=description,
                scheduled_for=remind_at,
                category="reminder",
                priority=6,
                source="voice"
            )

            if result.get("success"):
                time_str = remind_at.strftime("%I:%M %p")
                if remind_at.date() != datetime.now().date():
                    time_str = remind_at.strftime("%b %d at %I:%M %p")

                return CommandResult(
                    success=True,
                    message=f"I'll remind you: {description} at {time_str}",
                    data={"reminder_id": result.get("notification_id")},
                    undo_available=True,
                    undo_command_id=result.get("notification_id")
                )
            else:
                return CommandResult(
                    success=False,
                    message="Couldn't set that reminder."
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    async def cancel_reminder(self, command: ParsedCommand) -> CommandResult:
        """Handle 'cancel reminder' command."""
        # TODO: Implement reminder cancellation
        return CommandResult(
            success=False,
            message="Which reminder would you like to cancel?",
            follow_up_prompt="Say the reminder description or 'last reminder'."
        )

    async def snooze_reminder(self, command: ParsedCommand) -> CommandResult:
        """Handle 'snooze reminder' command."""
        # Extract duration if specified
        snooze_minutes = 10  # Default

        for entity in command.entities:
            if entity.entity_type == EntityType.DURATION:
                snooze_minutes = int(entity.value.total_seconds() / 60)

        # TODO: Implement actual snooze with notification system
        snooze_until = datetime.now() + timedelta(minutes=snooze_minutes)

        return CommandResult(
            success=True,
            message=f"Snoozed for {snooze_minutes} minutes.",
            data={"snooze_until": snooze_until.isoformat(), "minutes": snooze_minutes}
        )
```

#### 10. `tools/voice/commands/query_commands.py`

```python
"""Query-related voice command handlers."""

from datetime import datetime
from tools.voice.models import ParsedCommand, CommandResult, EntityType


class QueryCommandHandler:
    """Handles query-related voice commands."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def query_next_task(self, command: ParsedCommand) -> CommandResult:
        """Handle 'what's my next task' command."""
        from tools.tasks.current_step import get_current_task, get_current_step

        try:
            task = await get_current_task(self.user_id)

            if not task:
                return CommandResult(
                    success=True,
                    message="You don't have any tasks right now. Would you like to add one?",
                    follow_up_prompt="Say 'add task' followed by what you need to do."
                )

            step = await get_current_step(self.user_id)

            if step:
                return CommandResult(
                    success=True,
                    message=f"Your task: {task.get('title')}. Next step: {step}",
                    data={"task_id": task.get("id"), "task_title": task.get("title"), "current_step": step}
                )
            else:
                return CommandResult(
                    success=True,
                    message=f"Your next task: {task.get('title')}",
                    data={"task_id": task.get("id"), "task_title": task.get("title")}
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    async def query_schedule(self, command: ParsedCommand) -> CommandResult:
        """Handle 'what's on my schedule' command."""
        from tools.office.calendar.reader import get_today_events

        # Extract date if specified
        query_date = datetime.now()

        for entity in command.entities:
            if entity.entity_type == EntityType.DATETIME:
                query_date = entity.value

        try:
            events = await get_today_events(self.user_id, query_date)

            if not events:
                date_str = "today" if query_date.date() == datetime.now().date() else query_date.strftime("%A")
                return CommandResult(
                    success=True,
                    message=f"Your calendar is clear {date_str}.",
                    data={"events": [], "date": query_date.isoformat()}
                )

            # Format response
            event_summaries = []
            for event in events[:3]:  # Limit to 3 for voice
                time_str = event.get("start_time", "").strftime("%I:%M %p") if event.get("start_time") else ""
                event_summaries.append(f"{time_str}: {event.get('title', 'Event')}")

            message = f"You have {len(events)} event{'s' if len(events) > 1 else ''}: {', '.join(event_summaries)}"

            return CommandResult(
                success=True,
                message=message,
                data={"events": events, "date": query_date.isoformat()}
            )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Couldn't check your calendar: {str(e)}"
            )

    async def query_status(self, command: ParsedCommand) -> CommandResult:
        """Handle 'how am I doing' command."""
        from tools.tasks.manager import get_task_stats
        from tools.learning.energy_tracker import get_current_energy

        try:
            stats = await get_task_stats(self.user_id)
            energy = await get_current_energy(self.user_id)

            completed_today = stats.get("completed_today", 0)
            pending = stats.get("pending", 0)

            # Build response
            parts = []

            if completed_today > 0:
                parts.append(f"You've completed {completed_today} task{'s' if completed_today > 1 else ''} today")

            if pending > 0:
                parts.append(f"{pending} task{'s' if pending > 1 else ''} waiting")

            if energy:
                parts.append(f"Energy: {energy.get('level', 'unknown')}")

            if not parts:
                message = "Things are looking good. Nothing urgent."
            else:
                message = ". ".join(parts) + "."

            return CommandResult(
                success=True,
                message=message,
                data={"stats": stats, "energy": energy}
            )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    async def query_search(self, command: ParsedCommand) -> CommandResult:
        """Handle 'search for' command."""
        from tools.memory.hybrid_search import search

        # Extract search query
        query = None
        for entity in command.entities:
            if entity.entity_type == EntityType.TASK_DESCRIPTION:
                query = entity.value
                break

        if not query:
            return CommandResult(
                success=False,
                message="What would you like to search for?",
                follow_up_prompt="Tell me what you're looking for."
            )

        try:
            results = await search(self.user_id, query, limit=3)

            if not results:
                return CommandResult(
                    success=True,
                    message=f"I couldn't find anything matching '{query}'.",
                    data={"query": query, "results": []}
                )

            # Format results for voice
            summaries = [r.get("title", r.get("content", ""))[:50] for r in results]

            return CommandResult(
                success=True,
                message=f"Found {len(results)} results: {', '.join(summaries)}",
                data={"query": query, "results": results}
            )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Search error: {str(e)}"
            )
```

#### 11. `tools/voice/commands/control_commands.py`

```python
"""System control voice command handlers."""

from datetime import datetime, timedelta
from tools.voice.models import ParsedCommand, CommandResult, EntityType


class ControlCommandHandler:
    """Handles system control voice commands."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def start_focus(self, command: ParsedCommand) -> CommandResult:
        """Handle 'start focus mode' command."""
        from tools.automation.flow_detector import start_focus_mode

        # Extract duration if specified
        duration_minutes = 60  # Default 1 hour

        for entity in command.entities:
            if entity.entity_type == EntityType.DURATION:
                duration_minutes = int(entity.value.total_seconds() / 60)

        try:
            result = await start_focus_mode(
                user_id=self.user_id,
                duration_minutes=duration_minutes,
                source="voice"
            )

            if result.get("success"):
                return CommandResult(
                    success=True,
                    message=f"Focus mode started for {duration_minutes} minutes. I won't interrupt unless it's urgent.",
                    data={
                        "duration_minutes": duration_minutes,
                        "ends_at": result.get("ends_at")
                    }
                )
            else:
                return CommandResult(
                    success=False,
                    message="Couldn't start focus mode."
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    async def end_focus(self, command: ParsedCommand) -> CommandResult:
        """Handle 'end focus mode' command."""
        from tools.automation.flow_detector import end_focus_mode, get_flow_state

        try:
            # Check if actually in focus mode
            state = await get_flow_state(self.user_id)

            if not state.get("in_focus_mode"):
                return CommandResult(
                    success=True,
                    message="You're not in focus mode.",
                    data={"was_in_focus": False}
                )

            result = await end_focus_mode(self.user_id)

            if result.get("success"):
                # Mention any held notifications
                held_count = result.get("held_notifications", 0)
                message = "Focus mode ended."

                if held_count > 0:
                    message += f" You have {held_count} notification{'s' if held_count > 1 else ''} waiting."

                return CommandResult(
                    success=True,
                    message=message,
                    data={
                        "was_in_focus": True,
                        "duration_minutes": result.get("duration_minutes"),
                        "held_notifications": held_count
                    }
                )
            else:
                return CommandResult(
                    success=False,
                    message="Couldn't end focus mode."
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    async def pause_notifications(self, command: ParsedCommand) -> CommandResult:
        """Handle 'pause notifications' command."""
        from tools.mobile.preferences.user_preferences import set_quiet_mode

        # Extract duration if specified
        duration_minutes = 30  # Default

        for entity in command.entities:
            if entity.entity_type == EntityType.DURATION:
                duration_minutes = int(entity.value.total_seconds() / 60)

        try:
            until = datetime.now() + timedelta(minutes=duration_minutes)

            result = await set_quiet_mode(
                user_id=self.user_id,
                enabled=True,
                until=until
            )

            if result.get("success"):
                return CommandResult(
                    success=True,
                    message=f"Notifications paused for {duration_minutes} minutes.",
                    data={
                        "duration_minutes": duration_minutes,
                        "resumes_at": until.isoformat()
                    }
                )
            else:
                return CommandResult(
                    success=False,
                    message="Couldn't pause notifications."
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error: {str(e)}"
            )
```

#### 12. `tools/voice/preferences/user_preferences.py`

```python
"""Voice preference management."""

import json
from datetime import datetime
from tools.voice import get_connection


async def get_preferences(user_id: str) -> dict:
    """
    Get user's voice preferences with defaults.

    Returns:
        Preference dictionary
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM voice_preferences WHERE user_id = ?",
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)

    # Return defaults
    return {
        "user_id": user_id,
        "enabled": True,
        "preferred_source": "web_speech",
        "language": "en-US",
        "continuous_listening": False,
        "wake_word_enabled": False,
        "audio_feedback_enabled": True,
        "visual_feedback_enabled": True,
        "confirmation_verbosity": "brief",
        "tts_enabled": False,
        "tts_voice": "default",
        "tts_speed": 1.0,
        "auto_execute_high_confidence": True,
        "confidence_threshold": 0.85,
        "repeat_on_low_confidence": True
    }


async def update_preferences(user_id: str, **updates) -> dict:
    """
    Update user voice preferences.

    Args:
        user_id: User identifier
        **updates: Fields to update

    Returns:
        {"success": True, "preferences": dict}
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Ensure record exists
    cursor.execute(
        "INSERT OR IGNORE INTO voice_preferences (user_id) VALUES (?)",
        (user_id,)
    )

    # Build update query
    valid_fields = {
        "enabled", "preferred_source", "language", "continuous_listening",
        "wake_word_enabled", "audio_feedback_enabled", "visual_feedback_enabled",
        "confirmation_verbosity", "tts_enabled", "tts_voice", "tts_speed",
        "auto_execute_high_confidence", "confidence_threshold", "repeat_on_low_confidence"
    }

    update_fields = {k: v for k, v in updates.items() if k in valid_fields}

    if update_fields:
        set_clause = ", ".join(f"{k} = ?" for k in update_fields)
        values = list(update_fields.values())
        values.append(datetime.now().isoformat())
        values.append(user_id)

        cursor.execute(
            f"UPDATE voice_preferences SET {set_clause}, updated_at = ? WHERE user_id = ?",
            values
        )

    conn.commit()
    conn.close()

    prefs = await get_preferences(user_id)
    return {"success": True, "preferences": prefs}


async def set_voice_source(user_id: str, source: str) -> dict:
    """
    Set preferred voice recognition source.

    Args:
        user_id: User identifier
        source: 'web_speech', 'whisper_api', or 'whisper_local'

    Returns:
        {"success": True}
    """
    valid_sources = {"web_speech", "whisper_api", "whisper_local"}

    if source not in valid_sources:
        return {"success": False, "error": f"Invalid source. Choose from: {valid_sources}"}

    return await update_preferences(user_id, preferred_source=source)


async def set_language(user_id: str, language: str) -> dict:
    """
    Set voice recognition language.

    Args:
        user_id: User identifier
        language: BCP-47 language code (e.g., 'en-US', 'es-ES')

    Returns:
        {"success": True}
    """
    return await update_preferences(user_id, language=language)


async def toggle_wake_word(user_id: str, enabled: bool) -> dict:
    """
    Enable/disable wake word detection (Phase 11c).

    Args:
        user_id: User identifier
        enabled: Whether to enable wake word

    Returns:
        {"success": True}
    """
    return await update_preferences(user_id, wake_word_enabled=enabled)


async def get_command_history(
    user_id: str,
    limit: int = 20,
    intent_filter: str | None = None
) -> list[dict]:
    """
    Get user's voice command history.

    Args:
        user_id: User identifier
        limit: Maximum records to return
        intent_filter: Optional intent to filter by

    Returns:
        List of command records
    """
    conn = get_connection()
    cursor = conn.cursor()

    if intent_filter:
        cursor.execute("""
            SELECT * FROM voice_commands
            WHERE user_id = ? AND intent = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, intent_filter, limit))
    else:
        cursor.execute("""
            SELECT * FROM voice_commands
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
```

### Dashboard API Endpoints

Add to `tools/dashboard/backend/routes/voice.py`:

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/voice/status | Check if voice is enabled and get config |
| POST | /api/voice/transcribe | Process transcription result from client |
| POST | /api/voice/command | Parse and execute a voice command |
| GET | /api/voice/preferences | Get user voice preferences |
| PUT | /api/voice/preferences | Update voice preferences |
| GET | /api/voice/history | Get voice command history |
| GET | /api/voice/templates | Get available command templates |
| GET | /api/voice/web-speech-script | Get Web Speech API client script |

### Frontend Components

#### `frontend/components/voice/VoiceButton.tsx`

```typescript
interface VoiceButtonProps {
  onResult: (transcript: string, confidence: number) => void;
  onError: (error: string) => void;
  disabled?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

// ADHD-friendly voice button:
// - Large tap target
// - Clear visual state (idle, listening, processing)
// - Haptic feedback on mobile
// - Animated microphone icon
// - Pulsing border when listening
```

#### `frontend/components/voice/TranscriptDisplay.tsx`

```typescript
interface TranscriptDisplayProps {
  transcript: string;
  isInterim: boolean;
  confidence: number;
  intent?: string;
  processing?: boolean;
}

// Shows:
// - Live transcript as user speaks (interim results)
// - Confidence indicator
// - Detected intent badge
// - Processing spinner while executing
```

#### `frontend/components/voice/VoiceInput.tsx`

```typescript
interface VoiceInputProps {
  onCommand: (result: CommandResult) => void;
  autoExecute?: boolean;
  showTranscript?: boolean;
  position?: 'fixed' | 'inline';
}

// Full voice input component combining:
// - VoiceButton
// - TranscriptDisplay
// - Confirmation dialog (when needed)
// - Result feedback
```

### Configuration

#### `args/voice.yaml`

```yaml
# Voice Interface Configuration

recognition:
  # Default provider
  default_provider: "web_speech"  # 'web_speech', 'whisper_api', 'whisper_local'

  # Web Speech API settings
  web_speech:
    language: "en-US"
    continuous: false
    interim_results: true
    max_alternatives: 3

  # Whisper API settings (Phase 11b)
  whisper_api:
    model: "whisper-1"
    language: "en"
    temperature: 0
    max_audio_size_mb: 25

  # Local Whisper settings (Phase 11b)
  whisper_local:
    model_size: "base"  # tiny, base, small, medium, large
    device: "auto"      # cpu, cuda, auto
    cache_dir: "~/.cache/whisper"

parsing:
  # Confidence thresholds
  high_confidence: 0.85
  medium_confidence: 0.6
  low_confidence: 0.3

  # Auto-execution rules
  auto_execute_intents:
    - query_next_task
    - query_status
    - help

  confirm_intents:
    - complete_task
    - skip_task
    - undo

feedback:
  # Audio feedback (Phase 11c)
  audio:
    enabled: false
    sounds:
      listening_start: "sounds/boop.mp3"
      success: "sounds/success.mp3"
      error: "sounds/error.mp3"

  # Visual feedback
  visual:
    show_transcript: true
    show_confidence: true
    show_intent_badge: true
    processing_spinner: true

  # TTS settings (Phase 11c)
  tts:
    enabled: false
    voice: "default"
    speed: 1.0
    confirm_actions: true
    read_results: false

# ADHD-specific settings
adhd:
  # Reduce confirmation fatigue
  auto_execute_high_confidence: true

  # Quick capture mode
  quick_capture_enabled: true
  quick_capture_hotkey: "v"

  # Error recovery
  repeat_on_low_confidence: true
  suggest_on_unknown_intent: true

  # Prevent frustration
  max_retries: 2
  helpful_error_messages: true

# Wake word settings (Phase 11c)
wake_word:
  enabled: false
  phrase: "Hey Dex"
  sensitivity: 0.5
  on_device: true  # Privacy-first: process locally

# Debug settings
debug:
  log_all_transcriptions: true
  log_parsing_details: true
  show_alternatives: false
```

---

## Phase 11b: Whisper Integration

### Objective

Add OpenAI Whisper API integration for higher accuracy transcription, with optional local Whisper model support for privacy-sensitive users.

### New Tools

#### `tools/voice/recognition/whisper_api.py`

```python
"""OpenAI Whisper API integration for high-accuracy transcription."""

import httpx
from tools.voice.recognition.base import BaseTranscriber
from tools.voice.models import TranscriptionResult


class WhisperAPITranscriber(BaseTranscriber):
    """Whisper API for high-accuracy speech-to-text."""

    @property
    def name(self) -> str:
        return "whisper_api"

    @property
    def is_available(self) -> bool:
        """Check if API key is configured."""
        # Check vault for API key
        from tools.security.vault import get_secret
        return get_secret("OPENAI_API_KEY") is not None

    @property
    def supports_streaming(self) -> bool:
        return False  # Whisper API doesn't support streaming

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "en",
        **kwargs
    ) -> TranscriptionResult:
        """
        Transcribe audio using Whisper API.

        Args:
            audio_data: Audio bytes (supports mp3, mp4, wav, webm)
            language: ISO-639-1 language code
            **kwargs: Optional model, temperature, etc.

        Returns:
            TranscriptionResult
        """
        from tools.security.vault import get_secret
        import time

        api_key = get_secret("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        start_time = time.time()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": ("audio.webm", audio_data, "audio/webm")},
                data={
                    "model": kwargs.get("model", "whisper-1"),
                    "language": language[:2],  # Whisper uses ISO-639-1
                    "temperature": kwargs.get("temperature", 0),
                    "response_format": "verbose_json"
                },
                timeout=30.0
            )

            response.raise_for_status()
            data = response.json()

        duration_ms = int((time.time() - start_time) * 1000)

        return TranscriptionResult(
            transcript=data.get("text", ""),
            confidence=1.0 - data.get("temperature", 0),  # Approximate
            source="whisper_api",
            language=data.get("language", language),
            duration_ms=duration_ms,
            is_final=True,
            alternatives=[]
        )

    async def transcribe_stream(self, audio_stream, language: str = "en", **kwargs):
        """Not supported - collect audio and call transcribe()."""
        raise NotImplementedError("Whisper API does not support streaming")
```

#### `tools/voice/recognition/whisper_local.py`

```python
"""Local Whisper model for privacy-first transcription."""

from tools.voice.recognition.base import BaseTranscriber
from tools.voice.models import TranscriptionResult


class WhisperLocalTranscriber(BaseTranscriber):
    """Local Whisper model for offline, private transcription."""

    def __init__(self, model_size: str = "base", device: str = "auto"):
        self.model_size = model_size
        self.device = device
        self._model = None

    @property
    def name(self) -> str:
        return "whisper_local"

    @property
    def is_available(self) -> bool:
        """Check if whisper is installed."""
        try:
            import whisper
            return True
        except ImportError:
            return False

    @property
    def supports_streaming(self) -> bool:
        return False  # Local Whisper doesn't stream

    def _load_model(self):
        """Lazy load the model."""
        if self._model is None:
            import whisper
            import torch

            device = self.device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"

            self._model = whisper.load_model(self.model_size, device=device)

        return self._model

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "en",
        **kwargs
    ) -> TranscriptionResult:
        """
        Transcribe audio using local Whisper model.

        Args:
            audio_data: Audio bytes
            language: Language code
            **kwargs: Additional options

        Returns:
            TranscriptionResult
        """
        import tempfile
        import time

        start_time = time.time()

        # Write audio to temp file (Whisper needs a file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            model = self._load_model()

            result = model.transcribe(
                temp_path,
                language=language[:2],
                fp16=False,  # CPU compatible
                **kwargs
            )

            duration_ms = int((time.time() - start_time) * 1000)

            return TranscriptionResult(
                transcript=result.get("text", "").strip(),
                confidence=0.9,  # Local doesn't provide confidence
                source="whisper_local",
                language=result.get("language", language),
                duration_ms=duration_ms,
                is_final=True,
                alternatives=[]
            )
        finally:
            import os
            os.unlink(temp_path)

    async def transcribe_stream(self, audio_stream, language: str = "en", **kwargs):
        """Not supported - collect audio and call transcribe()."""
        raise NotImplementedError("Local Whisper does not support streaming")
```

#### `tools/voice/recognition/transcriber.py`

```python
"""Transcription coordinator - selects best available provider."""

from tools.voice.recognition.base import BaseTranscriber
from tools.voice.recognition.whisper_api import WhisperAPITranscriber
from tools.voice.recognition.whisper_local import WhisperLocalTranscriber
from tools.voice.models import TranscriptionResult


class TranscriptionCoordinator:
    """Coordinates between transcription providers with fallback."""

    def __init__(self, preferred_source: str = "web_speech"):
        self.preferred_source = preferred_source
        self._providers: dict[str, BaseTranscriber] = {}
        self._init_providers()

    def _init_providers(self):
        """Initialize available providers."""
        # Web Speech is handled client-side, not here

        whisper_api = WhisperAPITranscriber()
        if whisper_api.is_available:
            self._providers["whisper_api"] = whisper_api

        whisper_local = WhisperLocalTranscriber()
        if whisper_local.is_available:
            self._providers["whisper_local"] = whisper_local

    def get_provider(self, source: str | None = None) -> BaseTranscriber | None:
        """Get a transcription provider."""
        source = source or self.preferred_source

        if source == "web_speech":
            return None  # Handled client-side

        return self._providers.get(source)

    async def transcribe(
        self,
        audio_data: bytes,
        source: str | None = None,
        language: str = "en-US",
        **kwargs
    ) -> TranscriptionResult:
        """
        Transcribe audio using the best available provider.

        Falls back through providers if preferred is unavailable.

        Args:
            audio_data: Audio bytes
            source: Preferred source (None = use default)
            language: BCP-47 language code
            **kwargs: Provider-specific options

        Returns:
            TranscriptionResult
        """
        source = source or self.preferred_source

        # Try preferred provider
        provider = self.get_provider(source)
        if provider:
            try:
                return await provider.transcribe(audio_data, language, **kwargs)
            except Exception as e:
                # Fall through to next provider
                pass

        # Fallback order
        fallback_order = ["whisper_api", "whisper_local"]

        for fallback_source in fallback_order:
            if fallback_source == source:
                continue

            provider = self.get_provider(fallback_source)
            if provider:
                try:
                    return await provider.transcribe(audio_data, language, **kwargs)
                except Exception:
                    continue

        raise ValueError("No transcription providers available")

    def available_providers(self) -> list[str]:
        """List available transcription providers."""
        providers = ["web_speech"]  # Always available in browser
        providers.extend(self._providers.keys())
        return providers
```

### Audio Preprocessing

#### `tools/voice/recognition/audio_utils.py`

```python
"""Audio preprocessing utilities for voice recognition."""

import io
from typing import BinaryIO


def convert_to_wav(
    audio_data: bytes,
    source_format: str = "webm"
) -> bytes:
    """
    Convert audio to WAV format for processing.

    Args:
        audio_data: Input audio bytes
        source_format: Source format (webm, mp3, ogg, etc.)

    Returns:
        WAV audio bytes
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("pydub required for audio conversion: pip install pydub")

    # Load audio
    audio = AudioSegment.from_file(io.BytesIO(audio_data), format=source_format)

    # Convert to mono 16kHz WAV (optimal for speech recognition)
    audio = audio.set_channels(1).set_frame_rate(16000)

    # Export to WAV
    output = io.BytesIO()
    audio.export(output, format="wav")
    return output.getvalue()


def chunk_audio(
    audio_data: bytes,
    chunk_duration_ms: int = 30000,
    overlap_ms: int = 1000
) -> list[bytes]:
    """
    Split audio into overlapping chunks for long-form transcription.

    Args:
        audio_data: WAV audio bytes
        chunk_duration_ms: Maximum chunk duration
        overlap_ms: Overlap between chunks

    Returns:
        List of audio chunks
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("pydub required: pip install pydub")

    audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")

    chunks = []
    start = 0

    while start < len(audio):
        end = min(start + chunk_duration_ms, len(audio))
        chunk = audio[start:end]

        # Export chunk
        output = io.BytesIO()
        chunk.export(output, format="wav")
        chunks.append(output.getvalue())

        # Move start, accounting for overlap
        start = end - overlap_ms

        if start >= len(audio) - overlap_ms:
            break

    return chunks


def detect_silence(
    audio_data: bytes,
    silence_threshold_db: float = -40.0,
    min_silence_ms: int = 500
) -> list[tuple[int, int]]:
    """
    Detect silent segments in audio.

    Args:
        audio_data: WAV audio bytes
        silence_threshold_db: Volume threshold for silence
        min_silence_ms: Minimum silence duration

    Returns:
        List of (start_ms, end_ms) silence segments
    """
    try:
        from pydub import AudioSegment
        from pydub.silence import detect_silence as pydub_detect_silence
    except ImportError:
        raise ImportError("pydub required: pip install pydub")

    audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")

    return pydub_detect_silence(
        audio,
        min_silence_len=min_silence_ms,
        silence_thresh=silence_threshold_db
    )


def get_audio_duration_ms(audio_data: bytes) -> int:
    """Get audio duration in milliseconds."""
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("pydub required: pip install pydub")

    audio = AudioSegment.from_file(io.BytesIO(audio_data))
    return len(audio)
```

### Verification Checklist (Phase 11b)

- [ ] Whisper API transcriber implemented
- [ ] Local Whisper transcriber implemented
- [ ] TranscriptionCoordinator with fallback logic
- [ ] Audio preprocessing (conversion, chunking)
- [ ] API endpoint for server-side transcription
- [ ] Preferences for source selection
- [ ] Cost tracking for API usage
- [ ] Accuracy comparison logging

---

## Phase 11c: Advanced Features

### Objective

Add wake word detection, text-to-speech responses, and mobile voice integration.

### Wake Word Detection

#### `tools/voice/recognition/wake_word.py`

```python
"""On-device wake word detection for 'Hey Dex'."""

# Uses Porcupine or similar on-device wake word engine
# Processes audio locally for privacy
# Only activates full recognition after wake word detected

class WakeWordDetector:
    """
    On-device wake word detection.

    Privacy-first: All processing happens locally.
    No audio sent to servers until wake word detected.
    """

    def __init__(self, wake_phrase: str = "hey dex", sensitivity: float = 0.5):
        self.wake_phrase = wake_phrase
        self.sensitivity = sensitivity
        self._engine = None

    async def start_listening(self, on_wake: callable):
        """
        Start listening for wake word.

        Args:
            on_wake: Callback when wake word detected
        """
        pass

    async def stop_listening(self):
        """Stop wake word detection."""
        pass
```

### Text-to-Speech

#### `tools/voice/feedback/tts.py`

```python
"""Text-to-speech for voice responses."""

class TextToSpeech:
    """
    Generate spoken responses.

    Uses Web Speech API (browser) or cloud TTS for quality.
    """

    async def speak(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0
    ):
        """
        Speak text aloud.

        Args:
            text: Text to speak
            voice: Voice identifier
            speed: Speech rate multiplier
        """
        pass

    def get_client_script(self) -> str:
        """Get JavaScript for browser-side TTS."""
        return '''
        class DexTTS {
            speak(text, options = {}) {
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.rate = options.speed || 1.0;
                speechSynthesis.speak(utterance);
            }

            cancel() {
                speechSynthesis.cancel();
            }
        }
        window.DexTTS = DexTTS;
        '''
```

### Mobile Integration

For Phase 11c, integrate voice with the Expo mobile app:

- Add voice button to WebView overlay
- Handle microphone permissions natively
- Use native speech recognition on mobile
- Bridge voice results to web dashboard

### Verification Checklist (Phase 11c)

- [ ] Wake word detector implemented
- [ ] Wake word sensitivity configurable
- [ ] TTS client script for browser
- [ ] TTS voice selection
- [ ] Mobile voice button component
- [ ] Native microphone permissions
- [ ] Mobile-to-web voice bridge
- [ ] Continuous listening mode (opt-in)

---

## Supported Voice Commands

| Category | Command Examples | Intent |
|----------|------------------|--------|
| **Add Task** | "Add task: buy groceries" | add_task |
| | "Remind me to call mom" | add_task |
| | "Create task: finish report" | add_task |
| | "I need to email John" | add_task |
| **Complete** | "Done" / "Finished" | complete_task |
| | "Mark as complete" | complete_task |
| | "Task done" | complete_task |
| **Skip** | "Skip task" / "Next task" | skip_task |
| | "Move on" | skip_task |
| **Query** | "What's my next task?" | query_next_task |
| | "What should I do?" | query_next_task |
| | "What's on my calendar?" | query_schedule |
| | "How am I doing?" | query_status |
| | "Search for [keyword]" | query_search |
| **Reminders** | "Remind me to [action] [time]" | set_reminder |
| | "Snooze" / "Snooze for 10 minutes" | snooze_reminder |
| **Focus** | "Start focus mode" | start_focus |
| | "End focus mode" | end_focus |
| | "Do not disturb" | start_focus |
| **Control** | "Pause notifications" | pause_notifications |
| | "Quiet mode" | pause_notifications |
| **Meta** | "Help" / "What can I say?" | help |
| | "Cancel" / "Never mind" | cancel |
| | "Undo" | undo |

---

## ADHD-Specific Design Principles

### Voice Capture Philosophy

| Principle | Implementation |
|-----------|----------------|
| **Quick capture** | Push-to-talk with single button, no menu navigation |
| **Don't lose the thought** | Show transcript immediately, even if not understood |
| **Forgiveness** | "Cancel" always available, undo for completed actions |
| **No punishment** | Unknown commands get helpful suggestions, not errors |

### Feedback Design

| Principle | Implementation |
|-----------|----------------|
| **Immediate confirmation** | Visual + optional audio feedback within 200ms |
| **Brief responses** | Voice responses are single sentences |
| **No interruption** | TTS is interruptible by any user input |
| **Clear state** | Always obvious whether system is listening or not |

### Error Handling

| Principle | Implementation |
|-----------|----------------|
| **Assume good intent** | Low-confidence parses suggest closest match |
| **Offer alternatives** | "Did you mean: [option]?" |
| **Easy retry** | "Try again" button always visible |
| **Preserve input** | Original transcript always available |

---

## Dependencies

### Python Packages

```
# Core voice processing
SpeechRecognition>=3.10.0   # Unified STT interface
pydub>=0.25.0               # Audio processing

# Optional: Whisper
openai>=1.0.0               # Whisper API (Phase 11b)
openai-whisper>=20231117    # Local Whisper (Phase 11b, optional)
torch>=2.0.0                # For local Whisper (optional)

# Optional: Wake word (Phase 11c)
pvporcupine>=3.0.0          # On-device wake word detection
```

### Frontend Packages

```json
{
  "dependencies": {
    // No new dependencies - uses native Web Speech API
  }
}
```

---

## Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Microphone access** | Requires explicit permission, revocable at any time |
| **Audio storage** | Transcripts stored, raw audio discarded immediately |
| **Wake word privacy** | On-device processing only, no cloud for detection |
| **Sensitive data** | Don't transcribe in shared spaces warning |
| **API keys** | Whisper API key stored in vault, never exposed to client |
| **Command injection** | Voice transcripts sanitized before parsing |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Recognition accuracy (Web Speech) | >85% word accuracy |
| Recognition accuracy (Whisper) | >95% word accuracy |
| Command recognition rate | >90% of supported commands |
| Time to capture (thought to stored) | <3 seconds |
| User adoption (voice-enabled users) | >30% use voice at least weekly |
| Voice vs text preference | Survey shows voice preferred for quick capture |
| Error recovery rate | >80% of failed commands recovered within 1 retry |

---

## Implementation Order

### Phase 11a: Browser Voice + Push-to-Talk

1. **Create `tools/voice/__init__.py`**
   - Database schema
   - Path constants
   - Connection helper

2. **Create `tools/voice/models.py`**
   - VoiceCommand, Intent, Entity dataclasses
   - TranscriptionResult, ParsedCommand, CommandResult

3. **Create `tools/voice/recognition/web_speech.py`**
   - Client-side JavaScript code
   - Server-side result processing

4. **Create `tools/voice/parser/intent_parser.py`**
   - Intent patterns
   - parse_intent() function
   - seed_default_templates()

5. **Create `tools/voice/parser/entity_extractor.py`**
   - Datetime extraction
   - Duration extraction
   - Priority/energy extraction

6. **Create `tools/voice/parser/command_router.py`**
   - CommandRouter class
   - Handler registration
   - Command logging

7. **Create command handlers**
   - `task_commands.py`
   - `reminder_commands.py`
   - `query_commands.py`
   - `control_commands.py`

8. **Create `tools/voice/preferences/user_preferences.py`**
   - Get/update preferences
   - Command history

9. **Create dashboard API routes**
   - `tools/dashboard/backend/routes/voice.py`
   - All endpoints from table above

10. **Create frontend components**
    - VoiceButton.tsx
    - TranscriptDisplay.tsx
    - VoiceInput.tsx

11. **Create `args/voice.yaml`**
    - Configuration with defaults

12. **Integration testing**
    - End-to-end voice flow
    - Command recognition accuracy
    - Error handling

### Verification Checklist (Phase 11a)

#### Backend
- [ ] Database tables created correctly
- [ ] Web Speech client script generated
- [ ] Intent parser recognizes all patterns
- [ ] Entity extractor handles dates/times
- [ ] Command router dispatches correctly
- [ ] Task commands create/complete tasks
- [ ] Reminder commands schedule notifications
- [ ] Query commands return correct data
- [ ] Control commands affect flow state
- [ ] Preferences persist correctly
- [ ] Command history logged

#### Frontend
- [ ] Voice button renders and responds
- [ ] Transcript displays in real-time
- [ ] Confidence indicator accurate
- [ ] Intent badge shows detected intent
- [ ] Confirmation dialog works
- [ ] Result feedback clear
- [ ] Error states handled gracefully

#### ADHD-Specific
- [ ] Single-button capture (no menus)
- [ ] Sub-3-second capture time
- [ ] Unknown commands get suggestions
- [ ] Cancel always available
- [ ] Undo works for completed actions
- [ ] Visual feedback immediate
- [ ] No guilt language in responses

---

*This guide will be updated as implementation progresses.*
