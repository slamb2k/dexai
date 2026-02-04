"""
SDK Handler for Channel Messages

Handles messages from channel adapters using the DexAI SDK client.
Replaces agent_handler.py with a cleaner integration.

Features:
- Uses DexAIClient wrapper for ADHD-aware responses
- Integrates with router's security pipeline
- Stores messages in unified inbox
- Handles streaming responses
- Properly truncates for channel limits

Usage:
    from tools.channels.sdk_handler import sdk_handler
    router.add_message_handler(sdk_handler)
"""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure project root is in path
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.channels.models import UnifiedMessage


# Channel-specific message limits
CHANNEL_MESSAGE_LIMITS = {
    "telegram": 4096,
    "discord": 2000,
    "slack": 40000,
    "cli": 100000,
    "api": 100000,
}

# Default limit for unknown channels
DEFAULT_MESSAGE_LIMIT = 2000


class SDKSession:
    """
    Manages an SDK session for a user.

    Maintains state across messages for conversation continuity.
    """

    def __init__(self, user_id: str, working_dir: str | None = None):
        """
        Initialize SDK session.

        Args:
            user_id: User identifier for permissions and context
            working_dir: Working directory for file operations
        """
        self.user_id = user_id
        self.working_dir = working_dir or str(PROJECT_ROOT)
        self._client = None
        self._last_activity: datetime = datetime.now()
        self._message_count: int = 0
        self._total_cost: float = 0.0

    async def query(self, message: str, channel: str = "cli") -> dict[str, Any]:
        """
        Send a query to the SDK agent.

        Args:
            message: User's message content
            channel: Channel name for response formatting

        Returns:
            Dict with response content and metadata
        """
        try:
            from tools.agent.sdk_client import DexAIClient
        except ImportError:
            return {
                "success": False,
                "error": "SDK not installed",
                "content": "Agent SDK not installed. Please run: uv pip install claude-agent-sdk",
            }

        self._last_activity = datetime.now()
        self._message_count += 1

        try:
            async with DexAIClient(
                user_id=self.user_id,
                working_dir=self.working_dir
            ) as client:
                result = await client.query(message)

                self._total_cost += result.cost_usd

                # Get channel message limit
                limit = CHANNEL_MESSAGE_LIMITS.get(channel, DEFAULT_MESSAGE_LIMIT)

                # Truncate if needed
                content = result.text
                if len(content) > limit - 100:  # Leave room for truncation message
                    content = content[:limit - 100] + "\n\n[Response truncated for channel limit]"

                return {
                    "success": True,
                    "content": content,
                    "tool_uses": result.tool_uses,
                    "cost_usd": result.cost_usd,
                    "session_cost_usd": self._total_cost,
                    "message_count": self._message_count,
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": f"I encountered an error: {str(e)[:100]}",
            }

    @property
    def is_stale(self) -> bool:
        """Check if session is stale (no activity for 60+ minutes)."""
        from datetime import timedelta
        return datetime.now() - self._last_activity > timedelta(minutes=60)


# Store active sessions by user
_sessions: dict[str, SDKSession] = {}


def get_session(user_id: str) -> SDKSession:
    """
    Get or create an SDK session for a user.

    Args:
        user_id: User identifier

    Returns:
        SDKSession instance
    """
    # Clean up stale sessions periodically
    _cleanup_stale_sessions()

    if user_id not in _sessions:
        _sessions[user_id] = SDKSession(user_id)
    return _sessions[user_id]


def _cleanup_stale_sessions() -> None:
    """Remove stale sessions to free memory."""
    stale = [uid for uid, session in _sessions.items() if session.is_stale]
    for uid in stale:
        del _sessions[uid]


async def sdk_handler(message: UnifiedMessage, context: dict) -> dict[str, Any]:
    """
    Handle incoming messages using the SDK client.

    This is the main handler function registered with the router.

    Args:
        message: Inbound UnifiedMessage from a channel adapter
        context: Security and routing context from the security pipeline

    Returns:
        Dict with success status and processing results
    """
    # Get or create session for this user
    session = get_session(message.user_id)

    # Query the agent
    result = await session.query(message.content, message.channel)

    if not result.get("success"):
        # Log error
        _log_error(message, result.get("error", "unknown error"))

        # Send error response
        error_content = result.get(
            "content",
            "Sorry, I'm having trouble responding right now. Please try again."
        )
        response_content = error_content
    else:
        response_content = result.get("content", "I completed the task but have no text response.")

    # Create response message
    response = UnifiedMessage(
        id=str(uuid.uuid4()),
        channel=message.channel,
        channel_message_id=None,
        user_id=message.user_id,
        channel_user_id=message.channel_user_id,
        direction="outbound",
        content=response_content,
        content_type="text",
        attachments=[],
        reply_to=None,
        timestamp=datetime.now(),
        metadata={
            **message.metadata,
            "sdk_cost_usd": result.get("cost_usd", 0),
            "sdk_tool_uses": result.get("tool_uses", []),
        },
    )

    # Store outbound message in inbox
    try:
        from tools.channels import inbox
        inbox.store_message(response)
    except Exception:
        pass  # Don't fail if storage fails

    # Send response through router
    try:
        from tools.channels.router import get_router
        router = get_router()
        send_result = await router.route_outbound(response)
    except Exception as e:
        send_result = {"success": False, "error": str(e)}

    return {
        "success": True,
        "handler": "sdk_handler",
        "ai_response": result.get("success", False),
        "send_result": send_result,
        "cost_usd": result.get("cost_usd", 0),
        "tool_uses": len(result.get("tool_uses", [])),
    }


def _log_error(message: UnifiedMessage, error: str) -> None:
    """Log handler errors to audit."""
    try:
        from tools.security import audit

        audit.log_event(
            event_type="error",
            action="sdk_handler_error",
            user_id=message.user_id,
            channel=message.channel,
            details={
                "error": error[:500],
                "message_id": message.id,
            },
        )
    except Exception:
        pass


# =============================================================================
# Streaming Handler (for channels that support it)
# =============================================================================


async def sdk_handler_streaming(
    message: UnifiedMessage,
    context: dict,
    send_chunk: callable,
) -> dict[str, Any]:
    """
    Handle incoming messages with streaming responses.

    For channels that support progressive response display.

    Args:
        message: Inbound UnifiedMessage
        context: Security and routing context
        send_chunk: Async callable to send response chunks

    Returns:
        Dict with success status and processing results
    """
    try:
        from tools.agent.sdk_client import DexAIClient
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
    except ImportError:
        await send_chunk("Agent SDK not installed.")
        return {"success": False, "error": "SDK not installed"}

    session = get_session(message.user_id)

    try:
        async with DexAIClient(
            user_id=message.user_id,
            working_dir=session.working_dir
        ) as client:
            await client._client.query(message.content)

            full_response = []
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            await send_chunk(block.text)
                            full_response.append(block.text)
                elif isinstance(msg, ResultMessage):
                    break

            return {
                "success": True,
                "handler": "sdk_handler_streaming",
                "response_length": sum(len(p) for p in full_response),
            }

    except Exception as e:
        await send_chunk(f"Error: {str(e)[:100]}")
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing the SDK handler."""
    import argparse

    parser = argparse.ArgumentParser(description="SDK Handler Test")
    parser.add_argument("--user", default="test_user", help="User ID")
    parser.add_argument("--message", help="Message to send")
    parser.add_argument("--channel", default="cli", help="Channel name")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    async def run_test():
        if args.interactive:
            print("SDK Handler Interactive Test")
            print("-" * 40)
            print(f"User: {args.user}, Channel: {args.channel}")
            print("Type 'exit' to quit\n")

            while True:
                try:
                    user_input = input("You: ").strip()
                    if user_input.lower() in ("exit", "quit", "q"):
                        break
                    if not user_input:
                        continue

                    # Create test message
                    test_message = UnifiedMessage(
                        id=str(uuid.uuid4()),
                        channel=args.channel,
                        channel_message_id="test",
                        user_id=args.user,
                        channel_user_id=args.user,
                        direction="inbound",
                        content=user_input,
                        content_type="text",
                        attachments=[],
                        reply_to=None,
                        timestamp=datetime.now(),
                        metadata={},
                    )

                    # Process through handler
                    result = await sdk_handler(test_message, {})
                    print(f"\nDex: {result}")
                    print()

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"Error: {e}")

        elif args.message:
            test_message = UnifiedMessage(
                id=str(uuid.uuid4()),
                channel=args.channel,
                channel_message_id="test",
                user_id=args.user,
                channel_user_id=args.user,
                direction="inbound",
                content=args.message,
                content_type="text",
                attachments=[],
                reply_to=None,
                timestamp=datetime.now(),
                metadata={},
            )

            result = await sdk_handler(test_message, {})
            print(result)

        else:
            parser.print_help()

    asyncio.run(run_test())


if __name__ == "__main__":
    main()
