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
    The client is kept alive across messages to maintain conversation context.
    Each session has an isolated workspace directory for file operations.
    """

    def __init__(
        self,
        user_id: str,
        channel: str,
        session_type: str = "main",
        sdk_session_id: Optional[str] = None,
        ask_user_handler: Optional[Callable] = None,
        workspace_path: Optional[Path] = None,
    ):
        """
        Initialize a session.

        Args:
            user_id: User identifier
            channel: Communication channel (telegram, discord, slack, cli)
            session_type: Session type (main, subagent, heartbeat, cron)
            sdk_session_id: Optional SDK session ID to resume
            ask_user_handler: Optional handler for AskUserQuestion
            workspace_path: Optional workspace path (auto-created if None)
        """
        self.user_id = user_id
        self.channel = channel
        self.session_type = session_type
        self.sdk_session_id = sdk_session_id
        self.ask_user_handler = ask_user_handler
        self.workspace_path = workspace_path

        self._client = None
        self._client_active = False  # Track if client context is active
        self._last_activity = datetime.now()
        self._message_count = 0
        self._total_cost = 0.0
        self._created_at = datetime.now()
        self._lock = asyncio.Lock()  # Prevent concurrent client access

    async def _ensure_client(self) -> None:
        """
        Ensure the DexAIClient is initialized and active.

        The client is kept alive to maintain conversation context across messages.
        Workspace is created/retrieved for isolated file operations.
        """
        if self._client_active and self._client is not None:
            return

        from tools.agent.sdk_client import DexAIClient
        from tools.agent.workspace_manager import get_workspace_manager

        # Clean up any existing client first
        await self._cleanup_client()

        # Get or create workspace for this session
        if self.workspace_path is None:
            workspace_manager = get_workspace_manager()
            self.workspace_path = workspace_manager.get_workspace(
                user_id=self.user_id,
                channel=self.channel,
            )

        # Create new client with workspace as working directory
        self._client = DexAIClient(
            user_id=self.user_id,
            working_dir=str(self.workspace_path),
            session_type=self.session_type,
            channel=self.channel,
            resume_session_id=self.sdk_session_id,
            ask_user_handler=self.ask_user_handler,
        )

        # Enter the async context to start the client
        await self._client.__aenter__()
        self._client_active = True
        logger.debug(f"Initialized persistent client for session {self.user_id}:{self.channel} "
                     f"with workspace {self.workspace_path}")

    async def _cleanup_client(self) -> None:
        """Clean up the client when session ends."""
        if self._client is not None and self._client_active:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error cleaning up client: {e}")
            finally:
                self._client = None
                self._client_active = False

    async def send_message(self, content: str) -> dict[str, Any]:
        """
        Send a message and get a response.

        The client is kept alive across messages to maintain conversation context.
        This allows Claude to remember previous messages in the conversation.

        Args:
            content: Message content

        Returns:
            Dict with response data
        """
        async with self._lock:  # Prevent concurrent message sends
            self._last_activity = datetime.now()
            self._message_count += 1

            try:
                # Ensure client is initialized (reuse if already active)
                await self._ensure_client()

                # Query using the persistent client
                result = await self._client.query(content)

                # Capture session ID for persistence
                if self._client.session_id:
                    self.sdk_session_id = self._client.session_id

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
                # Clean up client on error - will be recreated on next message
                await self._cleanup_client()
                return {
                    "success": False,
                    "error": str(e),
                    "content": "",
                }

    async def stream_response(self, content: str) -> AsyncIterator[Any]:
        """
        Send a message and stream the response.

        Uses the persistent client to maintain conversation context.

        Args:
            content: Message content

        Yields:
            SDK message objects
        """
        async with self._lock:
            self._last_activity = datetime.now()
            self._message_count += 1

            try:
                # Ensure client is initialized (reuse if already active)
                await self._ensure_client()

                await self._client._client.query(content)

                async for msg in self._client.receive_response():
                    # Capture session ID from init message
                    if hasattr(msg, "type") and msg.type == "system":
                        if hasattr(msg, "subtype") and msg.subtype == "init":
                            if hasattr(msg, "session_id"):
                                self.sdk_session_id = msg.session_id

                    yield msg

            except Exception as e:
                logger.error(f"Session stream error for {self.user_id}: {e}")
                await self._cleanup_client()
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
        async with self._lock:
            self._last_activity = datetime.now()
            self._message_count += 1

            try:
                # Ensure client is initialized
                await self._ensure_client()

                async for msg in self._client.query_stream(message_generator):
                    # Capture session ID from init message
                    if hasattr(msg, "type") and msg.type == "system":
                        if hasattr(msg, "subtype") and msg.subtype == "init":
                            if hasattr(msg, "session_id"):
                                self.sdk_session_id = msg.session_id

                    yield msg

            except Exception as e:
                logger.error(f"Session stream input error for {self.user_id}: {e}")
                await self._cleanup_client()
                raise

    async def close(self) -> None:
        """
        Close the session and clean up resources.

        Should be called when the session is no longer needed.
        Also marks the workspace session as ended for cleanup.
        """
        await self._cleanup_client()

        # Mark workspace session end (for SESSION scoped workspaces)
        if self.workspace_path:
            try:
                from tools.agent.workspace_manager import get_workspace_manager
                workspace_manager = get_workspace_manager()
                workspace_manager.mark_session_end(self.user_id, self.channel)
            except Exception as e:
                logger.debug(f"Failed to mark workspace session end: {e}")

        logger.debug(f"Closed session for {self.user_id}:{self.channel}")

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
            "workspace_path": str(self.workspace_path) if self.workspace_path else None,
            "last_activity": self._last_activity.isoformat(),
            "message_count": self._message_count,
            "total_cost": self._total_cost,
            "created_at": self._created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict, ask_user_handler: Optional[Callable] = None) -> "Session":
        """Restore session from persisted state."""
        # Restore workspace path if present
        workspace_path = None
        if data.get("workspace_path"):
            workspace_path = Path(data["workspace_path"])

        session = cls(
            user_id=data["user_id"],
            channel=data["channel"],
            session_type=data.get("session_type", "main"),
            sdk_session_id=data.get("sdk_session_id"),
            ask_user_handler=ask_user_handler,
            workspace_path=workspace_path,
        )
        session._last_activity = datetime.fromisoformat(data["last_activity"])
        session._message_count = data.get("message_count", 0)
        session._total_cost = data.get("total_cost", 0.0)
        if "created_at" in data:
            session._created_at = datetime.fromisoformat(data["created_at"])
        # Note: _lock and _client are initialized in __init__
        # The client will be lazily initialized on first message
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

    async def clear_session(self, user_id: str, channel: str) -> bool:
        """
        Clear a specific session and clean up resources.

        Args:
            user_id: User identifier
            channel: Communication channel

        Returns:
            True if session was cleared, False if not found
        """
        key = self._session_key(user_id, channel)
        if key in self._sessions:
            session = self._sessions[key]
            await session.close()
            del self._sessions[key]
            if self._persist:
                self._save_sessions()
            return True
        return False

    async def clear_all_sessions(self, user_id: Optional[str] = None) -> int:
        """
        Clear sessions and clean up resources.

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
            session = self._sessions[key]
            await session.close()
            del self._sessions[key]

        if self._persist:
            self._save_sessions()

        return len(keys_to_remove)

    def _cleanup_stale_sessions(self) -> int:
        """Remove stale sessions and clean up their resources."""
        stale_keys = [
            key for key, session in self._sessions.items()
            if session.is_stale
        ]
        for key in stale_keys:
            logger.debug(f"Cleaning up stale session: {key}")
            session = self._sessions[key]
            # Schedule cleanup in background (don't block)
            try:
                asyncio.create_task(session.close())
            except RuntimeError:
                # No event loop running - try synchronous cleanup
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(session.close())
                    loop.close()
                except Exception:
                    pass
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
                    "client_active": session._client_active,
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
                  f"{session['age_minutes']:.1f} min old, "
                  f"client_active: {session.get('client_active', False)}")

    elif args.clear:
        async def do_clear():
            return await manager.clear_all_sessions(args.user)

        count = asyncio.run(do_clear())
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
                print(f"Message count: {result.get('message_count', 0)}")
            else:
                print(f"Error: {result.get('error')}")

        asyncio.run(test())

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
