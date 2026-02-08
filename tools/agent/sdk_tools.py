"""
DexAI SDK Tools

Exposes DexAI's unique features as SDK tools using the @tool decorator.
These run in-process with the SDK - no separate MCP server needed.

Usage:
    from tools.agent.sdk_tools import dexai_server

    options = ClaudeAgentOptions(
        mcp_servers={"dexai": dexai_server},
        allowed_tools=["mcp__dexai__*"]  # Allow all DexAI tools
    )
"""

import sys
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import from SDK (graceful handling if not installed)
try:
    from claude_agent_sdk import tool, create_sdk_mcp_server
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    # Create stubs for when SDK isn't installed (allows importing for inspection)
    def tool(name, desc, schema):
        def decorator(func):
            func._tool_name = name
            func._tool_desc = desc
            func._tool_schema = schema
            return func
        return decorator

    def create_sdk_mcp_server(name, version, tools):
        return {"name": name, "version": version, "tools": tools, "_stub": True}


# =============================================================================
# Memory Tools
# =============================================================================

@tool(
    "memory_search",
    "Search persistent memory using hybrid keyword + semantic search",
    {"query": str, "limit": int}
)
async def memory_search(args: dict[str, Any]) -> dict[str, Any]:
    """Search memory with BM25 + semantic embeddings."""
    from tools.agent.mcp.memory_tools import dexai_memory_search

    result = dexai_memory_search(
        query=args["query"],
        limit=args.get("limit", 10)
    )
    return _format_result(result)


@tool(
    "memory_write",
    "Write to persistent memory with importance classification",
    {"content": str, "entry_type": str, "importance": int}
)
async def memory_write(args: dict[str, Any]) -> dict[str, Any]:
    """Write a memory entry."""
    from tools.agent.mcp.memory_tools import dexai_memory_write

    result = dexai_memory_write(
        content=args["content"],
        entry_type=args.get("entry_type", "fact"),
        importance=args.get("importance", 5)
    )
    return _format_result(result)


@tool(
    "commitments_add",
    "Track a promise/commitment to prevent relationship damage",
    {"content": str, "target_person": str, "due_date": str}
)
async def commitments_add(args: dict[str, Any]) -> dict[str, Any]:
    """Add a commitment."""
    from tools.agent.mcp.memory_tools import dexai_commitments_add

    result = dexai_commitments_add(
        content=args["content"],
        target_person=args.get("target_person"),
        due_date=args.get("due_date")
    )
    return _format_result(result)


@tool(
    "commitments_list",
    "List active commitments with ADHD-friendly framing",
    {"status": str, "limit": int}
)
async def commitments_list(args: dict[str, Any]) -> dict[str, Any]:
    """List commitments."""
    from tools.agent.mcp.memory_tools import dexai_commitments_list

    result = dexai_commitments_list(
        status=args.get("status", "active"),
        limit=args.get("limit", 10)
    )
    return _format_result(result)


@tool(
    "context_capture",
    "Capture current context for later resumption (saves 20-45min on context switch)",
    {"trigger": str, "active_file": str, "next_step": str}
)
async def context_capture(args: dict[str, Any]) -> dict[str, Any]:
    """Capture context snapshot."""
    from tools.agent.mcp.memory_tools import dexai_context_capture

    result = dexai_context_capture(
        trigger=args.get("trigger", "manual"),
        active_file=args.get("active_file"),
        next_step=args.get("next_step")
    )
    return _format_result(result)


@tool(
    "context_resume",
    "Generate 'you were here' resumption prompt for quick context recovery",
    {"snapshot_id": str}
)
async def context_resume(args: dict[str, Any]) -> dict[str, Any]:
    """Resume from context snapshot."""
    from tools.agent.mcp.memory_tools import dexai_context_resume

    result = dexai_context_resume(
        snapshot_id=args.get("snapshot_id")
    )
    return _format_result(result)


# =============================================================================
# Task Tools
# =============================================================================

@tool(
    "task_decompose",
    "Break a vague task into concrete actionable steps (LLM-powered)",
    {"task": str, "depth": str}
)
async def task_decompose(args: dict[str, Any]) -> dict[str, Any]:
    """Decompose task into steps."""
    from tools.agent.mcp.task_tools import dexai_task_decompose

    result = dexai_task_decompose(
        task=args["task"],
        depth=args.get("depth", "shallow")
    )
    return _format_result(result)


@tool(
    "friction_check",
    "Identify hidden blockers preventing task completion",
    {"task_id": str, "task_description": str}
)
async def friction_check(args: dict[str, Any]) -> dict[str, Any]:
    """Check for friction points."""
    from tools.agent.mcp.task_tools import dexai_friction_check

    result = dexai_friction_check(
        task_id=args.get("task_id"),
        task_description=args.get("task_description")
    )
    return _format_result(result)


@tool(
    "current_step",
    "Get ONE next action to take right now - no lists, just one thing",
    {"task_id": str, "energy_level": str}
)
async def current_step(args: dict[str, Any]) -> dict[str, Any]:
    """Get the single next action."""
    from tools.agent.mcp.task_tools import dexai_current_step

    result = dexai_current_step(
        task_id=args.get("task_id"),
        energy_level=args.get("energy_level")
    )
    return _format_result(result)


@tool(
    "energy_match",
    "Match tasks to current energy level",
    {"limit": int}
)
async def energy_match(args: dict[str, Any]) -> dict[str, Any]:
    """Get energy-matched tasks."""
    from tools.agent.mcp.task_tools import dexai_energy_match

    result = dexai_energy_match(
        limit=args.get("limit", 3)
    )
    return _format_result(result)


# =============================================================================
# Automation Tools
# =============================================================================

@tool(
    "schedule",
    "Create a scheduled job (cron, heartbeat, or trigger)",
    {"name": str, "task": str, "schedule": str, "job_type": str}
)
async def schedule(args: dict[str, Any]) -> dict[str, Any]:
    """Create scheduled job."""
    from tools.agent.mcp.automation_tools import dexai_schedule

    result = dexai_schedule(
        name=args["name"],
        task=args["task"],
        schedule=args["schedule"],
        job_type=args.get("job_type", "cron")
    )
    return _format_result(result)


@tool(
    "notify",
    "Send a notification (respects flow state - suppresses during focus)",
    {"user_id": str, "content": str, "priority": str}
)
async def notify(args: dict[str, Any]) -> dict[str, Any]:
    """Send notification."""
    from tools.agent.mcp.automation_tools import dexai_notify

    result = dexai_notify(
        user_id=args["user_id"],
        content=args["content"],
        priority=args.get("priority", "normal")
    )
    return _format_result(result)


@tool(
    "reminder",
    "Set a reminder for a specific time (supports natural language like 'in 30 minutes')",
    {"user_id": str, "content": str, "when": str}
)
async def reminder(args: dict[str, Any]) -> dict[str, Any]:
    """Set reminder."""
    from tools.agent.mcp.automation_tools import dexai_reminder

    result = dexai_reminder(
        user_id=args["user_id"],
        content=args["content"],
        when=args["when"]
    )
    return _format_result(result)


# =============================================================================
# Office Tools
# =============================================================================

@tool(
    "email_list",
    "List emails from inbox with optional filters",
    {"account_id": str, "limit": int, "unread_only": bool, "query": str}
)
async def email_list(args: dict[str, Any]) -> dict[str, Any]:
    """List emails."""
    from tools.agent.mcp.office_tools import dexai_email_list

    result = dexai_email_list(
        account_id=args["account_id"],
        limit=args.get("limit", 20),
        unread_only=args.get("unread_only", False),
        query=args.get("query")
    )
    return _format_result(result)


@tool(
    "email_read",
    "Read a single email's full content",
    {"account_id": str, "message_id": str}
)
async def email_read(args: dict[str, Any]) -> dict[str, Any]:
    """Read email."""
    from tools.agent.mcp.office_tools import dexai_email_read

    result = dexai_email_read(
        account_id=args["account_id"],
        message_id=args["message_id"]
    )
    return _format_result(result)


@tool(
    "email_draft",
    "Create an email draft with sentiment analysis",
    {"account_id": str, "to": str, "subject": str, "body": str}
)
async def email_draft(args: dict[str, Any]) -> dict[str, Any]:
    """Create email draft."""
    from tools.agent.mcp.office_tools import dexai_email_draft

    # Handle to as list
    to = args["to"]
    if isinstance(to, str):
        to = [to]

    result = dexai_email_draft(
        account_id=args["account_id"],
        to=to,
        subject=args["subject"],
        body=args["body"]
    )
    return _format_result(result)


@tool(
    "calendar_today",
    "Get today's calendar schedule",
    {"account_id": str}
)
async def calendar_today(args: dict[str, Any]) -> dict[str, Any]:
    """Get today's events."""
    from tools.agent.mcp.office_tools import dexai_calendar_today

    result = dexai_calendar_today(
        account_id=args["account_id"]
    )
    return _format_result(result)


@tool(
    "calendar_propose",
    "Propose a meeting (requires confirmation to create)",
    {"account_id": str, "title": str, "start_time": str, "duration_minutes": int}
)
async def calendar_propose(args: dict[str, Any]) -> dict[str, Any]:
    """Propose meeting."""
    from tools.agent.mcp.office_tools import dexai_calendar_propose

    result = dexai_calendar_propose(
        account_id=args["account_id"],
        title=args["title"],
        start_time=args["start_time"],
        duration_minutes=args.get("duration_minutes", 30)
    )
    return _format_result(result)


# =============================================================================
# Channel Tools
# =============================================================================

@tool(
    "channel_pair",
    "Complete channel pairing with a pairing code. Use when user wants to pair/link their Telegram, Discord, or other chat app.",
    {"code": str}
)
async def channel_pair(args: dict[str, Any]) -> dict[str, Any]:
    """Pair a channel using a pairing code."""
    from tools.agent.mcp.channel_tools import dexai_channel_pair

    result = dexai_channel_pair(
        code=args["code"]
    )
    return _format_result(result)


# =============================================================================
# Helper Functions
# =============================================================================

def _format_result(result: dict) -> dict[str, Any]:
    """Format tool result for SDK response."""
    import json

    if result.get("success"):
        # Remove internal fields
        output = {k: v for k, v in result.items() if k not in ("success", "tool")}
        return {
            "content": [{
                "type": "text",
                "text": json.dumps(output, indent=2, default=str)
            }]
        }
    else:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: {result.get('error', 'Unknown error')}"
            }],
            "is_error": True
        }


# =============================================================================
# Create SDK MCP Server
# =============================================================================

# Collect all tools
ALL_TOOLS = [
    # Memory
    memory_search,
    memory_write,
    commitments_add,
    commitments_list,
    context_capture,
    context_resume,
    # Task
    task_decompose,
    friction_check,
    current_step,
    energy_match,
    # Automation
    schedule,
    notify,
    reminder,
    # Office
    email_list,
    email_read,
    email_draft,
    calendar_today,
    calendar_propose,
    # Channel
    channel_pair,
]

# Create the SDK MCP server
dexai_server = create_sdk_mcp_server(
    name="dexai",
    version="1.0.0",
    tools=ALL_TOOLS
)


def get_tool_names() -> list[str]:
    """Get all DexAI tool names in SDK format."""
    return [f"mcp__dexai__{t.name}" for t in ALL_TOOLS]
