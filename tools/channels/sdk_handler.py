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
- Intelligent model routing with complexity hints

Usage:
    from tools.channels.sdk_handler import sdk_handler
    router.add_message_handler(sdk_handler)
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Ensure project root is in path
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.channels.models import UnifiedMessage

if TYPE_CHECKING:
    from tools.agent.model_router import TaskComplexity

logger = logging.getLogger(__name__)


def _log_to_dashboard(
    event_type: str,
    summary: str,
    channel: str = None,
    user_id: str = None,
    details: dict = None,
    severity: str = "info",
) -> None:
    """Log event to dashboard database. Fails silently."""
    try:
        from tools.dashboard.backend.database import log_event

        log_event(event_type, summary, channel, user_id, details, severity)
    except Exception:
        pass


def _record_dashboard_metric(
    metric_name: str,
    metric_value: float,
    labels: dict = None,
) -> None:
    """Record metric to dashboard database. Fails silently."""
    try:
        from tools.dashboard.backend.database import record_metric

        record_metric(metric_name, metric_value, labels)
    except Exception:
        pass


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
        Send a query to Claude, trying Agent SDK first then falling back to direct API.

        The Agent SDK provides full agentic capabilities (tools, file access, etc.)
        but requires a native Linux environment. If it fails (e.g., Bun crash on WSL2),
        we fall back to the direct Anthropic API for basic chat.

        Args:
            message: User's message content
            channel: Channel name for response formatting

        Returns:
            Dict with response content and metadata
        """
        self._last_activity = datetime.now()
        self._message_count += 1

        # Try Agent SDK first (full capabilities, works in Docker/native Linux)
        result = await self._query_with_agent_sdk(message, channel)
        if result.get("success"):
            return result

        # Check if it was a Bun/SDK crash (not just a normal error)
        error = result.get("error", "")
        is_sdk_crash = any(x in error.lower() for x in [
            "segmentation fault", "process exited", "bun has crashed",
            "subprocess", "exited with code"
        ])

        if is_sdk_crash:
            # Fall back to direct API (basic chat, works everywhere)
            _log_to_dashboard(
                event_type="system",
                summary="Agent SDK crashed, falling back to direct API",
                channel=channel,
                user_id=self.user_id,
                details={"original_error": error[:200]},
                severity="warning",
            )
            return await self._query_with_direct_api(message, channel)

        # Return the original error if it wasn't an SDK crash
        return result

    def _infer_complexity(self, message: str) -> "TaskComplexity | None":
        """
        Infer complexity from message content for routing hints.

        Returns explicit complexity hint for clear-cut cases, None to let router decide.
        """
        try:
            from tools.agent.model_router import TaskComplexity
        except ImportError:
            return None

        message_lower = message.lower().strip()

        # TRIVIAL: Simple greetings, acknowledgments, single-word responses
        trivial_patterns = [
            r'^(hi|hey|hello|yo|sup)[\s!.?]*$',
            r'^(thanks|thank you|thx|ty)[\s!.?]*$',
            r'^(ok|okay|k|got it|sure|yep|yes|no|nope)[\s!.?]*$',
            r'^(bye|goodbye|later|cya)[\s!.?]*$',
            r'^(good morning|good night|gn|gm)[\s!.?]*$',
            r'^what time is it[\s?]*$',
            r'^how are you[\s?]*$',
        ]

        for pattern in trivial_patterns:
            if re.match(pattern, message_lower):
                return TaskComplexity.TRIVIAL

        # HIGH: Explicit multi-step, analysis, or complex task indicators
        high_indicators = [
            "step by step",
            "walk me through",
            "analyze",
            "analyse",
            "compare",
            "evaluate",
            "design",
            "architect",
            "implement",
            "refactor",
            "debug",
            "fix the",
            "build a",
            "create a system",
        ]

        for indicator in high_indicators:
            if indicator in message_lower:
                return TaskComplexity.HIGH

        # CRITICAL: Very complex or sensitive operations
        critical_indicators = [
            "production",
            "deploy to",
            "migration",
            "security audit",
            "comprehensive review",
        ]

        for indicator in critical_indicators:
            if indicator in message_lower:
                return TaskComplexity.CRITICAL

        # Let the router's heuristics decide for everything else
        return None

    async def _query_with_agent_sdk(self, message: str, channel: str) -> dict[str, Any]:
        """Query using the full Agent SDK (tools, file access, etc.)."""
        try:
            from tools.agent.sdk_client import DexAIClient
        except ImportError:
            return {
                "success": False,
                "error": "Agent SDK not installed",
                "content": "",
            }

        # Infer complexity for routing
        explicit_complexity = self._infer_complexity(message)

        try:
            async with DexAIClient(
                user_id=self.user_id,
                working_dir=self.working_dir,
                explicit_complexity=explicit_complexity,
            ) as client:
                result = await client.query(message)

                self._total_cost += result.cost_usd

                # Get channel message limit
                limit = CHANNEL_MESSAGE_LIMITS.get(channel, DEFAULT_MESSAGE_LIMIT)

                # Truncate if needed
                content = result.text
                if len(content) > limit - 100:
                    content = content[:limit - 100] + "\n\n[Response truncated]"

                return {
                    "success": True,
                    "content": content,
                    "tool_uses": result.tool_uses,
                    "cost_usd": result.cost_usd,
                    "session_cost_usd": self._total_cost,
                    "message_count": self._message_count,
                    "mode": "agent_sdk",
                    "model": result.model,
                    "complexity": result.complexity,
                    "routing_reasoning": result.routing_reasoning,
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": "",
            }

    async def _query_with_direct_api(self, message: str, channel: str) -> dict[str, Any]:
        """Query using direct Anthropic API (basic chat, no tools)."""
        try:
            import anthropic
        except ImportError:
            return {
                "success": False,
                "error": "anthropic not installed",
                "content": "Anthropic SDK not installed. Please run: uv add anthropic",
            }

        try:
            client = anthropic.Anthropic()

            # Get current date/time for context
            now = datetime.now()
            date_str = now.strftime("%A, %B %d, %Y")
            time_str = now.strftime("%I:%M %p")

            # Build system prompt
            system_prompt = f"""You are Dex, a helpful AI assistant designed for users with ADHD.

CURRENT DATE AND TIME: {date_str} at {time_str}

CORE PRINCIPLES:
1. ONE THING AT A TIME - Never present lists of options when one clear action will do
2. BREVITY FIRST - Keep responses short for chat. Details only when asked.
3. FORWARD-FACING - Focus on what to do, not what wasn't done
4. NO GUILT LANGUAGE - Avoid "you should have", "overdue", "forgot to"
5. PRE-SOLVE FRICTION - Identify blockers and solve them proactively

COMMUNICATION STYLE:
- Be direct and helpful, not enthusiastic or overly positive
- Use short sentences and paragraphs
- If breaking down tasks, present ONE step at a time
- Ask clarifying questions rather than making assumptions

NOTE: Running in fallback mode - file access and tool use unavailable."""

            # Add conversation history if available
            messages = self._conversation_history.copy() if hasattr(self, '_conversation_history') else []
            messages.append({"role": "user", "content": message})

            # Call Claude API
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
            )

            # Extract response text
            content = response.content[0].text if response.content else ""

            # Calculate approximate cost
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost_usd = (input_tokens * 3 + output_tokens * 15) / 1_000_000

            self._total_cost += cost_usd

            # Store in conversation history for context
            if not hasattr(self, '_conversation_history'):
                self._conversation_history = []
            self._conversation_history.append({"role": "user", "content": message})
            self._conversation_history.append({"role": "assistant", "content": content})

            # Keep history manageable (last 10 turns)
            if len(self._conversation_history) > 20:
                self._conversation_history = self._conversation_history[-20:]

            # Get channel message limit
            limit = CHANNEL_MESSAGE_LIMITS.get(channel, DEFAULT_MESSAGE_LIMIT)

            # Truncate if needed
            if len(content) > limit - 100:
                content = content[:limit - 100] + "\n\n[Response truncated]"

            return {
                "success": True,
                "content": content,
                "tool_uses": [],
                "cost_usd": cost_usd,
                "session_cost_usd": self._total_cost,
                "message_count": self._message_count,
                "mode": "direct_api",
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

        # Log to dashboard
        _log_to_dashboard(
            event_type="system",
            summary=f"SDK query failed: {result.get('error', 'unknown')[:50]}",
            channel=message.channel,
            user_id=message.user_id,
            details={
                "error": result.get("error"),
                "message_id": message.id,
            },
            severity="error",
        )

        # Send error response
        error_content = result.get(
            "content",
            "Sorry, I'm having trouble responding right now. Please try again."
        )
        response_content = error_content
    else:
        response_content = result.get("content", "I completed the task but have no text response.")

        # Log successful LLM response to dashboard
        _log_to_dashboard(
            event_type="task",
            summary=f"AI response generated ({len(response_content)} chars)",
            channel=message.channel,
            user_id=message.user_id,
            details={
                "message_id": message.id,
                "response_length": len(response_content),
                "tool_uses": len(result.get("tool_uses", [])),
                "cost_usd": result.get("cost_usd", 0),
            },
            severity="info",
        )

        # Record cost metric
        cost_usd = result.get("cost_usd", 0)
        if cost_usd > 0:
            _record_dashboard_metric(
                metric_name="api_cost_usd",
                metric_value=cost_usd,
                labels={"channel": message.channel, "user_id": message.user_id},
            )

        # Record response time (approximate from tool uses)
        _record_dashboard_metric(
            metric_name="llm_response_count",
            metric_value=1,
            labels={"channel": message.channel},
        )

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
