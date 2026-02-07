"""
Tool: Skill Tracker
Purpose: Track skill usage patterns to inform refinements

This tool tracks when skills activate, whether they're helpful, and generates
suggestions for skill refinement based on usage patterns.

Skills are located in `.claude/skills/` and include:
- adhd-decomposition: Task breakdown for overwhelm
- energy-matching: Match tasks to energy levels
- rsd-safe-communication: RSD-safe language filtering

Tracked Events:
- activation: Skill triggered (with trigger reason)
- helpful: User continued with suggested action
- ignored: User changed topic/didn't follow suggestion
- explicit_feedback: User rated skill (1-5 scale or thumbs up/down)

Usage:
    # Record activation
    python -m tools.agent.skill_tracker --record activation adhd-decomposition "overwhelm detected"

    # Record outcome
    python -m tools.agent.skill_tracker --record helpful adhd-decomposition
    python -m tools.agent.skill_tracker --record ignored energy-matching
    python -m tools.agent.skill_tracker --record feedback rsd-safe-communication 5

    # View statistics
    python -m tools.agent.skill_tracker --stats
    python -m tools.agent.skill_tracker --stats --skill adhd-decomposition

    # Get refinement suggestions
    python -m tools.agent.skill_tracker --suggestions

    # Export data
    python -m tools.agent.skill_tracker --export

Dependencies:
    - Standard library only (json, dataclasses, pathlib, datetime, argparse)

Output:
    JSON result with success status and data
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"
DEFAULT_DATA_FILE = DATA_DIR / "skill_usage.json"

# Schema version for future migrations
SCHEMA_VERSION = 1

# Known skill names
KNOWN_SKILLS = [
    "adhd-decomposition",
    "energy-matching",
    "rsd-safe-communication",
]

# Valid event types
EVENT_TYPES = ["activation", "helpful", "ignored", "feedback"]

# Refinement thresholds
LOW_SUCCESS_THRESHOLD = 0.50  # Below this suggests reviewing trigger conditions
HIGH_IGNORE_THRESHOLD = 0.40  # Above this suggests less aggressive activation
MIN_ACTIVATIONS_FOR_ANALYSIS = 5  # Need at least this many to analyze


@dataclass
class SkillUsageData:
    """
    Tracks usage data for a single skill.

    Attributes:
        skill_name: Name of the skill (e.g., 'adhd-decomposition')
        total_activations: How many times the skill has been triggered
        successful_outcomes: Times user continued with suggestion (helpful)
        ignored_outcomes: Times user changed topic/ignored suggestion
        user_ratings: List of explicit feedback scores (1-5 scale)
        trigger_patterns: Mapping of trigger reasons to activation counts
        last_activated: ISO timestamp of most recent activation
    """
    skill_name: str
    total_activations: int = 0
    successful_outcomes: int = 0
    ignored_outcomes: int = 0
    user_ratings: list[int] = field(default_factory=list)
    trigger_patterns: dict[str, int] = field(default_factory=dict)
    last_activated: str | None = None

    @property
    def success_rate(self) -> float | None:
        """Calculate success rate if we have outcomes."""
        total_outcomes = self.successful_outcomes + self.ignored_outcomes
        if total_outcomes == 0:
            return None
        return self.successful_outcomes / total_outcomes

    @property
    def ignore_rate(self) -> float | None:
        """Calculate ignore rate if we have outcomes."""
        total_outcomes = self.successful_outcomes + self.ignored_outcomes
        if total_outcomes == 0:
            return None
        return self.ignored_outcomes / total_outcomes

    @property
    def avg_rating(self) -> float | None:
        """Calculate average user rating if we have ratings."""
        if not self.user_ratings:
            return None
        return sum(self.user_ratings) / len(self.user_ratings)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillUsageData":
        """Create from dictionary (JSON deserialization)."""
        return cls(
            skill_name=data["skill_name"],
            total_activations=data.get("total_activations", 0),
            successful_outcomes=data.get("successful_outcomes", 0),
            ignored_outcomes=data.get("ignored_outcomes", 0),
            user_ratings=data.get("user_ratings", []),
            trigger_patterns=data.get("trigger_patterns", {}),
            last_activated=data.get("last_activated"),
        )


@dataclass
class ActivationEvent:
    """
    Record of a single skill activation.

    Used for detailed history tracking beyond aggregate stats.
    """
    skill_name: str
    trigger: str
    context: dict[str, Any]
    timestamp: str
    session_id: str | None = None
    user_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class SkillTracker:
    """
    Tracks skill usage patterns to inform refinements.

    Stores aggregate statistics in JSON format with the ability to:
    - Record activations with trigger reasons
    - Track outcomes (helpful vs ignored)
    - Collect explicit feedback (1-5 ratings)
    - Generate refinement suggestions based on patterns

    Attributes:
        data_file: Path to JSON storage file
        usage: Dictionary mapping skill names to SkillUsageData
        recent_activations: List of recent activation events (last 100)
    """

    def __init__(self, data_file: str | Path = DEFAULT_DATA_FILE):
        """
        Initialize the skill tracker.

        Args:
            data_file: Path to JSON storage file. Created if doesn't exist.
        """
        self.data_file = Path(data_file)
        self.usage: dict[str, SkillUsageData] = {}
        self.recent_activations: list[dict[str, Any]] = []
        self._schema_version = SCHEMA_VERSION
        self._load()

    def _ensure_data_dir(self) -> None:
        """Ensure data directory exists."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """Load data from JSON file."""
        if not self.data_file.exists():
            # Initialize with empty data for known skills
            for skill_name in KNOWN_SKILLS:
                self.usage[skill_name] = SkillUsageData(skill_name=skill_name)
            return

        try:
            with open(self.data_file, "r") as f:
                data = json.load(f)

            self._schema_version = data.get("schema_version", 1)
            self.recent_activations = data.get("recent_activations", [])

            # Load usage data
            usage_data = data.get("usage", {})
            for skill_name, skill_data in usage_data.items():
                self.usage[skill_name] = SkillUsageData.from_dict(skill_data)

            # Ensure known skills exist
            for skill_name in KNOWN_SKILLS:
                if skill_name not in self.usage:
                    self.usage[skill_name] = SkillUsageData(skill_name=skill_name)

        except (json.JSONDecodeError, KeyError) as e:
            # Corrupted file, start fresh
            print(f"Warning: Could not load skill usage data: {e}", file=sys.stderr)
            for skill_name in KNOWN_SKILLS:
                self.usage[skill_name] = SkillUsageData(skill_name=skill_name)

    def _save(self) -> None:
        """Save data to JSON file."""
        self._ensure_data_dir()

        # Keep only last 100 activations
        self.recent_activations = self.recent_activations[-100:]

        data = {
            "schema_version": SCHEMA_VERSION,
            "last_updated": datetime.now().isoformat(),
            "usage": {name: skill.to_dict() for name, skill in self.usage.items()},
            "recent_activations": self.recent_activations,
        }

        with open(self.data_file, "w") as f:
            json.dump(data, f, indent=2)

    def _get_or_create_skill(self, skill_name: str) -> SkillUsageData:
        """Get or create skill usage data."""
        if skill_name not in self.usage:
            self.usage[skill_name] = SkillUsageData(skill_name=skill_name)
        return self.usage[skill_name]

    def record_activation(
        self,
        skill_name: str,
        trigger: str,
        context: dict[str, Any] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Record when a skill is activated.

        Args:
            skill_name: Name of the skill (e.g., 'adhd-decomposition')
            trigger: What triggered the skill (e.g., 'overwhelm detected', 'vague task')
            context: Additional context (message snippet, channel, etc.)
            session_id: Optional session identifier for tracking
            user_id: Optional user identifier

        Returns:
            dict with success status and activation details
        """
        timestamp = datetime.now().isoformat()

        skill = self._get_or_create_skill(skill_name)
        skill.total_activations += 1
        skill.last_activated = timestamp

        # Track trigger pattern
        if trigger:
            skill.trigger_patterns[trigger] = skill.trigger_patterns.get(trigger, 0) + 1

        # Record activation event
        event = ActivationEvent(
            skill_name=skill_name,
            trigger=trigger,
            context=context or {},
            timestamp=timestamp,
            session_id=session_id,
            user_id=user_id,
        )
        self.recent_activations.append(event.to_dict())

        self._save()

        return {
            "success": True,
            "skill_name": skill_name,
            "trigger": trigger,
            "total_activations": skill.total_activations,
            "timestamp": timestamp,
        }

    def record_outcome(
        self,
        skill_name: str,
        outcome: str,
        user_feedback: int | None = None,
    ) -> dict[str, Any]:
        """
        Record the outcome of a skill activation.

        Args:
            skill_name: Name of the skill
            outcome: One of 'helpful', 'ignored', or 'feedback'
            user_feedback: For 'feedback' outcome, the rating (1-5)

        Returns:
            dict with success status and updated stats
        """
        if outcome not in ("helpful", "ignored", "feedback"):
            return {
                "success": False,
                "error": f"Invalid outcome: {outcome}. Must be 'helpful', 'ignored', or 'feedback'",
            }

        if outcome == "feedback" and user_feedback is None:
            return {
                "success": False,
                "error": "user_feedback (1-5) required for 'feedback' outcome",
            }

        if user_feedback is not None and not (1 <= user_feedback <= 5):
            return {
                "success": False,
                "error": f"user_feedback must be 1-5, got {user_feedback}",
            }

        skill = self._get_or_create_skill(skill_name)

        if outcome == "helpful":
            skill.successful_outcomes += 1
        elif outcome == "ignored":
            skill.ignored_outcomes += 1
        elif outcome == "feedback" and user_feedback is not None:
            skill.user_ratings.append(user_feedback)
            # Also count as helpful if rating >= 4, ignored if rating <= 2
            if user_feedback >= 4:
                skill.successful_outcomes += 1
            elif user_feedback <= 2:
                skill.ignored_outcomes += 1

        self._save()

        return {
            "success": True,
            "skill_name": skill_name,
            "outcome": outcome,
            "user_feedback": user_feedback,
            "success_rate": round(skill.success_rate, 3) if skill.success_rate else None,
            "total_outcomes": skill.successful_outcomes + skill.ignored_outcomes,
        }

    def get_stats(self, skill_name: str | None = None) -> dict[str, Any]:
        """
        Get usage statistics for one or all skills.

        Args:
            skill_name: Specific skill name, or None for all skills

        Returns:
            dict with success status and statistics
        """
        if skill_name:
            if skill_name not in self.usage:
                return {
                    "success": False,
                    "error": f"Unknown skill: {skill_name}",
                }

            skill = self.usage[skill_name]
            return {
                "success": True,
                "skill": {
                    "skill_name": skill.skill_name,
                    "total_activations": skill.total_activations,
                    "successful_outcomes": skill.successful_outcomes,
                    "ignored_outcomes": skill.ignored_outcomes,
                    "success_rate": round(skill.success_rate, 3) if skill.success_rate else None,
                    "ignore_rate": round(skill.ignore_rate, 3) if skill.ignore_rate else None,
                    "avg_rating": round(skill.avg_rating, 2) if skill.avg_rating else None,
                    "rating_count": len(skill.user_ratings),
                    "last_activated": skill.last_activated,
                    "top_triggers": sorted(
                        skill.trigger_patterns.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )[:5],
                },
            }

        # All skills
        stats = []
        for name, skill in self.usage.items():
            stats.append({
                "skill_name": name,
                "total_activations": skill.total_activations,
                "successful_outcomes": skill.successful_outcomes,
                "ignored_outcomes": skill.ignored_outcomes,
                "success_rate": round(skill.success_rate, 3) if skill.success_rate else None,
                "avg_rating": round(skill.avg_rating, 2) if skill.avg_rating else None,
                "last_activated": skill.last_activated,
            })

        # Sort by activation count
        stats.sort(key=lambda x: x["total_activations"], reverse=True)

        total_activations = sum(s["total_activations"] for s in stats)
        total_outcomes = sum(
            (s.get("successful_outcomes", 0) or 0) + (s.get("ignored_outcomes", 0) or 0)
            for s in stats
        )

        return {
            "success": True,
            "summary": {
                "total_activations": total_activations,
                "total_outcomes": total_outcomes,
                "skills_tracked": len(stats),
            },
            "skills": stats,
        }

    def get_refinement_suggestions(self) -> list[dict[str, Any]]:
        """
        Generate suggestions for skill refinement based on usage patterns.

        Returns:
            list of suggestion dicts with skill_name, issue, suggestion, and severity
        """
        suggestions = []

        for skill in self.usage.values():
            # Need minimum activations for analysis
            if skill.total_activations < MIN_ACTIVATIONS_FOR_ANALYSIS:
                continue

            # Check for low success rate
            if skill.success_rate is not None and skill.success_rate < LOW_SUCCESS_THRESHOLD:
                suggestions.append({
                    "skill_name": skill.skill_name,
                    "issue": "low_success_rate",
                    "severity": "high" if skill.success_rate < 0.3 else "medium",
                    "current_value": round(skill.success_rate, 3),
                    "threshold": LOW_SUCCESS_THRESHOLD,
                    "suggestion": (
                        f"Success rate is {skill.success_rate:.0%}. "
                        "Consider reviewing trigger conditions - the skill may be activating "
                        "in contexts where it's not actually helpful."
                    ),
                    "action_items": [
                        "Review 'When to Activate' section in SKILL.md",
                        "Check if triggers are too broad",
                        "Consider adding exclusion conditions",
                    ],
                })

            # Check for high ignore rate
            if skill.ignore_rate is not None and skill.ignore_rate > HIGH_IGNORE_THRESHOLD:
                suggestions.append({
                    "skill_name": skill.skill_name,
                    "issue": "high_ignore_rate",
                    "severity": "medium",
                    "current_value": round(skill.ignore_rate, 3),
                    "threshold": HIGH_IGNORE_THRESHOLD,
                    "suggestion": (
                        f"Ignore rate is {skill.ignore_rate:.0%}. "
                        "Consider less aggressive activation - users may find the skill intrusive."
                    ),
                    "action_items": [
                        "Increase confidence threshold for activation",
                        "Require multiple signals before triggering",
                        "Add a 'soft' mode that asks before fully activating",
                    ],
                })

            # Check for triggers that never lead to success
            if skill.trigger_patterns and skill.successful_outcomes > 0:
                total_outcomes = skill.successful_outcomes + skill.ignored_outcomes
                if total_outcomes >= 5:
                    # Estimate per-trigger success (simplified - would need detailed tracking)
                    sorted_triggers = sorted(
                        skill.trigger_patterns.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )
                    for trigger, count in sorted_triggers[:3]:
                        # If a trigger is >30% of activations but success rate is low,
                        # it might be a problematic trigger
                        if count > skill.total_activations * 0.3 and skill.success_rate and skill.success_rate < 0.5:
                            suggestions.append({
                                "skill_name": skill.skill_name,
                                "issue": "problematic_trigger",
                                "severity": "low",
                                "trigger": trigger,
                                "trigger_count": count,
                                "suggestion": (
                                    f"Trigger '{trigger}' accounts for {count}/{skill.total_activations} activations. "
                                    "Consider whether this trigger is too aggressive or misidentifying user intent."
                                ),
                                "action_items": [
                                    f"Review instances where '{trigger}' led to ignored outcomes",
                                    "Consider requiring additional context for this trigger",
                                    "May need to remove or refine this trigger pattern",
                                ],
                            })

            # Check for consistently positive feedback patterns
            if skill.avg_rating and skill.avg_rating >= 4.5 and len(skill.user_ratings) >= 5:
                suggestions.append({
                    "skill_name": skill.skill_name,
                    "issue": "positive_pattern",
                    "severity": "info",
                    "current_value": round(skill.avg_rating, 2),
                    "suggestion": (
                        f"Skill has high user satisfaction (avg rating: {skill.avg_rating:.1f}/5). "
                        "Document what's working well for reference when building new skills."
                    ),
                    "action_items": [
                        "Document successful trigger patterns",
                        "Consider this skill as a template for others",
                        "Look for opportunities to apply similar patterns elsewhere",
                    ],
                })

            # Check for low user feedback collection
            if skill.total_activations >= 20 and len(skill.user_ratings) < 3:
                suggestions.append({
                    "skill_name": skill.skill_name,
                    "issue": "low_feedback_collection",
                    "severity": "info",
                    "activations": skill.total_activations,
                    "ratings": len(skill.user_ratings),
                    "suggestion": (
                        f"Only {len(skill.user_ratings)} ratings from {skill.total_activations} activations. "
                        "Consider prompting for feedback more often to improve analysis."
                    ),
                    "action_items": [
                        "Add occasional 'Was that helpful?' prompts",
                        "Implement thumbs up/down reaction tracking",
                        "Review if feedback mechanism is visible enough",
                    ],
                })

        # Sort by severity
        severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        suggestions.sort(key=lambda x: severity_order.get(x["severity"], 4))

        return suggestions

    def export_data(self) -> dict[str, Any]:
        """
        Export all tracking data for analysis.

        Returns:
            dict with all usage data and recent activations
        """
        return {
            "success": True,
            "schema_version": SCHEMA_VERSION,
            "exported_at": datetime.now().isoformat(),
            "usage": {name: skill.to_dict() for name, skill in self.usage.items()},
            "recent_activations": self.recent_activations,
        }

    def reset_skill(self, skill_name: str) -> dict[str, Any]:
        """
        Reset statistics for a specific skill.

        Args:
            skill_name: Name of the skill to reset

        Returns:
            dict with success status
        """
        if skill_name not in self.usage:
            return {
                "success": False,
                "error": f"Unknown skill: {skill_name}",
            }

        self.usage[skill_name] = SkillUsageData(skill_name=skill_name)
        self._save()

        return {
            "success": True,
            "skill_name": skill_name,
            "message": f"Statistics reset for {skill_name}",
        }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Skill Usage Tracker - Track and analyze skill activation patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Record activation
    python -m tools.agent.skill_tracker --record activation adhd-decomposition "overwhelm detected"

    # Record outcomes
    python -m tools.agent.skill_tracker --record helpful adhd-decomposition
    python -m tools.agent.skill_tracker --record ignored energy-matching
    python -m tools.agent.skill_tracker --record feedback rsd-safe-communication 5

    # View statistics
    python -m tools.agent.skill_tracker --stats
    python -m tools.agent.skill_tracker --stats --skill adhd-decomposition

    # Get refinement suggestions
    python -m tools.agent.skill_tracker --suggestions

    # Export all data
    python -m tools.agent.skill_tracker --export

    # Reset skill statistics
    python -m tools.agent.skill_tracker --reset adhd-decomposition
        """,
    )

    # Action arguments (mutually exclusive)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--record",
        nargs="+",
        metavar=("EVENT", "SKILL"),
        help="Record an event: activation SKILL TRIGGER, helpful/ignored SKILL, or feedback SKILL RATING",
    )
    action_group.add_argument(
        "--stats",
        action="store_true",
        help="Display usage statistics",
    )
    action_group.add_argument(
        "--suggestions",
        action="store_true",
        help="Get refinement suggestions",
    )
    action_group.add_argument(
        "--export",
        action="store_true",
        help="Export all tracking data",
    )
    action_group.add_argument(
        "--reset",
        metavar="SKILL",
        help="Reset statistics for a skill",
    )

    # Additional arguments
    parser.add_argument(
        "--skill",
        help="Filter statistics to specific skill",
    )
    parser.add_argument(
        "--data-file",
        default=str(DEFAULT_DATA_FILE),
        help=f"Path to data file (default: {DEFAULT_DATA_FILE})",
    )
    parser.add_argument(
        "--context",
        help="JSON context for activation records",
    )

    args = parser.parse_args()
    tracker = SkillTracker(data_file=args.data_file)
    result: dict[str, Any] = {}

    if args.record:
        event_type = args.record[0].lower()

        if event_type not in EVENT_TYPES:
            result = {
                "success": False,
                "error": f"Unknown event type: {event_type}. Must be one of: {EVENT_TYPES}",
            }
        elif event_type == "activation":
            if len(args.record) < 3:
                result = {
                    "success": False,
                    "error": "Usage: --record activation SKILL TRIGGER",
                }
            else:
                skill_name = args.record[1]
                trigger = " ".join(args.record[2:])
                context = json.loads(args.context) if args.context else None
                result = tracker.record_activation(skill_name, trigger, context)

        elif event_type in ("helpful", "ignored"):
            if len(args.record) < 2:
                result = {
                    "success": False,
                    "error": f"Usage: --record {event_type} SKILL",
                }
            else:
                skill_name = args.record[1]
                result = tracker.record_outcome(skill_name, event_type)

        elif event_type == "feedback":
            if len(args.record) < 3:
                result = {
                    "success": False,
                    "error": "Usage: --record feedback SKILL RATING (1-5)",
                }
            else:
                skill_name = args.record[1]
                try:
                    rating = int(args.record[2])
                except ValueError:
                    result = {"success": False, "error": f"Invalid rating: {args.record[2]}"}
                else:
                    result = tracker.record_outcome(skill_name, "feedback", rating)

    elif args.stats:
        result = tracker.get_stats(args.skill)

    elif args.suggestions:
        suggestions = tracker.get_refinement_suggestions()
        result = {
            "success": True,
            "suggestion_count": len(suggestions),
            "suggestions": suggestions,
        }

    elif args.export:
        result = tracker.export_data()

    elif args.reset:
        result = tracker.reset_skill(args.reset)

    # Output result
    print(json.dumps(result, indent=2, default=str))
    if not result.get("success", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
