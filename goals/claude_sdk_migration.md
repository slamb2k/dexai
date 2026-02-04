# Claude Agent SDK Migration Assessment

## Executive Summary

DexAI has ~62,900 lines of code across 135 files. Analysis shows **~8,500-12,000 lines could be replaced or significantly simplified** by adopting Claude Agent SDK as the core agent runtime. The migration would take approximately **2-3 phases** and can be parallelized.

---

## 1. What Claude Agent SDK Provides (Free)

| Feature | SDK Provides | DexAI Current | Lines Saved |
|---------|--------------|---------------|-------------|
| **Agent Loop** | Built-in async loop with tool execution | `agent_handler.py` manual implementation | ~200 |
| **Built-in Tools** | Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, LS | `tools/system/fileops.py`, `executor.py` | ~1,500 |
| **Tool Permission Hooks** | PreToolUse, PostToolUse, Stop hooks | `tools/security/permissions.py` partially | ~300 |
| **MCP Integration** | Native in-process + external MCP servers | Not implemented | N/A (new capability) |
| **Cost Tracking** | `ResultMessage.total_cost_usd` | Not implemented | N/A (new capability) |
| **Multi-Agent** | `AgentDefinition` with different models/tools | Not implemented | N/A (new capability) |
| **Streaming** | Built-in async iteration | Manual in handlers | ~100 |
| **Sandboxing** | Built-in permission callbacks | `executor.py` allowlist | ~400 |

**Estimated Lines Replaceable: ~2,500 directly**

---

## 2. What DexAI Has That SDK Does NOT Provide

These components are **unique to DexAI** and must be retained:

| Component | Purpose | Lines | Keep? |
|-----------|---------|-------|-------|
| **Channel Adapters** | Telegram, Discord, Slack integration | 1,994 | ✅ Keep |
| **Message Router** | Cross-channel routing, security pipeline | 650 | ✅ Keep (simplified) |
| **Unified Inbox** | Cross-platform message storage, user linking | 1,071 | ✅ Keep |
| **RBAC System** | 5-tier role hierarchy, permission checks | 679 | ⚠️ Partial (SDK has hooks) |
| **Audit Logging** | Append-only security event log | 528 | ✅ Keep |
| **Rate Limiting** | Token bucket per user | 560 | ⚠️ Partial (can use SDK hooks) |
| **Session Management** | Cross-channel sessions | 561 | ✅ Keep |
| **Vault (Secrets)** | AES-256-GCM encrypted storage | 483 | ✅ Keep |
| **Task Decomposition** | ADHD-friendly task breakdown | 2,298 | ✅ Keep |
| **Memory System** | Persistent memory, semantic search | 5,319 | ✅ Keep |
| **Automation Engine** | Scheduler, triggers, notifications | 5,588 | ✅ Keep |
| **Learning System** | Energy tracking, patterns | 2,439 | ✅ Keep |
| **ADHD Communication** | RSD-safe language, brevity | 1,128 | ✅ Keep |
| **Office Integration** | Email, calendar, automation | 20,573 | ✅ Keep |
| **Dashboard** | FastAPI + Next.js frontend | 6,501 | ✅ Keep |
| **Mobile/Push** | Expo app, push notifications | 6,069 | ✅ Keep |

---

## 3. Components to REMOVE or SIMPLIFY

### 3.1 Remove Entirely (~2,000 lines)

| File | Lines | Reason |
|------|-------|--------|
| `tools/system/fileops.py` | 737 | SDK has Read, Write, Edit, Glob |
| `tools/system/executor.py` | 740 | SDK has Bash with sandboxing |
| `tools/channels/ai_handler.py` | 204 | Replaced by SDK agent |
| `tools/channels/agent_handler.py` | 167 | Rewrite to use SDK properly |
| `tools/system/browser.py` | 726 | Keep but optional (SDK has WebFetch) |

### 3.2 Simplify Significantly (~1,500 lines reduced)

| File | Current | After | Savings |
|------|---------|-------|---------|
| `tools/security/permissions.py` | 679 | ~300 | ~380 |
| `tools/security/sanitizer.py` | 377 | ~150 | ~227 |
| `tools/channels/router.py` | 650 | ~400 | ~250 |

**Security can use SDK's `can_use_tool` callback instead of custom pipeline.**

---

## 4. Migration Architecture

### Current Architecture
```
Telegram → Adapter → Router → Security Pipeline → ai/agent_handler → Claude API
                                    ↓
                              Manual tool execution
```

### Target Architecture
```
Telegram → Adapter → Router → SDK Agent Session
                                    ↓
                              ClaudeSDKClient
                                    ↓
                              Built-in tools + Custom MCP tools
                                    ↓
                              PreToolUse hooks (security)
```

### Key Changes

1. **Replace `agent_handler.py`** with proper SDK integration
2. **Move security checks** to SDK's `can_use_tool` callback
3. **Register custom tools** as MCP servers for DexAI-specific functionality
4. **Remove redundant** fileops.py, executor.py implementations
5. **Keep channel adapters** - SDK doesn't handle Telegram/Discord/Slack

---

## 5. Custom MCP Tools to Create

DexAI-specific tools that should be exposed to the agent via MCP:

| Tool Name | Purpose | Wraps |
|-----------|---------|-------|
| `dexai_memory_read` | Read from persistent memory | `tools/memory/memory_db.py` |
| `dexai_memory_write` | Write to persistent memory | `tools/memory/memory_db.py` |
| `dexai_memory_search` | Semantic memory search | `tools/memory/hybrid_search.py` |
| `dexai_task_create` | Create ADHD-friendly task | `tools/tasks/manager.py` |
| `dexai_task_decompose` | Break task into steps | `tools/tasks/decompose.py` |
| `dexai_task_current` | Get next single action | `tools/tasks/current_step.py` |
| `dexai_schedule` | Schedule a job | `tools/automation/scheduler.py` |
| `dexai_notify` | Send notification | `tools/automation/notify.py` |
| `dexai_email_read` | Read emails | `tools/office/email/reader.py` |
| `dexai_email_draft` | Create email draft | `tools/office/email/draft_manager.py` |
| `dexai_calendar` | Calendar operations | `tools/office/calendar/` |
| `dexai_vault_get` | Get secret from vault | `tools/security/vault.py` |

---

## 6. Detailed Migration Plan

### Phase 1: Core SDK Integration (Can Start Immediately)

**Duration: 1-2 days**
**Parallelizable: No (foundation)**

#### Tasks:

1. **Create SDK wrapper module** (`tools/agent/sdk_client.py`)
   - Initialize ClaudeSDKClient with DexAI defaults
   - Configure working directory
   - Set up system prompt from args/agent.yaml

2. **Implement permission callback** (`tools/agent/permissions.py`)
   - Port RBAC checks to `can_use_tool` callback
   - Map DexAI permissions to SDK tool names
   - Integrate audit logging

3. **Create new agent handler** (`tools/channels/sdk_handler.py`)
   - Replace agent_handler.py
   - Use ClaudeSDKClient for queries
   - Handle streaming responses
   - Store messages in inbox

4. **Update telegram_adapter.py**
   - Switch from agent_handler to sdk_handler

#### Deliverables:
- [ ] `tools/agent/__init__.py`
- [ ] `tools/agent/sdk_client.py`
- [ ] `tools/agent/permissions.py`
- [ ] `tools/channels/sdk_handler.py`
- [ ] Updated `tools/channels/telegram_adapter.py`

---

### Phase 2: Custom MCP Tools (Parallelizable)

**Duration: 2-3 days**
**Parallelizable: Yes (each tool independent)**

Split into parallel workstreams:

#### 2A: Memory Tools (1 developer)
```python
# tools/agent/mcp/memory_tools.py
@tool("dexai_memory_read", "Read from persistent memory", {...})
@tool("dexai_memory_write", "Write to persistent memory", {...})
@tool("dexai_memory_search", "Search memory semantically", {...})
```

#### 2B: Task Tools (1 developer)
```python
# tools/agent/mcp/task_tools.py
@tool("dexai_task_create", "Create a new task", {...})
@tool("dexai_task_decompose", "Break task into ADHD-friendly steps", {...})
@tool("dexai_task_current", "Get the single next action", {...})
@tool("dexai_task_complete", "Mark step/task complete", {...})
```

#### 2C: Automation Tools (1 developer)
```python
# tools/agent/mcp/automation_tools.py
@tool("dexai_schedule", "Schedule a future job", {...})
@tool("dexai_notify", "Send a notification", {...})
@tool("dexai_reminder", "Set a reminder", {...})
```

#### 2D: Office Tools (1 developer)
```python
# tools/agent/mcp/office_tools.py
@tool("dexai_email_read", "Read emails", {...})
@tool("dexai_email_draft", "Create email draft", {...})
@tool("dexai_email_send", "Send email (with approval)", {...})
@tool("dexai_calendar_view", "View calendar", {...})
@tool("dexai_calendar_create", "Create calendar event", {...})
```

#### Deliverables:
- [ ] `tools/agent/mcp/__init__.py`
- [ ] `tools/agent/mcp/memory_tools.py`
- [ ] `tools/agent/mcp/task_tools.py`
- [ ] `tools/agent/mcp/automation_tools.py`
- [ ] `tools/agent/mcp/office_tools.py`

---

### Phase 3: Cleanup & Optimization (After Phase 1+2)

**Duration: 1-2 days**
**Parallelizable: Partially**

#### 3A: Remove Redundant Code
- [ ] Delete `tools/system/fileops.py` (SDK has Read/Write/Edit)
- [ ] Delete `tools/system/executor.py` (SDK has Bash)
- [ ] Delete `tools/channels/ai_handler.py` (replaced)
- [ ] Delete `tools/channels/agent_handler.py` (replaced)
- [ ] Archive `tools/system/browser.py` (optional, SDK has WebFetch)

#### 3B: Simplify Security Pipeline
- [ ] Remove redundant checks from router.py (SDK handles tool permissions)
- [ ] Simplify sanitizer.py (SDK handles input validation)
- [ ] Update permissions.py to focus on user-level permissions only

#### 3C: Update Documentation
- [ ] Update `tools/manifest.md` with new MCP tools
- [ ] Update `CLAUDE.md` with SDK integration notes
- [ ] Create `goals/phase_sdk_migration.md` completion report

#### 3D: Testing
- [ ] Test all MCP tools individually
- [ ] Test end-to-end Telegram → SDK → Response flow
- [ ] Test permission denials
- [ ] Test audit logging
- [ ] Performance benchmarks

---

## 7. Parallel Execution Diagram

```
Week 1:
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: Core SDK Integration (BLOCKING - must complete)    │
│ - SDK wrapper, permissions callback, handler, adapter       │
└─────────────────────────────────────────────────────────────┘

Week 2:
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ 2A: Memory  │ │ 2B: Tasks   │ │ 2C: Auto    │ │ 2D: Office  │
│ Tools       │ │ Tools       │ │ Tools       │ │ Tools       │
│ (1 dev)     │ │ (1 dev)     │ │ (1 dev)     │ │ (1 dev)     │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
      ↓               ↓               ↓               ↓
      └───────────────┴───────────────┴───────────────┘
                              ↓
Week 3:
┌─────────────────────────────────────────────────────────────┐
│ Phase 3: Cleanup & Testing                                   │
│ - Remove redundant code, simplify security, documentation   │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| SDK breaking changes | High | Pin SDK version, monitor releases |
| Performance regression | Medium | Benchmark before/after |
| Permission gaps | High | Comprehensive testing of all tools |
| MCP tool errors | Medium | Error handling in each tool |
| Telegram rate limits | Low | Already handled in adapter |

---

## 9. Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Lines of code | ~62,900 | ~55,000-58,000 |
| Tool implementations | 4 custom | 0 custom (use SDK) |
| Security check locations | 5+ places | 1 (SDK callback) |
| Agent response latency | ~2-3s | ~1-2s (SDK optimized) |
| New capabilities | 0 | Multi-agent, cost tracking, MCP |

---

## 10. File Structure After Migration

```
tools/
├── agent/                    # NEW - SDK integration
│   ├── __init__.py
│   ├── sdk_client.py         # ClaudeSDKClient wrapper
│   ├── permissions.py        # can_use_tool callback
│   └── mcp/                   # Custom MCP tools
│       ├── __init__.py
│       ├── memory_tools.py
│       ├── task_tools.py
│       ├── automation_tools.py
│       └── office_tools.py
├── channels/
│   ├── sdk_handler.py        # NEW - replaces agent_handler
│   ├── telegram_adapter.py   # UPDATED
│   ├── discord.py            # UNCHANGED
│   ├── slack.py              # UNCHANGED
│   ├── router.py             # SIMPLIFIED
│   ├── inbox.py              # UNCHANGED
│   └── models.py             # UNCHANGED
├── security/
│   ├── permissions.py        # SIMPLIFIED (user-level only)
│   ├── audit.py              # UNCHANGED
│   ├── ratelimit.py          # SIMPLIFIED (use SDK)
│   ├── session.py            # UNCHANGED
│   ├── sanitizer.py          # SIMPLIFIED
│   └── vault.py              # UNCHANGED
├── system/
│   ├── fileops.py            # DELETED (SDK has Read/Write)
│   ├── executor.py           # DELETED (SDK has Bash)
│   ├── browser.py            # ARCHIVED (SDK has WebFetch)
│   └── network.py            # UNCHANGED
├── tasks/                    # UNCHANGED (exposed via MCP)
├── memory/                   # UNCHANGED (exposed via MCP)
├── automation/               # UNCHANGED (exposed via MCP)
├── office/                   # UNCHANGED (exposed via MCP)
├── learning/                 # UNCHANGED
├── adhd/                     # UNCHANGED
├── dashboard/                # UNCHANGED
└── mobile/                   # UNCHANGED
```

---

## 11. Immediate Next Steps

1. **Create feature branch**: `feature/claude-sdk-migration`
2. **Install SDK**: `uv pip install claude-agent-sdk` ✅ Done
3. **Start Phase 1**: Create `tools/agent/` directory structure
4. **Implement sdk_client.py**: Basic wrapper with DexAI defaults
5. **Test**: Verify SDK works with Telegram adapter

---

## Appendix: Code Examples

### A. SDK Client Wrapper

```python
# tools/agent/sdk_client.py
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

def get_agent_options(user_id: str, user_permissions: list[str]) -> ClaudeAgentOptions:
    """Create agent options with DexAI-specific configuration."""

    # Determine allowed tools based on user permissions
    allowed_tools = ["Read", "Glob", "Grep", "LS"]

    if "tools:execute" in user_permissions or "*:*" in user_permissions:
        allowed_tools.extend(["Bash", "Write", "Edit"])

    if "network:request" in user_permissions or "*:*" in user_permissions:
        allowed_tools.extend(["WebSearch", "WebFetch"])

    # Add DexAI custom MCP tools
    allowed_tools.extend([
        "mcp__dexai__memory_read",
        "mcp__dexai__memory_write",
        "mcp__dexai__task_create",
        # ... etc
    ])

    return ClaudeAgentOptions(
        allowed_tools=allowed_tools,
        cwd=str(PROJECT_ROOT),
        mcp_servers={"dexai": get_dexai_mcp_server()},
        can_use_tool=permission_callback,
        system_prompt=load_system_prompt(),
    )
```

### B. Permission Callback

```python
# tools/agent/permissions.py
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from tools.security import audit, permissions

async def permission_callback(tool_name: str, input_data: dict, context) -> PermissionResultAllow | PermissionResultDeny:
    """DexAI permission callback for SDK tools."""

    user_id = context.get("user_id")

    # Check RBAC permission
    perm_check = permissions.check_permission(
        user_id=user_id,
        permission=f"tools:{tool_name.lower()}"
    )

    if not perm_check.get("allowed"):
        audit.log_event(
            event_type="security",
            action="tool_denied",
            user_id=user_id,
            details={"tool": tool_name, "reason": "permission_denied"}
        )
        return PermissionResultDeny(message=f"Permission denied for {tool_name}")

    # Log allowed tool use
    audit.log_event(
        event_type="tool_use",
        action=tool_name,
        user_id=user_id,
        status="allowed"
    )

    return PermissionResultAllow()
```

---

*Document created: 2026-02-04*
*Author: Claude (via DexAI)*
