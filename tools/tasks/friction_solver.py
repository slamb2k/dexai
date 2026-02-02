"""
Tool: Friction Solver
Purpose: Identify and pre-solve blockers before the user hits them

The key insight: Often what blocks starting isn't the task but a prerequisite:
- Needing a password
- Needing to find a document
- Needing to make a phone call (its own ADHD nightmare)
- Needing to make a decision

This tool surfaces and pre-solves these hidden blockers.

Usage:
    python tools/tasks/friction_solver.py --action identify --task-id abc123
    python tools/tasks/friction_solver.py --action identify --step-id step123
    python tools/tasks/friction_solver.py --action solve --friction-id f123 --resolution "Password saved in vault"
    python tools/tasks/friction_solver.py --action list --user alice --unresolved

Dependencies:
    - anthropic (optional, for LLM friction identification)
    - sqlite3 (stdlib)

Output:
    JSON result with friction points and suggested resolutions
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import CONFIG_PATH, FRICTION_TYPES, PROJECT_ROOT
from .manager import add_friction, get_connection, get_step, get_task, row_to_dict, generate_id


def load_config() -> Dict[str, Any]:
    """Load task engine configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_friction_prompt() -> str:
    """Load the friction identification hardprompt template."""
    prompt_path = PROJECT_ROOT / "hardprompts" / "tasks" / "friction_identification.md"
    if prompt_path.exists():
        with open(prompt_path) as f:
            return f.read()
    # Fallback prompt
    return """You are a friction identification assistant for people with ADHD.

Your job is to identify the HIDDEN BLOCKERS that prevent someone from starting or completing a task.

FRICTION TYPES:
- missing_info: Information needed before starting (login URL, account number, contact details)
- phone_call: A dreaded phone task (these deserve special attention for ADHD)
- decision: An unmade choice blocking progress (which option? what color? when?)
- password: Authentication required (login, 2FA, security questions)
- document: Need to find or create a document
- appointment: Need to schedule something with someone else

FOCUS ON PREREQUISITES, NOT THE TASK ITSELF.

For each friction point, suggest a resolution.

Output JSON format:
{
  "friction_points": [
    {
      "type": "password",
      "description": "Need MyGov login credentials",
      "suggested_resolution": "Check password manager or email for password reset"
    }
  ]
}
"""


def identify_friction_with_llm(task_title: str, step_description: Optional[str] = None) -> Dict[str, Any]:
    """
    Use LLM to identify friction points.

    Args:
        task_title: The task title
        step_description: Optional specific step to analyze

    Returns:
        dict with friction points
    """
    try:
        import anthropic
    except ImportError:
        return {
            "success": False,
            "error": "anthropic package not installed. Run: pip install anthropic",
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"success": False, "error": "ANTHROPIC_API_KEY not set"}

    config = load_config()
    model = config.get("task_engine", {}).get("decomposition", {}).get("llm_model", "claude-3-haiku-20240307")

    prompt = load_friction_prompt()

    context = f"Task: {task_title}"
    if step_description:
        context += f"\nCurrent step: {step_description}"

    client = anthropic.Anthropic(api_key=api_key)

    try:
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"{prompt}\n\n{context}\n\nRespond with valid JSON only.",
                }
            ],
        )

        response_text = message.content[0].text.strip()

        # Extract JSON from response
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        result = json.loads(response_text)

        # Validate friction types
        for fp in result.get("friction_points", []):
            if fp.get("type") not in FRICTION_TYPES:
                fp["type"] = "missing_info"  # Default

        return {"success": True, "data": result}

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse LLM response: {e}"}
    except Exception as e:
        return {"success": False, "error": f"LLM friction identification failed: {e}"}


def identify_friction_simple(task_title: str, step_description: Optional[str] = None) -> Dict[str, Any]:
    """
    Simple rule-based friction identification fallback.
    """
    friction_points = []
    text = f"{task_title} {step_description or ''}".lower()

    # Phone call detection
    if any(word in text for word in ["call", "phone", "ring", "contact"]):
        friction_points.append({
            "type": "phone_call",
            "description": "This involves a phone call",
            "suggested_resolution": "Write down key points before calling. Best times are usually 10-11am or 2-3pm.",
        })

    # Password/login detection
    if any(word in text for word in ["login", "log in", "sign in", "password", "account", "portal"]):
        friction_points.append({
            "type": "password",
            "description": "May need login credentials",
            "suggested_resolution": "Check password manager or browser saved passwords first",
        })

    # Document detection
    if any(word in text for word in ["document", "file", "form", "receipt", "certificate", "statement"]):
        friction_points.append({
            "type": "document",
            "description": "Need to find or prepare a document",
            "suggested_resolution": "Check recent downloads, email attachments, or common folders",
        })

    # Decision detection
    if any(word in text for word in ["choose", "decide", "which", "option", "select"]):
        friction_points.append({
            "type": "decision",
            "description": "A decision needs to be made first",
            "suggested_resolution": "Set a 5-minute timer - any reasonable choice beats endless deliberation",
        })

    # Appointment detection
    if any(word in text for word in ["book", "schedule", "appointment", "meeting", "reserve"]):
        friction_points.append({
            "type": "appointment",
            "description": "Need to schedule with someone else",
            "suggested_resolution": "Check calendar for available slots first, then reach out",
        })

    return {"success": True, "data": {"friction_points": friction_points}}


def identify_friction(
    task_id: Optional[str] = None,
    step_id: Optional[str] = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """
    Identify friction points for a task or step.

    Args:
        task_id: Task to analyze
        step_id: Specific step to analyze
        use_llm: Whether to use LLM

    Returns:
        dict with friction points
    """
    if not task_id and not step_id:
        return {"success": False, "error": "Must specify task_id or step_id"}

    # Get context
    task_title = ""
    step_description = None

    if step_id:
        step_result = get_step(step_id)
        if not step_result["success"]:
            return step_result
        step_description = step_result["data"]["description"]
        # Get task for context
        task_result = get_task(step_result["data"]["task_id"], include_steps=False)
        if task_result["success"]:
            task_title = task_result["data"]["title"]
    elif task_id:
        task_result = get_task(task_id)
        if not task_result["success"]:
            return task_result
        task_title = task_result["data"]["title"]
        # Optionally get current step
        if task_result["data"].get("current_step_id"):
            step_result = get_step(task_result["data"]["current_step_id"])
            if step_result["success"]:
                step_description = step_result["data"]["description"]

    # Identify friction
    if use_llm:
        result = identify_friction_with_llm(task_title, step_description)
        if not result["success"]:
            result = identify_friction_simple(task_title, step_description)
    else:
        result = identify_friction_simple(task_title, step_description)

    if not result["success"]:
        return result

    # Store friction points
    stored_friction = []
    for fp in result["data"].get("friction_points", []):
        friction_result = add_friction(
            friction_type=fp["type"],
            description=fp.get("description", ""),
            task_id=task_id,
            step_id=step_id,
        )
        if friction_result["success"]:
            friction_data = friction_result["data"]
            friction_data["suggested_resolution"] = fp.get("suggested_resolution")
            stored_friction.append(friction_data)

    return {
        "success": True,
        "data": {"friction_points": stored_friction},
        "message": f"Identified {len(stored_friction)} friction points",
    }


def solve_friction(friction_id: str, resolution: str) -> Dict[str, Any]:
    """
    Mark friction as solved with a resolution.

    Args:
        friction_id: Friction point to resolve
        resolution: How it was solved

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE task_friction
        SET resolved = 1, resolution = ?, resolved_at = ?
        WHERE id = ?
    """,
        (resolution, datetime.now().isoformat(), friction_id),
    )

    if cursor.rowcount == 0:
        conn.close()
        return {"success": False, "error": f"Friction point not found: {friction_id}"}

    conn.commit()

    cursor.execute("SELECT * FROM task_friction WHERE id = ?", (friction_id,))
    friction = row_to_dict(cursor.fetchone())

    conn.close()

    return {
        "success": True,
        "data": friction,
        "message": "Friction resolved",
    }


def list_friction(
    user_id: Optional[str] = None,
    task_id: Optional[str] = None,
    unresolved_only: bool = False,
    friction_type: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    List friction points with filters.

    Args:
        user_id: Filter by user
        task_id: Filter by task
        unresolved_only: Only show unresolved
        friction_type: Filter by type
        limit: Maximum results

    Returns:
        dict with friction list
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params: List[Any] = []

    if user_id:
        # Join with tasks to filter by user
        conditions.append("t.user_id = ?")
        params.append(user_id)

    if task_id:
        conditions.append("f.task_id = ?")
        params.append(task_id)

    if unresolved_only:
        conditions.append("f.resolved = 0")

    if friction_type:
        if friction_type not in FRICTION_TYPES:
            conn.close()
            return {"success": False, "error": f"Invalid friction type. Must be one of: {FRICTION_TYPES}"}
        conditions.append("f.friction_type = ?")
        params.append(friction_type)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT f.*, t.title as task_title
        FROM task_friction f
        LEFT JOIN tasks t ON f.task_id = t.id
        WHERE {where_clause}
        ORDER BY f.created_at DESC
        LIMIT ?
    """

    cursor.execute(query, params + [limit])
    friction_points = [row_to_dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "success": True,
        "data": {"friction_points": friction_points, "count": len(friction_points)},
    }


def get_friction(friction_id: str) -> Dict[str, Any]:
    """
    Get a specific friction point.

    Args:
        friction_id: Friction ID

    Returns:
        dict with friction data
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM task_friction WHERE id = ?", (friction_id,))
    friction = row_to_dict(cursor.fetchone())

    conn.close()

    if not friction:
        return {"success": False, "error": f"Friction point not found: {friction_id}"}

    return {"success": True, "data": friction}


def main():
    parser = argparse.ArgumentParser(
        description="Friction Solver - Identify and pre-solve task blockers"
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["identify", "solve", "list", "get"],
        help="Action to perform",
    )

    parser.add_argument("--task-id", help="Task ID")
    parser.add_argument("--step-id", help="Step ID")
    parser.add_argument("--friction-id", help="Friction point ID")
    parser.add_argument("--user", help="User ID")
    parser.add_argument("--resolution", help="How friction was resolved")
    parser.add_argument("--type", dest="friction_type", choices=FRICTION_TYPES, help="Filter by friction type")
    parser.add_argument("--unresolved", action="store_true", help="Only show unresolved friction")
    parser.add_argument("--no-llm", action="store_true", help="Use simple rule-based identification")
    parser.add_argument("--limit", type=int, default=50, help="Max results")

    args = parser.parse_args()
    result = None

    if args.action == "identify":
        if not args.task_id and not args.step_id:
            print(json.dumps({"success": False, "error": "--task-id or --step-id required"}))
            sys.exit(1)
        result = identify_friction(
            task_id=args.task_id,
            step_id=args.step_id,
            use_llm=not args.no_llm,
        )

    elif args.action == "solve":
        if not args.friction_id or not args.resolution:
            print(json.dumps({"success": False, "error": "--friction-id and --resolution required"}))
            sys.exit(1)
        result = solve_friction(args.friction_id, args.resolution)

    elif args.action == "list":
        result = list_friction(
            user_id=args.user,
            task_id=args.task_id,
            unresolved_only=args.unresolved,
            friction_type=args.friction_type,
            limit=args.limit,
        )

    elif args.action == "get":
        if not args.friction_id:
            print(json.dumps({"success": False, "error": "--friction-id required"}))
            sys.exit(1)
        result = get_friction(args.friction_id)

    if result:
        print(json.dumps(result, indent=2, default=str))
        if not result.get("success"):
            sys.exit(1)


if __name__ == "__main__":
    main()
