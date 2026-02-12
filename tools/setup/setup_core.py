"""Shared setup functions for DexAI configuration.

Used by both CLI (dexai setup) and dashboard chat setup.
Designed for easy removal of CLI wizard when dashboard chat covers all setup.

All functions return ``{"success": bool, ...}`` dicts so callers can report
results consistently regardless of the UI layer.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_PATH = PROJECT_ROOT / "data"
ENV_FILE = PROJECT_ROOT / ".env"
CONFIG_PATH = PROJECT_ROOT / "args"


# ============================================================================
# check_prerequisites
# ============================================================================


def check_prerequisites() -> dict[str, Any]:
    """Check that all system prerequisites are met.

    Returns:
        dict with ``success``, ``checks`` list, and ``missing`` list.
    """
    checks: list[dict[str, Any]] = []
    missing: list[str] = []

    # Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    py_ok = sys.version_info >= (3, 11)
    checks.append({"name": "python", "version": py_version, "ok": py_ok})
    if not py_ok:
        missing.append(f"Python 3.11+ (found {py_version})")

    # uv
    uv_path = shutil.which("uv")
    checks.append({"name": "uv", "path": uv_path, "ok": uv_path is not None})
    if not uv_path:
        missing.append("uv package manager")

    # git
    git_path = shutil.which("git")
    checks.append({"name": "git", "path": git_path, "ok": git_path is not None})
    if not git_path:
        missing.append("git")

    # Docker (optional)
    docker_path = shutil.which("docker")
    docker_running = False
    if docker_path:
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            docker_running = result.returncode == 0
        except Exception:
            pass
    checks.append({
        "name": "docker",
        "path": docker_path,
        "running": docker_running,
        "ok": True,  # Docker is optional
        "optional": True,
    })

    # .env file
    env_exists = ENV_FILE.exists()
    checks.append({"name": "env_file", "path": str(ENV_FILE), "ok": env_exists})
    if not env_exists:
        missing.append(".env file")

    # data directory
    data_exists = DATA_PATH.is_dir()
    checks.append({"name": "data_dir", "path": str(DATA_PATH), "ok": data_exists})
    if not data_exists:
        missing.append("data/ directory")

    return {
        "success": len(missing) == 0,
        "checks": checks,
        "missing": missing,
    }


# ============================================================================
# init_vault
# ============================================================================


def init_vault(master_key: str) -> dict[str, Any]:
    """Initialize the vault with a master key.

    Generates a master key if *master_key* is empty, writes it to ``.env``,
    and initialises the vault database.

    Args:
        master_key: The master encryption key.  Pass an empty string to
            auto-generate a secure random key.

    Returns:
        dict with ``success`` and optional ``generated_key`` flag.
    """
    import secrets

    if not master_key:
        master_key = secrets.token_hex(32)
        generated = True
    else:
        generated = False

    # Persist to .env
    try:
        _set_env_var("DEXAI_MASTER_KEY", master_key)
    except Exception as e:
        return {"success": False, "error": f"Failed to write .env: {e}"}

    # Also set in the current process so subsequent vault calls work
    os.environ["DEXAI_MASTER_KEY"] = master_key

    # Initialise the vault database
    try:
        from tools.security.vault import get_connection
        conn = get_connection()
        conn.close()
    except Exception as e:
        return {"success": False, "error": f"Vault DB init failed: {e}"}

    return {"success": True, "generated_key": generated}


# ============================================================================
# configure_api_keys
# ============================================================================


def configure_api_keys(
    anthropic_key: str,
    openai_key: str | None = None,
    openrouter_key: str | None = None,
) -> dict[str, Any]:
    """Store API keys in the vault and .env.

    Args:
        anthropic_key: Anthropic API key (required).
        openai_key: OpenAI API key (optional, for embeddings).
        openrouter_key: OpenRouter API key (optional, for model routing).

    Returns:
        dict with ``success`` and ``stored`` list of key names.
    """
    stored: list[str] = []
    errors: list[str] = []

    keys_to_store = [
        ("ANTHROPIC_API_KEY", anthropic_key, "default"),
        ("OPENAI_API_KEY", openai_key, "default"),
        ("OPENROUTER_API_KEY", openrouter_key, "default"),
    ]

    for key_name, key_value, namespace in keys_to_store:
        if not key_value:
            continue
        try:
            # Store in vault
            from tools.security import vault
            result = vault.set_secret(key_name, key_value, namespace=namespace)
            if not result.get("success"):
                # Vault may not be initialised yet — fall back to .env
                _set_env_var(key_name, key_value)
            stored.append(key_name)
        except Exception:
            # Fall back to .env
            try:
                _set_env_var(key_name, key_value)
                stored.append(key_name)
            except Exception as e:
                errors.append(f"Failed to store {key_name}: {e}")

    return {
        "success": len(errors) == 0,
        "stored": stored,
        "errors": errors,
    }


# ============================================================================
# configure_channel
# ============================================================================


def configure_channel(channel: str, token: str, **kwargs: Any) -> dict[str, Any]:
    """Configure a messaging channel (telegram, discord, slack).

    Args:
        channel: Channel name — ``"telegram"``, ``"discord"``, or ``"slack"``.
        token: Primary bot token for the channel.
        **kwargs: Additional channel-specific config (e.g. ``app_token`` for
            Slack, ``channel_id`` for Discord).

    Returns:
        dict with ``success`` and channel details.
    """
    channel = channel.lower().strip()
    if channel not in ("telegram", "discord", "slack"):
        return {"success": False, "error": f"Unknown channel: {channel}"}

    errors: list[str] = []

    # Map channel to env var names
    token_map = {
        "telegram": [("TELEGRAM_BOT_TOKEN", token)],
        "discord": [("DISCORD_BOT_TOKEN", token)],
        "slack": [
            ("SLACK_BOT_TOKEN", token),
            ("SLACK_APP_TOKEN", kwargs.get("app_token", "")),
        ],
    }

    for env_name, env_value in token_map[channel]:
        if not env_value:
            continue
        try:
            from tools.security import vault
            result = vault.set_secret(env_name, env_value, namespace="channels")
            if not result.get("success"):
                _set_env_var(env_name, env_value)
        except Exception:
            try:
                _set_env_var(env_name, env_value)
            except Exception as e:
                errors.append(f"Failed to store {env_name}: {e}")

    # Update channels.yaml to enable the channel
    try:
        _enable_channel_yaml(channel)
    except Exception as e:
        errors.append(f"Failed to update channels.yaml: {e}")

    return {
        "success": len(errors) == 0,
        "channel": channel,
        "errors": errors,
    }


# ============================================================================
# run_migrations
# ============================================================================


def run_migrations() -> dict[str, Any]:
    """Run database migrations and initialise core databases.

    Returns:
        dict with ``success``, ``initialized`` list, and ``errors`` list.
    """
    initialized: list[str] = []
    errors: list[str] = []

    DATA_PATH.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "memory" / "logs").mkdir(parents=True, exist_ok=True)

    # Dashboard database
    try:
        from tools.dashboard.backend.database import init_db
        init_db()
        initialized.append("dashboard")
    except Exception as e:
        errors.append(f"Dashboard DB: {e}")

    # Memory database
    try:
        from tools.memory.memory_db import get_connection
        conn = get_connection()
        conn.close()
        initialized.append("memory")
    except Exception as e:
        errors.append(f"Memory DB: {e}")

    # Vault database
    try:
        from tools.security.vault import get_connection as get_vault_conn
        conn = get_vault_conn()
        conn.close()
        initialized.append("vault")
    except Exception as e:
        errors.append(f"Vault DB: {e}")

    # Forward-only SQL migrations (audit DB, etc.)
    try:
        from tools.ops.migrate import run_migrations as _run_sql_migrations
        result = _run_sql_migrations()
        if result.get("applied"):
            initialized.append(f"migrations({len(result['applied'])})")
    except Exception as e:
        errors.append(f"SQL migrations: {e}")

    return {
        "success": len(errors) == 0,
        "initialized": initialized,
        "errors": errors,
    }


# ============================================================================
# verify_installation
# ============================================================================


def verify_installation() -> dict[str, Any]:
    """Run post-setup verification checks.

    Returns:
        dict with ``success``, ``checks`` list, and ``warnings`` list.
    """
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    # 1. Check Python packages are importable
    for pkg_name, import_path in [
        ("anthropic", "anthropic"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("cryptography", "cryptography"),
        ("yaml", "yaml"),
    ]:
        try:
            __import__(import_path)
            checks.append({"name": pkg_name, "ok": True})
        except ImportError:
            checks.append({"name": pkg_name, "ok": False})
            warnings.append(f"Package '{pkg_name}' not importable")

    # 2. Check vault is accessible
    try:
        from tools.security.vault import get_connection
        conn = get_connection()
        conn.close()
        checks.append({"name": "vault_db", "ok": True})
    except Exception as e:
        checks.append({"name": "vault_db", "ok": False, "error": str(e)})
        warnings.append(f"Vault not accessible: {e}")

    # 3. Check master key is set
    master_key = os.environ.get("DEXAI_MASTER_KEY", "")
    has_master_key = bool(master_key) and master_key != "your-secure-master-password-here"
    checks.append({"name": "master_key", "ok": has_master_key})
    if not has_master_key:
        warnings.append("DEXAI_MASTER_KEY not set or is placeholder value")

    # 4. Check Anthropic key
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not has_api_key:
        try:
            from tools.security import vault
            result = vault.get_secret("ANTHROPIC_API_KEY", namespace="default")
            has_api_key = result.get("success", False)
        except Exception:
            pass
    checks.append({"name": "anthropic_key", "ok": has_api_key})
    if not has_api_key:
        warnings.append("Anthropic API key not configured")

    # 5. Check data directory
    data_ok = DATA_PATH.is_dir()
    checks.append({"name": "data_dir", "ok": data_ok})

    all_ok = all(c["ok"] for c in checks)
    return {
        "success": all_ok,
        "checks": checks,
        "warnings": warnings,
    }


# ============================================================================
# get_setup_status
# ============================================================================


def get_setup_status() -> dict[str, Any]:
    """Get current setup completion status.

    Returns a summary of what has been configured and what is still needed.

    Returns:
        dict with ``complete``, ``steps`` dict, and ``missing`` list.
    """
    steps: dict[str, bool] = {}
    missing: list[str] = []

    # Master key
    mk = os.environ.get("DEXAI_MASTER_KEY", "")
    steps["master_key"] = bool(mk) and mk != "your-secure-master-password-here"
    if not steps["master_key"]:
        missing.append("Master key (run: dexai setup)")

    # Anthropic key
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not has_api_key:
        try:
            from tools.security import vault
            result = vault.get_secret("ANTHROPIC_API_KEY", namespace="default")
            has_api_key = result.get("success", False)
        except Exception:
            pass
    steps["anthropic_key"] = has_api_key
    if not has_api_key:
        missing.append("Anthropic API key")

    # Databases
    steps["databases"] = (DATA_PATH / "dashboard.db").exists()
    if not steps["databases"]:
        missing.append("Database initialization")

    # User config
    user_yaml = CONFIG_PATH / "user.yaml"
    steps["user_config"] = user_yaml.exists()
    if not steps["user_config"]:
        missing.append("User preferences (name, timezone)")

    # At least one channel
    channels_yaml = CONFIG_PATH / "channels.yaml"
    steps["channel"] = False
    if channels_yaml.exists():
        try:
            import yaml
            with open(channels_yaml) as f:
                cfg = yaml.safe_load(f) or {}
            channels = cfg.get("channels", {})
            for ch_cfg in channels.values():
                if isinstance(ch_cfg, dict) and ch_cfg.get("enabled"):
                    steps["channel"] = True
                    break
        except Exception:
            pass
    if not steps["channel"]:
        missing.append("Messaging channel (telegram, discord, or slack)")

    complete = len(missing) == 0
    return {
        "success": True,
        "complete": complete,
        "steps": steps,
        "missing": missing,
    }


# ============================================================================
# Private Helpers
# ============================================================================


def _set_env_var(key: str, value: str) -> None:
    """Set or update a variable in the project .env file.

    If the key already exists (with any value), the line is replaced.
    Otherwise, the key=value pair is appended.

    Args:
        key: Environment variable name.
        value: Value to write.
    """
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    replaced = False

    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                if line.startswith(f"{key}="):
                    lines.append(f"{key}={value}\n")
                    replaced = True
                else:
                    lines.append(line)

    if not replaced:
        lines.append(f"{key}={value}\n")

    with open(ENV_FILE, "w") as f:
        f.writelines(lines)

    # Also export into the running process
    os.environ[key] = value


def _enable_channel_yaml(channel: str) -> None:
    """Enable *channel* in ``args/channels.yaml``.

    Args:
        channel: One of ``"telegram"``, ``"discord"``, ``"slack"``.
    """
    import yaml

    channels_path = CONFIG_PATH / "channels.yaml"
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)

    if channels_path.exists():
        with open(channels_path) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    if "channels" not in config:
        config["channels"] = {}

    if channel not in config["channels"]:
        config["channels"][channel] = {}

    config["channels"][channel]["enabled"] = True
    config["channels"][channel]["primary"] = True

    # Disable other channels as primary
    for ch in config["channels"]:
        if ch != channel and isinstance(config["channels"][ch], dict):
            config["channels"][ch]["primary"] = False

    with open(channels_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
