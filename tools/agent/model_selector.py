"""
DexAI Model Selector for Subagents
==================================

Provides intelligent model selection for ADHD-specific subagents based on
task complexity heuristics. Complements the main ModelRouter by offering
a simpler interface specifically for subagent model decisions.

Key Features:
- Task complexity scoring (0-10 scale)
- Agent-specific model defaults
- Override support for forcing specific models
- Integration with args/agent.yaml configuration

Usage:
    from tools.agent.model_selector import ModelSelector, get_model_for_agent

    # Quick usage with function
    model = get_model_for_agent("task-decomposer", "help me file my taxes")
    # Returns: "haiku" or "sonnet"

    # Full control with class
    selector = ModelSelector()
    score = selector.score_complexity("Break down this complex multi-step task", {})
    model = selector.select_model("...", "task-decomposer", {})

CLI:
    python -m tools.agent.model_selector --task "help me file my taxes" --agent task-decomposer
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
ARGS_DIR = PROJECT_ROOT / "args"
CONFIG_PATH = ARGS_DIR / "agent.yaml"


# =============================================================================
# Complexity Heuristics
# =============================================================================

# Technical terms that indicate higher complexity
TECHNICAL_TERMS = {
    # Code keywords
    "function", "class", "method", "variable", "import", "export", "async",
    "await", "promise", "callback", "error", "exception", "debug", "test",
    "refactor", "optimize", "api", "database", "query", "schema", "migration",
    # Error indicators
    "traceback", "stack", "error:", "failed", "exception", "bug", "issue",
    "broken", "crash", "undefined", "null", "none",
    # Architecture terms
    "architecture", "design", "pattern", "interface", "abstract", "implement",
    "dependency", "module", "package", "framework", "library",
}

# Multi-step indicators
MULTI_STEP_PATTERNS = {
    "and then",
    "after that",
    "next",
    "finally",
    "step by step",
    "steps",
    "first",
    "second",
    "third",
    "also",
    "additionally",
    "followed by",
    "once done",
    "when complete",
}

# Numbered list pattern (regex)
NUMBERED_LIST_PATTERN = re.compile(r'^\s*\d+[\.\)]\s+', re.MULTILINE)

# File path patterns (regex)
FILE_PATH_PATTERN = re.compile(
    r'(?:'
    r'[/\\][\w\-\.]+(?:[/\\][\w\-\.]+)+'  # Unix/Windows paths
    r'|[\w\-]+\.(?:py|js|ts|tsx|jsx|go|rs|java|cpp|c|h|md|yaml|yml|json|toml|sh)'  # File extensions
    r'|`[^`]+`'  # Backticked code references
    r')'
)

# Function/method name patterns
CODE_REFERENCE_PATTERN = re.compile(
    r'(?:'
    r'\w+\(\)'  # Function calls
    r'|\w+\.\w+'  # Method access
    r'|def \w+'  # Python function def
    r'|class \w+'  # Class definition
    r'|function \w+'  # JS function
    r')'
)

# Open-ended question indicators (higher complexity)
OPEN_ENDED_INDICATORS = {
    "how should",
    "what's the best",
    "how would you",
    "what do you think",
    "can you help me figure out",
    "i'm not sure how",
    "what's the right way",
    "how can i",
    "what approach",
    "where should i start",
}


@dataclass
class ComplexityBreakdown:
    """Detailed breakdown of complexity scoring for observability."""

    message_length_score: float = 0.0
    technical_terms_score: float = 0.0
    technical_terms_found: list[str] = field(default_factory=list)
    multi_step_score: float = 0.0
    multi_step_indicators_found: list[str] = field(default_factory=list)
    codebase_reference_score: float = 0.0
    file_paths_found: list[str] = field(default_factory=list)
    code_references_found: list[str] = field(default_factory=list)
    question_complexity_score: float = 0.0
    is_open_ended: bool = False
    total_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/debugging."""
        return {
            "message_length_score": self.message_length_score,
            "technical_terms_score": self.technical_terms_score,
            "technical_terms_found": self.technical_terms_found,
            "multi_step_score": self.multi_step_score,
            "multi_step_indicators_found": self.multi_step_indicators_found,
            "codebase_reference_score": self.codebase_reference_score,
            "file_paths_found": self.file_paths_found,
            "code_references_found": self.code_references_found,
            "question_complexity_score": self.question_complexity_score,
            "is_open_ended": self.is_open_ended,
            "total_score": self.total_score,
        }


# =============================================================================
# Agent Defaults
# =============================================================================

# Default models for each subagent (can be overridden by config)
AGENT_DEFAULTS: dict[str, str] = {
    "task-decomposer": "haiku",
    "energy-matcher": "haiku",
    "commitment-tracker": "haiku",
    "friction-solver": "sonnet",  # Always needs complex analysis
}

# Agents that should always use a specific model regardless of complexity
AGENT_FORCE_MODEL: dict[str, str] = {
    "friction-solver": "sonnet",  # Its job is complex analysis
}


# =============================================================================
# Model Selector
# =============================================================================


class ModelSelector:
    """
    Intelligent model selector for DexAI subagents.

    Analyzes task descriptions using heuristics to determine whether a
    subagent should use haiku (fast/cheap) or sonnet (powerful) for the task.

    Complexity Scoring (0-10):
        - Message length contributes up to 2 points
        - Technical terms contribute up to 2.5 points
        - Multi-step indicators contribute up to 2 points
        - Codebase references contribute up to 2 points
        - Question complexity contributes up to 1.5 points

    Model Selection Logic:
        - Score < 3: Always haiku (trivial tasks)
        - Score 3-6: Use agent default or haiku
        - Score 7-10: Use sonnet (complex analysis needed)
        - friction-solver always gets sonnet (its job is complex analysis)
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        agent_defaults: dict[str, str] | None = None,
        agent_force_model: dict[str, str] | None = None,
    ):
        """
        Initialize the ModelSelector.

        Args:
            config: Optional configuration override (default: load from args/agent.yaml)
            agent_defaults: Override default models for agents
            agent_force_model: Override forced models for specific agents
        """
        self.config = config or self._load_config()
        self._agent_defaults = agent_defaults or AGENT_DEFAULTS.copy()
        self._agent_force_model = agent_force_model or AGENT_FORCE_MODEL.copy()

        # Apply config overrides
        subagents_config = self.config.get("subagents", {})
        self._default_model = subagents_config.get("default_model", "haiku")

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from args/agent.yaml."""
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH) as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        return {}

    def score_complexity(
        self,
        task_description: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[float, ComplexityBreakdown]:
        """
        Calculate complexity score for a task description.

        Uses multiple heuristics to estimate task complexity:
        - Message length (longer = potentially more complex)
        - Technical terms (code keywords, error messages, file paths)
        - Multi-step indicators ("and then", "first", numbered lists)
        - Codebase references (file paths, function names)
        - Question complexity (open-ended vs yes/no)

        Args:
            task_description: The task or message to analyze
            context: Optional additional context (energy_level, pending_tasks, etc.)

        Returns:
            Tuple of (score from 0-10, ComplexityBreakdown with details)
        """
        context = context or {}
        breakdown = ComplexityBreakdown()
        task_lower = task_description.lower()
        words = task_description.split()

        # 1. Message length scoring (0-2 points)
        # Short messages (< 20 words) are likely simple
        # Long messages (> 100 words) indicate complexity
        word_count = len(words)
        if word_count < 20:
            breakdown.message_length_score = 0.0
        elif word_count < 50:
            breakdown.message_length_score = 0.5
        elif word_count < 100:
            breakdown.message_length_score = 1.0
        elif word_count < 200:
            breakdown.message_length_score = 1.5
        else:
            breakdown.message_length_score = 2.0

        # 2. Technical terms detection (0-2.5 points)
        # Each technical term adds 0.4 points, capped at 2.5
        found_terms = []
        for term in TECHNICAL_TERMS:
            if term in task_lower:
                found_terms.append(term)
        breakdown.technical_terms_found = found_terms
        breakdown.technical_terms_score = min(len(found_terms) * 0.4, 2.5)

        # 3. Multi-step indicators (0-2 points)
        # Each indicator adds 0.6 points, capped at 2
        found_indicators = []
        for indicator in MULTI_STEP_PATTERNS:
            if indicator in task_lower:
                found_indicators.append(indicator)

        # Check for numbered lists (1. 2. 3. etc.)
        numbered_items = NUMBERED_LIST_PATTERN.findall(task_description)
        if len(numbered_items) >= 2:
            found_indicators.append(f"numbered list ({len(numbered_items)} items)")

        breakdown.multi_step_indicators_found = found_indicators
        breakdown.multi_step_score = min(len(found_indicators) * 0.6, 2.0)

        # 4. Codebase references (0-2 points)
        # File paths and code references indicate technical tasks
        file_paths = FILE_PATH_PATTERN.findall(task_description)
        code_refs = CODE_REFERENCE_PATTERN.findall(task_description)
        breakdown.file_paths_found = file_paths[:5]  # Limit for display
        breakdown.code_references_found = code_refs[:5]

        path_score = min(len(file_paths) * 0.5, 1.0)
        code_score = min(len(code_refs) * 0.5, 1.0)
        breakdown.codebase_reference_score = path_score + code_score

        # 5. Question complexity (0-1.5 points)
        # Open-ended questions require more thought
        question_count = task_description.count("?")
        is_open_ended = any(ind in task_lower for ind in OPEN_ENDED_INDICATORS)
        breakdown.is_open_ended = is_open_ended

        if is_open_ended:
            breakdown.question_complexity_score = 1.5
        elif question_count > 2:
            breakdown.question_complexity_score = 1.0
        elif question_count == 1:
            breakdown.question_complexity_score = 0.5
        else:
            breakdown.question_complexity_score = 0.0

        # Calculate total score (0-10)
        total = (
            breakdown.message_length_score
            + breakdown.technical_terms_score
            + breakdown.multi_step_score
            + breakdown.codebase_reference_score
            + breakdown.question_complexity_score
        )
        breakdown.total_score = min(total, 10.0)

        return breakdown.total_score, breakdown

    def select_model(
        self,
        task_description: str,
        agent_name: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Select the appropriate model for a subagent task.

        Model Selection Logic:
            - Score < 3: Always haiku (trivial tasks)
            - Score 3-6: Use agent default or haiku
            - Score 7-10: Use sonnet (complex analysis needed)
            - friction-solver always gets sonnet

        Args:
            task_description: The task to analyze
            agent_name: Name of the subagent (e.g., "task-decomposer")
            context: Optional additional context

        Returns:
            "haiku" or "sonnet"
        """
        # Check if this agent has a forced model
        if agent_name in self._agent_force_model:
            forced = self._agent_force_model[agent_name]
            logger.debug(f"Agent '{agent_name}' forced to model: {forced}")
            return forced

        # Score the task complexity
        score, breakdown = self.score_complexity(task_description, context)

        # Determine model based on score
        if score < 3:
            # Trivial task - always use haiku
            selected = "haiku"
            reason = "trivial task"
        elif score < 7:
            # Moderate task - use agent default
            selected = self._agent_defaults.get(agent_name, self._default_model)
            reason = f"moderate task, using agent default"
        else:
            # Complex task - use sonnet
            selected = "sonnet"
            reason = "complex task requires sonnet"

        logger.debug(
            f"Model selection for '{agent_name}': {selected} "
            f"(score={score:.1f}, {reason})"
        )

        return selected

    def get_model_for_agent(
        self,
        agent_name: str,
        task_description: str | None = None,
        force_model: str | None = None,
    ) -> str:
        """
        Main entry point for getting the model for a subagent.

        This is the primary method to use from sdk_client.py or other
        callers that need to determine which model a subagent should use.

        Args:
            agent_name: Name of the subagent (e.g., "task-decomposer")
            task_description: Optional task description for complexity analysis
            force_model: Optional override to force a specific model

        Returns:
            "haiku" or "sonnet"
        """
        # Honor explicit override
        if force_model:
            if force_model in ("haiku", "sonnet"):
                return force_model
            logger.warning(f"Invalid force_model '{force_model}', ignoring")

        # If no task description, use agent default
        if not task_description:
            return self._agent_defaults.get(agent_name, self._default_model)

        # Otherwise, analyze and select
        return self.select_model(task_description, agent_name, {})

    def get_complexity_tier(self, score: float) -> str:
        """
        Convert numeric score to a complexity tier name.

        Args:
            score: Complexity score (0-10)

        Returns:
            Tier name: "trivial", "low", "moderate", "high", or "critical"
        """
        if score < 2:
            return "trivial"
        elif score < 4:
            return "low"
        elif score < 7:
            return "moderate"
        elif score < 9:
            return "high"
        else:
            return "critical"


# =============================================================================
# Module-Level Convenience Function
# =============================================================================

_selector: ModelSelector | None = None


def get_model_for_agent(
    agent_name: str,
    task_description: str | None = None,
    force_model: str | None = None,
) -> str:
    """
    Get the appropriate model for a subagent.

    Convenience function that uses a module-level ModelSelector instance.
    This is the recommended way to call from sdk_client.py.

    Args:
        agent_name: Name of the subagent (e.g., "task-decomposer")
        task_description: Optional task description for complexity analysis
        force_model: Optional override to force a specific model

    Returns:
        "haiku" or "sonnet"

    Example:
        from tools.agent.model_selector import get_model_for_agent

        model = get_model_for_agent("task-decomposer", "help me file my taxes")
        # Returns: "haiku" (simple task)

        model = get_model_for_agent(
            "task-decomposer",
            "Debug the authentication flow in tools/security/auth.py and then "
            "refactor the error handling and add proper logging"
        )
        # Returns: "sonnet" (complex task)
    """
    global _selector
    if _selector is None:
        _selector = ModelSelector()
    return _selector.get_model_for_agent(agent_name, task_description, force_model)


def score_task_complexity(task_description: str) -> tuple[float, dict[str, Any]]:
    """
    Score the complexity of a task description.

    Convenience function for scoring without model selection.

    Args:
        task_description: The task to analyze

    Returns:
        Tuple of (score from 0-10, breakdown dict with details)
    """
    global _selector
    if _selector is None:
        _selector = ModelSelector()
    score, breakdown = _selector.score_complexity(task_description, {})
    return score, breakdown.to_dict()


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing model selection."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="DexAI Model Selector for Subagents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage
    python -m tools.agent.model_selector --task "help me file my taxes" --agent task-decomposer

    # With JSON output
    python -m tools.agent.model_selector --task "debug auth flow" --agent friction-solver --json

    # Score only (no agent)
    python -m tools.agent.model_selector --task "complex multi-step refactoring" --score-only

    # Force a specific model
    python -m tools.agent.model_selector --task "simple task" --agent task-decomposer --force sonnet
        """,
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Task description to analyze",
    )
    parser.add_argument(
        "--agent",
        default="task-decomposer",
        choices=["task-decomposer", "energy-matcher", "commitment-tracker", "friction-solver"],
        help="Subagent name (default: task-decomposer)",
    )
    parser.add_argument(
        "--force",
        choices=["haiku", "sonnet"],
        help="Force a specific model (overrides analysis)",
    )
    parser.add_argument(
        "--score-only",
        action="store_true",
        help="Only show complexity score, don't select model",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed breakdown",
    )

    args = parser.parse_args()

    # Initialize selector
    selector = ModelSelector()

    # Score the task
    score, breakdown = selector.score_complexity(args.task, {})
    tier = selector.get_complexity_tier(score)

    if args.score_only:
        if args.json:
            output = {
                "task": args.task,
                "score": round(score, 2),
                "tier": tier,
            }
            if args.verbose:
                output["breakdown"] = breakdown.to_dict()
            print(json.dumps(output, indent=2))
        else:
            print(f"Complexity Score: {score:.2f}/10 ({tier})")
            if args.verbose:
                print(f"\nBreakdown:")
                print(f"  Message length:    {breakdown.message_length_score:.1f}")
                print(f"  Technical terms:   {breakdown.technical_terms_score:.1f} ({len(breakdown.technical_terms_found)} found)")
                print(f"  Multi-step:        {breakdown.multi_step_score:.1f} ({len(breakdown.multi_step_indicators_found)} found)")
                print(f"  Codebase refs:     {breakdown.codebase_reference_score:.1f}")
                print(f"  Question type:     {breakdown.question_complexity_score:.1f} (open-ended: {breakdown.is_open_ended})")
        return

    # Select model
    model = selector.get_model_for_agent(args.agent, args.task, args.force)

    if args.json:
        output = {
            "task": args.task,
            "agent": args.agent,
            "model": model,
            "score": round(score, 2),
            "tier": tier,
            "forced": args.force is not None,
        }
        if args.verbose:
            output["breakdown"] = breakdown.to_dict()
        print(json.dumps(output, indent=2))
    else:
        print(f"Agent: {args.agent}")
        print(f"Model: {model}")
        print(f"Score: {score:.2f}/10 ({tier})")
        if args.force:
            print(f"(forced to {args.force})")
        if args.verbose:
            print(f"\nBreakdown:")
            print(f"  Message length:    {breakdown.message_length_score:.1f}")
            print(f"  Technical terms:   {breakdown.technical_terms_score:.1f}")
            if breakdown.technical_terms_found:
                print(f"    Found: {', '.join(breakdown.technical_terms_found[:5])}")
            print(f"  Multi-step:        {breakdown.multi_step_score:.1f}")
            if breakdown.multi_step_indicators_found:
                print(f"    Found: {', '.join(breakdown.multi_step_indicators_found[:5])}")
            print(f"  Codebase refs:     {breakdown.codebase_reference_score:.1f}")
            if breakdown.file_paths_found:
                print(f"    Paths: {', '.join(breakdown.file_paths_found[:3])}")
            print(f"  Question type:     {breakdown.question_complexity_score:.1f}")


if __name__ == "__main__":
    main()
