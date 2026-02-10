"""
Audio Processor for Multi-Modal Messaging (Phase 15b)

Handles audio/voice processing:
- Whisper API transcription for voice notes and audio files
- TTS generation for voice responses
- Duration limits and cost controls
- Format conversion (OGG/Opus, MP3, WAV, M4A)

Usage:
    from tools.channels.audio_processor import AudioProcessor

    processor = AudioProcessor()
    result = await processor.transcribe(audio_bytes, filename, config)
    tts_result = await processor.generate_speech(text, voice, config)
"""

from __future__ import annotations

import io
import logging
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "multimodal.yaml"


def load_config() -> dict[str, Any]:
    """Load multimodal configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


class TranscriptionProvider(Enum):
    """Available transcription providers."""
    OPENAI_WHISPER = "openai"
    LOCAL_WHISPER = "local"


class TTSProvider(Enum):
    """Available TTS providers."""
    OPENAI = "openai"
    ELEVENLABS = "elevenlabs"


@dataclass
class TranscriptionResult:
    """Result from audio transcription."""
    success: bool
    text: str | None = None
    language: str | None = None
    duration_seconds: float | None = None
    cost_usd: float = 0.0
    error: str | None = None
    segments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "success": self.success,
            "text": self.text,
            "language": self.language,
            "duration_seconds": self.duration_seconds,
            "cost_usd": self.cost_usd,
            "error": self.error,
            "segments": self.segments,
        }


@dataclass
class TTSResult:
    """Result from TTS generation."""
    success: bool
    audio_bytes: bytes | None = None
    format: str = "mp3"
    duration_seconds: float | None = None
    cost_usd: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict (without audio bytes)."""
        return {
            "success": self.success,
            "format": self.format,
            "duration_seconds": self.duration_seconds,
            "cost_usd": self.cost_usd,
            "error": self.error,
            "has_audio": self.audio_bytes is not None,
        }


class AudioProcessor:
    """
    Process audio content for transcription and TTS.

    Handles:
    - Whisper API transcription (OpenAI)
    - TTS generation (OpenAI)
    - Format conversion
    - Duration limits
    - Cost tracking
    """

    # Supported audio formats for Whisper
    SUPPORTED_FORMATS = {
        "mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm", "ogg", "oga", "flac"
    }

    # MIME type to extension mapping
    MIME_TO_EXT = {
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
        "audio/flac": "flac",
        "audio/x-m4a": "m4a",
        "audio/opus": "ogg",  # Opus usually in OGG container
    }

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize audio processor.

        Args:
            config: Optional config override (defaults to args/multimodal.yaml)
        """
        self.config = config or load_config()
        self._temp_dir = Path(tempfile.mkdtemp(prefix="dexai_audio_"))

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.ogg",
        mime_type: str = "audio/ogg",
    ) -> TranscriptionResult:
        """
        Transcribe audio to text using Whisper API.

        Args:
            audio_bytes: Raw audio data
            filename: Original filename
            mime_type: MIME type of audio

        Returns:
            TranscriptionResult with text and metadata
        """
        transcription_config = self.config.get("processing", {}).get("transcription", {})

        if not transcription_config.get("enabled", True):
            return TranscriptionResult(
                success=False,
                error="Transcription disabled in configuration",
            )

        # Check file size (Whisper limit: 25MB)
        max_size_mb = 25
        if len(audio_bytes) > max_size_mb * 1024 * 1024:
            return TranscriptionResult(
                success=False,
                error=f"Audio file too large (>{max_size_mb}MB)",
            )

        # Determine provider
        provider = transcription_config.get("provider", "openai")

        if provider == "openai":
            return await self._transcribe_openai(
                audio_bytes, filename, mime_type, transcription_config
            )
        else:
            return TranscriptionResult(
                success=False,
                error=f"Unsupported transcription provider: {provider}",
            )

    async def _transcribe_openai(
        self,
        audio_bytes: bytes,
        filename: str,
        mime_type: str,
        config: dict[str, Any],
    ) -> TranscriptionResult:
        """
        Transcribe audio using OpenAI Whisper API.

        Args:
            audio_bytes: Raw audio data
            filename: Original filename
            mime_type: MIME type
            config: Transcription configuration

        Returns:
            TranscriptionResult
        """
        try:
            import openai
        except ImportError:
            return TranscriptionResult(
                success=False,
                error="OpenAI library not installed. Run: uv pip install openai",
            )

        # Ensure proper file extension
        ext = self._get_extension(filename, mime_type)
        if ext not in self.SUPPORTED_FORMATS:
            ext = "ogg"  # Default to OGG

        # Create a file-like object with proper name
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"audio.{ext}"

        try:
            client = openai.AsyncOpenAI()

            # Get configuration options
            model = config.get("model", "whisper-1")
            language_hint = config.get("language_hint")
            response_format = "verbose_json"  # Get timestamps and segments

            # Check duration limit (requires ffprobe or estimate from file size)
            max_duration = config.get("max_duration_seconds", 300)
            estimated_duration = self._estimate_duration(len(audio_bytes), ext)

            if estimated_duration > max_duration:
                return TranscriptionResult(
                    success=False,
                    error=f"Audio too long (estimated {estimated_duration:.0f}s > {max_duration}s limit)",
                    duration_seconds=estimated_duration,
                )

            # Call Whisper API
            kwargs = {
                "model": model,
                "file": audio_file,
                "response_format": response_format,
            }
            if language_hint:
                kwargs["language"] = language_hint

            response = await client.audio.transcriptions.create(**kwargs)

            # Extract results
            text = response.text
            if not text or not text.strip():
                return TranscriptionResult(
                    success=False,
                    error="No speech detected in audio",
                )

            language = getattr(response, "language", None)
            duration = getattr(response, "duration", estimated_duration)

            # Extract segments if available
            segments = []
            if hasattr(response, "segments"):
                segments = [
                    {
                        "start": seg.get("start", 0),
                        "end": seg.get("end", 0),
                        "text": seg.get("text", ""),
                    }
                    for seg in response.segments
                ]

            # Calculate cost (Whisper: $0.006/minute)
            pricing = config.get("pricing", {})
            cost_per_minute = pricing.get("per_minute_usd", 0.006)
            cost = (duration / 60.0) * cost_per_minute

            return TranscriptionResult(
                success=True,
                text=text,
                language=language,
                duration_seconds=duration,
                cost_usd=cost,
                segments=segments,
            )

        except openai.APIError as e:
            logger.error(f"Whisper API error: {e}")
            return TranscriptionResult(
                success=False,
                error=f"Whisper API error: {str(e)[:100]}",
            )
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return TranscriptionResult(
                success=False,
                error=f"Transcription failed: {str(e)[:100]}",
            )

    async def generate_speech(
        self,
        text: str,
        voice: str | None = None,
        output_format: str = "opus",
    ) -> TTSResult:
        """
        Generate speech audio from text using TTS.

        Args:
            text: Text to convert to speech
            voice: Voice ID (provider-specific)
            output_format: Output format (opus, mp3, aac, flac)

        Returns:
            TTSResult with audio bytes
        """
        tts_config = self.config.get("generation", {}).get("tts", {})

        if not tts_config.get("enabled", False):
            return TTSResult(
                success=False,
                error="TTS generation disabled in configuration",
            )

        # Check text length (OpenAI limit: 4096 chars)
        max_chars = 4096
        if len(text) > max_chars:
            return TTSResult(
                success=False,
                error=f"Text too long ({len(text)} > {max_chars} chars)",
            )

        provider = tts_config.get("provider", "openai")

        if provider == "openai":
            return await self._generate_speech_openai(
                text, voice, output_format, tts_config
            )
        else:
            return TTSResult(
                success=False,
                error=f"Unsupported TTS provider: {provider}",
            )

    async def _generate_speech_openai(
        self,
        text: str,
        voice: str | None,
        output_format: str,
        config: dict[str, Any],
    ) -> TTSResult:
        """
        Generate speech using OpenAI TTS API.

        Args:
            text: Text to convert
            voice: Voice ID
            output_format: Output format
            config: TTS configuration

        Returns:
            TTSResult
        """
        try:
            import openai
        except ImportError:
            return TTSResult(
                success=False,
                error="OpenAI library not installed. Run: uv pip install openai",
            )

        # Get voice (default to "alloy")
        voice = voice or config.get("voice", "alloy")

        # Validate voice
        valid_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
        if voice not in valid_voices:
            voice = "alloy"

        # Validate format (opus is best for voice notes)
        valid_formats = {"mp3", "opus", "aac", "flac", "wav", "pcm"}
        if output_format not in valid_formats:
            output_format = "opus"

        # Get model
        model = config.get("model", "tts-1")
        speed = config.get("speed", 1.0)

        try:
            client = openai.AsyncOpenAI()

            response = await client.audio.speech.create(
                model=model,
                voice=voice,
                input=text,
                response_format=output_format,
                speed=speed,
            )

            # Read audio bytes
            audio_bytes = response.read()

            # Estimate duration (rough: ~150 words per minute)
            word_count = len(text.split())
            estimated_duration = (word_count / 150) * 60 / speed

            # Calculate cost (TTS: $0.015/1K chars for tts-1, $0.030 for tts-1-hd)
            pricing = config.get("pricing", {})
            if model == "tts-1-hd":
                cost_per_1k_chars = pricing.get("hd_per_1k_chars_usd", 0.030)
            else:
                cost_per_1k_chars = pricing.get("per_1k_chars_usd", 0.015)

            cost = (len(text) / 1000) * cost_per_1k_chars

            return TTSResult(
                success=True,
                audio_bytes=audio_bytes,
                format=output_format,
                duration_seconds=estimated_duration,
                cost_usd=cost,
            )

        except openai.APIError as e:
            logger.error(f"TTS API error: {e}")
            return TTSResult(
                success=False,
                error=f"TTS API error: {str(e)[:100]}",
            )
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            return TTSResult(
                success=False,
                error=f"TTS generation failed: {str(e)[:100]}",
            )

    def _get_extension(self, filename: str, mime_type: str) -> str:
        """Get file extension from filename or MIME type."""
        # Try from filename first
        ext = Path(filename).suffix.lower().lstrip(".")
        if ext in self.SUPPORTED_FORMATS:
            return ext

        # Try from MIME type
        return self.MIME_TO_EXT.get(mime_type, "ogg")

    def _estimate_duration(self, file_size: int, format: str) -> float:
        """
        Estimate audio duration from file size.

        Rough estimates based on typical bitrates:
        - OGG/Opus: ~32kbps for voice
        - MP3: ~128kbps
        - WAV: ~1411kbps (uncompressed)
        """
        # Bitrates in bits per second
        bitrates = {
            "ogg": 32_000,
            "opus": 32_000,
            "mp3": 128_000,
            "m4a": 128_000,
            "wav": 1_411_000,
            "flac": 700_000,
            "webm": 64_000,
        }

        bitrate = bitrates.get(format, 64_000)
        duration = (file_size * 8) / bitrate  # Convert bytes to bits

        return duration

    def cleanup(self) -> None:
        """Remove temporary files."""
        import shutil

        try:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass


# =============================================================================
# Module-Level Instance
# =============================================================================

_processor_instance: AudioProcessor | None = None


def get_audio_processor() -> AudioProcessor:
    """Get or create the global AudioProcessor instance."""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = AudioProcessor()
    return _processor_instance


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI for testing audio processor."""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Audio Processor Test")
    parser.add_argument("--config", action="store_true", help="Show config")
    parser.add_argument("--transcribe", metavar="FILE", help="Transcribe audio file")
    parser.add_argument("--tts", metavar="TEXT", help="Generate TTS from text")
    parser.add_argument("--voice", default="alloy", help="TTS voice (default: alloy)")
    parser.add_argument("--output", metavar="FILE", help="Output file for TTS")

    args = parser.parse_args()

    if args.config:
        import json
        config = load_config()
        print(json.dumps(config.get("processing", {}).get("transcription", {}), indent=2))
        print("\nTTS config:")
        print(json.dumps(config.get("generation", {}).get("tts", {}), indent=2))

    elif args.transcribe:
        async def run_transcribe():
            processor = AudioProcessor()
            file_path = Path(args.transcribe)
            if not file_path.exists():
                print(f"File not found: {file_path}")
                return

            audio_bytes = file_path.read_bytes()
            result = await processor.transcribe(
                audio_bytes,
                file_path.name,
                f"audio/{file_path.suffix.lstrip('.')}"
            )

            print(f"Success: {result.success}")
            if result.success:
                print(f"Text: {result.text}")
                print(f"Language: {result.language}")
                print(f"Duration: {result.duration_seconds:.1f}s")
                print(f"Cost: ${result.cost_usd:.4f}")
            else:
                print(f"Error: {result.error}")

        asyncio.run(run_transcribe())

    elif args.tts:
        async def run_tts():
            processor = AudioProcessor()
            result = await processor.generate_speech(
                args.tts,
                voice=args.voice,
                output_format="opus"
            )

            print(f"Success: {result.success}")
            if result.success:
                print(f"Format: {result.format}")
                print(f"Duration: {result.duration_seconds:.1f}s")
                print(f"Cost: ${result.cost_usd:.4f}")

                if args.output:
                    Path(args.output).write_bytes(result.audio_bytes)
                    print(f"Saved to: {args.output}")
            else:
                print(f"Error: {result.error}")

        asyncio.run(run_tts())

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
