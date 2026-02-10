"""
Phase 15d: Button Handler

Manages interactive button creation, state persistence, and callback
resolution. Button state is stored in SQLite so callbacks can be resolved
after the original message context is gone.

Usage:
    handler = ButtonHandler()
    result = await handler.create_buttons(button_group, context)
    callback = await handler.handle_callback(callback_id, user_id, channel)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from tools.channels.models import Button, ButtonGroup, RenderContext

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class ButtonHandler:
    """
    Handles interactive button lifecycle for Phase 15d.

    Creates button state entries in SQLite, maps callback IDs to button
    actions, and validates callbacks when users interact with buttons.
    """

    def __init__(self, db_path: str | None = None) -> None:
        """
        Initialize ButtonHandler.

        Args:
            db_path: Path to SQLite database. Defaults to data/media.db
                     relative to project root.
        """
        if db_path is None:
            self.db_path = str(PROJECT_ROOT / "data" / "media.db")
        else:
            self.db_path = db_path
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Return a SQLite connection to the database.

        Creates parent directories if they do not exist.

        Returns:
            sqlite3.Connection to the configured database path.
        """
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        """
        Create the interactive_state table and indexes if they do not exist.

        Table columns:
            id              - Primary key (UUID)
            message_id      - Platform message ID this element belongs to
            user_id         - User who owns/created this element
            channel         - Channel name (telegram, discord, slack, etc.)
            element_type    - Type of element ('button', 'poll', 'select')
            element_data    - JSON-encoded element-specific data
            created_at      - Timestamp of creation
            expires_at      - Optional expiration timestamp
            callback_id     - Unique callback identifier for resolving interactions
        """
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interactive_state (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    element_type TEXT NOT NULL,
                    element_data TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME,
                    callback_id TEXT UNIQUE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_interactive_callback
                ON interactive_state (callback_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_interactive_user
                ON interactive_state (user_id, created_at)
            """)
            conn.commit()
        finally:
            conn.close()

    async def create_buttons(
        self, button_group: ButtonGroup, context: RenderContext
    ) -> dict:
        """
        Store button state in the database and assign callback IDs.

        Each button in the group gets a unique callback_id that can be used
        to resolve the button action when a user clicks it.

        Args:
            button_group: ButtonGroup containing the buttons to register.
            context: RenderContext with channel, user, and message info.

        Returns:
            Dict mapping callback_id to button label for each button.
            Example: {"btn_a1b2c3d4e5f6": "Approve", "btn_f6e5d4c3b2a1": "Reject"}
        """
        conn = self._get_connection()
        callback_map: dict[str, str] = {}
        try:
            for button in button_group.buttons:
                entry_id = str(uuid4())
                callback_id = f"btn_{uuid4().hex[:12]}"

                element_data = json.dumps({
                    "button": button.to_dict(),
                    "group_message_id": button_group.message_id,
                    "group_user_id": button_group.user_id,
                })

                expires_at_str: str | None = None
                if button_group.expires_at is not None:
                    expires_at_str = button_group.expires_at.isoformat()

                conn.execute(
                    """
                    INSERT INTO interactive_state
                        (id, message_id, user_id, channel, element_type,
                         element_data, expires_at, callback_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        context.message_id,
                        context.user_id,
                        context.channel,
                        "button",
                        element_data,
                        expires_at_str,
                        callback_id,
                    ),
                )
                callback_map[callback_id] = button.label

            conn.commit()
            logger.info(
                "Created %d button callbacks for message %s",
                len(callback_map),
                context.message_id,
            )
        finally:
            conn.close()

        return callback_map

    async def handle_callback(
        self, callback_id: str, user_id: str, channel: str
    ) -> dict:
        """
        Resolve a button callback interaction.

        Looks up the callback_id in the database, validates it has not
        expired, and returns the associated action and label.

        Args:
            callback_id: The unique callback identifier from the button.
            user_id: ID of the user who clicked the button.
            channel: Channel where the interaction occurred.

        Returns:
            On success: {"success": True, "action": str, "label": str}
            On failure: {"success": False, "error": str}
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM interactive_state WHERE callback_id = ?",
                (callback_id,),
            ).fetchone()

            if row is None:
                logger.warning("Callback not found: %s", callback_id)
                return {"success": False, "error": "Callback not found"}

            # Check expiration
            if row["expires_at"] is not None:
                expires_at = datetime.fromisoformat(row["expires_at"])
                if datetime.now() > expires_at:
                    logger.info("Callback expired: %s", callback_id)
                    return {"success": False, "error": "Button has expired"}

            # Parse element data
            element_data = json.loads(row["element_data"])
            button_data = element_data.get("button", {})
            action = button_data.get("action", "")
            label = button_data.get("label", "")

            logger.info(
                "Callback resolved: %s -> action=%s, label=%s, user=%s",
                callback_id,
                action,
                label,
                user_id,
            )
            return {"success": True, "action": action, "label": label}
        finally:
            conn.close()

    async def cleanup_expired(self) -> int:
        """
        Delete all expired interactive_state entries.

        Returns:
            Number of expired entries deleted.
        """
        conn = self._get_connection()
        try:
            now = datetime.now().isoformat()
            cursor = conn.execute(
                """
                DELETE FROM interactive_state
                WHERE expires_at IS NOT NULL AND expires_at < ?
                """,
                (now,),
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info("Cleaned up %d expired interactive entries", deleted)
            return deleted
        finally:
            conn.close()
