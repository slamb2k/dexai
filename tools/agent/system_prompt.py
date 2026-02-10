"""
System Prompt Builder for DexAI

Dynamically generates system prompts by composing:
- Workspace files (PERSONA.md, IDENTITY.md, USER.md, etc.)
- Runtime context (memory, commitments, energy)
- Session-specific data (tools, timezone, prompt mode)

Templates in docs/templates/ are used only during bootstrap to create workspace files.
At runtime, only workspace files are read.

Session-Based File Filtering (inspired by OpenClaw):
    Different session types get different workspace files to optimize for their purpose:
    - main: All files (full context for interactive sessions)
    - subagent: PERSONA.md + AGENTS.md only (task-focused, no personal context)
    - heartbeat: PERSONA.md + AGENTS.md + HEARTBEAT.md (proactive check-ins)
    - cron: PERSONA.md + AGENTS.md (scheduled background jobs)

Architecture:
    ┌────────────────────────────────────────────────────────────────────┐
    │                    SystemPromptBuilder                              │
    ├────────────────────────────────────────────────────────────────────┤
    │  SESSION TYPE determines file access                               │
    │  ─────────────────────────────────────                             │
    │  main     → All files + runtime context                            │
    │  subagent → PERSONA + AGENTS only (no USER, MEMORY, etc.)          │
    │  heartbeat→ PERSONA + AGENTS + HEARTBEAT                           │
    │  cron     → PERSONA + AGENTS                                       │
    ├────────────────────────────────────────────────────────────────────┤
    │  PROMPT MODE determines detail level                               │
    │  ───────────────────────────────────                               │
    │  full    → All allowed files + runtime context                     │
    │  minimal → Core identity + safety only                             │
    │  none    → Single identity line                                    │
    └────────────────────────────────────────────────────────────────────┘

Usage:
    from tools.agent.system_prompt import SystemPromptBuilder, PromptContext, PromptMode, SessionType

    # Build prompt for a main user session
    builder = SystemPromptBuilder()
    context = PromptContext(
        user_id="alice",
        timezone="America/Los_Angeles",
        channel="telegram",
        session_type=SessionType.MAIN,
    )
    prompt = builder.build(context)

    # Build prompt for a subagent (minimal context)
    context = PromptContext(
        user_id="alice",
        session_type=SessionType.SUBAGENT,
    )
    prompt = builder.build(context)  # Only gets PERSONA.md + AGENTS.md

    # Bootstrap a new workspace
    from tools.agent.system_prompt import bootstrap_workspace
    result = bootstrap_workspace(Path("/path/to/workspace"))
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

from tools.agent import PROJECT_ROOT, ARGS_DIR

logger = logging.getLogger(__name__)

# Path constants
TEMPLATES_PATH = PROJECT_ROOT / "docs" / "templates"
CONFIG_PATH = ARGS_DIR / "system_prompt.yaml"

# Limits to prevent prompt explosion
MAX_FILE_CHARS = 20_000
MAX_TOTAL_CHARS = 100_000

# Files to copy during bootstrap (order matters for display)
BOOTSTRAP_FILES = [
    "PERSONA.md",
    "IDENTITY.md",
    "USER.md",
    "AGENTS.md",
    "ENV.md",
    "HEARTBEAT.md",
]

# Fallback identity if no workspace files exist
FALLBACK_IDENTITY = "You are Dex, an AI assistant designed for people with ADHD."


class PromptMode(Enum):
    """Prompt modes controlling detail level."""

    FULL = "full"  # All allowed sections + runtime context
    MINIMAL = "minimal"  # Core identity + safety only
    NONE = "none"  # Single identity line only


class SessionType(Enum):
    """
    Session types controlling which workspace files are accessible.

    Inspired by OpenClaw's session-based bootstrap file filtering.
    Different session types have different file allowlists for security
    and token efficiency.
    """

    MAIN = "main"  # Interactive user session - full access
    SUBAGENT = "subagent"  # Task-focused agent spawned by Task tool
    HEARTBEAT = "heartbeat"  # Proactive background check-in
    CRON = "cron"  # Scheduled background job


# File allowlists per session type
# Only files in the allowlist are loaded for that session type
SESSION_FILE_ALLOWLISTS: dict[SessionType, set[str]] = {
    SessionType.MAIN: {
        "PERSONA.md",
        "IDENTITY.md",
        "USER.md",
        "AGENTS.md",
        "ENV.md",
        "HEARTBEAT.md",
    },
    SessionType.SUBAGENT: {
        "PERSONA.md",  # Core identity/values
        "AGENTS.md",  # Operational guidelines
        # NO: IDENTITY.md, USER.md, ENV.md, HEARTBEAT.md
        # Subagents don't need personal context - they're task-focused
    },
    SessionType.HEARTBEAT: {
        "PERSONA.md",
        "AGENTS.md",
        "HEARTBEAT.md",  # Proactive check-in config
        # NO: USER.md, IDENTITY.md, ENV.md
    },
    SessionType.CRON: {
        "PERSONA.md",
        "AGENTS.md",
        # Minimal context for scheduled jobs
    },
}

# Default prompt mode per session type
SESSION_DEFAULT_PROMPT_MODE: dict[SessionType, PromptMode] = {
    SessionType.MAIN: PromptMode.FULL,
    SessionType.SUBAGENT: PromptMode.MINIMAL,
    SessionType.HEARTBEAT: PromptMode.MINIMAL,
    SessionType.CRON: PromptMode.MINIMAL,
}


@dataclass
class PromptContext:
    """Runtime context for prompt building."""

    user_id: str
    timezone: str = "UTC"
    current_time: Optional[str] = None
    tools: list[str] = field(default_factory=list)
    session_type: SessionType = SessionType.MAIN
    prompt_mode: Optional[PromptMode] = None  # None = use session default
    channel: str = "direct"
    workspace_root: Optional[Path] = None

    def __post_init__(self):
        """Validate and convert types."""
        # Convert string session_type to enum
        if isinstance(self.session_type, str):
            self.session_type = SessionType(self.session_type)

        # Convert string prompt_mode to enum
        if isinstance(self.prompt_mode, str):
            self.prompt_mode = PromptMode(self.prompt_mode)

        # Apply default prompt mode based on session type if not specified
        if self.prompt_mode is None:
            self.prompt_mode = SESSION_DEFAULT_PROMPT_MODE.get(
                self.session_type, PromptMode.FULL
            )

        if self.workspace_root is not None:
            self.workspace_root = Path(self.workspace_root)

    @property
    def file_allowlist(self) -> set[str]:
        """Get the file allowlist for this session type."""
        return SESSION_FILE_ALLOWLISTS.get(self.session_type, set())

    @property
    def is_subagent(self) -> bool:
        """Check if this is a subagent session."""
        return self.session_type == SessionType.SUBAGENT

    @property
    def include_runtime_context(self) -> bool:
        """Check if runtime context (memory, commitments) should be included."""
        # Only main sessions get runtime context
        return self.session_type == SessionType.MAIN and self.prompt_mode == PromptMode.FULL


def bootstrap_workspace(workspace: Path, force: bool = False) -> dict:
    """
    Bootstrap a new workspace by copying templates.

    Copies all template files from docs/templates/ to the workspace root.
    This is a one-time operation during workspace initialization.

    Args:
        workspace: Path to workspace root
        force: If True, overwrite existing files

    Returns:
        Dict with 'success', 'created', 'skipped' keys
    """
    workspace = Path(workspace)
    created = []
    skipped = []
    errors = []

    # Ensure workspace directory exists
    workspace.mkdir(parents=True, exist_ok=True)

    for filename in BOOTSTRAP_FILES:
        template_path = TEMPLATES_PATH / filename
        workspace_path = workspace / filename

        if not template_path.exists():
            logger.warning(f"Template not found: {template_path}")
            continue

        if workspace_path.exists() and not force:
            skipped.append(filename)
            continue

        try:
            # Read template content
            content = template_path.read_text()

            # Strip YAML frontmatter for cleaner workspace files
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2].strip()

            # Write to workspace
            workspace_path.write_text(content)
            created.append(filename)
            logger.info(f"Created {workspace_path}")

        except Exception as e:
            errors.append(f"{filename}: {e}")
            logger.error(f"Failed to create {filename}: {e}")

    return {
        "success": len(errors) == 0,
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


def is_workspace_bootstrapped(workspace: Path) -> bool:
    """
    Check if workspace has been bootstrapped.

    A workspace is considered bootstrapped if PERSONA.md exists at the root.

    Args:
        workspace: Path to workspace root

    Returns:
        True if bootstrapped, False otherwise
    """
    return (Path(workspace) / "PERSONA.md").exists()


class SystemPromptBuilder:
    """
    Builds system prompts from workspace files and runtime context.

    This class reads markdown files from the workspace root and combines them
    with runtime context (memory, commitments, energy) to create a complete
    system prompt for the agent.

    The prompt is built in layers:
    1. Core identity (PERSONA.md) - always included
    2. Identity customizations (IDENTITY.md)
    3. User context (USER.md)
    4. Operational guidelines (AGENTS.md)
    5. Environment notes (ENV.md)
    6. Safety guardrails
    7. Temporal context (time, timezone)
    8. Channel-specific rules

    Different prompt modes control which layers are included:
    - FULL: All layers
    - MINIMAL: Core identity + safety only
    - NONE: Single identity line
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize the builder.

        Args:
            config: Optional configuration override (default: load from file)
        """
        self.config = config or self._load_config()
        self._cache: dict[str, str] = {}

    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH) as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        return {}

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content

    def _read_workspace_file(self, name: str, workspace: Path) -> Optional[str]:
        """
        Read a file from the workspace root.

        Args:
            name: Filename to read
            workspace: Workspace root path

        Returns:
            File content (frontmatter stripped) or None if not found
        """
        path = workspace / name
        if not path.exists():
            return None

        try:
            content = self._strip_frontmatter(path.read_text())

            # Truncate if too long
            if len(content) > MAX_FILE_CHARS:
                content = content[:MAX_FILE_CHARS] + "\n[... truncated ...]"

            return content
        except Exception as e:
            logger.warning(f"Failed to read {name}: {e}")
            return None

    def _is_file_allowed(self, filename: str, context: PromptContext) -> bool:
        """
        Check if a file is allowed for the current session type.

        Args:
            filename: Name of the workspace file
            context: Current prompt context

        Returns:
            True if file is in the session's allowlist
        """
        allowlist = context.file_allowlist
        return filename in allowlist

    def build(self, context: PromptContext) -> str:
        """
        Build the complete system prompt from workspace files.

        Files are filtered based on session type:
        - main: All files
        - subagent: PERSONA.md + AGENTS.md only
        - heartbeat: PERSONA.md + AGENTS.md + HEARTBEAT.md
        - cron: PERSONA.md + AGENTS.md

        Args:
            context: Runtime context with user info, channel, session type, etc.

        Returns:
            Complete system prompt string
        """
        workspace = context.workspace_root or PROJECT_ROOT
        parts = []

        # Mode: NONE - just identity line
        if context.prompt_mode == PromptMode.NONE:
            return FALLBACK_IDENTITY

        sections_config = self.config.get("sections", {})

        # 1. Core identity from PERSONA.md (always allowed for all session types)
        if sections_config.get("soul", True) and self._is_file_allowed("PERSONA.md", context):
            persona = self._read_workspace_file("PERSONA.md", workspace)
            if persona:
                parts.append(persona)
            else:
                # Fallback if workspace not bootstrapped
                parts.append(FALLBACK_IDENTITY)

        # 2. Identity customizations (only for main sessions)
        if sections_config.get("identity", True) and self._is_file_allowed("IDENTITY.md", context):
            identity = self._read_workspace_file("IDENTITY.md", workspace)
            if identity:
                parts.append(identity)

        # Mode: MINIMAL - stop here (core identity + safety only)
        if context.prompt_mode == PromptMode.MINIMAL:
            # For subagent/heartbeat/cron, also include AGENTS.md before stopping
            if self._is_file_allowed("AGENTS.md", context):
                agents = self._read_workspace_file("AGENTS.md", workspace)
                if agents:
                    parts.append(agents)

            # Add heartbeat config for heartbeat sessions
            if context.session_type == SessionType.HEARTBEAT and self._is_file_allowed("HEARTBEAT.md", context):
                heartbeat = self._read_workspace_file("HEARTBEAT.md", workspace)
                if heartbeat:
                    parts.append(f"## Heartbeat Tasks\n\n{heartbeat}")

            parts.append(self._build_safety_section())
            return self._finalize(parts)

        # 3. User context (only for main sessions with USER.md in allowlist)
        if sections_config.get("user", True) and self._is_file_allowed("USER.md", context):
            user = self._read_workspace_file("USER.md", workspace)
            if user:
                parts.append(f"## About the User\n\n{user}")

        # 4. Operational guidelines
        if sections_config.get("agents", True) and self._is_file_allowed("AGENTS.md", context):
            agents = self._read_workspace_file("AGENTS.md", workspace)
            if agents:
                parts.append(agents)

        # 5. Environment notes (only for main sessions)
        if sections_config.get("tools", True) and self._is_file_allowed("ENV.md", context):
            env = self._read_workspace_file("ENV.md", workspace)
            if env:
                parts.append(f"## Environment Notes\n\n{env}")

        # 6. Heartbeat config (only for heartbeat sessions in FULL mode)
        if context.session_type == SessionType.HEARTBEAT and self._is_file_allowed("HEARTBEAT.md", context):
            heartbeat = self._read_workspace_file("HEARTBEAT.md", workspace)
            if heartbeat:
                parts.append(f"## Heartbeat Tasks\n\n{heartbeat}")

        # 7. Safety guardrails
        if sections_config.get("safety", True):
            parts.append(self._build_safety_section())

        # 8. Temporal context
        if sections_config.get("temporal", True):
            parts.append(self._build_temporal_section(context))

        # 9. Setup context — inject missing field info for LLM-driven onboarding
        if context.session_type == SessionType.MAIN:
            try:
                from tools.setup.wizard import get_missing_setup_fields

                missing = get_missing_setup_fields()
                if missing:
                    setup_section = "## Setup Required\n\nThe following settings need to be collected from the user:\n"
                    for fld in missing:
                        setup_section += f"- {fld['label']} ({fld['field']}): {fld.get('description', '')}\n"
                    setup_section += (
                        "\nUse `dexai_show_control` to present each field with appropriate controls.\n"
                        "Use `dexai_save_setup_value` to persist each answer.\n"
                        "Ask for ONE field at a time to keep things simple.\n"
                    )
                    parts.append(setup_section)
            except Exception:
                pass

        # 10. Channel-specific rules (only for main sessions on messaging channels)
        if sections_config.get("channel_rules", True) and context.channel != "direct":
            if context.session_type == SessionType.MAIN:
                channel_rules = self._build_channel_rules(context.channel)
                if channel_rules:
                    parts.append(channel_rules)

        return self._finalize(parts)

    def _build_safety_section(self) -> str:
        """Build the safety guardrails section."""
        return """## Safety Guidelines

- Never exfiltrate private user data
- Confirm before external actions (emails, posts, API calls)
- Prefer recoverable actions (trash > delete)
- When uncertain, ask before acting"""

    def _build_temporal_section(self, context: PromptContext) -> str:
        """Build the temporal context section."""
        time_str = context.current_time or datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"""## Current Context

- Timezone: {context.timezone}
- Current time: {time_str}"""

    def _build_channel_rules(self, channel: str) -> Optional[str]:
        """
        Build channel-specific formatting rules.

        Args:
            channel: Channel identifier (telegram, discord, slack, etc.)

        Returns:
            Channel rules section or None if no specific rules
        """
        rules = {
            "telegram": "Keep responses concise. Markdown works but keep it simple. No tables.",
            "discord": "Use Discord formatting. Wrap links in <> to suppress embeds. No markdown tables.",
            "slack": "Use Slack-compatible formatting. Prefer bullet lists over tables.",
        }

        if channel in rules:
            return f"## Channel Rules ({channel})\n\n{rules[channel]}"
        return None

    def _finalize(self, parts: list[str]) -> str:
        """
        Finalize the prompt by joining parts and enforcing limits.

        Args:
            parts: List of prompt sections

        Returns:
            Final prompt string
        """
        result = "\n\n".join(filter(None, parts))

        # Enforce total length limit
        if len(result) > MAX_TOTAL_CHARS:
            result = result[:MAX_TOTAL_CHARS] + "\n[... prompt truncated ...]"

        return result


# =============================================================================
# Convenience Functions
# =============================================================================


def build_prompt(
    user_id: str,
    channel: str = "direct",
    session_type: str = "main",
    prompt_mode: Optional[str] = None,
    workspace: Optional[Path] = None,
) -> str:
    """
    Convenience function to build a system prompt.

    Args:
        user_id: User identifier
        channel: Communication channel (direct, telegram, discord, slack)
        session_type: Session type (main, subagent, heartbeat, cron)
        prompt_mode: Prompt mode override (full, minimal, none). If None, uses session default.
        workspace: Optional workspace root (default: PROJECT_ROOT)

    Returns:
        System prompt string
    """
    builder = SystemPromptBuilder()
    context = PromptContext(
        user_id=user_id,
        session_type=SessionType(session_type),
        prompt_mode=PromptMode(prompt_mode) if prompt_mode else None,
        channel=channel,
        workspace_root=workspace,
    )
    return builder.build(context)


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing."""
    import argparse

    parser = argparse.ArgumentParser(description="DexAI System Prompt Builder")
    parser.add_argument("--user", default="test_user", help="User ID")
    parser.add_argument("--channel", default="direct", help="Channel (direct, telegram, discord)")
    parser.add_argument("--session", default="main", choices=["main", "subagent", "heartbeat", "cron"],
                        help="Session type (controls which files are loaded)")
    parser.add_argument("--mode", choices=["full", "minimal", "none"],
                        help="Prompt mode override (default: based on session type)")
    parser.add_argument("--workspace", help="Workspace root path")
    parser.add_argument("--bootstrap", action="store_true", help="Bootstrap workspace with templates")
    parser.add_argument("--force", action="store_true", help="Force overwrite during bootstrap")
    parser.add_argument("--check", action="store_true", help="Check if workspace is bootstrapped")
    parser.add_argument("--show-allowlist", action="store_true", help="Show file allowlist for session type")

    args = parser.parse_args()

    workspace = Path(args.workspace) if args.workspace else PROJECT_ROOT

    if args.check:
        bootstrapped = is_workspace_bootstrapped(workspace)
        print(f"Workspace bootstrapped: {bootstrapped}")
        return

    if args.bootstrap:
        result = bootstrap_workspace(workspace, force=args.force)
        print(f"Bootstrap result: {result}")
        return

    if args.show_allowlist:
        session_type = SessionType(args.session)
        allowlist = SESSION_FILE_ALLOWLISTS.get(session_type, set())
        default_mode = SESSION_DEFAULT_PROMPT_MODE.get(session_type, PromptMode.FULL)
        print(f"Session type: {session_type.value}")
        print(f"Default prompt mode: {default_mode.value}")
        print(f"Allowed files: {sorted(allowlist)}")
        return

    # Build and display prompt
    prompt = build_prompt(
        user_id=args.user,
        channel=args.channel,
        session_type=args.session,
        prompt_mode=args.mode,
        workspace=workspace,
    )

    print(f"Session type: {args.session}")
    print(f"Prompt length: {len(prompt)} chars")
    print("=" * 60)
    print(prompt)


if __name__ == "__main__":
    main()
