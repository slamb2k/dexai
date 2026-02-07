"""
DexAI SDK Hooks

Lifecycle hooks for Claude Agent SDK integration.

Hooks provide pre/post tool execution callbacks and session lifecycle events.
DexAI uses these for:
- Context saving on session stop (ADHD-critical for resumption)
- Audit logging of tool usage
- Security checks as defense-in-depth

Usage:
    from tools.agent.hooks import create_hooks

    hooks = create_hooks(user_id="alice", channel="telegram")
    options = ClaudeAgentOptions(hooks=hooks, ...)
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)


# =============================================================================
# Stop Hook - Context Saving
# =============================================================================


async def save_context_on_stop(
    user_id: str,
    channel: str,
    session_data: dict | None = None,
) -> dict[str, Any]:
    """
    Save context when session stops.

    ADHD-critical: Context switching costs 20-45 minutes to re-orient.
    This captures where the user was so they can pick up instantly.

    Args:
        user_id: User whose context to save
        channel: Communication channel
        session_data: Optional session data from SDK

    Returns:
        Dict with success status
    """
    try:
        # Try to use the async context capture
        try:
            from tools.memory.service import MemoryService

            service = MemoryService()
            await service.initialize()

            # Build state from session data
            state = {
                "channel": channel,
                "session_end_time": datetime.now().isoformat(),
                "session_data": session_data,
            }

            # Extract meaningful context if available
            if session_data:
                state["last_message"] = session_data.get("last_message", "")
                state["tool_count"] = session_data.get("tool_count", 0)

            snapshot_id = await service.capture_context(
                user_id=user_id,
                state=state,
                trigger="timeout",  # Session end is like a timeout
                summary="Session ended - context saved for resumption",
            )

            logger.info(f"Context saved on stop for user {user_id}: {snapshot_id}")
            return {
                "success": True,
                "snapshot_id": snapshot_id,
                "message": "Context saved for resumption",
            }

        except ImportError:
            # Fallback to legacy context capture
            from tools.memory import context_capture

            result = context_capture.capture_context(
                user_id=user_id,
                trigger="timeout",
                channel=channel,
                metadata=session_data,
                summary="Session ended - context saved for resumption",
            )

            if result.get("success"):
                logger.info(f"Context saved on stop for user {user_id}")
            return result

    except Exception as e:
        logger.warning(f"Failed to save context on stop: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def create_stop_hook(
    user_id: str,
    channel: str,
) -> Callable[[dict], dict]:
    """
    Create a Stop hook callback for the SDK.

    The Stop hook is called when the session ends, allowing us to
    save context for later resumption.

    Args:
        user_id: User identifier
        channel: Communication channel

    Returns:
        Hook callback function
    """

    def stop_hook(input_data: dict) -> dict:
        """
        Stop hook callback.

        Args:
            input_data: Hook input data from SDK

        Returns:
            Hook output (empty dict to proceed)
        """
        # Extract session data if available
        session_data = {
            "hook_type": "Stop",
            "timestamp": datetime.now().isoformat(),
        }

        # Merge any data from input
        if input_data:
            session_data.update(input_data)

        # Run async save in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule for later execution
                asyncio.create_task(
                    save_context_on_stop(user_id, channel, session_data)
                )
            else:
                loop.run_until_complete(
                    save_context_on_stop(user_id, channel, session_data)
                )
        except RuntimeError:
            # No event loop - create one
            asyncio.run(save_context_on_stop(user_id, channel, session_data))

        # Return empty dict to allow session to stop normally
        return {}

    return stop_hook


# =============================================================================
# PreToolUse Hook - Audit Logging
# =============================================================================


def create_audit_hook(
    user_id: str,
) -> Callable[[dict, str, Any], dict]:
    """
    Create a PreToolUse audit hook.

    Logs all tool usage for security audit trail.

    Args:
        user_id: User identifier

    Returns:
        Hook callback function
    """

    def audit_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        """
        Audit hook callback for PreToolUse.

        Args:
            input_data: Tool input data
            tool_use_id: Unique tool use identifier
            context: SDK context

        Returns:
            Empty dict to proceed
        """
        try:
            from tools.security import audit

            tool_name = input_data.get("tool_name", "unknown")
            tool_input = input_data.get("tool_input", {})

            # Sanitize sensitive data before logging
            safe_input = _sanitize_for_logging(tool_input)

            audit.log_event(
                event_type="tool_use",
                action=tool_name,
                user_id=user_id,
                status="attempted",
                details={
                    "tool_use_id": tool_use_id,
                    "tool_input": safe_input,
                    "hook": "PreToolUse",
                },
            )
        except Exception as e:
            logger.debug(f"Audit hook error: {e}")

        # Always return empty to proceed
        return {}

    return audit_hook


def _sanitize_for_logging(tool_input: dict) -> dict:
    """Remove sensitive information from tool input for logging."""
    if not isinstance(tool_input, dict):
        return {"raw": str(tool_input)[:200]}

    sanitized = {}
    sensitive_keys = {"password", "secret", "token", "key", "credential", "api_key"}

    for key, value in tool_input.items():
        lower_key = key.lower()

        if any(s in lower_key for s in sensitive_keys):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str) and len(value) > 500:
            sanitized[key] = value[:200] + "...[truncated]"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_for_logging(value)
        else:
            sanitized[key] = value

    return sanitized


# =============================================================================
# PostToolUse Hook - Dashboard Recording
# =============================================================================


def create_dashboard_hook() -> Callable[[dict, str, Any], dict]:
    """
    Create a PostToolUse hook for dashboard recording.

    Records tool results to the dashboard for analytics.

    Returns:
        Hook callback function
    """

    def dashboard_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        """
        Dashboard hook callback for PostToolUse.

        Args:
            input_data: Tool result data
            tool_use_id: Unique tool use identifier
            context: SDK context

        Returns:
            Empty dict to proceed
        """
        try:
            from tools.dashboard.backend.database import record_tool_use

            tool_name = input_data.get("tool_name", "unknown")
            success = input_data.get("success", True)

            record_tool_use(
                tool_name=tool_name,
                tool_use_id=tool_use_id,
                success=success,
            )
        except ImportError:
            pass  # Dashboard not available
        except Exception as e:
            logger.debug(f"Dashboard hook error: {e}")

        return {}

    return dashboard_hook


# =============================================================================
# Hook Configuration Builder
# =============================================================================


def create_hooks(
    user_id: str,
    channel: str = "direct",
    enable_audit: bool = True,
    enable_dashboard: bool = True,
    enable_context_save: bool = True,
) -> dict[str, list]:
    """
    Create the hooks configuration for SDK.

    This builds the hooks dict that can be passed to ClaudeAgentOptions.

    Args:
        user_id: User identifier
        channel: Communication channel
        enable_audit: Enable PreToolUse audit logging
        enable_dashboard: Enable PostToolUse dashboard recording
        enable_context_save: Enable Stop context saving

    Returns:
        Hooks configuration dict for SDK
    """
    hooks = {}

    # PreToolUse hooks
    pre_hooks = []
    if enable_audit:
        pre_hooks.append({
            "hooks": [create_audit_hook(user_id)],
        })

    if pre_hooks:
        hooks["PreToolUse"] = pre_hooks

    # PostToolUse hooks
    post_hooks = []
    if enable_dashboard:
        post_hooks.append({
            "hooks": [create_dashboard_hook()],
        })

    if post_hooks:
        hooks["PostToolUse"] = post_hooks

    # Stop hooks
    stop_hooks = []
    if enable_context_save:
        stop_hooks.append({
            "hooks": [create_stop_hook(user_id, channel)],
        })

    if stop_hooks:
        hooks["Stop"] = stop_hooks

    return hooks


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing hooks."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="DexAI SDK Hooks")
    parser.add_argument("--user", default="test_user", help="User ID")
    parser.add_argument("--channel", default="cli", help="Channel")
    parser.add_argument("--test-stop", action="store_true", help="Test stop hook")
    parser.add_argument("--show-config", action="store_true", help="Show hooks config")

    args = parser.parse_args()

    if args.show_config:
        hooks = create_hooks(args.user, args.channel)
        print("Hooks configuration:")
        for hook_type, hook_list in hooks.items():
            print(f"\n{hook_type}:")
            for i, h in enumerate(hook_list):
                print(f"  Hook {i + 1}: {len(h.get('hooks', []))} callbacks")

    if args.test_stop:
        print(f"Testing stop hook for user {args.user}...")
        stop_hook = create_stop_hook(args.user, args.channel)
        result = stop_hook({"test": True})
        print(f"Result: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    main()
