"""
DexAI MCP Tools

Custom MCP tools that expose DexAI's unique ADHD features to the Claude Agent SDK.

These tools wrap existing DexAI functionality so the SDK agent can invoke them:
- Memory tools: hybrid search, commitments, context capture/resume
- Task tools: decomposition, friction solving, current step, energy matching
- ADHD tools: response formatting, RSD-safe language filtering
- Automation tools: scheduling, notifications, reminders
- Office tools: email, calendar integration

Tool naming convention: dexai_<feature>_<action>
Examples: dexai_memory_search, dexai_task_decompose, dexai_current_step

Usage:
    from tools.agent.mcp import memory_tools, task_tools, adhd_tools, automation_tools, office_tools
"""

from pathlib import Path

# Path constants
MCP_ROOT = Path(__file__).parent
AGENT_ROOT = MCP_ROOT.parent
PROJECT_ROOT = AGENT_ROOT.parent.parent

# Import tool modules for easy access
from tools.agent.mcp import memory_tools
from tools.agent.mcp import task_tools
from tools.agent.mcp import adhd_tools
from tools.agent.mcp import automation_tools
from tools.agent.mcp import office_tools

__all__ = [
    "MCP_ROOT",
    "AGENT_ROOT",
    "PROJECT_ROOT",
    "memory_tools",
    "task_tools",
    "adhd_tools",
    "automation_tools",
    "office_tools",
    "get_tool",
    "list_all_tools",
]


# =============================================================================
# Tool Access API
# =============================================================================
# Note: Progressive disclosure (tool search, lazy loading) is handled
# automatically by Claude Code when tools exceed 10% of context.
# No manual exposed/internal distinction needed.


def list_all_tools() -> dict[str, list[str]]:
    """List all available MCP tools grouped by category."""
    return {
        "memory": memory_tools.list_tools(),
        "task": task_tools.list_tools(),
        "adhd": adhd_tools.list_tools(),
        "automation": automation_tools.list_tools(),
        "office": office_tools.list_tools(),
    }


def get_tool(tool_name: str):
    """Get a tool function by name from any category."""
    for module in [memory_tools, task_tools, adhd_tools, automation_tools, office_tools]:
        tool = module.get_tool(tool_name)
        if tool:
            return tool
    return None
