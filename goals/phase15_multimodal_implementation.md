# Phase 15 Multi-Modal Messaging Implementation Plan

> Detailed implementation guide for Phases 15a-15d covering images, audio, video, documents, code blocks, and platform-specific rich formatting.

**Status:** Planning Complete
**Estimated Effort:** 18-23 days total
**Prerequisites:** Phase 1 (Channels), Design Doc (`multimodal_messaging.md`)

---

## Executive Summary

This implementation plan covers Phases 15a-15d of the multi-modal messaging feature, which adds support for images, audio, video, documents, code blocks, and platform-specific rich formatting across Telegram, Discord, and Slack channels.

**Key Architecture Decisions:**
1. **MediaContent as Enhanced Attachment** - Extends existing `Attachment` dataclass with processing metadata
2. **MediaProcessor Pipeline** - Centralized processing with platform-agnostic design
3. **ChannelRenderer Abstraction** - Platform-specific rendering for outbound formatting
4. **ContentFormatter/ContentBlock** - Structured approach to AI response parsing
5. **Integration Points** - Hooks into `sdk_handler.py` and channel adapters

---

## Phase 15a: Core Media Processing

**Goal:** Image analysis (Claude Vision), document extraction, code block formatting

**Estimated Effort:** 5-7 days

### Files to Create

| File | Purpose | Complexity |
|------|---------|------------|
| `tools/channels/media/__init__.py` | Module exports, MediaProcessor class | Medium |
| `tools/channels/media/downloader.py` | Download files from platform URLs with retry | Medium |
| `tools/channels/media/storage.py` | Temp/cache/permanent file management | Medium |
| `tools/channels/media/image_processor.py` | Claude Vision API, thumbnails, OCR detection | High |
| `tools/channels/media/document_processor.py` | PDF/Office text extraction | Medium |
| `tools/channels/media/cost_tracker.py` | Track processing costs per message | Low |
| `tools/channels/content/__init__.py` | ContentFormatter class, exports | Medium |
| `tools/channels/content/parser.py` | Parse AI response into ContentBlocks | Medium |
| `tools/channels/content/code_highlighter.py` | Language detection, syntax highlighting | Low |
| `args/multimodal.yaml` | Configuration from design doc | Low |

### Files to Modify

| File | Changes | Complexity |
|------|---------|------------|
| `tools/channels/models.py` | Add `MediaContent`, `MediaType`, `ContentBlock`, `BlockType` dataclasses | Medium |
| `tools/channels/sdk_handler.py` | Integrate MediaProcessor before AI call, ContentFormatter after | High |
| `tools/channels/telegram_adapter.py` | Add `download_attachment()` method | Medium |
| `tools/channels/discord.py` | Add `download_attachment()` method | Medium |
| `tools/channels/slack.py` | Add `download_attachment()` method | Medium |
| `tools/channels/router.py` | Add `ChannelAdapter.download_attachment()` abstract method | Low |
| `tools/manifest.md` | Add new media tools | Low |
| `goals/manifest.md` | Update Phase 15a status | Low |

### Database Schema

```sql
-- New table in data/media.db
CREATE TABLE IF NOT EXISTS media_processing_log (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    media_type TEXT NOT NULL,  -- 'image' | 'audio' | 'video' | 'document'
    filename TEXT,
    size_bytes INTEGER,
    processing_type TEXT,      -- 'vision' | 'transcription' | 'extraction' | 'thumbnail'
    cost_usd REAL DEFAULT 0.0,
    status TEXT DEFAULT 'pending',  -- 'pending' | 'completed' | 'failed'
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

CREATE INDEX idx_media_user ON media_processing_log(user_id, created_at);
CREATE INDEX idx_media_cost ON media_processing_log(user_id, cost_usd);
```

### Test Files to Create

| File | Purpose |
|------|---------|
| `tests/unit/channels/media/__init__.py` | Module init |
| `tests/unit/channels/media/test_image_processor.py` | Vision API mocking, thumbnail generation |
| `tests/unit/channels/media/test_document_processor.py` | PDF/text extraction |
| `tests/unit/channels/media/test_downloader.py` | Platform URL handling |
| `tests/unit/channels/media/test_storage.py` | Temp file lifecycle |
| `tests/integration/test_multimodal_flow.py` | End-to-end image -> analysis -> response |

### Implementation Order

```
1. models.py extensions ──────────────────────┐
2. args/multimodal.yaml ──────────────────────┤
3. storage.py ────────────────────────────────┤
                                              ▼
4. downloader.py ◄─────────────────── depends on storage
                                              │
5. cost_tracker.py ◄───────────────── depends on models
                                              │
6. image_processor.py ◄──────────────┬─ depends on downloader, storage, cost_tracker
7. document_processor.py ◄───────────┘
                                              │
8. media/__init__.py ◄───────────────── depends on all media modules
                                              │
9. content/parser.py ◄───────────────── depends on models
10. content/code_highlighter.py ─────────────┤
11. content/__init__.py ◄────────────────────┘
                                              │
12. Channel adapter modifications ◄──── depends on downloader
13. sdk_handler.py modifications ◄───── depends on MediaProcessor, ContentFormatter
```

### Key Interface: MediaProcessor

```python
# tools/channels/media/__init__.py
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ProcessingOptions:
    """Options for media processing."""
    max_cost_usd: float = 0.10          # Cost limit per attachment
    enable_vision: bool = True           # Use Claude vision
    enable_transcription: bool = True    # Use Whisper
    enable_ocr: bool = True              # OCR for images with text
    generate_thumbnail: bool = True      # Create thumbnails
    max_duration_seconds: float = 300    # Max audio/video length
    preferred_transcription: str = "whisper"  # 'whisper' | 'native'


class MediaProcessor:
    """Orchestrates media processing pipeline."""

    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self.storage = StorageManager()
        self.cost_tracker = CostTracker()

    async def process_attachment(
        self,
        attachment: Attachment,
        channel: str,
        options: ProcessingOptions = None,
    ) -> MediaContent:
        """
        Download and process an attachment.

        Steps:
        1. Download from platform
        2. Store in temp location
        3. Route to appropriate processor (image/doc/audio/video)
        4. Return enriched MediaContent
        """
        options = options or ProcessingOptions()

        # Download
        local_path = await self._download(attachment, channel)

        # Route to processor
        if attachment.type == "image":
            return await self._process_image(attachment, local_path, options)
        elif attachment.type == "document":
            return await self._process_document(attachment, local_path, options)
        elif attachment.type in ("audio", "voice"):
            return await self._process_audio(attachment, local_path, options)
        elif attachment.type == "video":
            return await self._process_video(attachment, local_path, options)
        else:
            return self._passthrough(attachment, local_path)

    async def process_attachments_batch(
        self,
        attachments: list[Attachment],
        channel: str,
        options: ProcessingOptions = None,
    ) -> list[MediaContent]:
        """Process multiple attachments with ADHD-friendly prioritization."""
        # Prioritize: images with questions > documents > other
        # Limit processing to max 3 for ADHD focus
        ...
```

### Key Interface: ContentFormatter

```python
# tools/channels/content/__init__.py
class ContentFormatter:
    """Format AI responses for channel delivery."""

    def __init__(self):
        self.parser = ResponseParser()
        self.highlighter = CodeHighlighter()

    def parse_response(
        self,
        response: str,
        attachments: list[MediaContent] = None,
    ) -> list[ContentBlock]:
        """
        Parse AI response into structured blocks.

        Detects:
        - Code blocks (```language\ncode```)
        - Markdown formatting
        - File/image references
        - Dividers (---)
        """
        blocks = []

        # Split on code blocks first
        parts = self._split_code_blocks(response)

        for part in parts:
            if part["type"] == "code":
                blocks.append(ContentBlock(
                    type=BlockType.CODE,
                    content=part["content"],
                    metadata={"language": part.get("language", "text")}
                ))
            else:
                # Parse markdown in text parts
                text_blocks = self._parse_markdown(part["content"])
                blocks.extend(text_blocks)

        return blocks

    def split_for_channel(
        self,
        blocks: list[ContentBlock],
        channel: str,
    ) -> list[list[ContentBlock]]:
        """
        Split blocks into message-sized chunks for channel limits.

        Respects:
        - Telegram: 4096 chars
        - Discord: 2000 chars
        - Slack: 40000 chars (but prefer smaller for readability)
        """
        limits = {
            "telegram": 4096,
            "discord": 2000,
            "slack": 4000,  # Practical limit for readability
        }
        max_len = limits.get(channel, 2000)

        # Split without breaking code blocks
        ...
```

### Verification Checklist (Phase 15a)

- [ ] Send image to Telegram → AI describes it
- [ ] Send PDF to Discord → AI summarizes content
- [ ] Send Word doc to Slack → AI extracts and responds
- [ ] AI response with code → proper formatting per channel
- [ ] Cost tracking records processing costs
- [ ] Large files rejected gracefully with user message
- [ ] Multiple images → ADHD-friendly summary ("I see 3 images...")

---

## Phase 15b: Audio/Video & Voice

**Goal:** Whisper transcription, TTS generation, video frame extraction

**Estimated Effort:** 4-5 days

### Files to Create

| File | Purpose | Complexity |
|------|---------|------------|
| `tools/channels/media/audio_processor.py` | Whisper API integration, format conversion | High |
| `tools/channels/media/video_processor.py` | Frame extraction, audio track transcription | High |
| `tools/channels/media/transcoder.py` | FFmpeg wrapper for format conversion | Medium |
| `tools/channels/media/tts_generator.py` | Text-to-speech with OpenAI TTS | Medium |

### Files to Modify

| File | Changes | Complexity |
|------|---------|------------|
| `tools/channels/media/__init__.py` | Add audio/video processor routing | Medium |
| `tools/channels/telegram_adapter.py` | Handle voice note format (OGG/Opus), send voice messages | Medium |
| `tools/channels/discord.py` | Handle voice messages (IS_VOICE_MESSAGE flag) | Medium |
| `tools/channels/slack.py` | Handle audio files | Low |
| `args/multimodal.yaml` | Add transcription/TTS config sections | Low |

### Implementation Order

```
1. transcoder.py ──────────────────────────────┐
                                               ▼
2. audio_processor.py ◄─────────────── depends on transcoder, storage, cost_tracker
                                               │
3. video_processor.py ◄─────────────── depends on transcoder, audio_processor
                                               │
4. tts_generator.py ◄──────────────── depends on storage
                                               │
5. MediaProcessor updates ◄────────── depends on audio/video processors
                                               │
6. Channel adapter updates ◄───────── depends on TTS generator
```

### Key Interface: AudioProcessor

```python
# tools/channels/media/audio_processor.py
from dataclasses import dataclass
from enum import Enum

class TranscriptionStrategy(Enum):
    WHISPER_API = "whisper_api"
    WHISPER_LOCAL = "whisper_local"
    PLATFORM_NATIVE = "native"


@dataclass
class TranscriptionConfig:
    """Configuration for audio transcription."""
    strategy: TranscriptionStrategy = TranscriptionStrategy.WHISPER_API
    max_duration_seconds: int = 300
    language_hint: str | None = None
    enable_timestamps: bool = False
    whisper_model: str = "whisper-1"


class AudioProcessor:
    """Process audio files with Whisper transcription."""

    def __init__(self, config: TranscriptionConfig = None):
        self.config = config or TranscriptionConfig()
        self.transcoder = Transcoder()

    async def transcribe(
        self,
        audio_path: str,
        config: TranscriptionConfig = None,
    ) -> dict[str, Any]:
        """
        Transcribe audio file to text.

        Returns:
            {
                "text": "transcribed content",
                "duration_seconds": 45.2,
                "language": "en",
                "cost_usd": 0.003,
                "segments": [...] if timestamps enabled
            }
        """
        config = config or self.config

        # Check duration limit
        duration = await self._get_duration(audio_path)
        if duration > config.max_duration_seconds:
            raise ValueError(f"Audio too long: {duration}s > {config.max_duration_seconds}s")

        # Convert to supported format if needed
        prepared_path = await self.transcoder.prepare_for_whisper(audio_path)

        # Transcribe
        if config.strategy == TranscriptionStrategy.WHISPER_API:
            return await self._transcribe_api(prepared_path, config)
        elif config.strategy == TranscriptionStrategy.WHISPER_LOCAL:
            return await self._transcribe_local(prepared_path, config)
        else:
            raise ValueError(f"Unknown strategy: {config.strategy}")

    async def _transcribe_api(self, path: str, config: TranscriptionConfig) -> dict:
        """Transcribe using OpenAI Whisper API."""
        import openai

        client = openai.AsyncOpenAI()

        with open(path, "rb") as f:
            response = await client.audio.transcriptions.create(
                model=config.whisper_model,
                file=f,
                language=config.language_hint,
                response_format="verbose_json" if config.enable_timestamps else "json",
            )

        # Calculate cost: $0.006 per minute
        duration = response.duration if hasattr(response, 'duration') else 0
        cost = (duration / 60) * 0.006

        return {
            "text": response.text,
            "duration_seconds": duration,
            "language": response.language if hasattr(response, 'language') else None,
            "cost_usd": cost,
            "segments": response.segments if config.enable_timestamps else None,
        }
```

### Key Interface: TTSGenerator

```python
# tools/channels/media/tts_generator.py
@dataclass
class TTSConfig:
    """Configuration for text-to-speech generation."""
    provider: str = "openai"
    voice: str = "alloy"  # alloy, echo, fable, onyx, nova, shimmer
    speed: float = 1.0
    output_format: str = "opus"  # For Telegram/Discord voice notes


class TTSGenerator:
    """Generate speech audio from text."""

    async def generate(
        self,
        text: str,
        config: TTSConfig = None,
        output_path: str = None,
    ) -> dict[str, Any]:
        """
        Generate speech audio from text.

        Returns:
            {
                "path": "/tmp/dexai/media/tts_123.opus",
                "duration_seconds": 5.2,
                "cost_usd": 0.023,
                "format": "opus"
            }
        """
        config = config or TTSConfig()

        import openai
        client = openai.AsyncOpenAI()

        response = await client.audio.speech.create(
            model="tts-1",
            voice=config.voice,
            input=text,
            response_format=config.output_format,
            speed=config.speed,
        )

        # Save to file
        output_path = output_path or self._generate_path(config.output_format)
        response.stream_to_file(output_path)

        # Calculate cost: $0.015 per 1K chars
        cost = (len(text) / 1000) * 0.015

        return {
            "path": output_path,
            "cost_usd": cost,
            "format": config.output_format,
        }
```

### Verification Checklist (Phase 15b)

- [ ] Send voice note on Telegram → AI responds with transcription context
- [ ] Send audio file on Discord → Transcription works
- [ ] Long audio (>5 min) → Rejected with helpful message
- [ ] Video file → Frame extraction + audio transcription
- [ ] TTS generation → Produces valid OGG/Opus file
- [ ] Cost tracking for Whisper API calls

---

## Phase 15c: Platform-Specific Rendering

**Goal:** Rich embeds (Discord), Block Kit (Slack), MarkdownV2 (Telegram), media groups

**Estimated Effort:** 5-6 days

### Files to Create

| File | Purpose | Complexity |
|------|---------|------------|
| `tools/channels/renderers/__init__.py` | ChannelRenderer base, registry | Medium |
| `tools/channels/renderers/telegram_renderer.py` | MarkdownV2, media groups (up to 10) | High |
| `tools/channels/renderers/discord_renderer.py` | Rich embeds, voice messages | High |
| `tools/channels/renderers/slack_renderer.py` | Block Kit elements | High |
| `tools/channels/content/splitter.py` | Split content for channel limits | Medium |
| `tools/channels/content/markdown.py` | Platform-specific markdown conversion | Medium |

### Files to Modify

| File | Changes | Complexity |
|------|---------|------------|
| `tools/channels/telegram_adapter.py` | Add `send_rich_message()`, `upload_file()` | High |
| `tools/channels/discord.py` | Add `send_rich_message()` using embeds, `upload_file()` | High |
| `tools/channels/slack.py` | Add `send_rich_message()` with Block Kit, new file upload flow | High |
| `tools/channels/sdk_handler.py` | Use renderers for outbound messages | Medium |
| `tools/channels/router.py` | Add abstract `send_rich_message()`, `upload_file()` | Low |
| `tools/channels/models.py` | Add `RenderedMessage`, `RenderContext` | Low |

### Implementation Order

```
1. models.py additions ────────────────────────┐
                                               ▼
2. content/markdown.py ◄───────────────────────┤
3. content/splitter.py ◄───────────────────────┤
                                               │
4. renderers/__init__.py ◄─────────────────────┘
                                               │
        ┌──────────────────┬───────────────────┼───────────────────┐
        ▼                  ▼                   ▼                   │
5. telegram_renderer  6. discord_renderer  7. slack_renderer      │
                                               │                   │
8. Channel adapter updates ◄───────────────────┴───────────────────┘
                                               │
9. sdk_handler.py updates ◄────────────────────┘
```

### Key Interface: ChannelRenderer

```python
# tools/channels/renderers/__init__.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class RenderContext:
    """Context for rendering decisions."""
    channel: str
    user_id: str
    message_id: str
    reply_to: str | None = None
    thread_id: str | None = None
    platform_config: dict = field(default_factory=dict)


@dataclass
class RenderedMessage:
    """Platform-native message ready to send."""
    channel: str
    content: str | dict  # Text or platform-specific structure
    attachments: list[str] = field(default_factory=list)  # Platform file IDs
    metadata: dict[str, Any] = field(default_factory=dict)


class ChannelRenderer(ABC):
    """Base class for channel-specific rendering."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Return the channel name this renderer handles."""
        ...

    @abstractmethod
    async def render_blocks(
        self,
        blocks: list[ContentBlock],
        context: RenderContext,
    ) -> list[RenderedMessage]:
        """Render content blocks to platform-native format."""
        ...

    @abstractmethod
    async def upload_media(
        self,
        media: MediaContent,
        context: RenderContext,
    ) -> str:
        """Upload media and return platform reference."""
        ...

    def escape_text(self, text: str) -> str:
        """Escape text for this platform's formatting."""
        return text


# Registry
_renderers: dict[str, ChannelRenderer] = {}

def register_renderer(renderer: ChannelRenderer):
    """Register a channel renderer."""
    _renderers[renderer.channel_name] = renderer

def get_renderer(channel: str) -> ChannelRenderer | None:
    """Get renderer for a channel."""
    return _renderers.get(channel)
```

### Telegram Renderer

```python
# tools/channels/renderers/telegram_renderer.py
class TelegramRenderer(ChannelRenderer):
    """Telegram-specific rendering with MarkdownV2 and media groups."""

    @property
    def channel_name(self) -> str:
        return "telegram"

    # Characters that need escaping in MarkdownV2
    ESCAPE_CHARS = r'_*[]()~`>#+-=|{}.!'

    def escape_text(self, text: str) -> str:
        """Escape text for Telegram MarkdownV2."""
        for char in self.ESCAPE_CHARS:
            text = text.replace(char, f'\\{char}')
        return text

    async def render_blocks(
        self,
        blocks: list[ContentBlock],
        context: RenderContext,
    ) -> list[RenderedMessage]:
        """Render blocks to Telegram format."""
        messages = []
        current_text = ""
        media_group = []

        for block in blocks:
            if block.type == BlockType.CODE:
                # Code block - use <pre> tag
                lang = block.metadata.get("language", "")
                code = block.content
                formatted = f'<pre><code class="language-{lang}">{self._escape_html(code)}</code></pre>'
                current_text += formatted + "\n"

            elif block.type == BlockType.IMAGE:
                # Collect for media group
                media_group.append(block)
                if len(media_group) >= 10:
                    # Flush media group
                    messages.append(self._create_media_group_message(media_group, context))
                    media_group = []

            elif block.type == BlockType.TEXT:
                current_text += self._format_markdown(block.content) + "\n"

            # Check message length limit
            if len(current_text) > 4000:
                messages.append(RenderedMessage(
                    channel="telegram",
                    content=current_text[:4096],
                    metadata={"parse_mode": "HTML"}
                ))
                current_text = current_text[4096:]

        # Flush remaining
        if current_text.strip():
            messages.append(RenderedMessage(
                channel="telegram",
                content=current_text,
                metadata={"parse_mode": "HTML"}
            ))

        if media_group:
            messages.append(self._create_media_group_message(media_group, context))

        return messages
```

### Discord Renderer

```python
# tools/channels/renderers/discord_renderer.py
class DiscordRenderer(ChannelRenderer):
    """Discord-specific rendering with embeds."""

    @property
    def channel_name(self) -> str:
        return "discord"

    async def render_blocks(
        self,
        blocks: list[ContentBlock],
        context: RenderContext,
    ) -> list[RenderedMessage]:
        """Render blocks to Discord format with embeds."""
        messages = []
        current_text = ""
        embeds = []

        for block in blocks:
            if block.type == BlockType.CODE:
                lang = block.metadata.get("language", "")
                code = block.content
                formatted = f"```{lang}\n{code}\n```"

                # Check if adding would exceed limit
                if len(current_text) + len(formatted) > 1900:
                    messages.append(RenderedMessage(
                        channel="discord",
                        content=current_text,
                    ))
                    current_text = formatted
                else:
                    current_text += formatted + "\n"

            elif block.type == BlockType.IMAGE:
                # Create embed for image
                embeds.append({
                    "image": {"url": block.content},
                    "color": context.platform_config.get("embed_color", 0x5865F2),
                })

            elif block.type == BlockType.TEXT:
                if len(current_text) + len(block.content) > 1900:
                    messages.append(RenderedMessage(
                        channel="discord",
                        content=current_text,
                    ))
                    current_text = block.content
                else:
                    current_text += block.content + "\n"

        # Flush remaining
        if current_text.strip() or embeds:
            messages.append(RenderedMessage(
                channel="discord",
                content=current_text,
                metadata={"embeds": embeds[:10]} if embeds else {},
            ))

        return messages
```

### Slack Renderer

```python
# tools/channels/renderers/slack_renderer.py
class SlackRenderer(ChannelRenderer):
    """Slack-specific rendering with Block Kit."""

    @property
    def channel_name(self) -> str:
        return "slack"

    async def render_blocks(
        self,
        blocks: list[ContentBlock],
        context: RenderContext,
    ) -> list[RenderedMessage]:
        """Render blocks to Slack Block Kit format."""
        slack_blocks = []

        for block in blocks:
            if block.type == BlockType.CODE:
                # Rich text block with preformatted section
                slack_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```{block.content}```"
                    }
                })

            elif block.type == BlockType.TEXT:
                slack_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": block.content
                    }
                })

            elif block.type == BlockType.IMAGE:
                slack_blocks.append({
                    "type": "image",
                    "image_url": block.content,
                    "alt_text": block.metadata.get("alt_text", "Image"),
                })

            elif block.type == BlockType.DIVIDER:
                slack_blocks.append({"type": "divider"})

            # Respect 50 block limit
            if len(slack_blocks) >= 50:
                break

        return [RenderedMessage(
            channel="slack",
            content={"blocks": slack_blocks},
        )]
```

### Verification Checklist (Phase 15c)

- [ ] Code response → syntax highlighted per platform
- [ ] Multiple images on Telegram → media group (album)
- [ ] Multiple images on Discord → embeds
- [ ] Long response → proper splitting without breaking code blocks
- [ ] Markdown formatting preserved per platform
- [ ] Block Kit renders correctly in Slack

---

## Phase 15d: Advanced & Interactive

**Goal:** Location, contacts, interactive buttons, polls, file storage management

**Estimated Effort:** 4-5 days

### Files to Create

| File | Purpose | Complexity |
|------|---------|------------|
| `tools/channels/media/location_processor.py` | Geocoding, place lookup | Medium |
| `tools/channels/media/contact_processor.py` | vCard parsing | Low |
| `tools/channels/media/storage_cleanup.py` | Scheduled cleanup job | Medium |
| `tools/channels/interactive/__init__.py` | Interactive element framework | Medium |
| `tools/channels/interactive/buttons.py` | Button definitions, handlers | Medium |
| `tools/channels/interactive/polls.py` | Poll creation, vote handling | Medium |
| `tools/automation/media_cleanup.py` | Cron job for media cleanup | Low |

### Files to Modify

| File | Changes | Complexity |
|------|---------|------------|
| `tools/channels/media/__init__.py` | Add location/contact processors | Low |
| `tools/channels/telegram_adapter.py` | Handle location, contact, button callbacks | Medium |
| `tools/channels/discord.py` | Handle buttons, message components | Medium |
| `tools/channels/slack.py` | Handle Block Kit interactive elements | Medium |
| `tools/channels/renderers/*.py` | Add button/poll rendering | Medium |
| `args/multimodal.yaml` | Add interactive/advanced sections | Low |

### Database Schema

```sql
-- Add to data/media.db
CREATE TABLE IF NOT EXISTS interactive_state (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    element_type TEXT NOT NULL,  -- 'button' | 'poll' | 'select'
    element_data TEXT,           -- JSON
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    callback_id TEXT UNIQUE
);

CREATE INDEX idx_interactive_callback ON interactive_state(callback_id);
CREATE INDEX idx_interactive_user ON interactive_state(user_id, created_at);
```

### Key Interfaces

```python
# tools/channels/interactive/buttons.py
@dataclass
class Button:
    """Interactive button definition."""
    id: str
    label: str
    style: str = "default"  # 'default' | 'primary' | 'danger'
    action: str = None      # Callback action identifier
    url: str = None         # For link buttons
    disabled: bool = False


@dataclass
class ButtonGroup:
    """Group of buttons for a message."""
    buttons: list[Button]
    message_id: str
    user_id: str
    expires_at: datetime = None


class ButtonHandler:
    """Handle button interactions."""

    async def create_buttons(
        self,
        buttons: list[Button],
        context: RenderContext,
    ) -> dict[str, Any]:
        """Create buttons and store state for callbacks."""
        ...

    async def handle_callback(
        self,
        callback_id: str,
        user_id: str,
        channel: str,
    ) -> dict[str, Any]:
        """Handle button click callback."""
        ...


# tools/channels/interactive/polls.py
@dataclass
class PollOption:
    """Single poll option."""
    id: str
    text: str
    votes: int = 0


@dataclass
class Poll:
    """Poll definition."""
    id: str
    question: str
    options: list[PollOption]
    multiple_choice: bool = False
    anonymous: bool = True
    close_at: datetime = None


class PollHandler:
    """Handle poll creation and voting."""

    async def create_poll(
        self,
        poll: Poll,
        context: RenderContext,
    ) -> dict[str, Any]:
        """Create poll on supported platforms."""
        # Telegram: native polls
        # Discord: reactions or buttons
        # Slack: Block Kit with buttons
        ...

    async def handle_vote(
        self,
        poll_id: str,
        option_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Handle vote on a poll."""
        ...
```

### Verification Checklist (Phase 15d)

- [ ] Share location on Telegram → AI understands place context
- [ ] Contact shared → vCard parsed and used
- [ ] Create poll on Telegram → Native poll created
- [ ] Button click → Callback handled correctly
- [ ] Storage cleanup runs on schedule
- [ ] Old temp files deleted automatically

---

## Dependencies (pyproject.toml)

```toml
[project.optional-dependencies]
multimodal = [
    "pypdf2>=3.0.0",              # PDF text extraction
    "python-docx>=0.8.11",        # Word document parsing
    "pillow>=10.0.0",             # Image processing, thumbnails
    "ffmpeg-python>=0.2.0",       # Audio/video transcoding
    "geopy>=2.4.0",               # Geocoding (optional)
    "vobject>=0.9.6.1",           # vCard parsing
]
```

---

## Configuration Reference

### args/multimodal.yaml

```yaml
# Multi-modal messaging configuration

processing:
  enabled: true
  max_file_size_mb: 50
  max_processing_cost_usd: 0.20

  vision:
    enabled: true
    provider: "anthropic"
    max_images_per_message: 3
    auto_analyze_triggers:
      - "what is"
      - "can you see"
      - "look at"
      - "screenshot"

  transcription:
    enabled: true
    provider: "openai"
    model: "whisper-1"
    max_duration_seconds: 300

  documents:
    enabled: true
    extract_text: true
    max_pages: 20
    supported_formats: ["pdf", "docx", "txt", "md"]

generation:
  tts:
    enabled: false
    provider: "openai"
    voice: "alloy"

storage:
  temp_retention_hours: 1
  cache_retention_hours: 24
  max_cache_size_mb: 500
  cleanup_enabled: true

channels:
  telegram:
    prefer_voice_notes: true
    use_markdown_v2: true
    max_media_group_size: 10

  discord:
    use_embeds: true
    embed_color: 0x5865F2
    max_embed_fields: 25

  slack:
    use_block_kit: true
    unfurl_links: true
    thread_replies: true

adhd:
  acknowledge_processing: true
  summarize_multiple: true
  max_inline_code_lines: 20

interactive:
  buttons:
    enabled: true
    max_per_message: 5
    expiry_hours: 24

  polls:
    enabled: true
    max_options: 10
    default_duration_hours: 24
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Vision API costs | VisionPolicy with strict limits, auto-disable at threshold |
| FFmpeg dependency | Make optional, graceful degradation |
| Platform API limits | Rate limiting per platform, queue for bulk uploads |
| File storage growth | Aggressive cleanup, size limits at download |
| Backward compatibility | All features opt-in via configuration |

---

## Estimated Effort Summary

| Phase | Days | Key Deliverables |
|-------|------|------------------|
| 15a | 5-7 | Image analysis, document extraction, code formatting |
| 15b | 4-5 | Voice transcription, TTS, video processing |
| 15c | 5-6 | Platform renderers, rich formatting, media groups |
| 15d | 4-5 | Location, contacts, buttons, polls, cleanup |
| **Total** | **18-23** | Full multi-modal support |

---

## Critical Integration Points

1. **`tools/channels/models.py`** - All new data models
2. **`tools/channels/sdk_handler.py`** - Inbound processing + outbound formatting
3. **`tools/channels/router.py`** - Abstract adapter methods
4. **Channel adapters** - Platform-specific implementations
5. **`args/multimodal.yaml`** - Feature flags and configuration

---

*Implementation Plan Created: 2026-02-09*
