"""
DexAI Task MCP Tools

Exposes DexAI's unique ADHD task features as MCP tools for the Claude Agent SDK.
These are the core differentiators - no other system has these.

Tools:
- dexai_task_decompose: Break vague tasks into concrete steps (LLM-powered)
- dexai_friction_check: Identify hidden blockers
- dexai_friction_solve: Pre-solve blockers before user hits them
- dexai_current_step: Get ONE next action (not a list!)
- dexai_energy_match: Match tasks to current energy level

Key Insight: "A list of five things is actually zero things for ADHD decision fatigue."

Usage:
    These tools are registered with the SDK via the agent configuration.
    The SDK agent invokes them as needed during conversations.
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Tool: dexai_task_decompose
# =============================================================================


def dexai_task_decompose(
    task: str,
    user_id: str = "default",
    depth: str = "shallow",
) -> dict[str, Any]:
    """
    Break a vague task into concrete, actionable steps using LLM.

    This is the core of the ADHD task engine. It takes overwhelming input
    like "do taxes" and breaks it into concrete steps like "find your
    income statement in email."

    Key insight: The decomposition itself requires executive function the
    user may not have. This does it proactively.

    Args:
        task: The vague task description (e.g., "do taxes", "plan birthday")
        user_id: User ID for context and storing the task
        depth: "shallow" (2-3 steps) or "full" (all steps up to 7)

    Returns:
        Dict with task ID and first step to start with

    Example:
        Input: "do taxes"
        Output: {
            "title": "File tax return",
            "first_step": "Find your income statement in your email",
            "total_steps": 5
        }
    """
    try:
        from tools.tasks import decompose

        result = decompose.decompose_task(
            raw_input=task,
            user_id=user_id,
            depth=depth,
        )

        if not result.get("success"):
            return {
                "success": False,
                "tool": "dexai_task_decompose",
                "error": result.get("error", "Decomposition failed"),
            }

        data = result.get("data", {})
        return {
            "success": True,
            "tool": "dexai_task_decompose",
            "task_id": data.get("task_id"),
            "title": data.get("title"),
            "total_steps": len(data.get("steps", [])),
            "first_step": data.get("steps", [{}])[0].get("description") if data.get("steps") else None,
            "steps": [
                {
                    "number": s.get("step_number"),
                    "description": s.get("description"),
                    "estimated_minutes": s.get("estimated_minutes"),
                    "friction_notes": s.get("friction_notes"),
                }
                for s in data.get("steps", [])
            ],
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_task_decompose",
            "error": f"Task decompose module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_task_decompose",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_friction_check
# =============================================================================


def dexai_friction_check(
    task_id: str | None = None,
    step_id: str | None = None,
    task_description: str | None = None,
) -> dict[str, Any]:
    """
    Identify hidden blockers that prevent starting or completing a task.

    Key insight: Often what blocks starting isn't the task but a prerequisite:
    - Needing a password
    - Needing to find a document
    - Needing to make a phone call (ADHD nightmare)
    - Needing to make a decision

    Args:
        task_id: Check friction for a specific task
        step_id: Check friction for a specific step
        task_description: Or provide task text to analyze

    Returns:
        Dict with identified friction points and suggested resolutions

    Example:
        Input: "Submit tax return"
        Output: {
            "friction_points": [
                {
                    "type": "password",
                    "description": "Need MyGov login credentials",
                    "suggested_resolution": "Check password manager"
                }
            ]
        }
    """
    try:
        from tools.tasks import friction_solver

        if task_id:
            result = friction_solver.identify_friction_for_task(task_id)
        elif step_id:
            result = friction_solver.identify_friction_for_step(step_id)
        elif task_description:
            result = friction_solver.identify_friction_from_text(task_description)
        else:
            return {
                "success": False,
                "tool": "dexai_friction_check",
                "error": "Must provide task_id, step_id, or task_description",
            }

        if not result.get("success"):
            return {
                "success": False,
                "tool": "dexai_friction_check",
                "error": result.get("error", "Friction check failed"),
            }

        friction_points = result.get("friction_points", [])
        return {
            "success": True,
            "tool": "dexai_friction_check",
            "count": len(friction_points),
            "friction_points": [
                {
                    "type": fp.get("type"),
                    "description": fp.get("description"),
                    "suggested_resolution": fp.get("suggested_resolution"),
                    "is_resolved": fp.get("is_resolved", False),
                }
                for fp in friction_points
            ],
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_friction_check",
            "error": f"Friction solver module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_friction_check",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_friction_solve
# =============================================================================


def dexai_friction_solve(
    friction_id: str,
    resolution: str,
    user_id: str = "default",
) -> dict[str, Any]:
    """
    Mark a friction point as resolved with the solution used.

    Pre-solving friction before the user hits it is key to ADHD task completion.

    Args:
        friction_id: The friction point ID to resolve
        resolution: How it was resolved (e.g., "Password found in vault")
        user_id: User resolving the friction

    Returns:
        Dict with success status
    """
    try:
        from tools.tasks import friction_solver

        result = friction_solver.resolve_friction(
            friction_id=friction_id,
            resolution=resolution,
            resolved_by=user_id,
        )

        return {
            "success": result.get("success", False),
            "tool": "dexai_friction_solve",
            "friction_id": friction_id,
            "resolution": resolution,
            "message": "Friction resolved" if result.get("success") else result.get("error"),
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_friction_solve",
            "error": f"Friction solver module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_friction_solve",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_current_step
# =============================================================================


def dexai_current_step(
    user_id: str = "default",
    task_id: str | None = None,
    energy_level: str | None = None,
) -> dict[str, Any]:
    """
    Get the SINGLE next action. No lists. No future steps. Just ONE thing.

    This is the core ADHD-friendly interface. When a user asks "what should
    I do?", they get exactly ONE actionable step with friction pre-solved.

    Key insight: "A list of five things is actually zero things for ADHD
    decision fatigue."

    Args:
        user_id: User to get step for
        task_id: Specific task (optional - otherwise picks highest priority)
        energy_level: Match to energy level ("low", "medium", "high")

    Returns:
        Dict with SINGLE current step and formatted instruction

    Example:
        Output: {
            "has_step": true,
            "instruction": "Find your income statement in your email",
            "friction_pre_solved": "Password is in your vault under 'ATO'",
            "estimated_minutes": 10
        }
    """
    try:
        from tools.tasks import current_step

        result = current_step.get_current_step(
            user_id=user_id,
            task_id=task_id,
            energy_level=energy_level,
        )

        if not result.get("success"):
            return {
                "success": False,
                "tool": "dexai_current_step",
                "error": result.get("error", "Could not get current step"),
            }

        data = result.get("data", {})

        if not data.get("has_step"):
            return {
                "success": True,
                "tool": "dexai_current_step",
                "has_step": False,
                "message": data.get("message", "No active tasks. What would you like to work on?"),
            }

        return {
            "success": True,
            "tool": "dexai_current_step",
            "has_step": True,
            "task_id": data.get("task_id"),
            "task_title": data.get("task_title"),
            "step_number": data.get("step_number"),
            "instruction": data.get("description"),
            "friction_pre_solved": data.get("friction_notes"),
            "estimated_minutes": data.get("estimated_minutes"),
            # ADHD-friendly formatted output
            "formatted": _format_current_step(data),
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_current_step",
            "error": f"Current step module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_current_step",
            "error": str(e),
        }


def _format_current_step(data: dict) -> str:
    """Format current step for ADHD-friendly display."""
    parts = []

    # Main instruction
    instruction = data.get("description", "")
    parts.append(instruction)

    # Friction notes (pre-solved)
    friction = data.get("friction_notes")
    if friction:
        parts.append(f"\n(Ready: {friction})")

    # Estimated time
    minutes = data.get("estimated_minutes")
    if minutes:
        parts.append(f"\n~{minutes} minutes")

    return "".join(parts)


# =============================================================================
# Tool: dexai_energy_match
# =============================================================================


def dexai_energy_match(
    user_id: str = "default",
    limit: int = 3,
) -> dict[str, Any]:
    """
    Get tasks matched to user's current energy level.

    ADHD users can't always power through. This matches available tasks
    to current capacity without requiring self-reporting.

    Args:
        user_id: User to match tasks for
        limit: Maximum suggestions (default 3, but still presents ONE first)

    Returns:
        Dict with energy estimate and matched tasks

    Example:
        Output: {
            "current_energy": "low",
            "confidence": 0.8,
            "best_match": {
                "task": "Archive old emails",
                "why": "Low-effort admin task perfect for low energy"
            },
            "alternatives": [...]
        }
    """
    try:
        from tools.learning import energy_tracker
        from tools.tasks import current_step

        # Get current energy estimate
        energy_result = energy_tracker.get_current_energy(user_id=user_id)

        if not energy_result.get("success"):
            # Fall back to medium if can't determine
            energy_level = "medium"
            confidence = 0.0
        else:
            energy_level = energy_result.get("energy_level", "medium")
            confidence = energy_result.get("confidence", 0.0)

        # Get tasks for this energy level
        step_result = current_step.get_current_step(
            user_id=user_id,
            energy_level=energy_level,
        )

        best_match = None
        if step_result.get("success") and step_result.get("data", {}).get("has_step"):
            data = step_result["data"]
            best_match = {
                "task_id": data.get("task_id"),
                "task_title": data.get("task_title"),
                "current_step": data.get("description"),
                "energy_level": energy_level,
            }

        return {
            "success": True,
            "tool": "dexai_energy_match",
            "current_energy": energy_level,
            "confidence": round(confidence, 2),
            "has_match": best_match is not None,
            "best_match": best_match,
            "message": _format_energy_match_message(energy_level, confidence, best_match),
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_energy_match",
            "error": f"Energy tracker module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_energy_match",
            "error": str(e),
        }


def _format_energy_match_message(
    energy: str, confidence: float, match: dict | None
) -> str:
    """Format energy match result for display."""
    if confidence < 0.5:
        energy_text = "I'm not sure about your current energy level"
    else:
        energy_labels = {
            "low": "Your energy seems low right now",
            "medium": "You're at moderate energy",
            "high": "You seem energized",
            "peak": "You're at peak energy - great for challenging tasks",
        }
        energy_text = energy_labels.get(energy, f"Energy level: {energy}")

    if match:
        task_text = f"Best match: {match.get('current_step', match.get('task_title', 'a task'))}"
        return f"{energy_text}. {task_text}"
    else:
        return f"{energy_text}. No tasks matched - what would you like to work on?"


# =============================================================================
# Tool Registry
# =============================================================================


TASK_TOOLS = {
    "dexai_task_decompose": {
        "function": dexai_task_decompose,
        "description": "Break vague tasks into concrete, actionable steps (LLM-powered)",
        "parameters": {
            "task": {"type": "string", "required": True},
            "depth": {"type": "string", "required": False, "default": "shallow"},
        },
    },
    "dexai_friction_check": {
        "function": dexai_friction_check,
        "description": "Identify hidden blockers preventing task completion",
        "parameters": {
            "task_id": {"type": "string", "required": False},
            "step_id": {"type": "string", "required": False},
            "task_description": {"type": "string", "required": False},
        },
    },
    "dexai_friction_solve": {
        "function": dexai_friction_solve,
        "description": "Mark a friction point as resolved",
        "parameters": {
            "friction_id": {"type": "string", "required": True},
            "resolution": {"type": "string", "required": True},
        },
    },
    "dexai_current_step": {
        "function": dexai_current_step,
        "description": "Get ONE next action - no lists, just one thing",
        "parameters": {
            "task_id": {"type": "string", "required": False},
            "energy_level": {"type": "string", "required": False},
        },
    },
    "dexai_energy_match": {
        "function": dexai_energy_match,
        "description": "Match tasks to current energy level",
        "parameters": {
            "limit": {"type": "integer", "required": False, "default": 3},
        },
    },
}


def get_tool(tool_name: str):
    """Get a tool function by name."""
    tool_info = TASK_TOOLS.get(tool_name)
    if tool_info:
        return tool_info["function"]
    return None


def list_tools() -> list[str]:
    """List all available task tools."""
    return list(TASK_TOOLS.keys())


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing task tools."""
    import argparse

    parser = argparse.ArgumentParser(description="DexAI Task MCP Tools")
    parser.add_argument("--tool", required=True, help="Tool to invoke")
    parser.add_argument("--args", help="JSON arguments")
    parser.add_argument("--list", action="store_true", help="List available tools")

    args = parser.parse_args()

    if args.list:
        print("Available task tools:")
        for name, info in TASK_TOOLS.items():
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
