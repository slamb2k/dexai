"""
Setup Flow Service — Deterministic Pre-LLM Bootstrap

Handles the initial onboarding phase before an API key is available.
Uses the same streaming protocol (chunk/control/done) as LLM-driven chat,
making the transition invisible to the user.

Flow:
    GREETING → API_KEY → API_KEY_VALIDATED → HANDOFF_TO_LLM

After the API key is validated, the deterministic phase ends and subsequent
messages are routed to the normal LLM pipeline.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
DATA_PATH = PROJECT_ROOT / "data"
SETUP_FLOW_STATE_PATH = DATA_PATH / "setup_flow_state.json"


class SetupFlowState:
    """Tracks the deterministic setup flow phase."""

    def __init__(self):
        self.phase: str = "greeting"  # greeting | api_key | complete
        self.api_key_validated: bool = False
        self.started_at: str = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "api_key_validated": self.api_key_validated,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SetupFlowState":
        state = cls()
        state.phase = data.get("phase", "greeting")
        state.api_key_validated = data.get("api_key_validated", False)
        state.started_at = data.get("started_at", datetime.now().isoformat())
        return state

    def save(self) -> None:
        DATA_PATH.mkdir(parents=True, exist_ok=True)
        with open(SETUP_FLOW_STATE_PATH, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls) -> "SetupFlowState":
        if SETUP_FLOW_STATE_PATH.exists():
            try:
                with open(SETUP_FLOW_STATE_PATH) as f:
                    return cls.from_dict(json.load(f))
            except Exception:
                pass
        return cls()


def _has_api_key() -> bool:
    """Check if an Anthropic API key is already configured."""
    # Check environment
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True

    # Check vault
    try:
        from tools.security import vault
        secret = vault.get_secret("ANTHROPIC_API_KEY", namespace="default")
        if secret:
            return True
    except Exception:
        pass

    return False


class SetupFlowService:
    """
    Deterministic pre-LLM setup flow.

    Emits the same streaming protocol as LLM chat (chunk, control, done),
    making the experience seamless from the user's perspective.
    """

    def __init__(self, conversation_id: str | None = None):
        self.conversation_id = conversation_id
        self._state = SetupFlowState.load()

    def is_active(self) -> bool:
        """Check if the deterministic setup flow should handle this message."""
        # If API key already available, deterministic flow is done
        if _has_api_key():
            self._state.phase = "complete"
            self._state.api_key_validated = True
            self._state.save()
            return False

        # Active if we haven't completed the deterministic phase
        return self._state.phase != "complete"

    def is_greeting_needed(self) -> bool:
        """Check if this is the first interaction (needs greeting)."""
        return self._state.phase == "greeting"

    async def handle_greeting(self) -> AsyncIterator[dict]:
        """Yield the initial greeting + API key prompt."""
        # Welcome message
        yield {
            "type": "chunk",
            "content": (
                "Hey! I'm Dex, your ADHD-friendly AI assistant. "
                "Before we can chat properly, I need one thing — your Anthropic API key.\n\n"
                "You can get one from [console.anthropic.com](https://console.anthropic.com/settings/keys). "
                "Paste it below and I'll verify it works."
            ),
            "conversation_id": self.conversation_id,
        }

        # API key control
        yield {
            "type": "control",
            "control_type": "secure_input",
            "control_id": "setup_api_key",
            "field": "anthropic_api_key",
            "label": "Anthropic API Key",
            "placeholder": "sk-ant-...",
            "required": True,
            "conversation_id": self.conversation_id,
        }

        yield {
            "type": "done",
            "conversation_id": self.conversation_id,
        }

        # Advance state
        self._state.phase = "api_key"
        self._state.save()

    async def handle_control_response(
        self, control_response: dict[str, Any]
    ) -> AsyncIterator[dict]:
        """Handle a control response during deterministic setup."""
        field = control_response.get("field", "")
        value = control_response.get("value", "")

        if field == "anthropic_api_key":
            async for chunk in self._handle_api_key(value):
                yield chunk
        else:
            yield {
                "type": "chunk",
                "content": "I didn't recognise that response. Let me try again.",
                "conversation_id": self.conversation_id,
            }
            yield {
                "type": "done",
                "conversation_id": self.conversation_id,
            }

    async def handle_message(
        self,
        message: str,
        control_response: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict]:
        """
        Main entry point — handles any message during setup flow.

        Routes to greeting, control response, or re-prompt as appropriate.
        """
        # If there's a control response, handle it
        if control_response:
            async for chunk in self.handle_control_response(control_response):
                yield chunk
            return

        # If this is the first interaction, show greeting
        if self.is_greeting_needed():
            async for chunk in self.handle_greeting():
                yield chunk
            return

        # User typed a free-text message during setup.
        # They might have pasted an API key directly.
        stripped = message.strip()
        if stripped.startswith("sk-ant-") or stripped.startswith("sk-"):
            async for chunk in self._handle_api_key(stripped):
                yield chunk
            return

        # Otherwise, re-prompt for the API key
        yield {
            "type": "chunk",
            "content": (
                "I still need your API key before we can get started. "
                "Paste it below — it starts with `sk-ant-`."
            ),
            "conversation_id": self.conversation_id,
        }
        yield {
            "type": "control",
            "control_type": "secure_input",
            "control_id": "setup_api_key",
            "field": "anthropic_api_key",
            "label": "Anthropic API Key",
            "placeholder": "sk-ant-...",
            "required": True,
            "conversation_id": self.conversation_id,
        }
        yield {
            "type": "done",
            "conversation_id": self.conversation_id,
        }

    async def _handle_api_key(self, api_key: str) -> AsyncIterator[dict]:
        """Validate and store an API key."""
        if not api_key:
            yield {
                "type": "chunk",
                "content": "No API key provided. Please paste your key below.",
                "conversation_id": self.conversation_id,
            }
            yield {
                "type": "control",
                "control_type": "secure_input",
                "control_id": "setup_api_key",
                "field": "anthropic_api_key",
                "label": "Anthropic API Key",
                "placeholder": "sk-ant-...",
                "required": True,
                "conversation_id": self.conversation_id,
            }
            yield {"type": "done", "conversation_id": self.conversation_id}
            return

        # Show validation in progress
        yield {
            "type": "chunk",
            "content": "Checking your API key...",
            "conversation_id": self.conversation_id,
        }

        # Validate the key
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
            yield {
                "type": "control",
                "control_type": "secure_input",
                "control_id": "setup_api_key",
                "field": "anthropic_api_key",
                "label": "Anthropic API Key",
                "placeholder": "sk-ant-...",
                "required": True,
                "conversation_id": self.conversation_id,
            }
            yield {"type": "done", "conversation_id": self.conversation_id}
            return

        # Store the key
        stored = self._store_api_key(api_key)
        if not stored:
            yield {
                "type": "chunk",
                "content": "\n\nKey is valid but I couldn't store it. Please set `ANTHROPIC_API_KEY` in your `.env` file and restart.",
                "conversation_id": self.conversation_id,
            }
            yield {"type": "done", "conversation_id": self.conversation_id}
            return

        # Success — mark deterministic phase complete
        self._state.phase = "complete"
        self._state.api_key_validated = True
        self._state.save()

        yield {
            "type": "chunk",
            "content": (
                "\n\nAPI key verified and stored! "
                "I'm ready to chat now. Let me get to know you a bit so I can "
                "personalise the experience — send me any message to continue."
            ),
            "conversation_id": self.conversation_id,
        }
        yield {"type": "done", "conversation_id": self.conversation_id}

    def _store_api_key(self, api_key: str) -> bool:
        """Store the API key in vault and environment."""
        # Set in current process environment so it's immediately available
        os.environ["ANTHROPIC_API_KEY"] = api_key

        # Persist to vault
        try:
            from tools.security import vault
            vault.set_secret("ANTHROPIC_API_KEY", api_key, namespace="default")
        except Exception as e:
            logger.warning(f"Could not store API key in vault: {e}")

        # Also write to .env if it exists
        try:
            env_path = PROJECT_ROOT / ".env"
            if env_path.exists():
                content = env_path.read_text()
                if "ANTHROPIC_API_KEY=" in content:
                    # Replace existing line
                    lines = content.splitlines()
                    new_lines = []
                    for line in lines:
                        if line.startswith("ANTHROPIC_API_KEY="):
                            new_lines.append(f"ANTHROPIC_API_KEY={api_key}")
                        else:
                            new_lines.append(line)
                    env_path.write_text("\n".join(new_lines) + "\n")
                else:
                    # Append
                    with open(env_path, "a") as f:
                        f.write(f"\nANTHROPIC_API_KEY={api_key}\n")
            else:
                env_path.write_text(f"ANTHROPIC_API_KEY={api_key}\n")
        except Exception as e:
            logger.warning(f"Could not write API key to .env: {e}")

        return True
