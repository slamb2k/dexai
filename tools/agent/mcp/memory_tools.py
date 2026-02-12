"""
DexAI Memory MCP Tools

Exposes DexAI's unique memory features as MCP tools for the Claude Agent SDK.
These tools use MemoryService for provider-agnostic memory operations.

Tools:
- dexai_memory_search: Hybrid semantic + keyword search
- dexai_memory_write: Write with importance and type
- dexai_commitments_add: Track a promise/commitment
- dexai_commitments_list: List active commitments
- dexai_context_capture: Snapshot current context
- dexai_context_resume: Generate "you were here" prompt

Provider Support:
- Native (default): Local SQLite + hybrid search
- Mem0: Cloud or self-hosted graph memory
- Zep: Cloud or self-hosted temporal knowledge graph
- SimpleMem: Cloud-only semantic compression
- ClaudeMem: Local progressive disclosure

Usage:
    These tools are registered with the SDK via the agent configuration.
    The SDK agent invokes them as needed during conversations.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent.constants import OWNER_USER_ID

logger = logging.getLogger(__name__)

# Global service instance (lazy-initialized)
_memory_service = None


def _get_event_loop():
    """Get or create an event loop for async operations."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.new_event_loop()


def _run_async(coro):
    """Run an async coroutine from sync context."""
    loop = _get_event_loop()
    if loop.is_running():
        # We're in an async context, create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return loop.run_until_complete(coro)


async def _get_service():
    """Get the memory service instance (lazy init)."""
    global _memory_service
    if _memory_service is None:
        try:
            from tools.memory.service import MemoryService
            _memory_service = MemoryService()
            await _memory_service.initialize()
        except Exception as e:
            logger.warning(f"Failed to initialize MemoryService: {e}, using legacy mode")
            _memory_service = None
    return _memory_service


def _use_legacy_mode():
    """Check if we should use legacy direct imports."""
    # Use legacy mode if service fails to initialize
    return _memory_service is None


# =============================================================================
# Tool: dexai_memory_search
# =============================================================================


def dexai_memory_search(
    query: str,
    entry_type: str | None = None,
    limit: int = 10,
    method: str = "hybrid",
    bm25_weight: float = 0.7,
    semantic_weight: float = 0.3,
) -> dict[str, Any]:
    """
    Search memory using hybrid BM25 + semantic search.

    DexAI's unique feature: combines keyword matching (BM25) with semantic
    similarity (embeddings) for optimal retrieval. Works with any configured
    memory provider (native, Mem0, Zep, SimpleMem, ClaudeMem).

    Args:
        query: Search query (natural language)
        entry_type: Optional filter by type (fact, preference, event, insight)
        limit: Maximum results (default 10)
        method: "hybrid", "keyword", or "semantic"
        bm25_weight: Weight for keyword matching (default 0.7)
        semantic_weight: Weight for semantic similarity (default 0.3)

    Returns:
        Dict with success status and search results
    """
    async def _search():
        service = await _get_service()
        if service:
            from tools.memory.providers.base import MemoryType, SearchFilters

            # Build filters
            filters = None
            if entry_type:
                try:
                    filters = SearchFilters(types=[MemoryType(entry_type)])
                except ValueError:
                    pass

            results = await service.search(
                query=query,
                limit=limit,
                filters=filters,
                search_type=method,
            )

            return {
                "success": True,
                "tool": "dexai_memory_search",
                "query": query,
                "method": method,
                "provider": service.provider.name,
                "count": len(results),
                "results": [
                    {
                        "id": r.id,
                        "content": r.content,
                        "type": r.type.value if hasattr(r.type, 'value') else r.type,
                        "score": r.score,
                        "importance": r.importance,
                    }
                    for r in results
                ],
            }
        else:
            # Fallback to legacy direct import
            from tools.memory import hybrid_search

            result = hybrid_search.hybrid_search(
                query=query,
                entry_type=entry_type,
                limit=limit,
                bm25_weight=bm25_weight,
                semantic_weight=semantic_weight,
                semantic_only=(method == "semantic"),
                keyword_only=(method == "keyword"),
            )

            return {
                "success": True,
                "tool": "dexai_memory_search",
                "query": query,
                "method": result.get("method", method),
                "provider": "native (legacy)",
                "count": len(result.get("results", [])),
                "results": [
                    {
                        "id": r.get("id"),
                        "content": r.get("content"),
                        "type": r.get("type"),
                        "score": r.get("score"),
                        "importance": r.get("importance"),
                    }
                    for r in result.get("results", [])
                ],
            }

    try:
        return _run_async(_search())
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_memory_search",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_memory_write
# =============================================================================


def dexai_memory_write(
    content: str,
    entry_type: str = "fact",
    importance: int = 5,
    source: str = "agent",
    tags: list[str] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    Write a memory entry with importance and type classification.

    Works with any configured memory provider (native, Mem0, Zep, SimpleMem, ClaudeMem).

    Args:
        content: Memory content to store
        entry_type: Type of memory (fact, preference, event, insight, task, relationship)
        importance: Importance score 1-10 (higher = more important)
        source: Source of the memory (default: "agent")
        tags: Optional tags for categorization
        user_id: Optional user ID for user-specific memory

    Returns:
        Dict with success status and entry ID
    """
    # Validate entry type
    valid_types = ["fact", "preference", "event", "insight", "task", "relationship"]
    if entry_type not in valid_types:
        entry_type = "fact"

    # Clamp importance
    importance = max(1, min(10, importance))

    async def _write():
        service = await _get_service()
        if service:
            from tools.memory.providers.base import MemoryType, MemorySource

            entry_id = await service.add(
                content=content,
                type=MemoryType(entry_type),
                importance=importance,
                source=MemorySource(source) if source in ["user", "inferred", "session", "external", "system", "agent"] else MemorySource.AGENT,
                tags=tags,
                user_id=user_id,
            )

            return {
                "success": True,
                "tool": "dexai_memory_write",
                "entry_id": entry_id,
                "entry_type": entry_type,
                "importance": importance,
                "provider": service.provider.name,
                "message": f"Memory stored: {content[:50]}...",
            }
        else:
            # Fallback to legacy
            from tools.memory import memory_write, memory_db

            result = memory_db.add_entry(
                entry_type=entry_type,
                content=content,
                source=source,
                importance=importance,
                tags=tags or [],
            )

            if result.get("success"):
                memory_write.append_to_daily_log(
                    content=content,
                    entry_type=entry_type,
                    timestamp=True,
                )

            return {
                "success": result.get("success", False),
                "tool": "dexai_memory_write",
                "entry_id": result.get("entry", {}).get("id"),
                "entry_type": entry_type,
                "importance": importance,
                "provider": "native (legacy)",
                "message": f"Memory stored: {content[:50]}...",
            }

    try:
        return _run_async(_write())
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_memory_write",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_commitments_add
# =============================================================================


def dexai_commitments_add(
    content: str,
    target_person: str | None = None,
    due_date: str | None = None,
    user_id: str = OWNER_USER_ID,
    source_channel: str = "agent",
) -> dict[str, Any]:
    """
    Track a commitment/promise made during conversation.

    ADHD-critical: Users often damage relationships through forgetting, not lack
    of caring. This tool tracks promises so nothing falls through the cracks.

    Works with any configured memory provider.

    Args:
        content: What was promised (e.g., "Send Sarah the docs")
        target_person: Who the commitment is to (e.g., "Sarah")
        due_date: When it's due (ISO format or relative like "tomorrow")
        user_id: User making the commitment
        source_channel: Channel where commitment was made

    Returns:
        Dict with success status and commitment ID
    """
    async def _add():
        service = await _get_service()
        if service:
            # Parse due date if provided
            parsed_due = None
            if due_date:
                try:
                    parsed_due = datetime.fromisoformat(due_date)
                except ValueError:
                    # Try relative parsing
                    from tools.memory.commitments import parse_due_date
                    parsed_str = parse_due_date(due_date)
                    if parsed_str:
                        parsed_due = datetime.fromisoformat(parsed_str)

            commitment_id = await service.add_commitment(
                content=content,
                user_id=user_id,
                target_person=target_person,
                due_date=parsed_due,
                source_channel=source_channel,
            )

            return {
                "success": True,
                "tool": "dexai_commitments_add",
                "commitment_id": commitment_id,
                "target_person": target_person,
                "due_date": parsed_due.isoformat() if parsed_due else None,
                "provider": service.provider.name,
                "message": f"Commitment tracked: {content[:50]}...",
            }
        else:
            # Fallback to legacy
            from tools.memory import commitments

            result = commitments.add_commitment(
                user_id=user_id,
                content=content,
                target_person=target_person,
                due_date=due_date,
                source_channel=source_channel,
            )

            return {
                "success": result.get("success", False),
                "tool": "dexai_commitments_add",
                "commitment_id": result.get("data", {}).get("id"),
                "target_person": target_person,
                "due_date": result.get("data", {}).get("due_date"),
                "provider": "native (legacy)",
                "message": f"Commitment tracked: {content[:50]}...",
            }

    try:
        return _run_async(_add())
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_commitments_add",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_commitments_list
# =============================================================================


def dexai_commitments_list(
    user_id: str = OWNER_USER_ID,
    status: str = "active",
    target_person: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """
    List commitments, optionally filtered by status or person.

    ADHD-friendly: Groups by target person for relationship context.
    Uses forward-facing language like "Sarah's waiting on..." not "overdue".

    Works with any configured memory provider.

    Args:
        user_id: User whose commitments to list
        status: Filter by status (active, completed, cancelled, all)
        target_person: Filter by who the commitment is to
        limit: Maximum results

    Returns:
        Dict with success status and commitment list
    """
    async def _list():
        service = await _get_service()
        if service:
            commitments_list = await service.list_commitments(
                user_id=user_id,
                status=status,
                limit=limit,
            )

            # Filter by target person if specified
            if target_person:
                commitments_list = [
                    c for c in commitments_list
                    if (c.get("target_person") or "").lower() == target_person.lower()
                ]

            return {
                "success": True,
                "tool": "dexai_commitments_list",
                "count": len(commitments_list),
                "provider": service.provider.name,
                "commitments": commitments_list[:limit],
            }
        else:
            # Fallback to legacy
            from tools.memory import commitments

            result = commitments.list_commitments(user_id=user_id, status=status, limit=limit)
            commitment_list = result.get("data", {}).get("commitments", [])

            # Filter by target person if specified
            if target_person:
                commitment_list = [
                    c for c in commitment_list
                    if (c.get("target_person") or "").lower() == target_person.lower()
                ]

            # Format with ADHD-friendly language
            formatted = []
            for c in commitment_list[:limit]:
                target = c.get("target_person", "someone")
                content = c.get("content", "")

                if target and target != "someone":
                    friendly = f"{target} is waiting on: {content}"
                else:
                    friendly = f"You mentioned: {content}"

                formatted.append({
                    "id": c.get("id"),
                    "content": content,
                    "target_person": target,
                    "due_date": c.get("due_date"),
                    "status": c.get("status"),
                    "friendly_description": friendly,
                })

            return {
                "success": True,
                "tool": "dexai_commitments_list",
                "count": len(formatted),
                "provider": "native (legacy)",
                "commitments": formatted,
            }

    try:
        return _run_async(_list())
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_commitments_list",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_context_capture
# =============================================================================


def dexai_context_capture(
    user_id: str = OWNER_USER_ID,
    trigger: str = "manual",
    active_file: str | None = None,
    last_action: str | None = None,
    next_step: str | None = None,
    channel: str = "agent",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Capture current context for later resumption.

    ADHD-critical: Context switching costs ADHD brains 20-45 minutes to
    re-orient. This captures where the user was so they can pick up instantly.

    Works with any configured memory provider.

    Args:
        user_id: User whose context to capture
        trigger: What caused the capture (switch, timeout, manual)
        active_file: Current file being worked on
        last_action: What was just completed
        next_step: What was about to be done
        channel: Channel where work was happening
        metadata: Additional metadata to store

    Returns:
        Dict with success status and snapshot ID
    """
    async def _capture():
        service = await _get_service()
        if service:
            # Build state dict from parameters
            state = {
                "active_file": active_file,
                "last_action": last_action,
                "next_step": next_step,
                "channel": channel,
                "metadata": metadata,
            }

            snapshot_id = await service.capture_context(
                user_id=user_id,
                state=state,
                trigger=trigger,
                summary=next_step,
            )

            return {
                "success": True,
                "tool": "dexai_context_capture",
                "snapshot_id": snapshot_id,
                "trigger": trigger,
                "provider": service.provider.name,
                "message": f"Context captured. Next step: {next_step or 'not specified'}",
            }
        else:
            # Fallback to legacy
            from tools.memory import context_capture

            result = context_capture.capture_context(
                user_id=user_id,
                trigger=trigger,
                active_file=active_file,
                last_action=last_action,
                next_step=next_step,
                channel=channel,
                metadata=metadata,
            )

            return {
                "success": result.get("success", False),
                "tool": "dexai_context_capture",
                "snapshot_id": result.get("data", {}).get("id"),
                "trigger": trigger,
                "provider": "native (legacy)",
                "message": f"Context captured. Next step: {next_step or 'not specified'}",
            }

    try:
        return _run_async(_capture())
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_context_capture",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_context_resume
# =============================================================================


def dexai_context_resume(
    user_id: str = OWNER_USER_ID,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """
    Generate a "you were here..." resumption prompt.

    ADHD-friendly: Uses forward-facing language like "Ready to pick up..."
    not "You abandoned...". Asks if stale contexts are still relevant.

    Works with any configured memory provider.

    Args:
        user_id: User whose context to resume
        snapshot_id: Specific snapshot to resume (default: most recent)

    Returns:
        Dict with resumption prompt and suggested action
    """
    async def _resume():
        service = await _get_service()
        if service:
            context_data = await service.resume_context(
                user_id=user_id,
                snapshot_id=snapshot_id,
            )

            if context_data:
                # Calculate staleness
                from datetime import datetime, timezone
                is_stale = False
                age_hours = 0
                if context_data.get("captured_at"):
                    try:
                        captured = datetime.fromisoformat(context_data["captured_at"].replace("Z", "+00:00"))
                        now = datetime.now(timezone.utc)
                        age_hours = (now - captured).total_seconds() / 3600
                        is_stale = age_hours > 24
                    except (ValueError, TypeError):
                        pass

                # Build ADHD-friendly resumption prompt
                next_step = context_data.get("next_step") or context_data.get("summary")
                active_file = context_data.get("active_file")

                if is_stale:
                    prompt = f"You had something in progress (it's been a while). Still relevant? Next step was: {next_step or 'not recorded'}"
                else:
                    prompt = f"Ready to pick up where you left off. Next step: {next_step or 'not recorded'}"

                if active_file:
                    prompt += f" (working on: {active_file})"

                return {
                    "success": True,
                    "tool": "dexai_context_resume",
                    "prompt": prompt,
                    "next_action": next_step,
                    "is_stale": is_stale,
                    "snapshot_age_hours": round(age_hours, 1),
                    "provider": service.provider.name,
                    "context": context_data,
                }
            else:
                return {
                    "success": True,
                    "tool": "dexai_context_resume",
                    "prompt": "No saved context found. Starting fresh.",
                    "next_action": None,
                    "is_stale": False,
                    "snapshot_age_hours": None,
                    "provider": service.provider.name,
                    "context": None,
                }
        else:
            # Fallback to legacy
            from tools.memory import context_resume

            result = context_resume.resume_context(
                user_id=user_id,
                snapshot_id=snapshot_id,
            )

            if result.get("success") and result.get("data"):
                data = result["data"]
                return {
                    "success": True,
                    "tool": "dexai_context_resume",
                    "prompt": data.get("prompt", "Ready to continue."),
                    "next_action": data.get("next_step"),
                    "is_stale": data.get("is_stale", False),
                    "snapshot_age_hours": data.get("age_hours"),
                    "provider": "native (legacy)",
                    "context": data,
                }
            else:
                return {
                    "success": True,
                    "tool": "dexai_context_resume",
                    "prompt": "No saved context found. Starting fresh.",
                    "next_action": None,
                    "is_stale": False,
                    "snapshot_age_hours": None,
                    "provider": "native (legacy)",
                    "context": None,
                }

    try:
        return _run_async(_resume())
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_context_resume",
            "error": str(e),
        }


# =============================================================================
# Tool Registry
# =============================================================================


MEMORY_TOOLS = {
    "dexai_memory_search": {
        "function": dexai_memory_search,
        "description": "Search memory using hybrid semantic + keyword search",
        "parameters": {
            "query": {"type": "string", "required": True},
            "entry_type": {"type": "string", "required": False},
            "limit": {"type": "integer", "required": False, "default": 10},
            "method": {"type": "string", "required": False, "default": "hybrid"},
        },
    },
    "dexai_memory_write": {
        "function": dexai_memory_write,
        "description": "Write a memory entry with importance classification",
        "parameters": {
            "content": {"type": "string", "required": True},
            "entry_type": {"type": "string", "required": False, "default": "fact"},
            "importance": {"type": "integer", "required": False, "default": 5},
        },
    },
    "dexai_commitments_add": {
        "function": dexai_commitments_add,
        "description": "Track a promise/commitment to prevent relationship damage",
        "parameters": {
            "content": {"type": "string", "required": True},
            "target_person": {"type": "string", "required": False},
            "due_date": {"type": "string", "required": False},
        },
    },
    "dexai_commitments_list": {
        "function": dexai_commitments_list,
        "description": "List active commitments with ADHD-friendly framing",
        "parameters": {
            "status": {"type": "string", "required": False, "default": "active"},
            "target_person": {"type": "string", "required": False},
        },
    },
    "dexai_context_capture": {
        "function": dexai_context_capture,
        "description": "Capture current context for later resumption",
        "parameters": {
            "trigger": {"type": "string", "required": False, "default": "manual"},
            "active_file": {"type": "string", "required": False},
            "last_action": {"type": "string", "required": False},
            "next_step": {"type": "string", "required": False},
        },
    },
    "dexai_context_resume": {
        "function": dexai_context_resume,
        "description": "Generate ADHD-friendly resumption prompt",
        "parameters": {
            "snapshot_id": {"type": "string", "required": False},
        },
    },
}


def get_tool(tool_name: str):
    """Get a tool function by name."""
    tool_info = MEMORY_TOOLS.get(tool_name)
    if tool_info:
        return tool_info["function"]
    return None


def list_tools() -> list[str]:
    """List all available memory tools."""
    return list(MEMORY_TOOLS.keys())


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing memory tools."""
    import argparse

    parser = argparse.ArgumentParser(description="DexAI Memory MCP Tools")
    parser.add_argument("--tool", required=True, help="Tool to invoke")
    parser.add_argument("--args", help="JSON arguments")
    parser.add_argument("--list", action="store_true", help="List available tools")

    args = parser.parse_args()

    if args.list:
        print("Available memory tools:")
        for name, info in MEMORY_TOOLS.items():
            print(f"  {name}: {info['description']}")
        return

    tool_func = get_tool(args.tool)
    if not tool_func:
        print(f"Unknown tool: {args.tool}")
        print(f"Available: {list_tools()}")
        sys.exit(1)

    # Parse arguments
    tool_args = {}
    if args.args:
        tool_args = json.loads(args.args)

    # Invoke tool
    result = tool_func(**tool_args)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
