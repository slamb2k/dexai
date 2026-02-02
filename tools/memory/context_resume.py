"""
Tool: Context Resume
Purpose: Generate "you were here..." prompts when ADHD users return after interruptions

This tool fetches the user's most recent context snapshot and generates a friendly,
ADHD-safe resumption prompt. It helps users recover context after interruptions
without guilt or shame.

Design principles (from adhd_design_principles.md):
- Never say "you still haven't..." or "you left this..."
- Always forward-facing: "Ready to pick up..." not "You abandoned..."
- If context is stale, don't guilt - just ask if still relevant
- Single action suggestion, not a list

Usage:
    # Generate resumption prompt for user
    python tools/memory/context_resume.py --action resume --user alice

    # Resume with specific snapshot
    python tools/memory/context_resume.py --action resume --user alice --snapshot-id "snap_abc123"

    # Just fetch context without generating prompt
    python tools/memory/context_resume.py --action fetch --user alice

Dependencies:
    - sqlite3 (stdlib)
    - json (stdlib)
    - yaml (pyyaml)

Output:
    JSON result with success status, resumption prompt, and suggested action
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

import yaml

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "context.db"
CONFIG_PATH = PROJECT_ROOT / "args" / "working_memory.yaml"
HARDPROMPT_PATH = PROJECT_ROOT / "hardprompts" / "memory" / "resumption_prompt.md"


def load_config() -> Dict[str, Any]:
    """Load working memory configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def get_connection() -> sqlite3.Connection:
    """Get database connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row) -> Optional[Dict]:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    d = dict(row)
    # Parse JSON state if present
    if 'state' in d and d['state']:
        try:
            d['state'] = json.loads(d['state'])
        except json.JSONDecodeError:
            pass
    return d


def load_hardprompt() -> str:
    """Load the resumption prompt template."""
    if HARDPROMPT_PATH.exists():
        with open(HARDPROMPT_PATH, 'r') as f:
            return f.read()
    # Fallback template if hardprompt doesn't exist
    return """Generate a friendly, forward-facing resumption prompt.

Context:
- Active file: {{active_file}}
- Last action: {{last_action}}
- Next step: {{next_step}}
- Time since: {{age_description}}

Rules:
- Never use guilt language ("you still haven't", "you left this")
- Be forward-facing ("Ready to pick up..." not "You abandoned...")
- Keep it brief (1-2 sentences)
- Suggest ONE concrete next action
"""


def get_latest_snapshot(user_id: str) -> Optional[Dict]:
    """Get the most recent context snapshot for a user."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM context_snapshots
        WHERE user_id = ?
          AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY captured_at DESC
        LIMIT 1
    ''', (user_id, datetime.now().isoformat()))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    snapshot = row_to_dict(row)

    # Calculate age
    captured_at = datetime.fromisoformat(snapshot['captured_at'])
    age = datetime.now() - captured_at
    snapshot['age_minutes'] = int(age.total_seconds() / 60)
    snapshot['age_hours'] = round(age.total_seconds() / 3600, 1)
    snapshot['age_days'] = round(age.total_seconds() / 86400, 1)

    return snapshot


def get_snapshot_by_id(snapshot_id: str) -> Optional[Dict]:
    """Get a specific context snapshot."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM context_snapshots WHERE id = ?', (snapshot_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    snapshot = row_to_dict(row)

    # Calculate age
    captured_at = datetime.fromisoformat(snapshot['captured_at'])
    age = datetime.now() - captured_at
    snapshot['age_minutes'] = int(age.total_seconds() / 60)
    snapshot['age_hours'] = round(age.total_seconds() / 3600, 1)
    snapshot['age_days'] = round(age.total_seconds() / 86400, 1)

    return snapshot


def get_recent_commitments(user_id: str, limit: int = 3) -> List[Dict]:
    """Get recent active commitments for context."""
    conn = get_connection()
    cursor = conn.cursor()

    # Check if commitments table exists
    cursor.execute('''
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='commitments'
    ''')
    if not cursor.fetchone():
        conn.close()
        return []

    cursor.execute('''
        SELECT id, content, target_person, due_date, created_at
        FROM commitments
        WHERE user_id = ? AND status = 'active'
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit))

    commitments = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return commitments


def format_age_description(age_minutes: int) -> str:
    """Convert age in minutes to human-friendly description."""
    if age_minutes < 5:
        return "just now"
    elif age_minutes < 60:
        return f"{age_minutes} minutes ago"
    elif age_minutes < 120:
        return "about an hour ago"
    elif age_minutes < 1440:  # 24 hours
        hours = age_minutes // 60
        return f"about {hours} hours ago"
    elif age_minutes < 2880:  # 48 hours
        return "yesterday"
    else:
        days = age_minutes // 1440
        return f"{days} days ago"


def generate_resumption_prompt(snapshot: Dict, config: Dict) -> Dict[str, Any]:
    """
    Generate an ADHD-friendly resumption prompt from a context snapshot.

    This generates the prompt locally using template-based formatting.
    For LLM-enhanced generation, the caller can use the hardprompt template
    with their preferred LLM.
    """
    state = snapshot.get('state', {})
    age_minutes = snapshot.get('age_minutes', 0)

    active_file = state.get('active_file', '')
    last_action = state.get('last_action', '')
    next_step = state.get('next_step', '')
    channel = state.get('channel', '')

    age_description = format_age_description(age_minutes)

    # Check if context is stale
    max_age_hours = config.get('working_memory', {}).get('resumption', {}).get('max_context_age_hours', 168)
    is_stale = snapshot.get('age_hours', 0) > max_age_hours
    stale_message = config.get('working_memory', {}).get('resumption', {}).get(
        'stale_context_message',
        "This is from a while ago - still relevant?"
    )

    # Build resumption prompt components
    prompt_parts = []

    # Main context description
    if active_file:
        file_name = Path(active_file).name if active_file else ""
        if last_action:
            prompt_parts.append(f"You were working on {file_name}. {last_action}.")
        else:
            prompt_parts.append(f"You were working on {file_name}.")
    elif last_action:
        prompt_parts.append(f"You were {last_action.lower() if last_action[0].isupper() else last_action}.")

    # Next step suggestion
    if next_step:
        prompt_parts.append(f"Next up: {next_step}")

    # Combine into resumption prompt
    resumption_prompt = " ".join(prompt_parts)

    # Add stale notice if needed
    if is_stale:
        resumption_prompt = f"{resumption_prompt}\n\n({stale_message})"

    # Generate suggested action
    suggested_action = None
    if next_step:
        if active_file:
            suggested_action = f"Open {active_file} and {next_step.lower() if next_step[0].isupper() else next_step}"
        else:
            suggested_action = next_step
    elif active_file:
        suggested_action = f"Open {active_file} to continue"

    return {
        "resumption_prompt": resumption_prompt,
        "suggested_action": suggested_action,
        "is_stale": is_stale,
        "age_description": age_description
    }


def fetch_context(user_id: str, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch context snapshot without generating prompt.

    Args:
        user_id: User identifier
        snapshot_id: Specific snapshot ID (optional, fetches latest if not provided)

    Returns:
        dict with snapshot data
    """
    if snapshot_id:
        snapshot = get_snapshot_by_id(snapshot_id)
        if not snapshot:
            return {"success": False, "error": f"Snapshot not found: {snapshot_id}"}
    else:
        snapshot = get_latest_snapshot(user_id)
        if not snapshot:
            return {
                "success": True,
                "data": None,
                "message": f"No context snapshots found for user {user_id}"
            }

    return {
        "success": True,
        "data": snapshot
    }


def resume_context(
    user_id: str,
    snapshot_id: Optional[str] = None,
    include_commitments: bool = True
) -> Dict[str, Any]:
    """
    Generate a resumption prompt for a user.

    Args:
        user_id: User identifier
        snapshot_id: Specific snapshot ID (optional)
        include_commitments: Include recent commitments in response

    Returns:
        dict with resumption prompt and context
    """
    config = load_config()

    # Get snapshot
    if snapshot_id:
        snapshot = get_snapshot_by_id(snapshot_id)
        if not snapshot:
            return {"success": False, "error": f"Snapshot not found: {snapshot_id}"}
    else:
        snapshot = get_latest_snapshot(user_id)
        if not snapshot:
            return {
                "success": True,
                "data": {
                    "snapshot_id": None,
                    "resumption_prompt": "No recent context found. What would you like to work on?",
                    "suggested_action": None,
                    "context": None
                },
                "message": "No context snapshots found"
            }

    # Generate resumption prompt
    prompt_data = generate_resumption_prompt(snapshot, config)

    # Get commitments if configured
    commitments = []
    if include_commitments:
        include_commits_config = config.get('working_memory', {}).get('resumption', {}).get('include_recent_commits', True)
        if include_commits_config:
            commitments = get_recent_commitments(user_id, limit=3)

    return {
        "success": True,
        "data": {
            "snapshot_id": snapshot['id'],
            "age_minutes": snapshot.get('age_minutes'),
            "age_description": prompt_data['age_description'],
            "is_stale": prompt_data['is_stale'],
            "resumption_prompt": prompt_data['resumption_prompt'],
            "suggested_action": prompt_data['suggested_action'],
            "context": snapshot.get('state'),
            "recent_commitments": commitments if commitments else None
        }
    }


def get_hardprompt_template(user_id: str, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the hardprompt template filled with context data.

    This allows callers to use their own LLM to generate more sophisticated
    resumption prompts.

    Args:
        user_id: User identifier
        snapshot_id: Specific snapshot ID (optional)

    Returns:
        dict with filled template ready for LLM
    """
    # Get snapshot
    if snapshot_id:
        snapshot = get_snapshot_by_id(snapshot_id)
        if not snapshot:
            return {"success": False, "error": f"Snapshot not found: {snapshot_id}"}
    else:
        snapshot = get_latest_snapshot(user_id)
        if not snapshot:
            return {"success": False, "error": "No context snapshots found"}

    state = snapshot.get('state', {})

    # Load and fill template
    template = load_hardprompt()
    filled_template = template.replace('{{active_file}}', state.get('active_file') or 'Not specified')
    filled_template = filled_template.replace('{{last_action}}', state.get('last_action') or 'Not specified')
    filled_template = filled_template.replace('{{next_step}}', state.get('next_step') or 'Not specified')
    filled_template = filled_template.replace('{{age_description}}', format_age_description(snapshot.get('age_minutes', 0)))

    return {
        "success": True,
        "data": {
            "template": filled_template,
            "snapshot_id": snapshot['id'],
            "context": state
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description='Context Resume - Generate ADHD-friendly "you were here" prompts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Generate resumption prompt for user
    %(prog)s --action resume --user alice

    # Resume with specific snapshot
    %(prog)s --action resume --user alice --snapshot-id "snap_abc123"

    # Just fetch context without generating prompt
    %(prog)s --action fetch --user alice

    # Get hardprompt template for LLM generation
    %(prog)s --action template --user alice
        '''
    )

    parser.add_argument('--action', required=True,
                       choices=['resume', 'fetch', 'template'],
                       help='Action to perform')

    parser.add_argument('--user', required=True, help='User ID')
    parser.add_argument('--snapshot-id', help='Specific snapshot ID to use')
    parser.add_argument('--no-commitments', action='store_true',
                       help='Do not include recent commitments')

    args = parser.parse_args()
    result = None

    if args.action == 'resume':
        result = resume_context(
            user_id=args.user,
            snapshot_id=args.snapshot_id,
            include_commitments=not args.no_commitments
        )

    elif args.action == 'fetch':
        result = fetch_context(
            user_id=args.user,
            snapshot_id=args.snapshot_id
        )

    elif args.action == 'template':
        result = get_hardprompt_template(
            user_id=args.user,
            snapshot_id=args.snapshot_id
        )

    if result:
        if result.get('success'):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
