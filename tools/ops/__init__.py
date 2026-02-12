"""
DexAI Operations Module

Provides database migrations, cost tracking, budget alerting, and backup utilities.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
BACKUP_DIR = PROJECT_ROOT / "backups"

DATA_DIR.mkdir(parents=True, exist_ok=True)

__all__ = [
    "BACKUP_DIR",
    "DATA_DIR",
    "MIGRATIONS_DIR",
    "PROJECT_ROOT",
]
