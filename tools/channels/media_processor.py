"""
Media Processor for Multi-Modal Messaging (Phase 15a/15b)

Handles processing of images, documents, audio, video, and other attachments:
- Image analysis via Claude Vision API
- Document text extraction (PDF, DOCX)
- Audio/voice transcription via Whisper API (Phase 15b)
- Video frame extraction and audio track transcription (Phase 15b)
- Cost tracking

Usage:
    from tools.channels.media_processor import MediaProcessor

    processor = MediaProcessor()
    media = await processor.process_attachment(attachment, channel, adapter)
"""

from __future__ import annotations

import base64
import io
import logging

# Ensure project root is in path
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml


PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.channels.models import Attachment, MediaContent


if TYPE_CHECKING:
    from tools.channels.router import ChannelAdapter

logger = logging.getLogger(__name__)

# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "multimodal.yaml"


def load_config() -> dict[str, Any]:
    """Load multimodal configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


class MediaProcessor:
    """
    Process media attachments for AI context.

    Handles:
    - Image analysis via Claude Vision
    - Document text extraction
    - Audio/voice transcription via Whisper (Phase 15b)
    - Video processing with frame extraction (Phase 15b)
    - Cost tracking and budget enforcement
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize media processor.

        Args:
            config: Optional config override (defaults to args/multimodal.yaml)
        """
        self.config = config or load_config()
        self._temp_dir = Path(tempfile.mkdtemp(prefix="dexai_media_"))

    async def process_attachment(
        self,
        attachment: Attachment,
        channel: str,
        adapter: ChannelAdapter,
    ) -> MediaContent:
        """
        Process a single attachment.

        Args:
            attachment: Attachment to process
            channel: Source channel name
            adapter: Channel adapter for downloading

        Returns:
            MediaContent with processing results
        """
        processing_config = self.config.get("processing", {})

        if not processing_config.get("enabled", True):
            return MediaContent(attachment=attachment, processed=False)

        # Check file size limit
        max_size_mb = processing_config.get("max_file_size_mb", 50)
        if attachment.size_bytes > max_size_mb * 1024 * 1024:
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=f"File too large (>{max_size_mb}MB)",
            )

        try:
            # Route to appropriate processor
            if attachment.type == "image":
                return await self._process_image(attachment, channel, adapter)
            elif attachment.type == "document":
                return await self._process_document(attachment, channel, adapter)
            elif attachment.type == "audio":
                return await self._process_audio(attachment, channel, adapter)
            elif attachment.type == "video":
                return await self._process_video(attachment, channel, adapter)
            else:
                # Passthrough for unsupported types
                return MediaContent(
                    attachment=attachment,
                    processed=False,
                    processing_error=f"Unsupported type: {attachment.type}",
                )

        except Exception as e:
            logger.error(f"Media processing failed: {e}")
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=str(e)[:200],
            )

    async def process_attachments_batch(
        self,
        attachments: list[Attachment],
        channel: str,
        adapter: ChannelAdapter,
    ) -> list[MediaContent]:
        """
        Process multiple attachments with ADHD-friendly limits.

        Args:
            attachments: List of attachments
            channel: Source channel name
            adapter: Channel adapter

        Returns:
            List of processed MediaContent
        """
        if not attachments:
            return []

        # ADHD: Limit to max 3 attachments
        adhd_config = self.config.get("adhd", {})
        max_attachments = adhd_config.get("max_attachments", 3)

        if len(attachments) > max_attachments:
            logger.info(
                f"ADHD limit: Processing only {max_attachments} of {len(attachments)} attachments"
            )
            attachments = attachments[:max_attachments]

        # Prioritize images over documents
        sorted_attachments = sorted(
            attachments,
            key=lambda a: 0 if a.type == "image" else 1,
        )

        # Process sequentially (not parallel - ADHD cognitive load)
        results = []
        total_cost = 0.0
        max_cost = self.config.get("processing", {}).get("max_processing_cost_usd", 0.20)

        for attachment in sorted_attachments:
            # Check budget
            if total_cost >= max_cost:
                logger.warning(f"Processing budget exceeded: ${total_cost:.3f}")
                results.append(MediaContent(
                    attachment=attachment,
                    processed=False,
                    processing_error="Processing budget exceeded",
                ))
                continue

            media = await self.process_attachment(attachment, channel, adapter)
            total_cost += media.processing_cost_usd
            results.append(media)

        return results

    # =========================================================================
    # Image Processing
    # =========================================================================

    async def _process_image(
        self,
        attachment: Attachment,
        channel: str,
        adapter: ChannelAdapter,
    ) -> MediaContent:
        """
        Process image with Claude Vision API.

        Args:
            attachment: Image attachment
            channel: Source channel
            adapter: Channel adapter for download

        Returns:
            MediaContent with vision description
        """
        vision_config = self.config.get("processing", {}).get("vision", {})

        if not vision_config.get("enabled", True):
            return MediaContent(attachment=attachment, processed=False)

        # Download image
        try:
            image_bytes = await adapter.download_attachment(attachment)
            if not image_bytes:
                return MediaContent(
                    attachment=attachment,
                    processed=False,
                    processing_error="Downloaded file is empty",
                )
        except Exception as e:
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=f"Download failed: {str(e)[:100]}",
            )

        # Prepare image for Vision API
        prepared_image = await self._prepare_image_for_vision(image_bytes)

        if not prepared_image:
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error="Failed to prepare image",
            )

        # Call Vision API
        try:
            description, cost = await self._call_vision_api(prepared_image)

            return MediaContent(
                attachment=attachment,
                processed=True,
                vision_description=description,
                processing_cost_usd=cost,
            )

        except Exception as e:
            logger.error(f"Vision API error: {e}")
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=f"Vision API error: {str(e)[:100]}",
            )

    async def _prepare_image_for_vision(
        self, image_bytes: bytes
    ) -> dict[str, Any] | None:
        """
        Prepare image for Claude Vision API.

        Resizes large images and converts to base64.

        Args:
            image_bytes: Raw image data

        Returns:
            Dict in Claude Vision format or None on error
        """
        try:
            from PIL import Image

            # Open and check image
            img = Image.open(io.BytesIO(image_bytes))

            # Resize if too large (Claude recommendation: 1568px max)
            max_size = 1568
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.LANCZOS)

            # Convert to JPEG for consistency
            output = io.BytesIO()
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(output, format="JPEG", quality=85)
            image_bytes = output.getvalue()

            # Check size (Claude limit: 5MB)
            if len(image_bytes) > 5 * 1024 * 1024:
                # Reduce quality
                output = io.BytesIO()
                img.save(output, format="JPEG", quality=60)
                image_bytes = output.getvalue()

            # Encode to base64
            b64_data = base64.standard_b64encode(image_bytes).decode("utf-8")

            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": b64_data,
                },
            }

        except ImportError:
            logger.error("Pillow not installed. Run: uv pip install pillow")
            return None
        except Exception as e:
            logger.error(f"Image preparation failed: {e}")
            return None

    async def _call_vision_api(
        self, image_data: dict[str, Any]
    ) -> tuple[str, float]:
        """
        Call Claude Vision API to describe image.

        Args:
            image_data: Prepared image dict

        Returns:
            Tuple of (description, cost_usd)
        """
        import anthropic

        client = anthropic.AsyncAnthropic()

        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        image_data,
                        {
                            "type": "text",
                            "text": "Describe this image concisely for context. Focus on key details, text content, or notable elements. Keep it brief (2-3 sentences max).",
                        },
                    ],
                }
            ],
        )

        description = response.content[0].text

        # Calculate cost from config (defaults: Sonnet vision pricing)
        pricing = self.config.get("processing", {}).get("vision", {}).get("pricing", {})
        input_per_mtok = pricing.get("input_per_mtok", 3.0)
        output_per_mtok = pricing.get("output_per_mtok", 15.0)

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = (input_tokens * input_per_mtok / 1_000_000) + (output_tokens * output_per_mtok / 1_000_000)

        return description, cost

    # =========================================================================
    # Document Processing
    # =========================================================================

    async def _process_document(
        self,
        attachment: Attachment,
        channel: str,
        adapter: ChannelAdapter,
    ) -> MediaContent:
        """
        Extract text from document.

        Args:
            attachment: Document attachment
            channel: Source channel
            adapter: Channel adapter for download

        Returns:
            MediaContent with extracted text
        """
        doc_config = self.config.get("processing", {}).get("documents", {})

        if not doc_config.get("enabled", True):
            return MediaContent(attachment=attachment, processed=False)

        # Check supported formats
        supported = doc_config.get("supported_formats", ["pdf", "docx", "txt", "md"])
        ext = Path(attachment.filename).suffix.lower().lstrip(".")

        if ext not in supported:
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=f"Unsupported format: {ext}",
            )

        # Download document
        try:
            doc_bytes = await adapter.download_attachment(attachment)
            if not doc_bytes:
                return MediaContent(
                    attachment=attachment,
                    processed=False,
                    processing_error="Downloaded file is empty",
                )
        except Exception as e:
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=f"Download failed: {str(e)[:100]}",
            )

        # Extract text
        try:
            max_pages = doc_config.get("max_pages", 20)
            max_chars = doc_config.get("max_chars_per_doc", 10000)

            if ext == "pdf":
                text, page_count = await self._extract_pdf(doc_bytes, max_pages)
            elif ext == "docx":
                text, page_count = await self._extract_docx(doc_bytes)
            elif ext in ("txt", "md"):
                text = doc_bytes.decode("utf-8", errors="ignore")
                page_count = 1
            else:
                text = f"[Document: {attachment.filename}]"
                page_count = None

            # Truncate to max chars
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n[Truncated - showing first {max_chars} chars]"

            return MediaContent(
                attachment=attachment,
                processed=True,
                extracted_text=text,
                page_count=page_count,
                processing_cost_usd=0.0,  # Local processing
            )

        except Exception as e:
            logger.error(f"Document extraction failed: {e}")
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=f"Extraction failed: {str(e)[:100]}",
            )

    async def _extract_pdf(
        self, pdf_bytes: bytes, max_pages: int
    ) -> tuple[str, int]:
        """
        Extract text from PDF using PyPDF2.

        Args:
            pdf_bytes: PDF file content
            max_pages: Maximum pages to extract

        Returns:
            Tuple of (text, page_count)
        """
        try:
            from PyPDF2 import PdfReader

            pdf_file = io.BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)

            page_count = len(reader.pages)
            pages_to_read = min(page_count, max_pages)

            text_parts = []
            for i in range(pages_to_read):
                page_text = reader.pages[i].extract_text()
                if page_text:
                    text_parts.append(f"--- Page {i + 1} ---\n{page_text}")

            text = "\n\n".join(text_parts)

            if pages_to_read < page_count:
                text += f"\n\n[Showing {pages_to_read} of {page_count} pages]"

            return text, page_count

        except ImportError:
            raise ImportError("PyPDF2 not installed. Run: uv pip install pypdf2")

    async def _extract_docx(self, docx_bytes: bytes) -> tuple[str, int]:
        """
        Extract text from Word document using python-docx.

        Args:
            docx_bytes: DOCX file content

        Returns:
            Tuple of (text, page_count estimate)
        """
        try:
            from docx import Document

            doc_file = io.BytesIO(docx_bytes)
            doc = Document(doc_file)

            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n\n".join(paragraphs)

            # Estimate page count (rough: ~3000 chars per page)
            page_count = max(1, len(text) // 3000)

            return text, page_count

        except ImportError:
            raise ImportError("python-docx not installed. Run: uv pip install python-docx")

    # =========================================================================
    # Audio Processing (Phase 15b)
    # =========================================================================

    async def _process_audio(
        self,
        attachment: Attachment,
        channel: str,
        adapter: ChannelAdapter,
    ) -> MediaContent:
        """
        Process audio/voice with Whisper transcription.

        Args:
            attachment: Audio attachment
            channel: Source channel
            adapter: Channel adapter for download

        Returns:
            MediaContent with transcription
        """
        transcription_config = self.config.get("processing", {}).get("transcription", {})

        if not transcription_config.get("enabled", True):
            return MediaContent(attachment=attachment, processed=False)

        # Download audio
        try:
            audio_bytes = await adapter.download_attachment(attachment)
            if not audio_bytes:
                return MediaContent(
                    attachment=attachment,
                    processed=False,
                    processing_error="Downloaded file is empty",
                )
        except Exception as e:
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=f"Download failed: {str(e)[:100]}",
            )

        # Use AudioProcessor for transcription
        try:
            from tools.channels.audio_processor import get_audio_processor

            audio_processor = get_audio_processor()
            result = await audio_processor.transcribe(
                audio_bytes,
                attachment.filename,
                attachment.mime_type,
            )

            if result.success:
                return MediaContent(
                    attachment=attachment,
                    processed=True,
                    transcription=result.text,
                    duration_seconds=result.duration_seconds,
                    processing_cost_usd=result.cost_usd,
                    metadata={
                        "language": result.language,
                        "segments": result.segments,
                    },
                )
            else:
                return MediaContent(
                    attachment=attachment,
                    processed=False,
                    processing_error=result.error,
                )

        except Exception as e:
            logger.error(f"Audio transcription error: {e}")
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=f"Transcription error: {str(e)[:100]}",
            )

    # =========================================================================
    # Video Processing (Phase 15b)
    # =========================================================================

    async def _process_video(
        self,
        attachment: Attachment,
        channel: str,
        adapter: ChannelAdapter,
    ) -> MediaContent:
        """
        Process video with frame extraction and audio transcription.

        Args:
            attachment: Video attachment
            channel: Source channel
            adapter: Channel adapter for download

        Returns:
            MediaContent with transcription and frame descriptions
        """
        video_config = self.config.get("processing", {}).get("video", {})

        if not video_config.get("enabled", True):
            return MediaContent(attachment=attachment, processed=False)

        # Download video
        try:
            video_bytes = await adapter.download_attachment(attachment)
            if not video_bytes:
                return MediaContent(
                    attachment=attachment,
                    processed=False,
                    processing_error="Downloaded file is empty",
                )
        except Exception as e:
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=f"Download failed: {str(e)[:100]}",
            )

        # Use VideoProcessor
        try:
            from tools.channels.video_processor import get_video_processor

            video_processor = get_video_processor()
            result = await video_processor.process_video(
                video_bytes,
                attachment.filename,
                attachment.mime_type,
            )

            if result.success:
                # Build description from transcription and frame descriptions
                description_parts = []

                if result.transcription:
                    description_parts.append(f"Audio transcription: {result.transcription}")

                if result.frame_descriptions:
                    description_parts.append("Key frames:")
                    for desc in result.frame_descriptions:
                        description_parts.append(f"  {desc}")

                combined_description = "\n".join(description_parts) if description_parts else None

                return MediaContent(
                    attachment=attachment,
                    processed=True,
                    transcription=result.transcription,
                    vision_description=combined_description,
                    duration_seconds=result.duration_seconds,
                    processing_cost_usd=result.total_cost_usd,
                    metadata={
                        "language": result.audio_language,
                        "width": result.width,
                        "height": result.height,
                        "fps": result.fps,
                        "frame_descriptions": result.frame_descriptions,
                        "has_thumbnail": result.thumbnail_bytes is not None,
                    },
                )
            else:
                return MediaContent(
                    attachment=attachment,
                    processed=False,
                    processing_error=result.error,
                )

        except Exception as e:
            logger.error(f"Video processing error: {e}")
            return MediaContent(
                attachment=attachment,
                processed=False,
                processing_error=f"Video error: {str(e)[:100]}",
            )

    # =========================================================================
    # Cleanup
    # =========================================================================

    def cleanup(self) -> None:
        """Remove temporary files."""
        import shutil

        try:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass


# =============================================================================
# Content Formatting Functions
# =============================================================================


def parse_response_blocks(response_text: str) -> list[dict[str, Any]]:
    """
    Parse AI response into content blocks.

    Detects code blocks (```language) and separates them from text.

    Args:
        response_text: Raw AI response

    Returns:
        List of block dicts with 'type', 'content', and 'metadata'
    """
    import re

    blocks = []
    # Pattern for fenced code blocks - handles with or without newline after fence
    pattern = r"```(\w*)\s*(.*?)```"

    last_end = 0
    for match in re.finditer(pattern, response_text, re.DOTALL):
        # Text before code block
        before_text = response_text[last_end:match.start()].strip()
        if before_text:
            blocks.append({
                "type": "text",
                "content": before_text,
                "metadata": {},
            })

        # Code block
        language = match.group(1) or "text"
        code = match.group(2)
        blocks.append({
            "type": "code",
            "content": code,
            "metadata": {"language": language},
        })

        last_end = match.end()

    # Remaining text after last code block
    remaining = response_text[last_end:].strip()
    if remaining:
        blocks.append({
            "type": "text",
            "content": remaining,
            "metadata": {},
        })

    # If no blocks found, treat entire response as text
    if not blocks:
        blocks.append({
            "type": "text",
            "content": response_text,
            "metadata": {},
        })

    return blocks


def format_blocks_for_channel(
    blocks: list[dict[str, Any]],
    channel: str,
) -> str:
    """
    Format content blocks for a specific channel.

    Applies channel-specific formatting:
    - Telegram: HTML <pre><code> tags
    - Discord: Markdown code fences
    - Slack: Triple backticks

    Args:
        blocks: Content blocks from parse_response_blocks
        channel: Target channel name

    Returns:
        Formatted response string
    """
    formatted_parts = []

    for block in blocks:
        if block["type"] == "code":
            language = block["metadata"].get("language", "")
            code = block["content"]

            if channel == "telegram":
                # Use HTML for Telegram
                escaped_code = (
                    code.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                formatted_parts.append(
                    f'<pre><code class="language-{language}">{escaped_code}</code></pre>'
                )

            elif channel == "discord":
                # Discord supports markdown code fences
                formatted_parts.append(f"```{language}\n{code}\n```")

            elif channel == "slack":
                # Slack code blocks (no language hint)
                formatted_parts.append(f"```{code}```")

            else:
                # Default markdown
                formatted_parts.append(f"```{language}\n{code}\n```")

        else:
            # Regular text
            formatted_parts.append(block["content"])

    return "\n\n".join(formatted_parts)


def split_for_channel(
    content: str,
    channel: str,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """
    Split content for channel message limits.

    Attempts to split at natural boundaries without breaking code blocks.

    Args:
        content: Formatted content string
        channel: Target channel name
        config: Optional config override

    Returns:
        List of message chunks
    """
    config = config or load_config()
    limits = config.get("formatting", {}).get("channel_limits", {})

    limit = limits.get(channel, 2000)

    if len(content) <= limit:
        return [content]

    chunks = []
    remaining = content

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        # Find a good split point
        split_point = limit

        # Try to split at paragraph boundary
        paragraph_break = remaining[:limit].rfind("\n\n")
        if paragraph_break > limit // 2:
            split_point = paragraph_break

        # Try to split at sentence boundary
        elif "." in remaining[:limit]:
            sentence_end = remaining[:limit].rfind(". ")
            if sentence_end > limit // 2:
                split_point = sentence_end + 1

        # Try to split at space
        elif " " in remaining[:limit]:
            space = remaining[:limit].rfind(" ")
            if space > limit // 2:
                split_point = space

        chunks.append(remaining[:split_point].strip())
        remaining = remaining[split_point:].strip()

    return chunks


# =============================================================================
# Module-Level Instance
# =============================================================================

_processor_instance: MediaProcessor | None = None


def get_media_processor() -> MediaProcessor:
    """Get or create the global MediaProcessor instance."""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = MediaProcessor()
    return _processor_instance


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI for testing media processor."""
    import argparse

    parser = argparse.ArgumentParser(description="Media Processor Test")
    parser.add_argument("--config", action="store_true", help="Show config")
    parser.add_argument("--test-parse", metavar="TEXT", help="Test response parsing")

    args = parser.parse_args()

    if args.config:
        import json
        config = load_config()
        print(json.dumps(config, indent=2))

    elif args.test_parse:
        blocks = parse_response_blocks(args.test_parse)
        import json
        print(json.dumps(blocks, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
