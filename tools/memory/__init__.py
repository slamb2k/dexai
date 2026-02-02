"""
Memory Module - Persistent memory system for the VS_AgentWorkforce

This module provides Moltbot-equivalent persistent memory capabilities:
- MEMORY.md for curated long-term facts/preferences
- Daily logs (memory/logs/YYYY-MM-DD.md) for session notes
- SQLite database for structured storage and search
- Vector embeddings for semantic search
- Hybrid search combining BM25 and vector similarity

Components:
    - memory_db.py: SQLite CRUD operations
    - memory_read.py: Load memory at session start
    - memory_write.py: Write to daily logs and database
    - embed_memory.py: Generate vector embeddings
    - semantic_search.py: Vector similarity search
    - hybrid_search.py: Combined BM25 + vector search
"""

from .memory_db import (
    add_entry,
    get_entry,
    list_entries,
    search_entries,
    update_entry,
    delete_entry,
    get_recent,
    get_stats,
    add_daily_log,
    get_daily_log,
    store_embedding,
    get_entries_without_embeddings
)

from .memory_read import (
    read_memory_file,
    read_daily_log,
    read_recent_logs,
    load_all_memory,
    format_as_markdown
)

from .memory_write import (
    append_to_daily_log,
    write_to_memory,
    append_to_memory_file,
    sync_log_to_db
)

__all__ = [
    # Database operations
    'add_entry',
    'get_entry',
    'list_entries',
    'search_entries',
    'update_entry',
    'delete_entry',
    'get_recent',
    'get_stats',
    'add_daily_log',
    'get_daily_log',
    'store_embedding',
    'get_entries_without_embeddings',
    # Read operations
    'read_memory_file',
    'read_daily_log',
    'read_recent_logs',
    'load_all_memory',
    'format_as_markdown',
    # Write operations
    'append_to_daily_log',
    'write_to_memory',
    'append_to_memory_file',
    'sync_log_to_db',
]
