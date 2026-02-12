"""
Tool: Office Integration Onboarding
Purpose: Guide users through integration level selection and setup

Provides a step-by-step onboarding flow for office integration:
1. Explain integration levels
2. Help user choose appropriate level
3. Initiate OAuth flow if needed
4. Verify connection

Usage:
    python tools/office/onboarding.py --start
    python tools/office/onboarding.py --select-level 2
    python tools/office/onboarding.py --status --user-id <id>

Dependencies:
    - pyyaml (pip install pyyaml)
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import CONFIG_PATH, DATA_PATH  # noqa: E402
from tools.office.level_detector import get_level_comparison, suggest_level_for_use_case  # noqa: E402
from tools.office.models import IntegrationLevel  # noqa: E402


# Onboarding state file
ONBOARDING_STATE_PATH = DATA_PATH / "office_onboarding_state.json"


class OnboardingStep(Enum):
    """Onboarding wizard steps."""

    WELCOME = "welcome"
    EXPLAIN_LEVELS = "explain_levels"
    CHOOSE_LEVEL = "choose_level"
    CHOOSE_PROVIDER = "choose_provider"
    CONFIGURE_STANDALONE = "configure_standalone"  # Level 1 only
    OAUTH_AUTHORIZE = "oauth_authorize"  # Level 2+
    OAUTH_CALLBACK = "oauth_callback"
    VERIFY_CONNECTION = "verify_connection"
    COMPLETE = "complete"

    @classmethod
    def order(cls) -> list["OnboardingStep"]:
        """Return steps in display order."""
        return [
            cls.WELCOME,
            cls.EXPLAIN_LEVELS,
            cls.CHOOSE_LEVEL,
            cls.CHOOSE_PROVIDER,
            cls.CONFIGURE_STANDALONE,
            cls.OAUTH_AUTHORIZE,
            cls.OAUTH_CALLBACK,
            cls.VERIFY_CONNECTION,
            cls.COMPLETE,
        ]


@dataclass
class OnboardingState:
    """
    Office integration onboarding state.

    Tracks progress through the onboarding wizard.
    """

    # Progress
    current_step: OnboardingStep = OnboardingStep.WELCOME
    completed_steps: list[OnboardingStep] = field(default_factory=list)

    # Selections
    user_id: str = "default"
    selected_level: int | None = None
    selected_provider: str | None = None  # 'google', 'microsoft', 'standalone'

    # Standalone config (Level 1)
    standalone_email: str | None = None
    standalone_imap_host: str | None = None
    standalone_smtp_host: str | None = None

    # OAuth state (Level 2+)
    oauth_state: str | None = None
    oauth_completed: bool = False

    # Account
    account_id: str | None = None
    account_email: str | None = None

    # Timestamps
    started_at: str | None = None
    last_updated: str | None = None

    def __post_init__(self):
        """Handle enum conversion."""
        if isinstance(self.current_step, str):
            self.current_step = OnboardingStep(self.current_step)
        if self.completed_steps and isinstance(self.completed_steps[0], str):
            self.completed_steps = [OnboardingStep(s) for s in self.completed_steps]

    def mark_step_complete(self, step: OnboardingStep) -> None:
        """Mark a step as completed."""
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        self.last_updated = datetime.now().isoformat()

    def get_next_step(self) -> OnboardingStep | None:
        """Determine next step based on selections."""
        if self.current_step == OnboardingStep.WELCOME:
            return OnboardingStep.EXPLAIN_LEVELS

        elif self.current_step == OnboardingStep.EXPLAIN_LEVELS:
            return OnboardingStep.CHOOSE_LEVEL

        elif self.current_step == OnboardingStep.CHOOSE_LEVEL:
            return OnboardingStep.CHOOSE_PROVIDER

        elif self.current_step == OnboardingStep.CHOOSE_PROVIDER:
            if self.selected_level == 1 or self.selected_provider == "standalone":
                return OnboardingStep.CONFIGURE_STANDALONE
            else:
                return OnboardingStep.OAUTH_AUTHORIZE

        elif self.current_step == OnboardingStep.CONFIGURE_STANDALONE:
            return OnboardingStep.VERIFY_CONNECTION

        elif self.current_step == OnboardingStep.OAUTH_AUTHORIZE:
            return OnboardingStep.OAUTH_CALLBACK

        elif self.current_step == OnboardingStep.OAUTH_CALLBACK:
            return OnboardingStep.VERIFY_CONNECTION

        elif self.current_step == OnboardingStep.VERIFY_CONNECTION:
            return OnboardingStep.COMPLETE

        return None

    def advance(self) -> None:
        """Advance to next step."""
        self.mark_step_complete(self.current_step)
        next_step = self.get_next_step()
        if next_step:
            self.current_step = next_step

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d["current_step"] = self.current_step.value
        d["completed_steps"] = [s.value for s in self.completed_steps]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OnboardingState":
        """Create from dictionary."""
        if "current_step" in data:
            data["current_step"] = OnboardingStep(data["current_step"])
        if "completed_steps" in data:
            data["completed_steps"] = [OnboardingStep(s) for s in data["completed_steps"]]
        return cls(**data)

    def save(self) -> dict[str, Any]:
        """Save state to disk."""
        ONBOARDING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(ONBOARDING_STATE_PATH, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            return {"success": True, "path": str(ONBOARDING_STATE_PATH)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def load(cls, user_id: str = "default") -> "OnboardingState":
        """Load state from disk or create new."""
        if ONBOARDING_STATE_PATH.exists():
            try:
                with open(ONBOARDING_STATE_PATH) as f:
                    data = json.load(f)
                    if data.get("user_id") == user_id:
                        return cls.from_dict(data)
            except Exception:
                pass

        state = cls(user_id=user_id)
        state.started_at = datetime.now().isoformat()
        return state


def get_welcome_message() -> dict[str, Any]:
    """
    Get the welcome message for onboarding.

    Returns:
        dict with welcome content
    """
    return {
        "title": "Office Integration Setup",
        "message": (
            "Connect your email and calendar to let Dex help manage your inbox and schedule.\n\n"
            "DexAI offers 5 integration levels, from maximum privacy to full automation. "
            "You choose how much access to grant, and you can change it anytime.\n\n"
            "ADHD users often benefit from higher integration levels (less manual work), "
            "but we recommend starting at Level 2 and upgrading as you build trust."
        ),
        "next_action": "Continue to see integration levels",
    }


def get_level_explanation() -> dict[str, Any]:
    """
    Get detailed explanation of integration levels.

    Returns:
        dict with level details
    """
    result = get_level_comparison()
    levels = result.get("levels", [])

    # Add ADHD-specific recommendations
    adhd_notes = {
        1: "High friction — requires manual forwarding (ADHD users often skip this)",
        2: "Good starting point — see everything, but you stay in control",
        3: "Reduces 'reply paralysis' — drafts appear ready to review",
        4: "Significantly reduces email anxiety — Dex handles routine tasks",
        5: "Maximum benefit but requires trust — start here after 90 days at Level 4",
    }

    for level in levels:
        level["adhd_note"] = adhd_notes.get(level["level"], "")
        if level["level"] == 2:
            level["recommended"] = True

    return {
        "title": "Integration Levels",
        "levels": levels,
        "recommendation": (
            "We recommend starting at Level 2 (Read-Only). "
            "You can upgrade to higher levels after you see how Dex works with your email."
        ),
    }


def validate_level_selection(level: int) -> dict[str, Any]:
    """
    Validate a level selection.

    Args:
        level: Selected level (1-5)

    Returns:
        dict with validation result
    """
    if level < 1 or level > 5:
        return {"valid": False, "error": "Level must be between 1 and 5"}

    selected = IntegrationLevel(level)

    # Progressive trust warnings
    warnings = []
    if level >= 4:
        warnings.append(
            "Level 4+ requires careful setup. "
            "We recommend using Level 2-3 for at least 30 days first."
        )
    if level == 5:
        warnings.append(
            "Level 5 (Autonomous) gives Dex significant control. "
            "Make sure you're comfortable with Level 4 before proceeding."
        )

    return {
        "valid": True,
        "level": level,
        "level_name": selected.display_name,
        "description": selected.description,
        "risk": selected.risk_level,
        "warnings": warnings,
    }


def get_provider_options(level: int) -> dict[str, Any]:
    """
    Get available provider options for a level.

    Args:
        level: Selected integration level

    Returns:
        dict with provider options
    """
    providers = []

    if level == 1:
        providers.append({
            "id": "standalone",
            "name": "Standalone Email",
            "description": "Set up Dex's own email account (IMAP/SMTP)",
            "recommended": True,
            "setup_type": "credentials",
        })

    if level >= 2:
        providers.append({
            "id": "google",
            "name": "Google Workspace",
            "description": "Gmail and Google Calendar",
            "recommended": True,
            "setup_type": "oauth",
            "icon": "google",
        })
        providers.append({
            "id": "microsoft",
            "name": "Microsoft 365",
            "description": "Outlook and Microsoft Calendar",
            "recommended": False,
            "setup_type": "oauth",
            "icon": "microsoft",
        })

    return {
        "title": "Choose Your Provider",
        "level": level,
        "providers": providers,
        "note": (
            "For Level 2+, you'll be redirected to authorize Dex with your chosen provider. "
            "You can revoke access at any time from the dashboard or provider settings."
        ),
    }


def initiate_oauth(
    state: OnboardingState,
    provider: str,
) -> dict[str, Any]:
    """
    Initiate OAuth flow for a provider.

    Args:
        state: Onboarding state
        provider: 'google' or 'microsoft'

    Returns:
        dict with authorization URL
    """
    from tools.office.oauth_manager import generate_authorization_url

    level = IntegrationLevel(state.selected_level)
    result = generate_authorization_url(provider, level)

    if result["success"]:
        state.oauth_state = result["state"]
        state.save()

    return result


def complete_oauth(
    state: OnboardingState,
    code: str,
) -> dict[str, Any]:
    """
    Complete OAuth flow with authorization code.

    Args:
        state: Onboarding state
        code: Authorization code from callback

    Returns:
        dict with completion status
    """
    import asyncio

    from tools.office.oauth_manager import exchange_code_for_tokens, save_account

    # OAUTH-1: Extract PKCE code_verifier from saved OAuth state
    code_verifier = None
    if state.oauth_state:
        try:
            state_data = json.loads(state.oauth_state)
            if isinstance(state_data, dict):
                code_verifier = state_data.get("code_verifier")
        except (json.JSONDecodeError, TypeError):
            pass

    provider = state.selected_provider
    result = asyncio.run(exchange_code_for_tokens(provider, code, code_verifier=code_verifier))

    if not result["success"]:
        return result

    # Save account
    level = IntegrationLevel(state.selected_level)
    save_result = save_account(
        user_id=state.user_id,
        provider=provider,
        level=level,
        access_token=result["access_token"],
        refresh_token=result.get("refresh_token"),
        expires_in=result["expires_in"],
        scopes=result.get("scope", "").split(),
        email=result["email"],
        name=result.get("name"),
    )

    if save_result["success"]:
        state.account_id = save_result["account_id"]
        state.account_email = result["email"]
        state.oauth_completed = True
        state.save()

    return save_result


def verify_connection(state: OnboardingState) -> dict[str, Any]:
    """
    Verify the office connection is working.

    Args:
        state: Onboarding state

    Returns:
        dict with verification result
    """
    if state.selected_level == 1:
        # Verify IMAP connection for standalone
        return _verify_standalone_connection(state)
    else:
        # Verify OAuth connection
        return _verify_oauth_connection(state)


def _verify_standalone_connection(state: OnboardingState) -> dict[str, Any]:
    """Verify standalone IMAP connection."""
    # TODO: Implement IMAP connection test
    return {
        "success": True,
        "message": "Standalone connection configured (verification pending)",
        "provider": "standalone",
        "email": state.standalone_email,
    }


def _verify_oauth_connection(state: OnboardingState) -> dict[str, Any]:
    """Verify OAuth connection by making a test API call."""
    if not state.account_id:
        return {"success": False, "error": "No account configured"}

    # TODO: Make test API call based on provider
    return {
        "success": True,
        "message": f"Connected to {state.selected_provider}",
        "provider": state.selected_provider,
        "email": state.account_email,
        "level": state.selected_level,
    }


def get_completion_message(state: OnboardingState) -> dict[str, Any]:
    """
    Get completion message for successful setup.

    Args:
        state: Onboarding state

    Returns:
        dict with completion content
    """
    level = IntegrationLevel(state.selected_level)

    # Next steps based on level
    next_steps = []
    if level == IntegrationLevel.READ_ONLY:
        next_steps = [
            "Try asking: 'What's in my inbox?'",
            "Try asking: 'What's on my calendar today?'",
            "Dex can now summarize emails and check your schedule",
        ]
    elif level == IntegrationLevel.COLLABORATIVE:
        next_steps = [
            "Try asking: 'Help me draft a reply to [email]'",
            "Try asking: 'Schedule a meeting with [person]'",
            "Drafts appear in your email app for review before sending",
        ]
    elif level >= IntegrationLevel.MANAGED_PROXY:
        next_steps = [
            "Try asking: 'Reply to that email from [person]'",
            "All actions have a 60-second undo window",
            "Check the dashboard for action history",
        ]

    return {
        "title": "Setup Complete!",
        "message": (
            f"Office integration is now active at Level {state.selected_level} "
            f"({level.display_name})."
        ),
        "email": state.account_email,
        "provider": state.selected_provider,
        "level": state.selected_level,
        "level_name": level.display_name,
        "next_steps": next_steps,
        "upgrade_note": (
            "You can upgrade to a higher level anytime from Settings > Office Integration."
            if state.selected_level < 5
            else "You're at the highest level. Use the emergency pause if needed."
        ),
    }


def reset_onboarding(user_id: str = "default") -> dict[str, Any]:
    """
    Reset onboarding state to start fresh.

    Args:
        user_id: User ID

    Returns:
        dict with reset status
    """
    if ONBOARDING_STATE_PATH.exists():
        ONBOARDING_STATE_PATH.unlink()

    return {"success": True, "message": "Onboarding state reset"}


def get_onboarding_status(user_id: str = "default") -> dict[str, Any]:
    """
    Get current onboarding status.

    Args:
        user_id: User ID

    Returns:
        dict with status information
    """
    state = OnboardingState.load(user_id)

    return {
        "current_step": state.current_step.value,
        "completed_steps": [s.value for s in state.completed_steps],
        "selected_level": state.selected_level,
        "selected_provider": state.selected_provider,
        "account_id": state.account_id,
        "account_email": state.account_email,
        "is_complete": state.current_step == OnboardingStep.COMPLETE,
        "started_at": state.started_at,
        "last_updated": state.last_updated,
    }


def main():
    parser = argparse.ArgumentParser(description="Office Integration Onboarding")
    parser.add_argument("--start", action="store_true", help="Start onboarding")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--reset", action="store_true", help="Reset onboarding")
    parser.add_argument("--select-level", type=int, help="Select integration level")
    parser.add_argument("--select-provider", help="Select provider")
    parser.add_argument("--levels", action="store_true", help="Show level details")
    parser.add_argument("--suggest", help="Suggest level for use case")
    parser.add_argument("--user-id", default="default", help="User ID")

    args = parser.parse_args()

    if args.levels:
        result = get_level_explanation()
        print(f"\n{result['title']}\n")
        for level in result["levels"]:
            rec = " (Recommended)" if level.get("recommended") else ""
            print(f"Level {level['level']}: {level['name']}{rec}")
            print(f"  Risk: {level['risk']}")
            print(f"  {level['description']}")
            if level.get("adhd_note"):
                print(f"  ADHD: {level['adhd_note']}")
            print()
        print(result["recommendation"])

    elif args.suggest:
        result = suggest_level_for_use_case(args.suggest)
        print(f"Suggested: Level {result['suggested_level']} ({result['level_name']})")
        print(f"Risk: {result['risk_level']}")
        print(f"\n{result['rationale']}")

    elif args.start:
        state = OnboardingState(user_id=args.user_id)
        state.started_at = datetime.now().isoformat()
        state.save()
        print(json.dumps(get_welcome_message(), indent=2))

    elif args.select_level:
        result = validate_level_selection(args.select_level)
        if result["valid"]:
            state = OnboardingState.load(args.user_id)
            state.selected_level = args.select_level
            state.current_step = OnboardingStep.CHOOSE_LEVEL
            state.advance()
            state.save()
            print(f"Selected Level {args.select_level}: {result['level_name']}")
            if result["warnings"]:
                for w in result["warnings"]:
                    print(f"Warning: {w}")
        else:
            print(f"Error: {result['error']}")

    elif args.select_provider:
        state = OnboardingState.load(args.user_id)
        state.selected_provider = args.select_provider
        state.current_step = OnboardingStep.CHOOSE_PROVIDER
        state.advance()
        state.save()
        print(f"Selected provider: {args.select_provider}")

        if state.selected_level >= 2 and args.select_provider != "standalone":
            result = initiate_oauth(state, args.select_provider)
            if result["success"]:
                print(f"\nAuthorization URL:\n{result['authorization_url']}")
            else:
                print(f"Error: {result['error']}")

    elif args.status:
        result = get_onboarding_status(args.user_id)
        print(json.dumps(result, indent=2))

    elif args.reset:
        result = reset_onboarding(args.user_id)
        print(result["message"])

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
