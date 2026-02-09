"""
SDK Handler for Channel Messages

Handles messages from channel adapters using the DexAI SDK client.
Uses SessionManager for ClaudeSDKClient-based continuous conversations.

Features:
- Uses SessionManager for SDK session resumption
- Uses DexAIClient wrapper for ADHD-aware responses
- Integrates with router's security pipeline
- Stores messages in unified inbox
- Handles streaming responses
- Properly truncates for channel limits
- Intelligent model routing with complexity hints
- AskUserQuestion handling for ADHD-friendly clarification

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
from typing import Any, Callable, Optional, TYPE_CHECKING

# Ensure project root is in path
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.channels.models import UnifiedMessage
from tools.channels.session_manager import get_session_manager, SessionManager

if TYPE_CHECKING:
    from tools.agent.model_router import TaskComplexity

logger = logging.getLogger(__name__)


# =============================================================================
# AskUserQuestion Handler
# =============================================================================

# Global storage for pending question responses
_pending_questions: dict[str, asyncio.Future] = {}


def create_ask_user_handler(
    message: UnifiedMessage,
    timeout: float = 300.0,
) -> Callable:
    """
    Create an AskUserQuestion handler for a specific message context.

    The handler sends formatted questions to the user through the channel
    and waits for their response.

    Args:
        message: The original inbound message (for channel/user context)
        timeout: Maximum seconds to wait for user response (default: 5 min)

    Returns:
        Async callable that handles AskUserQuestion tool invocation
    """

    async def ask_user_handler(
        formatted_questions: list[dict],
        user_id: str,
        channel: str,
    ) -> dict[str, Any]:
        """
        Handle AskUserQuestion by sending to channel and collecting response.

        Args:
            formatted_questions: ADHD-formatted questions from permissions.py
            user_id: User ID to send to
            channel: Channel to use

        Returns:
            Dict mapping question numbers to user answers
        """
        # Format questions for display
        question_text = _format_questions_for_display(formatted_questions)

        # Create unique key for this question session
        question_key = f"{user_id}:{channel}:{uuid.uuid4().hex[:8]}"

        # Create future to wait for response
        response_future: asyncio.Future = asyncio.get_event_loop().create_future()
        _pending_questions[question_key] = response_future

        try:
            # Send questions through the channel
            question_message = UnifiedMessage(
                id=str(uuid.uuid4()),
                channel=channel,
                channel_message_id=None,
                user_id=user_id,
                channel_user_id=message.channel_user_id,
                direction="outbound",
                content=question_text,
                content_type="text",
                attachments=[],
                reply_to=message.id,
                timestamp=datetime.now(),
                metadata={
                    "type": "ask_user_question",
                    "question_key": question_key,
                    "question_count": len(formatted_questions),
                },
            )

            # Route the question message
            try:
                from tools.channels.router import get_router
                router = get_router()
                await router.route_outbound(question_message)
            except Exception as e:
                logger.warning(f"Failed to send question: {e}")
                # Return empty answers on send failure
                return {}

            # Wait for user response with timeout
            try:
                answers = await asyncio.wait_for(response_future, timeout=timeout)
                return answers
            except asyncio.TimeoutError:
                logger.info(f"Question timeout for {user_id}")
                return {}  # Return empty on timeout

        finally:
            # Clean up pending question
            _pending_questions.pop(question_key, None)

    return ask_user_handler


def submit_question_response(
    user_id: str,
    channel: str,
    response_content: str,
) -> bool:
    """
    Submit a user's response to a pending question.

    Called by channel adapters when they detect a response to a question.

    Args:
        user_id: User who responded
        channel: Channel of response
        response_content: The user's response text

    Returns:
        True if response was matched to a pending question
    """
    # Find matching pending question
    prefix = f"{user_id}:{channel}:"
    for key, future in list(_pending_questions.items()):
        if key.startswith(prefix) and not future.done():
            # Parse response into answers dict
            answers = _parse_user_response(response_content)
            future.set_result(answers)
            return True

    return False


def has_pending_question(user_id: str, channel: str) -> bool:
    """Check if user has a pending question awaiting response."""
    prefix = f"{user_id}:{channel}:"
    return any(
        key.startswith(prefix) and not future.done()
        for key, future in _pending_questions.items()
    )


def _format_questions_for_display(formatted_questions: list[dict]) -> str:
    """
    Format questions for channel display.

    Creates ADHD-friendly text output:
    - Clear numbering
    - Brief options
    - Simple instructions

    Args:
        formatted_questions: Questions from permissions.py formatting

    Returns:
        Formatted string for display
    """
    lines = ["I need some clarification:\n"]

    for q in formatted_questions:
        num = q.get("number", 1)
        header = q.get("header", "")
        question = q.get("question", "")
        options = q.get("options", [])
        multi = q.get("multi_select", False)

        # Add question header
        if header:
            lines.append(f"**{header}**")
        lines.append(f"{num}. {question}")

        # Add options
        for opt in options:
            opt_num = opt.get("number", "")
            label = opt.get("label", "")
            desc = opt.get("description", "")

            if desc:
                lines.append(f"   {opt_num}) {label} - {desc}")
            else:
                lines.append(f"   {opt_num}) {label}")

        if multi:
            lines.append("   (You can select multiple)")
        lines.append("")

    lines.append("Reply with the number(s) of your choice, or type your own answer.")

    return "\n".join(lines)


def _parse_user_response(response: str) -> dict[str, Any]:
    """
    Parse user's response to extract answers.

    Handles:
    - Numeric selections ("1", "2,3", "1 and 3")
    - Text responses
    - Mixed responses

    Args:
        response: Raw user response text

    Returns:
        Dict with parsed answers (question_num -> answer)
    """
    response = response.strip()
    answers = {}

    # Try to extract numbers
    numbers = re.findall(r'\d+', response)

    if numbers:
        # User selected numbered options
        answers["selections"] = [int(n) for n in numbers]
        answers["raw"] = response
    else:
        # Free-text response
        answers["text"] = response
        answers["raw"] = response

    return answers


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


# =============================================================================
# Legacy SDKSession class removed in Phase 2 SDK alignment.
# Session management now handled by tools.channels.session_manager.SessionManager
# which provides ClaudeSDKClient-based continuous conversations.
# =============================================================================


async def sdk_handler(message: UnifiedMessage, context: dict) -> dict[str, Any]:
    """
    Handle incoming messages using the SDK client.

    This is the main handler function registered with the router.
    Uses SessionManager for continuous conversations with SDK session resumption.

    Args:
        message: Inbound UnifiedMessage from a channel adapter
        context: Security and routing context from the security pipeline

    Returns:
        Dict with success status and processing results
    """
    # Get session manager
    manager = get_session_manager()

    # Create AskUserQuestion handler for this message context
    ask_handler = create_ask_user_handler(message)

    # Handle message through session manager
    result = await manager.handle_message(
        user_id=message.user_id,
        channel=message.channel,
        content=message.content,
        context=context,
        ask_user_handler=ask_handler,
    )

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
        response_content = result.get("content") or "Sorry, I'm having trouble responding right now. Please try again."
    else:
        response_content = result.get("content") or "I completed the task but have no text response."

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
    Uses SessionManager for continuous conversation context.

    Args:
        message: Inbound UnifiedMessage
        context: Security and routing context
        send_chunk: Async callable to send response chunks

    Returns:
        Dict with success status and processing results
    """
    try:
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
    except ImportError:
        await send_chunk("Agent SDK not installed.")
        return {"success": False, "error": "SDK not installed"}

    # Get session manager
    manager = get_session_manager()

    # Create AskUserQuestion handler for this message context
    ask_handler = create_ask_user_handler(message)

    try:
        full_response = []
        async for msg in manager.stream_message(
            user_id=message.user_id,
            channel=message.channel,
            content=message.content,
            ask_user_handler=ask_handler,
        ):
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
# Channel-Specific Streaming Handlers
# =============================================================================

# Update interval for streaming messages (milliseconds)
STREAM_UPDATE_INTERVAL_MS = 500

# Typing cursor for streaming display
TYPING_CURSOR = "▌"


async def sdk_handler_slack_streaming(
    message: UnifiedMessage,
    context: dict,
) -> dict[str, Any]:
    """
    Handle Slack messages with streaming responses via message editing.

    Sends an initial "Thinking..." message, then progressively updates
    it with the streaming response. Updates every 500ms with a typing cursor.

    Args:
        message: Inbound UnifiedMessage from Slack
        context: Security and routing context

    Returns:
        Dict with success status and processing results
    """
    try:
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
    except ImportError:
        return {"success": False, "error": "SDK not installed"}

    # Get the Slack adapter from router
    from tools.channels.router import get_router
    router = get_router()
    adapter = router.adapters.get("slack")

    if not adapter:
        return {"success": False, "error": "Slack adapter not available"}

    # Get channel info from message metadata
    channel_id = message.metadata.get("slack_channel_id")
    thread_ts = message.metadata.get("slack_thread_ts")

    if not channel_id:
        channel_id = message.channel_user_id

    if not channel_id:
        return {"success": False, "error": "No channel ID for Slack message"}

    # Send initial "Thinking..." message
    initial_message = UnifiedMessage(
        id=str(uuid.uuid4()),
        channel="slack",
        channel_message_id=None,
        user_id=message.user_id,
        channel_user_id=message.channel_user_id,
        direction="outbound",
        content=f"Thinking...{TYPING_CURSOR}",
        content_type="text",
        attachments=[],
        reply_to=message.id,
        timestamp=datetime.now(),
        metadata={
            "slack_channel_id": channel_id,
            "slack_thread_ts": thread_ts,
        },
    )

    send_result = await adapter.send_message(initial_message)

    if not send_result.get("success"):
        # Fall back to non-streaming handler
        return await sdk_handler(message, context)

    message_ts = send_result.get("message_id")
    response_channel = send_result.get("channel_id", channel_id)

    # Get session manager and stream response
    manager = get_session_manager()
    ask_handler = create_ask_user_handler(message)

    accumulated_text = ""
    last_update_time = asyncio.get_event_loop().time()

    try:
        async for msg in manager.stream_message(
            user_id=message.user_id,
            channel=message.channel,
            content=message.content,
            ask_user_handler=ask_handler,
        ):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        accumulated_text += block.text

                        # Update message every 500ms
                        current_time = asyncio.get_event_loop().time()
                        if (current_time - last_update_time) * 1000 >= STREAM_UPDATE_INTERVAL_MS:
                            await adapter.update_message(
                                channel_id=response_channel,
                                message_ts=message_ts,
                                content=accumulated_text + TYPING_CURSOR,
                            )
                            last_update_time = current_time

            elif isinstance(msg, ResultMessage):
                break

        # Final update - remove typing cursor
        if accumulated_text:
            await adapter.update_message(
                channel_id=response_channel,
                message_ts=message_ts,
                content=accumulated_text,
            )
        else:
            # No response text - update with error message
            await adapter.update_message(
                channel_id=response_channel,
                message_ts=message_ts,
                content="I completed the task but have no text response.",
            )

        # Log success to dashboard
        _log_to_dashboard(
            event_type="task",
            summary=f"Slack streaming response ({len(accumulated_text)} chars)",
            channel="slack",
            user_id=message.user_id,
            details={
                "message_id": message.id,
                "response_length": len(accumulated_text),
                "streaming": True,
            },
            severity="info",
        )

        return {
            "success": True,
            "handler": "sdk_handler_slack_streaming",
            "response_length": len(accumulated_text),
            "streaming": True,
        }

    except Exception as e:
        logger.error(f"Slack streaming error: {e}")
        # Try to update message with error
        try:
            error_msg = accumulated_text or f"Error: {str(e)[:100]}"
            await adapter.update_message(
                channel_id=response_channel,
                message_ts=message_ts,
                content=error_msg,
            )
        except Exception:
            pass

        return {"success": False, "error": str(e)}


async def sdk_handler_discord_streaming(
    message: UnifiedMessage,
    context: dict,
) -> dict[str, Any]:
    """
    Handle Discord messages with streaming responses via message editing.

    Sends an initial "Thinking..." message, then progressively updates
    it with the streaming response. Updates every 500ms with a typing cursor.
    Respects Discord's 2000 character limit.

    Args:
        message: Inbound UnifiedMessage from Discord
        context: Security and routing context

    Returns:
        Dict with success status and processing results
    """
    try:
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
    except ImportError:
        return {"success": False, "error": "SDK not installed"}

    # Get the Discord adapter from router
    from tools.channels.router import get_router
    router = get_router()
    adapter = router.adapters.get("discord")

    if not adapter:
        return {"success": False, "error": "Discord adapter not available"}

    # Send initial "Thinking..." message
    initial_message = UnifiedMessage(
        id=str(uuid.uuid4()),
        channel="discord",
        channel_message_id=None,
        user_id=message.user_id,
        channel_user_id=message.channel_user_id,
        direction="outbound",
        content=f"Thinking...{TYPING_CURSOR}",
        content_type="text",
        attachments=[],
        reply_to=message.id,
        timestamp=datetime.now(),
        metadata=message.metadata,
    )

    send_result = await adapter.send_message(initial_message)

    if not send_result.get("success"):
        # Fall back to non-streaming handler
        return await sdk_handler(message, context)

    message_obj = send_result.get("message_obj")

    if not message_obj:
        # No message object returned, fall back to non-streaming
        return await sdk_handler(message, context)

    # Get session manager and stream response
    manager = get_session_manager()
    ask_handler = create_ask_user_handler(message)

    accumulated_text = ""
    last_update_time = asyncio.get_event_loop().time()

    try:
        async for msg in manager.stream_message(
            user_id=message.user_id,
            channel=message.channel,
            content=message.content,
            ask_user_handler=ask_handler,
        ):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        accumulated_text += block.text

                        # Update message every 500ms (respect 2000 char limit)
                        current_time = asyncio.get_event_loop().time()
                        if (current_time - last_update_time) * 1000 >= STREAM_UPDATE_INTERVAL_MS:
                            display_text = accumulated_text[:1997] + TYPING_CURSOR
                            await adapter.update_message(
                                message_obj=message_obj,
                                content=display_text,
                            )
                            last_update_time = current_time

            elif isinstance(msg, ResultMessage):
                break

        # Final update - remove typing cursor (respect 2000 char limit)
        if accumulated_text:
            final_text = accumulated_text[:2000]
            await adapter.update_message(
                message_obj=message_obj,
                content=final_text,
            )
        else:
            await adapter.update_message(
                message_obj=message_obj,
                content="I completed the task but have no text response.",
            )

        # Log success to dashboard
        _log_to_dashboard(
            event_type="task",
            summary=f"Discord streaming response ({len(accumulated_text)} chars)",
            channel="discord",
            user_id=message.user_id,
            details={
                "message_id": message.id,
                "response_length": len(accumulated_text),
                "streaming": True,
                "truncated": len(accumulated_text) > 2000,
            },
            severity="info",
        )

        return {
            "success": True,
            "handler": "sdk_handler_discord_streaming",
            "response_length": len(accumulated_text),
            "streaming": True,
            "truncated": len(accumulated_text) > 2000,
        }

    except Exception as e:
        logger.error(f"Discord streaming error: {e}")
        # Try to update message with error
        try:
            error_msg = accumulated_text[:2000] if accumulated_text else f"Error: {str(e)[:100]}"
            await adapter.update_message(
                message_obj=message_obj,
                content=error_msg,
            )
        except Exception:
            pass

        return {"success": False, "error": str(e)}


async def sdk_handler_telegram_fallback(
    message: UnifiedMessage,
    context: dict,
) -> dict[str, Any]:
    """
    Handle Telegram messages with a quick acknowledgment followed by full response.

    Telegram doesn't support message editing for streaming in the same way as
    Slack/Discord, so we send a quick acknowledgment and then the full response.

    Args:
        message: Inbound UnifiedMessage from Telegram
        context: Security and routing context

    Returns:
        Dict with success status and processing results
    """
    # Get the Telegram adapter from router
    from tools.channels.router import get_router
    router = get_router()
    adapter = router.adapters.get("telegram")

    if not adapter:
        return {"success": False, "error": "Telegram adapter not available"}

    # Send quick acknowledgment
    ack_message = UnifiedMessage(
        id=str(uuid.uuid4()),
        channel="telegram",
        channel_message_id=None,
        user_id=message.user_id,
        channel_user_id=message.channel_user_id,
        direction="outbound",
        content="Working on your request...",
        content_type="text",
        attachments=[],
        reply_to=message.channel_message_id,
        timestamp=datetime.now(),
        metadata=message.metadata,
    )

    await adapter.send_message(ack_message)

    # Now process with the standard handler (which sends the full response)
    return await sdk_handler(message, context)


# =============================================================================
# Channel-Aware Handler Dispatcher
# =============================================================================


async def sdk_handler_with_streaming(
    message: UnifiedMessage,
    context: dict,
) -> dict[str, Any]:
    """
    Smart handler that routes to channel-specific streaming implementations.

    - Slack: Uses message editing for progressive display
    - Discord: Uses message editing for progressive display (2000 char limit)
    - Telegram: Sends acknowledgment, then full response
    - Other channels: Uses standard non-streaming handler

    Args:
        message: Inbound UnifiedMessage
        context: Security and routing context

    Returns:
        Dict with success status and processing results
    """
    channel = message.channel

    if channel == "slack":
        return await sdk_handler_slack_streaming(message, context)
    elif channel == "discord":
        return await sdk_handler_discord_streaming(message, context)
    elif channel == "telegram":
        return await sdk_handler_telegram_fallback(message, context)
    else:
        # Default to standard non-streaming handler
        return await sdk_handler(message, context)


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
    parser.add_argument("--session", default="main",
                        choices=["main", "subagent", "heartbeat", "cron"],
                        help="Session type")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    async def run_test():
        if args.interactive:
            print("SDK Handler Interactive Test")
            print("-" * 40)
            print(f"User: {args.user}, Channel: {args.channel}, Session: {args.session}")
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
