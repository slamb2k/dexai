# Goal: Phase 8 Guided Installation

## Objective

Create a first-class onboarding experience that guides users through DexAI setup — available as both a browser-based wizard and a terminal-based TUI. The goal is **zero-friction setup** that gets users to their first successful interaction within minutes.

## Rationale

ADHD users often abandon software during setup if:
- Instructions are walls of text
- There are too many configuration decisions upfront
- The process feels overwhelming
- They can't see progress

DexAI's installation should feel like a **conversation with a helpful guide**, not a checklist of technical requirements. We want users to feel accomplished, not exhausted, after setup.

## Dependencies

- Phase 0 (Security) — For credential storage
- Phase 1 (Channels) — To configure messaging adapters
- Phase 7 (Dashboard) — Optional, for browser-based flow

---

## Design Principles for Installation

### 1. Progressive Disclosure

Don't show everything at once. Reveal options as they become relevant.

**Bad:** "Configure your Telegram bot token, Discord webhook, Slack app ID, and notification preferences."

**Good:** "Let's start with one channel. Which messaging app do you use most?"

### 2. Smart Defaults

Pre-fill sensible defaults. Let users change later, not during setup.

**Examples:**
- Active hours: 9 AM - 10 PM (user's timezone)
- Notification style: Gentle
- Model: Claude Sonnet (balanced cost/quality)

### 3. Immediate Feedback

After each step, show something working. Build confidence.

**Example:** After connecting Telegram, immediately send a test message: "Hi! Dex is connected and ready to help."

### 4. Easy Recovery

Installation can be interrupted and resumed. Progress is saved.

### 5. Skip Option

Power users can skip the wizard and configure manually.

---

## Installation Modes

### Mode 1: Browser-Based (Web Wizard)

**When to use:** User prefers visual interface, or is setting up on a remote server.

**Access:** `http://localhost:3000/setup` (or deployed URL)

**Flow:**
```
┌─────────────────────────────────────────────────────────────┐
│                    Welcome to DexAI                          │
│                                                              │
│        ┌─────────────────────────────┐                      │
│        │                             │                      │
│        │      DEX AVATAR (waving)    │                      │
│        │      "Hi! I'm Dex."         │                      │
│        │                             │                      │
│        └─────────────────────────────┘                      │
│                                                              │
│   I'm your AI assistant designed for how your brain         │
│   actually works. Let's get you set up in a few minutes.    │
│                                                              │
│        ┌─────────────────────────────────────┐              │
│        │         Get Started                 │              │
│        └─────────────────────────────────────┘              │
│                                                              │
│                     [ Skip Setup ]                           │
└─────────────────────────────────────────────────────────────┘
```

### Mode 2: Terminal-Based (TUI Wizard)

**When to use:** User is comfortable with terminal, or setting up on headless server.

**Command:** `dexai setup` or `python -m dexai.setup`

**Flow:**
```
╭───────────────────────────────────────────────────────────────╮
│                                                               │
│   ██████╗ ███████╗██╗  ██╗ █████╗ ██╗                        │
│   ██╔══██╗██╔════╝╚██╗██╔╝██╔══██╗██║                        │
│   ██║  ██║█████╗   ╚███╔╝ ███████║██║                        │
│   ██║  ██║██╔══╝   ██╔██╗ ██╔══██╗██║                        │
│   ██████╔╝███████╗██╔╝ ██╗██║  ██║██║                        │
│   ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝                        │
│                                                               │
│   Welcome! Let's get you set up.                             │
│                                                               │
│   Press Enter to continue, or 'q' to quit...                 │
│                                                               │
╰───────────────────────────────────────────────────────────────╯
```

**Library:** [Textual](https://textual.textualize.io/) or [Rich](https://rich.readthedocs.io/) for Python TUI.

---

## Setup Flow (Both Modes)

### Step 1: Welcome & Introduction

**Content:**
- Brief introduction to Dex
- What to expect during setup (3-5 minutes)
- What you'll need (just your messaging app of choice)

**Actions:**
- [Get Started] → Next step
- [Skip Setup] → Manual configuration instructions

### Step 2: First Channel Connection

**Content:**
```
Where would you like to chat with Dex?

Pick one to start — you can add more later.

    ○ Telegram (Recommended)
      Works great, minimal setup

    ○ Discord
      Good for gaming/community focus

    ○ Slack
      Best for work integration

    ○ I'll configure channels later
```

**Per-Channel Sub-Flow:**

#### Telegram Flow:
1. "Open @BotFather in Telegram"
2. "Send /newbot and follow the prompts"
3. "Paste your bot token here: [_______________]"
4. [Test Connection] → Sends test message
5. "Open your bot in Telegram and send 'hello'"
6. Verify Dex responds

#### Discord Flow:
1. "Go to Discord Developer Portal"
2. "Create a new application..."
3. [Detailed guide with screenshots in web mode]
4. Paste bot token
5. [Test Connection]
6. Select server, verify Dex is online

#### Slack Flow:
1. "Go to Slack App Directory"
2. Create app from manifest (we provide it)
3. Install to workspace
4. Paste tokens
5. [Test Connection]

### Step 3: Basic Preferences

**Content:**
```
A few quick preferences to personalize Dex:

What's your name?
[_______________]

What timezone are you in?
[Auto-detected: America/New_York ▼]

When should Dex be active?
[9:00 AM] to [10:00 PM]
(Dex won't disturb you outside these hours)
```

**Note:** Keep this minimal. More settings available in dashboard later.

### Step 4: Security Setup

**Content:**
```
Let's secure your assistant.

Create a master password:
[_______________]
(This encrypts your API keys and secrets)

Confirm password:
[_______________]

💡 Tip: Use a passphrase like "correct-horse-battery-staple"
```

**Actions:**
- Password strength indicator
- Option to generate secure password
- Store securely using vault.py

### Step 5: LLM API Key (Optional)

**Content:**
```
Dex uses Claude AI to understand and respond to you.

Do you have an Anthropic API key?

    ○ Yes, I have one
      [Paste your API key: _______________]

    ○ No, help me get one
      [Opens Anthropic Console in new tab]

    ○ Skip for now
      (You can add this later in Settings)
```

**Validation:**
- Test API key with a simple call
- Show remaining credits if possible
- Store encrypted in vault

### Step 6: First Interaction

**Content:**
```
You're all set! Let's try it out.

Send a message to Dex in [Telegram/Discord/Slack]:

   "Hi Dex, I just set you up!"

Waiting for your message...

    ◐ Listening...
```

**On Success:**
```
🎉 It worked!

Dex received your message and responded.
Your assistant is ready to help.

[Open Dashboard]    [Go to Telegram]
```

### Step 7: What's Next (Optional Tips)

**Content:**
```
Quick tips to get started:

💬  Just chat naturally
    "Remind me to call mom tomorrow"
    "What was I working on yesterday?"

⚡  Dex learns your patterns
    The more you chat, the better Dex gets

🔕  Dex respects your focus
    Won't interrupt during hyperfocus periods

Ready to explore more?
[Open Dashboard]    [Read the Guide]    [Done]
```

---

## Error Handling

### Connection Failures

```
Hmm, I couldn't connect to Telegram.

This usually means:
• The bot token has a typo
• The bot was deleted
• Network issues

Let's try again:
[Paste token again: _______________]

[← Back]    [Try Again]    [Skip for Now]
```

### API Key Invalid

```
That API key didn't work.

Make sure you:
• Copied the full key (starts with 'sk-ant-')
• Have billing set up on Anthropic Console

[Paste key again: _______________]

[← Back]    [Try Again]    [Get API Key]
```

### Partial Setup

```
Setup interrupted? No problem.

We saved your progress. Pick up where you left off:

✓ Welcome
✓ Channel: Telegram connected
○ Preferences (incomplete)
○ Security
○ API Key

[Resume Setup]    [Start Over]
```

---

## Technical Implementation

### File Structure

```
tools/setup/
├── __init__.py
├── wizard.py               # Core setup logic
├── web/                    # Browser-based wizard
│   ├── pages/
│   │   ├── welcome.tsx
│   │   ├── channel.tsx
│   │   ├── preferences.tsx
│   │   ├── security.tsx
│   │   ├── api-key.tsx
│   │   ├── test.tsx
│   │   └── complete.tsx
│   └── components/
│       ├── step-indicator.tsx
│       ├── channel-card.tsx
│       └── password-input.tsx
│
├── tui/                    # Terminal-based wizard
│   ├── __init__.py
│   ├── main.py             # Entry point
│   ├── screens/
│   │   ├── welcome.py
│   │   ├── channel.py
│   │   ├── preferences.py
│   │   ├── security.py
│   │   ├── api_key.py
│   │   ├── test.py
│   │   └── complete.py
│   └── widgets/
│       ├── step_progress.py
│       ├── password_field.py
│       └── channel_selector.py
│
└── guides/                 # Channel setup guides
    ├── telegram.md
    ├── discord.md
    └── slack.md
```

### Setup State Management

```python
# tools/setup/wizard.py

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
import json
from pathlib import Path

class SetupStep(Enum):
    WELCOME = "welcome"
    CHANNEL = "channel"
    PREFERENCES = "preferences"
    SECURITY = "security"
    API_KEY = "api_key"
    TEST = "test"
    COMPLETE = "complete"

@dataclass
class SetupState:
    current_step: SetupStep = SetupStep.WELCOME
    completed_steps: List[SetupStep] = field(default_factory=list)

    # Channel config
    primary_channel: Optional[str] = None
    channel_config: dict = field(default_factory=dict)
    channel_verified: bool = False

    # Preferences
    user_name: Optional[str] = None
    timezone: str = "UTC"
    active_hours_start: str = "09:00"
    active_hours_end: str = "22:00"

    # Security
    master_password_set: bool = False

    # API
    api_key_set: bool = False
    api_key_verified: bool = False

    def save(self, path: Path = Path("data/setup_state.json")):
        """Persist setup state for resume capability."""
        path.parent.mkdir(exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.__dict__, f, default=str)

    @classmethod
    def load(cls, path: Path = Path("data/setup_state.json")) -> "SetupState":
        """Load previous setup state."""
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                # Handle enum conversion
                data['current_step'] = SetupStep(data['current_step'])
                data['completed_steps'] = [SetupStep(s) for s in data['completed_steps']]
                return cls(**data)
        return cls()
```

### CLI Entry Point

```python
# tools/setup/tui/main.py

import click
from textual.app import App
from .screens import WelcomeScreen, ChannelScreen, PreferencesScreen

@click.command()
@click.option('--resume', is_flag=True, help='Resume previous setup')
@click.option('--web', is_flag=True, help='Open browser-based wizard')
@click.option('--reset', is_flag=True, help='Start fresh, clear previous state')
def setup(resume: bool, web: bool, reset: bool):
    """Launch DexAI setup wizard."""

    if reset:
        Path("data/setup_state.json").unlink(missing_ok=True)
        click.echo("Setup state cleared.")

    if web:
        import webbrowser
        webbrowser.open("http://localhost:3000/setup")
        return

    # Launch TUI
    app = SetupWizardApp()
    app.run()

class SetupWizardApp(App):
    """Textual TUI application for setup wizard."""

    CSS = """
    Screen {
        background: #0a0a0f;
    }
    """

    def on_mount(self):
        self.push_screen(WelcomeScreen())

if __name__ == "__main__":
    setup()
```

### Web Setup API Endpoints

```python
# tools/setup/web/api.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..wizard import SetupState, SetupStep

router = APIRouter(prefix="/api/setup")

@router.get("/state")
async def get_setup_state():
    """Get current setup state."""
    state = SetupState.load()
    return {
        "current_step": state.current_step.value,
        "completed_steps": [s.value for s in state.completed_steps],
        "is_complete": state.current_step == SetupStep.COMPLETE
    }

@router.post("/channel/test")
async def test_channel_connection(channel: str, config: dict):
    """Test channel connection with provided config."""
    # Import appropriate adapter
    if channel == "telegram":
        from tools.channels.telegram import TelegramAdapter
        adapter = TelegramAdapter(token=config.get("token"))
    elif channel == "discord":
        from tools.channels.discord import DiscordAdapter
        adapter = DiscordAdapter(token=config.get("token"))
    elif channel == "slack":
        from tools.channels.slack import SlackAdapter
        adapter = SlackAdapter(
            bot_token=config.get("bot_token"),
            app_token=config.get("app_token")
        )
    else:
        raise HTTPException(400, f"Unknown channel: {channel}")

    # Test connection
    try:
        result = await adapter.test_connection()
        return {"success": True, "details": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/complete")
async def complete_setup(state: dict):
    """Finalize setup and apply configuration."""
    # Validate all required fields
    # Apply configuration to args files
    # Initialize databases
    # Return success
    pass
```

---

## Configuration Generated

After setup completes, the wizard generates:

### 1. `args/user.yaml`

```yaml
user:
  name: "Alex"
  timezone: "America/New_York"

active_hours:
  start: "09:00"
  end: "22:00"
  days: [mon, tue, wed, thu, fri, sat, sun]

preferences:
  notification_style: gentle
  brevity_default: true
```

### 2. Channel Configuration

Credentials stored in vault:
```bash
vault set telegram_bot_token "123456:ABC..."
vault set anthropic_api_key "sk-ant-..."
```

Channel enabled in `args/channels.yaml`:
```yaml
channels:
  telegram:
    enabled: true
    primary: true
  discord:
    enabled: false
  slack:
    enabled: false
```

### 3. `data/setup_complete.flag`

Empty file indicating setup has been completed. Dashboard and other tools check for this.

---

## Verification Checklist

### TUI Wizard
- [ ] `dexai setup` launches TUI
- [ ] Welcome screen displays correctly
- [ ] Channel selection works (Telegram, Discord, Slack)
- [ ] Each channel guide is clear and complete
- [ ] Password input masks characters
- [ ] API key validation works
- [ ] Test message sends successfully
- [ ] Progress persists across interruptions
- [ ] Completion screen shows next steps

### Web Wizard
- [ ] `/setup` route accessible when setup incomplete
- [ ] Redirects to dashboard when setup complete
- [ ] All steps render correctly
- [ ] Channel connection tests work
- [ ] Form validation provides clear feedback
- [ ] Progress indicator shows current step
- [ ] Can navigate back to previous steps
- [ ] Mobile-responsive (stretch)

### Configuration Output
- [ ] `args/user.yaml` created with correct values
- [ ] Credentials stored encrypted in vault
- [ ] `args/channels.yaml` updated correctly
- [ ] `data/setup_complete.flag` created on completion

### Error Handling
- [ ] Invalid bot token shows clear error
- [ ] Invalid API key shows clear error
- [ ] Network failures handled gracefully
- [ ] Partial setup can be resumed
- [ ] "Skip" options work correctly

---

## Channel Setup Guides

Detailed guides should be created in `tools/setup/guides/`:

### `telegram.md`

```markdown
# Setting up Telegram with DexAI

## What You'll Need
- A Telegram account
- 2-3 minutes

## Steps

### 1. Open BotFather
Open Telegram and search for `@BotFather`, or click:
https://t.me/BotFather

### 2. Create Your Bot
Send `/newbot` to BotFather

You'll be asked:
1. **Bot name**: Choose something like "My DexAI Assistant"
2. **Username**: Must end in `bot`, like `mydex_bot`

### 3. Copy Your Token
BotFather will give you a token like:
`123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

Copy this entire token.

### 4. Paste in DexAI
Paste the token in the setup wizard.

### 5. Test It
Open your new bot in Telegram and send "hello".
You should get a response from Dex!

## Troubleshooting

**"Token invalid"**: Make sure you copied the entire token, including the numbers before the colon.

**"No response"**: Check that DexAI is running. Try restarting the service.
```

Similar guides for Discord and Slack with screenshots for web mode.

---

## Future Enhancements (Out of Scope for v1)

- [ ] Multi-language support
- [ ] Voice-guided setup
- [ ] Import from other tools (migration)
- [ ] Team/organization setup mode
- [ ] Setup via mobile app
- [ ] Interactive tutorials after setup

---

## References

- [Textual](https://textual.textualize.io/) — Python TUI framework
- [Rich](https://rich.readthedocs.io/) — Terminal formatting
- `tools/security/vault.py` — Credential storage
- `tools/channels/*.py` — Channel adapters
- `goals/phase7_dashboard.md` — Web interface

---

*A great first impression matters. This phase ensures users feel successful from minute one, reducing the chance they abandon DexAI before experiencing its value.*
