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
| `service.py` | MemoryService facade — provider-agnostic memory operations with ADHD transforms |
| `daemon.py` | Background memory daemon — extraction queue consumer, consolidation scheduler, health monitor |
| `l1_builder.py` | L1 memory block builder — condensed context for system prompt injection (~1000 tokens) |
| `auto_recall.py` | Auto-recall — searches L2 for relevant memories and injects into L1 context on topic shifts |

### Memory Extraction Pipeline (`tools/memory/extraction/`)

| Tool | Description |
|------|-------------|
| `gate.py` | Heuristic gate — fast regex-based pre-filter (<1ms) to decide if a turn warrants extraction |
| `queue.py` | Extraction queue — async background queue that decouples extraction from user response path |
| `extractor.py` | Session note extractor — LLM-based (Haiku) structured memory extraction from conversation turns |
| `classifier.py` | Supersession classifier — AUDN pipeline (Add/Update/Supersede/Noop) for memory lifecycle |

### Memory Providers (`tools/memory/providers/`)

Pluggable memory backend system supporting multiple storage providers.

| Provider | Description |
|----------|-------------|
| `base.py` | Abstract MemoryProvider base class, data structures (MemoryEntry, SearchFilters, etc.) |
| `native.py` | NativeProvider — Local SQLite with hybrid BM25 + semantic search (default) |
| `mem0_provider.py` | Mem0Provider — Graph-based memory (cloud or self-hosted with Qdrant) |
| `zep_provider.py` | ZepProvider — Temporal knowledge graph (cloud or self-hosted with Neo4j) |
| `simplemem_provider.py` | SimpleMemProvider — Cloud-only semantic compression API |
| `claudemem_provider.py` | ClaudeMemProvider — Local progressive disclosure memory |

**Provider Features:**
- **Native**: Local-only, SQLite, hybrid search, no external dependencies
- **Mem0**: Cloud + self-hosted, graph memory, automatic organization
- **Zep**: Cloud + self-hosted, temporal graph, bi-temporal modeling
- **SimpleMem**: Cloud-only, semantic compression, intent-aware retrieval
- **ClaudeMem**: Local-only, progressive disclosure, ADHD-optimized retrieval

**Configuration:** `args/memory.yaml`

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
| `container_executor.py` | Container-based execution isolation per user session (opt-in via DEXAI_CONTAINER_ISOLATION) |
| `advisory_feed.py` | Dynamic malicious package feed from OSV and PyPI advisory APIs with 24h SQLite cache |

---

## Operations Tools (`tools/ops/`)

| Tool | Description |
|------|-------------|
| `migrate.py` | Forward-only database migration runner (numbered SQL files in `migrations/`) |
| `cost_tracker.py` | Per-API-call cost recording and query with conversation-level aggregation |
| `budget_alerter.py` | Budget threshold alerting at 80%/95%/100% with audit logging and dashboard events |
| `backup.py` | WAL-safe SQLite backup with gzip compression and configurable retention |
| `circuit_breaker.py` | Circuit breaker for external APIs (closed/open/half_open states, provider fallback, per-provider tracking) |
| `prometheus.py` | Prometheus-compatible metrics endpoint (/metrics, auth-exempt, text exposition format) |
| `transparency.py` | "Show Your Work" transparency mode — per-conversation toggle exposing tool calls, routing, and cost |

---

## Logging Configuration (`tools/`)

| Tool | Description |
|------|-------------|
| `logging_config.py` | Structured JSON logging configuration via structlog wrapping stdlib |

---

## Channel Tools (`tools/channels/`)

| Tool | Description |
|------|-------------|
| `models.py` | Canonical data structures for cross-platform messaging (UnifiedMessage, Attachment, MediaContent, ContentBlock) |
| `inbox.py` | Message storage and conversation history |
| `router.py` | Central message routing hub with integrated security pipeline |
| `gateway.py` | WebSocket server for real-time communication backbone |
| `telegram_adapter.py` | Telegram bot adapter using python-telegram-bot (polling mode, voice notes, attachment download) |
| `discord.py` | Discord bot adapter using discord.py (slash commands, voice messages, attachment download) |
| `slack.py` | Slack app adapter using slack-bolt (Socket Mode, audio files, attachment download) |
| `session_manager.py` | ClaudeSDKClient-based session manager for continuous conversations with SDK resumption support |
| `sdk_handler.py` | Message handler using DexAIClient, session management via SessionManager, complexity hints, channel-aware truncation, media processing integration |
| `media_processor.py` | Multi-modal media processing: Claude Vision for images, Whisper for audio, FFmpeg for video, PyPDF2/python-docx for documents (Phase 15a/15b) |
| `image_generator.py` | Image generation via DALL-E API with cost tracking and configurable quality/size options (Phase 15a) |
| `audio_processor.py` | Audio/voice transcription via OpenAI Whisper API, TTS generation with cost tracking (Phase 15b) |
| `video_processor.py` | Video processing with FFmpeg: frame extraction, audio track transcription, thumbnail generation (Phase 15b) |
| `tts_generator.py` | Text-to-Speech generation via OpenAI TTS API with voice selection and channel-optimized formats (Phase 15b) |

### Platform Renderers (`tools/channels/renderers/`) — Phase 15c

| Tool | Description |
|------|-------------|
| `__init__.py` | ChannelRenderer ABC, renderer registry (register, get, list), auto-registration on import |
| `telegram_renderer.py` | Telegram renderer: HTML parse_mode, media groups, inline keyboards, native polls |
| `discord_renderer.py` | Discord renderer: rich embeds, markdown formatting, message components, reaction-based polls |
| `slack_renderer.py` | Slack renderer: Block Kit format, mrkdwn sections, action blocks, button/poll elements |

### Content Processing (`tools/channels/content/`) — Phase 15c

| Tool | Description |
|------|-------------|
| `__init__.py` | Re-exports ContentSplitter and MarkdownConverter |
| `splitter.py` | Content splitting per channel limits with code-block preservation and natural boundary detection |
| `markdown.py` | Markdown converter: to_telegram (HTML), to_discord (markdown), to_slack (mrkdwn), strip_markdown |

### Interactive Elements (`tools/channels/interactive/`) — Phase 15d

| Tool | Description |
|------|-------------|
| `__init__.py` | Re-exports ButtonHandler and PollHandler |
| `buttons.py` | Button state management with SQLite persistence, callback handling, expiry cleanup |
| `polls.py` | Poll lifecycle: creation, vote tracking (single/multi-choice), results, close with SQLite state |

### Media Processors (`tools/channels/media/`) — Phase 15d

| Tool | Description |
|------|-------------|
| `__init__.py` | Re-exports LocationProcessor, ContactProcessor, StorageCleanup with graceful fallbacks |
| `location_processor.py` | Geocoding via Nominatim (reverse/forward), rate-limited, map URL generation |
| `contact_processor.py` | vCard 3.0/4.0 parsing, Telegram contact dict processing, field extraction |
| `storage_cleanup.py` | Temp file cleanup, expired DB entry removal, storage stats reporting |

---

## System Tools (`tools/system/`)

| Tool | Description |
|------|-------------|
| `browser.py` | Playwright-based web automation with domain controls (DEPRECATED: prefer SDK WebFetch for simple cases) |
| `network.py` | HTTP client with domain allowlist, SSL enforcement, and private IP blocking |

> **SDK Migration Note:** `executor.py` and `fileops.py` were removed. Use SDK tools (Bash, Read, Write, Edit, Glob, Grep, LS) instead.

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
| `backend/routes/transparency.py` | GET/POST /api/transparency — "Show Your Work" mode toggle and reasoning trace retrieval |
| `backend/routes/skills.py` | GET/POST /api/skills — Skill listing, validation, and testing endpoints |

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
| `cli.py` | Main CLI entry point — `dexai setup`, `dexai dashboard`, `dexai doctor`, `dexai skill validate/test/list`, `dexai --version` |

---

## Setup Tools (`tools/setup/`)

| Tool | Description |
|------|-------------|
| `wizard.py` | Core setup state management, channel validation, test messaging, and configuration generation (Phase 8) |
| `setup_core.py` | Core install.sh helper — shared setup functions extracted from install.sh rewrite (prerequisites, env, DB init) |
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
| `tests/unit/voice/test_intent_parser.py` | Voice intent parsing tests (50+ patterns) |
| `tests/unit/voice/test_entity_extractor.py` | Voice entity extraction tests (datetime, duration, priority, energy) |

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
| `draft_manager.py` | Draft creation, approval workflow, sentiment analysis integration (Phase 12b) |
| `sentiment.py` | Email sentiment analysis for ADHD-safe sending (Phase 12b) |
| `sender.py` | Email sending with undo window, sentiment gating, bulk operations (Phase 12c) |

### Calendar Tools (`tools/office/calendar/`)

| Tool | Description |
|------|-------------|
| `reader.py` | Event retrieval, availability checking, free slot finding |
| `scheduler.py` | Meeting proposal, confirmation, time suggestion with conflict checking (Phase 12b) |

### Action Queue Tools (`tools/office/actions/`) — Phase 12c

| Tool | Description |
|------|-------------|
| `__init__.py` | Action types, statuses, priorities, and database index management |
| `queue.py` | Action queue management (queue, cancel, expedite, stats) |
| `validator.py` | Pre-queue validation (level check, rate limits, recipient safety) |
| `undo_manager.py` | Undo window calculation, action undo, window extension |
| `executor.py` | Action execution engine with provider dispatch |
| `audit_logger.py` | Append-only audit logging for all office actions |
| `digest.py` | Daily digest generation for action summaries |

### Automation Tools (`tools/office/automation/`) — Phase 12d

| Tool | Description |
|------|-------------|
| `__init__.py` | Automation module exports and lazy loading |
| `emergency.py` | Emergency pause/resume system for instant automation control |
| `contact_manager.py` | VIP contact management with priority levels |
| `inbox_processor.py` | Automated email processing against policies (Phase 12d) |
| `calendar_guardian.py` | Calendar protection, focus block defense, meeting auto-response (Phase 12d) |
| `auto_responder.py` | Template-based automatic email responses (Phase 12d) |

### Configuration

| File | Description |
|------|-------------|
| `args/office_integration.yaml` | Integration levels, OAuth config, ADHD safeguards, security settings |

### Dashboard Routes (Phase 12b)

| Endpoint | Description |
|----------|-------------|
| `GET /api/office/accounts` | List connected office accounts |
| `GET /api/office/drafts` | List email drafts with filters |
| `POST /api/office/drafts` | Create new draft with sentiment analysis |
| `POST /api/office/drafts/{id}/approve` | Approve draft for sending |
| `GET /api/office/meetings` | List meeting proposals |
| `POST /api/office/meetings` | Propose new meeting with availability check |
| `POST /api/office/meetings/{id}/confirm` | Confirm meeting and send invites |
| `GET /api/office/suggest-times` | Get AI-suggested meeting times |
| `GET /api/oauth/authorize/{provider}` | Get OAuth authorization URL |
| `GET /oauth/google/callback` | Google OAuth callback handler |
| `GET /oauth/microsoft/callback` | Microsoft OAuth callback handler |

---

## Mobile Push Tools (`tools/mobile/`) — Phase 10a/10b

### Core Modules

| Tool | Description |
|------|-------------|
| `__init__.py` | Database schema (subscriptions, queue, preferences), path constants |
| `models.py` | Data models (PushSubscription, Notification, NotificationCategory, DeliveryStatus) |

### Push Delivery (`tools/mobile/push/`)

| Tool | Description |
|------|-------------|
| `web_push.py` | VAPID key generation, Web Push sending via pywebpush, CLI for testing |
| `subscription_manager.py` | Subscription CRUD, stale subscription pruning, device management |
| `delivery.py` | Notification delivery with retry logic, 410 Gone handling, delivery logging |
| `native_tokens.py` | Expo/FCM/APNs token registration and native push sending (Phase 10b) |

### Queue Management (`tools/mobile/queue/`)

| Tool | Description |
|------|-------------|
| `notification_queue.py` | Priority queue for notifications, enqueue/process/cancel operations |
| `batcher.py` | Batch related notifications to reduce interruptions, ADHD-friendly summaries |
| `scheduler.py` | Quiet hours, flow state protection, rate limiting (ADHD-specific 6/hour max) |

### Preferences (`tools/mobile/preferences/`)

| Tool | Description |
|------|-------------|
| `user_preferences.py` | Per-user notification settings, quiet hours, category preferences |
| `category_manager.py` | Notification category definitions, default seeding |

### Analytics (`tools/mobile/analytics/`)

| Tool | Description |
|------|-------------|
| `delivery_tracker.py` | Track sent/delivered/clicked/dismissed events, aggregate statistics |

### Dashboard Routes (Phase 10a/10b)

| Endpoint | Description |
|----------|-------------|
| `GET /api/push/vapid-key` | Get VAPID public key for client subscription |
| `POST /api/push/subscribe` | Register push subscription |
| `DELETE /api/push/subscribe/{id}` | Unsubscribe device |
| `GET /api/push/subscriptions` | List user's subscriptions |
| `POST /api/push/test` | Send test notification |
| `GET /api/push/preferences` | Get notification preferences |
| `PUT /api/push/preferences` | Update preferences |
| `GET /api/push/categories` | List notification categories |
| `PUT /api/push/categories/{id}` | Update category preferences |
| `GET /api/push/history` | Get notification history |
| `GET /api/push/stats` | Get delivery statistics |
| `POST /api/push/track/delivered` | Track notification delivery |
| `POST /api/push/track/clicked` | Track notification click |
| `POST /api/push/track/dismissed` | Track notification dismissal |
| `POST /api/push/native-token` | Register native push token (Expo/FCM/APNs) (Phase 10b) |
| `DELETE /api/push/native-token/{token}` | Unregister native push token (Phase 10b) |
| `GET /api/push/native-tokens` | List user's native tokens (Phase 10b) |
| `POST /api/push/native-test` | Send test notification to native tokens (Phase 10b) |
| `GET /api/push/sync` | Get sync status for background fetch (Phase 10b) |

### Frontend Components (Phase 10a)

| File | Description |
|------|-------------|
| `frontend/public/sw.js` | Service worker for push event handling, click/dismiss tracking |
| `frontend/components/push/PushSubscription.tsx` | Push permission request UI, VAPID key fetch, subscription creation |
| `frontend/app/settings/push/page.tsx` | Push notification settings page (quiet hours, categories, test) |

### Configuration

| File | Description |
|------|-------------|
| `args/mobile_push.yaml` | VAPID config, rate limits, batching, categories, ADHD settings |

---

## Expo Mobile App (`mobile/`) — Phase 10b

Expo React Native wrapper for iOS push notifications and native app experience.

### Configuration Files

| File | Description |
|------|-------------|
| `app.json` | Expo configuration (app name, icons, splash, notification settings) |
| `package.json` | Dependencies (expo, expo-notifications, react-native-webview) |
| `tsconfig.json` | TypeScript configuration with path aliases |
| `babel.config.js` | Babel configuration for Expo |

### App Entry

| File | Description |
|------|-------------|
| `App.tsx` | Main entry point (push init, WebView wrapper, deep linking) |

### Components (`mobile/src/components/`)

| File | Description |
|------|-------------|
| `WebViewContainer.tsx` | WebView wrapper with auth injection, JS bridge, pull-to-refresh, error handling |

### Services (`mobile/src/services/`)

| File | Description |
|------|-------------|
| `push.ts` | Expo push token handling, permission requests, notification listeners |
| `background.ts` | Background fetch task, silent push handling, badge management |

### Utils (`mobile/src/utils/`)

| File | Description |
|------|-------------|
| `bridge.ts` | WebView JS bridge for native-to-web communication |
| `config.ts` | App configuration (API URLs, feature flags, debug settings) |

### Types (`mobile/src/types/`)

| File | Description |
|------|-------------|
| `index.ts` | TypeScript types (NotificationData, BridgeMessage, PushToken, etc.) |

### Assets (`mobile/assets/`)

| File | Description |
|------|-------------|
| `icon.png` | App store icon (placeholder - replace before production) |
| `splash.png` | Splash screen image (placeholder) |
| `adaptive-icon.png` | Android adaptive icon (placeholder) |
| `notification-icon.png` | Android notification icon (placeholder) |
| `README.md` | Asset requirements and design guidelines |

---

## Native Features (`mobile/src/native/`) — Phase 10c

Advanced native mobile features for deeper OS integration.

### Widgets (`mobile/src/native/widgets/`)

| File | Description |
|------|-------------|
| `index.ts` | Widget exports |
| `NextTaskWidget.tsx` | iOS/Android home screen widget showing next task and current step |
| `config.ts` | Widget configuration (sizes, refresh intervals, display options, themes) |

### Watch (`mobile/src/native/watch/`)

| File | Description |
|------|-------------|
| `index.ts` | Watch app exports |
| `WatchConnector.ts` | Apple Watch communication (send tasks, receive actions, complications) |
| `types.ts` | Watch-specific types (WatchMessage, ComplicationData, WatchAppState) |

### Shortcuts (`mobile/src/native/shortcuts/`)

| File | Description |
|------|-------------|
| `index.ts` | Shortcuts exports |
| `SiriShortcuts.ts` | Siri Shortcuts integration (voice commands, activity donation) |
| `QuickActions.ts` | 3D Touch / long press quick actions on app icon |

### Sync (`mobile/src/native/sync/`)

| File | Description |
|------|-------------|
| `index.ts` | Background sync exports |
| `BackgroundSync.ts` | Enhanced background sync service (tasks, preferences, notifications) |
| `OfflineQueue.ts` | Offline action queue with conflict detection and replay |

---

## Native Backend Tools (`tools/mobile/native/`) — Phase 10c

Backend APIs for native mobile features.

| Tool | Description |
|------|-------------|
| `__init__.py` | Module exports and path constants |
| `widget_data.py` | Get data for widgets (next task, current step, energy level, upcoming count) |
| `shortcuts.py` | Handle Siri shortcuts and quick actions, get suggested shortcuts |

### Native API Endpoints (Phase 10c)

| Endpoint | Description |
|----------|-------------|
| `GET /api/mobile/widget-data` | Get data formatted for home screen widget |
| `GET /api/mobile/watch-data` | Get data formatted for Apple Watch |
| `POST /api/mobile/shortcut/{id}` | Handle Siri shortcut invocation |
| `GET /api/mobile/shortcuts/suggested` | Get suggested shortcuts based on patterns |
| `POST /api/mobile/quick-action/{action}` | Handle 3D Touch quick action |

---

## Voice Interface Tools (`tools/voice/`) — Phase 11a/11b/11c

### Core Modules

| Tool | Description |
|------|-------------|
| `__init__.py` | Database schema (voice_commands, preferences, templates), path constants |
| `models.py` | Data models (IntentType, EntityType, TranscriptionResult, ParsedCommand, CommandResult) |

### Recognition (`tools/voice/recognition/`)

| Tool | Description |
|------|-------------|
| `base.py` | Abstract BaseTranscriber interface for all recognition providers |
| `web_speech_config.py` | Web Speech API config and result processing (browser-side recognition) |
| `whisper_adapter.py` | Adapter wrapping Phase 15b AudioProcessor as BaseTranscriber for Whisper API (Phase 11b) |
| `transcriber.py` | TranscriptionCoordinator — provider selection, fallback chain, accuracy logging (Phase 11b) |

### Parser (`tools/voice/parser/`)

| Tool | Description |
|------|-------------|
| `intent_parser.py` | Pattern-matching intent detection from transcribed text (17+ patterns) |
| `entity_extractor.py` | Entity extraction: datetime, duration, priority, energy from natural language |
| `command_router.py` | Route parsed commands to handlers with logging and error handling |

### Commands (`tools/voice/commands/`)

| Tool | Description |
|------|-------------|
| `task_commands.py` | Task voice handlers: add, complete, skip, decompose (via tools/tasks/) |
| `reminder_commands.py` | Reminder voice handlers: set, snooze, cancel (via tools/automation/) |
| `query_commands.py` | Query voice handlers: next task, schedule, status, search |
| `control_commands.py` | Control voice handlers: start/end focus, pause notifications |

### Preferences (`tools/voice/preferences/`)

| Tool | Description |
|------|-------------|
| `user_preferences.py` | Per-user voice settings CRUD, command history retrieval |

### Dashboard Routes (Phase 11a/11b/11c)

| Endpoint | Description |
|----------|-------------|
| `GET /api/voice/status` | Check voice config, available sources, user preferences |
| `POST /api/voice/command` | Submit transcript, parse intent, execute, return result |
| `POST /api/voice/transcribe` | Server-side audio transcription via Whisper API (Phase 11b) |
| `POST /api/voice/tts` | Text-to-speech generation with cloud/browser fallback (Phase 11c) |
| `GET /api/voice/preferences` | Get user voice preferences |
| `PUT /api/voice/preferences` | Update voice preferences |
| `GET /api/voice/history` | Get voice command history |
| `GET /api/voice/commands` | List all available voice commands |

### Frontend Components (Phase 11a/11b/11c)

| File | Description |
|------|-------------|
| `components/voice/use-voice-recognition.ts` | React hook wrapping Web Speech API (Chrome, Edge, Safari) |
| `components/voice/use-audio-recorder.ts` | React hook for MediaRecorder API audio capture (WebM/Opus) (Phase 11b) |
| `components/voice/use-tts.ts` | React hook for browser SpeechSynthesis + cloud TTS playback (Phase 11c) |
| `components/voice/use-audio-feedback.ts` | React hook for Web Audio API tone synthesis (start/stop/success/error) (Phase 11c) |
| `components/voice/voice-button.tsx` | Push-to-talk button with idle/listening/processing/unsupported states |
| `components/voice/transcript-display.tsx` | Live transcript with confidence indicator and intent badge |
| `components/voice/voice-input.tsx` | Composed widget: dual-mode (Web Speech / Whisper), TTS, audio feedback, continuous listening |
| `components/voice/voice-settings.tsx` | Voice settings panel (source, language, TTS, continuous listening, feedback toggles) |

### Configuration

| File | Description |
|------|-------------|
| `args/voice.yaml` | Recognition, transcription, TTS, audio feedback, continuous listening, ADHD settings |

---

## Agent SDK Integration (`tools/agent/`) — SDK Migration

Core integration layer for Claude Agent SDK with DexAI's ADHD features.

### Core Modules

| Tool | Description |
|------|-------------|
| `__init__.py` | Module exports, path constants (PROJECT_ROOT, DATA_DIR, CONFIG_PATH) |
| `skill_tracker.py` | Track skill usage patterns (activations, outcomes, feedback) to generate refinement suggestions |
| `sdk_client.py` | DexAIClient wrapper with ADHD-aware system prompts, intelligent routing, subagent registration, cost tracking, session resumption, structured output |
| `permissions.py` | SDK `can_use_tool` callback with PermissionResult types, AskUserQuestion handling, RBAC integration |
| `system_prompt.py` | SystemPromptBuilder for dynamic system prompt generation from workspace files + runtime context |
| `hooks.py` | SDK lifecycle hooks: security (PreToolUse blocking), audit logging, dashboard recording (PostToolUse), context saving (Stop) |
| `subagents.py` | ADHD-specific subagent definitions (task-decomposer, energy-matcher, commitment-tracker, friction-solver) for SDK agents parameter |
| `schemas.py` | JSON schemas for structured SDK output (task_decomposition, energy_assessment, commitment_list, friction_check, current_step) |
| `model_selector.py` | ModelSelector for subagent model selection: complexity scoring (0-10), heuristic analysis (technical terms, multi-step, codebase refs), agent-specific defaults |
| `workspace_manager.py` | Per-user isolated workspaces with bootstrap files, scope-based lifecycle management, and security boundaries |
| `skill_validator.py` | Skill testing and validation framework — shared core for MCP tools and CLI (syntax, security, execution checks) |
| `sdk_tools.py` | SDK tool wrappers — exposes DexAI MCP tools via `@tool` decorator for the SDK MCP server (memory, task, automation, office, channel, ADHD, skill, dependency) |

### System Prompt Architecture

Dynamic prompt generation inspired by OpenClaw. Templates in `docs/templates/` bootstrap workspace files; at runtime, only workspace files are read.

| Component | Description |
|-----------|-------------|
| `SystemPromptBuilder` | Composes prompts from workspace files + runtime context with session-based filtering |
| `PromptContext` | Runtime context dataclass (user_id, timezone, channel, session_type, prompt_mode) |
| `PromptMode` | Enum for prompt modes: FULL (all sections), MINIMAL (core + safety), NONE (identity line only) |
| `SessionType` | Enum for session types: MAIN (full access), SUBAGENT (task-focused), HEARTBEAT, CRON |
| `SESSION_FILE_ALLOWLISTS` | Per-session-type file access control (security + token efficiency) |
| `bootstrap_workspace()` | Copy templates to workspace root during first-run initialization |
| `is_workspace_bootstrapped()` | Check if PERSONA.md exists at workspace root |

**Session-Based File Filtering (inspired by OpenClaw):**

| Session Type | Files Loaded | Use Case | Token Savings |
|--------------|--------------|----------|---------------|
| `main` | All files | Interactive user sessions | — |
| `subagent` | PERSONA + AGENTS only | Task tool spawns | ~32% |
| `heartbeat` | PERSONA + AGENTS + HEARTBEAT | Proactive check-ins | ~20% |
| `cron` | PERSONA + AGENTS | Scheduled jobs | ~32% |

Subagents don't get USER.md, IDENTITY.md, or ENV.md — they're task-focused and shouldn't have access to personal context.

**Workspace Files (copied from templates):**
- `PERSONA.md` — Core Dex identity and ADHD principles
- `IDENTITY.md` — Name, vibe, personality customizations
- `USER.md` — User profile with ADHD context fields
- `AGENTS.md` — Operational guidelines for sessions
- `ENV.md` — Environment-specific notes (tools, platform, etc.)
- `HEARTBEAT.md` — Proactive check-in configuration
- ~~`BOOTSTRAP.md`~~ — Removed; onboarding is now handled via Direct Chat setup flow

**Configuration:** `args/system_prompt.yaml`

### Model Router (`tools/agent/model_router/`)

Intelligent model routing framework for cost-optimized, complexity-based model selection.

| Tool | Description |
|------|-------------|
| `__init__.py` | Module exports for routing framework |
| `model_router.py` | OpenRouter-first model router with complexity classification, subagent strategies, and YAML config loading |
| `examples.py` | Usage examples for the routing framework |

**Key Features:**
- **Complexity Classification**: Routes trivial tasks to Haiku (73% savings), complex tasks to Sonnet/Opus
- **Multi-Provider Support**: OpenRouter transport for Anthropic, OpenAI, Google, DeepSeek models
- **Subagent Downscaling**: Automatically uses cheaper models for subagent work when parent task is simple
- **Exacto Mode**: Enhanced tool-calling accuracy for complex agentic workloads
- **Observability**: Langfuse OTEL tracing and OpenRouter dashboard integration

**Configuration:** `args/routing.yaml`

### Channel Handler

Channel message handling is provided by `tools/channels/sdk_handler.py` — see Channel Tools section above.

### MCP Tools (`tools/agent/mcp/`)

Custom MCP tools exposing DexAI's unique ADHD features to the SDK agent.

#### Memory MCP Tools

Provider-agnostic memory tools using MemoryService facade. Works with any configured provider (native, Mem0, Zep, SimpleMem, ClaudeMem).

| Tool | Description |
|------|-------------|
| `dexai_memory_search` | Hybrid semantic + keyword search (BM25 + embeddings) |
| `dexai_memory_write` | Write memory with importance score and type classification |
| `dexai_commitments_add` | Track promises/commitments to prevent relationship damage |
| `dexai_commitments_list` | List active commitments with ADHD-friendly framing |
| `dexai_context_capture` | Snapshot context on task switch for working memory |
| `dexai_context_resume` | Generate "you were here..." resumption prompts |

#### Task MCP Tools

| Tool | Description |
|------|-------------|
| `dexai_task_decompose` | Break vague tasks into concrete steps (LLM-powered) |
| `dexai_friction_check` | Identify hidden blockers (passwords, decisions, phone calls) |
| `dexai_friction_solve` | Pre-solve blockers before user hits them |
| `dexai_current_step` | Get ONE next action (not a list!) — core ADHD interface |
| `dexai_energy_match` | Match tasks to current energy level |

#### ADHD Communication MCP Tools

| Tool | Description |
|------|-------------|
| `dexai_format_response` | Apply brevity rules, strip preamble, one-thing mode |
| `dexai_check_language` | Detect and reframe RSD-triggering language |

#### Automation MCP Tools

| Tool | Description |
|------|-------------|
| `dexai_schedule` | Create scheduled jobs (cron, heartbeat, trigger) |
| `dexai_schedule_list` | List scheduled jobs with optional filters |
| `dexai_schedule_manage` | Enable, disable, delete, or run jobs manually |
| `dexai_notify` | Send notification with flow-awareness (suppresses during focus) |
| `dexai_reminder` | Set reminder with natural language time ("in 30 minutes") |
| `dexai_suppressed_count` | Get count of notifications suppressed during flow state |
| `dexai_release_suppressed` | Release suppressed notifications after flow ends |

#### Office MCP Tools

| Tool | Description |
|------|-------------|
| `dexai_email_list` | List emails from inbox with optional filters |
| `dexai_email_read` | Read a single email's full content |
| `dexai_email_draft` | Create email draft with sentiment analysis |
| `dexai_email_send` | Queue email for sending with undo window |
| `dexai_calendar_today` | Get today's calendar events with summary |
| `dexai_calendar_week` | Get this week's calendar events |
| `dexai_calendar_propose` | Propose meeting (requires confirmation to create) |
| `dexai_calendar_availability` | Find available meeting time slots |

#### Skill MCP Tools

| Tool | Description |
|------|-------------|
| `dexai_validate_skill` | Validate a skill file (syntax, security, metadata checks) |
| `dexai_test_skill` | Run a skill in a sandboxed environment and return results |
| `dexai_list_skills` | List all installed skills with version and validation status |

#### Channel MCP Tools

| Tool | Description |
|------|-------------|
| `dexai_channel_pair` | Complete channel pairing with a pairing code (natural language: "pair my telegram with code 12345") |

### Workspace Isolation

Per-user isolated workspaces provide security through separation. Each user+channel combination gets a dedicated directory.

| Component | Description |
|-----------|-------------|
| `WorkspaceManager` | Create, get, delete, and cleanup workspaces |
| `WorkspaceScope` | Lifecycle control: SESSION (ephemeral), PERSISTENT (stale-cleaned), PERMANENT |
| `WorkspaceAccess` | Access level: NONE, RO (read-only), RW (read-write) |

**Security Model (Defense in Depth):**
1. SDK Sandbox — Container isolation, cwd enforcement
2. PreToolUse Hooks — Block dangerous bash, protected paths, path traversal
3. RBAC System — Tool permissions per user role
4. Workspace Isolation — Per-user directories, scope policies

**Configuration:** `args/workspace.yaml`

### Configuration

| File | Description |
|------|-------------|
| `args/agent.yaml` | Agent configuration (model, tools, system prompt, ADHD settings, security mapping) |
| `args/workspace.yaml` | Workspace isolation settings (scope, cleanup, restrictions) |

### Removed Modules (SDK Migration)

The following modules were removed as they are now provided by the Claude Agent SDK:

| Removed File | Replacement |
|--------------|-------------|
| `tools/system/fileops.py` | SDK tools: Read, Write, Edit, Glob, Grep, LS |
| `tools/system/executor.py` | SDK tool: Bash (with sandboxing) |

Note: `tools/system/browser.py` is deprecated but retained for advanced features (screenshots, PDFs) that WebFetch doesn't support.

---

## Deployment Infrastructure

### Root Files

| File | Description |
|------|-------------|
| `install.sh` | One-line installation script with prerequisites check, dependency install, and DB init |
| `Makefile` | Build automation (install, dev, test, lint, build, deploy, clean, status) |
| `Caddyfile` | Reverse proxy configuration with automatic HTTPS via Caddy |
| `docker-compose.yml` | Multi-service Docker deployment (backend, frontend, caddy, tailscale) |
| `.env.example` | Environment variable template with all configuration options |

### Systemd Services (`deploy/systemd/`)

| File | Description |
|------|-------------|
| `dexai.service` | Main service (Docker Compose mode) with security hardening |
| `dexai-backend.service` | Standalone backend service (no Docker) with resource limits |
| `dexai-channels.service` | Channel adapters service with auto-restart on failure |

### Tailscale Integration (`deploy/tailscale/`)

| File | Description |
|------|-------------|
| `README.md` | Tailscale setup guide (auth key, ACLs, MagicDNS, Funnel) |
| `tailscale-serve.json` | Tailscale Serve configuration for automatic HTTPS |

### Documentation (`docs/`)

| File | Description |
|------|-------------|
| `HARDENING.md` | Security hardening guide (system, AI, gateway, client, monitoring) |
| `RUNBOOK.md` | Operational runbooks for 9 incident/maintenance scenarios (alerts, recovery, rotation, backup) |

---

*Update this manifest when adding new tools.*
