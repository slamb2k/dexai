"""Abstract base class for speech transcription providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tools.voice.models import TranscriptionResult


class BaseTranscriber(ABC):
    """Abstract base for all transcription providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'web_speech', 'whisper_api')."""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether this provider is currently usable."""

    @property
    def supports_streaming(self) -> bool:
        """Whether this provider supports streaming transcription."""
        return False

    @abstractmethod
    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "en",
        **kwargs,
    ) -> TranscriptionResult:
        """Transcribe audio data to text."""

    async def transcribe_stream(
        self,
        audio_stream,
        language: str = "en",
        **kwargs,
    ):
        """Stream transcription results. Override if supported."""
        raise NotImplementedError(
            f"{self.name} does not support streaming transcription"
        )
