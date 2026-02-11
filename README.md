# DexAI

**A zero-maintenance AI personal assistant designed for ADHD users.**

DexAI is built around how ADHD brains actually work. Unlike generic productivity tools that fail when users can't consistently operate them, DexAI works even when forgotten for days -- surfacing gently, never guilting, and actively reducing cognitive load rather than adding to it.

---

## Key Features

- **Zero-Maintenance** -- Works even if you forget it exists for three days
- **Emotionally Safe** -- No guilt, no shame, no "overdue" counts; forward-facing only
- **One-Thing Focus** -- Presents single actionable items, not overwhelming lists
- **External Working Memory** -- Captures context on every switch, enables instant resumption
- **Time-Blindness Aware** -- Understands transition time, not just clock time
- **Hyperfocus Protection** -- Suppresses interruptions during productive flow states
- **Multi-Channel Support** -- Telegram, Discord, Slack, and WebSocket gateway
- **Web Dashboard** -- Visual management interface with Dex avatar and activity monitoring

---

## Architecture Overview

DexAI follows the GOTCHA Framework -- a 6-layer architecture for agentic systems:

```
┌─────────────────────────────────────────────────────────────┐
│                        DexAI Core                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Telegram│  │ Discord │  │  Slack  │  │ Gateway │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       └────────────┼───────────┴───────────┬┘              │
│                    ▼                                        │
│              ┌──────────┐                                   │
│              │  Router  │ ← Unified message handling        │
│              └────┬─────┘                                   │
│                   ▼                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Security Pipeline                       │   │
│  │  Sanitize → Authenticate → Rate Limit → Authorize   │   │
│  └─────────────────────────────────────────────────────┘   │
│                   ▼                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              ADHD Intelligence Layer                 │   │
│  │  Context Capture | RSD-Safe Response | Task Engine  │   │
│  └─────────────────────────────────────────────────────┘   │
│                   ▼                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │ Memory  │  │ Notify  │  │Scheduler│  │ Triggers│       │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Node.js 20+** (for the web dashboard)
- **uv** (recommended) or pip for Python package management

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/dexai/dexai.git
   cd dexai
   ```

2. **Set up Python environment with uv (recommended)**
   ```bash
   # Install uv if you don't have it
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Create virtual environment and install dependencies
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e .

   # Install dev dependencies (for testing/linting)
   uv pip install -e ".[dev]"

   # Install channel adapters (optional)
   uv pip install -e ".[channels]"
   ```

   **Or with pip:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   pip install -e ".[dev]"  # For development
   ```

3. **Set up the web dashboard frontend**
   ```bash
   cd tools/dashboard/frontend
   npm install
   cd ../../..
   ```

4. **Configure environment variables**
   ```bash
   # Create .env file from the template below
   cp .env.example .env  # Or create manually

   # Edit .env with your API keys
   ```

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Channel adapters (configure the ones you use)
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
DISCORD_BOT_TOKEN=your-discord-bot-token
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_APP_TOKEN=xapp-your-slack-app-token

# Dashboard (optional)
DASHBOARD_SECRET_KEY=your-random-secret-key
DASHBOARD_PORT=8080
FRONTEND_PORT=3000
```

### Running Locally

**Run the backend API server:**
```bash
uvicorn tools.dashboard.backend.main:app --host 0.0.0.0 --port 8080 --reload
```

**Run the web dashboard frontend (in a separate terminal):**
```bash
cd tools/dashboard/frontend
npm run dev
```

**Run the dashboard (setup is chat-based):**
```bash
dexai dashboard
```

### Running with Docker

**Build the Docker image:**
```bash
docker build -t dexai .
```

**Run the container:**
```bash
docker run -d \
  --name dexai \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  -e ANTHROPIC_API_KEY=your-api-key \
  dexai
```

The API will be available at `http://localhost:8080`.

---

## Project Structure

```
dexai/
├── tools/                    # Execution layer (Python scripts)
│   ├── adhd/                 # ADHD-specific intelligence
│   │   ├── response_formatter.py   # Brevity-first formatting
│   │   └── language_filter.py      # RSD-safe language detection
│   ├── automation/           # Scheduler, notifications, flow detection
│   ├── channels/             # Messaging adapters (Telegram, Discord, Slack)
│   ├── dashboard/            # Web dashboard
│   │   ├── backend/          # FastAPI API server
│   │   └── frontend/         # Next.js 14 web UI
│   ├── learning/             # Energy patterns, task matching
│   ├── memory/               # Persistent memory, context capture
│   ├── security/             # Auth, audit, permissions, vault
│   ├── setup/                # Setup wizard (TUI + guides)
│   ├── system/               # Sandboxed execution, file ops
│   └── tasks/                # Task decomposition, friction solving
├── args/                     # Configuration files (YAML)
├── context/                  # Design principles, research docs
├── goals/                    # PRD, phase plans, workflows
├── hardprompts/              # LLM instruction templates
├── data/                     # SQLite databases (gitignored)
├── memory/                   # Persistent user memory
├── tests/                    # Test suite
├── pyproject.toml            # Python project configuration
├── Dockerfile                # Container build
└── CLAUDE.md                 # System handbook (AI instructions)
```

---

## Configuration

Configuration files are stored in the `args/` directory:

| File | Purpose |
|------|---------|
| `adhd_mode.yaml` | Communication settings (brevity, RSD-safe language) |
| `working_memory.yaml` | Context capture settings |
| `smart_notifications.yaml` | Notification timing and flow protection |
| `task_engine.yaml` | Task decomposition settings |
| `learning.yaml` | Personalization and pattern detection |
| `dashboard.yaml` | Web dashboard settings |
| `setup.yaml` | Setup wizard configuration |

---

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=tools --cov-report=html

# Run specific test categories
pytest tests/unit/security/
pytest tests/unit/adhd/
pytest tests/unit/tasks/
```

### Linting and Type Checking

```bash
# Lint with ruff
ruff check .

# Auto-fix linting issues
ruff check --fix .

# Format code
ruff format .

# Type check with mypy
mypy tools/
```

### Frontend Tests

```bash
cd tools/dashboard/frontend
npm test
```

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| Database | SQLite (local-first, zero-config) |
| LLM | Claude API (Anthropic) |
| Backend | FastAPI, uvicorn, WebSockets |
| Frontend | Next.js 14, Tailwind CSS, shadcn/ui |
| TUI | Textual, Rich |
| Testing | pytest, Vitest |
| Linting | ruff, mypy |

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please follow the commit message conventions:
- `feat(scope):` -- New feature
- `fix(scope):` -- Bug fix
- `docs(scope):` -- Documentation
- `refactor(scope):` -- Code refactoring
- `chore(scope):` -- Maintenance tasks
