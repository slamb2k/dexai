"""
DexAI SDK Client

Wraps the Claude Agent SDK with DexAI-specific defaults, ADHD-aware system prompts,
intelligent model routing, and integration with the permission system.

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

    # With explicit complexity hint:
    from tools.agent.model_router import TaskComplexity
    async with DexAIClient(user_id="alice", explicit_complexity=TaskComplexity.TRIVIAL) as client:
        response = await client.query("hi")  # Routes to cheaper model
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Optional, TYPE_CHECKING

import yaml

from tools.agent import PROJECT_ROOT, CONFIG_PATH
from tools.agent.system_prompt import (
    SystemPromptBuilder,
    PromptContext,
    PromptMode,
    SessionType,
)

if TYPE_CHECKING:
    from tools.agent.model_router import TaskComplexity

logger = logging.getLogger(__name__)


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
    },
    "skills": {
        "allow_self_modification": True,
        "writable_directory": ".claude/skills",
        "protected_skills": ["prime", "ship", "sync"],
    },
}

# Self-improvement authorization for skill creation
SKILLS_AUTHORIZATION = """
## Self-Improvement Capabilities

You can extend your own capabilities by creating new skills.

SKILL CREATION RULES:
1. Create skills in `.claude/skills/<skill-name>/`
2. Each skill needs:
   - `SKILL.md` - YAML frontmatter (name, description) + brief overview
   - `instructions.md` - Step-by-step implementation instructions
3. Skills are automatically loaded on next interaction
4. Never modify skills in `.claude/prime/`, `.claude/ship/`, `.claude/sync/` - those are system skills

WHEN TO CREATE A SKILL:
- Repetitive multi-step workflows the user performs often
- Domain-specific knowledge worth preserving
- Automations that combine multiple tools

This is NOT modifying your core code - it's extending capabilities through the skills system.
"""


def load_config() -> dict:
    """Load agent configuration from YAML file."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                return yaml.safe_load(f) or DEFAULT_CONFIG
        except Exception:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def _get_memory_service():
    """Get or initialize the memory service for system prompt building."""
    try:
        import asyncio

        async def _init_service():
            from tools.memory.service import MemoryService
            service = MemoryService()
            await service.initialize()
            return service

        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - can't use run_until_complete
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _init_service())
                return future.result(timeout=5.0)
        except RuntimeError:
            # No running loop - we can create one
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_init_service())
            finally:
                loop.close()
    except Exception as e:
        logger.debug(f"Failed to initialize MemoryService: {e}")
        return None


def build_system_prompt(
    user_id: str,
    config: dict,
    channel: str = "direct",
    session_type: str = "main",
    prompt_mode: Optional[str] = None,
) -> str:
    """
    Build the system prompt with user-specific context.

    Uses SystemPromptBuilder for workspace-based prompts with session-based
    file filtering, then adds runtime context (memory, commitments, energy)
    for main sessions via MemoryService.

    Args:
        user_id: User identifier for context loading
        config: Agent configuration
        channel: Communication channel (direct, telegram, discord, slack)
        session_type: Session type (main, subagent, heartbeat, cron)
        prompt_mode: Prompt mode override (full, minimal, none). If None, uses session default.

    Returns:
        Complete system prompt string
    """
    # Build base prompt from workspace files with session-based filtering
    builder = SystemPromptBuilder(config.get("system_prompt", {}))
    context = PromptContext(
        user_id=user_id,
        session_type=SessionType(session_type),
        prompt_mode=PromptMode(prompt_mode) if prompt_mode else None,
        channel=channel,
        workspace_root=PROJECT_ROOT,
    )
    prompt = builder.build(context)

    # Only add runtime context for sessions that include it (main sessions with full mode)
    if context.include_runtime_context:
        prompt = _add_runtime_context(prompt, user_id, config)

    return prompt


def _add_runtime_context(prompt: str, user_id: str, config: dict) -> str:
    """
    Add runtime context (memory, commitments, energy, skills) to prompt.

    Args:
        prompt: Base prompt from SystemPromptBuilder
        user_id: User identifier
        config: Agent configuration

    Returns:
        Prompt with runtime context added
    """
    parts = [prompt]
    prompt_config = config.get("system_prompt", {})

    # Try to get memory service
    memory_service = _get_memory_service()

    # Include memory context
    if prompt_config.get("include_memory", True):
        try:
            if memory_service:
                # Use MemoryService (provider-agnostic)
                import asyncio
                from tools.memory.providers.base import SearchFilters, MemoryType

                async def _search():
                    filters = SearchFilters(
                        types=[MemoryType.PREFERENCE, MemoryType.FACT],
                        user_id=user_id,
                    )
                    return await memory_service.search(
                        query="user preferences and context",
                        limit=5,
                        filters=filters,
                    )

                try:
                    loop = asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, _search())
                        results = future.result(timeout=5.0)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        results = loop.run_until_complete(_search())
                    finally:
                        loop.close()

                if results:
                    memory_context = "\n".join(
                        f"- {r.content[:200]}"
                        for r in results[:3]
                    )
                    parts.append(f"\nRELEVANT MEMORY:\n{memory_context}")
            else:
                # Fallback to legacy direct import
                from tools.memory import hybrid_search

                result = hybrid_search.hybrid_search(
                    query="user preferences and context",
                    limit=5
                )
                if result.get("success") and result.get("results"):
                    memory_context = "\n".join(
                        f"- {r.get('content', '')[:200]}"
                        for r in result.get("results", [])[:3]
                    )
                    parts.append(f"\nRELEVANT MEMORY:\n{memory_context}")
        except Exception as e:
            logger.debug(f"Failed to load memory context: {e}")

    # Include active commitments
    if prompt_config.get("include_commitments", True):
        try:
            if memory_service:
                # Use MemoryService (provider-agnostic)
                import asyncio

                async def _list_commitments():
                    return await memory_service.list_commitments(
                        user_id=user_id,
                        status="active",
                        limit=5,
                    )

                try:
                    loop = asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, _list_commitments())
                        commitment_list = future.result(timeout=5.0)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        commitment_list = loop.run_until_complete(_list_commitments())
                    finally:
                        loop.close()

                if commitment_list:
                    formatted = "\n".join(
                        f"- {c.get('content', '')} (to {c.get('target_person', 'someone')})"
                        for c in commitment_list[:3]
                    )
                    parts.append(f"\nACTIVE COMMITMENTS:\n{formatted}")
            else:
                # Fallback to legacy direct import
                from tools.memory import commitments

                result = commitments.list_commitments(user_id=user_id, status="active")
                if result.get("success"):
                    data = result.get("data", {})
                    commitment_items = data.get("commitments", [])
                    if commitment_items:
                        formatted = "\n".join(
                            f"- {c.get('content', '')} (to {c.get('target_person', 'someone')})"
                            for c in commitment_items[:3]
                        )
                        parts.append(f"\nACTIVE COMMITMENTS:\n{formatted}")
        except Exception as e:
            logger.debug(f"Failed to load commitments: {e}")

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

    # Include skills self-modification authorization
    skills_config = config.get("skills", DEFAULT_CONFIG.get("skills", {}))
    if skills_config.get("allow_self_modification", False):
        parts.append(SKILLS_AUTHORIZATION)

        # List agent-created skills if any exist
        try:
            writable_dir = skills_config.get("writable_directory", ".claude/skills")
            skills_path = PROJECT_ROOT / writable_dir
            if skills_path.exists():
                agent_skills = [
                    d.name for d in skills_path.iterdir()
                    if d.is_dir() and (d / "SKILL.md").exists()
                ]
                if agent_skills:
                    skill_list = ", ".join(f"`{s}`" for s in sorted(agent_skills))
                    parts.append(f"\nAGENT-CREATED SKILLS: {skill_list}")
        except Exception:
            pass

    return "\n".join(parts)


class DexAIClient:
    """
    Claude Agent SDK client wrapper with DexAI integration.

    Provides:
    - ADHD-aware system prompts with session-based file filtering
    - DexAI permission integration
    - User-specific context loading
    - Intelligent model routing (complexity-based)
    - Cost tracking integration

    Session Types:
    - main: Full interactive session (all files + runtime context)
    - subagent: Task-focused agent (PERSONA + AGENTS only, no personal context)
    - heartbeat: Proactive check-in (PERSONA + AGENTS + HEARTBEAT)
    - cron: Scheduled job (PERSONA + AGENTS only)
    """

    def __init__(
        self,
        user_id: str,
        working_dir: str | None = None,
        config: dict | None = None,
        explicit_complexity: "TaskComplexity | None" = None,
        session_type: str = "main",
        channel: str = "direct",
    ):
        """
        Initialize DexAI client.

        Args:
            user_id: User identifier for permissions and context
            working_dir: Working directory for file operations (default: PROJECT_ROOT)
            config: Optional config override (default: load from args/agent.yaml)
            explicit_complexity: Optional explicit complexity hint for routing
            session_type: Session type (main, subagent, heartbeat, cron)
            channel: Communication channel (direct, telegram, discord, slack)
        """
        self.user_id = user_id
        self.config = config or load_config()
        self.working_dir = working_dir or str(
            self.config.get("agent", {}).get("working_directory") or PROJECT_ROOT
        )
        self.explicit_complexity = explicit_complexity
        self.session_type = session_type
        self.channel = channel
        self._client = None
        self._session_id: str | None = None
        self._total_cost: float = 0.0
        self._router = None
        self._pending_prompt: str | None = None
        self._last_routing_decision = None

    async def __aenter__(self) -> "DexAIClient":
        """Async context manager entry."""
        await self._init_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self._cleanup()

    def _init_router(self):
        """Initialize the model router if routing is enabled."""
        agent_config = self.config.get("agent", {})

        # Check if routing is enabled
        if not agent_config.get("use_routing", True):
            return None

        try:
            from tools.agent.model_router import ModelRouter, ROUTING_CONFIG_PATH

            if ROUTING_CONFIG_PATH.exists():
                router = ModelRouter.from_config(ROUTING_CONFIG_PATH)
                if router.enabled and router.openrouter_api_key:
                    logger.info(f"Model router initialized (profile={router.profile.value})")
                    return router
                elif not router.openrouter_api_key:
                    logger.warning("OPENROUTER_API_KEY not set, routing disabled")
            else:
                logger.debug("Routing config not found, using default model")
        except Exception as e:
            logger.warning(f"Failed to initialize router: {e}")

        return None

    async def _init_client(self) -> None:
        """Initialize the SDK client with intelligent model routing."""
        try:
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
        except ImportError:
            raise ImportError(
                "claude-agent-sdk required. Install with: uv pip install claude-agent-sdk"
            )

        # Import permission callback and DexAI tools
        from tools.agent.permissions import create_permission_callback
        from tools.agent.sdk_tools import dexai_server

        agent_config = self.config.get("agent", {})
        tools_config = self.config.get("tools", {})

        # Build allowed tools list: built-in + DexAI tools
        allowed_tools = tools_config.get("allowed_builtin", []).copy()
        allowed_tools.append("mcp__dexai__*")  # Allow all DexAI tools

        # Initialize router
        self._router = self._init_router()

        # Determine model and env vars via routing
        model = agent_config.get("model", "claude-sonnet-4-20250514")
        env = {}

        if self._router and self._pending_prompt:
            from tools.agent.model_router import TaskComplexity

            # Route the request
            decision = self._router.route(
                self._pending_prompt,
                explicit_complexity=self.explicit_complexity,
                tool_count=len(allowed_tools),
            )

            # Build options dict
            routing_options = self._router.build_options_dict(decision)

            model = routing_options["model"]
            env = routing_options["env"]
            self._last_routing_decision = decision

            logger.info(f"Routed to {model}: {routing_options['reasoning']}")

            # Record routing to dashboard
            self._record_routing_to_dashboard(decision)
        elif self._router:
            # No pending prompt yet, use moderate complexity as default
            from tools.agent.model_router import TaskComplexity

            decision = self._router.route(
                "",
                explicit_complexity=self.explicit_complexity or TaskComplexity.MODERATE,
                tool_count=len(allowed_tools),
            )
            routing_options = self._router.build_options_dict(decision)
            model = routing_options["model"]
            env = routing_options["env"]
            self._last_routing_decision = decision

        # Build options with session-aware system prompt
        options = ClaudeAgentOptions(
            model=model,
            allowed_tools=allowed_tools,
            mcp_servers={"dexai": dexai_server},  # Register DexAI tools
            cwd=self.working_dir,
            permission_mode=agent_config.get("permission_mode", "default"),
            system_prompt=build_system_prompt(
                user_id=self.user_id,
                config=self.config,
                channel=self.channel,
                session_type=self.session_type,
            ),
            can_use_tool=create_permission_callback(self.user_id, self.config),
            env=env or {},
        )

        self._client = ClaudeSDKClient(options=options)
        await self._client.__aenter__()

    def _record_routing_to_dashboard(self, decision) -> None:
        """Record routing decision to dashboard for analytics."""
        try:
            from tools.dashboard.backend.database import record_routing_decision
            record_routing_decision(
                user_id=self.user_id,
                complexity=decision.complexity.value,
                model=decision.primary_model.routed_id,
                exacto=decision.primary_model.use_exacto,
                reasoning=decision.reasoning,
            )
        except ImportError:
            pass  # Dashboard not available
        except Exception as e:
            logger.debug(f"Failed to record routing decision: {e}")

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

        # Store prompt for potential re-routing in future queries
        self._pending_prompt = message

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

        # Extract routing metadata if available
        model = None
        complexity = None
        routing_reasoning = None
        if self._last_routing_decision:
            model = self._last_routing_decision.primary_model.routed_id
            complexity = self._last_routing_decision.complexity.value
            routing_reasoning = self._last_routing_decision.reasoning

        return QueryResult(
            text=text,
            tool_uses=tool_uses,
            cost_usd=total_cost,
            session_total_cost_usd=self._total_cost,
            model=model,
            complexity=complexity,
            routing_reasoning=routing_reasoning,
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
        model: str | None = None,
        complexity: str | None = None,
        routing_reasoning: str | None = None,
    ):
        self.text = text
        self.tool_uses = tool_uses
        self.cost_usd = cost_usd
        self.session_total_cost_usd = session_total_cost_usd
        self.model = model
        self.complexity = complexity
        self.routing_reasoning = routing_reasoning

    def __str__(self) -> str:
        return self.text


# =============================================================================
# Convenience Functions
# =============================================================================


async def quick_query(
    user_id: str,
    message: str,
    session_type: str = "main",
    channel: str = "direct",
) -> str:
    """
    Quick one-shot query without context management.

    Args:
        user_id: User identifier
        message: Message to send
        session_type: Session type (main, subagent, heartbeat, cron)
        channel: Communication channel

    Returns:
        Response text
    """
    async with DexAIClient(
        user_id=user_id,
        session_type=session_type,
        channel=channel,
    ) as client:
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
    parser.add_argument("--session", default="main",
                        choices=["main", "subagent", "heartbeat", "cron"],
                        help="Session type (controls prompt content)")
    parser.add_argument("--channel", default="direct", help="Channel (direct, telegram, discord)")

    args = parser.parse_args()

    if args.show_config:
        config = load_config()
        print(yaml.dump(config, default_flow_style=False))
        return

    if args.query:
        async def run_query():
            result = await quick_query(
                args.user,
                args.query,
                session_type=args.session,
                channel=args.channel,
            )
            print(result)
            return result

        asyncio.run(run_query())

    elif args.interactive:
        async def interactive():
            async with DexAIClient(
                user_id=args.user,
                session_type=args.session,
                channel=args.channel,
            ) as client:
                print(f"DexAI Interactive Mode (session={args.session}, channel={args.channel})")
                print("Type 'exit' to quit")
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
