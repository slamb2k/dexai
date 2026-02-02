"""
Tool: Memory Reader
Purpose: Load persistent memory at session start (MEMORY.md + recent daily logs)

This matches Moltbot's memory loading pattern:
- Read MEMORY.md for curated long-term facts/preferences
- Read today's daily log
- Read yesterday's daily log (for continuity)
- Optionally load recent entries from SQLite

Usage:
    python tools/memory/memory_read.py                    # Load all memory context
    python tools/memory/memory_read.py --memory-only      # Just MEMORY.md
    python tools/memory/memory_read.py --logs-only        # Just daily logs
    python tools/memory/memory_read.py --days 3           # Include 3 days of logs
    python tools/memory/memory_read.py --include-db       # Also include SQLite entries
    python tools/memory/memory_read.py --format markdown  # Output as markdown
    python tools/memory/memory_read.py --format json      # Output as JSON

Dependencies:
    - pathlib (stdlib)
    - json (stdlib)
    - datetime (stdlib)

Output:
    Combined memory context ready for LLM injection
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

# Paths
MEMORY_DIR = Path(__file__).parent.parent.parent / "memory"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
LOGS_DIR = MEMORY_DIR / "logs"

# Import memory_db functions
sys.path.insert(0, str(Path(__file__).parent))
try:
    from memory_db import get_recent, list_entries, get_daily_log
except ImportError:
    # Fallback if running standalone
    def get_recent(hours=24, entry_type=None):
        return {"success": False, "entries": []}
    def list_entries(**kwargs):
        return {"success": False, "entries": []}
    def get_daily_log(date):
        return {"success": False}


def read_memory_file() -> Dict[str, Any]:
    """
    Read the main MEMORY.md file.

    Returns:
        dict with content and metadata
    """
    if not MEMORY_FILE.exists():
        return {
            "success": False,
            "error": f"MEMORY.md not found at {MEMORY_FILE}",
            "content": None
        }

    content = MEMORY_FILE.read_text(encoding='utf-8')

    # Parse sections (simple parsing)
    sections = {}
    current_section = "preamble"
    current_content = []

    for line in content.split('\n'):
        if line.startswith('## '):
            if current_content:
                sections[current_section] = '\n'.join(current_content).strip()
            current_section = line[3:].strip().lower().replace(' ', '_')
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        sections[current_section] = '\n'.join(current_content).strip()

    return {
        "success": True,
        "path": str(MEMORY_FILE),
        "content": content,
        "sections": sections,
        "last_modified": datetime.fromtimestamp(MEMORY_FILE.stat().st_mtime).isoformat()
    }


def read_daily_log(date: str) -> Dict[str, Any]:
    """
    Read a daily log file.

    Args:
        date: Date string (YYYY-MM-DD)

    Returns:
        dict with content and metadata
    """
    log_file = LOGS_DIR / f"{date}.md"

    if not log_file.exists():
        # Try SQLite
        db_result = get_daily_log(date)
        if db_result.get('success'):
            return {
                "success": True,
                "date": date,
                "source": "database",
                "content": db_result['log'].get('raw_log', ''),
                "summary": db_result['log'].get('summary', ''),
                "key_events": json.loads(db_result['log'].get('key_events', '[]') or '[]')
            }
        return {
            "success": False,
            "date": date,
            "error": f"No log found for {date}"
        }

    content = log_file.read_text(encoding='utf-8')

    # Extract key events (lines starting with - or *)
    key_events = []
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('- ') or line.startswith('* '):
            key_events.append(line[2:])

    return {
        "success": True,
        "date": date,
        "source": "file",
        "path": str(log_file),
        "content": content,
        "key_events": key_events,
        "last_modified": datetime.fromtimestamp(log_file.stat().st_mtime).isoformat()
    }


def read_recent_logs(days: int = 2) -> List[Dict[str, Any]]:
    """
    Read the most recent daily logs.

    Args:
        days: Number of days to include (default: 2 for today + yesterday)

    Returns:
        List of log results
    """
    logs = []
    today = datetime.now().date()

    for i in range(days):
        date = (today - timedelta(days=i)).isoformat()
        log = read_daily_log(date)
        logs.append(log)

    return logs


def read_db_entries(
    hours: int = 24,
    entry_type: Optional[str] = None,
    min_importance: int = 5
) -> List[Dict[str, Any]]:
    """
    Read recent entries from SQLite database.

    Args:
        hours: Hours to look back
        entry_type: Optional type filter
        min_importance: Minimum importance level

    Returns:
        List of entries
    """
    result = list_entries(
        entry_type=entry_type,
        min_importance=min_importance,
        limit=50
    )

    if result.get('success'):
        return result.get('entries', [])
    return []


def load_all_memory(
    include_memory: bool = True,
    include_logs: bool = True,
    include_db: bool = False,
    log_days: int = 2,
    db_hours: int = 24,
    min_importance: int = 5
) -> Dict[str, Any]:
    """
    Load all memory context for session start.

    Args:
        include_memory: Include MEMORY.md
        include_logs: Include daily logs
        include_db: Include SQLite entries
        log_days: Number of days of logs
        db_hours: Hours of DB entries
        min_importance: Min importance for DB entries

    Returns:
        Combined memory context
    """
    result = {
        "success": True,
        "loaded_at": datetime.now().isoformat(),
        "memory_file": None,
        "daily_logs": [],
        "db_entries": [],
        "summary": {}
    }

    # Load MEMORY.md
    if include_memory:
        memory = read_memory_file()
        result["memory_file"] = memory
        if memory.get('success'):
            result["summary"]["memory_sections"] = list(memory.get('sections', {}).keys())

    # Load daily logs
    if include_logs:
        logs = read_recent_logs(days=log_days)
        result["daily_logs"] = logs
        result["summary"]["logs_loaded"] = len([l for l in logs if l.get('success')])
        result["summary"]["log_dates"] = [l.get('date') for l in logs if l.get('success')]

    # Load DB entries
    if include_db:
        entries = read_db_entries(hours=db_hours, min_importance=min_importance)
        result["db_entries"] = entries
        result["summary"]["db_entries_loaded"] = len(entries)

    return result


def format_as_markdown(memory_context: Dict[str, Any]) -> str:
    """
    Format memory context as markdown for LLM injection.

    Args:
        memory_context: Result from load_all_memory()

    Returns:
        Markdown string
    """
    parts = []

    # MEMORY.md content
    if memory_context.get('memory_file', {}).get('success'):
        parts.append("# Persistent Memory\n")
        parts.append(memory_context['memory_file']['content'])
        parts.append("\n---\n")

    # Daily logs
    for log in memory_context.get('daily_logs', []):
        if log.get('success'):
            parts.append(f"## Daily Log: {log['date']}\n")
            if log.get('content'):
                parts.append(log['content'])
            elif log.get('summary'):
                parts.append(f"**Summary:** {log['summary']}")
                if log.get('key_events'):
                    parts.append("\n**Key Events:**")
                    for event in log['key_events']:
                        parts.append(f"- {event}")
            parts.append("\n")

    # DB entries (if included)
    if memory_context.get('db_entries'):
        parts.append("## Recent Memory Entries\n")
        for entry in memory_context['db_entries']:
            parts.append(f"- [{entry.get('type', 'fact')}] {entry.get('content')}")
        parts.append("\n")

    return '\n'.join(parts)


def format_as_json(memory_context: Dict[str, Any]) -> str:
    """Format memory context as JSON."""
    return json.dumps(memory_context, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(description='Memory Reader - Load persistent memory at session start')
    parser.add_argument('--memory-only', action='store_true', help='Only load MEMORY.md')
    parser.add_argument('--logs-only', action='store_true', help='Only load daily logs')
    parser.add_argument('--include-db', action='store_true', help='Include SQLite entries')
    parser.add_argument('--days', type=int, default=2, help='Days of logs to include')
    parser.add_argument('--db-hours', type=int, default=24, help='Hours of DB entries')
    parser.add_argument('--min-importance', type=int, default=5, help='Min importance for DB entries')
    parser.add_argument('--format', choices=['markdown', 'json', 'summary'], default='markdown',
                       help='Output format')
    parser.add_argument('--quiet', action='store_true', help='Suppress status messages')

    args = parser.parse_args()

    # Determine what to load
    include_memory = not args.logs_only
    include_logs = not args.memory_only

    # Load memory
    context = load_all_memory(
        include_memory=include_memory,
        include_logs=include_logs,
        include_db=args.include_db,
        log_days=args.days,
        db_hours=args.db_hours,
        min_importance=args.min_importance
    )

    # Format output
    if args.format == 'markdown':
        output = format_as_markdown(context)
        if not args.quiet:
            summary = context.get('summary', {})
            print(f"# Memory loaded: {summary.get('memory_sections', [])} sections, "
                  f"{summary.get('logs_loaded', 0)} logs", file=sys.stderr)
        print(output)

    elif args.format == 'json':
        print(format_as_json(context))

    elif args.format == 'summary':
        summary = context.get('summary', {})
        print(json.dumps({
            "success": True,
            "loaded_at": context.get('loaded_at'),
            "memory_file_loaded": context.get('memory_file', {}).get('success', False),
            "memory_sections": summary.get('memory_sections', []),
            "logs_loaded": summary.get('logs_loaded', 0),
            "log_dates": summary.get('log_dates', []),
            "db_entries_loaded": summary.get('db_entries_loaded', 0)
        }, indent=2))


if __name__ == "__main__":
    main()
