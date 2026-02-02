"""Dashboard Backend Package

FastAPI-based REST API and WebSocket server for the DexAI dashboard.
"""

from pathlib import Path


# Re-export project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dashboard.db"
CONFIG_PATH = PROJECT_ROOT / "args" / "dashboard.yaml"
