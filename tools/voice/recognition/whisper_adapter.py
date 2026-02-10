"""Adapter wrapping Phase 15b AudioProcessor as a BaseTranscriber.

Reuses existing Whisper API infrastructure from tools/channels/audio_processor.py.
No duplicate Whisper code — all transcription routes through AudioProcessor.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from tools.voice.models import TranscriptionResult
from tools.voice.recognition.base import BaseTranscriber

logger = logging.getLogger(__name__)


class WhisperAPIAdapter(BaseTranscriber):
    """Wraps AudioProcessor.transcribe() to conform to BaseTranscriber interface."""

    @property
    def name(self) -> str:
        return "whisper_api"

    @property
    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    @property
    def supports_streaming(self) -> bool:
        return False

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "en",
        **kwargs: Any,
    ) -> TranscriptionResult:
        """Transcribe audio via Whisper API through AudioProcessor."""
        from tools.channels.audio_processor import get_audio_processor

        mime_type = kwargs.get("mime_type", "audio/webm")
        filename = kwargs.get("filename", "recording.webm")

        processor = get_audio_processor()
        result = await processor.transcribe(audio_data, filename, mime_type)

        if not result.success:
            logger.warning("Whisper transcription failed: %s", result.error)
            return TranscriptionResult(
                transcript="",
                confidence=0.0,
                source="whisper_api",
                language=language,
                is_final=True,
            )

        return TranscriptionResult(
            transcript=result.text or "",
            confidence=0.95,  # Whisper is consistently high-accuracy
            source="whisper_api",
            language=result.language or language,
            duration_ms=int((result.duration_seconds or 0) * 1000),
            is_final=True,
            alternatives=[],
        )


# Module-level singleton
_adapter: WhisperAPIAdapter | None = None


def get_whisper_adapter() -> WhisperAPIAdapter:
    """Get or create the global WhisperAPIAdapter instance."""
    global _adapter
    if _adapter is None:
        _adapter = WhisperAPIAdapter()
    return _adapter
