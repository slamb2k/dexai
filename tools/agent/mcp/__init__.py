"""
DexAI MCP Tools

Custom MCP tools that expose DexAI's unique ADHD features to the Claude Agent SDK.

These tools wrap existing DexAI functionality so the SDK agent can invoke them:
- Memory tools: hybrid search, commitments, context capture/resume
- Task tools: decomposition, friction solving, current step, energy matching
- ADHD tools: response formatting, RSD-safe language filtering

Tool naming convention: dexai_<feature>_<action>
Examples: dexai_memory_search, dexai_task_decompose, dexai_current_step
"""

from pathlib import Path

# Path constants
MCP_ROOT = Path(__file__).parent
AGENT_ROOT = MCP_ROOT.parent
PROJECT_ROOT = AGENT_ROOT.parent.parent

__all__ = ["MCP_ROOT", "AGENT_ROOT", "PROJECT_ROOT"]
