"""Per-user voice settings management.

Handles CRUD operations on voice_preferences and voice_commands tables.
"""

from __future__ import annotations

import json
from typing import Any

from tools.voice import get_connection

# Default preferences for new users
DEFAULT_PREFERENCES = {
    "enabled": True,
    "preferred_source": "web_speech",
    "language": "en-US",
    "continuous_listening": False,
    "wake_word_enabled": False,
    "audio_feedback_enabled": True,
    "visual_feedback_enabled": True,
    "confirmation_verbosity": "brief",
    "tts_enabled": False,
    "tts_voice": "alloy",
    "tts_speed": 1.0,
    "auto_execute_high_confidence": True,
    "confidence_threshold": 0.85,
    "repeat_on_low_confidence": True,
}


def get_preferences(user_id: str) -> dict[str, Any]:
    """Get voice preferences for a user, creating defaults if needed."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM voice_preferences WHERE user_id = ?", (user_id,)
    ).fetchone()

    if row:
        prefs = dict(row)
        # Convert sqlite booleans
        for key in (
            "enabled", "continuous_listening", "wake_word_enabled",
            "audio_feedback_enabled", "visual_feedback_enabled",
            "tts_enabled", "auto_execute_high_confidence",
            "repeat_on_low_confidence",
        ):
            if key in prefs:
                prefs[key] = bool(prefs[key])
        conn.close()
        return {"success": True, "data": prefs}

    # Create defaults
    conn.execute(
        """INSERT INTO voice_preferences (user_id) VALUES (?)""",
        (user_id,),
    )
    conn.commit()
    conn.close()

    return {"success": True, "data": {**DEFAULT_PREFERENCES, "user_id": user_id}}


def update_preferences(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update voice preferences for a user."""
    # Validate fields
    valid_fields = set(DEFAULT_PREFERENCES.keys())
    invalid = set(updates.keys()) - valid_fields
    if invalid:
        return {"success": False, "error": f"Invalid fields: {invalid}"}

    # Ensure user has preferences
    get_preferences(user_id)

    # Build update query
    set_clauses = []
    values = []
    for key, value in updates.items():
        if key in valid_fields:
            set_clauses.append(f"{key} = ?")
            values.append(value)

    if not set_clauses:
        return {"success": False, "error": "No valid fields to update"}

    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    values.append(user_id)

    conn = get_connection()
    conn.execute(
        f"UPDATE voice_preferences SET {', '.join(set_clauses)} WHERE user_id = ?",
        values,
    )
    conn.commit()
    conn.close()

    return get_preferences(user_id)


def get_command_history(
    user_id: str,
    limit: int = 50,
    intent: str | None = None,
) -> dict[str, Any]:
    """Get recent voice command history for a user."""
    conn = get_connection()

    query = "SELECT * FROM voice_commands WHERE user_id = ?"
    params: list[Any] = [user_id]

    if intent:
        query += " AND intent = ?"
        params.append(intent)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    commands = []
    for row in rows:
        cmd = dict(row)
        # Parse JSON fields
        for field in ("entities", "result"):
            if cmd.get(field) and isinstance(cmd[field], str):
                try:
                    cmd[field] = json.loads(cmd[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        commands.append(cmd)

    return {"success": True, "data": {"commands": commands, "count": len(commands)}}
