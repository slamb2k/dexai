"""
Session Manager for Continuous Conversations

Uses ClaudeSDKClient from the Claude Agent SDK for maintaining conversation
continuity across messages. This replaces the custom SDKSession class with
proper SDK session management.

Features:
- Maintains ClaudeSDKClient instances per user+channel
- Uses SDK's native session resumption (resume parameter)
- Handles session lifecycle (creation, resumption, cleanup)
- Integrates with DexAI's ADHD features via DexAIClient
- Persists session IDs for cross-restart resumption

Usage:
    from tools.channels.session_manager import SessionManager

    manager = SessionManager()

    # Handle a user message
    async for msg in manager.handle_message(user_id, channel, message):
        print(msg)
"""

from __future__ import annotations

import asyncio
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Callable, AsyncGenerator, Union

# Project root for paths
PROJECT_ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)


# Default session timeout
SESSION_TIMEOUT_MINUTES = 60

# Path for persisting session IDs
SESSION_STORE_PATH = PROJECT_ROOT / "data" / "sessions.json"


class Session:
    """
    Represents a user's conversation session.

    Wraps DexAIClient and maintains session state for continuity.
    Uses SDK session resumption for context persistence.
    """

    def __init__(
        self,
        user_id: str,
        channel: str,
        session_type: str = "main",
        sdk_session_id: Optional[str] = None,
        ask_user_handler: Optional[Callable] = None,
    ):
        """
        Initialize a session.

        Args:
            user_id: User identifier
            channel: Communication channel (telegram, discord, slack, cli)
            session_type: Session type (main, subagent, heartbeat, cron)
            sdk_session_id: Optional SDK session ID to resume
            ask_user_handler: Optional handler for AskUserQuestion
        """
        self.user_id = user_id
        self.channel = channel
        self.session_type = session_type
        self.sdk_session_id = sdk_session_id
        self.ask_user_handler = ask_user_handler

        self._client = None
        self._last_activity = datetime.now()
        self._message_count = 0
        self._total_cost = 0.0
        self._created_at = datetime.now()
        # Track how many messages were sent before SDK session was established.
        # When session_id is first captured, we record how many turns were
        # "orphaned" (not part of the SDK's conversation memory). On the next
        # message we inject history one final time so those orphaned turns
        # are bridged into the resumed session.
        self._sdk_session_started_at_msg: int = 0

    def _check_post_compact(self) -> bool:
        """
        Check if the SDK session was recently compacted.

        If so, consume the compaction data and flag for history re-injection.
        After a compact the SDK's context is a summary — detailed early
        messages are gone. We inject history once to restore them.

        Returns:
            True if a compaction was detected and history should be injected
        """
        if not self.sdk_session_id:
            return False

        try:
            from tools.agent.hooks import get_compacted_session_data

            compact_data = get_compacted_session_data(self.sdk_session_id)
            if compact_data:
                logger.info(
                    f"Post-compact detected for {self.user_id} "
                    f"(session={self.sdk_session_id}). "
                    f"Re-injecting history to restore detailed context."
                )
                return True
        except ImportError:
            pass

        return False

    def _build_message_with_history(self, content: str) -> str:
        """
        Build message content with recent conversation history prepended.

        When SDK session resumption is not available (no sdk_session_id),
        fetches recent messages from the inbox to provide conversation context.
        This ensures the agent always knows about prior messages.

        Also handles two recovery cases:

        1. **Bridge**: If the SDK session was established partway through the
           conversation (e.g. session_id first captured on Message 3), the
           resumed session only knows about that one turn. Messages 1-2 are
           orphaned. We inject history one more time on the first resume to
           bridge those orphaned messages into the SDK session.

        2. **Post-compact**: After the SDK compacts the context window, early
           messages are summarized away. We detect compaction via the
           PreCompact hook and inject history once to restore detail.

        Args:
            content: Current message content

        Returns:
            Message with history context prepended, or original content if
            session resumption is available or no history exists
        """
        # Only inject history after the first message
        if self._message_count <= 1:
            return content

        # Check if a compaction just happened — if so, force history injection
        post_compact = self._check_post_compact()

        if self.sdk_session_id and not post_compact:
            # SDK session exists and no compact. Check if there are orphaned
            # messages that the SDK doesn't know about (messages before the
            # session started). If the session was established on the same
            # turn as the first message (_sdk_session_started_at_msg <= 1),
            # the SDK has full history and we can skip injection.
            if self._sdk_session_started_at_msg <= 1:
                return content

            # Session was established mid-conversation. Check if this is
            # the first resume after capture (one turn after capture).
            if self._message_count == self._sdk_session_started_at_msg + 1:
                logger.info(
                    f"Bridging {self._sdk_session_started_at_msg - 1} orphaned "
                    f"messages into SDK session for {self.user_id}"
                )
                # Fall through to inject history this one time
            else:
                # Already bridged on a prior turn, SDK has full context now
                return content

        try:
            from tools.channels import inbox

            history = inbox.get_conversation_history(
                user_id=self.user_id,
                limit=10,
                channel=self.channel,
            )

            if not history:
                return content

            # History comes in descending order, reverse to chronological
            history.reverse()

            # Build conversation context
            history_lines = []
            for msg in history:
                role = "User" if msg.direction == "inbound" else "Assistant"
                # Truncate long messages in history
                msg_content = msg.content[:500] if msg.content else ""
                if len(msg.content or "") > 500:
                    msg_content += "..."
                history_lines.append(f"[{role}]: {msg_content}")

            if not history_lines:
                return content

            history_context = "\n".join(history_lines)
            return (
                f"[CONVERSATION HISTORY - for context, these are our recent messages]\n"
                f"{history_context}\n"
                f"[END HISTORY]\n\n"
                f"{content}"
            )

        except Exception as e:
            logger.warning(f"Failed to load message history: {e}")
            return content

    async def send_message(self, content: str) -> dict[str, Any]:
        """
        Send a message and get a response.

        Uses DexAIClient with session resumption for context continuity.
        Falls back to injecting conversation history from inbox when
        session resumption is not available.

        Args:
            content: Message content

        Returns:
            Dict with response data
        """
        from tools.agent.sdk_client import DexAIClient

        self._last_activity = datetime.now()
        self._message_count += 1

        # Prepend conversation history if no SDK session to resume
        enriched_content = self._build_message_with_history(content)

        if self.sdk_session_id:
            logger.info(f"Resuming SDK session {self.sdk_session_id} for {self.user_id}")
        elif self._message_count > 1:
            logger.info(f"No SDK session for {self.user_id}, injecting message history")

        try:
            async with DexAIClient(
                user_id=self.user_id,
                session_type=self.session_type,
                channel=self.channel,
                resume_session_id=self.sdk_session_id,
                ask_user_handler=self.ask_user_handler,
            ) as client:
                result = await client.query(enriched_content)

                # Capture session ID for future resumption
                if client.session_id and not self.sdk_session_id:
                    self.sdk_session_id = client.session_id
                    self._sdk_session_started_at_msg = self._message_count
                    logger.info(
                        f"Captured SDK session_id for {self.user_id} on message "
                        f"{self._message_count}: {self.sdk_session_id}"
                    )
                elif client.session_id:
                    self.sdk_session_id = client.session_id

                self._total_cost += result.cost_usd

                return {
                    "success": True,
                    "content": result.text,
                    "tool_uses": result.tool_uses,
                    "cost_usd": result.cost_usd,
                    "session_cost_usd": self._total_cost,
                    "message_count": self._message_count,
                    "model": result.model,
                    "complexity": result.complexity,
                    "routing_reasoning": result.routing_reasoning,
                    "sdk_session_id": self.sdk_session_id,
                }

        except Exception as e:
            logger.error(f"Session query error for {self.user_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": "",
            }

    async def stream_response(self, content: str) -> AsyncIterator[Any]:
        """
        Send a message and stream the response.

        Yields message objects from the SDK.

        Args:
            content: Message content

        Yields:
            SDK message objects
        """
        from tools.agent.sdk_client import DexAIClient

        self._last_activity = datetime.now()
        self._message_count += 1

        # Prepend conversation history if no SDK session to resume
        enriched_content = self._build_message_with_history(content)

        try:
            async with DexAIClient(
                user_id=self.user_id,
                session_type=self.session_type,
                channel=self.channel,
                resume_session_id=self.sdk_session_id,
                ask_user_handler=self.ask_user_handler,
            ) as client:
                await client._client.query(enriched_content)

                async for msg in client.receive_response():
                    # Capture session ID using robust extraction
                    if not self.sdk_session_id:
                        from tools.agent.sdk_client import DexAIClient as _Client
                        sid = _Client._extract_session_id(msg)
                        if sid:
                            self.sdk_session_id = sid
                            self._sdk_session_started_at_msg = self._message_count

                    yield msg

                # Fallback: capture from client after stream completes
                if not self.sdk_session_id and client.session_id:
                    self.sdk_session_id = client.session_id
                    self._sdk_session_started_at_msg = self._message_count

        except Exception as e:
            logger.error(f"Session stream error for {self.user_id}: {e}")
            raise

    async def stream_input(
        self,
        message_generator: AsyncGenerator[Union[str, dict], None],
    ) -> AsyncIterator[Any]:
        """
        Send messages dynamically using streaming input mode.

        The SDK supports streaming input where an AsyncGenerator can yield messages
        dynamically. This allows users to add context mid-conversation (interruption).

        The generator should yield messages in one of these formats:
        - String: Converted to {"type": "user", "message": {"role": "user", "content": str}}
        - Dict: Used directly, should follow SDK format:
            {"type": "user", "message": {"role": "user", "content": "..."}}

        Args:
            message_generator: AsyncGenerator yielding messages

        Yields:
            SDK message objects (responses from Claude)

        Example:
            async def my_messages():
                yield "Initial question"
                await asyncio.sleep(2)  # User thinking...
                yield "Actually, also consider this context"

            async for response in session.stream_input(my_messages()):
                print(response)
        """
        from tools.agent.sdk_client import DexAIClient

        self._last_activity = datetime.now()
        self._message_count += 1

        try:
            async with DexAIClient(
                user_id=self.user_id,
                session_type=self.session_type,
                channel=self.channel,
                resume_session_id=self.sdk_session_id,
                ask_user_handler=self.ask_user_handler,
            ) as client:
                async for msg in client.query_stream(message_generator):
                    # Capture session ID using robust extraction
                    if not self.sdk_session_id:
                        from tools.agent.sdk_client import DexAIClient as _Client
                        sid = _Client._extract_session_id(msg)
                        if sid:
                            self.sdk_session_id = sid
                            self._sdk_session_started_at_msg = self._message_count

                    yield msg

                # Fallback: capture from client after stream completes
                if not self.sdk_session_id and client.session_id:
                    self.sdk_session_id = client.session_id
                    self._sdk_session_started_at_msg = self._message_count

        except Exception as e:
            logger.error(f"Session stream input error for {self.user_id}: {e}")
            raise

    @property
    def is_stale(self) -> bool:
        """Check if session is stale (inactive for too long)."""
        timeout = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        return datetime.now() - self._last_activity > timeout

    @property
    def age_minutes(self) -> float:
        """Get session age in minutes."""
        return (datetime.now() - self._created_at).total_seconds() / 60

    def to_dict(self) -> dict[str, Any]:
        """Serialize session state for persistence."""
        return {
            "user_id": self.user_id,
            "channel": self.channel,
            "session_type": self.session_type,
            "sdk_session_id": self.sdk_session_id,
            "sdk_session_started_at_msg": self._sdk_session_started_at_msg,
            "last_activity": self._last_activity.isoformat(),
            "message_count": self._message_count,
            "total_cost": self._total_cost,
            "created_at": self._created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict, ask_user_handler: Optional[Callable] = None) -> "Session":
        """Restore session from persisted state."""
        session = cls(
            user_id=data["user_id"],
            channel=data["channel"],
            session_type=data.get("session_type", "main"),
            sdk_session_id=data.get("sdk_session_id"),
            ask_user_handler=ask_user_handler,
        )
        session._last_activity = datetime.fromisoformat(data["last_activity"])
        session._message_count = data.get("message_count", 0)
        session._total_cost = data.get("total_cost", 0.0)
        session._sdk_session_started_at_msg = data.get("sdk_session_started_at_msg", 0)
        if "created_at" in data:
            session._created_at = datetime.fromisoformat(data["created_at"])
        return session


class SessionManager:
    """
    Manages conversation sessions across users and channels.

    Provides:
    - Session creation and retrieval
    - SDK session resumption support
    - Automatic stale session cleanup
    - Optional persistence across restarts
    """

    def __init__(
        self,
        persist: bool = True,
        timeout_minutes: int = SESSION_TIMEOUT_MINUTES,
    ):
        """
        Initialize session manager.

        Args:
            persist: Whether to persist sessions to disk
            timeout_minutes: Session timeout in minutes
        """
        self._sessions: dict[str, Session] = {}
        self._persist = persist
        self._timeout_minutes = timeout_minutes

        # Load persisted sessions
        if persist:
            self._load_sessions()

    def _session_key(self, user_id: str, channel: str) -> str:
        """Generate session key from user and channel."""
        return f"{user_id}:{channel}"

    def get_session(
        self,
        user_id: str,
        channel: str,
        session_type: str = "main",
        ask_user_handler: Optional[Callable] = None,
    ) -> Session:
        """
        Get or create a session for a user.

        Args:
            user_id: User identifier
            channel: Communication channel
            session_type: Session type (main, subagent, heartbeat, cron)
            ask_user_handler: Optional handler for AskUserQuestion

        Returns:
            Session instance
        """
        self._cleanup_stale_sessions()

        key = self._session_key(user_id, channel)

        if key in self._sessions:
            session = self._sessions[key]
            # Update handler if provided
            if ask_user_handler:
                session.ask_user_handler = ask_user_handler
            return session

        # Create new session
        session = Session(
            user_id=user_id,
            channel=channel,
            session_type=session_type,
            ask_user_handler=ask_user_handler,
        )
        self._sessions[key] = session

        logger.debug(f"Created new session for {key}")
        return session

    async def handle_message(
        self,
        user_id: str,
        channel: str,
        content: str,
        session_type: str = "main",
        context: Optional[dict] = None,
        ask_user_handler: Optional[Callable] = None,
    ) -> dict[str, Any]:
        """
        Handle an incoming message.

        Gets or creates session and sends the message.

        Args:
            user_id: User identifier
            channel: Communication channel
            content: Message content
            session_type: Session type
            context: Optional context dict (for heartbeat, cron detection)
            ask_user_handler: Optional handler for AskUserQuestion

        Returns:
            Response dict from session
        """
        # Detect session type from context if provided
        if context:
            session_type = self._detect_session_type(context, session_type)

        session = self.get_session(
            user_id=user_id,
            channel=channel,
            session_type=session_type,
            ask_user_handler=ask_user_handler,
        )

        result = await session.send_message(content)

        # Persist sessions after each message
        if self._persist:
            self._save_sessions()

        return result

    async def stream_message(
        self,
        user_id: str,
        channel: str,
        content: Union[str, AsyncGenerator[Union[str, dict], None]],
        session_type: str = "main",
        ask_user_handler: Optional[Callable] = None,
    ) -> AsyncIterator[Any]:
        """
        Handle a message with streaming response.

        Supports both static messages (str) and dynamic message streams
        (AsyncGenerator) for streaming input mode.

        Args:
            user_id: User identifier
            channel: Communication channel
            content: Message content (str) or message generator (AsyncGenerator)
            session_type: Session type
            ask_user_handler: Optional handler for AskUserQuestion

        Yields:
            SDK message objects

        Example with static message:
            async for msg in manager.stream_message(user_id, channel, "Hello"):
                print(msg)

        Example with streaming input:
            async def messages():
                yield "Initial question"
                await asyncio.sleep(2)
                yield "More context"

            async for msg in manager.stream_message(user_id, channel, messages()):
                print(msg)
        """
        session = self.get_session(
            user_id=user_id,
            channel=channel,
            session_type=session_type,
            ask_user_handler=ask_user_handler,
        )

        # Check if content is a generator (streaming input mode)
        if hasattr(content, "__anext__"):
            # AsyncGenerator - use streaming input
            async for msg in session.stream_input(content):
                yield msg
        else:
            # Static string - use regular streaming
            async for msg in session.stream_response(content):
                yield msg

        # Persist after streaming complete
        if self._persist:
            self._save_sessions()

    def _detect_session_type(self, context: dict, default: str) -> str:
        """Detect session type from context."""
        if context.get("is_heartbeat"):
            return "heartbeat"
        if context.get("is_cron") or context.get("is_scheduled"):
            return "cron"
        if context.get("is_subagent") or context.get("spawned_by_task"):
            return "subagent"
        return default

    def clear_session(self, user_id: str, channel: str) -> bool:
        """
        Clear a specific session.

        Args:
            user_id: User identifier
            channel: Communication channel

        Returns:
            True if session was cleared, False if not found
        """
        key = self._session_key(user_id, channel)
        if key in self._sessions:
            del self._sessions[key]
            if self._persist:
                self._save_sessions()
            return True
        return False

    def clear_all_sessions(self, user_id: Optional[str] = None) -> int:
        """
        Clear sessions.

        Args:
            user_id: Optional user ID to clear only their sessions

        Returns:
            Number of sessions cleared
        """
        if user_id:
            keys_to_remove = [
                k for k in self._sessions.keys()
                if k.startswith(f"{user_id}:")
            ]
        else:
            keys_to_remove = list(self._sessions.keys())

        for key in keys_to_remove:
            del self._sessions[key]

        if self._persist:
            self._save_sessions()

        return len(keys_to_remove)

    def _cleanup_stale_sessions(self) -> int:
        """Remove stale sessions."""
        stale_keys = [
            key for key, session in self._sessions.items()
            if session.is_stale
        ]
        for key in stale_keys:
            logger.debug(f"Cleaning up stale session: {key}")
            del self._sessions[key]

        if stale_keys and self._persist:
            self._save_sessions()

        return len(stale_keys)

    def get_session_stats(self) -> dict[str, Any]:
        """Get statistics about active sessions."""
        self._cleanup_stale_sessions()

        return {
            "active_sessions": len(self._sessions),
            "sessions": [
                {
                    "key": key,
                    "age_minutes": session.age_minutes,
                    "message_count": session._message_count,
                    "total_cost": session._total_cost,
                    "has_sdk_session": bool(session.sdk_session_id),
                }
                for key, session in self._sessions.items()
            ],
        }

    def _save_sessions(self) -> None:
        """Persist sessions to disk."""
        try:
            SESSION_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)

            data = {
                key: session.to_dict()
                for key, session in self._sessions.items()
                if not session.is_stale
            }

            with open(SESSION_STORE_PATH, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save sessions: {e}")

    def _load_sessions(self) -> None:
        """Load persisted sessions from disk."""
        if not SESSION_STORE_PATH.exists():
            return

        try:
            with open(SESSION_STORE_PATH) as f:
                data = json.load(f)

            for key, session_data in data.items():
                try:
                    session = Session.from_dict(session_data)
                    if not session.is_stale:
                        self._sessions[key] = session
                except Exception as e:
                    logger.warning(f"Failed to restore session {key}: {e}")

            logger.info(f"Loaded {len(self._sessions)} sessions from disk")

        except Exception as e:
            logger.warning(f"Failed to load sessions: {e}")


# =============================================================================
# Global Instance
# =============================================================================

_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """
    Get the global session manager instance.

    Returns:
        SessionManager singleton
    """
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing session manager."""
    import argparse

    parser = argparse.ArgumentParser(description="Session Manager")
    parser.add_argument("--stats", action="store_true", help="Show session stats")
    parser.add_argument("--clear", action="store_true", help="Clear all sessions")
    parser.add_argument("--user", help="User ID for operations")
    parser.add_argument("--channel", default="cli", help="Channel")
    parser.add_argument("--message", help="Send a test message")

    args = parser.parse_args()

    manager = get_session_manager()

    if args.stats:
        stats = manager.get_session_stats()
        print(f"Active sessions: {stats['active_sessions']}")
        for session in stats["sessions"]:
            print(f"  {session['key']}: {session['message_count']} msgs, "
                  f"${session['total_cost']:.4f}, "
                  f"{session['age_minutes']:.1f} min old")

    elif args.clear:
        count = manager.clear_all_sessions(args.user)
        print(f"Cleared {count} sessions")

    elif args.message and args.user:
        async def test():
            result = await manager.handle_message(
                user_id=args.user,
                channel=args.channel,
                content=args.message,
            )
            if result.get("success"):
                print(f"Response: {result['content']}")
                print(f"Cost: ${result.get('cost_usd', 0):.4f}")
            else:
                print(f"Error: {result.get('error')}")

        asyncio.run(test())

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
