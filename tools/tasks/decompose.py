"""
Tool: Task Decomposer
Purpose: Break vague tasks into concrete, actionable steps using LLM

This is the core of the ADHD task engine. It takes overwhelming input
like "do taxes" and breaks it into concrete steps like "find your
group certificate in your email."

Key insight: The decomposition itself requires executive function the
user may not have. This tool does it proactively.

Usage:
    python tools/tasks/decompose.py --action decompose --task "do taxes" --user alice
    python tools/tasks/decompose.py --action decompose --task "plan birthday party" --user alice --depth full
    python tools/tasks/decompose.py --action redecompose --task-id abc123

Dependencies:
    - anthropic (optional, for LLM decomposition)
    - sqlite3 (stdlib)

Output:
    JSON result with task and first step
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import ACTION_VERBS, CONFIG_PATH, DB_PATH, PROJECT_ROOT
from .manager import add_step, create_task, get_task, update_task


def load_config() -> Dict[str, Any]:
    """Load task engine configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_decomposition_prompt() -> str:
    """Load the decomposition hardprompt template."""
    prompt_path = PROJECT_ROOT / "hardprompts" / "tasks" / "decomposition.md"
    if prompt_path.exists():
        with open(prompt_path) as f:
            return f.read()
    # Fallback prompt if file doesn't exist
    return """You are a task decomposition assistant for people with ADHD.

Break down the given task into concrete, actionable steps.

RULES:
1. Each step must start with an action verb (find, send, call, open, write, review, submit, book, check, gather, download)
2. Each step should be completable in under 15 minutes
3. Maximum 7 steps (if more needed, it's a project, not a task)
4. No nested subtasks - keep everything flat
5. Consider common friction points (passwords, documents, decisions, phone calls)
6. First step should be the easiest possible starting point

Output JSON format:
{
  "title": "Clean title for the task",
  "steps": [
    {"step_number": 1, "description": "...", "action_verb": "...", "friction_notes": "...", "estimated_minutes": N},
    ...
  ]
}
"""


def decompose_with_llm(raw_input: str, depth: str = "shallow") -> Dict[str, Any]:
    """
    Use LLM to decompose a task into steps.

    Args:
        raw_input: The vague task description
        depth: "shallow" (2-3 steps) or "full" (all steps)

    Returns:
        dict with title and steps
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
    max_steps = config.get("task_engine", {}).get("decomposition", {}).get("max_steps", 7)

    prompt = load_decomposition_prompt()

    depth_instruction = ""
    if depth == "shallow":
        depth_instruction = "\n\nIMPORTANT: Only provide the first 2-3 steps. The user doesn't need to see the whole breakdown - just enough to get started."

    client = anthropic.Anthropic(api_key=api_key)

    try:
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"{prompt}{depth_instruction}\n\nTask to decompose: {raw_input}\n\nRespond with valid JSON only.",
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

        # Validate steps
        if "steps" not in result:
            return {"success": False, "error": "LLM response missing 'steps' field"}

        # Limit steps
        if len(result["steps"]) > max_steps:
            result["steps"] = result["steps"][:max_steps]

        return {"success": True, "data": result}

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse LLM response as JSON: {e}"}
    except Exception as e:
        return {"success": False, "error": f"LLM decomposition failed: {e}"}


def decompose_simple(raw_input: str) -> Dict[str, Any]:
    """
    Simple rule-based decomposition fallback.

    Used when LLM is not available.
    """
    # Basic heuristic decomposition for common tasks
    input_lower = raw_input.lower()

    if "tax" in input_lower:
        return {
            "success": True,
            "data": {
                "title": "File tax return",
                "steps": [
                    {"step_number": 1, "description": "Find your income statement or group certificate in your email", "action_verb": "find", "friction_notes": "Search for 'payment summary' or 'income statement' from your employer around July", "estimated_minutes": 10},
                    {"step_number": 2, "description": "Gather receipts for deductions you want to claim", "action_verb": "gather", "friction_notes": "Check your downloads folder, email, and bank statements", "estimated_minutes": 15},
                    {"step_number": 3, "description": "Open the tax portal and log in", "action_verb": "open", "friction_notes": "May need to retrieve password", "estimated_minutes": 5},
                ],
            },
        }

    if "email" in input_lower and ("send" in input_lower or "write" in input_lower):
        return {
            "success": True,
            "data": {
                "title": "Send email",
                "steps": [
                    {"step_number": 1, "description": "Open your email client", "action_verb": "open", "estimated_minutes": 1},
                    {"step_number": 2, "description": "Write the email", "action_verb": "write", "estimated_minutes": 10},
                    {"step_number": 3, "description": "Review and send", "action_verb": "send", "estimated_minutes": 2},
                ],
            },
        }

    if "call" in input_lower or "phone" in input_lower:
        return {
            "success": True,
            "data": {
                "title": "Make phone call",
                "steps": [
                    {"step_number": 1, "description": "Find the phone number you need", "action_verb": "find", "friction_notes": "Check your contacts, previous emails, or the website", "estimated_minutes": 5},
                    {"step_number": 2, "description": "Write down what you want to say", "action_verb": "write", "friction_notes": "Just bullet points - you don't need a script", "estimated_minutes": 5},
                    {"step_number": 3, "description": "Make the call", "action_verb": "call", "friction_notes": "Best times are usually 10-11am or 2-3pm", "estimated_minutes": 10},
                ],
            },
        }

    # Generic fallback
    return {
        "success": True,
        "data": {
            "title": raw_input.strip().capitalize(),
            "steps": [
                {"step_number": 1, "description": f"Start working on: {raw_input}", "action_verb": "open", "estimated_minutes": 15},
            ],
        },
    }


def decompose_task(
    user_id: str,
    raw_input: str,
    depth: str = "shallow",
    use_llm: bool = True,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Decompose a task into concrete steps.

    Args:
        user_id: User creating the task
        raw_input: The vague task description
        depth: "shallow" (first 2-3 steps) or "full" (all steps)
        use_llm: Whether to use LLM for decomposition
        task_id: Existing task ID to add steps to (if re-decomposing)

    Returns:
        dict with task and first step
    """
    # Get decomposition
    if use_llm:
        result = decompose_with_llm(raw_input, depth)
        if not result["success"]:
            # Fall back to simple decomposition
            result = decompose_simple(raw_input)
    else:
        result = decompose_simple(raw_input)

    if not result["success"]:
        return result

    data = result["data"]
    title = data.get("title", raw_input)
    steps = data.get("steps", [])

    # Create or get task
    if task_id:
        task_result = get_task(task_id)
        if not task_result["success"]:
            return task_result
        # Update title
        update_task(task_id, title=title)
    else:
        task_result = create_task(user_id=user_id, raw_input=raw_input, title=title)
        if not task_result["success"]:
            return task_result
        task_id = task_result["data"]["task_id"]

    # Add steps
    first_step = None
    for step in steps:
        step_result = add_step(
            task_id=task_id,
            step_number=step.get("step_number", 1),
            description=step.get("description", ""),
            action_verb=step.get("action_verb"),
            friction_notes=step.get("friction_notes"),
            estimated_minutes=step.get("estimated_minutes"),
        )
        if step_result["success"] and first_step is None:
            first_step = step_result["data"]

    # Set current step to first step
    if first_step:
        update_task(task_id, current_step_id=first_step["id"])

    return {
        "success": True,
        "data": {
            "task_id": task_id,
            "raw_input": raw_input,
            "title": title,
            "total_steps": len(steps),
            "first_step": first_step,
        },
        "message": f"Task decomposed into {len(steps)} steps",
    }


def redecompose_task(task_id: str, depth: str = "shallow") -> Dict[str, Any]:
    """
    Re-decompose an existing task with fresh steps.

    Useful when the first decomposition didn't work for the user.

    Args:
        task_id: Task to re-decompose
        depth: "shallow" or "full"

    Returns:
        dict with updated task
    """
    from .manager import get_connection

    # Get existing task
    task_result = get_task(task_id, include_steps=False)
    if not task_result["success"]:
        return task_result

    task = task_result["data"]

    # Delete existing steps
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM task_steps WHERE task_id = ?", (task_id,))
    cursor.execute("DELETE FROM task_friction WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()

    # Re-decompose
    return decompose_task(
        user_id=task["user_id"],
        raw_input=task["raw_input"],
        depth=depth,
        task_id=task_id,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Task Decomposer - Break vague tasks into concrete steps"
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["decompose", "redecompose"],
        help="Action to perform",
    )

    parser.add_argument("--task", help="Task description to decompose")
    parser.add_argument("--task-id", help="Task ID (for redecompose)")
    parser.add_argument("--user", help="User ID")
    parser.add_argument(
        "--depth",
        choices=["shallow", "full"],
        default="shallow",
        help="Decomposition depth (shallow = 2-3 steps, full = all steps)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Use simple rule-based decomposition instead of LLM",
    )

    args = parser.parse_args()
    result = None

    if args.action == "decompose":
        if not args.user or not args.task:
            print(json.dumps({"success": False, "error": "--user and --task required for decompose"}))
            sys.exit(1)
        result = decompose_task(
            user_id=args.user,
            raw_input=args.task,
            depth=args.depth,
            use_llm=not args.no_llm,
        )

    elif args.action == "redecompose":
        if not args.task_id:
            print(json.dumps({"success": False, "error": "--task-id required for redecompose"}))
            sys.exit(1)
        result = redecompose_task(task_id=args.task_id, depth=args.depth)

    if result:
        print(json.dumps(result, indent=2, default=str))
        if not result.get("success"):
            sys.exit(1)


if __name__ == "__main__":
    main()
