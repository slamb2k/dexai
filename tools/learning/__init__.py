"""Learning Tools - Pattern recognition and personalization

Philosophy:
    Learn from behavior, not configuration forms.
    ADHD users won't fill out preference surveys.
    Observe, infer, suggest - never require.

Core Principle:
    The system should become smarter over time without
    asking the user to do anything. Every interaction
    is a data point. Patterns emerge from observation.

Components:
    energy_tracker.py: Infer energy levels from activity patterns
        - Response times indicate mental sharpness
        - Message length correlates with engagement
        - Session duration reveals flow states
        - Task completions map to productive periods

    pattern_analyzer.py: Detect recurring patterns in behavior
        - Daily routines (same-time activities)
        - Weekly cycles (day-of-week patterns)
        - Avoidance patterns (tasks repeatedly postponed)
        - Productive bursts (clusters of completions)

    task_matcher.py: Match tasks to optimal times/energy
        - Given a task, suggest the best time
        - Given current time, suggest the best task
        - Never overwhelming lists - single suggestions

ADHD Safety Rules:
    1. No self-reporting required - pure observation
    2. No guilt-inducing language about patterns
    3. Avoidance is friction information, not failure
    4. Graceful degradation when data insufficient
    5. Energy levels are rhythms, not moral judgments

Database: data/learning.db
    - energy_observations: Raw activity signals
    - energy_profiles: Aggregated hourly patterns
    - peak_hours: Derived optimal times per day
    - behavior_patterns: Detected recurring patterns

Configuration: args/learning.yaml
    - Signal weights for energy inference
    - Energy level thresholds
    - Pattern detection settings
    - Task-energy matching rules
"""

from pathlib import Path

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'learning.db'
CONFIG_PATH = PROJECT_ROOT / 'args' / 'learning.yaml'

# Energy levels
ENERGY_LEVELS = ['low', 'medium', 'high', 'peak']

# Pattern types
PATTERN_TYPES = [
    'daily_routine',
    'weekly_cycle',
    'avoidance',
    'productive_burst',
    'context_switch'
]

# Default task energy requirements
DEFAULT_TASK_ENERGY = {
    'creative': 'peak',
    'problem_solving': 'high',
    'writing': 'medium',
    'admin': 'low',
    'organizing': 'low',
    'communication': 'medium',
    'learning': 'high',
    'review': 'medium'
}
