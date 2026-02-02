"""
Tool: Memory Database Migration
Purpose: Migrate memory.db from old 5-column schema to new 16-column schema

This script handles the one-time migration from the initial schema:
    (id, content, entry_type, importance, created_at)
to the full schema expected by memory_db.py:
    (id, type, content, content_hash, source, confidence, importance,
     created_at, updated_at, last_accessed, access_count, embedding,
     embedding_model, tags, context, expires_at, is_active)

Also creates auxiliary tables: daily_logs, memory_access_log

Usage:
    python tools/memory/migrate_db.py              # Run migration
    python tools/memory/migrate_db.py --dry-run    # Show what would happen
    python tools/memory/migrate_db.py --rollback   # Restore from backup

Dependencies:
    - sqlite3 (stdlib)
    - shutil (stdlib)
"""

import os
import sys
import json
import sqlite3
import shutil
import hashlib
import argparse
from datetime import datetime
from pathlib import Path

# Paths
DB_PATH = Path(__file__).parent.parent.parent / "data" / "memory.db"
BACKUP_PATH = Path(__file__).parent.parent.parent / "data" / "memory.db.backup"


def compute_content_hash(content: str) -> str:
    """Compute hash of content for deduplication."""
    return hashlib.sha256(content.strip().lower().encode()).hexdigest()[:16]


def check_schema_version(conn) -> str:
    """
    Determine current schema version.

    Returns:
        'old' - Original 5-column schema
        'new' - Full 16-column schema
        'empty' - No tables exist
    """
    cursor = conn.cursor()

    # Check if memory_entries table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='memory_entries'
    """)
    if not cursor.fetchone():
        return 'empty'

    # Check column count
    cursor.execute("PRAGMA table_info(memory_entries)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]

    if 'content_hash' in column_names and 'is_active' in column_names:
        return 'new'
    else:
        return 'old'


def backup_database():
    """Create a backup of the current database."""
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"✓ Backup created: {BACKUP_PATH}")
        return True
    return False


def rollback_database():
    """Restore database from backup."""
    if not BACKUP_PATH.exists():
        print("✗ No backup file found")
        return False

    shutil.copy2(BACKUP_PATH, DB_PATH)
    print(f"✓ Database restored from backup")
    return True


def migrate_old_to_new(conn, dry_run: bool = False):
    """
    Migrate from old 5-column schema to new 16-column schema.

    Old schema: id, content, entry_type, importance, created_at
    New schema: id, type, content, content_hash, source, confidence, importance,
                created_at, updated_at, last_accessed, access_count, embedding,
                embedding_model, tags, context, expires_at, is_active
    """
    cursor = conn.cursor()

    # Get existing data
    cursor.execute("SELECT id, content, entry_type, importance, created_at FROM memory_entries")
    existing_entries = cursor.fetchall()

    if dry_run:
        print(f"Would migrate {len(existing_entries)} entries")
        for entry in existing_entries[:5]:
            print(f"  - ID {entry[0]}: {entry[1][:50]}...")
        if len(existing_entries) > 5:
            print(f"  ... and {len(existing_entries) - 5} more")
        return

    # Rename old table
    cursor.execute("ALTER TABLE memory_entries RENAME TO memory_entries_old")
    print("✓ Renamed old table to memory_entries_old")

    # Create new schema
    cursor.execute('''
        CREATE TABLE memory_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('fact', 'preference', 'event', 'insight', 'task', 'relationship')),
            content TEXT NOT NULL,
            content_hash TEXT UNIQUE,
            source TEXT DEFAULT 'session' CHECK(source IN ('user', 'inferred', 'session', 'external', 'system')),
            confidence REAL DEFAULT 1.0,
            importance INTEGER DEFAULT 5 CHECK(importance BETWEEN 1 AND 10),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_accessed DATETIME,
            access_count INTEGER DEFAULT 0,
            embedding BLOB,
            embedding_model TEXT,
            tags TEXT,
            context TEXT,
            expires_at DATETIME,
            is_active INTEGER DEFAULT 1
        )
    ''')
    print("✓ Created new memory_entries table")

    # Migrate data with defaults
    migrated = 0
    for entry in existing_entries:
        old_id, content, entry_type, importance, created_at = entry

        # Map old entry_type to new type (handle any naming differences)
        type_mapping = {
            'fact': 'fact',
            'preference': 'preference',
            'event': 'event',
            'insight': 'insight',
            'task': 'task',
            'relationship': 'relationship'
        }
        new_type = type_mapping.get(entry_type, 'fact')

        # Compute content hash
        content_hash = compute_content_hash(content)

        # Ensure importance is within bounds
        importance = max(1, min(10, importance or 5))

        try:
            cursor.execute('''
                INSERT INTO memory_entries
                (id, type, content, content_hash, source, confidence, importance,
                 created_at, updated_at, is_active)
                VALUES (?, ?, ?, ?, 'session', 1.0, ?, ?, ?, 1)
            ''', (old_id, new_type, content, content_hash, importance, created_at, created_at))
            migrated += 1
        except sqlite3.IntegrityError as e:
            # Handle duplicate content hash (shouldn't happen normally)
            print(f"  Warning: Skipped entry {old_id} due to duplicate content hash")

    print(f"✓ Migrated {migrated}/{len(existing_entries)} entries")

    # Drop old table
    cursor.execute("DROP TABLE memory_entries_old")
    print("✓ Dropped old table")

    conn.commit()


def create_auxiliary_tables(conn, dry_run: bool = False):
    """Create daily_logs and memory_access_log tables."""
    cursor = conn.cursor()

    if dry_run:
        print("Would create auxiliary tables: daily_logs, memory_access_log")
        return

    # Daily logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL UNIQUE,
            summary TEXT,
            raw_log TEXT,
            key_events TEXT,
            entry_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✓ Created daily_logs table")

    # Memory access log
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory_access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id INTEGER,
            access_type TEXT CHECK(access_type IN ('read', 'search', 'update', 'reference')),
            query TEXT,
            accessed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            FOREIGN KEY (memory_id) REFERENCES memory_entries(id)
        )
    ''')
    print("✓ Created memory_access_log table")

    conn.commit()


def create_indexes(conn, dry_run: bool = False):
    """Create performance indexes."""
    cursor = conn.cursor()

    indexes = [
        ('idx_memory_type', 'memory_entries(type)'),
        ('idx_memory_source', 'memory_entries(source)'),
        ('idx_memory_created', 'memory_entries(created_at)'),
        ('idx_memory_active', 'memory_entries(is_active)'),
        ('idx_memory_importance', 'memory_entries(importance)'),
        ('idx_daily_logs_date', 'daily_logs(date)'),
        ('idx_access_log_memory', 'memory_access_log(memory_id)'),
        ('idx_access_log_time', 'memory_access_log(accessed_at)')
    ]

    if dry_run:
        print(f"Would create {len(indexes)} indexes")
        return

    for idx_name, idx_def in indexes:
        try:
            cursor.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}')
        except sqlite3.OperationalError:
            pass  # Index might already exist

    print(f"✓ Created {len(indexes)} performance indexes")
    conn.commit()


def verify_migration(conn):
    """Verify the migration was successful."""
    cursor = conn.cursor()

    # Check table exists
    cursor.execute("PRAGMA table_info(memory_entries)")
    columns = cursor.fetchall()
    expected_columns = [
        'id', 'type', 'content', 'content_hash', 'source', 'confidence',
        'importance', 'created_at', 'updated_at', 'last_accessed', 'access_count',
        'embedding', 'embedding_model', 'tags', 'context', 'expires_at', 'is_active'
    ]

    actual_columns = [col[1] for col in columns]
    missing = set(expected_columns) - set(actual_columns)

    if missing:
        print(f"✗ Missing columns: {missing}")
        return False

    # Check entry count
    cursor.execute("SELECT COUNT(*) FROM memory_entries")
    count = cursor.fetchone()[0]
    print(f"✓ memory_entries has {count} entries with {len(actual_columns)} columns")

    # Check auxiliary tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    for table in ['daily_logs', 'memory_access_log']:
        if table in tables:
            print(f"✓ {table} table exists")
        else:
            print(f"✗ {table} table missing")
            return False

    return True


def main():
    parser = argparse.ArgumentParser(description='Memory Database Migration Tool')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would happen without making changes')
    parser.add_argument('--rollback', action='store_true',
                       help='Restore database from backup')
    parser.add_argument('--force', action='store_true',
                       help='Force migration even if schema appears current')

    args = parser.parse_args()

    if args.rollback:
        if rollback_database():
            print("\n✓ Rollback complete")
        else:
            print("\n✗ Rollback failed")
            sys.exit(1)
        return

    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Check if database exists
    if not DB_PATH.exists():
        print(f"Database does not exist at {DB_PATH}")
        print("Creating fresh database with new schema...")

        if args.dry_run:
            print("Would create new database with full schema")
            return

        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Create new schema directly
        cursor.execute('''
            CREATE TABLE memory_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK(type IN ('fact', 'preference', 'event', 'insight', 'task', 'relationship')),
                content TEXT NOT NULL,
                content_hash TEXT UNIQUE,
                source TEXT DEFAULT 'session' CHECK(source IN ('user', 'inferred', 'session', 'external', 'system')),
                confidence REAL DEFAULT 1.0,
                importance INTEGER DEFAULT 5 CHECK(importance BETWEEN 1 AND 10),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_accessed DATETIME,
                access_count INTEGER DEFAULT 0,
                embedding BLOB,
                embedding_model TEXT,
                tags TEXT,
                context TEXT,
                expires_at DATETIME,
                is_active INTEGER DEFAULT 1
            )
        ''')
        print("✓ Created memory_entries table")

        create_auxiliary_tables(conn)
        create_indexes(conn)
        conn.close()

        print("\n✓ Fresh database created successfully")
        return

    # Open existing database
    conn = sqlite3.connect(str(DB_PATH))

    # Check current schema version
    version = check_schema_version(conn)
    print(f"Current schema version: {version}")

    if version == 'new' and not args.force:
        print("Database already has the new schema. Nothing to do.")
        print("Use --force to re-run migration anyway.")
        conn.close()
        return

    if version == 'empty':
        print("Database has no tables. Creating fresh schema...")
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE memory_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK(type IN ('fact', 'preference', 'event', 'insight', 'task', 'relationship')),
                content TEXT NOT NULL,
                content_hash TEXT UNIQUE,
                source TEXT DEFAULT 'session' CHECK(source IN ('user', 'inferred', 'session', 'external', 'system')),
                confidence REAL DEFAULT 1.0,
                importance INTEGER DEFAULT 5 CHECK(importance BETWEEN 1 AND 10),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_accessed DATETIME,
                access_count INTEGER DEFAULT 0,
                embedding BLOB,
                embedding_model TEXT,
                tags TEXT,
                context TEXT,
                expires_at DATETIME,
                is_active INTEGER DEFAULT 1
            )
        ''')
        create_auxiliary_tables(conn, args.dry_run)
        create_indexes(conn, args.dry_run)
        conn.commit()
        conn.close()
        print("\n✓ Fresh database created successfully")
        return

    # We have the old schema - need to migrate
    print("\nStarting migration from old schema to new schema...")

    if not args.dry_run:
        backup_database()

    try:
        migrate_old_to_new(conn, args.dry_run)
        create_auxiliary_tables(conn, args.dry_run)
        create_indexes(conn, args.dry_run)

        if not args.dry_run:
            if verify_migration(conn):
                print("\n✓ Migration completed successfully!")
            else:
                print("\n✗ Migration verification failed")
                print("Run with --rollback to restore from backup")
                sys.exit(1)
        else:
            print("\n[Dry run complete - no changes made]")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        if not args.dry_run:
            print("Run with --rollback to restore from backup")
        conn.close()
        sys.exit(1)

    conn.close()


if __name__ == "__main__":
    main()
