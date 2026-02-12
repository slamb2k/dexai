"""
Forward-only database migration runner.

Applies numbered SQL migration files from the migrations/ directory
to a target SQLite database. Tracks applied migrations in a
schema_migrations table.

Usage:
    python -m tools.ops.migrate
    python -m tools.ops.migrate --db data/audit.db
    python -m tools.ops.migrate --dry-run
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from tools.ops import DATA_DIR, MIGRATIONS_DIR


try:
    from tools.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = DATA_DIR / "audit.db"

MIGRATION_PATTERN = re.compile(r'^(\d{4})_[\w-]+\.sql$')


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    db_path = db_path or DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    return conn


def applied_versions(conn: sqlite3.Connection) -> set[str]:
    cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
    return {row["version"] for row in cursor.fetchall()}


def pending_migrations(db_path: Path | None = None) -> list[Path]:
    conn = get_connection(db_path)
    try:
        done = applied_versions(conn)
    finally:
        conn.close()

    if not MIGRATIONS_DIR.exists():
        return []

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    pending = []
    for f in files:
        match = MIGRATION_PATTERN.match(f.name)
        if not match:
            logger.warning(f"Skipping malformed migration file: {f.name}")
            continue
        version = match.group(1)
        if version not in done:
            pending.append(f)
    return pending


def run_migrations(
    db_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    conn = get_connection(db_path)
    try:
        done = applied_versions(conn)

        if not MIGRATIONS_DIR.exists():
            return {"success": True, "applied": [], "message": "No migrations directory"}

        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        applied: list[str] = []

        for f in files:
            version = f.name.split("_", 1)[0]
            if version in done:
                continue

            sql = f.read_text()
            if dry_run:
                logger.info(f"[dry-run] Would apply {f.name}")
                applied.append(f.name)
                continue

            try:
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, filename) VALUES (?, ?)",
                    (version, f.name),
                )
                conn.commit()
                applied.append(f.name)
                logger.info(f"Applied migration {f.name}")
            except Exception as e:
                return {
                    "success": False,
                    "applied": applied,
                    "error": f"Migration {f.name} failed: {e}",
                }

        return {
            "success": True,
            "applied": applied,
            "message": f"Applied {len(applied)} migration(s)",
        }
    finally:
        conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Database Migration Runner")
    parser.add_argument("--db", type=Path, default=None, help="Database path")
    parser.add_argument("--dry-run", action="store_true", help="Show pending without applying")
    parser.add_argument("--pending", action="store_true", help="List pending migrations")

    args = parser.parse_args()

    if args.pending:
        pending = pending_migrations(args.db)
        if pending:
            print(f"{len(pending)} pending migration(s):")
            for p in pending:
                print(f"  {p.name}")
        else:
            print("No pending migrations")
        return

    result = run_migrations(db_path=args.db, dry_run=args.dry_run)
    if result["success"]:
        print(result["message"])
        for name in result["applied"]:
            print(f"  {name}")
    else:
        print(f"ERROR: {result['error']}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
