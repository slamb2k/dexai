# Claude Agent SDK Alignment Review

> **Purpose**: Analyze DexAI's current SDK integration and identify opportunities to better leverage the Claude Agent SDK's capabilities.
>
> **Date**: 2026-02-08
> **Status**: Research Complete - Ready for Implementation Planning

---

## Executive Summary

DexAI has built a sophisticated wrapper around the Claude Agent SDK that adds ADHD-specific features, intelligent model routing, and multi-channel support. However, the current implementation predates several SDK features and uses custom solutions where native SDK capabilities now exist.

**Key Findings:**
1. **Permissions**: Custom RBAC system overlaps with SDK's `canUseTool` callback - opportunity to integrate
2. **Streaming**: Using basic streaming but not leveraging `ClaudeSDKClient` for continuous conversations
3. **User Input**: Not using `AskUserQuestion` tool for clarifying questions from users
4. **Sessions**: Custom session management instead of SDK's native session resumption
5. **Subagents**: Not using SDK's programmatic `agents` parameter
6. **Skills/Commands**: Not leveraging SDK's skill/command system
7. **Hooks**: Not using SDK hooks for pre/post tool execution
8. **Sandboxing**: No sandbox configuration for Bash commands

**Estimated Impact:**
- 40% reduction in custom code by adopting native SDK features
- Improved security through SDK's permission callbacks and sandboxing
- Better user experience with `AskUserQuestion` for clarifying prompts
- Simplified session management with SDK's native resumption

---

## Current Architecture Overview

### What DexAI Currently Implements

```
┌─────────────────────────────────────────────────────────────────┐
│                  DexAI Current Architecture                      │
└─────────────────────────────────────────────────────────────────┘

Channel Adapters (Telegram/Discord/Slack)
          ↓
Security Pipeline (router.py)
  - Sanitization
  - User Resolution
  - Rate Limiting
  - RBAC Permission Check ← Custom implementation
          ↓
sdk_handler (channels/sdk_handler.py)
  - Session Management ← Custom implementation
  - Streaming ← Basic streaming only
  - Fallback Logic
          ↓
DexAIClient (agent/sdk_client.py)
  - SystemPromptBuilder ← Custom implementation
  - Permission Callback ← Maps to custom RBAC
  - Model Router ← Custom implementation (valuable)
  - MCP Tools Registration ← Custom tools
          ↓
Claude Agent SDK
  - Tool execution
  - Streaming responses
          ↓
OpenRouter → Providers
```

### What the SDK Now Provides Natively

| Feature | DexAI Custom | SDK Native | Gap |
|---------|--------------|------------|-----|
| Permission callbacks | `create_permission_callback()` | `canUseTool` with `PermissionResultAllow/Deny` | **Partial overlap** |
| Session management | `SDKSession` class | `resume` parameter + `session_id` | **Can simplify** |
| Continuous conversation | Not implemented | `ClaudeSDKClient` class | **Missing** |
| User clarification | Not implemented | `AskUserQuestion` tool | **Missing** |
| Subagents | Not implemented | `agents` parameter | **Missing** |
| Skills | Not implemented | `.claude/skills/` + `Skill` tool | **Missing** |
| Slash commands | Not implemented | `.claude/commands/` | **Missing** |
| Pre/Post hooks | Not implemented | `hooks` parameter | **Missing** |
| Sandbox config | Not implemented | `sandbox` parameter | **Missing** |
| Streaming input | Not implemented | AsyncGenerator input | **Missing** |
| Structured output | Not implemented | `output_format` parameter | **Missing** |
| File checkpointing | Not implemented | `enable_file_checkpointing` | **Missing** |

---

## Detailed Gap Analysis

### 1. Permissions System

#### Current Implementation
```python
# tools/agent/permissions.py
async def create_permission_callback(user_id: str, config: dict):
    async def callback(tool_name: str, tool_input: dict) -> bool:
        # Maps SDK tools to DexAI permission strings
        permission = TOOL_TO_PERMISSION.get(tool_name)
        # Checks against custom RBAC system
        return check_permission(user_id, permission)
    return callback
```

#### SDK Native Capability
```python
# SDK's canUseTool with rich response types
async def can_use_tool(tool_name, input_data, context) -> PermissionResult:
    # Can ALLOW with modified input
    return PermissionResultAllow(updated_input={...})

    # Can DENY with explanation
    return PermissionResultDeny(
        message="User doesn't have permission",
        interrupt=True  # Stop execution
    )

    # Can access permission suggestions from SDK
    suggestions = context.suggestions  # SDK-provided suggestions
```

#### Recommendation
**Integrate, don't replace.** Keep DexAI's RBAC system but return proper `PermissionResult` objects:

```python
async def dexai_permission_callback(tool_name, input_data, context):
    # Use existing RBAC check
    if not check_permission(user_id, tool_name):
        return PermissionResultDeny(
            message=f"Permission denied: {tool_name} requires elevated access",
            interrupt=False  # Let Claude try alternative approach
        )

    # ADHD-safe: Auto-approve read-only tools
    if tool_name in READ_ONLY_TOOLS:
        return PermissionResultAllow(updated_input=input_data)

    # For write operations, could use AskUserQuestion for confirmation
    return PermissionResultAllow(updated_input=input_data)
```

---

### 2. Streaming & User Input

#### Current Implementation
```python
# Basic streaming - only yields text chunks
async for message in client.receive_response():
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                await send_chunk(block.text)
```

#### SDK Native Capabilities

**A. Streaming Input Mode (for dynamic conversations)**
```python
async def message_stream():
    yield {"type": "user", "message": {"role": "user", "content": "Initial prompt"}}
    # Wait for user to add more context
    await asyncio.sleep(5)
    yield {"type": "user", "message": {"role": "user", "content": "Additional info"}}

# SDK handles queued messages with interruption support
async for message in query(prompt=message_stream(), options=options):
    process(message)
```

**B. AskUserQuestion Tool (for clarifying questions)**
```python
# SDK's built-in tool for multi-choice clarification
async def can_use_tool(tool_name, input_data, context):
    if tool_name == "AskUserQuestion":
        # input_data contains Claude's generated questions
        questions = input_data.get("questions", [])
        # Display to user, collect answers
        answers = await display_questions_to_user(questions)
        return PermissionResultAllow(
            updated_input={"questions": questions, "answers": answers}
        )
```

**C. ClaudeSDKClient for Continuous Conversations**
```python
# SDK's client maintains conversation context
async with ClaudeSDKClient(options) as client:
    await client.query("What's my next task?")
    async for msg in client.receive_response():
        print(msg)

    # Follow-up - Claude remembers previous context!
    await client.query("Tell me more about that")
    async for msg in client.receive_response():
        print(msg)

    # Can interrupt long-running tasks
    await client.interrupt()
```

#### Recommendation
**High Priority.** Implement `AskUserQuestion` handling for ADHD-friendly clarification:

```python
# In canUseTool callback
if tool_name == "AskUserQuestion":
    # Format questions for ADHD users (numbered, clear, brief)
    questions = input_data.get("questions", [])
    formatted = format_for_adhd(questions)  # Apply RSD-safe language

    # Send to channel (Telegram, Discord, etc.)
    answers = await channel.ask_user(formatted)

    return PermissionResultAllow(
        updated_input={"questions": questions, "answers": answers}
    )
```

**Medium Priority.** Migrate to `ClaudeSDKClient` for session continuity:
```python
# Instead of creating new query() per message
# Maintain ClaudeSDKClient instances per user session
class UserSession:
    def __init__(self, user_id):
        self.client = ClaudeSDKClient(options)

    async def handle_message(self, message):
        await self.client.query(message)
        async for msg in self.client.receive_response():
            yield msg
```

---

### 3. Hosting & Sandboxing

#### Current Implementation
- No sandbox configuration
- Bash commands run with full system access
- Relies on permission checks to block dangerous operations

#### SDK Native Capability
```python
from claude_agent_sdk import ClaudeAgentOptions, SandboxSettings

sandbox_settings: SandboxSettings = {
    "enabled": True,
    "autoAllowBashIfSandboxed": True,  # Auto-approve bash in sandbox
    "excludedCommands": ["docker"],     # Always bypass sandbox
    "allowUnsandboxedCommands": False,  # Block escape requests
    "network": {
        "allowLocalBinding": True,      # For dev servers
        "allowUnixSockets": [],         # Restrict socket access
    }
}

options = ClaudeAgentOptions(
    sandbox=sandbox_settings,
    permission_mode="acceptEdits"  # Auto-approve file edits
)
```

#### Recommendation
**High Priority for Production.** Enable sandboxing for Bash commands:

```python
# In args/agent.yaml
sandbox:
  enabled: true
  auto_allow_bash_if_sandboxed: true
  network:
    allow_local_binding: true
  excluded_commands:
    - docker
    - git  # Trust git operations
```

This would:
1. Allow ADHD users to safely explore without dangerous command execution
2. Auto-approve sandboxed bash (faster, less friction)
3. Provide defense-in-depth beyond RBAC

---

### 4. Subagents

#### Current Implementation
- Uses SDK's built-in `Task` tool with `subagent_type`
- No custom agent definitions
- Relies on SDK's general-purpose agent

#### SDK Native Capability
```python
from claude_agent_sdk import AgentDefinition

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "Task"],
    agents={
        "code-reviewer": AgentDefinition(
            description="Expert code review for quality and security",
            prompt="You are a code review specialist...",
            tools=["Read", "Grep", "Glob"],  # Read-only
            model="sonnet"
        ),
        "task-decomposer": AgentDefinition(
            description="Break down vague tasks into concrete steps",
            prompt="You help ADHD users by breaking tasks into small steps...",
            tools=["Read", "Glob"],
            model="haiku"  # Fast, cheap for decomposition
        ),
        "friction-solver": AgentDefinition(
            description="Identify and pre-solve hidden blockers",
            prompt="You anticipate what might block task completion...",
            tools=["Read", "Grep", "Glob", "Bash"],
            model="sonnet"
        )
    }
)
```

#### Recommendation
**Medium Priority.** Define ADHD-specific subagents programmatically:

```python
# tools/agent/subagents.py
DEXAI_AGENTS = {
    "task-decomposer": AgentDefinition(
        description="Breaks vague tasks into concrete, one-thing steps. Use for ADHD task overwhelm.",
        prompt="""You help users with ADHD by:
1. Breaking tasks into 5-15 minute chunks
2. Identifying the ONE next physical action
3. Pre-solving hidden blockers
4. Using RSD-safe, encouraging language

Never give lists of 10 things. Give ONE thing to do now.""",
        tools=["Read", "Glob", "Grep"],
        model="haiku"  # Fast response for low-friction
    ),

    "energy-matcher": AgentDefinition(
        description="Matches tasks to current energy level. Use when user seems overwhelmed.",
        prompt="""You help match tasks to energy levels:
- LOW: Reading, organizing, simple edits
- MEDIUM: Code review, writing, debugging
- HIGH: Architecture, complex features, learning new tech

Ask about energy if unclear. Never suggest high-energy tasks to tired users.""",
        tools=["Read", "Glob"],
        model="haiku"
    ),

    "commitment-tracker": AgentDefinition(
        description="Tracks and surfaces promises/commitments. Use for accountability.",
        prompt="""You track what the user has committed to doing.
Surface commitments gently, never accusingly (RSD-safe).
Help prioritize which commitments to address first.""",
        tools=["Read"],
        model="haiku"
    )
}
```

Benefits:
- Moves MCP tool logic into cleaner subagent definitions
- SDK handles spawning, context isolation, and result aggregation
- Can use different models per subagent (haiku for simple tasks = cost savings)

---

### 5. Skills & Slash Commands

#### Current Implementation
- Not using SDK's skill system
- Custom MCP tools for ADHD features
- No slash command support

#### SDK Native Capability

**Skills** (`.claude/skills/SKILL.md`):
```markdown
---
name: ADHD Task Decomposition
description: Break down overwhelming tasks into manageable steps
---

When a user feels overwhelmed or mentions a task seems too big:

1. Acknowledge the feeling (RSD-safe)
2. Ask about current energy level
3. Break the task into 5-15 minute chunks
4. Identify the ONE next physical action
5. Offer to set a timer or reminder

Never give lists longer than 3 items at once.
```

**Slash Commands** (`.claude/commands/decompose.md`):
```markdown
---
description: Break down a task into ADHD-friendly steps
allowed-tools: Read, Glob
---

Break down the following task using ADHD-friendly principles:

$ARGUMENTS

Steps should be:
- 5-15 minutes each
- Single physical actions
- Include any prerequisites
```

#### Recommendation
**Medium Priority.** Create DexAI-specific skills and commands:

```bash
.claude/
├── skills/
│   ├── adhd-decomposition/
│   │   └── SKILL.md
│   ├── energy-matching/
│   │   └── SKILL.md
│   └── rsd-safe-communication/
│       └── SKILL.md
└── commands/
    ├── decompose.md      # /decompose <task>
    ├── energy.md         # /energy - check/set energy level
    ├── focus.md          # /focus - one-thing mode
    └── commitments.md    # /commitments - list active promises
```

Benefits:
- Users can invoke `/decompose` directly
- Skills auto-trigger when Claude detects relevant context
- Cleaner than MCP tools for behavior modifications
- Version-controlled with the project

---

### 6. Hooks System

#### Current Implementation
- No hook usage
- Security checks happen before SDK invocation
- No post-tool logging to SDK

#### SDK Native Capability
```python
from claude_agent_sdk import HookMatcher

async def audit_tool_use(input_data, tool_use_id, context):
    """Log all tool usage to DexAI audit system."""
    await audit_log.write({
        "tool": input_data["tool_name"],
        "input": sanitize(input_data["tool_input"]),
        "user_id": context.user_id,
        "timestamp": datetime.now()
    })
    return {}  # Allow to proceed

async def block_dangerous_patterns(input_data, tool_use_id, context):
    """Block dangerous bash patterns."""
    if input_data["tool_name"] == "Bash":
        command = input_data["tool_input"].get("command", "")
        for pattern in DANGEROUS_PATTERNS:
            if pattern in command:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Blocked: {pattern}"
                    }
                }
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(hooks=[block_dangerous_patterns]),
            HookMatcher(matcher="Write|Edit", hooks=[audit_tool_use])
        ],
        "PostToolUse": [
            HookMatcher(hooks=[audit_tool_use])
        ],
        "Stop": [
            HookMatcher(hooks=[save_session_state])
        ]
    }
)
```

#### Recommendation
**High Priority.** Migrate security checks to hooks:

```python
# tools/agent/hooks.py
DEXAI_HOOKS = {
    "PreToolUse": [
        HookMatcher(
            matcher="Bash",
            hooks=[block_dangerous_commands, audit_bash_use]
        ),
        HookMatcher(
            matcher="Write|Edit",
            hooks=[validate_file_path, audit_file_change]
        ),
        HookMatcher(hooks=[log_all_tool_use])  # Catch-all
    ],
    "PostToolUse": [
        HookMatcher(hooks=[record_to_dashboard])
    ],
    "SubagentStop": [
        HookMatcher(hooks=[aggregate_subagent_results])
    ],
    "Stop": [
        HookMatcher(hooks=[save_context_for_resume])
    ]
}
```

Benefits:
- Security logic runs at SDK level (defense in depth)
- Cleaner separation from business logic
- PostToolUse can capture actual results for auditing
- Stop hook can auto-save context (crucial for ADHD context recovery)

---

### 7. Session Management

#### Current Implementation
```python
class SDKSession:
    """Custom session tracking per user."""
    def __init__(self, user_id, channel):
        self.messages = []
        self.total_cost = 0.0
        self.message_count = 0

    async def query(self, message, channel):
        # Creates new query() each time
        result = await self._query_with_agent_sdk(message, channel)
        self.messages.append(result)
        return result
```

#### SDK Native Capability
```python
# SDK handles session internally
async for message in query(
    prompt="Initial task",
    options=ClaudeAgentOptions(allowed_tools=[...])
):
    if message.type == "system" and message.subtype == "init":
        session_id = message.session_id  # Capture for later
    if message.type == "result":
        print(message.result)

# Resume later with full context
async for message in query(
    prompt="Continue from where we left off",
    options=ClaudeAgentOptions(
        resume=session_id,  # SDK loads full history
        fork_session=False  # Continue same session
    )
):
    process(message)
```

#### Recommendation
**High Priority.** Simplify session management:

```python
# tools/channels/session_manager.py
class SessionManager:
    def __init__(self):
        self.sessions: dict[str, str] = {}  # user_id -> session_id

    async def get_or_create_session(self, user_id: str) -> ClaudeAgentOptions:
        session_id = self.sessions.get(user_id)

        if session_id:
            # Resume existing session
            return ClaudeAgentOptions(
                resume=session_id,
                # ... other options
            )
        else:
            # New session - will capture ID from init message
            return ClaudeAgentOptions(
                allowed_tools=[...],
                agents=DEXAI_AGENTS,
                hooks=DEXAI_HOOKS,
            )

    async def handle_message(self, user_id: str, message: str):
        options = await self.get_or_create_session(user_id)

        async for msg in query(prompt=message, options=options):
            if msg.type == "system" and msg.subtype == "init":
                self.sessions[user_id] = msg.session_id
            yield msg
```

Benefits:
- SDK handles context window management
- Automatic session compaction when needed
- Can fork sessions for "what if" explorations
- Session state persists across restarts

---

### 8. Structured Output

#### Current Implementation
- Returns plain text responses
- No JSON schema validation
- Manual parsing of structured data

#### SDK Native Capability
```python
options = ClaudeAgentOptions(
    output_format={
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "next_step": {"type": "string"},
                "estimated_minutes": {"type": "integer"},
                "energy_required": {"enum": ["low", "medium", "high"]},
                "blockers": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["next_step", "estimated_minutes"]
        }
    }
)

async for message in query(prompt="What should I do next?", options=options):
    if message.type == "result":
        structured = message.structured_output
        # Guaranteed to match schema
        print(f"Do: {structured['next_step']} ({structured['estimated_minutes']} min)")
```

#### Recommendation
**Low Priority.** Use for specific structured responses:

```python
TASK_DECOMPOSITION_SCHEMA = {
    "type": "object",
    "properties": {
        "current_step": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "duration_minutes": {"type": "integer"},
                "energy_level": {"enum": ["low", "medium", "high"]}
            }
        },
        "remaining_steps": {"type": "integer"},
        "blockers": {"type": "array", "items": {"type": "string"}}
    }
}
```

---

## Implementation Roadmap

### Phase 1: Quick Wins (1-2 days)

| Task | Impact | Effort |
|------|--------|--------|
| Add `AskUserQuestion` handling to `canUseTool` | High | Low |
| Enable sandbox configuration in `args/agent.yaml` | High | Low |
| Use SDK session resumption instead of custom tracking | Medium | Low |
| Add `Stop` hook for context saving | Medium | Low |

### Phase 2: Core Integration (3-5 days)

| Task | Impact | Effort |
|------|--------|--------|
| Define ADHD subagents via `agents` parameter | High | Medium |
| Migrate security checks to PreToolUse hooks | High | Medium |
| Migrate to `ClaudeSDKClient` for continuous conversations | Medium | Medium |
| Add PostToolUse hooks for dashboard logging | Medium | Low |

### Phase 3: Enhanced Features (5-7 days)

| Task | Impact | Effort |
|------|--------|--------|
| Create `.claude/skills/` for ADHD capabilities | Medium | Medium |
| Create `.claude/commands/` for user shortcuts | Medium | Low |
| Implement streaming input for dynamic conversations | Medium | Medium |
| Add structured output for task decomposition | Low | Low |

### Phase 4: Optimization (Ongoing)

| Task | Impact | Effort |
|------|--------|--------|
| Tune subagent model selection (haiku vs sonnet) | Medium | Low |
| Monitor and optimize hook performance | Low | Low |
| Refine skill/command definitions based on usage | Low | Ongoing |

---

## Code Migration Examples

### Before: Custom Permission Check

```python
# Current: tools/agent/permissions.py
async def create_permission_callback(user_id: str, config: dict):
    async def callback(tool_name: str, tool_input: dict) -> bool:
        permission = TOOL_TO_PERMISSION.get(tool_name, "unknown")
        allowed = await check_rbac(user_id, permission)
        if allowed:
            await audit_log(user_id, tool_name, tool_input)
        return allowed
    return callback
```

### After: SDK-Native with Rich Responses

```python
# New: tools/agent/permissions.py
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext
)

async def dexai_permission_callback(
    tool_name: str,
    input_data: dict,
    context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:

    # Handle AskUserQuestion specially
    if tool_name == "AskUserQuestion":
        answers = await handle_clarifying_question(input_data)
        return PermissionResultAllow(
            updated_input={**input_data, "answers": answers}
        )

    # Check RBAC
    permission = TOOL_TO_PERMISSION.get(tool_name, "unknown")
    if not await check_rbac(context.user_id, permission):
        return PermissionResultDeny(
            message=f"Permission denied for {tool_name}",
            interrupt=False  # Let Claude try alternatives
        )

    # Auto-approve read-only tools for low friction
    if tool_name in READ_ONLY_TOOLS:
        return PermissionResultAllow(updated_input=input_data)

    # For write operations, allow with original input
    return PermissionResultAllow(updated_input=input_data)
```

---

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Session migration | User loses context during transition | Run old/new in parallel, migrate gradually |
| Hook-based security | Hooks might not fire in edge cases | Keep RBAC as backup, defense-in-depth |
| Subagent adoption | Different behavior from MCP tools | A/B test, monitor user satisfaction |
| Sandbox enablement | Might break legitimate operations | Start with `allowUnsandboxedCommands: true` |

---

## Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Custom code lines | ~2000 | ~1200 | Code line count in tools/agent/ |
| Security check latency | ~50ms | ~20ms | Hooks vs RBAC lookup |
| Context recovery time | 20-45min | <5min | SDK session resume |
| User clarification rate | N/A | Track | AskUserQuestion usage |
| Subagent cost savings | N/A | 30%+ | Haiku vs Sonnet usage |

---

## Appendix: SDK Version Requirements

Current DexAI uses `claude-agent-sdk` (version from pyproject.toml).

Required features need:
- `canUseTool` callback with `PermissionResult` types
- `agents` parameter for programmatic subagents
- `hooks` parameter for lifecycle hooks
- `sandbox` parameter for command sandboxing
- `resume` parameter for session management
- `AskUserQuestion` tool support

Verify SDK version supports all features before implementation.

---

## Next Steps

1. **Review this document** with stakeholders
2. **Prioritize Phase 1** quick wins for immediate value
3. **Create implementation tickets** for each phase
4. **Set up metrics tracking** before changes
5. **Plan rollout strategy** (gradual, A/B, or big bang)

---

*Document created by Claude Opus 4.5 based on SDK documentation and codebase analysis.*
