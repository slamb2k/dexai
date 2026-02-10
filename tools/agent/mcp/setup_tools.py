"""
DexAI Setup MCP Tools

Provides LLM-invocable tools for the onboarding experience (Phase 2):
- dexai_show_control: Emit rich inline controls to the chat UI
- dexai_save_setup_value: Persist setup values to args/user.yaml, vault, etc.

These use thread-local storage (same pattern as channel_tools.py pending images)
to pass control data from tool execution to the response stream handler.
"""

import os
import threading
from pathlib import Path
from typing import Any

# Thread-local storage for pending controls
_pending_controls = threading.local()

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def get_pending_control() -> dict | None:
    """Get the pending control for the current thread."""
    return getattr(_pending_controls, "control", None)


def set_pending_control(control: dict) -> None:
    """Set a pending control for the response handler to emit."""
    _pending_controls.control = control


def clear_pending_control() -> None:
    """Clear the pending control."""
    _pending_controls.control = None


def dexai_show_control(
    control_type: str,
    field: str,
    label: str = "",
    options: list | None = None,
    default_value: str = "",
    placeholder: str = "",
    required: bool = True,
) -> dict[str, Any]:
    """
    Show a rich inline control in the chat UI.

    Use this when you need to collect structured input from the user during
    onboarding or configuration. The control will appear inline in your
    message bubble.

    Args:
        control_type: One of "select", "button_group", "text_input", "secure_input"
        field: The setting field name (e.g. "timezone", "user_name")
        label: Display label for the control
        options: For select/button_group — list of {"value": str, "label": str, "description": str}
        default_value: Pre-selected value
        placeholder: Placeholder text for input fields
        required: Whether the field is required

    Returns:
        {"success": True, "field": str, "control_type": str}
    """
    import uuid

    control = {
        "control_type": control_type,
        "control_id": f"setup_{field}_{uuid.uuid4().hex[:6]}",
        "field": field,
        "label": label,
        "required": required,
    }

    if options:
        control["options"] = options
    if default_value:
        control["default_value"] = default_value
    if placeholder:
        control["placeholder"] = placeholder

    set_pending_control(control)

    return {
        "success": True,
        "field": field,
        "control_type": control_type,
        "message": f"Showing {control_type} control for '{field}'.",
    }


def dexai_save_setup_value(field: str, value: str) -> dict[str, Any]:
    """
    Persist a setup configuration value.

    Writes to the appropriate storage location based on the field:
    - API keys → vault + environment
    - User preferences → args/user.yaml
    - Workspace files → USER.md, etc.

    After saving, checks if all required fields are present and marks
    setup complete if so.

    Args:
        field: The setting field name (e.g. "user_name", "timezone")
        value: The value to store

    Returns:
        {"success": True, "field": str, "setup_complete": bool}
    """
    import logging

    logger = logging.getLogger(__name__)

    if not field or not value:
        return {"success": False, "error": "Both field and value are required."}

    try:
        if field == "anthropic_api_key":
            _save_api_key(value)
        elif field in ("user_name", "timezone"):
            _save_user_yaml(field, value)
            # Also update workspace files
            _update_workspace_files(field, value)
        else:
            _save_user_yaml(field, value)

        # Check if setup is now complete
        from tools.setup.wizard import get_missing_setup_fields, is_setup_complete
        from tools.setup import SETUP_COMPLETE_FLAG

        missing = get_missing_setup_fields()
        required_missing = [f for f in missing if f.get("required")]
        setup_complete = len(required_missing) == 0

        if setup_complete and not is_setup_complete():
            SETUP_COMPLETE_FLAG.parent.mkdir(parents=True, exist_ok=True)
            SETUP_COMPLETE_FLAG.touch()
            logger.info("Setup marked as complete — all required fields present.")

        return {
            "success": True,
            "field": field,
            "setup_complete": setup_complete,
            "remaining_fields": len(required_missing),
        }

    except Exception as e:
        logger.error(f"Failed to save setup value {field}: {e}")
        return {"success": False, "error": str(e)}


def _save_api_key(api_key: str) -> None:
    """Store API key in environment and vault."""
    os.environ["ANTHROPIC_API_KEY"] = api_key
    try:
        from tools.security import vault

        vault.set_secret("ANTHROPIC_API_KEY", api_key, namespace="default")
    except Exception:
        pass


def _save_user_yaml(field: str, value: str) -> None:
    """Write a value to args/user.yaml."""
    import yaml

    config_path = PROJECT_ROOT / "args"
    config_path.mkdir(parents=True, exist_ok=True)
    user_yaml = config_path / "user.yaml"

    if user_yaml.exists():
        with open(user_yaml) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # Map field names to YAML structure
    field_map = {
        "user_name": ("user", "name"),
        "timezone": ("user", "timezone"),
    }

    keys = field_map.get(field)
    if keys:
        # Navigate/create nested structure
        current = data
        for key in keys[:-1]:
            if key not in current or not isinstance(current.get(key), dict):
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
    else:
        # Store at top level under a 'setup' key
        if "setup" not in data:
            data["setup"] = {}
        data["setup"][field] = value

    with open(user_yaml, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _update_workspace_files(field: str, value: str) -> None:
    """Update workspace template files (USER.md etc.)."""
    try:
        from tools.setup.wizard import populate_workspace_files

        # Try both .claude/ workspace and project root
        workspace = PROJECT_ROOT / ".claude"
        if workspace.exists():
            populate_workspace_files(workspace, field, value)

        # Also check for workspace subdirectories
        for ws_dir in workspace.glob("*/"):
            if ws_dir.is_dir():
                populate_workspace_files(ws_dir, field, value)
    except Exception:
        pass


# =============================================================================
# Tool registry (standard pattern for MCP tool modules)
# =============================================================================


def list_tools() -> list[str]:
    """List available setup tools."""
    return ["dexai_show_control", "dexai_save_setup_value"]


def get_tool(name: str):
    """Get a tool function by name."""
    tools = {
        "dexai_show_control": dexai_show_control,
        "dexai_save_setup_value": dexai_save_setup_value,
    }
    return tools.get(name)
