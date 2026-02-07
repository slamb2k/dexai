"""
DexAI SDK Hooks

Lifecycle hooks for Claude Agent SDK integration.

Hooks provide pre/post tool execution callbacks and session lifecycle events.
DexAI uses these for:
- Security checks via PreToolUse (defense-in-depth)
- Context saving on session stop (ADHD-critical for resumption)
- Audit logging of tool usage
- Dashboard recording for analytics

Usage:
    from tools.agent.hooks import create_hooks

    hooks = create_hooks(user_id="alice", channel="telegram")
    options = ClaudeAgentOptions(hooks=hooks, ...)
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)


# =============================================================================
# Dangerous Command Patterns (for security hooks)
# =============================================================================

# Patterns that should ALWAYS be blocked
DANGEROUS_BASH_PATTERNS = [
    # Destructive filesystem operations
    r"rm\s+(-rf?|--recursive)\s+[/~]",  # rm -rf / or ~
    r"rm\s+(-rf?|--recursive)\s+\*",     # rm -rf *
    r":\(\)\{\s*:\|\:\s*&\s*\};:",       # Fork bomb
    r">\s*/dev/sd[a-z]",                  # Write to raw disk
    r"mkfs\.",                            # Format filesystem
    r"dd\s+.*of=/dev/",                   # dd to device

    # Privilege escalation
    r"sudo\s+su\s*$",                     # sudo su (become root)
    r"sudo\s+-i",                         # sudo -i (root shell)
    r"chmod\s+.*777\s+/",                 # chmod 777 /

    # Credential theft
    r"cat\s+.*\.ssh/",                    # Read SSH keys
    r"cat\s+.*/\.env",                    # Read env files from root paths
    r"cat\s+.*passwd",                    # Read password file
    r"cat\s+.*shadow",                    # Read shadow file

    # Network exfiltration
    r"curl\s+.*\|\s*bash",               # Pipe to bash
    r"wget\s+.*\|\s*bash",               # Pipe to bash
    r"curl\s+.*\|\s*sh",                  # Pipe to sh
    r"wget\s+.*\|\s*sh",                  # Pipe to sh

    # Crypto/mining patterns
    r"xmrig",                             # Mining software
    r"cpuminer",                          # Mining software
]

# Patterns that should trigger a warning but not block
SUSPICIOUS_BASH_PATTERNS = [
    r"sudo\s+",                           # Any sudo usage
    r"chmod\s+777",                       # Overly permissive chmod
    r"curl\s+.*-o",                       # Download to file
    r"wget\s+",                           # Download
    r"pip\s+install",                     # Installing packages
    r"npm\s+install\s+-g",                # Global npm install
]

# File paths that should never be written to
PROTECTED_PATHS = [
    "/etc/",
    "/usr/",
    "/bin/",
    "/sbin/",
    "/boot/",
    "/root/",
    "/var/log/",
    "/sys/",
    "/proc/",
    "~/.ssh/",
    "~/.gnupg/",
]


# =============================================================================
# PreToolUse Security Hooks
# =============================================================================


def create_bash_security_hook(
    user_id: str,
    block_dangerous: bool = True,
    log_suspicious: bool = True,
) -> Callable[[dict, str, Any], dict]:
    """
    Create a PreToolUse security hook for Bash commands.

    Blocks dangerous patterns and logs suspicious ones.
    This provides defense-in-depth beyond RBAC permissions.

    Args:
        user_id: User identifier for logging
        block_dangerous: Whether to block dangerous patterns
        log_suspicious: Whether to log suspicious patterns

    Returns:
        Hook callback function
    """

    def bash_security_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        """
        Security hook for Bash command execution.

        Returns empty dict to proceed, or denial response to block.
        """
        tool_name = input_data.get("tool_name", "")
        if tool_name != "Bash":
            return {}

        command = input_data.get("tool_input", {}).get("command", "")
        if not command:
            return {}

        # Check for dangerous patterns
        if block_dangerous:
            for pattern in DANGEROUS_BASH_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    logger.warning(
                        f"BLOCKED dangerous command for {user_id}: {command[:100]}"
                    )
                    _log_security_event(
                        user_id=user_id,
                        event="dangerous_command_blocked",
                        command=command,
                        pattern=pattern,
                    )
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": (
                                f"Security: Command matches dangerous pattern. "
                                f"This command type is blocked for safety."
                            ),
                        }
                    }

        # Log suspicious patterns
        if log_suspicious:
            for pattern in SUSPICIOUS_BASH_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    logger.info(
                        f"Suspicious command for {user_id}: {command[:100]}"
                    )
                    _log_security_event(
                        user_id=user_id,
                        event="suspicious_command",
                        command=command,
                        pattern=pattern,
                    )
                    break  # Only log once

        return {}

    return bash_security_hook


def create_file_path_security_hook(
    user_id: str,
) -> Callable[[dict, str, Any], dict]:
    """
    Create a PreToolUse security hook for file path validation.

    Blocks writes to protected system paths.

    Args:
        user_id: User identifier for logging

    Returns:
        Hook callback function
    """

    def file_path_security_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        """
        Security hook for file write operations.

        Returns empty dict to proceed, or denial response to block.
        """
        tool_name = input_data.get("tool_name", "")
        if tool_name not in ("Write", "Edit", "NotebookEdit"):
            return {}

        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")

        if not file_path:
            return {}

        # Expand ~ to home directory for checking
        expanded_path = file_path.replace("~", str(Path.home()))

        # Check against protected paths
        for protected in PROTECTED_PATHS:
            protected_expanded = protected.replace("~", str(Path.home()))
            if expanded_path.startswith(protected_expanded):
                logger.warning(
                    f"BLOCKED write to protected path for {user_id}: {file_path}"
                )
                _log_security_event(
                    user_id=user_id,
                    event="protected_path_blocked",
                    file_path=file_path,
                    protected_prefix=protected,
                )
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            f"Security: Cannot write to protected path {protected}. "
                            f"This path is protected for system safety."
                        ),
                    }
                }

        return {}

    return file_path_security_hook


def _log_security_event(
    user_id: str,
    event: str,
    **details,
) -> None:
    """Log a security event to the audit trail."""
    try:
        from tools.security import audit

        audit.log_event(
            event_type="security",
            action=event,
            user_id=user_id,
            status="blocked" if "blocked" in event else "warning",
            details=details,
        )
    except Exception as e:
        logger.debug(f"Failed to log security event: {e}")


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
    enable_security: bool = True,
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
        enable_security: Enable PreToolUse security checks (dangerous command blocking)
        enable_audit: Enable PreToolUse audit logging
        enable_dashboard: Enable PostToolUse dashboard recording
        enable_context_save: Enable Stop context saving

    Returns:
        Hooks configuration dict for SDK
    """
    hooks = {}

    # PreToolUse hooks
    pre_hooks = []

    # Security hooks (run first for defense-in-depth)
    if enable_security:
        # Bash security - block dangerous commands
        pre_hooks.append({
            "matcher": "Bash",
            "hooks": [create_bash_security_hook(user_id)],
        })
        # File path security - block writes to protected paths
        pre_hooks.append({
            "matcher": "Write|Edit|NotebookEdit",
            "hooks": [create_file_path_security_hook(user_id)],
        })

    # Audit hooks (run after security checks)
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
