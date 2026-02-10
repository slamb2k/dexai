"""
Phase 15d: Poll Handler

Manages poll creation, vote tracking, result aggregation, and poll
closing. Poll state is stored in the same interactive_state table used
by ButtonHandler (with element_type='poll').

Usage:
    handler = PollHandler()
    result = await handler.create_poll(poll, context)
    vote = await handler.handle_vote(poll_id, option_id, user_id)
    results = await handler.get_results(poll_id)
    closed = await handler.close_poll(poll_id)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from tools.channels.models import Poll, PollOption, RenderContext

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class PollHandler:
    """
    Handles poll lifecycle for Phase 15d.

    Creates polls in SQLite, tracks votes per option, aggregates results,
    and supports closing polls. Shares the interactive_state table with
    ButtonHandler using element_type='poll'.
    """

    def __init__(self, db_path: str | None = None) -> None:
        """
        Initialize PollHandler.

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

        This is the same table used by ButtonHandler. Both handlers share
        state storage, distinguished by the element_type column.
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

    async def create_poll(
        self, poll: Poll, context: RenderContext
    ) -> dict:
        """
        Store a poll and its options in the database.

        Creates one interactive_state row for the poll itself (storing the
        full poll definition and vote tracking in element_data) and assigns
        callback IDs for each option so votes can be resolved.

        Args:
            poll: Poll definition with question and options.
            context: RenderContext with channel, user, and message info.

        Returns:
            Dict with poll_id and a mapping of option callback IDs.
            Example:
                {
                    "poll_id": "poll_a1b2c3d4e5f6",
                    "callbacks": {
                        "poll_opt_aaa111": "Option A",
                        "poll_opt_bbb222": "Option B",
                    }
                }
        """
        conn = self._get_connection()
        try:
            poll_id = f"poll_{uuid4().hex[:12]}"
            entry_id = str(uuid4())

            # Build option callbacks
            option_callbacks: dict[str, str] = {}
            option_callback_ids: dict[str, str] = {}  # option.id -> callback_id
            for option in poll.options:
                callback_id = f"poll_opt_{uuid4().hex[:12]}"
                option_callbacks[callback_id] = option.text
                option_callback_ids[option.id] = callback_id

            # Store poll data with vote tracking
            element_data = json.dumps({
                "poll": poll.to_dict(),
                "poll_id": poll_id,
                "votes": {opt.id: 0 for opt in poll.options},
                "voters": {},  # user_id -> list of option_ids voted for
                "option_callbacks": option_callback_ids,
                "closed": False,
            })

            expires_at_str: str | None = None
            if poll.close_at is not None:
                expires_at_str = poll.close_at.isoformat()

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
                    "poll",
                    element_data,
                    expires_at_str,
                    poll_id,
                ),
            )
            conn.commit()

            logger.info(
                "Created poll '%s' with %d options (poll_id=%s)",
                poll.question,
                len(poll.options),
                poll_id,
            )

            return {
                "poll_id": poll_id,
                "callbacks": option_callbacks,
            }
        finally:
            conn.close()

    async def handle_vote(
        self, poll_id: str, option_id: str, user_id: str
    ) -> dict:
        """
        Record a vote on a poll option.

        Validates the poll exists and is not closed, then increments the
        vote count for the selected option. For single-choice polls,
        previous votes by the same user are replaced.

        Args:
            poll_id: The poll identifier (used as callback_id in DB).
            option_id: The option.id being voted for.
            user_id: ID of the user casting the vote.

        Returns:
            On success: {"success": True, "results": {option_id: vote_count, ...}}
            On failure: {"success": False, "error": str}
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM interactive_state WHERE callback_id = ? AND element_type = 'poll'",
                (poll_id,),
            ).fetchone()

            if row is None:
                logger.warning("Poll not found: %s", poll_id)
                return {"success": False, "error": "Poll not found"}

            element_data = json.loads(row["element_data"])

            # Check if poll is closed
            if element_data.get("closed", False):
                return {"success": False, "error": "Poll is closed"}

            # Check expiration
            if row["expires_at"] is not None:
                expires_at = datetime.fromisoformat(row["expires_at"])
                if datetime.now() > expires_at:
                    return {"success": False, "error": "Poll has expired"}

            # Validate option_id exists
            votes = element_data.get("votes", {})
            if option_id not in votes:
                return {"success": False, "error": f"Invalid option: {option_id}"}

            voters = element_data.get("voters", {})
            poll_data = element_data.get("poll", {})
            multiple_choice = poll_data.get("multiple_choice", False)

            if not multiple_choice:
                # Single choice: remove previous vote if any
                if user_id in voters:
                    previous_options = voters[user_id]
                    for prev_opt in previous_options:
                        if prev_opt in votes:
                            votes[prev_opt] = max(0, votes[prev_opt] - 1)

                voters[user_id] = [option_id]
                votes[option_id] = votes.get(option_id, 0) + 1
            else:
                # Multiple choice: toggle vote
                if user_id not in voters:
                    voters[user_id] = []

                if option_id in voters[user_id]:
                    # Remove vote (toggle off)
                    voters[user_id].remove(option_id)
                    votes[option_id] = max(0, votes[option_id] - 1)
                else:
                    # Add vote
                    voters[user_id].append(option_id)
                    votes[option_id] = votes.get(option_id, 0) + 1

            # Update stored data
            element_data["votes"] = votes
            element_data["voters"] = voters

            conn.execute(
                "UPDATE interactive_state SET element_data = ? WHERE callback_id = ?",
                (json.dumps(element_data), poll_id),
            )
            conn.commit()

            logger.info(
                "Vote recorded on poll %s: option=%s, user=%s",
                poll_id,
                option_id,
                user_id,
            )

            return {"success": True, "results": votes}
        finally:
            conn.close()

    async def get_results(self, poll_id: str) -> dict:
        """
        Get current poll results.

        Args:
            poll_id: The poll identifier.

        Returns:
            On success: {
                "success": True,
                "question": str,
                "results": {option_id: vote_count, ...},
                "total_votes": int,
                "closed": bool,
            }
            On failure: {"success": False, "error": str}
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM interactive_state WHERE callback_id = ? AND element_type = 'poll'",
                (poll_id,),
            ).fetchone()

            if row is None:
                return {"success": False, "error": "Poll not found"}

            element_data = json.loads(row["element_data"])
            votes = element_data.get("votes", {})
            poll_data = element_data.get("poll", {})
            total_votes = sum(votes.values())

            return {
                "success": True,
                "question": poll_data.get("question", ""),
                "results": votes,
                "total_votes": total_votes,
                "closed": element_data.get("closed", False),
            }
        finally:
            conn.close()

    async def close_poll(self, poll_id: str) -> dict:
        """
        Close a poll so no further votes are accepted.

        Args:
            poll_id: The poll identifier.

        Returns:
            On success: {"success": True, "results": {option_id: vote_count, ...}, "total_votes": int}
            On failure: {"success": False, "error": str}
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM interactive_state WHERE callback_id = ? AND element_type = 'poll'",
                (poll_id,),
            ).fetchone()

            if row is None:
                return {"success": False, "error": "Poll not found"}

            element_data = json.loads(row["element_data"])

            if element_data.get("closed", False):
                return {"success": False, "error": "Poll is already closed"}

            element_data["closed"] = True
            votes = element_data.get("votes", {})
            total_votes = sum(votes.values())

            conn.execute(
                "UPDATE interactive_state SET element_data = ? WHERE callback_id = ?",
                (json.dumps(element_data), poll_id),
            )
            conn.commit()

            logger.info("Poll closed: %s (total votes: %d)", poll_id, total_votes)

            return {
                "success": True,
                "results": votes,
                "total_votes": total_votes,
            }
        finally:
            conn.close()
