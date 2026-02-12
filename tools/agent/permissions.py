"""
SDK Permission Callback

Provides the can_use_tool callback for Claude Agent SDK that integrates with
DexAI's RBAC permission system.

The callback:
1. Maps SDK tool names to DexAI permission strings
2. Checks user permissions via the existing RBAC system
3. Logs tool usage to audit trail
4. Handles elevated actions requiring confirmation
5. Handles AskUserQuestion for ADHD-friendly clarification

Usage:
    from tools.agent.permissions import create_permission_callback

    callback = create_permission_callback(config=config)
    options = ClaudeAgentOptions(can_use_tool=callback, ...)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Union

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent.constants import OWNER_USER_ID

logger = logging.getLogger(__name__)

# Permission result types for SDK integration
# These match the claude-agent-sdk types for proper integration


class PermissionResultAllow:
    """Allow tool execution, optionally with modified input."""

    def __init__(self, updated_input: dict | None = None):
        self.type = "allow"
        self.updated_input = updated_input


class PermissionResultDeny:
    """Deny tool execution with optional message."""

    def __init__(self, message: str = "", interrupt: bool = False):
        self.type = "deny"
        self.message = message
        self.interrupt = interrupt


PermissionResult = Union[PermissionResultAllow, PermissionResultDeny, bool]


# Read-only tools that can be auto-approved for lower friction
READ_ONLY_TOOLS = {
    "Read", "Glob", "Grep", "LS", "WebSearch", "WebFetch",
    "TaskGet", "TaskList", "NotebookRead",
    "dexai_memory_search", "dexai_commitments_list",
    "dexai_context_resume", "dexai_friction_check",
    "dexai_current_step", "dexai_energy_match",
}


# Default permission mapping (SDK tool -> DexAI permission)
DEFAULT_PERMISSION_MAPPING = {
    # File operations
    "Read": "files:read",
    "Write": "files:write",
    "Edit": "files:write",
    "Glob": "files:read",
    "Grep": "files:read",
    "LS": "files:read",

    # System operations
    "Bash": "system:execute",

    # Network operations
    "WebSearch": "network:request",
    "WebFetch": "network:request",

    # Task operations (native SDK tasks)
    "TaskCreate": "tasks:write",
    "TaskUpdate": "tasks:write",
    "TaskGet": "tasks:read",
    "TaskList": "tasks:read",

    # Notebook operations
    "NotebookEdit": "files:write",
    "NotebookRead": "files:read",

    # User interaction (handled specially in callback)
    "AskUserQuestion": "chat:send",
}

# DexAI custom tool permission mapping
DEXAI_PERMISSION_MAPPING = {
    # Memory tools
    "dexai_memory_search": "memory:read",
    "dexai_memory_write": "memory:write",
    "dexai_commitments_add": "memory:write",
    "dexai_commitments_list": "memory:read",
    "dexai_context_capture": "memory:write",
    "dexai_context_resume": "memory:read",

    # Task tools
    "dexai_task_decompose": "tasks:write",
    "dexai_friction_check": "tasks:read",
    "dexai_friction_solve": "tasks:write",
    "dexai_current_step": "tasks:read",
    "dexai_energy_match": "tasks:read",

    # ADHD communication tools
    "dexai_format_response": "chat:send",
    "dexai_check_language": "chat:send",
}


def create_permission_callback(
    config: dict | None = None,
    channel: str = "direct",
    ask_user_handler: Callable | None = None,
) -> Callable[[str, dict], PermissionResult]:
    """
    Create a permission callback for the SDK.

    Returns proper PermissionResult types (Allow/Deny) for richer SDK integration.
    Handles AskUserQuestion specially for ADHD-friendly clarification.

    Args:
        config: Agent configuration (optional, loads from args/agent.yaml)
        channel: Communication channel (for formatting questions)
        ask_user_handler: Optional async callable to handle AskUserQuestion

    Returns:
        Callback function: (tool_name: str, tool_input: dict) -> PermissionResult
    """
    # Load permission mappings from config if provided
    if config:
        security_config = config.get("security", {})
        sdk_mapping = security_config.get("permission_mapping", DEFAULT_PERMISSION_MAPPING)
        dexai_mapping = security_config.get("dexai_permission_mapping", DEXAI_PERMISSION_MAPPING)
        audit_enabled = security_config.get("audit_tool_use", True)
    else:
        sdk_mapping = DEFAULT_PERMISSION_MAPPING
        dexai_mapping = DEXAI_PERMISSION_MAPPING
        audit_enabled = True

    # Combine mappings
    all_mappings = {**sdk_mapping, **dexai_mapping}

    def can_use_tool(tool_name: str, tool_input: dict) -> PermissionResult:
        """
        Check if the user can use a specific tool.

        Returns PermissionResultAllow or PermissionResultDeny for SDK integration.
        Handles AskUserQuestion specially for ADHD-friendly clarification.

        Args:
            tool_name: Name of the tool being invoked
            tool_input: Input parameters for the tool

        Returns:
            PermissionResultAllow or PermissionResultDeny
        """
        # Handle AskUserQuestion specially - this is the SDK's clarification tool
        if tool_name == "AskUserQuestion":
            return _handle_ask_user_question(
                tool_input=tool_input,
                channel=channel,
                handler=ask_user_handler,
                audit_enabled=audit_enabled,
            )

        # Get required permission for this tool
        required_permission = all_mappings.get(tool_name)

        if not required_permission:
            # Unknown tool - default to deny for security
            _log_tool_use(
                user_id=OWNER_USER_ID,
                tool_name=tool_name,
                tool_input=tool_input,
                allowed=False,
                reason="unknown_tool",
                audit_enabled=audit_enabled,
            )
            return PermissionResultDeny(
                message=f"Unknown tool: {tool_name}",
                interrupt=False,  # Let Claude try alternatives
            )

        # Check permission using DexAI's RBAC system
        try:
            from tools.security import permissions

            result = permissions.check_permission(
                user_id=user_id,
                permission=required_permission,
            )

            allowed = result.get("allowed", False)
            requires_elevation = result.get("requires_elevation", False)

            # Log the tool use
            _log_tool_use(
                user_id=OWNER_USER_ID,
                tool_name=tool_name,
                tool_input=tool_input,
                allowed=allowed,
                reason="permission_check",
                permission=required_permission,
                requires_elevation=requires_elevation,
                audit_enabled=audit_enabled,
            )

            if not allowed:
                return PermissionResultDeny(
                    message=f"Permission denied: {tool_name} requires {required_permission}",
                    interrupt=False,  # Let Claude try alternatives
                )

            # Auto-approve read-only tools for lower friction (ADHD-friendly)
            if tool_name in READ_ONLY_TOOLS:
                return PermissionResultAllow(updated_input=tool_input)

            # For write operations, allow with original input
            return PermissionResultAllow(updated_input=tool_input)

        except ImportError:
            # Permission system not available - allow with warning
            _log_tool_use(
                user_id=OWNER_USER_ID,
                tool_name=tool_name,
                tool_input=tool_input,
                allowed=True,
                reason="permission_system_unavailable",
                audit_enabled=audit_enabled,
            )
            return PermissionResultAllow(updated_input=tool_input)

        except Exception as e:
            # Error checking permissions - deny for safety
            _log_tool_use(
                user_id=OWNER_USER_ID,
                tool_name=tool_name,
                tool_input=tool_input,
                allowed=False,
                reason=f"permission_check_error: {str(e)}",
                audit_enabled=audit_enabled,
            )
            return PermissionResultDeny(
                message=f"Permission check error: {str(e)}",
                interrupt=False,
            )

    return can_use_tool


def _handle_ask_user_question(
    tool_input: dict,
    channel: str,
    handler: Callable | None,
    audit_enabled: bool,
) -> PermissionResult:
    """
    Handle AskUserQuestion tool for ADHD-friendly clarification.

    Formats questions for ADHD users (numbered, clear, brief) and
    collects answers through the channel adapter.

    Args:
        tool_input: Tool input containing questions
        channel: Communication channel
        handler: Optional async callable to handle question display
        audit_enabled: Whether to log

    Returns:
        PermissionResultAllow with answers or PermissionResultDeny
    """
    questions = tool_input.get("questions", [])

    # Format questions for ADHD users (RSD-safe, clear, numbered)
    formatted_questions = _format_questions_for_adhd(questions)

    # Log the question attempt
    _log_tool_use(
        user_id=OWNER_USER_ID,
        tool_name="AskUserQuestion",
        tool_input={"question_count": len(questions)},
        allowed=True,
        reason="ask_user_question",
        audit_enabled=audit_enabled,
    )

    # If we have a handler, use it to get answers
    if handler:
        try:
            # Run async handler
            if asyncio.iscoroutinefunction(handler):
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in async context - create task
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            handler(formatted_questions, OWNER_USER_ID, channel)
                        )
                        answers = future.result(timeout=300)  # 5 min timeout
                else:
                    answers = loop.run_until_complete(
                        handler(formatted_questions, OWNER_USER_ID, channel)
                    )
            else:
                answers = handler(formatted_questions, OWNER_USER_ID, channel)

            # Return with collected answers
            return PermissionResultAllow(
                updated_input={
                    "questions": questions,
                    "answers": answers,
                }
            )
        except Exception as e:
            logger.warning(f"AskUserQuestion handler error: {e}")
            # Fall through to default behavior

    # Default: Allow with empty answers (SDK will handle display)
    return PermissionResultAllow(
        updated_input={
            "questions": questions,
            "answers": {},  # SDK will collect answers
        }
    )


def _format_questions_for_adhd(questions: list[dict]) -> list[dict]:
    """
    Format questions for ADHD users.

    ADHD-friendly formatting:
    - Numbered for clear tracking
    - Brief and direct
    - RSD-safe language (no judgment)
    - Clear options

    Args:
        questions: List of question dicts from SDK

    Returns:
        Formatted question list
    """
    formatted = []
    for i, q in enumerate(questions, 1):
        question_text = q.get("question", "")
        options = q.get("options", [])
        header = q.get("header", "")

        # Format options with numbers
        formatted_options = []
        for j, opt in enumerate(options, 1):
            label = opt.get("label", f"Option {j}")
            desc = opt.get("description", "")
            formatted_options.append({
                "number": j,
                "label": label,
                "description": desc,
            })

        formatted.append({
            "number": i,
            "header": header,
            "question": question_text,
            "options": formatted_options,
            "multi_select": q.get("multiSelect", False),
        })

    return formatted


def _log_tool_use(
    user_id: str,
    tool_name: str,
    tool_input: dict,
    allowed: bool,
    reason: str,
    permission: str | None = None,
    requires_elevation: bool = False,
    audit_enabled: bool = True,
) -> None:
    """Log tool usage to audit trail."""
    if not audit_enabled:
        return

    try:
        from tools.security import audit

        # Sanitize tool input for logging (remove sensitive data)
        safe_input = _sanitize_for_logging(tool_input)

        audit.log_event(
            event_type="tool_use",
            action=tool_name,
            user_id=user_id,
            status="allowed" if allowed else "denied",
            details={
                "tool_input": safe_input,
                "reason": reason,
                "required_permission": permission,
                "requires_elevation": requires_elevation,
            },
        )
    except Exception:
        # Don't fail if audit logging fails
        pass


def _sanitize_for_logging(tool_input: dict) -> dict:
    """
    Remove sensitive information from tool input for logging.

    Args:
        tool_input: Original tool input

    Returns:
        Sanitized tool input safe for logging
    """
    if not isinstance(tool_input, dict):
        return {"raw": str(tool_input)[:200]}

    sanitized = {}
    sensitive_keys = {"password", "secret", "token", "key", "credential", "api_key"}

    for key, value in tool_input.items():
        lower_key = key.lower()

        # Check if key contains sensitive terms
        if any(s in lower_key for s in sensitive_keys):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str) and len(value) > 500:
            # Truncate long values
            sanitized[key] = value[:200] + "...[truncated]"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_for_logging(value)
        else:
            sanitized[key] = value

    return sanitized


def check_tool_permission(
    tool_name: str,
    config: dict | None = None,
    user_id: str = OWNER_USER_ID,
) -> dict[str, Any]:
    """
    Check if a user can use a specific tool (for testing/debugging).

    Args:
        user_id: User identifier
        tool_name: Tool name to check
        config: Optional configuration override

    Returns:
        Dict with permission check results
    """
    # Get permission mapping
    if config:
        security_config = config.get("security", {})
        sdk_mapping = security_config.get("permission_mapping", DEFAULT_PERMISSION_MAPPING)
        dexai_mapping = security_config.get("dexai_permission_mapping", DEXAI_PERMISSION_MAPPING)
    else:
        sdk_mapping = DEFAULT_PERMISSION_MAPPING
        dexai_mapping = DEXAI_PERMISSION_MAPPING

    all_mappings = {**sdk_mapping, **dexai_mapping}
    required_permission = all_mappings.get(tool_name)

    if not required_permission:
        return {
            "success": True,
            "allowed": False,
            "tool_name": tool_name,
            "reason": "unknown_tool",
            "required_permission": None,
        }

    try:
        from tools.security import permissions

        result = permissions.check_permission(
            user_id=user_id,
            permission=required_permission,
        )

        return {
            "success": True,
            "allowed": result.get("allowed", False),
            "tool_name": tool_name,
            "required_permission": required_permission,
            "user_permissions": result.get("user_permissions", []),
            "requires_elevation": result.get("requires_elevation", False),
        }

    except Exception as e:
        return {
            "success": False,
            "allowed": False,
            "tool_name": tool_name,
            "required_permission": required_permission,
            "error": str(e),
        }


def get_allowed_tools(config: dict | None = None, user_id: str = OWNER_USER_ID) -> dict[str, Any]:
    """
    Get list of tools a user is allowed to use.

    Args:
        user_id: User identifier
        config: Optional configuration override

    Returns:
        Dict with lists of allowed SDK and DexAI tools
    """
    if config:
        security_config = config.get("security", {})
        sdk_mapping = security_config.get("permission_mapping", DEFAULT_PERMISSION_MAPPING)
        dexai_mapping = security_config.get("dexai_permission_mapping", DEXAI_PERMISSION_MAPPING)
    else:
        sdk_mapping = DEFAULT_PERMISSION_MAPPING
        dexai_mapping = DEXAI_PERMISSION_MAPPING

    allowed_sdk = []
    allowed_dexai = []

    try:
        from tools.security import permissions

        user_perms = permissions.get_user_permissions(user_id)

        # Check SDK tools
        for tool_name, required_perm in sdk_mapping.items():
            if any(permissions.permission_matches(up, required_perm) for up in user_perms):
                allowed_sdk.append(tool_name)

        # Check DexAI tools
        for tool_name, required_perm in dexai_mapping.items():
            if any(permissions.permission_matches(up, required_perm) for up in user_perms):
                allowed_dexai.append(tool_name)

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }

    return {
        "success": True,
        "user_id": user_id,
        "allowed_sdk_tools": sorted(allowed_sdk),
        "allowed_dexai_tools": sorted(allowed_dexai),
        "total_allowed": len(allowed_sdk) + len(allowed_dexai),
    }


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for permission testing."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="SDK Permission Checker")
    parser.add_argument("--tool", help="Specific tool to check")
    parser.add_argument("--list-allowed", action="store_true", help="List all allowed tools")
    parser.add_argument("--list-mappings", action="store_true", help="List permission mappings")

    args = parser.parse_args()

    if args.list_mappings:
        print("SDK Tool -> Permission Mapping:")
        print("-" * 40)
        for tool, perm in sorted(DEFAULT_PERMISSION_MAPPING.items()):
            print(f"  {tool}: {perm}")
        print()
        print("DexAI Tool -> Permission Mapping:")
        print("-" * 40)
        for tool, perm in sorted(DEXAI_PERMISSION_MAPPING.items()):
            print(f"  {tool}: {perm}")
        return

    if args.list_allowed:
        result = get_allowed_tools()
        if result.get("success"):
            print(f"Allowed tools for owner:")
            print()
            print("SDK Tools:")
            for tool in result.get("allowed_sdk_tools", []):
                print(f"  - {tool}")
            print()
            print("DexAI Tools:")
            for tool in result.get("allowed_dexai_tools", []):
                print(f"  - {tool}")
            print()
            print(f"Total: {result.get('total_allowed', 0)} tools")
        else:
            print(f"Error: {result.get('error')}")
        return

    if args.tool:
        result = check_tool_permission(args.tool)
        status = "ALLOWED" if result.get("allowed") else "DENIED"
        print(f"{status}: {args.tool}")
        print(json.dumps(result, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
