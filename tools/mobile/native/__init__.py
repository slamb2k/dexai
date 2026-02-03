"""
DexAI Mobile Native Tools - Phase 10c

Backend support for native mobile features:
- Widget data API
- Watch data API
- Siri shortcuts handling
- Quick actions handling

This module provides the backend APIs that power the native enhancements
in the mobile app.
"""

from pathlib import Path

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_PATH = PROJECT_ROOT / "args" / "mobile_push.yaml"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Module exports
from .widget_data import get_widget_data, get_watch_data
from .shortcuts import (
    handle_shortcut,
    get_suggested_shortcuts,
    handle_quick_action,
)

__all__ = [
    "get_widget_data",
    "get_watch_data",
    "handle_shortcut",
    "get_suggested_shortcuts",
    "handle_quick_action",
    "PROJECT_ROOT",
    "DATA_DIR",
    "CONFIG_PATH",
]
