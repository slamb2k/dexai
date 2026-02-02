"""
Tool: Task Matcher
Purpose: Match tasks to optimal times based on energy levels and patterns

This tool combines energy profiles with task requirements to suggest:
1. Best time for a specific task (based on its energy demands)
2. Best task for right now (based on current energy level)
3. Proactive suggestions when energy/task match well

Core ADHD Principle:
    Present ONE suggestion, not overwhelming lists.
    The user can ask for alternatives, but default is a single clear action.

Usage:
    # Best time for a specific task
    python tools/learning/task_matcher.py --action best-time --user alice \\
        --task "Write project proposal" --task-type creative

    # Best task for right now
    python tools/learning/task_matcher.py --action best-task --user alice

    # Get proactive suggestions
    python tools/learning/task_matcher.py --action suggest --user alice --count 3

    # Check if now is good for a task type
    python tools/learning/task_matcher.py --action check --user alice --task-type creative

Dependencies:
    - sqlite3 (stdlib)
    - yaml (PyYAML)
    - energy_tracker (sibling module)
    - pattern_analyzer (sibling module)

Output:
    JSON result with success status and suggestions
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "learning.db"
CONFIG_PATH = PROJECT_ROOT / "args" / "learning.yaml"
TASKS_DB_PATH = PROJECT_ROOT / "data" / "tasks.db"

# Energy levels and their numeric values
ENERGY_LEVELS = {"low": 0.2, "medium": 0.5, "high": 0.7, "peak": 0.9}

# Day name mapping
DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
            return config.get("learning", {}).get("task_matching", {})
    # Return defaults if no config
    return {
        "enabled": True,
        "match_energy_to_task": True,
        "avoid_high_demand_in_low_energy": True,
        "suggest_easier_when_tired": True,
        "internal_candidate_count": 10,
        "look_ahead_hours": 8,
        "min_gap_between_suggestions": 2,
        "task_energy_requirements": {
            "creative": "peak",
            "problem_solving": "high",
            "writing": "medium",
            "admin": "low",
            "organizing": "low",
            "communication": "medium",
            "learning": "high",
            "review": "medium",
        },
        "fallback_behavior": "suggest_any",
        "messages": {
            "insufficient_data": "I'm still learning your patterns - give me a few more days of activity.",
            "energy_mismatch_warning": "This might be easier during your {optimal_period} when you're usually sharper.",
            "avoidance_detected": "I notice {task} keeps getting pushed - want me to find the smallest first step?",
            "good_match": "Good timing - {task_type} work matches your current energy.",
        },
    }


def get_learning_connection() -> sqlite3.Connection:
    """Get connection to learning database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_tasks_connection() -> sqlite3.Connection | None:
    """Get connection to tasks database if it exists."""
    if not TASKS_DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(TASKS_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _import_energy_tracker():
    """Import energy_tracker module handling both package and standalone execution."""
    try:
        from . import energy_tracker

        return energy_tracker
    except ImportError:
        # Running as standalone script
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "energy_tracker", Path(__file__).parent / "energy_tracker.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def _import_pattern_analyzer():
    """Import pattern_analyzer module handling both package and standalone execution."""
    try:
        from . import pattern_analyzer

        return pattern_analyzer
    except ImportError:
        # Running as standalone script
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "pattern_analyzer", Path(__file__).parent / "pattern_analyzer.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def get_current_energy(user_id: str) -> dict[str, Any]:
    """Get current energy estimate from energy_tracker."""
    energy_tracker = _import_energy_tracker()
    return energy_tracker.get_current_energy(user_id)


def get_energy_profile(user_id: str) -> dict[str, Any]:
    """Get full energy profile from energy_tracker."""
    energy_tracker = _import_energy_tracker()
    return energy_tracker.get_energy_profile(user_id)


def get_peak_hours(user_id: str, day: str | None = None) -> dict[str, Any]:
    """Get peak hours from energy_tracker."""
    energy_tracker = _import_energy_tracker()
    return energy_tracker.get_peak_hours(user_id, day)


def get_avoidance_patterns(user_id: str) -> dict[str, Any]:
    """Get avoidance patterns from pattern_analyzer."""
    pattern_analyzer = _import_pattern_analyzer()
    return pattern_analyzer.get_avoidance(user_id)


def energy_requirement_to_score(level: str) -> float:
    """Convert energy level name to numeric score."""
    return ENERGY_LEVELS.get(level, 0.5)


def score_to_energy_level(score: float) -> str:
    """Convert numeric score to energy level name."""
    if score >= 0.8:
        return "peak"
    elif score >= 0.6:
        return "high"
    elif score >= 0.4:
        return "medium"
    else:
        return "low"


def get_pending_tasks(user_id: str) -> list[dict]:
    """Get pending tasks from tasks database if available."""
    conn = get_tasks_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, task_type, due_date, priority, energy_requirement
            FROM tasks
            WHERE status = 'pending' AND (user_id = ? OR user_id IS NULL)
            ORDER BY priority DESC, due_date ASC
            LIMIT 20
        """,
            (user_id,),
        )

        tasks = []
        for row in cursor.fetchall():
            tasks.append(dict(row))

        conn.close()
        return tasks
    except sqlite3.OperationalError:
        # Table might not exist with expected schema
        conn.close()
        return []


def find_best_time_for_task(
    user_id: str, task_type: str, task_name: str | None = None
) -> dict[str, Any]:
    """
    Find the best time to do a task based on energy requirements.

    Args:
        user_id: User identifier
        task_type: Type of task (creative, admin, etc.)
        task_name: Optional task name for display

    Returns:
        dict with suggested times
    """
    config = load_config()

    if not config.get("enabled", True):
        return {"success": False, "error": "Task matching is disabled"}

    # Get task energy requirement
    requirements = config.get("task_energy_requirements", {})
    required_level = requirements.get(task_type, "medium")
    required_score = energy_requirement_to_score(required_level)

    # Get user's energy profile
    profile_result = get_energy_profile(user_id)

    if not profile_result.get("sufficient_data", False):
        # Not enough data - use fallback
        if config.get("fallback_behavior") == "wait_for_data":
            return {
                "success": True,
                "user_id": user_id,
                "task_type": task_type,
                "task_name": task_name,
                "suggestions": [],
                "message": config.get("messages", {}).get(
                    "insufficient_data", "I'm still learning your patterns."
                ),
            }
        else:
            # Suggest general peak hours (9-11am for most people)
            return {
                "success": True,
                "user_id": user_id,
                "task_type": task_type,
                "task_name": task_name,
                "suggestions": [
                    {
                        "hour": 9,
                        "day": "any",
                        "reason": "Morning hours tend to work well for focused work",
                    },
                    {"hour": 10, "day": "any", "reason": "Mid-morning is typically high-energy"},
                ],
                "note": "These are general suggestions - I'll learn your specific patterns over time.",
            }

    profile = profile_result.get("profile", {})
    now = datetime.now()
    current_hour = now.hour
    current_day = DAY_NAMES[now.weekday()]

    # Find matching time slots
    suggestions = []
    look_ahead = config.get("look_ahead_hours", 8)

    # Check upcoming hours today
    for offset in range(look_ahead):
        check_hour = (current_hour + offset) % 24
        check_day = (
            current_day if (current_hour + offset) < 24 else DAY_NAMES[(now.weekday() + 1) % 7]
        )

        if check_day in profile and check_hour in profile[check_day]:
            slot = profile[check_day][check_hour]
            if slot.get("reliable", False) and slot.get("score", 0) >= required_score:
                suggestions.append(
                    {
                        "hour": check_hour,
                        "day": check_day,
                        "energy_score": slot["score"],
                        "energy_level": slot["level"],
                        "hours_from_now": offset,
                        "reason": f"{slot['level'].title()} energy matches {task_type} requirements",
                    }
                )

    # Also check peak hours
    peak_result = get_peak_hours(user_id)
    if peak_result.get("peak_hours"):
        peak_hours = peak_result["peak_hours"]
        if peak_hours.get(current_day):
            for peak_hour in peak_hours[current_day]:
                if peak_hour > current_hour and not any(
                    s["hour"] == peak_hour for s in suggestions
                ):
                    suggestions.append(
                        {
                            "hour": peak_hour,
                            "day": current_day,
                            "energy_level": "peak",
                            "reason": "This is typically one of your peak hours",
                        }
                    )

    # Sort by hours from now (soonest first)
    suggestions.sort(key=lambda x: x.get("hours_from_now", 99))

    # Limit to top 3
    suggestions = suggestions[:3]

    if not suggestions:
        return {
            "success": True,
            "user_id": user_id,
            "task_type": task_type,
            "task_name": task_name,
            "suggestions": [],
            "message": f"No ideal slots found in the next {look_ahead} hours for {required_level}-energy {task_type} work.",
        }

    return {
        "success": True,
        "user_id": user_id,
        "task_type": task_type,
        "task_name": task_name,
        "required_energy": required_level,
        "suggestions": suggestions,
        "best_suggestion": suggestions[0] if suggestions else None,
    }


def find_best_task_for_now(user_id: str) -> dict[str, Any]:
    """
    Find the best task type for current energy level.

    Args:
        user_id: User identifier

    Returns:
        dict with task suggestion (single, ADHD-friendly)
    """
    config = load_config()

    if not config.get("enabled", True):
        return {"success": False, "error": "Task matching is disabled"}

    # Get current energy
    energy_result = get_current_energy(user_id)

    if energy_result.get("energy_level") is None:
        # No energy data
        if config.get("fallback_behavior") == "wait_for_data":
            return {
                "success": True,
                "user_id": user_id,
                "suggestion": None,
                "message": config.get("messages", {}).get(
                    "insufficient_data", "I'm still learning your patterns."
                ),
            }
        else:
            # Suggest based on time of day
            hour = datetime.now().hour
            if 9 <= hour <= 11:
                task_type = "creative"
                reason = "Morning is often good for creative work"
            elif 14 <= hour <= 16:
                task_type = "admin"
                reason = "Afternoon can be good for lighter admin tasks"
            else:
                task_type = "review"
                reason = "A good time for review and planning"

            return {
                "success": True,
                "user_id": user_id,
                "suggested_task_type": task_type,
                "reason": reason,
                "note": "This is a general suggestion - I'll learn your patterns over time.",
            }

    current_level = energy_result.get("energy_level")
    current_score = energy_result.get("energy_score", 0.5)

    # Find task types that match current energy
    requirements = config.get("task_energy_requirements", {})

    matching_types = []
    for task_type, required_level in requirements.items():
        required_score = energy_requirement_to_score(required_level)

        # Check if current energy meets or exceeds requirement
        if current_score >= required_score * 0.8:  # Allow 20% buffer
            match_quality = 1.0 - abs(current_score - required_score)
            matching_types.append(
                {
                    "task_type": task_type,
                    "match_quality": match_quality,
                    "required_level": required_level,
                }
            )

    # Sort by match quality
    matching_types.sort(key=lambda x: x["match_quality"], reverse=True)

    if not matching_types:
        # Current energy is too low for tracked task types
        return {
            "success": True,
            "user_id": user_id,
            "current_energy": current_level,
            "suggested_task_type": "admin",
            "reason": "Your energy seems low right now - admin or organizing tasks might be a good fit.",
            "alternatives": ["organizing", "review"],
        }

    best_match = matching_types[0]

    # Check for pending tasks of this type
    pending = get_pending_tasks(user_id)
    matching_task = None
    for task in pending:
        if task.get("task_type") == best_match["task_type"]:
            matching_task = task
            break

    # Check for avoidance patterns
    avoidance = get_avoidance_patterns(user_id)
    avoidance_warning = None
    if avoidance.get("avoidance_patterns"):
        # Gently suggest addressing avoided tasks during peak energy
        if current_level in ["peak", "high"]:
            avoided = avoidance["avoidance_patterns"][0]
            avoidance_warning = {
                "task_name": avoided["task_name"],
                "message": f"You've got good energy - maybe tackle '{avoided['task_name']}'? I can help find the smallest step.",
            }

    result = {
        "success": True,
        "user_id": user_id,
        "current_energy": current_level,
        "energy_score": round(current_score, 3),
        "suggested_task_type": best_match["task_type"],
        "match_quality": round(best_match["match_quality"], 2),
        "reason": f"Your {current_level} energy level is good for {best_match['task_type']} work.",
    }

    if matching_task:
        result["suggested_task"] = {
            "id": matching_task.get("id"),
            "title": matching_task.get("title"),
            "priority": matching_task.get("priority"),
        }

    if avoidance_warning:
        result["avoidance_nudge"] = avoidance_warning

    return result


def check_energy_match(user_id: str, task_type: str) -> dict[str, Any]:
    """
    Check if current energy matches a task type.

    Args:
        user_id: User identifier
        task_type: Type of task to check

    Returns:
        dict with match status and advice
    """
    config = load_config()

    if not config.get("enabled", True):
        return {"success": False, "error": "Task matching is disabled"}

    # Get current energy
    energy_result = get_current_energy(user_id)
    current_level = energy_result.get("energy_level")
    current_score = energy_result.get("energy_score", 0.5)

    # Get task requirement
    requirements = config.get("task_energy_requirements", {})
    required_level = requirements.get(task_type, "medium")
    required_score = energy_requirement_to_score(required_level)

    if current_level is None:
        return {
            "success": True,
            "user_id": user_id,
            "task_type": task_type,
            "match": "unknown",
            "message": "I don't have enough data about your energy patterns yet.",
        }

    # Determine match quality
    energy_diff = current_score - required_score

    if energy_diff >= 0:
        # Current energy meets or exceeds requirement
        match_status = "good"
        message = (
            config.get("messages", {})
            .get("good_match", "Good timing - {task_type} work matches your current energy.")
            .format(task_type=task_type)
        )
    elif energy_diff >= -0.2:
        # Slightly under but manageable
        match_status = "acceptable"
        message = (
            f"Your energy is a bit lower than ideal for {task_type} work, but you can manage it."
        )
    else:
        # Significant mismatch
        match_status = "poor"
        # Find better time
        best_time = find_best_time_for_task(user_id, task_type)
        if best_time.get("suggestions"):
            suggestion = best_time["suggestions"][0]
            optimal_time = f"{suggestion['hour']}:00"
            if suggestion["day"] != DAY_NAMES[datetime.now().weekday()]:
                optimal_time = f"{suggestion['day'].title()} at {suggestion['hour']}:00"
            message = (
                config.get("messages", {})
                .get("energy_mismatch_warning", "This might be easier around {optimal_period}.")
                .format(optimal_period=optimal_time)
            )
        else:
            message = f"Your current energy ({current_level}) is lower than ideal for {task_type} work ({required_level} recommended)."

    return {
        "success": True,
        "user_id": user_id,
        "task_type": task_type,
        "required_energy": required_level,
        "current_energy": current_level,
        "match_status": match_status,
        "message": message,
    }


def get_suggestions(user_id: str, count: int = 3) -> dict[str, Any]:
    """
    Get proactive task suggestions based on current state.

    Args:
        user_id: User identifier
        count: Number of suggestions (max)

    Returns:
        dict with suggestions (still presents ONE primary suggestion)
    """
    config = load_config()

    # Get current energy
    energy_result = get_current_energy(user_id)
    current_level = energy_result.get("energy_level")
    current_score = energy_result.get("energy_score", 0.5)

    # Get pending tasks
    pending = get_pending_tasks(user_id)

    # Get avoidance patterns
    avoidance = get_avoidance_patterns(user_id)

    suggestions = []

    # Check for high-priority tasks that match energy
    requirements = config.get("task_energy_requirements", {})

    if pending:
        for task in pending[:10]:
            task_type = task.get("task_type", "admin")
            required_level = requirements.get(task_type, "medium")
            required_score = energy_requirement_to_score(required_level)

            if current_score and current_score >= required_score * 0.8:
                suggestions.append(
                    {
                        "type": "pending_task",
                        "task_id": task.get("id"),
                        "task_title": task.get("title"),
                        "task_type": task_type,
                        "reason": "Energy matches and this is pending",
                        "priority": task.get("priority", 0),
                    }
                )

    # If high energy, suggest tackling avoided tasks
    if current_level in ["peak", "high"] and avoidance.get("avoidance_patterns"):
        avoided = avoidance["avoidance_patterns"][0]
        suggestions.append(
            {
                "type": "avoidance_tackle",
                "task_name": avoided["task_name"],
                "reason": "Good energy for tackling something you've been putting off",
                "offer": "Want me to find the smallest first step?",
            }
        )

    # Add general task type suggestion
    if current_level:
        best_types = []
        for task_type, required_level in requirements.items():
            required_score = energy_requirement_to_score(required_level)
            if abs(current_score - required_score) < 0.2:
                best_types.append(task_type)

        if best_types:
            suggestions.append(
                {
                    "type": "task_type_match",
                    "suggested_types": best_types[:3],
                    "reason": f"Your {current_level} energy is good for {', '.join(best_types[:2])} work",
                }
            )

    # Limit and format
    suggestions = suggestions[:count]

    # ADHD principle: present ONE primary suggestion
    primary = suggestions[0] if suggestions else None
    alternatives = suggestions[1:] if len(suggestions) > 1 else []

    return {
        "success": True,
        "user_id": user_id,
        "current_energy": current_level,
        "primary_suggestion": primary,
        "alternatives": alternatives,
        "total_suggestions": len(suggestions),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Task Matcher - Match tasks to optimal times based on energy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Best time for a specific task type
    python task_matcher.py --action best-time --user alice --task-type creative

    # Best time with task name
    python task_matcher.py --action best-time --user alice \\
        --task "Write project proposal" --task-type creative

    # Best task for right now
    python task_matcher.py --action best-task --user alice

    # Get suggestions
    python task_matcher.py --action suggest --user alice --count 3

    # Check if now is good for a task type
    python task_matcher.py --action check --user alice --task-type creative

Task Types:
    creative        - Writing, design, strategy (requires peak energy)
    problem_solving - Debugging, analysis (requires high energy)
    writing         - Documentation, emails (requires medium energy)
    admin           - Filing, organizing (works with low energy)
    organizing      - Cleanup, sorting (works with low energy)
    communication   - Calls, meetings (requires medium energy)
    learning        - New concepts, tutorials (requires high energy)
    review          - Code review, feedback (requires medium energy)
        """,
    )

    parser.add_argument(
        "--action",
        required=True,
        choices=["best-time", "best-task", "suggest", "check"],
        help="Action to perform",
    )
    parser.add_argument("--user", required=True, help="User ID")
    parser.add_argument("--task", help="Task name/description")
    parser.add_argument(
        "--task-type",
        choices=[
            "creative",
            "problem_solving",
            "writing",
            "admin",
            "organizing",
            "communication",
            "learning",
            "review",
        ],
        help="Type of task",
    )
    parser.add_argument(
        "--count", type=int, default=3, help="Number of suggestions for suggest action"
    )

    args = parser.parse_args()
    result = None

    if args.action == "best-time":
        if not args.task_type:
            print(
                json.dumps({"success": False, "error": "--task-type required for best-time action"})
            )
            sys.exit(1)
        result = find_best_time_for_task(args.user, args.task_type, args.task)

    elif args.action == "best-task":
        result = find_best_task_for_now(args.user)

    elif args.action == "suggest":
        result = get_suggestions(args.user, args.count)

    elif args.action == "check":
        if not args.task_type:
            print(json.dumps({"success": False, "error": "--task-type required for check action"}))
            sys.exit(1)
        result = check_energy_match(args.user, args.task_type)

    if result:
        print(json.dumps(result, indent=2, default=str))
        if not result.get("success"):
            sys.exit(1)


if __name__ == "__main__":
    main()
