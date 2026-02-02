# tools/system/__init__.py
"""
System Access Tools

This package provides secure system access capabilities:
- executor: Sandboxed command execution with allowlists
- fileops: Secure file read/write with path validation
- browser: Web automation with domain controls
- network: HTTP client with domain allowlists
"""

from pathlib import Path


# Package info
__version__ = "1.0.0"
__all__ = ["browser", "executor", "fileops", "network"]

# Common paths
SYSTEM_ROOT = Path(__file__).parent
PROJECT_ROOT = SYSTEM_ROOT.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ARGS_DIR = PROJECT_ROOT / "args"
