#!/usr/bin/env python3
"""
TUI Setup Wizard - Main Application

Launches the terminal-based setup wizard using Textual.

Usage:
    python -m tools.setup.tui.main
    python -m tools.setup.tui.main --resume
    python -m tools.setup.tui.main --reset

Dependencies:
    pip install textual
"""

import argparse
import sys
from pathlib import Path


# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from textual import events
    from textual.app import App, ComposeResult
    from textual.containers import Center, Container, Horizontal, Vertical
    from textual.screen import Screen
    from textual.widgets import Button, Footer, Header, Input, Label, RadioButton, RadioSet, Static

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

from tools.setup.wizard import (
    SetupState,
    SetupStep,
    apply_configuration,
    detect_timezone,
    is_setup_complete,
    reset_setup,
    validate_channel,
)


# =============================================================================
# ASCII Art Banner
# =============================================================================

DEXAI_BANNER = """
██████╗ ███████╗██╗  ██╗ █████╗ ██╗
██╔══██╗██╔════╝╚██╗██╔╝██╔══██╗██║
██║  ██║█████╗   ╚███╔╝ ███████║██║
██║  ██║██╔══╝   ██╔██╗ ██╔══██╗██║
██████╔╝███████╗██╔╝ ██╗██║  ██║██║
╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝
"""

# =============================================================================
# Screens
# =============================================================================

if TEXTUAL_AVAILABLE:

    class WelcomeScreen(Screen):
        """Welcome screen - first impression."""

        CSS = """
        WelcomeScreen {
            align: center middle;
        }

        #banner {
            text-align: center;
            color: $accent;
            margin-bottom: 1;
        }

        #welcome-text {
            text-align: center;
            margin: 1 0;
        }

        #button-row {
            align: center middle;
            margin-top: 2;
        }

        Button {
            margin: 0 1;
        }
        """

        def compose(self) -> ComposeResult:
            yield Header()
            with Container():
                yield Static(DEXAI_BANNER, id="banner")
                yield Static(
                    "\nWelcome! I'm Dex, your AI assistant.\n"
                    "Let's get you set up in just a few minutes.\n\n"
                    "What you'll need:\n"
                    "• A messaging app (Telegram, Discord, or Slack)\n"
                    "• About 3-5 minutes\n",
                    id="welcome-text",
                )
                with Horizontal(id="button-row"):
                    yield Button("Get Started", variant="primary", id="start")
                    yield Button("Skip Setup", variant="default", id="skip")
            yield Footer()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "start":
                self.app.state.mark_step_complete(SetupStep.WELCOME)
                self.app.state.save()
                self.app.push_screen(ChannelScreen())
            elif event.button.id == "skip":
                self.app.exit(message="Setup skipped. Run 'dexai setup' to continue later.")

    class ChannelScreen(Screen):
        """Channel selection screen."""

        CSS = """
        ChannelScreen {
            align: center middle;
        }

        #title {
            text-align: center;
            text-style: bold;
            margin-bottom: 1;
        }

        #subtitle {
            text-align: center;
            color: $text-muted;
            margin-bottom: 2;
        }

        RadioSet {
            margin: 1 0;
            padding: 1;
            background: $surface;
            border: solid $primary;
        }

        #channel-info {
            margin-top: 1;
            padding: 1;
            background: $surface;
            min-height: 5;
        }

        #button-row {
            align: center middle;
            margin-top: 2;
        }
        """

        selected_channel = None

        def compose(self) -> ComposeResult:
            yield Header()
            with Container():
                yield Static("Where would you like to chat with Dex?", id="title")
                yield Static("Pick one to start — you can add more later.", id="subtitle")

                with RadioSet(id="channel-select"):
                    yield RadioButton("Telegram (Recommended)", id="telegram", value=True)
                    yield RadioButton("Discord", id="discord")
                    yield RadioButton("Slack", id="slack")
                    yield RadioButton("I'll configure later", id="skip")

                yield Static("", id="channel-info")

                with Horizontal(id="button-row"):
                    yield Button("← Back", variant="default", id="back")
                    yield Button("Continue →", variant="primary", id="continue")
            yield Footer()

        def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
            """Update info when selection changes."""
            info_widget = self.query_one("#channel-info", Static)

            if event.pressed.id == "telegram":
                self.selected_channel = "telegram"
                info_widget.update(
                    "Telegram works great and requires minimal setup.\n"
                    "You'll create a bot through @BotFather in the Telegram app."
                )
            elif event.pressed.id == "discord":
                self.selected_channel = "discord"
                info_widget.update(
                    "Good for gaming and community focus.\n"
                    "You'll create an application in the Discord Developer Portal."
                )
            elif event.pressed.id == "slack":
                self.selected_channel = "slack"
                info_widget.update(
                    "Best for work integration.\nYou'll create an app in the Slack App Directory."
                )
            else:
                self.selected_channel = None
                info_widget.update(
                    "You can configure channels later in Settings.\n"
                    "Some features won't work without a messaging channel."
                )

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "back":
                self.app.pop_screen()
            elif event.button.id == "continue":
                self.app.state.primary_channel = self.selected_channel

                if self.selected_channel:
                    # Go to channel-specific token entry
                    self.app.push_screen(ChannelTokenScreen(self.selected_channel))
                else:
                    # Skip channel setup
                    self.app.state.mark_step_complete(SetupStep.CHANNEL)
                    self.app.state.save()
                    self.app.push_screen(PreferencesScreen())

    class ChannelTokenScreen(Screen):
        """Token entry for selected channel."""

        CSS = """
        ChannelTokenScreen {
            align: center middle;
        }

        #title {
            text-align: center;
            text-style: bold;
            margin-bottom: 1;
        }

        #instructions {
            margin: 1 0;
            padding: 1;
            background: $surface;
        }

        Input {
            margin: 1 0;
        }

        #status {
            margin: 1 0;
            min-height: 2;
        }

        .success {
            color: $success;
        }

        .error {
            color: $error;
        }

        #button-row {
            align: center middle;
            margin-top: 1;
        }
        """

        def __init__(self, channel: str):
            super().__init__()
            self.channel = channel
            self.token_valid = False

        def compose(self) -> ComposeResult:
            yield Header()
            with Container():
                if self.channel == "telegram":
                    yield Static("Set up Telegram", id="title")
                    yield Static(
                        "1. Open Telegram and search for @BotFather\n"
                        "2. Send /newbot and follow the prompts\n"
                        "3. Copy the token BotFather gives you\n"
                        "4. Paste it below:",
                        id="instructions",
                    )
                    yield Input(
                        placeholder="Paste your Telegram bot token here", id="token", password=True
                    )

                elif self.channel == "discord":
                    yield Static("Set up Discord", id="title")
                    yield Static(
                        "1. Go to discord.com/developers/applications\n"
                        "2. Click 'New Application' and name it\n"
                        "3. Go to Bot → Add Bot → Copy Token\n"
                        "4. Paste it below:",
                        id="instructions",
                    )
                    yield Input(
                        placeholder="Paste your Discord bot token here", id="token", password=True
                    )

                elif self.channel == "slack":
                    yield Static("Set up Slack", id="title")
                    yield Static(
                        "1. Go to api.slack.com/apps and create a new app\n"
                        "2. Go to OAuth & Permissions and install to workspace\n"
                        "3. Copy the Bot User OAuth Token (xoxb-...)\n"
                        "4. Go to Basic Information and get App-Level Token (xapp-...)",
                        id="instructions",
                    )
                    yield Input(placeholder="Bot Token (xoxb-...)", id="bot_token", password=True)
                    yield Input(placeholder="App Token (xapp-...)", id="app_token", password=True)

                yield Static("", id="status")

                with Horizontal(id="button-row"):
                    yield Button("← Back", variant="default", id="back")
                    yield Button("Test Connection", variant="warning", id="test")
                    yield Button("Continue →", variant="primary", id="continue", disabled=True)
            yield Footer()

        async def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "back":
                self.app.pop_screen()

            elif event.button.id == "test":
                status = self.query_one("#status", Static)
                status.update("Testing connection...")

                # Get tokens
                if self.channel == "slack":
                    config = {
                        "bot_token": self.query_one("#bot_token", Input).value,
                        "app_token": self.query_one("#app_token", Input).value,
                    }
                else:
                    config = {"token": self.query_one("#token", Input).value}

                # Validate
                result = await validate_channel(self.channel, config)

                if result["success"]:
                    bot_name = result.get("bot_username") or result.get("bot_name", "Bot")
                    status.update(f"✓ Connected! Bot: @{bot_name}")
                    status.add_class("success")
                    status.remove_class("error")
                    self.token_valid = True
                    self.app.state.channel_config = config
                    self.app.state.channel_verified = True
                    self.query_one("#continue", Button).disabled = False
                else:
                    status.update(f"✗ {result.get('error', 'Connection failed')}")
                    status.add_class("error")
                    status.remove_class("success")
                    self.token_valid = False
                    self.query_one("#continue", Button).disabled = True

            elif event.button.id == "continue":
                if self.token_valid:
                    self.app.state.mark_step_complete(SetupStep.CHANNEL)
                    self.app.state.save()
                    self.app.push_screen(PreferencesScreen())

    class PreferencesScreen(Screen):
        """User preferences screen."""

        CSS = """
        PreferencesScreen {
            align: center middle;
        }

        #title {
            text-align: center;
            text-style: bold;
            margin-bottom: 2;
        }

        .field {
            margin: 1 0;
        }

        Label {
            margin-bottom: 0;
        }

        Input {
            margin-top: 0;
        }

        #button-row {
            align: center middle;
            margin-top: 2;
        }
        """

        def compose(self) -> ComposeResult:
            detected_tz = detect_timezone()

            yield Header()
            with Container():
                yield Static("A few quick preferences:", id="title")

                with Vertical(classes="field"):
                    yield Label("What's your name?")
                    yield Input(placeholder="Your name", id="name")

                with Vertical(classes="field"):
                    yield Label("What timezone are you in?")
                    yield Input(value=detected_tz, id="timezone")

                with Vertical(classes="field"):
                    yield Label("When should Dex be active? (Start hour, 0-23)")
                    yield Input(value="9", id="start_hour")

                with Vertical(classes="field"):
                    yield Label("End hour (0-23)")
                    yield Input(value="22", id="end_hour")

                yield Static("\n(Dex won't disturb you outside these hours)", id="hint")

                with Horizontal(id="button-row"):
                    yield Button("← Back", variant="default", id="back")
                    yield Button("Continue →", variant="primary", id="continue")
            yield Footer()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "back":
                self.app.pop_screen()
            elif event.button.id == "continue":
                # Save preferences
                name = self.query_one("#name", Input).value
                timezone = self.query_one("#timezone", Input).value
                start = self.query_one("#start_hour", Input).value
                end = self.query_one("#end_hour", Input).value

                self.app.state.user_name = name if name else None
                self.app.state.timezone = timezone or "UTC"
                self.app.state.active_hours_start = (
                    f"{int(start):02d}:00" if start.isdigit() else "09:00"
                )
                self.app.state.active_hours_end = f"{int(end):02d}:00" if end.isdigit() else "22:00"

                self.app.state.mark_step_complete(SetupStep.PREFERENCES)
                self.app.state.mark_step_complete(SetupStep.SECURITY)  # Skip security for now
                self.app.state.save()
                self.app.push_screen(ApiKeyScreen())

    class ApiKeyScreen(Screen):
        """API key entry screen."""

        CSS = """
        ApiKeyScreen {
            align: center middle;
        }

        #title {
            text-align: center;
            text-style: bold;
            margin-bottom: 1;
        }

        #instructions {
            margin: 1 0;
        }

        Input {
            margin: 1 0;
        }

        #status {
            margin: 1 0;
            min-height: 2;
        }

        .success {
            color: $success;
        }

        .error {
            color: $error;
        }

        #button-row {
            align: center middle;
            margin-top: 1;
        }
        """

        def compose(self) -> ComposeResult:
            yield Header()
            with Container():
                yield Static("Dex uses Claude AI to understand you.", id="title")
                yield Static(
                    "Do you have an Anthropic API key?\n\n"
                    "If not, get one at console.anthropic.com\n"
                    "(You can also skip this and add it later)",
                    id="instructions",
                )
                yield Input(
                    placeholder="Paste your API key (sk-ant-...)", id="api_key", password=True
                )
                yield Static("", id="status")

                with Horizontal(id="button-row"):
                    yield Button("← Back", variant="default", id="back")
                    yield Button("Skip", variant="default", id="skip")
                    yield Button("Verify & Continue →", variant="primary", id="continue")
            yield Footer()

        async def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "back":
                self.app.pop_screen()

            elif event.button.id == "skip":
                self.app.state.api_key_skipped = True
                self.app.state.mark_step_complete(SetupStep.API_KEY)
                self.app.state.mark_step_complete(SetupStep.TEST)  # Skip test too
                self.app.state.save()
                self.app.push_screen(CompleteScreen())

            elif event.button.id == "continue":
                api_key = self.query_one("#api_key", Input).value
                status = self.query_one("#status", Static)

                if not api_key:
                    status.update("Please enter an API key or click Skip")
                    return

                status.update("Verifying API key...")

                from tools.setup.wizard import validate_anthropic_key

                result = await validate_anthropic_key(api_key)

                if result["success"]:
                    status.update("✓ API key is valid!")
                    status.add_class("success")
                    status.remove_class("error")

                    self.app.state.api_key_set = True
                    self.app.state.api_key_verified = True
                    self.app.state.channel_config["anthropic_api_key"] = api_key
                    self.app.state.mark_step_complete(SetupStep.API_KEY)
                    self.app.state.mark_step_complete(SetupStep.TEST)
                    self.app.state.save()

                    # Small delay so user sees the success message
                    import asyncio

                    await asyncio.sleep(1)
                    self.app.push_screen(CompleteScreen())
                else:
                    status.update(f"✗ {result.get('error', 'Verification failed')}")
                    status.add_class("error")
                    status.remove_class("success")

    class CompleteScreen(Screen):
        """Setup complete screen."""

        CSS = """
        CompleteScreen {
            align: center middle;
        }

        #banner {
            text-align: center;
            color: $success;
            margin-bottom: 1;
        }

        #message {
            text-align: center;
            margin: 1 0;
        }

        #tips {
            margin: 2 0;
            padding: 1;
            background: $surface;
        }

        #button-row {
            align: center middle;
            margin-top: 2;
        }
        """

        def compose(self) -> ComposeResult:
            yield Header()
            with Container():
                yield Static("🎉", id="banner")
                yield Static(
                    "You're all set!\n\nDex is configured and ready to help.", id="message"
                )

                yield Static(
                    "Quick tips to get started:\n\n"
                    "💬  Just chat naturally\n"
                    '    "Remind me to call mom tomorrow"\n\n'
                    "⚡  Dex learns your patterns\n"
                    "    The more you chat, the better Dex gets\n\n"
                    "🔕  Dex respects your focus\n"
                    "    Won't interrupt during hyperfocus periods",
                    id="tips",
                )

                with Horizontal(id="button-row"):
                    yield Button("Finish Setup", variant="primary", id="finish")
            yield Footer()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "finish":
                # Apply configuration
                self.app.state.mark_step_complete(SetupStep.COMPLETE)
                result = apply_configuration(self.app.state)

                if result["success"]:
                    self.app.exit(message="Setup complete! Start chatting with Dex.")
                else:
                    self.app.exit(message=f"Setup finished with warnings: {result['errors']}")

    # =========================================================================
    # Main Application
    # =========================================================================

    class SetupWizardApp(App):
        """DexAI Setup Wizard TUI Application."""

        TITLE = "DexAI Setup"
        CSS = """
        Screen {
            background: $background;
        }

        Container {
            width: 70;
            max-width: 80%;
            padding: 1 2;
        }
        """

        BINDINGS = [
            ("q", "quit", "Quit"),
            ("escape", "back", "Back"),
        ]

        def __init__(self, resume: bool = False):
            super().__init__()
            self.state = SetupState.load() if resume else SetupState()
            if not resume:
                self.state.started_at = __import__("datetime").datetime.now().isoformat()

        def on_mount(self) -> None:
            """Start on the appropriate screen."""
            # Resume from current step if resuming
            if (
                self.state.current_step == SetupStep.WELCOME
                or SetupStep.WELCOME not in self.state.completed_steps
            ):
                self.push_screen(WelcomeScreen())
            elif self.state.current_step == SetupStep.CHANNEL:
                self.push_screen(ChannelScreen())
            elif self.state.current_step == SetupStep.PREFERENCES:
                self.push_screen(PreferencesScreen())
            elif self.state.current_step == SetupStep.API_KEY:
                self.push_screen(ApiKeyScreen())
            elif self.state.current_step == SetupStep.COMPLETE:
                self.push_screen(CompleteScreen())
            else:
                self.push_screen(WelcomeScreen())

        def action_back(self) -> None:
            """Go back to previous screen."""
            if len(self.screen_stack) > 1:
                self.pop_screen()

        def action_quit(self) -> None:
            """Quit and save progress."""
            self.state.save()
            self.exit(message="Progress saved. Run 'dexai setup --resume' to continue.")


# =============================================================================
# CLI Entry Point
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="DexAI Setup Wizard")
    parser.add_argument("--resume", action="store_true", help="Resume previous setup")
    parser.add_argument("--reset", action="store_true", help="Reset and start fresh")
    parser.add_argument("--web", action="store_true", help="Open web-based wizard")
    parser.add_argument("--status", action="store_true", help="Show setup status")

    args = parser.parse_args()

    if args.status:
        import json

        from tools.setup.wizard import get_setup_status

        print(json.dumps(get_setup_status(), indent=2))
        return

    if args.reset:
        result = reset_setup()
        print("Setup state reset." if result["success"] else f"Error: {result}")
        return

    if args.web:
        import webbrowser

        webbrowser.open("http://localhost:3000/setup")
        print("Opening web setup wizard...")
        return

    if not TEXTUAL_AVAILABLE:
        print("Error: Textual not installed.")
        print("Install with: pip install textual")
        print("\nAlternatively, use the web wizard: python -m tools.setup.tui.main --web")
        sys.exit(1)

    # Check if already complete
    if is_setup_complete() and not args.resume:
        print("Setup is already complete!")
        print("To re-run setup, use: python -m tools.setup.tui.main --reset")
        return

    # Run the TUI app
    app = SetupWizardApp(resume=args.resume)
    result = app.run()

    if result:
        print(result)


if __name__ == "__main__":
    main()
