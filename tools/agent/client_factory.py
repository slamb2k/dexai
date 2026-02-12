from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml

from tools.agent import PROJECT_ROOT, CONFIG_PATH
from tools.agent.constants import OWNER_USER_ID
from tools.agent.system_prompt import (
    SystemPromptBuilder,
    PromptContext,
    PromptMode,
    SessionType,
)

logger = logging.getLogger(__name__)


def _run_async_sync(coro, timeout=5.0):
    """Run an async coroutine from a sync context.

    Handles both cases: when an event loop is already running (uses a thread)
    and when no loop exists (creates a new one).

    Args:
        coro: An awaitable coroutine (not a coroutine function).
        timeout: Timeout in seconds for the thread-based fallback.

    Returns:
        The result of the coroutine.
    """
    import asyncio
    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result(timeout=timeout)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

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
- Ask clarifying questions rather than making assumptions

CONVERSATION CONTINUITY:
You greet users through the chat interface on page load. When you receive the
user's first message, do not re-introduce yourself or repeat your greeting.
Respond naturally to their request.""",
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


_VALIDATED_CONFIG_NAMES = {"agent", "routing", "memory", "multimodal", "security", "workspace"}


def load_config(config_name: str = "agent") -> dict:
    # For core configs, try Pydantic validation first
    if config_name in _VALIDATED_CONFIG_NAMES:
        try:
            from tools.agent.config_models import load_and_validate
            validated = load_and_validate(config_name)
            return validated.model_dump()
        except Exception as e:
            logger.warning(f"Config validation failed for {config_name}, using raw config: {e}")

    # Fall back to raw YAML loading (also the default path for "agent" config)
    if config_name == "agent":
        config_path = CONFIG_PATH
    else:
        from tools.agent import ARGS_DIR
        config_path = ARGS_DIR / f"{config_name}.yaml"

    if config_path.exists():
        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or DEFAULT_CONFIG
        except Exception:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def _get_memory_service():
    try:
        async def _init_service():
            from tools.memory.service import MemoryService
            service = MemoryService()
            await service.initialize()
            return service

        return _run_async_sync(_init_service())
    except Exception as e:
        logger.debug(f"Failed to initialize MemoryService: {e}")
        return None


def build_system_prompt(
    config: dict,
    channel: str = "direct",
    session_type: str = "main",
    prompt_mode: Optional[str] = None,
    workspace_root: Optional[Path] = None,
) -> str:
    builder = SystemPromptBuilder(config.get("system_prompt", {}))
    context = PromptContext(
        user_id=OWNER_USER_ID,
        session_type=SessionType(session_type),
        prompt_mode=PromptMode(prompt_mode) if prompt_mode else None,
        channel=channel,
        workspace_root=workspace_root or PROJECT_ROOT,
    )
    prompt = builder.build(context)

    if context.include_runtime_context:
        prompt = _add_runtime_context(
            prompt, config, workspace_root=workspace_root or PROJECT_ROOT
        )

    return prompt


def _add_runtime_context(
    prompt: str,
    config: dict,
    workspace_root: Optional[Path] = None,
) -> str:
    parts = [prompt]
    prompt_config = config.get("system_prompt", {})

    memory_service = _get_memory_service()

    if prompt_config.get("include_memory", True):
        try:
            if memory_service:
                from tools.memory.providers.base import SearchFilters, MemoryType

                async def _search():
                    filters = SearchFilters(
                        types=[MemoryType.PREFERENCE, MemoryType.FACT],
                    )
                    return await memory_service.search(
                        query="user preferences and context",
                        limit=5,
                        filters=filters,
                    )

                results = _run_async_sync(_search())

                if results:
                    memory_context = "\n".join(
                        f"- {r.content[:200]}"
                        for r in results[:3]
                    )
                    parts.append(f"\nRELEVANT MEMORY:\n{memory_context}")
            else:
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

    if prompt_config.get("include_commitments", True):
        try:
            if memory_service:
                async def _list_commitments():
                    return await memory_service.list_commitments(
                        status="active",
                        limit=5,
                    )

                commitment_list = _run_async_sync(_list_commitments())

                if commitment_list:
                    formatted = "\n".join(
                        f"- {c.get('content', '')} (to {c.get('target_person', 'someone')})"
                        for c in commitment_list[:3]
                    )
                    parts.append(f"\nACTIVE COMMITMENTS:\n{formatted}")
            else:
                from tools.memory import commitments

                result = commitments.list_commitments(user_id=OWNER_USER_ID, status="active")
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

    if prompt_config.get("include_energy", True):
        try:
            from tools.learning import energy_tracker

            result = energy_tracker.get_current_energy(user_id=OWNER_USER_ID)
            if result.get("success"):
                energy = result.get("energy_level", "unknown")
                confidence = result.get("confidence", 0)
                if confidence > 0.5:
                    parts.append(f"\nCURRENT ENERGY LEVEL: {energy}")
        except Exception:
            pass

    skills_config = config.get("skills", DEFAULT_CONFIG.get("skills", {}))
    if skills_config.get("allow_self_modification", False):
        parts.append(SKILLS_AUTHORIZATION)

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
