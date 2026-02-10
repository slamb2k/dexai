# Phase 11: Voice Interface — Tactical Implementation Guide

**Status:** Phase 11a Complete
**Depends on:** Phase 0 (Security), Phase 5 (Task Engine), Phase 7 (Dashboard), Phase 10 (Mobile Push), Phase 15b (Audio/TTS)
**Last Updated:** 2026-02-10

---

## Overview

Phase 11 adds voice interaction capabilities to DexAI, enabling hands-free task capture, queries, and control. For ADHD users, voice input dramatically reduces the friction between having a thought and capturing it — no app switching, no typing, no losing the thought while fumbling with a keyboard.

**Key Philosophy:** Voice is not a replacement for text; it's a **low-friction capture mechanism** for moments when typing isn't practical. The goal is to get thoughts out of the ADHD brain and into the system before they evaporate.

**ADHD-Specific Design:**
- **Quick capture when hands are busy:** "Dex, remind me to call mom tomorrow"
- **Reduce friction:** Voice is faster than typing for ADHD brains in motion
- **Confirmation without interruption:** Gentle audio feedback, no screen required
- **Ambient listening opt-in only:** Respect privacy, default to push-to-talk

---

## Architecture Decision: Progressive Enhancement

Rather than building a complex voice system immediately, we use a **progressive enhancement** approach:

| Phase | Approach | Features | Cost |
|-------|----------|----------|------|
| **11a** | Web Speech API | Browser-based STT, push-to-talk | Free |
| **11b** | Whisper Integration | Higher accuracy, server-side fallback | API credits |
| **11c** | Advanced Features | Wake word, TTS responses, mobile integration | Medium |

**Rationale:** Web Speech API provides a zero-cost MVP that works in Chrome, Edge, and Safari. Whisper API adds accuracy for users who need it. Wake word detection and TTS are power-user features added last.

---

## What Phase 15b Already Provides (Reuse, Don't Rebuild)

Phase 15b (completed 2026-02-10) built the audio/TTS infrastructure that Phase 11 should leverage:

| Component | Location | What It Does |
|-----------|----------|-------------|
| `AudioProcessor` | `tools/channels/audio_processor.py` | Whisper API transcription (10+ formats, cost tracking, 5min max) |
| `TTSGenerator` | `tools/channels/tts_generator.py` | OpenAI TTS (6 voices, opus/mp3/wav, channel-optimized) |
| `VideoProcessor` | `tools/channels/video_processor.py` | Audio extraction from video, frame analysis |
| `MediaProcessor` | `tools/channels/media_processor.py` | Orchestrates audio/video/image processing |
| Config | `args/multimodal.yaml` | Whisper model, TTS voice/format/speed, cost limits |

**Phase 11 builds ON Phase 15b, not alongside it.** The voice interface adds:
- Browser-side voice capture (Web Speech API)
- Voice command parsing (intent + entity extraction)
- Command routing to existing task/reminder/query systems
- Voice-specific UI components
- Server-side transcription fallback via existing `AudioProcessor`
- TTS responses via existing `TTSGenerator`

---

## Sub-Phases

| Sub-Phase | Focus | Status | Est. Effort |
|-----------|-------|--------|-------------|
| **11a** | Browser Voice + Push-to-Talk + Command Parsing | Complete | 4-5 days |
| **11b** | Whisper Server Fallback + Accuracy Enhancement | Planned | 2-3 days |
| **11c** | Wake Word + TTS Responses + Mobile Voice | Planned | 3-4 days |

**Total estimated:** 9-12 days

---

## Phase 11a: Browser Voice + Push-to-Talk

### Objective

Implement voice input in the dashboard using the Web Speech API, providing zero-cost voice capture for Chrome, Edge, and Safari users with a simple push-to-talk interface. This phase includes the full command parsing pipeline — the voice button should actually do things, not just transcribe.

### Integration Points (Current Architecture)

**Frontend (Next.js 14.2 + Zustand + Tailwind):**
- `components/quick-chat.tsx` — Has disabled mic button (`<Mic>` icon, title="Voice input coming soon")
- `lib/api.ts` — `streamChatMessage()` WebSocket streaming to backend
- `lib/store.ts` — Zustand stores (DexStore, ActivityStore, MetricsStore)
- `lib/socket.ts` — Socket.io for real-time state updates

**Backend (FastAPI):**
- `routes/chat.py` — REST + WebSocket chat endpoints
- `services/chat_service.py` — ChatService with streaming via SessionManager
- `backend/websocket.py` — WebSocket manager for broadcasting

**Existing systems to connect voice commands to:**
- Task system: `tools/tasks/` — create, complete, skip, decompose
- Memory system: `tools/memory/` — search, commitments
- Notification system: `tools/notifications/` — flow state, reminders
- Energy tracking: `tools/learning/` — energy patterns

### Directory Structure

```
tools/voice/
├── __init__.py                     # Path constants, DB connection, shared utilities
├── models.py                       # VoiceCommand, Intent, Entity, TranscriptionResult
│
├── recognition/
│   ├── __init__.py
│   ├── base.py                     # Abstract Transcriber interface
│   └── web_speech_config.py        # Web Speech API config + result processing
│
├── parser/
│   ├── __init__.py
│   ├── intent_parser.py            # Extract intents from transcribed text
│   ├── entity_extractor.py         # Extract entities (dates, tasks, people, etc.)
│   └── command_router.py           # Route parsed commands to handlers
│
├── commands/
│   ├── __init__.py
│   ├── task_commands.py            # Task-related voice commands
│   ├── reminder_commands.py        # Reminder commands
│   ├── query_commands.py           # Questions about tasks, schedule, status
│   └── control_commands.py         # System control (focus mode, navigation)
│
└── preferences/
    ├── __init__.py
    └── user_preferences.py         # Voice settings per user
```

### Database Schema

```sql
-- data/voice.db

-- Voice command history (for learning and debugging)
CREATE TABLE IF NOT EXISTS voice_commands (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,

    -- Transcription
    transcript TEXT NOT NULL,
    confidence REAL,                  -- Recognition confidence (0-1)
    source TEXT DEFAULT 'web_speech', -- 'web_speech', 'whisper_api', 'whisper_local'
    audio_duration_ms INTEGER,

    -- Parsing
    intent TEXT,                      -- Detected intent (add_task, query_next, etc.)
    entities TEXT,                    -- JSON: extracted entities
    parsed_successfully BOOLEAN DEFAULT TRUE,

    -- Execution
    handler TEXT,                     -- Which command handler processed it
    result TEXT,                      -- JSON: command result
    executed_successfully BOOLEAN,
    error_message TEXT,

    -- Timing
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    transcription_time_ms INTEGER,
    parsing_time_ms INTEGER,
    execution_time_ms INTEGER
);

-- Voice preferences per user
CREATE TABLE IF NOT EXISTS voice_preferences (
    user_id TEXT PRIMARY KEY,

    -- Recognition settings
    enabled BOOLEAN DEFAULT TRUE,
    preferred_source TEXT DEFAULT 'web_speech',
    language TEXT DEFAULT 'en-US',
    continuous_listening BOOLEAN DEFAULT FALSE,  -- Phase 11c
    wake_word_enabled BOOLEAN DEFAULT FALSE,     -- Phase 11c

    -- Feedback settings
    audio_feedback_enabled BOOLEAN DEFAULT TRUE,
    visual_feedback_enabled BOOLEAN DEFAULT TRUE,
    confirmation_verbosity TEXT DEFAULT 'brief', -- 'silent', 'brief', 'verbose'
    tts_enabled BOOLEAN DEFAULT FALSE,           -- Phase 11c
    tts_voice TEXT DEFAULT 'alloy',              -- Matches multimodal.yaml voices
    tts_speed REAL DEFAULT 1.0,

    -- ADHD settings
    auto_execute_high_confidence BOOLEAN DEFAULT TRUE,
    confidence_threshold REAL DEFAULT 0.85,
    repeat_on_low_confidence BOOLEAN DEFAULT TRUE,

    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Voice command templates (for learning patterns)
CREATE TABLE IF NOT EXISTS voice_command_templates (
    id TEXT PRIMARY KEY,
    intent TEXT NOT NULL,
    template_pattern TEXT NOT NULL,
    example_phrases TEXT,            -- JSON array of example phrases
    priority INTEGER DEFAULT 5,
    user_id TEXT,                    -- NULL = global, otherwise user-specific
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_voice_commands_user ON voice_commands(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_voice_commands_intent ON voice_commands(intent);
CREATE INDEX IF NOT EXISTS idx_voice_templates_intent ON voice_command_templates(intent, priority);
```

### Implementation Order (Phase 11a)

#### Step 1: Backend Foundation (tools/voice/)

**1.1 `tools/voice/__init__.py`** — DB connection, path constants
- SQLite connection to `data/voice.db`
- Table creation on first connection
- Path constants: `PROJECT_ROOT`, `DB_PATH`, `CONFIG_PATH`

**1.2 `tools/voice/models.py`** — Data models
- `IntentType` enum: add_task, complete_task, skip_task, set_reminder, query_next_task, query_schedule, query_status, start_focus, end_focus, help, cancel, undo, unknown
- `EntityType` enum: task_description, datetime, duration, person, priority, energy_level, task_reference
- `Entity`, `TranscriptionResult`, `ParsedCommand`, `CommandResult` dataclasses

**1.3 `tools/voice/recognition/base.py`** — Abstract transcriber interface
- `BaseTranscriber` ABC with `transcribe()` and `transcribe_stream()` methods

**1.4 `tools/voice/recognition/web_speech_config.py`** — Web Speech API config
- `WebSpeechConfig` dataclass (language, continuous, interim_results, max_alternatives)
- `process_web_speech_result()` — Convert client-side result dict to `TranscriptionResult`
- No client-side JS here — that lives in the React component

**1.5 `tools/voice/parser/intent_parser.py`** — Intent extraction
- Pattern-matching with priority-sorted regex patterns
- Covers: task CRUD, reminders, queries, focus control, meta commands
- `parse_intent()` → (IntentType, confidence, captured_groups)
- `parse_command()` → `ParsedCommand` with entities and confirmation logic
- `seed_default_templates()` for database

**1.6 `tools/voice/parser/entity_extractor.py`** — Entity extraction
- `extract_entities()` — orchestrate extraction by type
- `extract_datetime_entities()` — "today", "tomorrow", "in 2 hours", "at 3pm"
- `extract_duration_entities()` — "for 30 minutes", "2 hours"
- `extract_priority_entity()` — "high priority", "urgent"
- `extract_energy_entity()` — "low energy", "I'm tired"

**1.7 `tools/voice/parser/command_router.py`** — Route to handlers
- `CommandRouter` class with handler registration
- `route_command()` — dispatch to appropriate handler
- Command logging to `voice_commands` table
- Error handling with ADHD-friendly messages

**1.8 `tools/voice/commands/task_commands.py`** — Task handler
- `handle_add_task()` — Creates task via task system
- `handle_complete_task()` — Marks current task done
- `handle_skip_task()` — Skips to next task
- `handle_decompose_task()` — Triggers task decomposition subagent

**1.9 `tools/voice/commands/reminder_commands.py`** — Reminder handler
- `handle_set_reminder()` — Schedule notification
- `handle_snooze_reminder()` — Snooze current reminder
- `handle_cancel_reminder()` — Cancel reminder

**1.10 `tools/voice/commands/query_commands.py`** — Query handler
- `handle_query_next_task()` — Returns next task based on energy
- `handle_query_schedule()` — Returns today's schedule
- `handle_query_status()` — Returns progress summary
- `handle_query_search()` — Searches memory/tasks

**1.11 `tools/voice/commands/control_commands.py`** — Control handler
- `handle_start_focus()` — Enter focus mode, pause notifications
- `handle_end_focus()` — Exit focus mode
- `handle_pause_notifications()` — Temporary notification pause

**1.12 `tools/voice/preferences/user_preferences.py`** — User settings
- `get_preferences()` / `update_preferences()` — CRUD on voice_preferences table
- `set_voice_source()` — Switch between web_speech/whisper_api/whisper_local
- `set_language()` — Set recognition language
- `get_command_history()` — Retrieve past commands

#### Step 2: Dashboard API Routes

**2.1 `tools/dashboard/backend/routes/voice.py`** — Voice API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/voice/status` | Check if voice is enabled, get config |
| POST | `/api/voice/command` | Receive transcript, parse intent, execute, return result |
| GET | `/api/voice/preferences` | Get user voice preferences |
| PUT | `/api/voice/preferences` | Update voice preferences |
| GET | `/api/voice/history` | Get voice command history |
| GET | `/api/voice/commands` | List available voice commands |

**Key endpoint: `POST /api/voice/command`**
```
Input:  { transcript, confidence, source, language, duration_ms, alternatives? }
Flow:   parse_command() → route_command() → log_command()
Output: { success, message, intent, data?, follow_up_prompt?, undo_available? }
```

**2.2 Register routes in `backend/main.py`**
- Import and include voice router with `/api/voice` prefix

#### Step 3: Frontend Components

**3.1 `components/voice/use-voice-recognition.ts`** — React hook
- Wraps Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`)
- State: `isListening`, `transcript`, `interimTranscript`, `confidence`, `isSupported`, `error`
- Methods: `startListening()`, `stopListening()`, `resetTranscript()`
- Auto-detects browser support
- Handles permission requests gracefully

**3.2 `components/voice/voice-button.tsx`** — Push-to-talk button
- Three visual states: idle (grey mic), listening (pulsing green), processing (spinning)
- Large tap target (min 44x44px) for ADHD accessibility
- Hold-to-talk or click-to-toggle modes
- Animated microphone icon with pulsing border when listening
- Keyboard shortcut: `V` key for quick capture (configurable)

**3.3 `components/voice/transcript-display.tsx`** — Live feedback
- Shows interim transcript as user speaks (lighter text, italic)
- Final transcript in normal weight
- Confidence indicator (color-coded: green >0.85, yellow >0.6, red <0.6)
- Detected intent badge
- Processing spinner during command execution

**3.4 `components/voice/voice-input.tsx`** — Composed voice widget
- Combines VoiceButton + TranscriptDisplay
- Handles the full flow: listen → transcribe → display → confirm? → execute → feedback
- Confirmation dialog for destructive/low-confidence commands
- Result feedback (success/error message with auto-dismiss)
- Can be used standalone or embedded in QuickChat

**3.5 Update `components/quick-chat.tsx`** — Enable the mic button
- Replace disabled `<Mic>` button with `<VoiceInput>` component
- When voice result is a command: execute via `/api/voice/command`
- When voice result is free-form text: insert into chat input for sending as message
- Show transcript in input field before sending

**3.6 `components/voice/voice-settings.tsx`** — Settings panel
- Language selector
- Recognition source selector (web_speech only in 11a)
- Confidence threshold slider
- Auto-execute toggle
- Audio feedback toggle
- Add to existing Settings page

#### Step 4: Configuration

**4.1 `args/voice.yaml`** — Voice config
```yaml
recognition:
  default_provider: "web_speech"
  web_speech:
    language: "en-US"
    continuous: false
    interim_results: true
    max_alternatives: 3

parsing:
  high_confidence: 0.85
  medium_confidence: 0.6
  low_confidence: 0.3
  auto_execute_intents: [query_next_task, query_status, help]
  confirm_intents: [complete_task, skip_task, undo]

feedback:
  visual:
    show_transcript: true
    show_confidence: true
    show_intent_badge: true
    processing_spinner: true

adhd:
  auto_execute_high_confidence: true
  quick_capture_hotkey: "v"
  repeat_on_low_confidence: true
  suggest_on_unknown_intent: true
  max_retries: 2
  helpful_error_messages: true

debug:
  log_all_transcriptions: true
  log_parsing_details: true
```

#### Step 5: Integration Testing

- End-to-end voice flow: button → transcript → parse → execute → feedback
- Command recognition accuracy across all intents
- Entity extraction (dates, durations, priorities)
- Confirmation flow for destructive commands
- Error handling (unsupported browser, permission denied, no speech detected)
- Keyboard shortcut (V key) activation
- Mobile browser support (iOS Safari, Android Chrome)

### Verification Checklist (Phase 11a)

#### Backend
- [ ] `tools/voice/__init__.py` — DB tables created, connections work
- [ ] `tools/voice/models.py` — All data models defined
- [ ] Intent parser recognizes all 17+ command patterns
- [ ] Entity extractor handles dates, durations, priorities, energy
- [ ] Command router dispatches to correct handler
- [ ] Task commands create/complete/skip tasks via task system
- [ ] Reminder commands schedule notifications
- [ ] Query commands return correct data
- [ ] Control commands toggle focus mode
- [ ] Voice preferences persist to DB
- [ ] Command history logged to `voice_commands` table
- [ ] API routes registered and responding

#### Frontend
- [ ] `useVoiceRecognition` hook works in Chrome, Edge, Safari
- [ ] Voice button renders with correct visual states
- [ ] Transcript displays in real-time (interim + final)
- [ ] Confidence indicator shows color-coded feedback
- [ ] Intent badge shows detected command type
- [ ] Confirmation dialog appears for destructive commands
- [ ] Result feedback shows success/error with auto-dismiss
- [ ] Mic button enabled in QuickChat (replaces disabled placeholder)
- [ ] V key shortcut activates voice
- [ ] Graceful fallback for unsupported browsers
- [ ] Voice settings panel works

#### ADHD-Specific
- [ ] Single-button capture (no menus, no navigation)
- [ ] Sub-3-second capture time (thought → stored task)
- [ ] Unknown commands get helpful suggestions, not error messages
- [ ] Cancel always available during any step
- [ ] Undo works for completed actions
- [ ] Visual feedback immediate (<200ms)
- [ ] No guilt/shame language in any response

---

## Phase 11b: Whisper Server Fallback + Accuracy Enhancement

### Objective

Add server-side transcription via the **existing** `AudioProcessor` from Phase 15b, giving users a higher-accuracy fallback when Web Speech API isn't available or underperforms. Also add accuracy comparison logging to help users choose the best provider.

### Key Principle: Reuse Phase 15b Infrastructure

Phase 15b already built `tools/channels/audio_processor.py` with:
- Whisper API transcription (10+ audio formats)
- Cost tracking ($0.006/minute)
- File size limits (25MB)
- Duration limits (configurable, default 5min)
- Error handling and format validation

**Phase 11b wraps this existing infrastructure**, adding:
1. A `BaseTranscriber`-compatible adapter around `AudioProcessor`
2. Audio recording in the browser (MediaRecorder API → WebM/Opus)
3. A server-side transcription endpoint
4. A `TranscriptionCoordinator` for provider selection + fallback
5. Accuracy comparison logging

### New/Modified Components

#### 2.1 `tools/voice/recognition/whisper_adapter.py` — Adapter around AudioProcessor

```python
"""Adapter wrapping Phase 15b AudioProcessor as a BaseTranscriber."""

from tools.voice.recognition.base import BaseTranscriber
from tools.voice.models import TranscriptionResult
from tools.channels.audio_processor import AudioProcessor


class WhisperAPIAdapter(BaseTranscriber):
    """
    Wraps AudioProcessor.transcribe() to conform to BaseTranscriber interface.
    Reuses Phase 15b infrastructure — no duplicate Whisper code.
    """

    def __init__(self):
        self._processor = AudioProcessor()

    @property
    def name(self) -> str:
        return "whisper_api"

    @property
    def is_available(self) -> bool:
        import os
        return bool(os.environ.get("OPENAI_API_KEY"))

    @property
    def supports_streaming(self) -> bool:
        return False

    async def transcribe(self, audio_data, language="en", **kwargs):
        result = await self._processor.transcribe(audio_data, "audio.webm")
        return TranscriptionResult(
            transcript=result.text,
            confidence=0.95,  # Whisper is high-accuracy
            source="whisper_api",
            language=result.language or language,
            duration_ms=int((result.duration_seconds or 0) * 1000),
            is_final=True,
            alternatives=[]
        )

    async def transcribe_stream(self, audio_stream, language="en", **kwargs):
        raise NotImplementedError("Whisper API does not support streaming")
```

#### 2.2 `tools/voice/recognition/whisper_local.py` — Local Whisper (optional)

For privacy-sensitive users who want on-device transcription:
- Uses `openai-whisper` Python package
- Lazy model loading (base model by default)
- CPU/CUDA auto-detection
- No audio leaves the device

#### 2.3 `tools/voice/recognition/transcriber.py` — Provider coordinator

```python
"""Coordinates transcription providers with fallback chain."""

class TranscriptionCoordinator:
    """
    Selects best available provider, falls back on failure.
    Priority: user_preference → whisper_api → whisper_local → web_speech
    """
    def __init__(self, preferred_source="web_speech"):
        ...

    async def transcribe(self, audio_data, source=None, language="en-US"):
        # Try preferred, fall back through chain
        ...

    def available_providers(self) -> list[str]:
        # Always includes "web_speech" (browser-side)
        ...
```

#### 2.4 `tools/voice/recognition/audio_utils.py` — Audio preprocessing

- `convert_to_wav()` — Format conversion via pydub
- `chunk_audio()` — Split long audio with overlap for long-form transcription
- `detect_silence()` — Find silent segments
- `get_audio_duration_ms()` — Duration check

#### 2.5 Frontend: Audio recording hook

**`components/voice/use-audio-recorder.ts`** — MediaRecorder hook
- Records audio via `navigator.mediaDevices.getUserMedia()`
- Outputs WebM/Opus (best for Whisper API)
- Provides `startRecording()`, `stopRecording()`, `audioBlob`
- Handles permissions and error states
- Used when provider is set to `whisper_api` instead of `web_speech`

#### 2.6 Backend: Transcription endpoint

**`POST /api/voice/transcribe`** — Server-side transcription
```
Input:  multipart/form-data with audio file
Flow:   AudioProcessor.transcribe() → TranscriptionResult
Output: { transcript, confidence, language, duration_ms, cost_usd }
```

#### 2.7 Accuracy comparison logging

- Log both Web Speech and Whisper results when both available
- Store in `voice_commands` table with separate confidence scores
- Dashboard can show accuracy comparison over time
- Helps users decide which provider to use

### Dependencies (Phase 11b)

```
# Already installed (Phase 15b):
openai>=1.0.0          # Whisper API via AudioProcessor

# New (optional for local Whisper):
openai-whisper>=20231117
torch>=2.0.0
pydub>=0.25.0          # Audio format conversion
```

### Verification Checklist (Phase 11b)

- [ ] `WhisperAPIAdapter` wraps `AudioProcessor` correctly
- [ ] Server-side transcription endpoint works with WebM audio
- [ ] `TranscriptionCoordinator` selects best provider
- [ ] Fallback chain works when preferred provider fails
- [ ] Audio recording hook captures clean WebM/Opus audio
- [ ] Cost tracking shows per-transcription cost
- [ ] Accuracy comparison logged when both providers available
- [ ] User can switch provider in voice settings
- [ ] Local Whisper works when installed (optional)
- [ ] No duplicate Whisper code — all routes through `AudioProcessor`

---

## Phase 11c: Wake Word + TTS Responses + Mobile Voice

### Objective

Add power-user features: wake word detection ("Hey Dex"), text-to-speech responses using the **existing** `TTSGenerator` from Phase 15b, and mobile voice integration via the Expo app.

### Key Principle: Reuse Phase 15b TTS

Phase 15b already built `tools/channels/tts_generator.py` with:
- OpenAI TTS (tts-1 / tts-1-hd models)
- 6 voices: alloy, echo, fable, onyx, nova, shimmer
- Output formats: opus, mp3, aac, flac, wav, pcm
- Speed control (0.25x - 4.0x)
- Cost tracking ($0.015/1K chars standard, $0.030/1K chars HD)
- Channel-optimized output format selection

**Phase 11c adds:**
1. Browser-side TTS via Web Speech Synthesis API (free, instant)
2. High-quality TTS via existing `TTSGenerator` (API cost, better quality)
3. Wake word detection for hands-free activation
4. Mobile voice integration via Expo WebView bridge

### New/Modified Components

#### 3.1 Wake Word Detection

**`tools/voice/recognition/wake_word.py`**
- Uses Porcupine (pvporcupine) for on-device wake word detection
- Privacy-first: All wake word processing happens locally
- No audio sent to servers until wake word is detected
- Configurable: phrase ("Hey Dex"), sensitivity (0.0-1.0)
- Browser implementation via AudioWorklet for low-latency processing

**`components/voice/use-wake-word.ts`** — Frontend hook
- Uses AudioWorklet API for background mic monitoring
- Triggers voice recognition when wake word detected
- Visual indicator when wake word listening is active
- Toggle on/off from voice settings

#### 3.2 TTS Responses

**`tools/voice/feedback/tts_service.py`** — TTS orchestrator
```python
"""
TTS service that routes between:
1. Browser Speech Synthesis API (free, instant, lower quality)
2. TTSGenerator from Phase 15b (API cost, high quality)

Selection based on user preference and response importance.
"""

class VoiceTTSService:
    def __init__(self):
        from tools.channels.tts_generator import TTSGenerator
        self._cloud_tts = TTSGenerator()

    async def generate_response(self, text, user_prefs):
        if user_prefs.get("tts_source") == "browser":
            # Return config for browser-side SpeechSynthesis
            return {"type": "browser_tts", "text": text, ...}
        else:
            # Generate via TTSGenerator, return audio bytes
            result = await self._cloud_tts.generate_speech(text, ...)
            return {"type": "audio", "data": result.audio_bytes, ...}
```

**`components/voice/use-tts.ts`** — Frontend TTS hook
- Browser Speech Synthesis API for free, instant responses
- Audio playback for cloud-generated TTS
- Interruptible: any user input cancels TTS
- Speed/voice controls
- Queue management for multiple responses

**`tools/voice/feedback/audio_feedback.py`** — Confirmation sounds
- Short audio cues: listening start (boop), success (chime), error (buzz)
- Uses pre-generated audio files (no API cost)
- Configurable: enable/disable, volume

#### 3.3 TTS Response Formatting

Not every response should be spoken. Rules:
- **Speak:** Confirmations ("Task added"), brief answers ("Your next task is...")
- **Don't speak:** Long lists, code blocks, complex data
- **Truncate:** Cap TTS at ~100 words, offer "read more" for longer responses
- **ADHD-friendly:** Single sentences, no filler words, direct answers

#### 3.4 Mobile Voice Integration

**Expo App Changes (`tools/dashboard/mobile/`):**
- Add voice button overlay to WebView
- Handle native microphone permissions (iOS/Android)
- Use React Native Voice (`@react-native-voice/voice`) for native STT
- Bridge voice results to web dashboard via `postMessage`
- Native haptic feedback on voice events

**Voice Message Bridge:**
```
Mobile App → Native STT → postMessage → WebView → /api/voice/command
Mobile App ← Audio Playback ← TTS Response ← WebView ← API Response
```

#### 3.5 Continuous Listening Mode

- Opt-in only (default: off, requires explicit user activation)
- Uses wake word detection as gate
- Auto-timeout after 30 seconds of silence
- Visual indicator always visible when active
- Privacy warning on first enable
- Configurable auto-off timer (default: 5 minutes)

### Configuration Updates

Add to `args/voice.yaml`:
```yaml
# Phase 11c additions
wake_word:
  enabled: false
  phrase: "Hey Dex"
  sensitivity: 0.5
  on_device: true

tts:
  enabled: false
  source: "browser"       # 'browser' (free) or 'cloud' (TTSGenerator)
  voice: "alloy"           # For cloud TTS
  speed: 1.0
  max_words: 100           # Truncate long responses
  confirm_actions: true    # Speak "Task added" etc.
  read_results: false      # Speak query results

continuous_listening:
  enabled: false
  timeout_seconds: 30
  auto_off_minutes: 5
```

### Dependencies (Phase 11c)

```
# Wake word detection
pvporcupine>=3.0.0        # On-device wake word

# Already available (Phase 15b):
# TTSGenerator uses openai for cloud TTS

# Mobile (Expo):
@react-native-voice/voice  # Native STT for iOS/Android
```

### Verification Checklist (Phase 11c)

#### Wake Word
- [ ] Wake word detector works in Chrome/Edge (AudioWorklet)
- [ ] No audio sent to server during wake word listening
- [ ] Sensitivity configurable (0.0-1.0)
- [ ] Visual indicator shows when wake word listening is active
- [ ] Wake word triggers voice recognition correctly

#### TTS
- [ ] Browser Speech Synthesis works (free TTS)
- [ ] Cloud TTS works via existing `TTSGenerator`
- [ ] User can choose between browser/cloud TTS
- [ ] TTS is interruptible by user input
- [ ] Long responses truncated (max ~100 words)
- [ ] Speed/voice controls work
- [ ] Confirmation sounds play on events

#### Mobile
- [ ] Voice button renders in Expo WebView overlay
- [ ] Native microphone permissions handled (iOS + Android)
- [ ] Native STT results bridge to web dashboard
- [ ] TTS audio plays through native audio
- [ ] Haptic feedback on voice events

#### Continuous Listening
- [ ] Opt-in only (explicit user activation required)
- [ ] Privacy warning on first enable
- [ ] Auto-timeout after configured silence period
- [ ] Visual indicator always visible when active
- [ ] Auto-off timer works

---

## Supported Voice Commands

| Category | Command Examples | Intent |
|----------|------------------|--------|
| **Add Task** | "Add task: buy groceries" | add_task |
| | "Remind me to call mom" | add_task |
| | "I need to email John" | add_task |
| **Complete** | "Done" / "Finished" | complete_task |
| | "Mark as complete" | complete_task |
| **Skip** | "Skip task" / "Next task" | skip_task |
| | "Move on" | skip_task |
| **Query** | "What's my next task?" | query_next_task |
| | "What's on my calendar?" | query_schedule |
| | "How am I doing?" | query_status |
| | "Search for [keyword]" | query_search |
| **Reminders** | "Remind me to [action] [time]" | set_reminder |
| | "Snooze" / "Snooze for 10 min" | snooze_reminder |
| **Focus** | "Start focus mode" | start_focus |
| | "End focus mode" / "Resume" | end_focus |
| | "Do not disturb" | start_focus |
| **Control** | "Pause notifications" | pause_notifications |
| | "Quiet mode" | pause_notifications |
| **Meta** | "Help" / "What can I say?" | help |
| | "Cancel" / "Never mind" | cancel |
| | "Undo" | undo |

---

## ADHD-Specific Design Principles

### Voice Capture Philosophy

| Principle | Implementation |
|-----------|----------------|
| **Quick capture** | Push-to-talk with single button, no menu navigation |
| **Don't lose the thought** | Show transcript immediately, even if not understood |
| **Forgiveness** | "Cancel" always available, undo for completed actions |
| **No punishment** | Unknown commands get helpful suggestions, not errors |

### Feedback Design

| Principle | Implementation |
|-----------|----------------|
| **Immediate confirmation** | Visual + optional audio feedback within 200ms |
| **Brief responses** | Voice responses are single sentences |
| **No interruption** | TTS is interruptible by any user input |
| **Clear state** | Always obvious whether system is listening or not |

### Error Handling

| Principle | Implementation |
|-----------|----------------|
| **Assume good intent** | Low-confidence parses suggest closest match |
| **Offer alternatives** | "Did you mean: [option]?" |
| **Easy retry** | "Try again" button always visible |
| **Preserve input** | Original transcript always available |

---

## Dependencies Summary

### Python Packages

```
# Phase 11a (no new packages needed - uses Web Speech API in browser)

# Phase 11b
pydub>=0.25.0               # Audio format conversion
# openai already installed   # Whisper API via existing AudioProcessor
# openai-whisper (optional)  # Local Whisper model
# torch (optional)           # For local Whisper GPU support

# Phase 11c
pvporcupine>=3.0.0          # On-device wake word detection
```

### Frontend Packages

```json
{
  "Phase 11a": "No new deps — Web Speech API is native",
  "Phase 11b": "No new deps — MediaRecorder API is native",
  "Phase 11c": {
    "@react-native-voice/voice": "^3.0.0"  // Mobile only (Expo)
  }
}
```

---

## Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Microphone access** | Requires explicit browser permission, revocable at any time |
| **Audio storage** | Transcripts stored, raw audio discarded immediately after transcription |
| **Wake word privacy** | On-device processing only, no cloud for detection |
| **Sensitive data** | Warning about shared spaces; no audio in logs |
| **API keys** | Whisper/TTS API keys in vault, never exposed to client |
| **Command injection** | Voice transcripts sanitized via existing `sanitizer.py` before parsing |
| **Cost control** | Per-transcription cost tracked, budget limits from `multimodal.yaml` |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Recognition accuracy (Web Speech) | >85% word accuracy |
| Recognition accuracy (Whisper) | >95% word accuracy |
| Command recognition rate | >90% of supported commands correctly parsed |
| Time to capture (thought → stored) | <3 seconds |
| User adoption | >30% of active users try voice at least once |
| Error recovery rate | >80% of failed commands recovered within 1 retry |
| TTS satisfaction | Users prefer voice responses for quick queries |

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Web Speech API not supported (Firefox) | Medium | Low | Graceful fallback message + Whisper option in 11b |
| Microphone permission denied | Medium | Medium | Clear permission request UI + retry guidance |
| Poor accuracy in noisy environments | High | Medium | Show confidence, offer retry, Whisper fallback |
| Voice commands misunderstood | Medium | Medium | Confirmation for destructive actions, undo support |
| Cost overrun on Whisper API | Low | Low | Budget limits from multimodal.yaml, prefer Web Speech |
| Wake word false positives | Medium | Low | Configurable sensitivity, easy cancel |

---

## Cross-Phase Dependencies

```
Phase 15b (Audio/TTS) ──→ Phase 11b (Whisper adapter reuses AudioProcessor)
                       ──→ Phase 11c (TTS responses reuse TTSGenerator)

Phase 5 (Task Engine)  ──→ Phase 11a (Voice commands create/complete tasks)
Phase 4 (Notifications) ─→ Phase 11a (Voice triggers reminders, focus mode)
Phase 6 (Learning)     ──→ Phase 11a (Query commands use energy matching)
Phase 7 (Dashboard)    ──→ Phase 11a (Voice button lives in QuickChat)
Phase 10 (Mobile)      ──→ Phase 11c (Mobile voice via Expo bridge)
```

---

*This guide will be updated as implementation progresses.*
