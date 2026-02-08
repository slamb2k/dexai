"""
DexAI SDK Hooks

Lifecycle hooks for Claude Agent SDK integration.

Hooks provide pre/post tool execution callbacks and session lifecycle events.
DexAI uses these for:
- Security checks via PreToolUse (defense-in-depth)
- Context saving on session stop (ADHD-critical for resumption)
- Audit logging of tool usage
- Dashboard recording for analytics
- Performance monitoring of hook execution times

Usage:
    from tools.agent.hooks import create_hooks, get_hook_performance_summary

    hooks = create_hooks(user_id="alice", channel="telegram")
    options = ClaudeAgentOptions(hooks=hooks, ...)

    # Check hook performance
    summary = get_hook_performance_summary()
"""

from __future__ import annotations

import asyncio
import functools
import logging
import re
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)

# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# Performance Monitoring Infrastructure
# =============================================================================


class HookMetrics:
    """
    Singleton for tracking hook execution timing metrics.

    Thread-safe collection of timing data for all hooks.
    """

    _instance: HookMetrics | None = None
    _lock = threading.Lock()

    def __new__(cls) -> HookMetrics:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize instance variables."""
        self.timings: dict[str, list[float]] = {}  # hook_name -> [times_ms]
        self.slow_threshold_ms: float = 50.0
        self._timings_lock = threading.Lock()

    def record(self, hook_name: str, duration_ms: float) -> None:
        """
        Record a hook execution time.

        Args:
            hook_name: Name of the hook
            duration_ms: Execution duration in milliseconds
        """
        with self._timings_lock:
            if hook_name not in self.timings:
                self.timings[hook_name] = []
            self.timings[hook_name].append(duration_ms)

        # Log warning for slow hooks
        if duration_ms > self.slow_threshold_ms:
            logger.warning(
                f"Slow hook detected: {hook_name} took {duration_ms:.2f}ms "
                f"(threshold: {self.slow_threshold_ms}ms)"
            )

    def get_stats(self, hook_name: str) -> dict:
        """
        Get statistics for a specific hook.

        Args:
            hook_name: Name of the hook

        Returns:
            Dict with avg, p50, p95, p99, count, min, max
        """
        with self._timings_lock:
            times = self.timings.get(hook_name, [])

        if not times:
            return {
                "hook_name": hook_name,
                "count": 0,
                "avg_ms": 0.0,
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
            }

        sorted_times = sorted(times)
        count = len(times)

        def percentile(data: list[float], p: float) -> float:
            """Calculate percentile from sorted data."""
            if not data:
                return 0.0
            k = (len(data) - 1) * (p / 100)
            f = int(k)
            c = f + 1 if f + 1 < len(data) else f
            return data[f] + (k - f) * (data[c] - data[f]) if f != c else data[f]

        return {
            "hook_name": hook_name,
            "count": count,
            "avg_ms": statistics.mean(times),
            "p50_ms": percentile(sorted_times, 50),
            "p95_ms": percentile(sorted_times, 95),
            "p99_ms": percentile(sorted_times, 99),
            "min_ms": min(times),
            "max_ms": max(times),
        }

    def get_slow_calls(self) -> list[dict]:
        """
        Get list of hooks that have had slow calls.

        Returns:
            List of dicts with hook_name, slow_count, avg_slow_time, max_time
        """
        slow_calls = []

        with self._timings_lock:
            for hook_name, times in self.timings.items():
                slow_times = [t for t in times if t > self.slow_threshold_ms]
                if slow_times:
                    slow_calls.append({
                        "hook_name": hook_name,
                        "slow_count": len(slow_times),
                        "total_count": len(times),
                        "avg_slow_ms": statistics.mean(slow_times),
                        "max_ms": max(slow_times),
                        "threshold_ms": self.slow_threshold_ms,
                    })

        return sorted(slow_calls, key=lambda x: x["max_ms"], reverse=True)

    def summary(self) -> dict:
        """
        Get summary of all hook performance.

        Returns:
            Dict with all hooks statistics and overall metrics
        """
        with self._timings_lock:
            hook_names = list(self.timings.keys())

        stats = {}
        total_calls = 0
        total_time_ms = 0.0

        for hook_name in hook_names:
            hook_stats = self.get_stats(hook_name)
            stats[hook_name] = hook_stats
            total_calls += hook_stats["count"]
            total_time_ms += hook_stats["avg_ms"] * hook_stats["count"]

        return {
            "hooks": stats,
            "slow_calls": self.get_slow_calls(),
            "total_calls": total_calls,
            "total_time_ms": total_time_ms,
            "slow_threshold_ms": self.slow_threshold_ms,
            "hooks_count": len(hook_names),
        }

    def reset(self) -> None:
        """Reset all collected metrics."""
        with self._timings_lock:
            self.timings.clear()
        logger.info("Hook metrics reset")

    def set_slow_threshold(self, threshold_ms: float) -> None:
        """
        Set the threshold for slow hook warnings.

        Args:
            threshold_ms: Threshold in milliseconds
        """
        self.slow_threshold_ms = threshold_ms


# Module-level singleton instance
_metrics = HookMetrics()


def get_hook_metrics() -> HookMetrics:
    """Get the global HookMetrics singleton."""
    return _metrics


def get_hook_performance_summary() -> dict:
    """
    Get hook performance summary for dashboard.

    This is the main interface for external monitoring.

    Returns:
        Dict with complete performance summary
    """
    return _metrics.summary()


def timed_hook(hook_name: str) -> Callable[[F], F]:
    """
    Decorator that wraps a sync hook function to track execution time.

    Args:
        hook_name: Name to use for recording metrics

    Returns:
        Decorated function
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                _metrics.record(hook_name, duration_ms)
        return wrapper  # type: ignore
    return decorator


def async_timed_hook(hook_name: str) -> Callable[[F], F]:
    """
    Decorator that wraps an async hook function to track execution time.

    Args:
        hook_name: Name to use for recording metrics

    Returns:
        Decorated async function
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                _metrics.record(hook_name, duration_ms)
        return wrapper  # type: ignore
    return decorator


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
        Hook callback function (wrapped with timing)
    """

    @timed_hook("bash_security_hook")
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
    workspace_path: Optional[Path] = None,
) -> Callable[[dict, str, Any], dict]:
    """
    Create a PreToolUse security hook for file path validation.

    Blocks writes to protected system paths and workspace escape attempts.

    Args:
        user_id: User identifier for logging
        workspace_path: Optional workspace path to enforce boundary

    Returns:
        Hook callback function (wrapped with timing)
    """

    @timed_hook("file_path_security_hook")
    def file_path_security_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        """
        Security hook for file write operations.

        Returns empty dict to proceed, or denial response to block.
        """
        tool_name = input_data.get("tool_name", "")
        if tool_name not in ("Write", "Edit", "NotebookEdit", "Read"):
            return {}

        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")

        if not file_path:
            return {}

        # Expand ~ to home directory for checking
        expanded_path = file_path.replace("~", str(Path.home()))

        # Check for path traversal attempts (../../../ patterns)
        if ".." in file_path:
            # Resolve the path to check if it escapes workspace
            try:
                resolved = Path(file_path).resolve()
                if workspace_path:
                    workspace_resolved = workspace_path.resolve()
                    if not str(resolved).startswith(str(workspace_resolved)):
                        logger.warning(
                            f"BLOCKED path traversal escape for {user_id}: {file_path}"
                        )
                        _log_security_event(
                            user_id=user_id,
                            event="path_traversal_blocked",
                            file_path=file_path,
                            resolved_path=str(resolved),
                            workspace=str(workspace_path),
                        )
                        return {
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "permissionDecision": "deny",
                                "permissionDecisionReason": (
                                    "Security: Path traversal outside workspace is not allowed. "
                                    "File operations must stay within your workspace."
                                ),
                            }
                        }
            except Exception:
                pass  # If resolve fails, continue with other checks

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
                            f"Security: Cannot access protected path {protected}. "
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


@async_timed_hook("save_context_on_stop")
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
        Hook callback function (wrapped with timing)
    """

    @timed_hook("stop_hook")
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
        Hook callback function (wrapped with timing)
    """

    @timed_hook("audit_hook")
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
        Hook callback function (wrapped with timing)
    """

    @timed_hook("dashboard_hook")
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
    workspace_path: Optional[Path] = None,
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
        workspace_path: Optional workspace path for enforcing workspace boundaries

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
        # File path security - block writes to protected paths and workspace escapes
        pre_hooks.append({
            "matcher": "Write|Edit|NotebookEdit|Read",
            "hooks": [create_file_path_security_hook(user_id, workspace_path)],
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
    """CLI interface for testing hooks and viewing metrics."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="DexAI SDK Hooks")
    parser.add_argument("--user", default="test_user", help="User ID")
    parser.add_argument("--channel", default="cli", help="Channel")
    parser.add_argument("--test-stop", action="store_true", help="Test stop hook")
    parser.add_argument("--show-config", action="store_true", help="Show hooks config")
    parser.add_argument("--show-metrics", action="store_true", help="Show hook performance metrics")
    parser.add_argument("--reset-metrics", action="store_true", help="Reset all performance metrics")
    parser.add_argument(
        "--set-threshold",
        type=float,
        metavar="MS",
        help="Set slow hook threshold in milliseconds"
    )

    args = parser.parse_args()

    if args.reset_metrics:
        _metrics.reset()
        print("Hook performance metrics reset.")
        return

    if args.set_threshold:
        _metrics.set_slow_threshold(args.set_threshold)
        print(f"Slow hook threshold set to {args.set_threshold}ms")
        return

    if args.show_metrics:
        summary = get_hook_performance_summary()
        print("Hook Performance Metrics")
        print("=" * 60)
        print(f"Total hooks tracked: {summary['hooks_count']}")
        print(f"Total calls: {summary['total_calls']}")
        print(f"Total time: {summary['total_time_ms']:.2f}ms")
        print(f"Slow threshold: {summary['slow_threshold_ms']}ms")
        print()

        if summary["hooks"]:
            print("Per-Hook Statistics:")
            print("-" * 60)
            for hook_name, stats in summary["hooks"].items():
                print(f"\n  {hook_name}:")
                print(f"    Calls: {stats['count']}")
                print(f"    Avg:   {stats['avg_ms']:.3f}ms")
                print(f"    P50:   {stats['p50_ms']:.3f}ms")
                print(f"    P95:   {stats['p95_ms']:.3f}ms")
                print(f"    P99:   {stats['p99_ms']:.3f}ms")
                print(f"    Min:   {stats['min_ms']:.3f}ms")
                print(f"    Max:   {stats['max_ms']:.3f}ms")
        else:
            print("No hook metrics recorded yet.")

        if summary["slow_calls"]:
            print()
            print("Slow Calls Detected:")
            print("-" * 60)
            for slow in summary["slow_calls"]:
                print(f"\n  {slow['hook_name']}:")
                print(f"    Slow calls: {slow['slow_count']}/{slow['total_count']}")
                print(f"    Avg slow:   {slow['avg_slow_ms']:.3f}ms")
                print(f"    Max:        {slow['max_ms']:.3f}ms")
        return

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

        # Show metrics after test
        print("\nMetrics after test:")
        summary = get_hook_performance_summary()
        for hook_name, stats in summary["hooks"].items():
            print(f"  {hook_name}: {stats['count']} calls, avg {stats['avg_ms']:.3f}ms")


if __name__ == "__main__":
    main()
