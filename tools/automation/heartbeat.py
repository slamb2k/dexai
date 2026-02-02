"""
Tool: Heartbeat Engine
Purpose: Periodic background awareness checks

Features:
- Parse check definitions from HEARTBEAT.md
- Sync checks to database for tracking
- Activity-aware execution (skip if user active)
- Batch checks into single LLM turn for efficiency
- Track check results and history

Usage:
    python tools/automation/heartbeat.py --action parse
    python tools/automation/heartbeat.py --action list
    python tools/automation/heartbeat.py --action run
    python tools/automation/heartbeat.py --action status

HEARTBEAT.md Format:
    # Heartbeat Checks

    ## Section Name
    - Check description 1
    - Check description 2

    ## Another Section
    - Another check

Dependencies:
    - pyyaml
"""

import argparse
import json
import re
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.automation import CONFIG_PATH, DB_PATH, HEARTBEAT_FILE


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    default_config = {
        "heartbeat": {
            "enabled": True,
            "interval_minutes": 30,
            "activity_skip_window": 300,
            "cost_limit": 0.25,
            "timeout_seconds": 180,
            "batch_checks": True,
            "checks_file": "HEARTBEAT.md",
            "active_hours": {"start": "06:00", "end": "23:00"},
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

    # Heartbeat checks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS heartbeat_checks (
            id TEXT PRIMARY KEY,
            section TEXT NOT NULL,
            check_name TEXT NOT NULL,
            check_description TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            last_run DATETIME,
            last_result TEXT,
            last_output TEXT,
            UNIQUE(section, check_name)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_heartbeat_enabled ON heartbeat_checks(enabled)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_heartbeat_section ON heartbeat_checks(section)")

    conn.commit()
    return conn


def parse_heartbeat_file(path: Path | None = None) -> list[dict[str, Any]]:
    """
    Parse HEARTBEAT.md file to extract check definitions.

    Expected format:
        # Heartbeat Checks

        ## Section Name
        - Check description here
        - Another check description

        ## Another Section
        - More checks

    Returns:
        List of check dicts with section, name, and description
    """
    file_path = path or HEARTBEAT_FILE

    if not file_path.exists():
        return []

    with open(file_path) as f:
        content = f.read()

    checks = []
    current_section = "Default"

    for line in content.split("\n"):
        line = line.strip()

        # Skip empty lines and main title
        if not line or line.startswith("# "):
            continue

        # Section header (## Section Name)
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue

        # Check item (- Description)
        if line.startswith("- "):
            description = line[2:].strip()
            if description:
                # Generate a name from description (first few words)
                words = re.sub(r"[^\w\s]", "", description.lower()).split()[:4]
                name = "_".join(words) if words else f"check_{len(checks)}"

                checks.append(
                    {"section": current_section, "name": name, "description": description}
                )

    return checks


def sync_checks_to_db(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Sync parsed checks to database.

    - Adds new checks
    - Updates existing check descriptions
    - Disables checks no longer in file
    """
    conn = get_connection()
    cursor = conn.cursor()

    added = 0
    updated = 0
    disabled = 0

    # Get existing checks
    cursor.execute("SELECT id, section, check_name, check_description FROM heartbeat_checks")
    existing = {(row["section"], row["check_name"]): row for row in cursor.fetchall()}

    # Track which checks are still in file
    current_keys = set()

    for check in checks:
        key = (check["section"], check["name"])
        current_keys.add(key)

        if key in existing:
            # Update if description changed
            if existing[key]["check_description"] != check["description"]:
                cursor.execute(
                    """
                    UPDATE heartbeat_checks
                    SET check_description = ?, enabled = 1
                    WHERE section = ? AND check_name = ?
                """,
                    (check["description"], check["section"], check["name"]),
                )
                updated += 1
            else:
                # Re-enable if was disabled
                cursor.execute(
                    """
                    UPDATE heartbeat_checks SET enabled = 1
                    WHERE section = ? AND check_name = ? AND enabled = 0
                """,
                    (check["section"], check["name"]),
                )
        else:
            # Add new check
            check_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO heartbeat_checks (id, section, check_name, check_description, enabled)
                VALUES (?, ?, ?, ?, 1)
            """,
                (check_id, check["section"], check["name"], check["description"]),
            )
            added += 1

    # Disable checks no longer in file
    for key in existing:
        if key not in current_keys:
            cursor.execute(
                """
                UPDATE heartbeat_checks SET enabled = 0
                WHERE section = ? AND check_name = ?
            """,
                (key[0], key[1]),
            )
            disabled += 1

    conn.commit()
    conn.close()

    return {
        "success": True,
        "added": added,
        "updated": updated,
        "disabled": disabled,
        "total": len(checks),
        "message": f"Synced {len(checks)} checks: {added} added, {updated} updated, {disabled} disabled",
    }


def get_checks(enabled_only: bool = True) -> list[dict[str, Any]]:
    """Get all heartbeat checks from database."""
    conn = get_connection()
    cursor = conn.cursor()

    if enabled_only:
        cursor.execute(
            "SELECT * FROM heartbeat_checks WHERE enabled = 1 ORDER BY section, check_name"
        )
    else:
        cursor.execute("SELECT * FROM heartbeat_checks ORDER BY section, check_name")

    checks = []
    for row in cursor.fetchall():
        checks.append(
            {
                "id": row["id"],
                "section": row["section"],
                "name": row["check_name"],
                "description": row["check_description"],
                "enabled": bool(row["enabled"]),
                "last_run": row["last_run"],
                "last_result": row["last_result"],
                "last_output": row["last_output"],
            }
        )

    conn.close()
    return checks


def is_within_active_hours() -> tuple[bool, str]:
    """Check if current time is within configured active hours."""
    config = load_config()
    hb_config = config.get("heartbeat", {})
    active_hours = hb_config.get("active_hours", {})

    start_str = active_hours.get("start", "06:00")
    end_str = active_hours.get("end", "23:00")

    now = datetime.now()
    current_time = now.strftime("%H:%M")

    # Simple string comparison works for HH:MM format
    if start_str <= end_str:
        # Normal range (e.g., 06:00 to 23:00)
        is_active = start_str <= current_time <= end_str
    else:
        # Overnight range (e.g., 22:00 to 06:00)
        is_active = current_time >= start_str or current_time <= end_str

    if not is_active:
        return False, f"Outside active hours ({start_str} - {end_str})"

    return True, "Within active hours"


def get_last_activity_time() -> datetime | None:
    """
    Get timestamp of last user activity.

    Checks multiple sources:
    - Audit log for recent user actions
    - Message inbox for recent messages
    """
    last_activity = None

    # Check audit log
    try:
        from tools.security import audit

        events = audit.query_events(limit=1)
        if events.get("events"):
            last_event = events["events"][0]
            last_activity = datetime.fromisoformat(last_event["timestamp"])
    except Exception:
        pass

    # Check inbox for recent messages
    try:
        inbox_db = PROJECT_ROOT / "data" / "inbox.db"
        if inbox_db.exists():
            conn = sqlite3.connect(str(inbox_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp FROM messages
                WHERE direction = 'inbound'
                ORDER BY timestamp DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                msg_time = datetime.fromisoformat(row["timestamp"])
                if last_activity is None or msg_time > last_activity:
                    last_activity = msg_time
            conn.close()
    except Exception:
        pass

    return last_activity


def should_skip_heartbeat() -> tuple[bool, str]:
    """
    Determine if heartbeat should be skipped.

    Reasons to skip:
    - Outside active hours
    - User was active recently (within activity_skip_window)
    - Heartbeat disabled in config
    """
    config = load_config()
    hb_config = config.get("heartbeat", {})

    # Check if enabled
    if not hb_config.get("enabled", True):
        return True, "Heartbeat disabled in configuration"

    # Check active hours
    is_active, reason = is_within_active_hours()
    if not is_active:
        return True, reason

    # Check recent activity
    activity_window = hb_config.get("activity_skip_window", 300)
    last_activity = get_last_activity_time()

    if last_activity:
        seconds_since = (datetime.now() - last_activity).total_seconds()
        if seconds_since < activity_window:
            return True, f"User active {int(seconds_since)}s ago (window: {activity_window}s)"

    return False, "Ready to run"


def build_heartbeat_prompt(checks: list[dict[str, Any]]) -> str:
    """
    Build a prompt for the LLM to perform heartbeat checks.

    If batch_checks is enabled, combines all checks into one prompt.
    """
    if not checks:
        return ""

    config = load_config()
    hb_config = config.get("heartbeat", {})

    # Group checks by section
    sections = {}
    for check in checks:
        section = check["section"]
        if section not in sections:
            sections[section] = []
        sections[section].append(check)

    prompt_parts = [
        "# Heartbeat Check",
        "",
        "Perform the following periodic checks and report any findings:",
        "",
    ]

    for section, section_checks in sections.items():
        prompt_parts.append(f"## {section}")
        for check in section_checks:
            prompt_parts.append(f"- {check['description']}")
        prompt_parts.append("")

    prompt_parts.extend(
        [
            "For each check:",
            "1. Perform the check",
            "2. Report status: OK, WARNING, or ALERT",
            "3. Provide brief details if anything notable",
            "",
            "Be concise. Only report issues or important updates.",
        ]
    )

    return "\n".join(prompt_parts)


def record_check_result(check_id: str, result: str, output: str | None = None) -> dict[str, Any]:
    """Record the result of a heartbeat check."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE heartbeat_checks
        SET last_run = ?, last_result = ?, last_output = ?
        WHERE id = ?
    """,
        (datetime.now().isoformat(), result, output, check_id),
    )

    if cursor.rowcount == 0:
        conn.close()
        return {"success": False, "error": f"Check '{check_id}' not found"}

    conn.commit()
    conn.close()

    return {
        "success": True,
        "check_id": check_id,
        "result": result,
        "message": f"Check result recorded: {result}",
    }


def record_batch_results(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """
    Record results for multiple checks at once.

    Args:
        results: Dict mapping check_id to {result, output}
    """
    conn = get_connection()
    cursor = conn.cursor()

    recorded = 0
    now = datetime.now().isoformat()

    for check_id, data in results.items():
        cursor.execute(
            """
            UPDATE heartbeat_checks
            SET last_run = ?, last_result = ?, last_output = ?
            WHERE id = ?
        """,
            (now, data.get("result", "unknown"), data.get("output"), check_id),
        )
        if cursor.rowcount > 0:
            recorded += 1

    conn.commit()
    conn.close()

    return {"success": True, "recorded": recorded, "total": len(results)}


def run_heartbeat() -> dict[str, Any]:
    """
    Execute heartbeat checks.

    This prepares the checks and returns the prompt/data needed.
    Actual LLM execution should be handled by the runner.
    """
    # Check if we should skip
    should_skip, reason = should_skip_heartbeat()
    if should_skip:
        return {"success": True, "skipped": True, "reason": reason}

    # Get enabled checks
    checks = get_checks(enabled_only=True)
    if not checks:
        return {"success": True, "skipped": True, "reason": "No enabled checks found"}

    config = load_config()
    hb_config = config.get("heartbeat", {})

    # Build prompt
    prompt = build_heartbeat_prompt(checks)

    return {
        "success": True,
        "skipped": False,
        "checks": checks,
        "check_count": len(checks),
        "prompt": prompt,
        "cost_limit": hb_config.get("cost_limit", 0.25),
        "timeout_seconds": hb_config.get("timeout_seconds", 180),
        "batch_checks": hb_config.get("batch_checks", True),
    }


def get_status() -> dict[str, Any]:
    """Get heartbeat status and statistics."""
    config = load_config()
    hb_config = config.get("heartbeat", {})

    checks = get_checks(enabled_only=False)
    enabled_checks = [c for c in checks if c["enabled"]]

    # Count by last result
    results_count = {"ok": 0, "warning": 0, "alert": 0, "unknown": 0}
    for check in enabled_checks:
        result = (check.get("last_result") or "unknown").lower()
        if result in results_count:
            results_count[result] += 1
        else:
            results_count["unknown"] += 1

    # Check if should run
    should_skip, skip_reason = should_skip_heartbeat()

    return {
        "success": True,
        "enabled": hb_config.get("enabled", True),
        "interval_minutes": hb_config.get("interval_minutes", 30),
        "checks": {
            "total": len(checks),
            "enabled": len(enabled_checks),
            "by_result": results_count,
        },
        "should_skip": should_skip,
        "skip_reason": skip_reason,
        "active_hours": hb_config.get("active_hours", {}),
    }


def main():
    parser = argparse.ArgumentParser(description="Heartbeat Engine")
    parser.add_argument(
        "--action",
        required=True,
        choices=["parse", "sync", "list", "run", "status", "record", "enable", "disable"],
        help="Action to perform",
    )

    parser.add_argument("--file", help="Path to HEARTBEAT.md file")
    parser.add_argument("--check-id", help="Check ID for record action")
    parser.add_argument("--result", help="Result status (ok, warning, alert)")
    parser.add_argument("--output", help="Result output/details")
    parser.add_argument("--all", action="store_true", help="Include disabled checks")

    args = parser.parse_args()
    result = None

    if args.action == "parse":
        file_path = Path(args.file) if args.file else HEARTBEAT_FILE
        checks = parse_heartbeat_file(file_path)
        result = {"success": True, "checks": checks, "count": len(checks)}

    elif args.action == "sync":
        file_path = Path(args.file) if args.file else HEARTBEAT_FILE
        checks = parse_heartbeat_file(file_path)
        result = sync_checks_to_db(checks)

    elif args.action == "list":
        checks = get_checks(enabled_only=not args.all)
        result = {"success": True, "checks": checks, "count": len(checks)}

    elif args.action == "run":
        result = run_heartbeat()

    elif args.action == "status":
        result = get_status()

    elif args.action == "record":
        if not args.check_id or not args.result:
            print("Error: --check-id and --result required for record")
            sys.exit(1)
        result = record_check_result(args.check_id, args.result, args.output)

    elif args.action == "enable":
        if not args.check_id:
            print("Error: --check-id required")
            sys.exit(1)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE heartbeat_checks SET enabled = 1 WHERE id = ?", (args.check_id,))
        conn.commit()
        conn.close()
        result = {"success": True, "message": f"Check {args.check_id} enabled"}

    elif args.action == "disable":
        if not args.check_id:
            print("Error: --check-id required")
            sys.exit(1)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE heartbeat_checks SET enabled = 0 WHERE id = ?", (args.check_id,))
        conn.commit()
        conn.close()
        result = {"success": True, "message": f"Check {args.check_id} disabled"}

    # Output
    if result.get("success"):
        print(f"OK {result.get('message', 'Success')}")
    else:
        print(f"ERROR {result.get('error')}")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
