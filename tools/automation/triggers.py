"""
Tool: Event Triggers
Purpose: React to file changes and webhooks

Features:
- File watcher with glob patterns
- Webhook endpoint for external events
- Debouncing to prevent rapid-fire triggers
- Trigger-to-job mapping

Usage:
    python tools/automation/triggers.py --action create --name inbox_watch \
        --type file --target ".tmp/inbox/*.txt" --job process_inbox
    python tools/automation/triggers.py --action list
    python tools/automation/triggers.py --action fire --name inbox_watch

Dependencies:
    - watchdog>=4.0.0 (file system watching)
    - pyyaml
"""

import os
import sys
import json
import sqlite3
import argparse
import uuid
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from fnmatch import fnmatch

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.automation import DB_PATH, CONFIG_PATH

# Try to import watchdog for file watching
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # Define a dummy base class when watchdog isn't available
    class FileSystemEventHandler:
        pass

# Valid trigger types
VALID_TRIGGER_TYPES = ['file', 'webhook']


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    default_config = {
        'triggers': {
            'enabled': True,
            'file_watcher': {
                'enabled': True,
                'watch_dirs': ['workspace', '.tmp/inbox'],
                'ignore_patterns': ['*.swp', '*.tmp', '.*', '__pycache__', '*.pyc'],
                'debounce_seconds': 5
            },
            'webhook': {
                'enabled': False,
                'port': 18790,
                'host': '127.0.0.1',
                'secret_env_var': 'WEBHOOK_SECRET'
            }
        }
    }

    if not CONFIG_PATH.exists():
        return default_config

    try:
        import yaml
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        return config if config else default_config
    except Exception:
        return default_config


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Triggers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS triggers (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            trigger_type TEXT CHECK(trigger_type IN ('file', 'webhook')) NOT NULL,
            target TEXT NOT NULL,
            job_id TEXT,
            action TEXT,
            enabled INTEGER DEFAULT 1,
            debounce_seconds INTEGER DEFAULT 5,
            last_fired DATETIME,
            fire_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_triggers_enabled ON triggers(enabled)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_triggers_type ON triggers(trigger_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_triggers_target ON triggers(target)')

    conn.commit()
    return conn


def create_trigger(
    name: str,
    trigger_type: str,
    target: str,
    job_id: Optional[str] = None,
    action: Optional[str] = None,
    debounce_seconds: int = 5,
    enabled: bool = True
) -> Dict[str, Any]:
    """
    Create a new event trigger.

    Args:
        name: Unique trigger name
        trigger_type: 'file' or 'webhook'
        target: Path pattern for file triggers, or endpoint for webhooks
        job_id: Job to execute when triggered (optional)
        action: Ad-hoc action/task to perform (optional, alternative to job_id)
        debounce_seconds: Minimum seconds between fires
        enabled: Whether trigger is active

    Returns:
        dict with success status and trigger details
    """
    if trigger_type not in VALID_TRIGGER_TYPES:
        return {
            "success": False,
            "error": f"Invalid trigger_type: {trigger_type}. Must be one of {VALID_TRIGGER_TYPES}"
        }

    if not job_id and not action:
        return {
            "success": False,
            "error": "Either job_id or action must be provided"
        }

    trigger_id = str(uuid.uuid4())

    conn = get_connection()
    cursor = conn.cursor()

    # Verify job exists if job_id provided
    if job_id:
        cursor.execute('SELECT id FROM jobs WHERE id = ? OR name = ?', (job_id, job_id))
        job_row = cursor.fetchone()
        if not job_row:
            conn.close()
            return {"success": False, "error": f"Job '{job_id}' not found"}
        job_id = job_row['id']  # Normalize to ID

    try:
        cursor.execute('''
            INSERT INTO triggers (id, name, trigger_type, target, job_id, action,
                                 debounce_seconds, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (trigger_id, name, trigger_type, target, job_id, action,
              debounce_seconds, 1 if enabled else 0))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return {"success": False, "error": f"Trigger with name '{name}' already exists"}

    conn.close()

    # Log to audit
    try:
        from tools.security import audit
        audit.log_event(
            event_type='system',
            action='trigger_created',
            resource=f"trigger:{name}",
            status='success',
            details={'trigger_type': trigger_type, 'target': target}
        )
    except Exception:
        pass

    return {
        "success": True,
        "trigger_id": trigger_id,
        "name": name,
        "trigger_type": trigger_type,
        "target": target,
        "message": f"Trigger '{name}' created successfully"
    }


def get_trigger(trigger_id_or_name: str) -> Optional[Dict[str, Any]]:
    """Get a trigger by ID or name."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM triggers WHERE id = ? OR name = ?',
                  (trigger_id_or_name, trigger_id_or_name))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        'id': row['id'],
        'name': row['name'],
        'trigger_type': row['trigger_type'],
        'target': row['target'],
        'job_id': row['job_id'],
        'action': row['action'],
        'enabled': bool(row['enabled']),
        'debounce_seconds': row['debounce_seconds'],
        'last_fired': row['last_fired'],
        'fire_count': row['fire_count'],
        'created_at': row['created_at']
    }


def list_triggers(
    trigger_type: Optional[str] = None,
    enabled: Optional[bool] = None
) -> List[Dict[str, Any]]:
    """List all triggers with optional filters."""
    conn = get_connection()
    cursor = conn.cursor()

    query = 'SELECT * FROM triggers WHERE 1=1'
    params = []

    if trigger_type:
        query += ' AND trigger_type = ?'
        params.append(trigger_type)

    if enabled is not None:
        query += ' AND enabled = ?'
        params.append(1 if enabled else 0)

    query += ' ORDER BY created_at DESC'

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    triggers = []
    for row in rows:
        triggers.append({
            'id': row['id'],
            'name': row['name'],
            'trigger_type': row['trigger_type'],
            'target': row['target'],
            'job_id': row['job_id'],
            'action': row['action'][:50] + '...' if row['action'] and len(row['action']) > 50 else row['action'],
            'enabled': bool(row['enabled']),
            'last_fired': row['last_fired'],
            'fire_count': row['fire_count']
        })

    return triggers


def update_trigger(trigger_id: str, **updates) -> Dict[str, Any]:
    """Update trigger properties."""
    trigger = get_trigger(trigger_id)
    if not trigger:
        return {"success": False, "error": f"Trigger '{trigger_id}' not found"}

    allowed_fields = {'name', 'target', 'job_id', 'action', 'debounce_seconds', 'enabled'}
    valid_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not valid_updates:
        return {"success": False, "error": "No valid fields to update"}

    conn = get_connection()
    cursor = conn.cursor()

    set_clauses = []
    params = []
    for field, value in valid_updates.items():
        if field == 'enabled':
            value = 1 if value else 0
        set_clauses.append(f"{field} = ?")
        params.append(value)

    params.append(trigger['id'])

    cursor.execute(f"UPDATE triggers SET {', '.join(set_clauses)} WHERE id = ?", params)
    conn.commit()
    conn.close()

    return {
        "success": True,
        "trigger_id": trigger['id'],
        "updated_fields": list(valid_updates.keys()),
        "message": f"Trigger '{trigger['name']}' updated"
    }


def delete_trigger(trigger_id: str) -> Dict[str, Any]:
    """Delete a trigger."""
    trigger = get_trigger(trigger_id)
    if not trigger:
        return {"success": False, "error": f"Trigger '{trigger_id}' not found"}

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM triggers WHERE id = ?', (trigger['id'],))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "trigger_id": trigger['id'],
        "name": trigger['name'],
        "message": f"Trigger '{trigger['name']}' deleted"
    }


def enable_trigger(trigger_id: str) -> Dict[str, Any]:
    """Enable a trigger."""
    return update_trigger(trigger_id, enabled=True)


def disable_trigger(trigger_id: str) -> Dict[str, Any]:
    """Disable a trigger."""
    return update_trigger(trigger_id, enabled=False)


def should_debounce(trigger_id: str) -> bool:
    """Check if trigger should be debounced (fired too recently)."""
    trigger = get_trigger(trigger_id)
    if not trigger:
        return True

    if not trigger['last_fired']:
        return False

    last_fired = datetime.fromisoformat(trigger['last_fired'])
    debounce = timedelta(seconds=trigger['debounce_seconds'])

    return datetime.now() < last_fired + debounce


def record_fire(trigger_id: str) -> Dict[str, Any]:
    """Record that a trigger was fired."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE triggers
        SET last_fired = ?, fire_count = fire_count + 1
        WHERE id = ?
    ''', (datetime.now().isoformat(), trigger_id))

    conn.commit()
    conn.close()

    return {"success": True}


async def fire_trigger(trigger_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Fire a trigger and execute its associated job or action.

    Args:
        trigger_id: Trigger to fire
        context: Additional context (e.g., file path that changed)

    Returns:
        dict with success status and execution details
    """
    trigger = get_trigger(trigger_id)
    if not trigger:
        return {"success": False, "error": f"Trigger '{trigger_id}' not found"}

    if not trigger['enabled']:
        return {"success": False, "error": "Trigger is disabled"}

    # Check debounce
    if should_debounce(trigger['id']):
        return {
            "success": True,
            "debounced": True,
            "message": f"Trigger debounced (last fired: {trigger['last_fired']})"
        }

    # Record the fire
    record_fire(trigger['id'])

    # Log to audit
    try:
        from tools.security import audit
        audit.log_event(
            event_type='system',
            action='trigger_fired',
            resource=f"trigger:{trigger['name']}",
            status='success',
            details={'context': context}
        )
    except Exception:
        pass

    # Execute job or action
    if trigger['job_id']:
        try:
            from tools.automation import scheduler
            result = scheduler.run_job(trigger['job_id'], triggered_by=f"trigger:{trigger['name']}")
            return {
                "success": True,
                "trigger_name": trigger['name'],
                "execution_id": result.get('execution_id'),
                "message": f"Trigger fired, job execution created"
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to execute job: {str(e)}"}

    elif trigger['action']:
        # Return action for external execution
        return {
            "success": True,
            "trigger_name": trigger['name'],
            "action": trigger['action'],
            "context": context,
            "message": "Trigger fired with ad-hoc action"
        }

    return {"success": False, "error": "Trigger has no job or action"}


def get_file_triggers() -> List[Dict[str, Any]]:
    """Get all enabled file triggers."""
    return [t for t in list_triggers(trigger_type='file', enabled=True)]


def matches_pattern(path: str, pattern: str) -> bool:
    """Check if a file path matches a glob pattern."""
    # Handle both absolute and relative paths
    path_obj = Path(path)
    pattern_parts = pattern.split('/')

    # Match against filename
    if fnmatch(path_obj.name, pattern):
        return True

    # Match against full path
    if fnmatch(str(path_obj), pattern):
        return True

    # Match against relative path from project root
    try:
        relative = path_obj.relative_to(PROJECT_ROOT)
        if fnmatch(str(relative), pattern):
            return True
    except ValueError:
        pass

    return False


def should_ignore(path: str, ignore_patterns: List[str]) -> bool:
    """Check if path should be ignored based on patterns."""
    path_obj = Path(path)

    for pattern in ignore_patterns:
        if fnmatch(path_obj.name, pattern):
            return True
        if fnmatch(str(path_obj), pattern):
            return True

    return False


class TriggerEventHandler(FileSystemEventHandler):
    """Handle file system events and fire matching triggers."""

    def __init__(self, callback: Optional[Callable] = None):
        super().__init__()
        self.callback = callback
        config = load_config()
        self.ignore_patterns = config.get('triggers', {}).get('file_watcher', {}).get(
            'ignore_patterns', ['*.swp', '*.tmp', '.*']
        )

    def on_any_event(self, event: 'FileSystemEvent'):
        # Skip directories
        if event.is_directory:
            return

        # Skip ignored patterns
        if should_ignore(event.src_path, self.ignore_patterns):
            return

        # Get matching triggers
        triggers = get_file_triggers()
        for trigger in triggers:
            if matches_pattern(event.src_path, trigger['target']):
                context = {
                    'event_type': event.event_type,
                    'path': event.src_path,
                    'timestamp': datetime.now().isoformat()
                }

                if self.callback:
                    self.callback(trigger['id'], context)
                else:
                    # Synchronous fire for testing
                    asyncio.run(fire_trigger(trigger['id'], context))


def setup_file_watcher(callback: Optional[Callable] = None) -> Optional['Observer']:
    """
    Set up file system watcher.

    Args:
        callback: Function to call when trigger matches (trigger_id, context)

    Returns:
        Observer instance (call .start() to begin watching)
    """
    if not WATCHDOG_AVAILABLE:
        return None

    config = load_config()
    file_config = config.get('triggers', {}).get('file_watcher', {})

    if not file_config.get('enabled', True):
        return None

    watch_dirs = file_config.get('watch_dirs', ['workspace', '.tmp/inbox'])

    observer = Observer()
    handler = TriggerEventHandler(callback)

    for watch_dir in watch_dirs:
        dir_path = PROJECT_ROOT / watch_dir
        if dir_path.exists():
            observer.schedule(handler, str(dir_path), recursive=True)

    return observer


def get_stats() -> Dict[str, Any]:
    """Get trigger statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    # Count by type
    cursor.execute('''
        SELECT trigger_type, COUNT(*) as count FROM triggers
        GROUP BY trigger_type
    ''')
    by_type = {row['trigger_type']: row['count'] for row in cursor.fetchall()}

    # Count enabled
    cursor.execute('SELECT COUNT(*) FROM triggers WHERE enabled = 1')
    enabled = cursor.fetchone()[0]

    # Total fires
    cursor.execute('SELECT SUM(fire_count) FROM triggers')
    total_fires = cursor.fetchone()[0] or 0

    # Recent fires (24h)
    cursor.execute('''
        SELECT COUNT(*) FROM triggers
        WHERE last_fired > datetime('now', '-24 hours')
    ''')
    fired_24h = cursor.fetchone()[0]

    conn.close()

    return {
        "success": True,
        "by_type": by_type,
        "enabled": enabled,
        "total_fires": total_fires,
        "fired_24h": fired_24h,
        "watchdog_available": WATCHDOG_AVAILABLE
    }


def main():
    parser = argparse.ArgumentParser(description='Event Triggers')
    parser.add_argument('--action', required=True,
                       choices=['create', 'get', 'list', 'update', 'delete',
                               'enable', 'disable', 'fire', 'stats', 'watch'],
                       help='Action to perform')

    parser.add_argument('--name', help='Trigger name')
    parser.add_argument('--id', help='Trigger ID')
    parser.add_argument('--type', choices=VALID_TRIGGER_TYPES, help='Trigger type')
    parser.add_argument('--target', help='Target pattern or endpoint')
    parser.add_argument('--job', help='Job ID or name to execute')
    parser.add_argument('--task', help='Ad-hoc action/task')
    parser.add_argument('--debounce', type=int, default=5, help='Debounce seconds')
    parser.add_argument('--enabled', type=bool, default=True, help='Enable trigger')

    args = parser.parse_args()
    result = None

    if args.action == 'create':
        if not args.name or not args.type or not args.target:
            print("Error: --name, --type, and --target required for create")
            sys.exit(1)
        if not args.job and not args.task:
            print("Error: --job or --task required for create")
            sys.exit(1)
        result = create_trigger(
            name=args.name,
            trigger_type=args.type,
            target=args.target,
            job_id=args.job,
            action=args.task,
            debounce_seconds=args.debounce,
            enabled=args.enabled
        )

    elif args.action == 'get':
        trigger_id = args.id or args.name
        if not trigger_id:
            print("Error: --id or --name required")
            sys.exit(1)
        trigger = get_trigger(trigger_id)
        result = {"success": True, "trigger": trigger} if trigger else {"success": False, "error": "Not found"}

    elif args.action == 'list':
        triggers = list_triggers(trigger_type=args.type)
        result = {"success": True, "triggers": triggers, "count": len(triggers)}

    elif args.action == 'update':
        trigger_id = args.id or args.name
        if not trigger_id:
            print("Error: --id or --name required")
            sys.exit(1)
        updates = {}
        if args.target:
            updates['target'] = args.target
        if args.job:
            updates['job_id'] = args.job
        if args.task:
            updates['action'] = args.task
        if args.debounce:
            updates['debounce_seconds'] = args.debounce
        result = update_trigger(trigger_id, **updates)

    elif args.action == 'delete':
        trigger_id = args.id or args.name
        if not trigger_id:
            print("Error: --id or --name required")
            sys.exit(1)
        result = delete_trigger(trigger_id)

    elif args.action == 'enable':
        trigger_id = args.id or args.name
        if not trigger_id:
            print("Error: --id or --name required")
            sys.exit(1)
        result = enable_trigger(trigger_id)

    elif args.action == 'disable':
        trigger_id = args.id or args.name
        if not trigger_id:
            print("Error: --id or --name required")
            sys.exit(1)
        result = disable_trigger(trigger_id)

    elif args.action == 'fire':
        trigger_id = args.id or args.name
        if not trigger_id:
            print("Error: --id or --name required")
            sys.exit(1)
        result = asyncio.run(fire_trigger(trigger_id))

    elif args.action == 'stats':
        result = get_stats()

    elif args.action == 'watch':
        if not WATCHDOG_AVAILABLE:
            print("Error: watchdog not installed (pip install watchdog)")
            sys.exit(1)

        print("Starting file watcher (Ctrl+C to stop)...")
        observer = setup_file_watcher()
        if observer:
            observer.start()
            try:
                while True:
                    import time
                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
            observer.join()
            result = {"success": True, "message": "Watcher stopped"}
        else:
            result = {"success": False, "error": "Could not start watcher"}

    # Output
    if result:
        if result.get('success'):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
