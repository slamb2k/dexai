"""
Bash AST Parser — Structural analysis of shell commands via bashlex.

Parses bash commands into an AST and walks the tree to detect dangerous
patterns (destructive commands, privilege escalation, credential theft,
network exfiltration, crypto mining, disk writes).

Falls back gracefully if bashlex is not installed — callers should use
regex-based detection as a fallback when this module returns None.

Usage:
    from tools.security.bash_ast_parser import analyze_bash_command

    result = analyze_bash_command("rm -rf /")
    # {"dangerous": True, "reason": "Destructive command: rm with recursive flag", "method": "ast"}

    result = analyze_bash_command("echo hello")
    # {"dangerous": False, "reason": "", "method": "ast"}
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import bashlex — graceful degradation if unavailable
_BASHLEX_AVAILABLE = False
try:
    import bashlex

    _BASHLEX_AVAILABLE = True
except ImportError:
    bashlex = None  # type: ignore[assignment]
    logger.debug("bashlex not installed — AST parsing unavailable, will use regex fallback")


# =============================================================================
# Dangerous command definitions
# =============================================================================

# Commands that are destructive when combined with certain flags/arguments
DESTRUCTIVE_COMMANDS = {
    "rm": {
        "flags": {"-rf", "-r", "--recursive", "-fr"},
        "reason": "Destructive command: rm with recursive flag",
    },
    "mkfs": {
        "flags": set(),  # Always dangerous
        "reason": "Destructive command: mkfs (filesystem format)",
    },
    "shred": {
        "flags": set(),
        "reason": "Destructive command: shred (secure file deletion)",
    },
    "wipefs": {
        "flags": set(),
        "reason": "Destructive command: wipefs (wipe filesystem signatures)",
    },
}

# Commands that indicate privilege escalation
PRIVILEGE_ESCALATION = {
    "sudo": {
        "subcommands": {"su", "-i"},
        "reason": "Privilege escalation: sudo to root shell",
    },
}

# Commands that can steal credentials when targeting sensitive paths
CREDENTIAL_THEFT_COMMANDS = {"cat", "less", "more", "head", "tail", "grep"}
SENSITIVE_PATHS = {".ssh/", ".env", "passwd", "shadow", ".gnupg/", ".aws/credentials"}

# Pipe targets that indicate network exfiltration
DANGEROUS_PIPE_TARGETS = {"bash", "sh", "python", "perl", "ruby"}

# Crypto mining binaries
CRYPTO_MINERS = {"xmrig", "cpuminer", "minerd"}

# Dangerous disk write targets
DANGEROUS_DISK_PREFIXES = ("/dev/sd", "/dev/nvme")
DISK_WRITE_COMMANDS = {"tee", "dd"}


# =============================================================================
# AST Walking
# =============================================================================


def _get_node_parts(node) -> list:
    """
    Recursively collect all child nodes from a bashlex AST node.

    Handles both 'parts' and 'list' attributes used by different node kinds.
    """
    children = []
    if hasattr(node, "parts"):
        children.extend(node.parts)
    if hasattr(node, "list"):
        children.extend(node.list)
    return children


def _extract_words(node) -> list[str]:
    """Extract word values from a command node's parts."""
    words = []
    if hasattr(node, "parts"):
        for part in node.parts:
            if part.kind == "word":
                words.append(part.word)
    return words


def _check_command_node(words: list[str]) -> Optional[dict]:
    """
    Check a single command (list of words) for dangerous patterns.

    Returns a result dict if dangerous, None otherwise.
    """
    if not words:
        return None

    cmd = words[0]
    # Strip path prefix (e.g., /usr/bin/rm -> rm)
    if "/" in cmd:
        cmd = cmd.rsplit("/", 1)[-1]

    args = words[1:] if len(words) > 1 else []
    args_set = set(args)
    args_str = " ".join(args)

    # --- Destructive commands ---
    # Check if command starts with a destructive command prefix (e.g., mkfs.ext4)
    for dest_cmd, info in DESTRUCTIVE_COMMANDS.items():
        if cmd == dest_cmd or cmd.startswith(dest_cmd + "."):
            if not info["flags"]:
                # Always dangerous (mkfs, shred, wipefs)
                return {"dangerous": True, "reason": info["reason"], "method": "ast"}
            # Check for exact flag match OR combined flags (e.g. -rfv contains -r)
            if args_set & info["flags"]:
                return {"dangerous": True, "reason": info["reason"], "method": "ast"}
            for arg in args:
                if arg.startswith("-") and not arg.startswith("--"):
                    # Check if any required single-char flag is in a combined flag
                    arg_chars = set(arg.lstrip("-"))
                    for flag in info["flags"]:
                        if flag.startswith("-") and not flag.startswith("--"):
                            flag_chars = set(flag.lstrip("-"))
                            if flag_chars <= arg_chars:
                                return {"dangerous": True, "reason": info["reason"], "method": "ast"}

    # --- dd with of=/dev/ ---
    if cmd == "dd":
        for arg in args:
            if arg.startswith("of=/dev/"):
                return {
                    "dangerous": True,
                    "reason": "Destructive command: dd writing to device",
                    "method": "ast",
                }

    # --- Privilege escalation ---
    if cmd in PRIVILEGE_ESCALATION:
        info = PRIVILEGE_ESCALATION[cmd]
        if args_set & info["subcommands"]:
            return {"dangerous": True, "reason": info["reason"], "method": "ast"}

    # --- Credential theft ---
    if cmd in CREDENTIAL_THEFT_COMMANDS:
        for arg in args:
            for sensitive in SENSITIVE_PATHS:
                if sensitive in arg:
                    return {
                        "dangerous": True,
                        "reason": f"Credential theft: {cmd} targeting {sensitive}",
                        "method": "ast",
                    }

    # --- Crypto mining ---
    if cmd in CRYPTO_MINERS:
        return {
            "dangerous": True,
            "reason": f"Crypto mining: {cmd}",
            "method": "ast",
        }

    # --- Disk writes to /dev/sd* or /dev/nvme* ---
    if cmd in DISK_WRITE_COMMANDS:
        for arg in args:
            for prefix in DANGEROUS_DISK_PREFIXES:
                if arg.startswith(prefix):
                    return {
                        "dangerous": True,
                        "reason": f"Disk write: {cmd} to {arg}",
                        "method": "ast",
                    }

    return None


def _check_pipeline_node(node) -> Optional[dict]:
    """
    Check a pipeline node for dangerous patterns like curl|bash.

    Detects: curl|bash, wget|bash, curl|sh, wget|sh, and similar
    pipe-to-interpreter patterns.
    """
    if not hasattr(node, "parts") or len(node.parts) < 2:
        return None

    # Get the last command in the pipeline (the receiver)
    last_part = node.parts[-1]
    last_words = _extract_words(last_part)

    if not last_words:
        return None

    last_cmd = last_words[0]
    if "/" in last_cmd:
        last_cmd = last_cmd.rsplit("/", 1)[-1]

    if last_cmd in DANGEROUS_PIPE_TARGETS:
        # Check if any earlier command is curl/wget
        for part in node.parts[:-1]:
            part_words = _extract_words(part)
            if part_words:
                source_cmd = part_words[0]
                if "/" in source_cmd:
                    source_cmd = source_cmd.rsplit("/", 1)[-1]
                if source_cmd in ("curl", "wget"):
                    return {
                        "dangerous": True,
                        "reason": f"Network exfiltration: {source_cmd} piped to {last_cmd}",
                        "method": "ast",
                    }

    return None


def _walk_ast(node) -> Optional[dict]:
    """
    Recursively walk a bashlex AST node and check for dangerous patterns.

    Returns the first dangerous result found, or None if clean.
    """
    # Check pipeline nodes
    if node.kind == "pipeline":
        result = _check_pipeline_node(node)
        if result:
            return result

    # Check command nodes
    if node.kind == "command":
        words = _extract_words(node)
        result = _check_command_node(words)
        if result:
            return result

    # Recurse into children
    for child in _get_node_parts(node):
        result = _walk_ast(child)
        if result:
            return result

    return None


# =============================================================================
# Public API
# =============================================================================


def analyze_bash_command(command: str) -> Optional[dict]:
    """
    Analyze a bash command for dangerous patterns using AST parsing.

    Args:
        command: The bash command string to analyze

    Returns:
        dict with keys:
            - dangerous (bool): Whether the command is dangerous
            - reason (str): Human-readable explanation
            - method (str): "ast" for AST-based detection
        None if bashlex is unavailable or fails to parse (signals caller
        to fall back to regex-based detection)
    """
    if not _BASHLEX_AVAILABLE:
        return None

    if not command or not command.strip():
        return {"dangerous": False, "reason": "", "method": "ast"}

    try:
        parts = bashlex.parse(command)
    except Exception:
        # bashlex cannot parse this command — signal fallback
        logger.debug(f"bashlex failed to parse command: {command[:100]}")
        return None

    for node in parts:
        result = _walk_ast(node)
        if result:
            return result

    return {"dangerous": False, "reason": "", "method": "ast"}


def get_bashlex_status() -> dict:
    """
    Get diagnostic information about bashlex availability.

    Returns:
        dict with:
            - available (bool): Whether bashlex is importable
            - version (str): bashlex version if available
    """
    status = {
        "available": _BASHLEX_AVAILABLE,
        "version": "",
    }

    if _BASHLEX_AVAILABLE and bashlex is not None:
        status["version"] = getattr(bashlex, "__version__", "unknown")

    return status
