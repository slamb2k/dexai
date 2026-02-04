"""
DexAI SDK Client

Wraps the Claude Agent SDK with DexAI-specific defaults, ADHD-aware system prompts,
and integration with the permission system.

Usage:
    from tools.agent.sdk_client import DexAIClient

    async with DexAIClient(user_id="alice") as client:
        response = await client.query("What's my next task?")
        print(response.text)

    # Or for streaming:
    async with DexAIClient(user_id="alice") as client:
        await client.query("Help me with taxes")
        async for message in client.receive_response():
            print(message)
"""

import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator

import yaml

from tools.agent import PROJECT_ROOT, CONFIG_PATH


# Default configuration if file doesn't exist
DEFAULT_CONFIG = {
    "agent": {
        "model": "claude-sonnet-4-20250514",
        "working_directory": None,
        "max_tokens": 4096,
        "permission_mode": "default",
    },
    "tools": {
        "allowed_builtin": [
            "Read", "Write", "Edit", "Glob", "Grep", "LS",
            "Bash", "WebSearch", "WebFetch",
            "TaskCreate", "TaskList", "TaskUpdate", "TaskGet",
        ],
        "require_confirmation": ["Write", "Edit", "Bash"],
    },
    "system_prompt": {
        "base": """You are Dex, a helpful AI assistant designed for users with ADHD.

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
- Ask clarifying questions rather than making assumptions""",
        "include_memory": True,
        "include_commitments": True,
        "include_energy": True,
    },
    "adhd": {
        "response": {
            "max_length_chat": 500,
            "strip_preamble": True,
            "one_thing_mode": True,
        }
    }
}


def load_config() -> dict:
    """Load agent configuration from YAML file."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                return yaml.safe_load(f) or DEFAULT_CONFIG
        except Exception:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def build_system_prompt(user_id: str, config: dict) -> str:
    """
    Build the system prompt with user-specific context.

    Args:
        user_id: User identifier for context loading
        config: Agent configuration

    Returns:
        Complete system prompt string
    """
    prompt_config = config.get("system_prompt", {})
    parts = [prompt_config.get("base", DEFAULT_CONFIG["system_prompt"]["base"])]

    # Include memory context
    if prompt_config.get("include_memory", True):
        try:
            from tools.memory import hybrid_search

            result = hybrid_search.search(
                query="user preferences and context",
                user_id=user_id,
                limit=5
            )
            if result.get("success") and result.get("results"):
                memory_context = "\n".join(
                    f"- {r.get('content', '')[:200]}"
                    for r in result.get("results", [])[:3]
                )
                parts.append(f"\nRELEVANT MEMORY:\n{memory_context}")
        except Exception:
            pass

    # Include active commitments
    if prompt_config.get("include_commitments", True):
        try:
            from tools.memory import commitments

            result = commitments.get_active_commitments(user_id=user_id)
            if result.get("success") and result.get("commitments"):
                commitment_list = "\n".join(
                    f"- {c.get('description', '')} (to {c.get('target_person', 'someone')})"
                    for c in result.get("commitments", [])[:3]
                )
                parts.append(f"\nACTIVE COMMITMENTS:\n{commitment_list}")
        except Exception:
            pass

    # Include energy level
    if prompt_config.get("include_energy", True):
        try:
            from tools.learning import energy_tracker

            result = energy_tracker.get_current_energy(user_id=user_id)
            if result.get("success"):
                energy = result.get("energy_level", "unknown")
                confidence = result.get("confidence", 0)
                if confidence > 0.5:
                    parts.append(f"\nCURRENT ENERGY LEVEL: {energy}")
        except Exception:
            pass

    return "\n".join(parts)


class DexAIClient:
    """
    Claude Agent SDK client wrapper with DexAI integration.

    Provides:
    - ADHD-aware system prompts
    - DexAI permission integration
    - User-specific context loading
    - Cost tracking integration
    """

    def __init__(
        self,
        user_id: str,
        working_dir: str | None = None,
        config: dict | None = None
    ):
        """
        Initialize DexAI client.

        Args:
            user_id: User identifier for permissions and context
            working_dir: Working directory for file operations (default: PROJECT_ROOT)
            config: Optional config override (default: load from args/agent.yaml)
        """
        self.user_id = user_id
        self.config = config or load_config()
        self.working_dir = working_dir or str(
            self.config.get("agent", {}).get("working_directory") or PROJECT_ROOT
        )
        self._client = None
        self._session_id: str | None = None
        self._total_cost: float = 0.0

    async def __aenter__(self) -> "DexAIClient":
        """Async context manager entry."""
        await self._init_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self._cleanup()

    async def _init_client(self) -> None:
        """Initialize the SDK client."""
        try:
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
        except ImportError:
            raise ImportError(
                "claude-agent-sdk required. Install with: uv pip install claude-agent-sdk"
            )

        # Import permission callback
        from tools.agent.permissions import create_permission_callback

        agent_config = self.config.get("agent", {})
        tools_config = self.config.get("tools", {})

        # Build options
        options = ClaudeAgentOptions(
            model=agent_config.get("model", "claude-sonnet-4-20250514"),
            allowed_tools=tools_config.get("allowed_builtin", []),
            cwd=self.working_dir,
            permission_mode=agent_config.get("permission_mode", "default"),
            system_prompt=build_system_prompt(self.user_id, self.config),
            can_use_tool=create_permission_callback(self.user_id, self.config),
            max_tokens=agent_config.get("max_tokens", 4096),
        )

        self._client = ClaudeSDKClient(options=options)
        await self._client.__aenter__()

    async def _cleanup(self) -> None:
        """Clean up the SDK client."""
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def query(self, message: str) -> "QueryResult":
        """
        Send a query to the agent.

        Args:
            message: User message to send

        Returns:
            QueryResult with response text and metadata
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        try:
            from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
        except ImportError:
            raise ImportError("claude-agent-sdk required")

        await self._client.query(message)

        response_parts = []
        tool_uses = []
        total_cost = 0.0

        async for msg in self._client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        response_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        tool_uses.append({
                            "tool": block.name,
                            "input": block.input,
                        })
            elif isinstance(msg, ResultMessage):
                if hasattr(msg, "total_cost_usd"):
                    total_cost = msg.total_cost_usd or 0.0
                break

        self._total_cost += total_cost

        # Apply ADHD formatting if enabled
        text = "\n".join(response_parts)
        adhd_config = self.config.get("adhd", {}).get("response", {})

        if adhd_config.get("strip_preamble", True):
            text = self._strip_preamble(text)

        max_length = adhd_config.get("max_length_chat", 500)
        if len(text) > max_length * 2:  # Only truncate if way over
            text = text[:max_length * 2] + "..."

        return QueryResult(
            text=text,
            tool_uses=tool_uses,
            cost_usd=total_cost,
            session_total_cost_usd=self._total_cost,
        )

    async def receive_response(self) -> AsyncIterator[Any]:
        """
        Stream responses from the agent.

        Yields:
            Message objects from the SDK (AssistantMessage, ResultMessage, etc.)
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        async for msg in self._client.receive_response():
            yield msg

    def _strip_preamble(self, text: str) -> str:
        """Remove common AI preambles from response."""
        preambles = [
            "Certainly!", "Of course!", "Sure!", "Absolutely!",
            "Great question!", "Good question!", "Happy to help!",
            "I'd be happy to", "I'll be glad to", "Let me help you with that.",
        ]
        stripped = text.strip()
        for preamble in preambles:
            if stripped.startswith(preamble):
                stripped = stripped[len(preamble):].lstrip()
        return stripped

    @property
    def total_cost(self) -> float:
        """Total cost for this session in USD."""
        return self._total_cost


class QueryResult:
    """Result from a query to the agent."""

    def __init__(
        self,
        text: str,
        tool_uses: list[dict],
        cost_usd: float,
        session_total_cost_usd: float,
    ):
        self.text = text
        self.tool_uses = tool_uses
        self.cost_usd = cost_usd
        self.session_total_cost_usd = session_total_cost_usd

    def __str__(self) -> str:
        return self.text


# =============================================================================
# Convenience Functions
# =============================================================================


async def quick_query(user_id: str, message: str) -> str:
    """
    Quick one-shot query without context management.

    Args:
        user_id: User identifier
        message: Message to send

    Returns:
        Response text
    """
    async with DexAIClient(user_id=user_id) as client:
        result = await client.query(message)
        return result.text


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing."""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="DexAI SDK Client")
    parser.add_argument("--user", default="test_user", help="User ID")
    parser.add_argument("--query", help="Query to send")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--show-config", action="store_true", help="Show configuration")

    args = parser.parse_args()

    if args.show_config:
        config = load_config()
        print(yaml.dump(config, default_flow_style=False))
        return

    if args.query:
        async def run_query():
            result = await quick_query(args.user, args.query)
            print(result)
            return result

        asyncio.run(run_query())

    elif args.interactive:
        async def interactive():
            async with DexAIClient(user_id=args.user) as client:
                print("DexAI Interactive Mode (type 'exit' to quit)")
                print("-" * 40)

                while True:
                    try:
                        user_input = input("\nYou: ").strip()
                        if user_input.lower() in ("exit", "quit", "q"):
                            break
                        if not user_input:
                            continue

                        result = await client.query(user_input)
                        print(f"\nDex: {result.text}")
                        if result.cost_usd > 0:
                            print(f"[Cost: ${result.cost_usd:.4f}]")

                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        print(f"Error: {e}")

                print(f"\nSession total cost: ${client.total_cost:.4f}")

        asyncio.run(interactive())

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
