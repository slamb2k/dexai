# Multi-Modal Messaging Design

> Design document for handling different content modalities (images, audio, video, documents, code, markdown) across communication channels.

**Status:** Design Complete
**Target Phases:** 15a-15d
**Prerequisites:** Phase 1 (Channels), Phase 8 (Installation)

---

## Problem Statement

DexAI currently handles text messages across Telegram, Discord, and Slack, with basic attachment metadata capture. However:

1. **Inbound attachments are not processed** - Images, audio, video, and documents are received but not analyzed or used in AI context
2. **Outbound is text-only** - AI cannot send images, code blocks, or rich formatted responses
3. **No transcription** - Voice notes and audio files are acknowledged but not transcribed
4. **Platform-specific formatting is lost** - Markdown, code blocks, and rich text vary by platform but we don't adapt
5. **No file storage strategy** - Temporary files aren't managed, and there's no caching for re-use

---

## Design Goals

1. **Unified modality abstraction** - Single interface for all content types, with platform-specific rendering
2. **Bidirectional support** - Process inbound media AND generate/send outbound media
3. **Graceful degradation** - Fall back appropriately when platforms don't support a modality
4. **ADHD-friendly** - Don't overwhelm with multiple attachments; prioritize and summarize
5. **Cost-aware** - Vision/audio APIs are expensive; use them judiciously
6. **Extensible** - Easy to add new modalities (e.g., location, contacts, stickers)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Inbound Flow                              │
├─────────────────────────────────────────────────────────────────┤
│  Channel Adapter → Media Processor → Content Store → AI Context │
│  (Telegram/etc)    (download,        (temp/perm)    (UnifiedMsg) │
│                     transcode)                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        Outbound Flow                             │
├─────────────────────────────────────────────────────────────────┤
│  AI Response → Content Formatter → Channel Renderer → Platform  │
│  (blocks,      (split, adapt)      (embeds, Block    (send API) │
│   media refs)                       Kit, etc)                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Supported Modalities

### Tier 1: Core (Phase 15a)

| Modality | Inbound | Outbound | Processing |
|----------|---------|----------|------------|
| **Text** | ✅ | ✅ | Markdown rendering, code block detection |
| **Images** | ✅ | ✅ | Vision API analysis, thumbnail generation |
| **Documents** | ✅ | ✅ | Text extraction (PDF, Office), size limits |
| **Code Blocks** | ✅ | ✅ | Syntax highlighting, language detection |

### Tier 2: Extended (Phase 15b)

| Modality | Inbound | Outbound | Processing |
|----------|---------|----------|------------|
| **Voice/Audio** | ✅ | ✅ | Whisper transcription, TTS generation |
| **Video** | ✅ | Limited | Frame extraction, Whisper for audio track |
| **Markdown** | ✅ | ✅ | Platform-specific rendering |

### Tier 3: Platform-Specific (Phase 15c)

| Modality | Telegram | Discord | Slack |
|----------|----------|---------|-------|
| **Stickers** | ✅ Receive | ❌ | ❌ |
| **Embeds** | ❌ | ✅ Send | ❌ |
| **Block Kit** | ❌ | ❌ | ✅ Send |
| **Reactions** | ❌ | ✅ | ✅ |
| **Voice Channels** | ❌ | Future | ❌ |

### Tier 4: Advanced (Phase 15d)

| Modality | Support | Notes |
|----------|---------|-------|
| **Location** | Receive only | Geocoding, place lookup |
| **Contacts** | Receive only | vCard parsing |
| **Polls** | Both | Platform-native where supported |
| **Buttons/Actions** | Send only | Interactive elements |

---

## Data Models

### Enhanced Attachment Model

```python
@dataclass
class MediaContent:
    """
    Enhanced attachment with processing metadata.

    Extends the existing Attachment dataclass with processed content.
    """
    # Core identity
    id: str
    type: MediaType  # 'image' | 'audio' | 'video' | 'document' | 'code'
    filename: str
    mime_type: str
    size_bytes: int

    # Location
    source_url: str | None = None      # Platform URL (may expire)
    local_path: str | None = None       # Downloaded temp file
    permanent_path: str | None = None   # If stored permanently

    # Processing results
    processed: bool = False
    processing_error: str | None = None

    # Type-specific processed content
    text_content: str | None = None     # Transcription, OCR, extracted text
    description: str | None = None      # Vision API description
    thumbnail_path: str | None = None   # Generated thumbnail
    duration_seconds: float | None = None  # For audio/video
    dimensions: tuple[int, int] | None = None  # Width x height

    # Cost tracking
    processing_cost_usd: float = 0.0

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class MediaType(Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    CODE = "code"
    VOICE = "voice"
    STICKER = "sticker"
    ANIMATION = "animation"
    LOCATION = "location"
    CONTACT = "contact"
```

### Rich Content Blocks (for outbound)

```python
@dataclass
class ContentBlock:
    """
    Structured content block for rich responses.

    The AI returns these blocks; they're rendered per-platform.
    """
    type: BlockType
    content: str | dict
    metadata: dict[str, Any] = field(default_factory=dict)


class BlockType(Enum):
    TEXT = "text"           # Plain or markdown text
    CODE = "code"           # Code with language hint
    IMAGE = "image"         # Image URL or file reference
    FILE = "file"           # Document attachment
    DIVIDER = "divider"     # Visual separator
    QUOTE = "quote"         # Block quote
    LIST = "list"           # Bullet or numbered list
    TABLE = "table"         # Tabular data
    EMBED = "embed"         # Rich embed (Discord) / unfurl (Slack)
    BUTTON = "button"       # Interactive button
    POLL = "poll"           # Poll/survey
```

---

## Platform Capabilities Reference

### Telegram Bot API

| Feature | Limit | Notes |
|---------|-------|-------|
| Max file upload | 50 MB | 2 GB with local Bot API server |
| Max file download | 20 MB | Via getFile API |
| Photo dimensions | 10,000px total | Width + height combined |
| Voice format | OGG/Opus | For native voice note display |
| Message length | 4,096 chars | Per message |
| Media group | 10 items | Album-style display |
| Rate limit | 30 req/s global | 1 msg/s per chat recommended |

**Unique features:** Native stickers (static/animated/video), voice notes, video notes (round), media groups

### Discord API

| Feature | Limit | Notes |
|---------|-------|-------|
| Max file upload | 25-500 MB | Depends on Nitro status |
| Attachments per msg | 10 | Including embeds |
| Message length | 2,000 chars | Per message |
| Embed total chars | 6,000 | Per embed |
| Embeds per message | 10 | Rich cards |
| Voice message format | OGG/Opus 48kHz | With IS_VOICE_MESSAGE flag |
| Rate limit | 50 req/s global | 5 msg/s per channel |

**Unique features:** Rich embeds, voice channels, slash commands, message components (buttons, selects)

### Slack API

| Feature | Limit | Notes |
|---------|-------|-------|
| Max file upload | 1 GB | 5 GB total for free workspaces |
| Blocks per message | 50 | Block Kit elements |
| Message length | 40,000 chars | Including Block Kit |
| Video blocks | Embed only | External iframe (YouTube, etc.) |
| Rate limit | 20 req/min (Tier 2) | For file operations |

**Unique features:** Block Kit (rich layouts), Workflows, Slack Connect, threaded conversations

**Note:** `files.upload` deprecated - must use `files.getUploadURLExternal` flow by Nov 2025.

---

## Implementation Components

### 1. Media Processor (`tools/channels/media/`)

```
tools/channels/media/
├── __init__.py           # MediaProcessor class, exports
├── downloader.py         # Download files from platform URLs
├── transcoder.py         # Format conversion (FFmpeg wrapper)
├── image_processor.py    # Vision API, thumbnails, OCR
├── audio_processor.py    # Whisper transcription, TTS
├── document_processor.py # PDF/Office text extraction
├── storage.py            # Temp/permanent file management
└── cost_tracker.py       # Track API costs for media processing
```

**Key classes:**

```python
class MediaProcessor:
    """Orchestrates media processing pipeline."""

    async def process_attachment(
        self,
        attachment: Attachment,
        channel: str,
        options: ProcessingOptions,
    ) -> MediaContent:
        """
        Download and process an attachment.

        Args:
            attachment: Raw attachment from channel
            channel: Source channel (for platform-specific handling)
            options: Processing options (e.g., max_cost, skip_vision)

        Returns:
            Processed MediaContent with extracted text/description
        """
        ...

    async def generate_media(
        self,
        media_type: MediaType,
        content: str | bytes,
        options: GenerationOptions,
    ) -> MediaContent:
        """
        Generate media content (e.g., TTS audio from text).
        """
        ...


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
```

### 2. Content Formatter (`tools/channels/content/`)

```
tools/channels/content/
├── __init__.py           # ContentFormatter class
├── parser.py             # Parse AI response into blocks
├── markdown.py           # Markdown processing
├── code_highlighter.py   # Syntax highlighting
└── splitter.py           # Split long content
```

**Key classes:**

```python
class ContentFormatter:
    """Format AI responses for channel delivery."""

    def parse_response(
        self,
        response: str,
        attachments: list[MediaContent] = None,
    ) -> list[ContentBlock]:
        """
        Parse AI response text into structured blocks.

        Detects:
        - Code blocks (```language\ncode```)
        - Markdown formatting
        - File/image references
        - Dividers
        """
        ...

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
        - Slack: 40000 chars (but prefer smaller)
        """
        ...
```

### 3. Channel Renderers (`tools/channels/renderers/`)

```
tools/channels/renderers/
├── __init__.py           # ChannelRenderer base, registry
├── telegram_renderer.py  # Telegram-specific formatting
├── discord_renderer.py   # Discord embeds, formatting
└── slack_renderer.py     # Slack Block Kit
```

**Key classes:**

```python
class ChannelRenderer(ABC):
    """Base class for channel-specific rendering."""

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


class TelegramRenderer(ChannelRenderer):
    """Telegram-specific rendering with markdown and media groups."""

    async def render_blocks(self, blocks, context):
        # Use MarkdownV2 for formatting
        # Group images into media groups (max 10)
        # Convert code blocks to pre-formatted text
        ...


class DiscordRenderer(ChannelRenderer):
    """Discord-specific rendering with embeds."""

    async def render_blocks(self, blocks, context):
        # Use rich embeds for structured content
        # Syntax highlighting via code blocks
        # Voice message formatting for audio
        ...


class SlackRenderer(ChannelRenderer):
    """Slack-specific rendering with Block Kit."""

    async def render_blocks(self, blocks, context):
        # Convert to Block Kit elements
        # Use section, divider, code blocks
        # Video blocks for embeddable URLs only
        ...
```

### 4. Enhanced Adapter Methods

Each channel adapter gains new methods:

```python
class ChannelAdapter(ABC):
    # Existing methods...

    @abstractmethod
    async def download_attachment(
        self,
        attachment: Attachment,
    ) -> bytes:
        """Download attachment content from platform."""
        ...

    @abstractmethod
    async def upload_file(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> str:
        """Upload file and return platform reference."""
        ...

    @abstractmethod
    async def send_rich_message(
        self,
        rendered: RenderedMessage,
    ) -> dict[str, Any]:
        """Send platform-native rich message."""
        ...
```

---

## Processing Pipelines

### Inbound Processing Pipeline

```
1. Receive Message (Channel Adapter)
   └─→ UnifiedMessage with raw Attachments

2. Media Processing (MediaProcessor)
   ├─→ Download file from platform
   ├─→ Store in temp location
   ├─→ Determine processing strategy
   │   ├─→ Image: Vision API description + OCR if text-heavy
   │   ├─→ Audio/Voice: Whisper transcription
   │   ├─→ Video: Frame extraction + audio transcription
   │   └─→ Document: Text extraction (PDF, Office, text)
   └─→ Return MediaContent with processed data

3. Context Building (SDK Handler)
   ├─→ Add text_content/description to message context
   ├─→ Pass image content to Claude Vision (if image)
   └─→ Include relevant metadata (dimensions, duration)

4. AI Processing (DexAIClient)
   └─→ Process with full multimodal context
```

### Outbound Processing Pipeline

```
1. AI Response (DexAIClient)
   └─→ Raw text response (may contain code blocks, markdown)

2. Content Parsing (ContentFormatter)
   ├─→ Parse into ContentBlocks
   ├─→ Detect code blocks, images refs, formatting
   └─→ Split for channel limits

3. Rendering (ChannelRenderer)
   ├─→ Convert blocks to platform-native format
   ├─→ Upload any generated media
   └─→ Return RenderedMessage(s)

4. Send (Channel Adapter)
   └─→ Send via platform API
```

---

## Vision API Integration

### When to Use Vision

| Scenario | Use Vision | Reasoning |
|----------|------------|-----------|
| User asks about image | Yes | Explicit request |
| Image with caption asking question | Yes | Context suggests analysis needed |
| Screenshot/code image | Yes + OCR | Extract text content |
| Meme/reaction image | Optional | May not need analysis |
| Profile picture | No | Rarely relevant |
| Multiple images | Selective | Process most relevant, summarize others |

### Vision Cost Control

```python
@dataclass
class VisionPolicy:
    """Policy for vision API usage."""
    max_images_per_message: int = 3
    max_cost_per_image: float = 0.05
    max_cost_per_session: float = 0.50
    auto_vision_triggers: list[str] = field(default_factory=lambda: [
        "what is this",
        "can you see",
        "look at",
        "in the image",
        "in the picture",
        "screenshot",
    ])
    skip_vision_for: list[str] = field(default_factory=lambda: [
        "sticker",
        "emoji",
        "reaction",
    ])
```

---

## Audio/Voice Integration

### Transcription Strategy

```python
class TranscriptionStrategy(Enum):
    WHISPER_API = "whisper_api"      # OpenAI Whisper API
    WHISPER_LOCAL = "whisper_local"  # Local Whisper model
    PLATFORM_NATIVE = "native"        # Platform's built-in (if available)


@dataclass
class TranscriptionConfig:
    """Configuration for audio transcription."""
    strategy: TranscriptionStrategy = TranscriptionStrategy.WHISPER_API
    max_duration_seconds: int = 300   # 5 minutes
    language_hint: str | None = None  # ISO 639-1 code
    enable_timestamps: bool = False
    enable_speaker_diarization: bool = False
    whisper_model: str = "whisper-1"  # For API
    local_model_size: str = "base"    # For local: tiny, base, small, medium, large
```

### TTS Generation (Outbound Voice)

```python
class TTSConfig:
    """Configuration for text-to-speech generation."""
    provider: str = "openai"          # 'openai' | 'elevenlabs' | 'local'
    voice: str = "alloy"              # Provider-specific voice ID
    speed: float = 1.0
    output_format: str = "opus"       # For Telegram/Discord voice notes
```

---

## Code Block Handling

### Detection and Formatting

```python
class CodeBlockHandler:
    """Handle code block detection and formatting."""

    # Language aliases for consistent detection
    LANGUAGE_ALIASES = {
        "js": "javascript",
        "ts": "typescript",
        "py": "python",
        "rb": "ruby",
        "sh": "bash",
        "shell": "bash",
        "yml": "yaml",
        # ... more aliases
    }

    def detect_language(self, code: str, hint: str = None) -> str:
        """Detect programming language from code content."""
        ...

    def format_for_channel(
        self,
        code: str,
        language: str,
        channel: str,
    ) -> str:
        """Format code block for specific channel."""
        if channel == "telegram":
            # Use <code> or <pre> tags
            return f"<pre><code class=\"language-{language}\">{escape_html(code)}</code></pre>"
        elif channel == "discord":
            # Use triple backticks with language
            return f"```{language}\n{code}\n```"
        elif channel == "slack":
            # Use Block Kit code block
            return {"type": "section", "text": {"type": "mrkdwn", "text": f"```{code}```"}}
```

---

## File Storage Strategy

### Storage Tiers

| Tier | Location | Retention | Use Case |
|------|----------|-----------|----------|
| **Temp** | `/tmp/dexai/media/` | Session | Processing intermediates |
| **Cache** | `data/media/cache/` | 24 hours | Re-uploadable content |
| **Permanent** | `data/media/files/` | Indefinite | User-requested saves |

### Cleanup Policy

```python
@dataclass
class StoragePolicy:
    """Policy for media file storage and cleanup."""
    temp_retention_hours: int = 1
    cache_retention_hours: int = 24
    max_cache_size_mb: int = 500
    max_file_size_mb: int = 50
    cleanup_interval_minutes: int = 60
```

---

## ADHD-Friendly Media Handling

### Principles

1. **Don't overwhelm** - If multiple images, summarize first: "I see 3 images. The first shows..."
2. **Prioritize text** - Extract and present text content prominently
3. **One thing at a time** - Process sequentially, report progressively
4. **Acknowledge receipt** - "Got your image, analyzing..." before long processing

### Response Formatting

```python
class ADHDMediaFormatter:
    """ADHD-friendly formatting for media responses."""

    def format_image_analysis(
        self,
        analyses: list[dict],
        user_question: str | None,
    ) -> str:
        """
        Format image analysis results.

        If single image: Direct response
        If multiple: Brief summary, then details on request
        """
        if len(analyses) == 1:
            return analyses[0]["description"]

        # Multiple images - summarize first
        summary = f"I looked at {len(analyses)} images:\n"
        for i, analysis in enumerate(analyses, 1):
            summary += f"{i}. {analysis['brief']}\n"
        summary += "\nAsk about any specific one for details."
        return summary
```

---

## Configuration

### `args/multimodal.yaml`

```yaml
# Multi-modal messaging configuration

# Media processing
processing:
  enabled: true
  max_file_size_mb: 50
  max_processing_cost_usd: 0.20  # Per message

  vision:
    enabled: true
    provider: "anthropic"  # Use Claude Vision
    max_images_per_message: 3
    auto_analyze_triggers:
      - "what is"
      - "can you see"
      - "look at"
      - "screenshot"

  transcription:
    enabled: true
    provider: "openai"     # Whisper API
    model: "whisper-1"
    max_duration_seconds: 300
    language_hint: null    # Auto-detect

  documents:
    enabled: true
    extract_text: true
    max_pages: 20
    supported_formats:
      - "pdf"
      - "docx"
      - "txt"
      - "md"

# Outbound generation
generation:
  tts:
    enabled: false         # Off by default
    provider: "openai"
    voice: "alloy"

  images:
    enabled: false         # No image generation by default

# Storage
storage:
  temp_retention_hours: 1
  cache_retention_hours: 24
  max_cache_size_mb: 500
  cleanup_enabled: true

# Channel-specific overrides
channels:
  telegram:
    prefer_voice_notes: true    # Send voice as native voice note
    use_markdown_v2: true
    max_media_group_size: 10

  discord:
    use_embeds: true
    embed_color: 0x5865F2       # Discord blurple
    max_embed_fields: 25

  slack:
    use_block_kit: true
    unfurl_links: true
    thread_replies: true

# ADHD settings
adhd:
  acknowledge_processing: true  # "Analyzing your image..."
  summarize_multiple: true      # Don't dump all analyses at once
  max_inline_code_lines: 20     # Collapse longer code blocks
```

---

## Implementation Phases

### Phase 15a: Core Media Processing

**Scope:** Image analysis, document extraction, basic code formatting

**Deliverables:**
- [ ] `tools/channels/media/` module structure
- [ ] `MediaProcessor` with download, process pipeline
- [ ] Image processing with Claude Vision integration
- [ ] Document text extraction (PDF, basic Office)
- [ ] Code block detection and formatting
- [ ] Updated `UnifiedMessage` with processed attachments
- [ ] Configuration in `args/multimodal.yaml`

**Verification:**
- Send image to Telegram → AI describes it
- Send PDF → AI summarizes content
- AI response with code → proper formatting per channel

### Phase 15b: Audio/Video & Voice

**Scope:** Whisper transcription, TTS generation, video frame extraction

**Deliverables:**
- [ ] `audio_processor.py` with Whisper integration
- [ ] Voice note transcription for Telegram/Discord
- [ ] Optional TTS output generation
- [ ] Video processing (frame extraction, audio track transcription)
- [ ] Duration limits and cost controls

**Verification:**
- Send voice note → AI responds with transcription context
- Long audio → proper truncation and summarization
- Video → frame + audio analysis

### Phase 15c: Platform-Specific Rendering

**Scope:** Rich embeds, Block Kit, platform-native formatting

**Deliverables:**
- [ ] `TelegramRenderer` with MarkdownV2, media groups
- [ ] `DiscordRenderer` with rich embeds, voice messages
- [ ] `SlackRenderer` with Block Kit
- [ ] Content splitting for channel limits
- [ ] Sticker/reaction handling (receive)

**Verification:**
- Code response → syntax highlighted per platform
- Multiple images → album (Telegram) / embeds (Discord)
- Long response → proper splitting without breaking code blocks

### Phase 15d: Advanced & Interactive

**Scope:** Location, contacts, interactive elements, polls

**Deliverables:**
- [ ] Location message handling (geocoding)
- [ ] Contact/vCard parsing
- [ ] Interactive buttons (where supported)
- [ ] Poll creation and handling
- [ ] File storage management and cleanup

**Verification:**
- Share location → AI understands place context
- Create poll → works on supported platforms
- Button interactions → handled correctly

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/media/test_image_processor.py
class TestImageProcessor:
    async def test_download_telegram_photo(self):
        """Test downloading photo from Telegram file_id."""
        ...

    async def test_vision_analysis(self):
        """Test Claude Vision API integration."""
        ...

    async def test_cost_tracking(self):
        """Test processing cost is tracked."""
        ...
```

### Integration Tests

```python
# tests/integration/test_multimodal_flow.py
class TestMultimodalFlow:
    async def test_image_message_e2e(self):
        """Test full flow: image in → analysis → response."""
        ...

    async def test_voice_transcription_e2e(self):
        """Test voice note transcription flow."""
        ...

    async def test_code_block_rendering(self):
        """Test code blocks render correctly per channel."""
        ...
```

### Manual Testing Checklist

- [ ] Telegram: Photo, voice note, document, sticker, video note
- [ ] Discord: Image, file, voice message, embed response
- [ ] Slack: File upload, code block, Block Kit response

---

## Cost Estimation

| Operation | Estimated Cost | Notes |
|-----------|---------------|-------|
| Vision (per image) | $0.01-0.05 | Depends on image size |
| Whisper (per minute) | $0.006 | 60 sec audio = $0.006 |
| TTS (per 1K chars) | $0.015 | OpenAI TTS |
| Document extraction | $0.00 | Local processing |

**Budget Controls:**
- Max $0.20 per message (configurable)
- Max $2.00 per session
- Admin can disable expensive features

---

## Migration Notes

### Existing Code Changes

1. **`tools/channels/models.py`**
   - Add `MediaContent` dataclass
   - Add `ContentBlock` and `BlockType`
   - Extend `Attachment` with processing fields

2. **`tools/channels/sdk_handler.py`**
   - Integrate media processing before AI call
   - Handle rich response formatting after AI call

3. **Channel Adapters**
   - Add `download_attachment()` method
   - Add `upload_file()` method
   - Add `send_rich_message()` method

### Backward Compatibility

- Existing text-only flow unchanged
- Attachments without processing still stored
- New features are opt-in via configuration

---

## References

- [Telegram Bot API - File Upload](https://core.telegram.org/bots/api#sending-files)
- [Discord Embeds Guide](https://discordjs.guide/popular-topics/embeds.html)
- [Slack Block Kit Builder](https://app.slack.com/block-kit-builder)
- [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text)
- [Claude Vision Documentation](https://docs.anthropic.com/claude/docs/vision)

---

*Last Updated: 2026-02-09*
