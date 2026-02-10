"""Voice Interface - Hands-free task capture and control (Phase 11)

Philosophy:
    Voice is not a replacement for text; it's a low-friction capture mechanism
    for moments when typing isn't practical. The goal is to get thoughts out of
    the ADHD brain and into the system before they evaporate.

Components:
    models.py: Data models (IntentType, EntityType, dataclasses)
    recognition/: Speech recognition (Web Speech API config, Whisper adapter)
    parser/: Intent parsing, entity extraction, command routing
    commands/: Voice command handlers (task, reminder, query, control)
    preferences/: Per-user voice settings

ADHD Design Principles:
    - Quick capture when hands are busy
    - Reduce friction between thought and stored task
    - Gentle confirmation without interruption
    - Push-to-talk by default (respect privacy)

Usage:
    from tools.voice.parser.intent_parser import parse_command
    from tools.voice.parser.command_router import CommandRouter

    parsed = parse_command("add task buy groceries")
    router = CommandRouter()
    result = await router.route_command(parsed, user_id="alice")
"""

import sqlite3
from pathlib import Path

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "voice.db"
CONFIG_PATH = PROJECT_ROOT / "args" / "voice.yaml"


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables on first use."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create voice tables if they don't exist."""
    conn.executescript("""
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
        );

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
            tts_voice TEXT DEFAULT 'alloy',
            tts_speed REAL DEFAULT 1.0,
            auto_execute_high_confidence BOOLEAN DEFAULT TRUE,
            confidence_threshold REAL DEFAULT 0.85,
            repeat_on_low_confidence BOOLEAN DEFAULT TRUE,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS voice_command_templates (
            id TEXT PRIMARY KEY,
            intent TEXT NOT NULL,
            template_pattern TEXT NOT NULL,
            example_phrases TEXT,
            priority INTEGER DEFAULT 5,
            user_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_voice_commands_user
            ON voice_commands(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_voice_commands_intent
            ON voice_commands(intent);
        CREATE INDEX IF NOT EXISTS idx_voice_templates_intent
            ON voice_command_templates(intent, priority);
    """)
    conn.commit()


__all__ = [
    "CONFIG_PATH",
    "DB_PATH",
    "PROJECT_ROOT",
    "get_connection",
]
