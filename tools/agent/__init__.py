"""
DexAI Agent Module

Provides Claude Agent SDK integration for DexAI with ADHD-aware features.

Components:
- sdk_client.py: Main ClaudeSDKClient wrapper with DexAI defaults
- permissions.py: SDK can_use_tool callback mapping DexAI RBAC
- mcp/: Custom MCP tools exposing DexAI's unique ADHD features

Usage:
    from tools.agent import DexAIClient, create_permission_callback

    # Create client with DexAI defaults
    client = DexAIClient(user_id="alice")

    # Query the agent
    response = await client.query("What's my next task?")
"""

from pathlib import Path

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
TOOLS_ROOT = Path(__file__).parent.parent
AGENT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
ARGS_DIR = PROJECT_ROOT / "args"
CONFIG_PATH = ARGS_DIR / "agent.yaml"

# Database paths
DB_PATH = DATA_DIR / "agent.db"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Exports
__all__ = [
    "PROJECT_ROOT",
    "TOOLS_ROOT",
    "AGENT_ROOT",
    "DATA_DIR",
    "ARGS_DIR",
    "CONFIG_PATH",
    "DB_PATH",
]
