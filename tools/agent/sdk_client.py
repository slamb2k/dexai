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
from typing import Any, AsyncIterator, AsyncGenerator, Optional, Union, TYPE_CHECKING

import yaml

from tools.agent import PROJECT_ROOT, CONFIG_PATH
from tools.agent.system_prompt import (
    SystemPromptBuilder,
    PromptContext,
    PromptMode,
    SessionType,
)
from tools.agent.subagents import get_agents_for_sdk
from tools.agent.schemas import (
    TASK_DECOMPOSITION_SCHEMA,
    ENERGY_ASSESSMENT_SCHEMA,
    COMMITMENT_LIST_SCHEMA,
    FRICTION_CHECK_SCHEMA,
    CURRENT_STEP_SCHEMA,
    get_schema,
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

You can extend your own capabilities by creating new skills in your workspace.

SKILL CREATION RULES:
1. Create skills in `.claude/skills/<skill-name>/` (relative to your workspace)
2. Each skill needs:
   - `SKILL.md` - YAML frontmatter (name, description, dependencies) + brief overview
   - `instructions.md` - Step-by-step implementation instructions
3. Skills are automatically loaded and visible in the dashboard
4. Built-in skills (adhd-decomposition, energy-matching, etc.) are read-only

SKILL.md FORMAT:
```yaml
---
name: skill-name
description: What the skill does
dependencies:        # Optional - Python packages needed
  - package-name>=1.0.0
  - another-package
---
# Skill Title
[Brief overview of what this skill does]
```

DEPENDENCY HANDLING:
When a skill requires external packages:

1. **Declare dependencies** in SKILL.md frontmatter (as shown above)
2. **Check user preference** using `dexai_get_skill_dependency_setting` tool
3. Based on setting:
   - "ask": Ask user "This skill needs `{package}`. Install it?"
   - "always": Inform user, then verify and install
   - "never": Suggest code-only alternative OR report cannot create skill
4. **Before installing**, verify package security using `dexai_verify_package` tool
5. **Install** using `dexai_install_package` tool (NOT direct pip commands)
6. **Verify** the import works before completing skill creation

WHEN DEPENDENCIES AREN'T AVAILABLE:
- First, try to find a code-only solution (pure Python, no external deps)
- If no alternative exists, clearly explain what's needed and why
- Never create a skill that won't work due to missing dependencies

WHEN TO CREATE A SKILL:
- Repetitive multi-step workflows the user performs often
- Domain-specific knowledge worth preserving
- Automations that combine multiple tools

Your skills are stored in your isolated workspace and are separate from built-in system skills.
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
    workspace_root: Optional[Path] = None,
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
        workspace_root: Optional workspace root for reading bootstrap files.
                       If None, uses PROJECT_ROOT.

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
        workspace_root=workspace_root or PROJECT_ROOT,
    )
    prompt = builder.build(context)

    # Only add runtime context for sessions that include it (main sessions with full mode)
    if context.include_runtime_context:
        prompt = _add_runtime_context(
            prompt, user_id, config, workspace_root=workspace_root or PROJECT_ROOT
        )

    return prompt


def _add_runtime_context(
    prompt: str,
    user_id: str,
    config: dict,
    workspace_root: Optional[Path] = None,
) -> str:
    """
    Add runtime context (memory, commitments, energy, skills) to prompt.

    Args:
        prompt: Base prompt from SystemPromptBuilder
        user_id: User identifier
        config: Agent configuration
        workspace_root: Optional workspace root for skill paths.
                       If None, uses PROJECT_ROOT.

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

        # List agent-created skills if any exist (from workspace, not global)
        try:
            writable_dir = skills_config.get("writable_directory", ".claude/skills")
            skills_root = workspace_root or PROJECT_ROOT
            skills_path = skills_root / writable_dir
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
    - DexAI permission integration with AskUserQuestion support
    - User-specific context loading
    - Intelligent model routing (complexity-based)
    - Cost tracking integration
    - SDK session resumption for context continuity
    - Lifecycle hooks for context saving
    - Sandbox configuration for safe Bash execution

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
        resume_session_id: str | None = None,
        ask_user_handler: Optional[callable] = None,
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
            resume_session_id: Optional session ID to resume (SDK session resumption)
            ask_user_handler: Optional async callable to handle AskUserQuestion
        """
        self.user_id = user_id
        self.config = config or load_config()
        self.working_dir = working_dir or str(
            self.config.get("agent", {}).get("working_directory") or PROJECT_ROOT
        )
        self.explicit_complexity = explicit_complexity
        self.session_type = session_type
        self.channel = channel
        self.resume_session_id = resume_session_id
        self.ask_user_handler = ask_user_handler
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
        """Initialize the SDK client with intelligent model routing, hooks, and sandbox."""
        try:
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
        except ImportError:
            raise ImportError(
                "claude-agent-sdk required. Install with: uv pip install claude-agent-sdk"
            )

        # Import permission callback, hooks, and DexAI tools
        from tools.agent.permissions import create_permission_callback
        from tools.agent.hooks import create_hooks
        from tools.agent.sdk_tools import dexai_server

        agent_config = self.config.get("agent", {})
        tools_config = self.config.get("tools", {})
        sandbox_config = self.config.get("sandbox", {})

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

        # Build sandbox settings if enabled
        sandbox_settings = None
        if sandbox_config.get("enabled", False):
            sandbox_settings = {
                "enabled": True,
                "autoAllowBashIfSandboxed": sandbox_config.get(
                    "auto_allow_bash_if_sandboxed", True
                ),
                "excludedCommands": sandbox_config.get("excluded_commands", []),
                "allowUnsandboxedCommands": sandbox_config.get(
                    "allow_unsandboxed_commands", True
                ),
            }
            # Add network settings if present
            network_config = sandbox_config.get("network", {})
            if network_config:
                sandbox_settings["network"] = {
                    "allowLocalBinding": network_config.get("allow_local_binding", True),
                    "allowUnixSockets": network_config.get("allow_unix_sockets", []),
                }

        # Determine workspace root for system prompt and security hooks
        workspace_root = Path(self.working_dir) if self.working_dir else None

        # Build hooks for lifecycle events (including security)
        hooks = create_hooks(
            user_id=self.user_id,
            channel=self.channel,
            enable_security=True,  # Block dangerous commands
            enable_audit=True,
            enable_dashboard=True,
            enable_context_save=True,
            workspace_path=workspace_root,  # For workspace boundary enforcement
        )

        # Get subagent definitions if enabled
        subagents_config = self.config.get("subagents", {})
        agents = None
        if subagents_config.get("enabled", True):
            try:
                agents = get_agents_for_sdk()
                logger.debug(f"Registered {len(agents)} ADHD subagents")
            except Exception as e:
                logger.warning(f"Failed to load subagents: {e}")

        # Build options with session-aware system prompt
        options_kwargs = {
            "model": model,
            "allowed_tools": allowed_tools,
            "mcp_servers": {"dexai": dexai_server},
            "cwd": self.working_dir,
            "permission_mode": agent_config.get("permission_mode", "default"),
            "system_prompt": build_system_prompt(
                user_id=self.user_id,
                config=self.config,
                channel=self.channel,
                session_type=self.session_type,
                workspace_root=workspace_root,
            ),
            "can_use_tool": create_permission_callback(
                user_id=self.user_id,
                config=self.config,
                channel=self.channel,
                ask_user_handler=self.ask_user_handler,
            ),
            "env": env or {},
        }

        # Add subagents if loaded
        if agents:
            options_kwargs["agents"] = agents

        # Add sandbox if configured
        if sandbox_settings:
            options_kwargs["sandbox"] = sandbox_settings

        # Add hooks if any
        if hooks:
            options_kwargs["hooks"] = hooks

        # Add session resumption if we have a session ID
        if self.resume_session_id:
            options_kwargs["resume"] = self.resume_session_id
            logger.info(f"Resuming session: {self.resume_session_id}")

        options = ClaudeAgentOptions(**options_kwargs)

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

        Captures session_id from SDK for future session resumption.

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
            # Capture session_id from init message for future resumption
            if hasattr(msg, "type") and msg.type == "system":
                if hasattr(msg, "subtype") and msg.subtype == "init":
                    if hasattr(msg, "session_id"):
                        self._session_id = msg.session_id
                        logger.debug(f"Captured session_id: {self._session_id}")

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

    async def query_stream(
        self,
        message_generator: AsyncGenerator[Union[str, dict], None],
    ) -> AsyncIterator[Any]:
        """
        Send messages dynamically using streaming input mode.

        The SDK supports streaming input where an AsyncGenerator can yield messages
        dynamically. This allows users to add context mid-conversation while
        Claude is processing (interruption support).

        The generator should yield messages in one of these formats:
        - String: Automatically converted to SDK format:
            {"type": "user", "message": {"role": "user", "content": str}}
        - Dict: Used directly, should follow SDK format:
            {"type": "user", "message": {"role": "user", "content": "..."}}

        Args:
            message_generator: AsyncGenerator yielding messages (str or dict)

        Yields:
            SDK message objects (AssistantMessage, ResultMessage, etc.)

        Example:
            async def dynamic_messages():
                yield "What's the weather like?"
                await asyncio.sleep(3)  # User adds more context
                yield "Actually, I'm in Seattle"

            async with DexAIClient(user_id="alice") as client:
                async for msg in client.query_stream(dynamic_messages()):
                    if isinstance(msg, AssistantMessage):
                        print(msg.content)
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        # Create a wrapper generator that normalizes message format
        async def normalized_generator():
            async for msg in message_generator:
                if isinstance(msg, str):
                    # Convert string to SDK format
                    yield {
                        "type": "user",
                        "message": {"role": "user", "content": msg}
                    }
                elif isinstance(msg, dict):
                    # Ensure dict has the right structure
                    if "type" not in msg:
                        # Wrap raw content dict
                        yield {
                            "type": "user",
                            "message": {"role": "user", "content": msg.get("content", str(msg))}
                        }
                    else:
                        yield msg
                else:
                    # Fallback: convert to string
                    yield {
                        "type": "user",
                        "message": {"role": "user", "content": str(msg)}
                    }

        # Use the SDK's streaming input mode
        # The SDK accepts an AsyncGenerator as the prompt parameter
        try:
            from claude_agent_sdk import query
        except ImportError:
            raise ImportError(
                "claude-agent-sdk required. Install with: uv pip install claude-agent-sdk"
            )

        # We need to use the SDK's query function directly with the generator
        # The SDK handles queued messages with interruption support
        async for msg in query(
            prompt=normalized_generator(),
            options=self._client._options if hasattr(self._client, "_options") else None,
        ):
            # Capture session_id from init message
            if hasattr(msg, "type") and msg.type == "system":
                if hasattr(msg, "subtype") and msg.subtype == "init":
                    if hasattr(msg, "session_id"):
                        self._session_id = msg.session_id
                        logger.debug(f"Captured session_id from stream: {self._session_id}")

            yield msg

    async def interrupt(self) -> None:
        """
        Interrupt an ongoing query.

        Can be used to stop Claude's processing, for example when the user
        wants to cancel or provide new instructions.
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        if hasattr(self._client, "interrupt"):
            await self._client.interrupt()
        else:
            logger.warning("Interrupt not supported by current SDK client")

    async def query_structured(
        self,
        message: str,
        schema_name: str | None = None,
        output_format: dict[str, Any] | None = None,
    ) -> "StructuredQueryResult":
        """
        Query the agent with structured JSON output.

        Uses the SDK's output_format parameter to request validated JSON responses.
        The response is guaranteed to match the provided schema.

        Args:
            message: User message to send
            schema_name: Name of a predefined schema (e.g., "task_decomposition")
            output_format: Custom output format dict (overrides schema_name)

        Returns:
            StructuredQueryResult with structured_output dict and metadata

        Raises:
            ValueError: If neither schema_name nor output_format is provided
            ValueError: If schema_name is unknown

        Example:
            result = await client.query_structured(
                "Break down 'do taxes' into steps",
                schema_name="task_decomposition"
            )
            step = result.structured_output["current_step"]
            print(f"Do: {step['action']} ({step['duration_minutes']} min)")

        Available schemas:
            - task_decomposition: ADHD task breakdown with one step at a time
            - energy_assessment: Energy level detection and task matching
            - commitment_list: RSD-safe commitment tracking
            - friction_check: Blocker identification and solutions
            - current_step: One-thing mode single action
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        # Determine output format
        if output_format:
            selected_format = output_format
        elif schema_name:
            selected_format = get_schema(schema_name)
            if not selected_format:
                raise ValueError(
                    f"Unknown schema: {schema_name}. "
                    f"Available: task_decomposition, energy_assessment, "
                    f"commitment_list, friction_check, current_step"
                )
        else:
            raise ValueError(
                "Either schema_name or output_format must be provided"
            )

        try:
            from claude_agent_sdk import (
                ClaudeSDKClient,
                ClaudeAgentOptions,
                AssistantMessage,
                ResultMessage,
                TextBlock,
                ToolUseBlock,
            )
        except ImportError:
            raise ImportError("claude-agent-sdk required")

        # Store prompt for potential re-routing
        self._pending_prompt = message

        # Create a new client with output_format
        # We need to build new options with the output_format parameter
        from tools.agent.permissions import create_permission_callback
        from tools.agent.hooks import create_hooks
        from tools.agent.sdk_tools import dexai_server

        agent_config = self.config.get("agent", {})
        tools_config = self.config.get("tools", {})
        sandbox_config = self.config.get("sandbox", {})

        allowed_tools = tools_config.get("allowed_builtin", []).copy()
        allowed_tools.append("mcp__dexai__*")

        # Use existing routing decision or route new
        model = agent_config.get("model", "claude-sonnet-4-20250514")
        env = {}

        if self._router:
            from tools.agent.model_router import TaskComplexity

            decision = self._router.route(
                message,
                explicit_complexity=self.explicit_complexity,
                tool_count=len(allowed_tools),
            )
            routing_options = self._router.build_options_dict(decision)
            model = routing_options["model"]
            env = routing_options["env"]
            self._last_routing_decision = decision

        # Build sandbox settings if enabled
        sandbox_settings = None
        if sandbox_config.get("enabled", False):
            sandbox_settings = {
                "enabled": True,
                "autoAllowBashIfSandboxed": sandbox_config.get(
                    "auto_allow_bash_if_sandboxed", True
                ),
                "excludedCommands": sandbox_config.get("excluded_commands", []),
                "allowUnsandboxedCommands": sandbox_config.get(
                    "allow_unsandboxed_commands", True
                ),
            }
            network_config = sandbox_config.get("network", {})
            if network_config:
                sandbox_settings["network"] = {
                    "allowLocalBinding": network_config.get("allow_local_binding", True),
                    "allowUnixSockets": network_config.get("allow_unix_sockets", []),
                }

        # Determine workspace root for system prompt and security hooks
        workspace_root = Path(self.working_dir) if self.working_dir else None

        hooks = create_hooks(
            user_id=self.user_id,
            channel=self.channel,
            enable_security=True,
            enable_audit=True,
            enable_dashboard=True,
            enable_context_save=True,
            workspace_path=workspace_root,  # For workspace boundary enforcement
        )

        subagents_config = self.config.get("subagents", {})
        agents = None
        if subagents_config.get("enabled", True):
            try:
                agents = get_agents_for_sdk()
            except Exception:
                pass

        # Build options with output_format
        options_kwargs = {
            "model": model,
            "allowed_tools": allowed_tools,
            "mcp_servers": {"dexai": dexai_server},
            "cwd": self.working_dir,
            "permission_mode": agent_config.get("permission_mode", "default"),
            "system_prompt": build_system_prompt(
                user_id=self.user_id,
                config=self.config,
                channel=self.channel,
                session_type=self.session_type,
                workspace_root=workspace_root,
            ),
            "can_use_tool": create_permission_callback(
                user_id=self.user_id,
                config=self.config,
                channel=self.channel,
                ask_user_handler=self.ask_user_handler,
            ),
            "env": env or {},
            "output_format": selected_format,  # Key addition for structured output
        }

        if agents:
            options_kwargs["agents"] = agents
        if sandbox_settings:
            options_kwargs["sandbox"] = sandbox_settings
        if hooks:
            options_kwargs["hooks"] = hooks
        if self.resume_session_id:
            options_kwargs["resume"] = self.resume_session_id

        options = ClaudeAgentOptions(**options_kwargs)

        # Create temporary client for structured query
        structured_client = ClaudeSDKClient(options=options)
        await structured_client.__aenter__()

        try:
            await structured_client.query(message)

            response_parts = []
            tool_uses = []
            total_cost = 0.0
            structured_output = None

            async for msg in structured_client.receive_response():
                # Capture session_id
                if hasattr(msg, "type") and msg.type == "system":
                    if hasattr(msg, "subtype") and msg.subtype == "init":
                        if hasattr(msg, "session_id"):
                            self._session_id = msg.session_id

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
                    # Extract structured output from result
                    if hasattr(msg, "structured_output"):
                        structured_output = msg.structured_output
                    break

            self._total_cost += total_cost

            # If no structured_output from SDK, try to parse from text
            if structured_output is None and response_parts:
                import json
                text = "\n".join(response_parts).strip()
                # Try to extract JSON from response
                try:
                    # Check if response is pure JSON
                    if text.startswith("{"):
                        structured_output = json.loads(text)
                    # Check for JSON in markdown code block
                    elif "```json" in text:
                        json_start = text.find("```json") + 7
                        json_end = text.find("```", json_start)
                        if json_end > json_start:
                            json_str = text[json_start:json_end].strip()
                            structured_output = json.loads(json_str)
                    elif "```" in text:
                        # Generic code block
                        json_start = text.find("```") + 3
                        json_end = text.find("```", json_start)
                        if json_end > json_start:
                            json_str = text[json_start:json_end].strip()
                            if json_str.startswith("{"):
                                structured_output = json.loads(json_str)
                except json.JSONDecodeError:
                    logger.debug("Failed to parse JSON from response text")

            # Extract routing metadata
            model_used = None
            complexity = None
            routing_reasoning = None
            if self._last_routing_decision:
                model_used = self._last_routing_decision.primary_model.routed_id
                complexity = self._last_routing_decision.complexity.value
                routing_reasoning = self._last_routing_decision.reasoning

            return StructuredQueryResult(
                structured_output=structured_output or {},
                raw_text="\n".join(response_parts),
                tool_uses=tool_uses,
                cost_usd=total_cost,
                session_total_cost_usd=self._total_cost,
                schema_name=schema_name,
                model=model_used,
                complexity=complexity,
                routing_reasoning=routing_reasoning,
            )

        finally:
            await structured_client.__aexit__(None, None, None)

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

    @property
    def session_id(self) -> str | None:
        """
        Session ID from SDK for resumption.

        Use this to resume the session later by passing to resume_session_id.
        """
        return self._session_id


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


class StructuredQueryResult:
    """
    Result from a structured query to the agent.

    Contains validated JSON output that matches the requested schema,
    plus metadata about the query.
    """

    def __init__(
        self,
        structured_output: dict[str, Any],
        raw_text: str,
        tool_uses: list[dict],
        cost_usd: float,
        session_total_cost_usd: float,
        schema_name: str | None = None,
        model: str | None = None,
        complexity: str | None = None,
        routing_reasoning: str | None = None,
    ):
        self.structured_output = structured_output
        self.raw_text = raw_text
        self.tool_uses = tool_uses
        self.cost_usd = cost_usd
        self.session_total_cost_usd = session_total_cost_usd
        self.schema_name = schema_name
        self.model = model
        self.complexity = complexity
        self.routing_reasoning = routing_reasoning

    def __str__(self) -> str:
        """String representation shows formatted JSON."""
        import json
        return json.dumps(self.structured_output, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the structured output."""
        return self.structured_output.get(key, default)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-like access to structured output."""
        return self.structured_output[key]

    def __contains__(self, key: str) -> bool:
        """Check if key exists in structured output."""
        return key in self.structured_output

    @property
    def current_step(self) -> dict[str, Any] | None:
        """
        Convenience accessor for task decomposition current_step.

        Returns:
            Current step dict or None if not present
        """
        return self.structured_output.get("current_step")

    @property
    def blockers(self) -> list[dict[str, Any]]:
        """
        Convenience accessor for blockers list.

        Returns:
            List of blocker dicts (empty if none)
        """
        return self.structured_output.get("blockers", [])

    @property
    def remaining_steps(self) -> int:
        """
        Convenience accessor for remaining step count.

        Returns:
            Number of remaining steps or 0 if not present
        """
        return self.structured_output.get("remaining_steps", 0)


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


async def quick_decompose(
    user_id: str,
    task: str,
    channel: str = "direct",
) -> StructuredQueryResult:
    """
    Quick task decomposition with structured output.

    Uses the task_decomposition schema for ADHD-friendly task breakdown.

    Args:
        user_id: User identifier
        task: Task to decompose
        channel: Communication channel

    Returns:
        StructuredQueryResult with current_step, remaining_steps, and blockers
    """
    async with DexAIClient(
        user_id=user_id,
        session_type="main",
        channel=channel,
    ) as client:
        return await client.query_structured(
            f"Break down this task into small steps: {task}",
            schema_name="task_decomposition",
        )


async def quick_energy_match(
    user_id: str,
    context: str,
    channel: str = "direct",
) -> StructuredQueryResult:
    """
    Quick energy assessment with structured output.

    Detects energy level and suggests matched tasks.

    Args:
        user_id: User identifier
        context: Context for energy detection
        channel: Communication channel

    Returns:
        StructuredQueryResult with detected_energy and suggested_task
    """
    async with DexAIClient(
        user_id=user_id,
        session_type="main",
        channel=channel,
    ) as client:
        return await client.query_structured(
            f"Assess energy and match tasks: {context}",
            schema_name="energy_assessment",
        )


async def quick_friction_check(
    user_id: str,
    task: str,
    channel: str = "direct",
) -> StructuredQueryResult:
    """
    Quick friction check with structured output.

    Identifies blockers that might stall progress.

    Args:
        user_id: User identifier
        task: Task to check for friction
        channel: Communication channel

    Returns:
        StructuredQueryResult with friction_found, blockers, and ready_to_proceed
    """
    async with DexAIClient(
        user_id=user_id,
        session_type="main",
        channel=channel,
    ) as client:
        return await client.query_structured(
            f"Check for friction/blockers: {task}",
            schema_name="friction_check",
        )


async def quick_current_step(
    user_id: str,
    context: str = "",
    channel: str = "direct",
) -> StructuredQueryResult:
    """
    Get the ONE thing to do right now (one-thing mode).

    Args:
        user_id: User identifier
        context: Optional context about current work
        channel: Communication channel

    Returns:
        StructuredQueryResult with step (action, context, duration)
    """
    prompt = "What's the ONE thing I should do right now?"
    if context:
        prompt = f"{prompt} Context: {context}"

    async with DexAIClient(
        user_id=user_id,
        session_type="main",
        channel=channel,
    ) as client:
        return await client.query_structured(prompt, schema_name="current_step")


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
