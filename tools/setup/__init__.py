"""Setup Wizard - Guided DexAI installation

Philosophy:
    Setup should feel like a conversation, not a checklist.
    ADHD users abandon software during setup if it feels overwhelming.
    Get to first successful interaction in minutes, not hours.

Design Principles:
    1. Progressive Disclosure - Don't show everything at once
    2. Smart Defaults - Pre-fill sensible values, let users change later
    3. Immediate Feedback - After each step, show something working
    4. Easy Recovery - Can interrupt and resume at any point

Components:
    wizard.py: Core setup state management and validation
    tui/main.py: Terminal UI using Textual
    tui/screens/: Individual wizard screens
    guides/: Channel setup documentation
"""

from pathlib import Path

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / 'args'
DATA_PATH = PROJECT_ROOT / 'data'
SETUP_STATE_PATH = DATA_PATH / 'setup_state.json'
SETUP_COMPLETE_FLAG = DATA_PATH / 'setup_complete.flag'
