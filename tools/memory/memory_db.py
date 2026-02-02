"""
Tool: Memory Database Manager
Purpose: SQLite CRUD operations for persistent memory entries with embedding support

This matches Moltbot's memory architecture:
- Markdown files for human-readable memory (MEMORY.md, daily logs)
- SQLite for structured storage and vector search
- Embeddings stored as BLOBs for semantic search

Usage:
    python tools/memory/memory_db.py --action add --type fact --content "User prefers GPT for images"
    python tools/memory/memory_db.py --action add --type preference --content "Dark mode enabled" --source user
    python tools/memory/memory_db.py --action search --query "image generation preferences"
    python tools/memory/memory_db.py --action list [--type fact|preference|event|insight]
    python tools/memory/memory_db.py --action get --id 5
    python tools/memory/memory_db.py --action delete --id 5
    python tools/memory/memory_db.py --action stats
    python tools/memory/memory_db.py --action recent --hours 24

Dependencies:
    - sqlite3 (stdlib)
    - json (stdlib)
    - openai (for embeddings, optional)

Output:
    JSON result with success status and data
"""

import os
import sys
import json
import sqlite3
import argparse
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data" / "memory.db"

# Valid memory types
VALID_TYPES = ['fact', 'preference', 'event', 'insight', 'task', 'relationship']

# Valid sources
VALID_SOURCES = ['user', 'inferred', 'session', 'external', 'system']


def get_connection():
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Main memory entries table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory_entries (
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

    # Daily logs table (syncs with memory/logs/*.md files)
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

    # Memory access history for analytics
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

    # Indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_entries(type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_memory_source ON memory_entries(source)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_memory_created ON memory_entries(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_memory_active ON memory_entries(is_active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_memory_importance ON memory_entries(importance)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_logs_date ON daily_logs(date)')

    conn.commit()
    return conn


def row_to_dict(row) -> Optional[Dict]:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    d = dict(row)
    # Don't include raw embedding blob in output
    if 'embedding' in d and d['embedding']:
        d['has_embedding'] = True
        del d['embedding']
    return d


def compute_content_hash(content: str) -> str:
    """Compute hash of content for deduplication."""
    return hashlib.sha256(content.strip().lower().encode()).hexdigest()[:16]


def add_entry(
    content: str,
    entry_type: str = 'fact',
    source: str = 'session',
    confidence: float = 1.0,
    importance: int = 5,
    tags: Optional[List[str]] = None,
    context: Optional[str] = None,
    expires_at: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add a new memory entry.

    Args:
        content: The memory content
        entry_type: Type of memory (fact, preference, event, insight, task, relationship)
        source: Source of memory (user, inferred, session, external, system)
        confidence: Confidence score 0-1
        importance: Importance level 1-10
        tags: Optional list of tags
        context: Optional context about when/why this was learned
        expires_at: Optional expiration datetime

    Returns:
        dict with success status and entry data
    """
    if entry_type not in VALID_TYPES:
        return {"success": False, "error": f"Invalid type. Must be one of: {VALID_TYPES}"}

    if source not in VALID_SOURCES:
        return {"success": False, "error": f"Invalid source. Must be one of: {VALID_SOURCES}"}

    content_hash = compute_content_hash(content)

    conn = get_connection()
    cursor = conn.cursor()

    # Check for duplicate
    cursor.execute('SELECT id, content FROM memory_entries WHERE content_hash = ?', (content_hash,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return {
            "success": False,
            "error": "Duplicate content already exists",
            "existing_id": existing['id'],
            "existing_content": existing['content']
        }

    tags_json = json.dumps(tags) if tags else None

    cursor.execute('''
        INSERT INTO memory_entries
        (type, content, content_hash, source, confidence, importance, tags, context, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (entry_type, content, content_hash, source, confidence, importance, tags_json, context, expires_at))

    entry_id = cursor.lastrowid
    conn.commit()

    # Fetch the created entry
    cursor.execute('SELECT * FROM memory_entries WHERE id = ?', (entry_id,))
    entry = row_to_dict(cursor.fetchone())

    conn.close()

    return {"success": True, "entry": entry, "message": f"Memory entry created with ID {entry_id}"}


def get_entry(entry_id: int) -> Dict[str, Any]:
    """Get a single memory entry by ID and record access."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM memory_entries WHERE id = ?', (entry_id,))
    entry = row_to_dict(cursor.fetchone())

    if not entry:
        conn.close()
        return {"success": False, "error": f"Memory entry {entry_id} not found"}

    # Update access tracking
    cursor.execute('''
        UPDATE memory_entries
        SET last_accessed = CURRENT_TIMESTAMP, access_count = access_count + 1
        WHERE id = ?
    ''', (entry_id,))

    # Log access
    cursor.execute(
        'INSERT INTO memory_access_log (memory_id, access_type) VALUES (?, ?)',
        (entry_id, 'read')
    )

    conn.commit()
    conn.close()

    return {"success": True, "entry": entry}


def list_entries(
    entry_type: Optional[str] = None,
    source: Optional[str] = None,
    active_only: bool = True,
    limit: int = 100,
    offset: int = 0,
    min_importance: int = 1
) -> Dict[str, Any]:
    """
    List memory entries with optional filters.

    Args:
        entry_type: Filter by type
        source: Filter by source
        active_only: Only show active entries
        limit: Max results
        offset: Pagination offset
        min_importance: Minimum importance level

    Returns:
        dict with entries array
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []

    if entry_type:
        if entry_type not in VALID_TYPES:
            conn.close()
            return {"success": False, "error": f"Invalid type. Must be one of: {VALID_TYPES}"}
        conditions.append('type = ?')
        params.append(entry_type)

    if source:
        if source not in VALID_SOURCES:
            conn.close()
            return {"success": False, "error": f"Invalid source. Must be one of: {VALID_SOURCES}"}
        conditions.append('source = ?')
        params.append(source)

    if active_only:
        conditions.append('is_active = 1')
        conditions.append('(expires_at IS NULL OR expires_at > datetime("now"))')

    conditions.append('importance >= ?')
    params.append(min_importance)

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    cursor.execute(f'''
        SELECT * FROM memory_entries
        WHERE {where_clause}
        ORDER BY importance DESC, created_at DESC
        LIMIT ? OFFSET ?
    ''', params + [limit, offset])

    entries = [row_to_dict(row) for row in cursor.fetchall()]

    # Get total count
    cursor.execute(f'SELECT COUNT(*) as count FROM memory_entries WHERE {where_clause}', params)
    total = cursor.fetchone()['count']

    conn.close()

    return {"success": True, "entries": entries, "total": total, "limit": limit, "offset": offset}


def search_entries(
    query: str,
    entry_type: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Search memory entries by text (basic full-text search).
    For semantic search, use semantic_search.py which uses embeddings.

    Args:
        query: Search query
        entry_type: Optional type filter
        limit: Max results

    Returns:
        dict with matching entries
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Simple LIKE search (for basic text matching)
    search_pattern = f'%{query}%'

    if entry_type:
        cursor.execute('''
            SELECT * FROM memory_entries
            WHERE is_active = 1
            AND type = ?
            AND (content LIKE ? OR tags LIKE ? OR context LIKE ?)
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
        ''', (entry_type, search_pattern, search_pattern, search_pattern, limit))
    else:
        cursor.execute('''
            SELECT * FROM memory_entries
            WHERE is_active = 1
            AND (content LIKE ? OR tags LIKE ? OR context LIKE ?)
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
        ''', (search_pattern, search_pattern, search_pattern, limit))

    entries = [row_to_dict(row) for row in cursor.fetchall()]

    # Log search
    for entry in entries:
        cursor.execute(
            'INSERT INTO memory_access_log (memory_id, access_type, query) VALUES (?, ?, ?)',
            (entry['id'], 'search', query)
        )

    conn.commit()
    conn.close()

    return {"success": True, "entries": entries, "query": query, "count": len(entries)}


def update_entry(entry_id: int, **kwargs) -> Dict[str, Any]:
    """
    Update a memory entry.

    Args:
        entry_id: Entry ID to update
        **kwargs: Fields to update

    Returns:
        dict with updated entry
    """
    allowed_fields = ['content', 'type', 'source', 'confidence', 'importance', 'tags', 'context', 'expires_at', 'is_active']

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM memory_entries WHERE id = ?', (entry_id,))
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Memory entry {entry_id} not found"}

    updates = []
    values = []

    for field, value in kwargs.items():
        if field in allowed_fields:
            if field == 'type' and value not in VALID_TYPES:
                conn.close()
                return {"success": False, "error": f"Invalid type. Must be one of: {VALID_TYPES}"}
            if field == 'source' and value not in VALID_SOURCES:
                conn.close()
                return {"success": False, "error": f"Invalid source. Must be one of: {VALID_SOURCES}"}
            if field == 'tags' and isinstance(value, list):
                value = json.dumps(value)
            if field == 'content':
                # Update content hash too
                updates.append('content_hash = ?')
                values.append(compute_content_hash(value))
            updates.append(f'{field} = ?')
            values.append(value)

    if not updates:
        conn.close()
        return {"success": False, "error": "No valid fields to update"}

    updates.append('updated_at = CURRENT_TIMESTAMP')
    values.append(entry_id)

    cursor.execute(f'UPDATE memory_entries SET {", ".join(updates)} WHERE id = ?', values)
    conn.commit()

    # Log update
    cursor.execute(
        'INSERT INTO memory_access_log (memory_id, access_type) VALUES (?, ?)',
        (entry_id, 'update')
    )
    conn.commit()

    # Fetch updated entry
    cursor.execute('SELECT * FROM memory_entries WHERE id = ?', (entry_id,))
    entry = row_to_dict(cursor.fetchone())

    conn.close()

    return {"success": True, "entry": entry, "message": f"Memory entry {entry_id} updated"}


def delete_entry(entry_id: int, soft_delete: bool = True) -> Dict[str, Any]:
    """
    Delete a memory entry.

    Args:
        entry_id: Entry ID to delete
        soft_delete: If True, just mark as inactive. If False, permanently delete.

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM memory_entries WHERE id = ?', (entry_id,))
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Memory entry {entry_id} not found"}

    if soft_delete:
        cursor.execute('UPDATE memory_entries SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (entry_id,))
        message = f"Memory entry {entry_id} marked as inactive"
    else:
        cursor.execute('DELETE FROM memory_access_log WHERE memory_id = ?', (entry_id,))
        cursor.execute('DELETE FROM memory_entries WHERE id = ?', (entry_id,))
        message = f"Memory entry {entry_id} permanently deleted"

    conn.commit()
    conn.close()

    return {"success": True, "message": message}


def get_recent(hours: int = 24, entry_type: Optional[str] = None) -> Dict[str, Any]:
    """Get memory entries from the last N hours."""
    conn = get_connection()
    cursor = conn.cursor()

    cutoff = datetime.now() - timedelta(hours=hours)

    if entry_type:
        cursor.execute('''
            SELECT * FROM memory_entries
            WHERE is_active = 1 AND type = ? AND created_at >= ?
            ORDER BY created_at DESC
        ''', (entry_type, cutoff.isoformat()))
    else:
        cursor.execute('''
            SELECT * FROM memory_entries
            WHERE is_active = 1 AND created_at >= ?
            ORDER BY created_at DESC
        ''', (cutoff.isoformat(),))

    entries = [row_to_dict(row) for row in cursor.fetchall()]

    conn.close()

    return {"success": True, "entries": entries, "count": len(entries), "hours": hours}


def get_stats() -> Dict[str, Any]:
    """Get memory statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    # Count by type
    cursor.execute('''
        SELECT type, COUNT(*) as count
        FROM memory_entries
        WHERE is_active = 1
        GROUP BY type
    ''')
    by_type = {row['type']: row['count'] for row in cursor.fetchall()}

    # Count by source
    cursor.execute('''
        SELECT source, COUNT(*) as count
        FROM memory_entries
        WHERE is_active = 1
        GROUP BY source
    ''')
    by_source = {row['source']: row['count'] for row in cursor.fetchall()}

    # Total counts
    cursor.execute('SELECT COUNT(*) as total FROM memory_entries WHERE is_active = 1')
    total_active = cursor.fetchone()['total']

    cursor.execute('SELECT COUNT(*) as total FROM memory_entries WHERE is_active = 0')
    total_inactive = cursor.fetchone()['total']

    # Entries with embeddings
    cursor.execute('SELECT COUNT(*) as count FROM memory_entries WHERE embedding IS NOT NULL AND is_active = 1')
    with_embeddings = cursor.fetchone()['count']

    # Most accessed
    cursor.execute('''
        SELECT id, content, access_count
        FROM memory_entries
        WHERE is_active = 1
        ORDER BY access_count DESC
        LIMIT 5
    ''')
    most_accessed = [row_to_dict(row) for row in cursor.fetchall()]

    # Daily log count
    cursor.execute('SELECT COUNT(*) as count FROM daily_logs')
    daily_log_count = cursor.fetchone()['count']

    conn.close()

    return {
        "success": True,
        "stats": {
            "total_active": total_active,
            "total_inactive": total_inactive,
            "by_type": by_type,
            "by_source": by_source,
            "with_embeddings": with_embeddings,
            "daily_logs": daily_log_count,
            "most_accessed": most_accessed
        }
    }


def add_daily_log(date: str, summary: str, raw_log: str, key_events: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Add or update a daily log entry.

    Args:
        date: Date string (YYYY-MM-DD)
        summary: Summary of the day
        raw_log: Full log content
        key_events: List of key events

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    key_events_json = json.dumps(key_events) if key_events else None

    # Upsert
    cursor.execute('''
        INSERT INTO daily_logs (date, summary, raw_log, key_events, entry_count)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            summary = excluded.summary,
            raw_log = excluded.raw_log,
            key_events = excluded.key_events,
            entry_count = entry_count + 1,
            updated_at = CURRENT_TIMESTAMP
    ''', (date, summary, raw_log, key_events_json, 1))

    conn.commit()

    cursor.execute('SELECT * FROM daily_logs WHERE date = ?', (date,))
    log = row_to_dict(cursor.fetchone())

    conn.close()

    return {"success": True, "log": log, "message": f"Daily log for {date} saved"}


def get_daily_log(date: str) -> Dict[str, Any]:
    """Get a daily log by date."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM daily_logs WHERE date = ?', (date,))
    log = row_to_dict(cursor.fetchone())

    conn.close()

    if not log:
        return {"success": False, "error": f"No daily log found for {date}"}

    return {"success": True, "log": log}


def store_embedding(entry_id: int, embedding: bytes, model: str = 'text-embedding-3-small') -> Dict[str, Any]:
    """
    Store an embedding for a memory entry.
    Called by embed_memory.py after generating embeddings.

    Args:
        entry_id: Memory entry ID
        embedding: Embedding bytes
        model: Model used to generate embedding

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE memory_entries
        SET embedding = ?, embedding_model = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (embedding, model, entry_id))

    conn.commit()
    conn.close()

    return {"success": True, "message": f"Embedding stored for entry {entry_id}"}


def get_entries_without_embeddings(limit: int = 50) -> Dict[str, Any]:
    """Get entries that don't have embeddings yet."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, content, type
        FROM memory_entries
        WHERE embedding IS NULL AND is_active = 1
        ORDER BY importance DESC, created_at DESC
        LIMIT ?
    ''', (limit,))

    entries = [row_to_dict(row) for row in cursor.fetchall()]

    conn.close()

    return {"success": True, "entries": entries, "count": len(entries)}


def main():
    parser = argparse.ArgumentParser(description='Memory Database Manager')
    parser.add_argument('--action', required=True,
                       choices=['add', 'get', 'list', 'search', 'update', 'delete',
                               'recent', 'stats', 'add-log', 'get-log', 'needs-embedding'],
                       help='Action to perform')
    parser.add_argument('--id', type=int, help='Entry ID')
    parser.add_argument('--content', help='Memory content')
    parser.add_argument('--type', help='Memory type (fact, preference, event, insight, task, relationship)')
    parser.add_argument('--source', default='session', help='Source (user, inferred, session, external, system)')
    parser.add_argument('--confidence', type=float, default=1.0, help='Confidence score 0-1')
    parser.add_argument('--importance', type=int, default=5, help='Importance level 1-10')
    parser.add_argument('--tags', help='Comma-separated tags')
    parser.add_argument('--context', help='Context about when/why this was learned')
    parser.add_argument('--query', help='Search query')
    parser.add_argument('--hours', type=int, default=24, help='Hours for recent entries')
    parser.add_argument('--date', help='Date for daily log (YYYY-MM-DD)')
    parser.add_argument('--summary', help='Summary for daily log')
    parser.add_argument('--raw-log', help='Raw log content')
    parser.add_argument('--limit', type=int, default=100, help='Limit for list')
    parser.add_argument('--offset', type=int, default=0, help='Offset for list')
    parser.add_argument('--hard-delete', action='store_true', help='Permanently delete instead of soft delete')

    args = parser.parse_args()

    result = None

    if args.action == 'add':
        if not args.content:
            print("Error: --content required for add action")
            sys.exit(1)
        tags = args.tags.split(',') if args.tags else None
        result = add_entry(
            content=args.content,
            entry_type=args.type or 'fact',
            source=args.source,
            confidence=args.confidence,
            importance=args.importance,
            tags=tags,
            context=args.context
        )

    elif args.action == 'get':
        if not args.id:
            print("Error: --id required for get action")
            sys.exit(1)
        result = get_entry(args.id)

    elif args.action == 'list':
        result = list_entries(
            entry_type=args.type,
            source=args.source,
            limit=args.limit,
            offset=args.offset
        )

    elif args.action == 'search':
        if not args.query:
            print("Error: --query required for search action")
            sys.exit(1)
        result = search_entries(args.query, entry_type=args.type, limit=args.limit)

    elif args.action == 'update':
        if not args.id:
            print("Error: --id required for update action")
            sys.exit(1)
        kwargs = {}
        if args.content:
            kwargs['content'] = args.content
        if args.type:
            kwargs['type'] = args.type
        if args.source:
            kwargs['source'] = args.source
        if args.tags:
            kwargs['tags'] = args.tags.split(',')
        if args.context:
            kwargs['context'] = args.context
        if args.importance:
            kwargs['importance'] = args.importance
        result = update_entry(args.id, **kwargs)

    elif args.action == 'delete':
        if not args.id:
            print("Error: --id required for delete action")
            sys.exit(1)
        result = delete_entry(args.id, soft_delete=not args.hard_delete)

    elif args.action == 'recent':
        result = get_recent(hours=args.hours, entry_type=args.type)

    elif args.action == 'stats':
        result = get_stats()

    elif args.action == 'add-log':
        if not args.date or not args.summary:
            print("Error: --date and --summary required for add-log action")
            sys.exit(1)
        result = add_daily_log(
            date=args.date,
            summary=args.summary,
            raw_log=args.raw_log or args.summary
        )

    elif args.action == 'get-log':
        if not args.date:
            print("Error: --date required for get-log action")
            sys.exit(1)
        result = get_daily_log(args.date)

    elif args.action == 'needs-embedding':
        result = get_entries_without_embeddings(limit=args.limit)

    if result:
        if result.get('success'):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
