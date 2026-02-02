"""
Tool: Sandbox Executor
Purpose: Secure command execution with allowlists, resource limits, and audit logging

Security Model:
- Only pre-approved commands can run (allowlist)
- Shell metacharacters blocked (|, &, ;, $, `, etc.)
- Resource limits: timeout, memory (via ulimit if available)
- All executions logged to audit trail
- Path traversal blocked in arguments

Usage:
    python tools/system/executor.py --run "ls -la"
    python tools/system/executor.py --run "python3 script.py" --timeout 120
    python tools/system/executor.py --run "grep pattern file.txt" --working-dir /tmp/workspace
    python tools/system/executor.py --history --user alice
    python tools/system/executor.py --allowlist
    python tools/system/executor.py --validate "rm -rf /"

Dependencies:
    - sqlite3 (stdlib)
    - subprocess (stdlib)
    - shlex (stdlib)

Output:
    JSON result with success status, stdout, stderr, exit code
"""

import argparse
import json
import os
import re
import resource
import shlex
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Database path
DB_PATH = PROJECT_ROOT / "data" / "executions.db"

# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "system_access.yaml"

# Default command allowlist
DEFAULT_ALLOWLIST = {
    # File inspection (read-only)
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "file",
    "stat",
    "find",
    "du",
    # Text processing
    "grep",
    "awk",
    "sed",
    "sort",
    "uniq",
    "cut",
    "tr",
    "diff",
    "comm",
    # Archive
    "tar",
    "gzip",
    "gunzip",
    "zip",
    "unzip",
    "bzip2",
    "bunzip2",
    # Development
    "python3",
    "python",
    "node",
    "npm",
    "npx",
    "pip3",
    "pip",
    "git",
    # Network (limited)
    "curl",
    "wget",
    # System info
    "date",
    "whoami",
    "pwd",
    "env",
    "which",
    "uname",
    "hostname",
    # Misc
    "echo",
    "printf",
    "true",
    "false",
    "test",
    "basename",
    "dirname",
    "realpath",
    "readlink",
    "md5sum",
    "sha256sum",
}

# Patterns that indicate dangerous commands
BLOCKED_PATTERNS = [
    (r"[;&|`$()]", "shell_metachar", "Shell metacharacters not allowed"),
    (r"^\s*>", "redirect", "Output redirection not allowed via shell"),
    (r"<\s*\(", "process_sub", "Process substitution not allowed"),
    (r"\.\./", "path_traversal", "Path traversal not allowed"),
    (r"/\.\.", "path_traversal", "Path traversal not allowed"),
    (r"\bsudo\b", "privilege_escalation", "sudo not allowed"),
    (r"\bsu\b", "privilege_escalation", "su not allowed"),
    (r"\brm\s+.*-[rf]", "dangerous_rm", "Recursive/force rm not allowed"),
    (r"\bchmod\s+.*777", "insecure_chmod", "chmod 777 not allowed"),
    (r"\bchmod\s+.*\+s", "setuid", "setuid not allowed"),
    (r"\bdd\s+", "disk_write", "dd not allowed"),
    (r"\bmkfs\.", "filesystem", "mkfs not allowed"),
    (r"\bfdisk\b", "partition", "fdisk not allowed"),
    (r"\bshutdown\b", "system", "shutdown not allowed"),
    (r"\breboot\b", "system", "reboot not allowed"),
    (r"\bkill\s+-9", "signal", "kill -9 not allowed"),
    (r"\bkillall\b", "signal", "killall not allowed"),
    (r"\bpkill\b", "signal", "pkill not allowed"),
]

# Default resource limits
DEFAULT_TIMEOUT = 60  # seconds
MAX_TIMEOUT = 300  # 5 minutes max
DEFAULT_MEMORY_MB = 512


def get_connection():
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Executions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS executions (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            command TEXT NOT NULL,
            working_dir TEXT,
            exit_code INTEGER,
            stdout TEXT,
            stderr TEXT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            duration_ms INTEGER,
            status TEXT CHECK(status IN ('running', 'completed', 'timeout', 'error', 'blocked'))
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exec_user ON executions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exec_status ON executions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exec_started ON executions(started_at)")

    conn.commit()
    return conn


def row_to_dict(row) -> dict | None:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    return dict(row)


def load_config() -> dict:
    """Load executor configuration from YAML file."""
    default_config = {
        "enabled": True,
        "default_timeout": DEFAULT_TIMEOUT,
        "max_timeout": MAX_TIMEOUT,
        "allowed_commands": list(DEFAULT_ALLOWLIST),
        "limits": {
            "memory_mb": DEFAULT_MEMORY_MB,
            "cpu_percent": 50,
        },
        "default_working_dir": str(Path.home() / "addulting" / "workspace"),
    }

    if not CONFIG_PATH.exists():
        return default_config

    try:
        import yaml

        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        if config and "executor" in config:
            # Merge with defaults
            executor_config = config["executor"]
            for key, value in executor_config.items():
                default_config[key] = value
            # Extend allowlist, don't replace
            if "allowed_commands" in executor_config:
                default_config["allowed_commands"] = list(
                    set(DEFAULT_ALLOWLIST) | set(executor_config["allowed_commands"])
                )
    except ImportError:
        pass
    except Exception:
        pass

    return default_config


def validate_command(command: list[str]) -> tuple[bool, str]:
    """
    Validate if a command is allowed to execute.

    Args:
        command: Command as list of strings

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not command:
        return False, "Empty command"

    config = load_config()
    allowlist = set(config.get("allowed_commands", DEFAULT_ALLOWLIST))

    # Get the base command (first element)
    base_cmd = Path(command[0]).name  # Handle full paths

    # Check if command is in allowlist
    if base_cmd not in allowlist:
        return False, f"Command '{base_cmd}' not in allowlist"

    # Check full command string for dangerous patterns
    full_command = " ".join(command)

    for pattern, category, message in BLOCKED_PATTERNS:
        if re.search(pattern, full_command, re.IGNORECASE):
            return False, f"Blocked ({category}): {message}"

    return True, ""


def set_resource_limits():
    """Set resource limits for child process."""
    config = load_config()
    limits = config.get("limits", {})
    memory_mb = limits.get("memory_mb", DEFAULT_MEMORY_MB)

    try:
        # Set memory limit (soft, hard)
        memory_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    except (OSError, ValueError):
        pass  # Not all systems support this

    try:
        # Set CPU time limit (generous, timeout handles real limit)
        resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    except (OSError, ValueError):
        pass

    try:
        # Limit number of child processes
        resource.setrlimit(resource.RLIMIT_NPROC, (50, 50))
    except (OSError, ValueError):
        pass


def execute(
    command: list[str],
    working_dir: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute a command with security constraints.

    Args:
        command: Command as list of strings
        working_dir: Working directory for command
        timeout: Timeout in seconds
        env: Additional environment variables
        user_id: User requesting execution

    Returns:
        dict with success status, stdout, stderr, exit_code
    """
    config = load_config()

    # Check if executor is enabled
    if not config.get("enabled", True):
        return {"success": False, "error": "Executor is disabled"}

    # Validate timeout
    max_timeout = config.get("max_timeout", MAX_TIMEOUT)
    if timeout > max_timeout:
        timeout = max_timeout

    # Validate command
    is_valid, error = validate_command(command)
    if not is_valid:
        # Log blocked execution
        execution_id = str(uuid.uuid4())
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO executions (id, user_id, command, working_dir, status, stderr)
            VALUES (?, ?, ?, ?, 'blocked', ?)
        """,
            (execution_id, user_id, json.dumps(command), working_dir, error),
        )
        conn.commit()
        conn.close()

        # Log to audit
        try:
            from tools.security import audit

            audit.log_event(
                event_type="command",
                action="execute",
                user_id=user_id,
                resource=command[0] if command else "unknown",
                status="blocked",
                details={"command": command, "reason": error},
            )
        except Exception:
            pass

        return {"success": False, "error": error, "execution_id": execution_id}

    # Check permissions
    try:
        from tools.security import permissions

        perm_result = permissions.check_permission(user_id or "anonymous", "system:execute")
        if not perm_result.get("allowed", False):
            return {"success": False, "error": "Permission denied: system:execute required"}
    except Exception:
        pass  # If permissions module unavailable, allow execution

    # Resolve working directory
    if working_dir:
        working_dir = str(Path(working_dir).expanduser().resolve())
        if not Path(working_dir).is_dir():
            return {"success": False, "error": f"Working directory not found: {working_dir}"}
    else:
        default_wd = config.get("default_working_dir")
        if default_wd:
            working_dir = str(Path(default_wd).expanduser().resolve())
            Path(working_dir).mkdir(parents=True, exist_ok=True)

    # Prepare environment
    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    # Remove sensitive environment variables from child
    sensitive_vars = ["API_KEY", "SECRET", "PASSWORD", "TOKEN", "CREDENTIAL"]
    for key in list(process_env.keys()):
        if any(s in key.upper() for s in sensitive_vars):
            del process_env[key]

    # Create execution record
    execution_id = str(uuid.uuid4())
    start_time = datetime.now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO executions (id, user_id, command, working_dir, status)
        VALUES (?, ?, ?, ?, 'running')
    """,
        (execution_id, user_id, json.dumps(command), working_dir),
    )
    conn.commit()
    conn.close()

    # Execute command
    try:
        result = subprocess.run(
            command,
            cwd=working_dir,
            env=process_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=set_resource_limits if os.name != "nt" else None,
        )

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Update execution record
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE executions
            SET exit_code = ?, stdout = ?, stderr = ?,
                completed_at = ?, duration_ms = ?, status = 'completed'
            WHERE id = ?
        """,
            (
                result.returncode,
                result.stdout[:100000] if result.stdout else "",  # Limit stored output
                result.stderr[:100000] if result.stderr else "",
                end_time.isoformat(),
                duration_ms,
                execution_id,
            ),
        )
        conn.commit()
        conn.close()

        # Log to audit
        try:
            from tools.security import audit

            audit.log_event(
                event_type="command",
                action="execute",
                user_id=user_id,
                resource=command[0],
                status="success" if result.returncode == 0 else "failure",
                details={
                    "command": command,
                    "exit_code": result.returncode,
                    "duration_ms": duration_ms,
                },
            )
        except Exception:
            pass

        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": duration_ms,
            "execution_id": execution_id,
        }

    except subprocess.TimeoutExpired:
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Update record
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE executions
            SET completed_at = ?, duration_ms = ?, status = 'timeout',
                stderr = ?
            WHERE id = ?
        """,
            (end_time.isoformat(), duration_ms, f"Timeout after {timeout}s", execution_id),
        )
        conn.commit()
        conn.close()

        # Log to audit
        try:
            from tools.security import audit

            audit.log_event(
                event_type="command",
                action="execute",
                user_id=user_id,
                resource=command[0],
                status="failure",
                details={"command": command, "reason": "timeout", "timeout_seconds": timeout},
            )
        except Exception:
            pass

        return {
            "success": False,
            "error": f"Command timed out after {timeout} seconds",
            "execution_id": execution_id,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Update record
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE executions
            SET completed_at = ?, duration_ms = ?, status = 'error',
                stderr = ?
            WHERE id = ?
        """,
            (end_time.isoformat(), duration_ms, str(e), execution_id),
        )
        conn.commit()
        conn.close()

        return {
            "success": False,
            "error": str(e),
            "execution_id": execution_id,
            "duration_ms": duration_ms,
        }


def execute_string(
    command_string: str,
    working_dir: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute a command from a string (will be safely parsed).

    Args:
        command_string: Command as a string
        working_dir: Working directory
        timeout: Timeout in seconds
        user_id: User requesting execution

    Returns:
        dict with execution result
    """
    try:
        command = shlex.split(command_string)
    except ValueError as e:
        return {"success": False, "error": f"Invalid command syntax: {e}"}

    return execute(command, working_dir, timeout, user_id=user_id)


def get_execution(execution_id: str) -> dict | None:
    """Retrieve execution record by ID."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM executions WHERE id = ?", (execution_id,))
    row = cursor.fetchone()

    conn.close()

    result = row_to_dict(row)
    if result and result.get("command"):
        try:
            result["command"] = json.loads(result["command"])
        except json.JSONDecodeError:
            pass

    return result


def list_executions(
    user_id: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    """
    List execution history.

    Args:
        user_id: Filter by user
        status: Filter by status
        limit: Maximum results
        offset: Pagination offset

    Returns:
        dict with executions list
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []

    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)

    if status:
        conditions.append("status = ?")
        params.append(status)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    cursor.execute(
        f"""
        SELECT id, user_id, command, working_dir, exit_code,
               started_at, completed_at, duration_ms, status
        FROM executions
        WHERE {where_clause}
        ORDER BY started_at DESC
        LIMIT ? OFFSET ?
    """,
        params + [limit, offset],
    )

    executions = []
    for row in cursor.fetchall():
        exec_dict = row_to_dict(row)
        if exec_dict.get("command"):
            try:
                exec_dict["command"] = json.loads(exec_dict["command"])
            except json.JSONDecodeError:
                pass
        executions.append(exec_dict)

    # Get total count
    cursor.execute(f"SELECT COUNT(*) as count FROM executions WHERE {where_clause}", params)
    total = cursor.fetchone()["count"]

    conn.close()

    return {
        "success": True,
        "executions": executions,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_allowlist() -> dict[str, Any]:
    """Get the current command allowlist."""
    config = load_config()
    allowlist = config.get("allowed_commands", list(DEFAULT_ALLOWLIST))

    return {
        "success": True,
        "allowlist": sorted(allowlist),
        "count": len(allowlist),
        "config_path": str(CONFIG_PATH) if CONFIG_PATH.exists() else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Sandbox Executor")

    # Actions
    parser.add_argument("--run", help="Command to execute")
    parser.add_argument("--validate", help="Validate command without executing")
    parser.add_argument("--history", action="store_true", help="Show execution history")
    parser.add_argument("--get", help="Get execution by ID")
    parser.add_argument("--allowlist", action="store_true", help="Show allowed commands")

    # Run options
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument("--working-dir", help="Working directory")
    parser.add_argument("--user", help="User ID")

    # History options
    parser.add_argument(
        "--status",
        choices=["running", "completed", "timeout", "error", "blocked"],
        help="Filter by status",
    )
    parser.add_argument("--limit", type=int, default=50, help="Max results")
    parser.add_argument("--offset", type=int, default=0, help="Pagination offset")

    args = parser.parse_args()
    result = None

    if args.run:
        result = execute_string(
            args.run, working_dir=args.working_dir, timeout=args.timeout, user_id=args.user
        )

    elif args.validate:
        try:
            command = shlex.split(args.validate)
        except ValueError as e:
            result = {"success": False, "error": f"Invalid command syntax: {e}"}
        else:
            is_valid, error = validate_command(command)
            result = {
                "success": True,
                "valid": is_valid,
                "command": command,
                "error": error if not is_valid else None,
            }

    elif args.history:
        result = list_executions(
            user_id=args.user, status=args.status, limit=args.limit, offset=args.offset
        )

    elif args.get:
        execution = get_execution(args.get)
        if execution:
            result = {"success": True, "execution": execution}
        else:
            result = {"success": False, "error": f"Execution not found: {args.get}"}

    elif args.allowlist:
        result = get_allowlist()

    else:
        print("Error: Must specify an action (--run, --validate, --history, --get, --allowlist)")
        sys.exit(1)

    if result:
        if result.get("success"):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
