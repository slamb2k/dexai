"""Task Engine - ADHD-friendly task decomposition and tracking

Philosophy:
    The problem isn't the task - it's the invisible friction.
    "Do taxes" fails because of hidden prerequisites.
    This engine surfaces ONE step at a time with friction pre-solved.

Components:
    manager.py: Task CRUD operations
    decompose.py: Break tasks into concrete steps
    friction_solver.py: Identify and solve blockers
    current_step.py: Return only the immediate next action

Key ADHD Insight:
    "Do taxes" is not a task, it's a project - but ADHD brains write it as
    one line item, feel overwhelmed, and avoid it.

    The decomposition itself requires executive function the user may not have.
    This engine does the decomposition proactively, then presents ONLY the
    current step (not the full breakdown - that's overwhelming too).

Usage:
    # Create and decompose a task
    from tools.tasks.manager import create_task
    from tools.tasks.decompose import decompose_task
    from tools.tasks.current_step import get_current_step

    task = create_task(user_id="alice", raw_input="do taxes")
    decompose_task(task["data"]["task_id"])

    # Get ONLY the next step
    step = get_current_step(user_id="alice")
    print(step["data"]["formatted"])
    # "Find your group certificate - search email for 'payment summary'"
"""

from pathlib import Path

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "tasks.db"
CONFIG_PATH = PROJECT_ROOT / "args" / "task_engine.yaml"

# Valid statuses
TASK_STATUSES = ("pending", "in_progress", "completed", "abandoned")
STEP_STATUSES = ("pending", "in_progress", "completed", "skipped")
ENERGY_LEVELS = ("low", "medium", "high")

# Friction types
FRICTION_TYPES = (
    "missing_info",
    "phone_call",
    "decision",
    "password",
    "document",
    "appointment",
)

# Action verbs for task steps
ACTION_VERBS = (
    "find",
    "send",
    "call",
    "open",
    "write",
    "review",
    "submit",
    "wait",
    "book",
    "check",
    "create",
    "download",
    "upload",
    "gather",
    "schedule",
)

__all__ = [
    "PROJECT_ROOT",
    "DB_PATH",
    "CONFIG_PATH",
    "TASK_STATUSES",
    "STEP_STATUSES",
    "ENERGY_LEVELS",
    "FRICTION_TYPES",
    "ACTION_VERBS",
]
