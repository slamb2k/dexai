"""
WAL-safe SQLite backup using sqlite3.Connection.backup().

Produces gzip-compressed copies with retention: 7 daily + 4 weekly.

Usage:
    python -m tools.ops.backup
    python -m tools.ops.backup --db data/audit.db
    python -m tools.ops.backup --retention-daily 14
"""

from __future__ import annotations

import gzip
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.ops import BACKUP_DIR, DATA_DIR


try:
    from tools.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

DEFAULT_DBS = ["audit.db", "dashboard.db", "sessions.db", "memory.db"]
DAILY_RETENTION = 7
WEEKLY_RETENTION = 4


def enable_wal(db_path: Path) -> None:
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()


def backup_database(
    db_path: Path,
    dest_dir: Path | None = None,
    compress: bool = True,
) -> Path | None:
    if not db_path.exists():
        logger.debug(f"Skipping {db_path} (does not exist)")
        return None

    dest_dir = dest_dir or BACKUP_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{db_path.stem}_{timestamp}.db"
    raw_dest = dest_dir / base_name

    src_conn = sqlite3.connect(str(db_path))
    dst_conn = sqlite3.connect(str(raw_dest))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    if compress:
        gz_dest = raw_dest.with_suffix(".db.gz")
        with open(raw_dest, "rb") as f_in, gzip.open(gz_dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        raw_dest.unlink()
        logger.info(f"Backed up {db_path.name} -> {gz_dest.name}")
        return gz_dest
    else:
        logger.info(f"Backed up {db_path.name} -> {raw_dest.name}")
        return raw_dest


def enforce_retention(
    dest_dir: Path | None = None,
    daily: int = DAILY_RETENTION,
    weekly: int = WEEKLY_RETENTION,
) -> int:
    dest_dir = dest_dir or BACKUP_DIR
    if not dest_dir.exists():
        return 0

    removed = 0
    stems: dict[str, list[Path]] = {}

    for f in dest_dir.iterdir():
        if not (f.suffix == ".gz" or f.suffix == ".db"):
            continue
        # Extract stem (e.g. "audit" from "audit_20260101_120000.db.gz")
        parts = f.stem.split("_")
        if f.name.endswith(".db.gz"):
            parts = f.name.replace(".db.gz", "").split("_")
        db_stem = parts[0] if parts else f.stem
        stems.setdefault(db_stem, []).append(f)

    for _db_stem, files in stems.items():
        files.sort(key=lambda p: p.name, reverse=True)
        keep = daily + weekly
        for old_file in files[keep:]:
            old_file.unlink()
            removed += 1
            logger.debug(f"Removed old backup: {old_file.name}")

    return removed


def backup_all(
    data_dir: Path | None = None,
    dest_dir: Path | None = None,
    compress: bool = True,
) -> dict[str, Any]:
    data_dir = data_dir or DATA_DIR
    results: list[str] = []

    for db_name in DEFAULT_DBS:
        db_path = data_dir / db_name
        result = backup_database(db_path, dest_dir=dest_dir, compress=compress)
        if result:
            results.append(result.name)

    # Also enable WAL for all databases
    import contextlib

    for db_name in DEFAULT_DBS:
        db_path = data_dir / db_name
        with contextlib.suppress(Exception):
            enable_wal(db_path)

    removed = enforce_retention(dest_dir)
    return {
        "success": True,
        "backed_up": results,
        "old_removed": removed,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="WAL-safe SQLite Backup")
    parser.add_argument("--db", type=Path, default=None, help="Specific database to back up")
    parser.add_argument("--dest", type=Path, default=None, help="Backup destination directory")
    parser.add_argument("--no-compress", action="store_true", help="Skip gzip compression")
    parser.add_argument("--retention-daily", type=int, default=DAILY_RETENTION)
    parser.add_argument("--retention-weekly", type=int, default=WEEKLY_RETENTION)
    parser.add_argument("--enable-wal", action="store_true", help="Enable WAL mode on all DBs")

    args = parser.parse_args()

    if args.enable_wal:
        for db_name in DEFAULT_DBS:
            db_path = DATA_DIR / db_name
            if db_path.exists():
                enable_wal(db_path)
                print(f"WAL enabled: {db_path}")
        return

    if args.db:
        result = backup_database(args.db, dest_dir=args.dest, compress=not args.no_compress)
        if result:
            print(f"Backed up: {result}")
        else:
            print(f"Database not found: {args.db}")
        enforce_retention(args.dest, daily=args.retention_daily, weekly=args.retention_weekly)
    else:
        result = backup_all(dest_dir=args.dest, compress=not args.no_compress)
        print(f"Backed up {len(result['backed_up'])} databases, removed {result['old_removed']} old backups")
        for name in result["backed_up"]:
            print(f"  {name}")


if __name__ == "__main__":
    main()
