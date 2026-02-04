# tools/system/__init__.py
"""
System Access Tools

This package provides secure system access capabilities:
- browser: Web automation with domain controls (DEPRECATED: use SDK WebFetch)
- network: HTTP client with domain allowlists

Note: executor and fileops were removed in the SDK migration.
The Claude Agent SDK provides Read, Write, Edit, Glob, Grep, LS, and Bash
which replace these modules with better sandboxing and integration.
"""

from pathlib import Path


# Package info
__version__ = "2.0.0"
__all__ = ["browser", "network"]

# Common paths
SYSTEM_ROOT = Path(__file__).parent
PROJECT_ROOT = SYSTEM_ROOT.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ARGS_DIR = PROJECT_ROOT / "args"
