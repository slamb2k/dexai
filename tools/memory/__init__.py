"""
Memory Module - Persistent memory system for DexAI

This module provides persistent memory capabilities:
- MEMORY.md for curated long-term facts/preferences
- Daily logs (memory/logs/YYYY-MM-DD.md) for session notes
- SQLite database for structured storage and search
- Vector embeddings for semantic search
- Hybrid search combining BM25 and vector similarity

Phase 2 additions (External Working Memory for ADHD):
- context_capture.py: Auto-snapshot context on task switches
- context_resume.py: Generate "you were here..." prompts
- commitments.py: Track promises from conversations

Components:
    - memory_db.py: SQLite CRUD operations
    - memory_read.py: Load memory at session start
    - memory_write.py: Write to daily logs and database
    - embed_memory.py: Generate vector embeddings
    - semantic_search.py: Vector similarity search
    - hybrid_search.py: Combined BM25 + vector search
    - context_capture.py: Context snapshot capture (Phase 2)
    - context_resume.py: Context resumption prompts (Phase 2)
    - commitments.py: Commitment tracking (Phase 2)
"""

from .commitments import (
    add_commitment,
    cancel_commitment,
    complete_commitment,
    extract_commitments,
    get_commitment,
    get_due_soon,
    get_overdue,
    list_commitments,
    mark_reminder_sent,
)

# Phase 2: External Working Memory
from .context_capture import (
    capture_context,
    cleanup_snapshots,
    delete_snapshot,
    get_latest_snapshot,
    get_snapshot,
    list_snapshots,
)
from .context_resume import (
    fetch_context,
    resume_context,
)
from .context_resume import (
    get_hardprompt_template as get_resumption_template,
)
from .memory_db import (
    add_daily_log,
    add_entry,
    delete_entry,
    get_daily_log,
    get_entries_without_embeddings,
    get_entry,
    get_recent,
    get_stats,
    list_entries,
    search_entries,
    store_embedding,
    update_entry,
)
from .memory_read import (
    format_as_markdown,
    load_all_memory,
    read_daily_log,
    read_memory_file,
    read_recent_logs,
)
from .memory_write import (
    append_to_daily_log,
    append_to_memory_file,
    sync_log_to_db,
    write_to_memory,
)


__all__ = [
    # Database operations
    "add_entry",
    "get_entry",
    "list_entries",
    "search_entries",
    "update_entry",
    "delete_entry",
    "get_recent",
    "get_stats",
    "add_daily_log",
    "get_daily_log",
    "store_embedding",
    "get_entries_without_embeddings",
    # Read operations
    "read_memory_file",
    "read_daily_log",
    "read_recent_logs",
    "load_all_memory",
    "format_as_markdown",
    # Write operations
    "append_to_daily_log",
    "write_to_memory",
    "append_to_memory_file",
    "sync_log_to_db",
    # Phase 2: Context capture
    "capture_context",
    "list_snapshots",
    "get_snapshot",
    "get_latest_snapshot",
    "cleanup_snapshots",
    "delete_snapshot",
    # Phase 2: Context resume
    "resume_context",
    "fetch_context",
    "get_resumption_template",
    # Phase 2: Commitments
    "add_commitment",
    "list_commitments",
    "get_commitment",
    "complete_commitment",
    "cancel_commitment",
    "get_due_soon",
    "get_overdue",
    "extract_commitments",
    "mark_reminder_sent",
]
