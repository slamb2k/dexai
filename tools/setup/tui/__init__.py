"""
TUI Setup Wizard - Terminal-based installation interface

Uses Textual for a rich terminal experience.
Provides an accessible alternative to the web wizard.

Components:
    main.py: Entry point and app shell
    screens/: Individual wizard screens
"""

from pathlib import Path

ASSETS_PATH = Path(__file__).parent / 'assets'
