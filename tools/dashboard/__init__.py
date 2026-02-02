"""Web Dashboard - Real-time monitoring and configuration

Components:
    backend/main.py: FastAPI application
    backend/routes/: API route handlers
    backend/websocket.py: Real-time event streaming

This module provides a web-based management interface for DexAI
with real-time monitoring, configuration management, and debugging tools.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dashboard.db"
CONFIG_PATH = PROJECT_ROOT / "args" / "dashboard.yaml"

# Version
__version__ = "0.1.0"
