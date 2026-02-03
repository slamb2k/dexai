# Tools Manifest

Master list of all available tools. Check here before creating new scripts.

---

## Memory Tools (`tools/memory/`)

| Tool | Description |
|------|-------------|
| `memory_db.py` | Database operations for memory entries (CRUD, search) |
| `memory_read.py` | Read memory context (MEMORY.md, logs, recent entries) |
| `memory_write.py` | Write entries to memory (facts, events, preferences) |
| `embed_memory.py` | Generate embeddings for memory entries |
| `semantic_search.py` | Vector-based semantic search across memory |
| `hybrid_search.py` | Combined keyword + semantic search (best results) |
| `migrate_db.py` | Database schema migration tool |
| `context_capture.py` | Auto-snapshot context on task switches for ADHD working memory (Phase 2) |
| `context_resume.py` | Generate ADHD-friendly "you were here..." resumption prompts (Phase 2) |
| `commitments.py` | Track promises from conversations to prevent relationship damage (Phase 2) |

---

## Security Tools (`tools/security/`)

| Tool | Description |
|------|-------------|
| `audit.py` | Append-only security event logging for forensics and compliance |
| `vault.py` | Encrypted secrets storage with AES-256-GCM encryption |
| `sanitizer.py` | Input validation, HTML stripping, and prompt injection detection |
| `ratelimit.py` | Token bucket rate limiting with cost tracking |
| `session.py` | Session management with secure tokens and idle timeout |
| `permissions.py` | Role-based access control (RBAC) with 5 default roles |

---

## Channel Tools (`tools/channels/`)

| Tool | Description |
|------|-------------|
| `models.py` | Canonical data structures for cross-platform messaging (UnifiedMessage, Attachment, ChannelUser) |
| `inbox.py` | Message storage, cross-channel identity linking, and user preferences |
| `router.py` | Central message routing hub with integrated security pipeline |
| `gateway.py` | WebSocket server for real-time communication backbone |
| `telegram.py` | Telegram bot adapter using python-telegram-bot (polling mode) |
| `discord.py` | Discord bot adapter using discord.py (slash commands) |
| `slack.py` | Slack app adapter using slack-bolt (Socket Mode) |

---

## System Tools (`tools/system/`)

| Tool | Description |
|------|-------------|
| `executor.py` | Sandboxed command execution with allowlists, timeouts, and resource limits |
| `fileops.py` | Secure file read/write/delete sandboxed to approved directories |
| `browser.py` | Playwright-based web automation with domain controls and isolated profiles |
| `network.py` | HTTP client with domain allowlist, SSL enforcement, and private IP blocking |

---

## Automation Tools (`tools/automation/`)

| Tool | Description |
|------|-------------|
| `scheduler.py` | Cron job scheduling with execution tracking, retry logic, and cost limits |
| `heartbeat.py` | Periodic background awareness checks parsed from HEARTBEAT.md |
| `notify.py` | Notification dispatch with priority queuing, DND support, flow awareness, and channel routing |
| `triggers.py` | Event triggers for file changes (watchdog) and webhooks with debouncing |
| `runner.py` | Background daemon that orchestrates all automation components |
| `flow_detector.py` | Hyperfocus/flow state detection from activity patterns and manual overrides (Phase 4) |
| `transition_calculator.py` | ADHD-appropriate reminder time calculation with learning from patterns (Phase 4) |

---

## ADHD Communication Tools (`tools/adhd/`)

| Tool | Description |
|------|-------------|
| `response_formatter.py` | Brevity-first formatting, preamble stripping, and one-thing mode extraction |
| `language_filter.py` | RSD-safe language detection and reframing (no guilt-inducing phrases) |

---

## Task Engine Tools (`tools/tasks/`)

| Tool | Description |
|------|-------------|
| `manager.py` | Task CRUD operations with parent/subtask relationships and step tracking (Phase 5) |
| `decompose.py` | Break vague tasks into concrete steps using LLM or rule-based fallback (Phase 5) |
| `friction_solver.py` | Identify and pre-solve hidden blockers (passwords, documents, phone calls) (Phase 5) |
| `current_step.py` | Return ONLY the single next action - core ADHD-friendly interface (Phase 5) |

---

## Learning Tools (`tools/learning/`)

| Tool | Description |
|------|-------------|
| `energy_tracker.py` | Infer energy levels from activity signals (response time, message length, session duration) (Phase 6) |
| `pattern_analyzer.py` | Detect behavioral patterns (daily routines, weekly cycles, avoidance, productive bursts) (Phase 6) |
| `task_matcher.py` | Match tasks to optimal times based on energy profiles and patterns (Phase 6) |

---

## Dashboard Tools (`tools/dashboard/`)

### Backend (FastAPI)

| Tool | Description |
|------|-------------|
| `backend/main.py` | FastAPI application with CORS, session auth, health checks, and router registration |
| `backend/database.py` | SQLite database operations for events, metrics, state, and preferences |
| `backend/models.py` | Pydantic models for all API request/response types |
| `backend/websocket.py` | WebSocket server for real-time event streaming (state, activity, tasks, metrics) |
| `backend/routes/status.py` | GET/PUT /api/status — Dex avatar state for monitoring |
| `backend/routes/tasks.py` | GET /api/tasks — Task list with filters and detail view |
| `backend/routes/activity.py` | GET/POST /api/activity — Activity feed with pagination |
| `backend/routes/metrics.py` | GET /api/metrics/summary, /timeseries — Usage stats and charts |
| `backend/routes/settings.py` | GET/PATCH /api/settings — Configuration management |

### Frontend (Next.js 14)

| File | Description |
|------|-------------|
| `frontend/app/layout.tsx` | Root layout with sidebar, top bar, and toast container |
| `frontend/app/page.tsx` | Home/overview page with avatar, stats, and activity feed |
| `frontend/app/tasks/page.tsx` | Task list with filters and detail modal |
| `frontend/app/activity/page.tsx` | Real-time activity stream with WebSocket support |
| `frontend/app/metrics/page.tsx` | Usage statistics with Recharts visualizations |
| `frontend/app/settings/page.tsx` | Configuration UI with collapsible sections |
| `frontend/app/audit/page.tsx` | Security audit log viewer with filters |
| `frontend/app/debug/page.tsx` | Admin debug tools (health, logs, database) |
| `frontend/components/dex-avatar.tsx` | Animated Dex avatar with 9 states (idle, thinking, working, etc.) |
| `frontend/components/sidebar.tsx` | Navigation sidebar with collapsible state |
| `frontend/components/stat-card.tsx` | Metric display cards with sparklines |
| `frontend/components/activity-feed.tsx` | Activity event list component |
| `frontend/components/task-card.tsx` | Task display card with status indicators |
| `frontend/components/toast.tsx` | Toast notification system |
| `frontend/lib/api.ts` | Typed fetch wrapper for all API endpoints |
| `frontend/lib/socket.ts` | WebSocket client for real-time updates |
| `frontend/lib/store.ts` | Zustand stores for client state management |
| `frontend/lib/utils.ts` | Utility functions (cn, formatters, debounce) |

---

## CLI Entry Point (`tools/cli.py`)

| Tool | Description |
|------|-------------|
| `cli.py` | Main CLI entry point — `dexai setup`, `dexai dashboard`, `dexai --version` |

---

## Setup Tools (`tools/setup/`)

| Tool | Description |
|------|-------------|
| `wizard.py` | Core setup state management, channel validation, test messaging, and configuration generation (Phase 8) |
| `tui/main.py` | Textual-based terminal UI wizard with all setup screens (Phase 8) |
| `guides/telegram.md` | Step-by-step Telegram bot setup instructions |
| `guides/discord.md` | Step-by-step Discord bot setup instructions |
| `guides/slack.md` | Step-by-step Slack app setup instructions |

---

## Dashboard Setup API (`tools/dashboard/backend/routes/setup.py`)

| Endpoint | Description |
|----------|-------------|
| `GET /api/setup/state` | Get current setup wizard state |
| `POST /api/setup/channel/validate` | Validate channel credentials |
| `POST /api/setup/channel/test` | Send test message to channel |
| `POST /api/setup/apikey/validate` | Validate Anthropic API key |
| `POST /api/setup/complete` | Finalize setup and apply configuration |
| `POST /api/setup/reset` | Reset setup state |

---

## Shell Scripts (`scripts/`)

| Script | Description |
|--------|-------------|
| `claude-tasks.sh` | Shell helpers for Claude Code task system — aliases for init, status, clear |

---

## Testing Infrastructure (`tests/`)

| File | Description |
|------|-------------|
| `conftest.py` | Shared pytest fixtures (temp_db, mock_user_id, sample_task, etc.) |
| `unit/security/*.py` | Unit tests for security tools (sanitizer, audit, permissions) |
| `unit/adhd/*.py` | Unit tests for ADHD communication tools (language_filter, response_formatter) |
| `unit/tasks/*.py` | Unit tests for task engine (manager) |
| `unit/memory/*.py` | Unit tests for memory tools (commitments) |
| `integration/conftest.py` | Integration test fixtures (test clients, mock adapters, database isolation) |
| `integration/test_dashboard_api.py` | Integration tests for FastAPI dashboard routes (/api/status, /tasks, /activity) |
| `integration/test_message_pipeline.py` | Integration tests for message routing and security pipeline |
| `integration/test_task_flow.py` | Integration tests for task lifecycle (create -> decompose -> complete) |

---

## CI/CD Configuration

| File | Description |
|------|-------------|
| `pyproject.toml` | Python project configuration (dependencies, pytest, ruff, mypy) |
| `.github/workflows/ci.yml` | GitHub Actions CI pipeline (lint, typecheck, test, frontend) |
| `tools/dashboard/frontend/vitest.config.ts` | Frontend test configuration |
| `tools/dashboard/frontend/__tests__/` | Frontend component tests |

---

## Office Integration Tools (`tools/office/`) — Phase 12

### Core Modules

| Tool | Description |
|------|-------------|
| `__init__.py` | Database schema, path constants, shared utilities |
| `models.py` | Data models (Email, CalendarEvent, OfficeAccount, IntegrationLevel) |
| `oauth_manager.py` | OAuth 2.0 flows for Google and Microsoft (token exchange, refresh, storage) |
| `level_detector.py` | Detect integration level from granted scopes, suggest upgrades |
| `onboarding.py` | Integration level selection wizard for setup |

### Providers (`tools/office/providers/`)

| Tool | Description |
|------|-------------|
| `base.py` | Abstract OfficeProvider base class defining provider interface |
| `google_workspace.py` | Gmail and Google Calendar API integration (Level 2-5) |
| `microsoft_365.py` | Microsoft Graph API for Outlook and Calendar (Level 2-5) |
| `standalone_imap.py` | IMAP/SMTP provider for Dex's own mailbox (Level 1) |

### Email Tools (`tools/office/email/`)

| Tool | Description |
|------|-------------|
| `reader.py` | Unified inbox reading, search, filtering across providers |
| `summarizer.py` | ADHD-friendly inbox summaries, priority detection, "one thing" mode |

### Calendar Tools (`tools/office/calendar/`)

| Tool | Description |
|------|-------------|
| `reader.py` | Event retrieval, availability checking, free slot finding |

### Configuration

| File | Description |
|------|-------------|
| `args/office_integration.yaml` | Integration levels, OAuth config, ADHD safeguards, security settings |

---

*Update this manifest when adding new tools.*
