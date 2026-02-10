"""
Setup Flow Service — Deterministic Pre-LLM Bootstrap

Handles onboarding by checking which required fields are missing
(API key, user name, timezone) and asking for them one at a time
through the chat interface.

Uses the same streaming protocol (chunk/control/done) as LLM-driven chat,
making the transition invisible to the user.

Once all fields are populated, the flow becomes inactive and messages
are routed to the normal LLM pipeline.
"""

import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator
from zoneinfo import available_timezones

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "args"


class SetupFlowService:
    """
    Deterministic pre-LLM setup flow.

    Checks get_missing_setup_fields() to determine what's needed,
    then asks for each field in order (API key first).

    Text fields (name) are collected via the normal chat input.
    Select fields (timezone) emit a control with options + "Other".
    Secure fields (API key) emit a masked input control.
    """

    def __init__(self, conversation_id: str | None = None):
        self.conversation_id = conversation_id
        self._missing: list[dict[str, Any]] | None = None

    def _get_missing(self) -> list[dict[str, Any]]:
        """Get missing fields, cached for the lifetime of this request."""
        if self._missing is None:
            from tools.setup.wizard import get_missing_setup_fields
            self._missing = get_missing_setup_fields()
        return self._missing

    def _invalidate_cache(self) -> None:
        """Force re-check of missing fields after a value is stored."""
        self._missing = None

    @staticmethod
    def _resolve_timezone(text: str) -> tuple[str | None, list[str]]:
        """Resolve free text to IANA timezone(s).

        Returns (exact_match, candidates):
        - exact_match is set if the text is already a valid IANA zone
          or if there's a single unambiguous city match.
        - candidates is a list of possible IANA zones when ambiguous.

        Handles compound inputs like "Melbourne, UK" by extracting the
        city part and matching against IANA zone city segments.
        """
        all_zones = sorted(available_timezones())
        normalised = text.strip()

        # Direct IANA match (e.g. "Australia/Sydney")
        for tz in all_zones:
            if tz.lower() == normalised.lower():
                return tz, []

        # Build a list of queries to try: full text first, then the
        # city part if the input contains a comma or slash
        queries = [normalised]
        for sep in [",", "/"]:
            if sep in normalised:
                city_part = normalised.split(sep)[0].strip()
                if city_part and city_part != normalised:
                    queries.append(city_part)

        for query_raw in queries:
            query = query_raw.lower().replace(" ", "_")

            # Exact match on the city segment (last part after '/')
            matches = [
                tz for tz in all_zones
                if tz.split("/")[-1].lower() == query
            ]
            if len(matches) == 1:
                return matches[0], []
            if matches:
                return None, matches

            # Substring match on city segment
            matches = [
                tz for tz in all_zones
                if query in tz.split("/")[-1].lower()
            ]
            if len(matches) == 1:
                return matches[0], []
            if matches:
                return None, matches[:6]

        return None, []

    def _finalize_workspace_files(self) -> None:
        """Write USER.md (and other derived files) across all workspaces.

        Called once when ALL required setup fields are populated.
        Reads current values from args/user.yaml and writes them all at once.
        """
        try:
            from tools.setup.wizard import populate_workspace_files

            workspaces_dir = PROJECT_ROOT / "data" / "workspaces"
            if not workspaces_dir.exists():
                return

            user_yaml_path = CONFIG_PATH / "user.yaml"
            if not user_yaml_path.exists():
                return

            with open(user_yaml_path) as f:
                data = yaml.safe_load(f) or {}

            user_name = data.get("user", {}).get("name")
            timezone = data.get("user", {}).get("timezone")

            for workspace in workspaces_dir.iterdir():
                if workspace.is_dir():
                    if user_name:
                        populate_workspace_files(workspace, "user_name", user_name)
                    if timezone:
                        populate_workspace_files(workspace, "timezone", timezone)
        except Exception as e:
            logger.warning(f"Could not finalize workspace files: {e}")

    def _get_known_user_name(self) -> str | None:
        """Get the user's name if already set."""
        try:
            user_yaml_path = CONFIG_PATH / "user.yaml"
            if user_yaml_path.exists():
                with open(user_yaml_path) as f:
                    data = yaml.safe_load(f) or {}
                name = data.get("user", {}).get("name")
                if name:
                    return name
        except Exception:
            pass
        return None

    def is_active(self) -> bool:
        """Setup flow is active when any required field is missing."""
        return len(self._get_missing()) > 0

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def handle_message(
        self,
        message: str,
        control_response: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict]:
        """
        Main entry point — handles any message during setup flow.

        - control_response → submitted select/secure value
        - sk-ant-* / sk-*  → API key
        - free text         → routed to the next expected text/select field
        - __setup_init__    → prompt for next field with greeting
        """
        # Handle a submitted control value (select option or secure input)
        if control_response:
            async for chunk in self._handle_control_response(control_response):
                yield chunk
            return

        stripped = message.strip()

        # API key detection
        if stripped.startswith("sk-ant-") or stripped.startswith("sk-"):
            async for chunk in self._handle_field_value("anthropic_api_key", stripped):
                yield chunk
            return

        # Free-text input: route to the next expected field
        missing = self._get_missing()
        if missing and stripped and stripped != "__setup_init__":
            next_field = missing[0]
            if next_field["type"] in ("text_input", "select"):
                async for chunk in self._handle_field_value(next_field["field"], stripped):
                    yield chunk
                return

        # First interaction or re-prompt
        async for chunk in self._prompt_next_field(greeting=True):
            yield chunk

    async def _handle_control_response(
        self, control_response: dict[str, Any]
    ) -> AsyncIterator[dict]:
        """Handle a submitted control value, then prompt for the next field."""
        field = control_response.get("field", "")
        value = control_response.get("value", "")

        async for chunk in self._handle_field_value(field, value):
            yield chunk

    async def _handle_field_value(
        self, field: str, value: str
    ) -> AsyncIterator[dict]:
        """Validate and store a field value, then prompt for the next missing field."""
        if not value:
            yield {
                "type": "chunk",
                "content": "No value provided — please try again.",
                "conversation_id": self.conversation_id,
            }
            async for chunk in self._prompt_next_field():
                yield chunk
            return

        if field == "anthropic_api_key":
            async for chunk in self._store_api_key(value):
                yield chunk
        elif field == "user_name":
            self._store_user_yaml_value("user", "name", value)
            self._invalidate_cache()
            yield {
                "type": "chunk",
                "content": f"Nice to meet you, {value}!",
                "conversation_id": self.conversation_id,
            }
            async for chunk in self._prompt_next_field():
                yield chunk
        elif field == "timezone":
            exact, candidates = self._resolve_timezone(value)
            if exact:
                self._store_user_yaml_value("user", "timezone", exact)
                self._invalidate_cache()
                yield {
                    "type": "chunk",
                    "content": f"Timezone set to **{exact}**.",
                    "conversation_id": self.conversation_id,
                }
                async for chunk in self._prompt_next_field():
                    yield chunk
            elif candidates:
                # Ambiguous — offer suggestions as a select control
                yield {
                    "type": "chunk",
                    "content": (
                        f"I found a few timezones matching **{value}**. "
                        "Which one did you mean?"
                    ),
                    "conversation_id": self.conversation_id,
                }
                yield {
                    "type": "control",
                    "control_type": "select",
                    "control_id": "setup_timezone",
                    "field": "timezone",
                    "label": "Timezone",
                    "required": True,
                    "options": [
                        {"label": tz, "value": tz} for tz in candidates
                    ],
                    "conversation_id": self.conversation_id,
                }
                yield {"type": "done", "conversation_id": self.conversation_id}
            else:
                yield {
                    "type": "chunk",
                    "content": (
                        f"I couldn't find a timezone matching **{value}**. "
                        "Try a city name (e.g. **Sydney**) or IANA format "
                        "(e.g. **Australia/Sydney**)."
                    ),
                    "conversation_id": self.conversation_id,
                }
                async for chunk in self._prompt_next_field():
                    yield chunk
        else:
            yield {
                "type": "chunk",
                "content": "I didn't recognise that response. Let me try again.",
                "conversation_id": self.conversation_id,
            }
            async for chunk in self._prompt_next_field():
                yield chunk

    # ------------------------------------------------------------------
    # Prompting
    # ------------------------------------------------------------------

    async def _prompt_next_field(self, greeting: bool = False) -> AsyncIterator[dict]:
        """Emit a message (and optionally a control) for the next missing field.

        - text_input fields: question in the message, NO control emitted.
          The user types in the normal chat input.
        - select fields: question in the message, control emitted with options.
        - secure_input fields: question in the message, control emitted.
        """
        missing = self._get_missing()

        if not missing:
            # All required fields populated — finalize derived files
            self._finalize_workspace_files()

            yield {
                "type": "chunk",
                "content": (
                    "\n\nYou're all set! I'm ready to help. "
                    "Send me a message to get started."
                ),
                "conversation_id": self.conversation_id,
            }
            yield {"type": "done", "conversation_id": self.conversation_id}
            return

        next_field = missing[0]
        field_name = next_field["field"]

        # ------ Build the message text ------
        if greeting:
            known_name = self._get_known_user_name()
            hey = f"Hey {known_name}!" if known_name else "Hey!"

            if field_name == "anthropic_api_key":
                yield {
                    "type": "chunk",
                    "content": (
                        f"{hey} I'm Dex, your ADHD-friendly AI assistant. "
                        "Before we can chat properly, I need a few things from you.\n\n"
                        "First up — your **Anthropic API Key**. "
                        "You can get one from "
                        "[console.anthropic.com](https://console.anthropic.com/settings/keys). "
                        "Paste it below and I'll verify it works."
                    ),
                    "conversation_id": self.conversation_id,
                }
            elif field_name == "user_name":
                yield {
                    "type": "chunk",
                    "content": (
                        f"{hey} I'm Dex, your ADHD-friendly AI assistant. "
                        "I just need a couple of things to personalise your experience.\n\n"
                        "What should I call you? Type your **name** below."
                    ),
                    "conversation_id": self.conversation_id,
                }
            elif field_name == "timezone":
                yield {
                    "type": "chunk",
                    "content": (
                        f"{hey} I'm Dex, your ADHD-friendly AI assistant. "
                        "I just need one more thing.\n\n"
                        "Pick your **timezone** below, or choose **Other** to type your own."
                    ),
                    "conversation_id": self.conversation_id,
                }
        else:
            # Transition text after a field was just stored
            if field_name == "anthropic_api_key":
                yield {
                    "type": "chunk",
                    "content": (
                        "\n\nNow I need your **Anthropic API Key**. "
                        "Paste it below and I'll verify it works."
                    ),
                    "conversation_id": self.conversation_id,
                }
            elif field_name == "user_name":
                yield {
                    "type": "chunk",
                    "content": "\n\nWhat should I call you? Type your **name** below.",
                    "conversation_id": self.conversation_id,
                }
            elif field_name == "timezone":
                yield {
                    "type": "chunk",
                    "content": (
                        "\n\nNow pick your **timezone** below, "
                        "or choose **Other** to type your own."
                    ),
                    "conversation_id": self.conversation_id,
                }

        # ------ Emit control only for select / secure_input ------
        if next_field["type"] in ("select", "secure_input"):
            control: dict[str, Any] = {
                "type": "control",
                "control_type": next_field["type"],
                "control_id": f"setup_{field_name}",
                "field": field_name,
                "label": next_field.get("label", field_name),
                "required": next_field.get("required", True),
                "conversation_id": self.conversation_id,
            }
            if "placeholder" in next_field:
                control["placeholder"] = next_field["placeholder"]
            if "options" in next_field:
                control["options"] = next_field["options"]
            if "default_value" in next_field:
                control["default_value"] = next_field["default_value"]
            yield control

        yield {"type": "done", "conversation_id": self.conversation_id}

    # ------------------------------------------------------------------
    # Storage helpers
    # ------------------------------------------------------------------

    async def _store_api_key(self, api_key: str) -> AsyncIterator[dict]:
        """Validate and store an API key, then prompt for next field."""
        yield {
            "type": "chunk",
            "content": "Checking your API key...",
            "conversation_id": self.conversation_id,
        }

        try:
            from tools.setup.wizard import validate_anthropic_key
            result = await validate_anthropic_key(api_key)
        except Exception as e:
            result = {"success": False, "error": str(e)}

        if not result.get("success"):
            error = result.get("error", "Unknown validation error")
            yield {
                "type": "chunk",
                "content": f"\n\nThat didn't work: {error}\n\nPlease double-check and try again.",
                "conversation_id": self.conversation_id,
            }
            async for chunk in self._prompt_next_field():
                yield chunk
            return

        os.environ["ANTHROPIC_API_KEY"] = api_key

        try:
            from tools.security import vault
            vault.set_secret("ANTHROPIC_API_KEY", api_key, namespace="default")
        except Exception as e:
            logger.warning(f"Could not store API key in vault: {e}")

        try:
            env_path = PROJECT_ROOT / ".env"
            if env_path.exists():
                content = env_path.read_text()
                if "ANTHROPIC_API_KEY=" in content:
                    lines = content.splitlines()
                    new_lines = [
                        f"ANTHROPIC_API_KEY={api_key}" if line.startswith("ANTHROPIC_API_KEY=") else line
                        for line in lines
                    ]
                    env_path.write_text("\n".join(new_lines) + "\n")
                else:
                    with open(env_path, "a") as f:
                        f.write(f"\nANTHROPIC_API_KEY={api_key}\n")
            else:
                env_path.write_text(f"ANTHROPIC_API_KEY={api_key}\n")
        except Exception as e:
            logger.warning(f"Could not write API key to .env: {e}")

        self._invalidate_cache()

        yield {
            "type": "chunk",
            "content": "\n\nAPI key verified and stored!",
            "conversation_id": self.conversation_id,
        }

        async for chunk in self._prompt_next_field():
            yield chunk

    def _store_user_yaml_value(self, *keys_and_value: str) -> None:
        """Write a value into args/user.yaml. Last argument is the value, rest are keys."""
        path_keys = keys_and_value[:-1]
        value = keys_and_value[-1]
        CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        user_yaml_path = CONFIG_PATH / "user.yaml"

        try:
            if user_yaml_path.exists():
                with open(user_yaml_path) as f:
                    data = yaml.safe_load(f) or {}
            else:
                data = {}

            current = data
            for key in path_keys[:-1]:
                if key not in current or not isinstance(current[key], dict):
                    current[key] = {}
                current = current[key]
            current[path_keys[-1]] = value

            with open(user_yaml_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.error(f"Failed to write user.yaml: {e}")
