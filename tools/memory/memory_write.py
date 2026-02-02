"""
Tool: Memory Writer
Purpose: Append to daily logs and add entries to SQLite database

This tool handles the "write" side of persistent memory:
- Append events/notes to today's daily log (memory/logs/YYYY-MM-DD.md)
- Add structured entries to SQLite for searchability
- Sync between markdown files and database

Usage:
    python tools/memory/memory_write.py --content "User prefers GPT for images"
    python tools/memory/memory_write.py --content "Had meeting about X" --type event
    python tools/memory/memory_write.py --content "Learned that Y" --type insight --importance 8
    python tools/memory/memory_write.py --log-only --content "Quick note"  # Only to daily log
    python tools/memory/memory_write.py --db-only --content "Structured fact"  # Only to SQLite
    python tools/memory/memory_write.py --update-memory "New preference line"  # Append to MEMORY.md

Dependencies:
    - pathlib (stdlib)
    - json (stdlib)
    - datetime (stdlib)

Output:
    JSON result with success status
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Paths
MEMORY_DIR = Path(__file__).parent.parent.parent / "memory"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
LOGS_DIR = MEMORY_DIR / "logs"

# Import memory_db functions
sys.path.insert(0, str(Path(__file__).parent))
try:
    from memory_db import add_entry, add_daily_log as db_add_daily_log
except ImportError:
    def add_entry(**kwargs):
        return {"success": False, "error": "memory_db not available"}
    def db_add_daily_log(**kwargs):
        return {"success": False, "error": "memory_db not available"}


def ensure_directories():
    """Ensure memory directories exist."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_today_log_path() -> Path:
    """Get path to today's daily log file."""
    today = datetime.now().strftime('%Y-%m-%d')
    return LOGS_DIR / f"{today}.md"


def append_to_daily_log(
    content: str,
    entry_type: str = 'note',
    timestamp: bool = True,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """
    Append an entry to today's daily log file.

    Args:
        content: The content to append
        entry_type: Type of entry (note, event, insight, task, etc.)
        timestamp: Whether to include timestamp
        category: Optional category tag

    Returns:
        dict with success status
    """
    ensure_directories()
    log_path = get_today_log_path()
    today = datetime.now().strftime('%Y-%m-%d')

    # Create file with header if it doesn't exist
    if not log_path.exists():
        header = f"""# Daily Log: {today}

> Session log for {datetime.now().strftime('%A, %B %d, %Y')}

---

## Events & Notes

"""
        log_path.write_text(header, encoding='utf-8')

    # Format the entry
    time_str = datetime.now().strftime('%H:%M') if timestamp else ''
    type_prefix = f"[{entry_type}]" if entry_type != 'note' else ''
    category_tag = f" #{category}" if category else ''

    if timestamp:
        entry_line = f"- {time_str} {type_prefix} {content}{category_tag}\n"
    else:
        entry_line = f"- {type_prefix} {content}{category_tag}\n"

    # Append to file
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(entry_line)

    return {
        "success": True,
        "path": str(log_path),
        "date": today,
        "entry": entry_line.strip(),
        "message": f"Appended to daily log for {today}"
    }


def write_to_memory(
    content: str,
    entry_type: str = 'fact',
    source: str = 'session',
    importance: int = 5,
    tags: Optional[List[str]] = None,
    context: Optional[str] = None,
    log_to_file: bool = True,
    add_to_db: bool = True
) -> Dict[str, Any]:
    """
    Write to both daily log and SQLite database.

    Args:
        content: Memory content
        entry_type: Type (fact, preference, event, insight, task, relationship)
        source: Source (user, inferred, session, external, system)
        importance: Importance level 1-10
        tags: Optional tags
        context: Optional context
        log_to_file: Whether to append to daily log
        add_to_db: Whether to add to SQLite

    Returns:
        dict with results from both operations
    """
    results = {
        "success": True,
        "log_result": None,
        "db_result": None
    }

    # Append to daily log
    if log_to_file:
        log_result = append_to_daily_log(
            content=content,
            entry_type=entry_type,
            category=tags[0] if tags else None
        )
        results["log_result"] = log_result
        if not log_result.get('success'):
            results["success"] = False

    # Add to SQLite
    if add_to_db:
        db_result = add_entry(
            content=content,
            entry_type=entry_type,
            source=source,
            importance=importance,
            tags=tags,
            context=context
        )
        results["db_result"] = db_result
        # Don't fail if it's a duplicate - that's expected
        if not db_result.get('success') and 'Duplicate' not in db_result.get('error', ''):
            results["success"] = False

    return results


def append_to_memory_file(
    content: str,
    section: str = 'key_facts'
) -> Dict[str, Any]:
    """
    Append a line to a specific section in MEMORY.md.
    Use sparingly - for truly persistent facts that should always be loaded.

    Args:
        content: Content to append
        section: Section name (user_preferences, key_facts, learned_behaviors, etc.)

    Returns:
        dict with success status
    """
    if not MEMORY_FILE.exists():
        return {"success": False, "error": "MEMORY.md does not exist"}

    full_content = MEMORY_FILE.read_text(encoding='utf-8')

    # Find the section and append
    section_header = f"## {section.replace('_', ' ').title()}"
    lines = full_content.split('\n')
    new_lines = []
    found_section = False
    inserted = False

    for i, line in enumerate(lines):
        new_lines.append(line)

        # Found our section
        if line.strip().lower() == section_header.lower():
            found_section = True
            continue

        # We're in our section, look for the next section or end
        if found_section and not inserted:
            # Check if this is a new section or blank line before next section
            if line.startswith('## ') or (line.strip() == '' and i + 1 < len(lines) and lines[i + 1].startswith('## ')):
                # Insert before this line
                new_lines.insert(-1, f"- {content}")
                inserted = True
            elif line.strip() == '---':
                # Insert before horizontal rule
                new_lines.insert(-1, f"- {content}")
                inserted = True

    # If we found the section but didn't insert (section is at end)
    if found_section and not inserted:
        new_lines.append(f"- {content}")
        inserted = True

    if not found_section:
        return {"success": False, "error": f"Section '{section}' not found in MEMORY.md"}

    # Update the last modified line
    for i, line in enumerate(new_lines):
        if line.startswith('*Last updated:'):
            new_lines[i] = f"*Last updated: {datetime.now().strftime('%Y-%m-%d')}*"
            break

    # Write back
    MEMORY_FILE.write_text('\n'.join(new_lines), encoding='utf-8')

    return {
        "success": True,
        "path": str(MEMORY_FILE),
        "section": section,
        "content": content,
        "message": f"Appended to {section} in MEMORY.md"
    }


def sync_log_to_db(date: Optional[str] = None) -> Dict[str, Any]:
    """
    Sync a daily log file to the SQLite database.

    Args:
        date: Date string (YYYY-MM-DD), defaults to today

    Returns:
        dict with sync results
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')

    log_path = LOGS_DIR / f"{date}.md"

    if not log_path.exists():
        return {"success": False, "error": f"No log file for {date}"}

    content = log_path.read_text(encoding='utf-8')

    # Extract key events (lines starting with - or *)
    key_events = []
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('- ') or line.startswith('* '):
            key_events.append(line[2:])

    # Create summary (first non-header, non-empty line or first event)
    summary = key_events[0] if key_events else f"Log for {date}"

    # Sync to DB
    result = db_add_daily_log(
        date=date,
        summary=summary,
        raw_log=content,
        key_events=key_events
    )

    return {
        "success": result.get('success', False),
        "date": date,
        "events_found": len(key_events),
        "db_result": result
    }


def main():
    parser = argparse.ArgumentParser(description='Memory Writer - Write to persistent memory')
    parser.add_argument('--content', required=True, help='Content to write')
    parser.add_argument('--type', default='fact',
                       choices=['fact', 'preference', 'event', 'insight', 'task', 'relationship', 'note'],
                       help='Type of memory entry')
    parser.add_argument('--source', default='session',
                       choices=['user', 'inferred', 'session', 'external', 'system'],
                       help='Source of the memory')
    parser.add_argument('--importance', type=int, default=5, help='Importance level 1-10')
    parser.add_argument('--tags', help='Comma-separated tags')
    parser.add_argument('--context', help='Context about when/why this was learned')

    parser.add_argument('--log-only', action='store_true', help='Only write to daily log file')
    parser.add_argument('--db-only', action='store_true', help='Only write to SQLite database')
    parser.add_argument('--update-memory', action='store_true',
                       help='Append to MEMORY.md instead of daily log')
    parser.add_argument('--section', default='key_facts',
                       help='Section in MEMORY.md to append to')
    parser.add_argument('--no-timestamp', action='store_true', help='Omit timestamp in daily log')
    parser.add_argument('--sync', help='Sync a daily log to DB (date: YYYY-MM-DD)')

    args = parser.parse_args()

    result = None

    # Handle sync operation
    if args.sync:
        result = sync_log_to_db(args.sync)

    # Handle MEMORY.md update
    elif args.update_memory:
        result = append_to_memory_file(args.content, args.section)

    # Handle normal write
    else:
        tags = args.tags.split(',') if args.tags else None

        # Determine what to write to
        log_to_file = not args.db_only
        add_to_db = not args.log_only

        # Handle 'note' type specially - only goes to log
        if args.type == 'note':
            result = append_to_daily_log(
                content=args.content,
                entry_type='note',
                timestamp=not args.no_timestamp,
                category=tags[0] if tags else None
            )
        else:
            result = write_to_memory(
                content=args.content,
                entry_type=args.type,
                source=args.source,
                importance=args.importance,
                tags=tags,
                context=args.context,
                log_to_file=log_to_file,
                add_to_db=add_to_db
            )

    if result:
        if result.get('success'):
            print(f"OK {result.get('message', 'Memory written successfully')}")
        else:
            print(f"ERROR {result.get('error', 'Unknown error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
