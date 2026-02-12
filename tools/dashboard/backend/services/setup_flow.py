"""
Setup Flow Service — Deterministic Pre-LLM Bootstrap

Handles onboarding by checking which required fields are missing
(API key, user name, timezone) and asking for them one at a time
through the chat interface.  After required fields are complete,
runs an optional phase with 11 additional questions (schedule,
channels, ADHD context) that can each be skipped.

Uses the same streaming protocol (chunk/control/done) as LLM-driven chat,
making the transition invisible to the user.

Once all fields are populated (or skipped), the flow becomes inactive
and messages are routed to the normal LLM pipeline.

Selection patterns supported:

  Type 1 — Strict single select (e.g. timezone):
    Options + "Something else". User MUST pick from provided options.
    "Something else" → free text → resolve to new options → must pick.

  Type 2 — Flexible single select:
    Options + "Something else". Free text accepted as-is.

  Type 3 — Multi-select strict:
    Toggleable options, confirm button. No custom items.
    Value arrives as JSON array: '["opt1","opt2"]'.

  Type 4 — Multi-select flexible:
    Same as Type 3 but also allows custom items added by the user.
    Value arrives as JSON array: '["opt1","custom_item"]'.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator
from zoneinfo import available_timezones

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "args"


# ======================================================================
# Optional field definitions (O1–O11)
# ======================================================================

OPTIONAL_FIELDS: list[dict[str, Any]] = [
    # --- Group A: Schedule & Preferences ---
    {
        "field": "active_hours_start",
        "label": "When does your day usually start?",
        "type": "select",
        "options": [
            {"label": "6:00 AM", "value": "06:00"},
            {"label": "7:00 AM", "value": "07:00"},
            {"label": "8:00 AM", "value": "08:00"},
            {"label": "9:00 AM", "value": "09:00"},
            {"label": "10:00 AM", "value": "10:00"},
            {"label": "11:00 AM", "value": "11:00"},
            {"label": "12:00 PM", "value": "12:00"},
        ],
        "yaml_path": ("active_hours", "start"),
        "group": "preferences",
        "depends_on": None,
        "strict": False,
    },
    {
        "field": "active_hours_end",
        "label": "When do you usually wrap up?",
        "type": "select",
        "options": [
            {"label": "5:00 PM", "value": "17:00"},
            {"label": "6:00 PM", "value": "18:00"},
            {"label": "7:00 PM", "value": "19:00"},
            {"label": "8:00 PM", "value": "20:00"},
            {"label": "9:00 PM", "value": "21:00"},
            {"label": "10:00 PM", "value": "22:00"},
            {"label": "11:00 PM", "value": "23:00"},
        ],
        "yaml_path": ("active_hours", "end"),
        "group": "preferences",
        "depends_on": None,
        "strict": False,
    },
    {
        "field": "active_days",
        "label": "Which days do you typically work?",
        "type": "select",
        "multi_select": True,
        "allow_custom": False,
        "options": [
            {"label": "Monday", "value": "mon"},
            {"label": "Tuesday", "value": "tue"},
            {"label": "Wednesday", "value": "wed"},
            {"label": "Thursday", "value": "thu"},
            {"label": "Friday", "value": "fri"},
            {"label": "Saturday", "value": "sat"},
            {"label": "Sunday", "value": "sun"},
        ],
        "yaml_path": ("active_hours", "days"),
        "group": "preferences",
        "depends_on": None,
        "strict": True,
    },
    {
        "field": "notification_style",
        "label": "How should I get your attention?",
        "type": "select",
        "options": [
            {"label": "Gentle", "value": "gentle", "description": "Soft nudges, never pushy"},
            {"label": "Balanced", "value": "balanced", "description": "Clear but not overwhelming"},
            {"label": "Persistent", "value": "persistent", "description": "Keep reminding until done"},
        ],
        "yaml_path": ("preferences", "notification_style"),
        "group": "preferences",
        "depends_on": None,
        "strict": True,
    },
    {
        "field": "brevity_preference",
        "label": "How much detail do you prefer?",
        "type": "select",
        "options": [
            {"label": "Brief", "value": "brief", "description": "Short and to the point"},
            {"label": "Balanced", "value": "balanced", "description": "Some detail, not too much"},
            {"label": "Detailed", "value": "detailed", "description": "Give me everything"},
        ],
        "yaml_path": ("preferences", "brevity_default"),
        "group": "preferences",
        "depends_on": None,
        "strict": True,
    },
    # --- Group B: Channels ---
    {
        "field": "primary_channel",
        "label": "Want to connect a messaging channel?",
        "type": "select",
        "options": [
            {"label": "Telegram", "value": "telegram"},
            {"label": "Discord", "value": "discord"},
            {"label": "Slack", "value": "slack"},
            {"label": "Web only", "value": "web"},
        ],
        "yaml_path": ("channels", "primary"),
        "group": "channels",
        "depends_on": None,
        "strict": True,
    },
    {
        "field": "channel_token",
        "label": "Paste your bot token",
        "type": "secure_input",
        "placeholder": "Bot token",
        "yaml_path": None,  # stored in vault
        "group": "channels",
        "depends_on": "primary_channel",
        "skip_if_parent_value": "web",
    },
    {
        "field": "slack_app_token",
        "label": "Paste your Slack app token",
        "type": "secure_input",
        "placeholder": "xapp-...",
        "yaml_path": None,  # stored in vault
        "group": "channels",
        "depends_on": "primary_channel",
        "only_if_parent_value": "slack",
    },
    # --- Group C: ADHD Context ---
    {
        "field": "work_focus_areas",
        "label": "What kind of work do you mostly do?",
        "type": "select",
        "multi_select": True,
        "allow_custom": True,
        "placeholder": "Add your own (comma-separated)",
        "options": [
            {"label": "Software Development", "value": "software_dev"},
            {"label": "Writing & Content", "value": "writing"},
            {"label": "Design", "value": "design"},
            {"label": "Research", "value": "research"},
            {"label": "Project Management", "value": "project_mgmt"},
            {"label": "Admin & Operations", "value": "admin"},
        ],
        "yaml_path": ("preferences", "work_focus_areas"),
        "group": "adhd",
        "depends_on": None,
    },
    {
        "field": "energy_pattern",
        "label": "When do you usually have the most energy?",
        "type": "select",
        "options": [
            {"label": "Morning", "value": "morning", "description": "Peak focus before noon"},
            {"label": "Afternoon", "value": "afternoon", "description": "Hit my stride after lunch"},
            {"label": "Evening", "value": "evening", "description": "Best work happens late"},
            {"label": "Variable", "value": "variable", "description": "Changes day to day"},
        ],
        "yaml_path": ("preferences", "energy_pattern"),
        "group": "adhd",
        "depends_on": None,
        "strict": True,
    },
    {
        "field": "adhd_challenges",
        "label": "What trips you up the most?",
        "type": "select",
        "multi_select": True,
        "allow_custom": True,
        "placeholder": "Add your own (comma-separated)",
        "options": [
            {"label": "Getting started", "value": "getting_started"},
            {"label": "Task switching", "value": "task_switching"},
            {"label": "Staying focused", "value": "staying_focused"},
            {"label": "Finishing things", "value": "finishing"},
            {"label": "Time estimation", "value": "time_estimation"},
            {"label": "Prioritising", "value": "prioritising"},
        ],
        "yaml_path": ("preferences", "adhd_challenges"),
        "group": "adhd",
        "depends_on": None,
    },
    {
        "field": "encouragement_level",
        "label": "How much encouragement do you want?",
        "type": "select",
        "options": [
            {"label": "None", "value": "none", "description": "Just the facts"},
            {"label": "Light", "value": "light", "description": "A gentle nudge now and then"},
            {"label": "Full", "value": "full", "description": "Celebrate wins, cheer me on"},
        ],
        "yaml_path": ("preferences", "encouragement_level"),
        "group": "adhd",
        "depends_on": "adhd_challenges",
        "strict": True,
    },
]


class SetupFlowService:
    """
    Deterministic pre-LLM setup flow.

    Checks get_missing_setup_fields() to determine what's needed,
    then asks for each field in order (API key first).

    Text fields (name) are collected via the normal chat input.
    Select fields (timezone) emit a control with options + "Something else".
    Secure fields (API key) emit a masked input control.

    Select fields support two modes:

    **Strict select** (e.g. timezone):
      Options + "Something else". Choosing an option accepts it.
      Choosing "Something else" asks the user to type free text, which
      is resolved into new options. The user MUST eventually pick from
      Dex-provided options — free text only narrows the search.

    **Flexible select** (future fields):
      Options + "Something else". Choosing an option accepts it.
      Choosing "Something else" asks for free text which is accepted
      as-is — useful when offering common choices but allowing custom
      input.
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

    @staticmethod
    def _parse_multi_select(value: str) -> list[str] | None:
        """Parse a multi-select value (JSON array string) into a list.

        Returns None if the value is not a valid JSON array.
        """
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list) and all(isinstance(v, str) for v in parsed):
                return [v for v in parsed if v.strip()]
        except (json.JSONDecodeError, TypeError):
            pass
        return None

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
            tz = data.get("user", {}).get("timezone")
            energy = data.get("preferences", {}).get("energy_pattern")
            challenges = data.get("preferences", {}).get("adhd_challenges")
            focus = data.get("preferences", {}).get("work_focus_areas")

            field_values = {
                "user_name": user_name,
                "timezone": tz,
                "energy_pattern": energy,
                "adhd_challenges": (
                    ", ".join(challenges) if isinstance(challenges, list) else challenges
                ),
                "work_focus_areas": (
                    ", ".join(focus) if isinstance(focus, list) else focus
                ),
            }

            for workspace in workspaces_dir.iterdir():
                if workspace.is_dir():
                    for field, value in field_values.items():
                        if value:
                            populate_workspace_files(workspace, field, str(value))
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

    # ------------------------------------------------------------------
    # Onboarding state helpers
    # ------------------------------------------------------------------

    def _get_onboarding_state(self) -> dict[str, Any]:
        """Read the onboarding section from args/user.yaml."""
        try:
            user_yaml_path = CONFIG_PATH / "user.yaml"
            if user_yaml_path.exists():
                with open(user_yaml_path) as f:
                    data = yaml.safe_load(f) or {}
                return data.get("onboarding", {})
        except Exception:
            pass
        return {}

    def _update_onboarding_state(self, **kwargs: Any) -> None:
        """Update specific keys in the onboarding section of user.yaml."""
        CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        user_yaml_path = CONFIG_PATH / "user.yaml"
        try:
            if user_yaml_path.exists():
                with open(user_yaml_path) as f:
                    data = yaml.safe_load(f) or {}
            else:
                data = {}
            if "onboarding" not in data:
                data["onboarding"] = {}
            data["onboarding"].update(kwargs)
            with open(user_yaml_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.error(f"Failed to update onboarding state: {e}")

    def _get_optional_fields_for_scope(self, scope: str) -> list[dict[str, Any]]:
        """Filter OPTIONAL_FIELDS by group scope."""
        if scope == "all":
            return list(OPTIONAL_FIELDS)
        return [f for f in OPTIONAL_FIELDS if f.get("group") == scope]

    # ------------------------------------------------------------------
    # Active check
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        """Setup flow is active when required fields are missing or optional phase is in progress."""
        if len(self._get_missing()) > 0:
            return True
        state = self._get_onboarding_state()
        idx = state.get("optional_index", -1)
        return idx >= 0 and not state.get("optional_completed", False)

    # ------------------------------------------------------------------
    # Welcome bundle (REST endpoint support)
    # ------------------------------------------------------------------

    def get_welcome_bundle(self) -> dict[str, Any]:
        """Return the welcome state as structured data for the REST endpoint.

        Determines the current onboarding scenario and returns the appropriate
        greeting text and optional control, without streaming.  This lets the
        frontend render the greeting instantly instead of waiting for a
        WebSocket round-trip.

        Returns dict with keys:
            scenario: str   — "no_api_key" | "needs_name" | "needs_timezone"
                              | "optional_pending" | "ready"
            greeting: str   — Markdown greeting text
            control:  dict | None — Inline control definition (select / secure_input)
            user_name: str | None — Known user name (if any)
        """
        missing = self._get_missing()
        known_name = self._get_known_user_name()
        hey = f"Hey {known_name}!" if known_name else "Hey!"

        # --- Required fields still missing ---
        if missing:
            next_field = missing[0]
            field_name = next_field["field"]

            if field_name == "anthropic_api_key":
                greeting = (
                    f"{hey} I'm Dex, your ADHD-friendly AI assistant. "
                    "Before we can chat properly, I need a few things from you.\n\n"
                    "First up — your **Anthropic API Key**. "
                    "You can get one from "
                    "[console.anthropic.com](https://console.anthropic.com/settings/keys). "
                    "Paste it below and I'll verify it works."
                )
                return {
                    "scenario": "no_api_key",
                    "greeting": greeting,
                    "control": {
                        "control_type": "secure_input",
                        "control_id": "setup_anthropic_api_key",
                        "field": "anthropic_api_key",
                        "label": next_field.get("label", "API Key"),
                        "placeholder": next_field.get("placeholder", "sk-ant-..."),
                        "required": True,
                    },
                    "user_name": known_name,
                }

            if field_name == "user_name":
                greeting = (
                    f"{hey} I'm Dex, your ADHD-friendly AI assistant. "
                    "I just need a couple of things to personalise your experience.\n\n"
                    "What should I call you? Type your **name** below."
                )
                return {
                    "scenario": "needs_name",
                    "greeting": greeting,
                    "control": None,
                    "user_name": known_name,
                }

            if field_name == "timezone":
                greeting = (
                    f"{hey} I'm Dex, your ADHD-friendly AI assistant. "
                    "I just need one more thing.\n\n"
                    "Pick your **timezone** from the options below. "
                    "If yours isn't listed, choose **Something else** and I'll help you find yours."
                )
                control = {
                    "control_type": "select",
                    "control_id": "setup_timezone",
                    "field": "timezone",
                    "label": next_field.get("label", "Timezone"),
                    "required": True,
                }
                if "options" in next_field:
                    control["options"] = next_field["options"]
                if "default_value" in next_field:
                    control["default_value"] = next_field["default_value"]
                return {
                    "scenario": "needs_timezone",
                    "greeting": greeting,
                    "control": control,
                    "user_name": known_name,
                }

        # --- Required fields done — check optional phase ---
        state = self._get_onboarding_state()
        optional_completed = state.get("optional_completed", False)
        idx = state.get("optional_index", -1)

        if not optional_completed:
            scope = state.get("optional_scope", "all")
            fields = self._get_optional_fields_for_scope(scope)

            # Haven't started optional phase yet — start it
            if idx < 0:
                self._update_onboarding_state(optional_index=0, version=1)
                idx = 0

            # Skip dependent fields that should be auto-skipped
            while idx < len(fields):
                if self._should_skip_dependent(fields[idx], state):
                    skipped = state.get("skipped_fields", [])
                    if fields[idx]["field"] not in skipped:
                        skipped.append(fields[idx]["field"])
                        self._update_onboarding_state(skipped_fields=skipped)
                        state["skipped_fields"] = skipped
                    idx += 1
                    self._update_onboarding_state(optional_index=idx)
                else:
                    break

            if idx < len(fields):
                field_def = fields[idx]
                intro = ""
                if idx == 0 and state.get("optional_index", -1) <= 0:
                    intro = (
                        "You're all set to use Dex! I have a few quick questions "
                        "that help me work better for you. **No pressure — skip any of them.**\n\n"
                    )
                greeting = f"{hey} {intro}{field_def['label']}"

                control: dict[str, Any] = {
                    "control_type": field_def["type"],
                    "control_id": f"setup_{field_def['field']}",
                    "field": field_def["field"],
                    "label": field_def.get("label", field_def["field"]),
                    "required": False,
                    "skippable": True,
                }
                if "options" in field_def:
                    control["options"] = field_def["options"]
                if "placeholder" in field_def:
                    control["placeholder"] = field_def["placeholder"]
                if field_def.get("multi_select"):
                    control["multi_select"] = True
                if field_def.get("allow_custom"):
                    control["allow_custom"] = True
                existing = self._read_optional_field_value(field_def["field"])
                if existing:
                    control["default_value"] = existing

                # Finalize workspace files since required fields are done
                self._finalize_workspace_files()

                return {
                    "scenario": "optional_pending",
                    "greeting": greeting,
                    "control": control,
                    "user_name": known_name,
                }
            else:
                # All optional fields exhausted — mark complete
                self._update_onboarding_state(
                    optional_completed=True,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                self._finalize_workspace_files()

        # --- Everything complete ---
        self._finalize_workspace_files()
        greeting = (
            f"{hey} I'm Dex, your ADHD-friendly AI assistant. "
            "How can I help?"
        )
        return {
            "scenario": "ready",
            "greeting": greeting,
            "control": None,
            "user_name": known_name,
        }

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
        # Required fields still missing — handle those first
        missing = self._get_missing()
        if missing:
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
            if stripped and stripped != "__setup_init__":
                next_field = missing[0]
                if next_field["type"] in ("text_input", "select"):
                    async for chunk in self._handle_field_value(next_field["field"], stripped):
                        yield chunk
                    return

            # First interaction or re-prompt
            async for chunk in self._prompt_next_field(greeting=True):
                yield chunk
            return

        # Required fields are done — route to optional phase
        async for chunk in self._handle_optional_phase(message, control_response):
            yield chunk

    async def _handle_control_response(
        self, control_response: dict[str, Any]
    ) -> AsyncIterator[dict]:
        """Handle a submitted control value, then prompt for the next field."""
        field = control_response.get("field", "")
        value = control_response.get("value", "")

        async for chunk in self._handle_field_value(field, value, from_control=True):
            yield chunk

    async def _handle_field_value(
        self, field: str, value: str, *, from_control: bool = False
    ) -> AsyncIterator[dict]:
        """Validate and store a field value, then prompt for the next missing field.

        from_control: True when the value came from clicking a select button
        (accept directly). False when typed as free text (strict selects must
        present matches as options to click).
        """
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
            # --- Strict select: user must pick from Dex-provided options ---

            # User chose "Something else" — ask them to type a search term
            if value == "__other__":
                yield {
                    "type": "chunk",
                    "content": (
                        "No worries! Type a **city name** or timezone below "
                        "(e.g. **Melbourne** or **Australia/Melbourne**) "
                        "and I'll find matching options for you."
                    ),
                    "conversation_id": self.conversation_id,
                }
                yield {"type": "done", "conversation_id": self.conversation_id}
                return

            exact, candidates = self._resolve_timezone(value)

            if from_control and exact:
                # User clicked a button — accept directly
                self._store_user_yaml_value("user", "timezone", exact)
                self._invalidate_cache()
                yield {
                    "type": "chunk",
                    "content": f"Timezone set to **{exact}**.",
                    "conversation_id": self.conversation_id,
                }
                async for chunk in self._prompt_next_field():
                    yield chunk
            elif exact or candidates:
                # Free text resolved to matches — present them to pick
                all_matches = [exact] if exact else candidates
                if len(all_matches) == 1:
                    msg = (
                        f"I found **{all_matches[0]}** matching **{value}**. "
                        "Select it below to confirm, or choose "
                        "**Something else** to try a different name."
                    )
                else:
                    msg = (
                        f"I found a few timezones matching **{value}**. "
                        "Pick the right one below, or choose "
                        "**Something else** to try a different name."
                    )
                yield {
                    "type": "chunk",
                    "content": msg,
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
                        {"label": tz, "value": tz} for tz in all_matches
                    ],
                    "conversation_id": self.conversation_id,
                }
                yield {"type": "done", "conversation_id": self.conversation_id}
            else:
                # No match at all — re-present the original options
                yield {
                    "type": "chunk",
                    "content": (
                        f"I couldn't find any timezones matching **{value}**. "
                        "Pick from the options below, or choose "
                        "**Something else** to try a different name."
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

            # Start optional phase
            state = self._get_onboarding_state()
            if not state.get("optional_completed", False) and state.get("optional_index", -1) < 0:
                yield {
                    "type": "chunk",
                    "content": (
                        "\n\nYou're all set to use Dex! I've got a few quick questions "
                        "that help me work better for you. **No pressure — skip any of them.**"
                    ),
                    "conversation_id": self.conversation_id,
                }
                self._update_onboarding_state(optional_index=0, version=1)
                # Prompt the first optional field
                fields = self._get_optional_fields_for_scope(
                    state.get("optional_scope", "all")
                )
                if fields:
                    async for chunk in self._prompt_optional_field(fields[0]):
                        yield chunk
                    return

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
                        "Pick your **timezone** from the options below. "
                        "If yours isn't listed, choose **Something else** and I'll help you find yours."
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
                        "\n\nNow pick your **timezone** from the options below. "
                        "If yours isn't listed, choose **Something else** and I'll help you find yours."
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
    # Optional phase
    # ------------------------------------------------------------------

    async def _handle_optional_phase(
        self,
        message: str,
        control_response: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict]:
        """Handle the optional onboarding questions (O1–O11)."""
        state = self._get_onboarding_state()
        scope = state.get("optional_scope", "all")
        fields = self._get_optional_fields_for_scope(scope)
        idx = state.get("optional_index", -1)

        # Not yet started — start now
        if idx < 0:
            yield {
                "type": "chunk",
                "content": (
                    "I've got a few quick questions that help me work better for you. "
                    "**No pressure — skip any of them.**"
                ),
                "conversation_id": self.conversation_id,
            }
            self._update_onboarding_state(optional_index=0, version=1)
            if fields:
                field_def = fields[0]
                if self._should_skip_dependent(field_def, state):
                    async for chunk in self._advance_optional(0, fields, state, auto_skipped=True):
                        yield chunk
                else:
                    async for chunk in self._prompt_optional_field(field_def):
                        yield chunk
            else:
                async for chunk in self._complete_optional():
                    yield chunk
            return

        # Handle the response for the current field
        if idx >= len(fields):
            async for chunk in self._complete_optional():
                yield chunk
            return

        field_def = fields[idx]
        value = ""

        if control_response:
            value = control_response.get("value", "")
        elif message.strip() and message.strip() not in ("__setup_init__", "__control_response__"):
            value = message.strip()

        # Skip
        if value == "__skip__":
            skipped = state.get("skipped_fields", [])
            skipped.append(field_def["field"])
            self._update_onboarding_state(skipped_fields=skipped)
            async for chunk in self._advance_optional(idx, fields, state):
                yield chunk
            return

        # Store value
        if value:
            self._store_optional_value(field_def, value)
            async for chunk in self._advance_optional(idx, fields, state):
                yield chunk
            return

        # Re-prompt current field
        if self._should_skip_dependent(field_def, state):
            async for chunk in self._advance_optional(idx, fields, state, auto_skipped=True):
                yield chunk
        else:
            async for chunk in self._prompt_optional_field(field_def):
                yield chunk

    async def _advance_optional(
        self,
        current_idx: int,
        fields: list[dict[str, Any]],
        state: dict[str, Any],
        *,
        auto_skipped: bool = False,
    ) -> AsyncIterator[dict]:
        """Move to the next optional field, auto-skipping dependents if needed."""
        next_idx = current_idx + 1

        # Auto-skip dependent fields
        while next_idx < len(fields):
            next_field = fields[next_idx]
            if self._should_skip_dependent(next_field, state):
                skipped = state.get("skipped_fields", [])
                if next_field["field"] not in skipped:
                    skipped.append(next_field["field"])
                    self._update_onboarding_state(skipped_fields=skipped)
                    state["skipped_fields"] = skipped
                next_idx += 1
            else:
                break

        if next_idx >= len(fields):
            self._update_onboarding_state(optional_index=next_idx)
            if not auto_skipped:
                async for chunk in self._complete_optional():
                    yield chunk
            else:
                yield {
                    "type": "chunk",
                    "content": "No worries! Skipping the follow-up too.",
                    "conversation_id": self.conversation_id,
                }
                async for chunk in self._complete_optional():
                    yield chunk
            return

        self._update_onboarding_state(optional_index=next_idx)

        if auto_skipped and next_idx > current_idx + 1:
            yield {
                "type": "chunk",
                "content": "No worries! Skipping the follow-up too.",
                "conversation_id": self.conversation_id,
            }

        async for chunk in self._prompt_optional_field(fields[next_idx]):
            yield chunk

    def _should_skip_dependent(
        self, field_def: dict[str, Any], state: dict[str, Any]
    ) -> bool:
        """Check if a field should be auto-skipped due to dependency."""
        depends_on = field_def.get("depends_on")
        if not depends_on:
            return False

        skipped = state.get("skipped_fields", [])
        if depends_on in skipped:
            return True

        # Check skip_if_parent_value
        skip_val = field_def.get("skip_if_parent_value")
        if skip_val:
            parent_value = self._read_optional_field_value(depends_on)
            if parent_value == skip_val:
                return True

        # Check only_if_parent_value
        only_val = field_def.get("only_if_parent_value")
        if only_val:
            parent_value = self._read_optional_field_value(depends_on)
            if parent_value != only_val:
                return True

        return False

    def _read_optional_field_value(self, field: str) -> str | None:
        """Read the current value of an optional field from user.yaml."""
        for fdef in OPTIONAL_FIELDS:
            if fdef["field"] == field:
                yaml_path = fdef.get("yaml_path")
                if not yaml_path:
                    return None
                try:
                    user_yaml_path = CONFIG_PATH / "user.yaml"
                    if user_yaml_path.exists():
                        with open(user_yaml_path) as f:
                            data = yaml.safe_load(f) or {}
                        current = data
                        for key in yaml_path:
                            current = current.get(key, {}) if isinstance(current, dict) else None
                            if current is None:
                                return None
                        return str(current) if current else None
                except Exception:
                    return None
        return None

    async def _complete_optional(self) -> AsyncIterator[dict]:
        """Mark optional phase complete and emit done message."""
        self._update_onboarding_state(
            optional_completed=True,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        self._finalize_workspace_files()
        yield {
            "type": "chunk",
            "content": (
                "\n\nAll done! I've got everything I need. "
                "Send me a message whenever you're ready."
            ),
            "conversation_id": self.conversation_id,
        }
        yield {"type": "done", "conversation_id": self.conversation_id}

    async def _prompt_optional_field(self, field_def: dict[str, Any]) -> AsyncIterator[dict]:
        """Emit question text + control for an optional field."""
        yield {
            "type": "chunk",
            "content": f"\n\n{field_def['label']}",
            "conversation_id": self.conversation_id,
        }

        control: dict[str, Any] = {
            "type": "control",
            "control_type": field_def["type"],
            "control_id": f"setup_{field_def['field']}",
            "field": field_def["field"],
            "label": field_def.get("label", field_def["field"]),
            "required": False,
            "skippable": True,
            "conversation_id": self.conversation_id,
        }

        if "options" in field_def:
            control["options"] = field_def["options"]
        if "placeholder" in field_def:
            control["placeholder"] = field_def["placeholder"]
        if field_def.get("multi_select"):
            control["multi_select"] = True
        if field_def.get("allow_custom"):
            control["allow_custom"] = True

        # Read existing value as default for re-runs
        existing = self._read_optional_field_value(field_def["field"])
        if existing:
            control["default_value"] = existing

        yield control
        yield {"type": "done", "conversation_id": self.conversation_id}

    def _store_optional_value(self, field_def: dict[str, Any], value: str) -> None:
        """Store an optional field value to the appropriate location."""
        field = field_def["field"]
        yaml_path = field_def.get("yaml_path")

        # Channel tokens go to vault
        if field == "channel_token":
            self._store_channel_token(value)
            return
        if field == "slack_app_token":
            self._store_slack_app_token(value)
            return

        if not yaml_path:
            return

        # Multi-select: parse JSON array
        if field_def.get("multi_select"):
            parsed = self._parse_multi_select(value)
            if parsed:
                self._store_user_yaml_value_any(*yaml_path, parsed)
                return

        # Brevity preference mapping
        if field == "brevity_preference":
            mapped = {"brief": True, "balanced": "balanced", "detailed": False}.get(value, value)
            self._store_user_yaml_value_any(*yaml_path, mapped)
            return

        self._store_user_yaml_value(*yaml_path, value)

    def _store_channel_token(self, token: str) -> None:
        """Store a channel bot token in vault based on primary_channel."""
        primary = self._read_optional_field_value("primary_channel")
        if not primary or primary == "web":
            return
        try:
            from tools.security import vault
            env_key_map = {
                "telegram": "TELEGRAM_BOT_TOKEN",
                "discord": "DISCORD_BOT_TOKEN",
                "slack": "SLACK_BOT_TOKEN",
            }
            env_key = env_key_map.get(primary)
            if env_key:
                vault.set_secret(env_key, token, namespace="default")
                os.environ[env_key] = token
        except Exception as e:
            logger.warning(f"Could not store channel token: {e}")

    def _store_slack_app_token(self, token: str) -> None:
        """Store a Slack app-level token in vault."""
        try:
            from tools.security import vault
            vault.set_secret("SLACK_APP_TOKEN", token, namespace="default")
            os.environ["SLACK_APP_TOKEN"] = token
        except Exception as e:
            logger.warning(f"Could not store Slack app token: {e}")

    def _start_optional_rerun(self, scope: str = "all") -> None:
        """Reset optional phase for a re-run, optionally scoped."""
        update: dict[str, Any] = {
            "optional_index": 0,
            "optional_completed": False,
            "optional_scope": scope,
        }
        if scope == "all":
            update["skipped_fields"] = []
        else:
            # Only clear skipped fields for this scope
            state = self._get_onboarding_state()
            current_skipped = state.get("skipped_fields", [])
            scope_fields = {f["field"] for f in OPTIONAL_FIELDS if f.get("group") == scope}
            update["skipped_fields"] = [s for s in current_skipped if s not in scope_fields]

        self._update_onboarding_state(**update)

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

        # Signal the frontend to reload (clear chat, re-fetch welcome bundle)
        # instead of continuing the setup flow inline.
        yield {"type": "done", "conversation_id": self.conversation_id, "action": "reload"}

    def _store_user_yaml_value(self, *keys_and_value: str) -> None:
        """Write a string value into args/user.yaml. Last argument is the value, rest are keys."""
        path_keys = keys_and_value[:-1]
        value: Any = keys_and_value[-1]
        self._store_user_yaml_value_any(*path_keys, value)

    def _store_user_yaml_value_any(self, *keys_and_value: Any) -> None:
        """Write any value into args/user.yaml. Last argument is the value, rest are keys."""
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
