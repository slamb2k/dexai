"""
DexAI Memory MCP Tools

Exposes DexAI's unique memory features as MCP tools for the Claude Agent SDK.
These tools wrap existing functionality so the SDK agent can invoke them.

Tools:
- dexai_memory_search: Hybrid semantic + keyword search
- dexai_memory_write: Write with importance and type
- dexai_commitments_add: Track a promise/commitment
- dexai_commitments_list: List active commitments
- dexai_context_capture: Snapshot current context
- dexai_context_resume: Generate "you were here" prompt

Usage:
    These tools are registered with the SDK via the agent configuration.
    The SDK agent invokes them as needed during conversations.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


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
    similarity (embeddings) for optimal retrieval.

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
    try:
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

        # Format for SDK response
        return {
            "success": True,
            "tool": "dexai_memory_search",
            "query": query,
            "method": result.get("method", method),
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

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_memory_search",
            "error": f"Memory search module not available: {e}",
        }
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
    try:
        from tools.memory import memory_write, memory_db

        # Validate entry type
        valid_types = ["fact", "preference", "event", "insight", "task", "relationship"]
        if entry_type not in valid_types:
            entry_type = "fact"

        # Clamp importance
        importance = max(1, min(10, importance))

        # Write to database
        result = memory_db.add_entry(
            entry_type=entry_type,
            content=content,
            source=source,
            importance=importance,
            tags=tags or [],
        )

        if result.get("success"):
            # Also log to daily log for visibility
            memory_write.append_to_daily_log(
                content=content,
                entry_type=entry_type,
                timestamp=True,
            )

        return {
            "success": result.get("success", False),
            "tool": "dexai_memory_write",
            "entry_id": result.get("id"),
            "entry_type": entry_type,
            "importance": importance,
            "message": f"Memory stored: {content[:50]}...",
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_memory_write",
            "error": f"Memory write module not available: {e}",
        }
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
    user_id: str = "default",
    source_channel: str = "agent",
) -> dict[str, Any]:
    """
    Track a commitment/promise made during conversation.

    ADHD-critical: Users often damage relationships through forgetting, not lack
    of caring. This tool tracks promises so nothing falls through the cracks.

    Args:
        content: What was promised (e.g., "Send Sarah the docs")
        target_person: Who the commitment is to (e.g., "Sarah")
        due_date: When it's due (ISO format or relative like "tomorrow")
        user_id: User making the commitment
        source_channel: Channel where commitment was made

    Returns:
        Dict with success status and commitment ID
    """
    try:
        from tools.memory import commitments

        result = commitments.add_commitment(
            user_id=user_id,
            content=content,
            target_person=target_person,
            due_date_str=due_date,
            source_channel=source_channel,
        )

        return {
            "success": result.get("success", False),
            "tool": "dexai_commitments_add",
            "commitment_id": result.get("id"),
            "target_person": target_person,
            "due_date": result.get("due_date"),
            "message": f"Commitment tracked: {content[:50]}...",
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_commitments_add",
            "error": f"Commitments module not available: {e}",
        }
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
    user_id: str = "default",
    status: str = "active",
    target_person: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """
    List commitments, optionally filtered by status or person.

    ADHD-friendly: Groups by target person for relationship context.
    Uses forward-facing language like "Sarah's waiting on..." not "overdue".

    Args:
        user_id: User whose commitments to list
        status: Filter by status (active, completed, cancelled, all)
        target_person: Filter by who the commitment is to
        limit: Maximum results

    Returns:
        Dict with success status and commitment list
    """
    try:
        from tools.memory import commitments

        if status == "all":
            result = commitments.get_all_commitments(user_id=user_id, limit=limit)
        else:
            result = commitments.get_active_commitments(user_id=user_id, limit=limit)

        commitment_list = result.get("commitments", [])

        # Filter by target person if specified
        if target_person:
            commitment_list = [
                c for c in commitment_list
                if c.get("target_person", "").lower() == target_person.lower()
            ]

        # Format with ADHD-friendly language
        formatted = []
        for c in commitment_list[:limit]:
            target = c.get("target_person", "someone")
            content = c.get("content", "")

            # ADHD-friendly framing
            if target:
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
            "commitments": formatted,
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_commitments_list",
            "error": f"Commitments module not available: {e}",
        }
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
    user_id: str = "default",
    trigger: str = "manual",
    active_file: str | None = None,
    last_action: str | None = None,
    next_step: str | None = None,
    channel: str = "agent",
) -> dict[str, Any]:
    """
    Capture current context for later resumption.

    ADHD-critical: Context switching costs ADHD brains 20-45 minutes to
    re-orient. This captures where the user was so they can pick up instantly.

    Args:
        user_id: User whose context to capture
        trigger: What caused the capture (switch, timeout, manual)
        active_file: Current file being worked on
        last_action: What was just completed
        next_step: What was about to be done
        channel: Channel where work was happening

    Returns:
        Dict with success status and snapshot ID
    """
    try:
        from tools.memory import context_capture

        result = context_capture.capture_context(
            user_id=user_id,
            trigger=trigger,
            active_file=active_file,
            last_action=last_action,
            next_step=next_step,
            channel=channel,
        )

        return {
            "success": result.get("success", False),
            "tool": "dexai_context_capture",
            "snapshot_id": result.get("id"),
            "trigger": trigger,
            "message": f"Context captured. Next step: {next_step or 'not specified'}",
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_context_capture",
            "error": f"Context capture module not available: {e}",
        }
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
    user_id: str = "default",
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """
    Generate a "you were here..." resumption prompt.

    ADHD-friendly: Uses forward-facing language like "Ready to pick up..."
    not "You abandoned...". Asks if stale contexts are still relevant.

    Args:
        user_id: User whose context to resume
        snapshot_id: Specific snapshot to resume (default: most recent)

    Returns:
        Dict with resumption prompt and suggested action
    """
    try:
        from tools.memory import context_resume

        result = context_resume.generate_resumption(
            user_id=user_id,
            snapshot_id=snapshot_id,
        )

        return {
            "success": result.get("success", False),
            "tool": "dexai_context_resume",
            "prompt": result.get("prompt"),
            "next_action": result.get("next_action"),
            "is_stale": result.get("is_stale", False),
            "snapshot_age_hours": result.get("age_hours"),
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_context_resume",
            "error": f"Context resume module not available: {e}",
        }
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
