"""
ADHD Communication Tools - RSD-safe, brevity-first responses

This package implements communication patterns specifically designed for ADHD users:

1. **Brevity by Default**: Responses are 1-2 sentences unless user asks for more
2. **RSD Protection**: No guilt-inducing language ever ("overdue", "you haven't")
3. **One-Thing Mode**: "What should I do?" returns exactly one actionable item
4. **Recoverable Depth**: "more" or "explain" unlocks detailed responses

Core Principles (from adhd_design_principles.md):
- A list of five things is actually zero things
- The emotional safety of the system determines whether users keep engaging
- Everything is forward-facing, never backward-looking blame

Components:
    response_formatter.py: Apply brevity rules, strip preamble, one-thing mode
    language_filter.py: RSD-safe language detection and reframing

Usage:
    # Format a response for brevity
    from tools.adhd import response_formatter
    result = response_formatter.format_response("Your long response here...")

    # Filter for RSD-safe language
    from tools.adhd import language_filter
    result = language_filter.filter_content("You still haven't sent the invoice")
    # Returns: {"success": True, "filtered": "Ready to send that invoice when you are"}

Configuration:
    All settings in args/adhd_mode.yaml - includes blocked phrases, reframe
    patterns, brevity limits, and one-thing mode toggles.

Dependencies:
    - pyyaml (configuration loading)
    - re (pattern matching)
"""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / 'args' / 'adhd_mode.yaml'

__all__ = [
    'PROJECT_ROOT',
    'CONFIG_PATH',
]
