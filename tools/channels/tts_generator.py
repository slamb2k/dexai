"""
TTS Generator for Multi-Modal Messaging (Phase 15b)

Generates voice responses using Text-to-Speech:
- OpenAI TTS API integration
- Voice selection
- Output format handling (Opus for voice notes)
- Cost tracking

Usage:
    from tools.channels.tts_generator import TTSGenerator

    generator = TTSGenerator()
    result = await generator.generate(text, voice="alloy")
"""

from __future__ import annotations

import logging

# Ensure project root is in path
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.channels.audio_processor import TTSResult


logger = logging.getLogger(__name__)

# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "multimodal.yaml"


def load_config() -> dict[str, Any]:
    """Load multimodal configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


class TTSGenerator:
    """
    Generate voice responses using TTS APIs.

    Handles:
    - Text-to-speech generation
    - Voice selection
    - Format optimization for channels
    - Cost tracking
    """

    # Available voices (OpenAI TTS)
    VOICES = {
        "alloy": "Neutral and balanced",
        "echo": "Warm and confident",
        "fable": "Expressive and animated",
        "onyx": "Deep and authoritative",
        "nova": "Friendly and upbeat",
        "shimmer": "Clear and pleasant",
    }

    # Output formats
    FORMATS = {
        "opus": "Best for voice notes (Telegram, Discord)",
        "mp3": "Universal compatibility",
        "aac": "Good quality, smaller size",
        "flac": "Lossless (large files)",
    }

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize TTS generator.

        Args:
            config: Optional config override (defaults to args/multimodal.yaml)
        """
        self.config = config or load_config()

    def is_enabled(self) -> bool:
        """Check if TTS generation is enabled."""
        return self.config.get("generation", {}).get("tts", {}).get("enabled", False)

    async def generate(
        self,
        text: str,
        voice: str | None = None,
        format: str | None = None,
        speed: float | None = None,
    ) -> TTSResult:
        """
        Generate speech audio from text.

        Args:
            text: Text to convert to speech
            voice: Voice ID (alloy, echo, fable, onyx, nova, shimmer)
            format: Output format (opus, mp3, aac, flac)
            speed: Speech speed (0.25 to 4.0)

        Returns:
            TTSResult with audio bytes and metadata
        """
        tts_config = self.config.get("generation", {}).get("tts", {})

        if not tts_config.get("enabled", False):
            return TTSResult(
                success=False,
                error="TTS generation is disabled. Enable in args/multimodal.yaml",
            )

        # Get defaults from config
        voice = voice or tts_config.get("voice", "alloy")
        format = format or tts_config.get("output_format", "opus")
        speed = speed or tts_config.get("speed", 1.0)

        # Validate voice
        if voice not in self.VOICES:
            voice = "alloy"

        # Validate format
        if format not in self.FORMATS:
            format = "opus"

        # Validate speed
        speed = max(0.25, min(4.0, speed))

        # Check text length
        max_chars = tts_config.get("max_chars", 4096)
        if len(text) > max_chars:
            return TTSResult(
                success=False,
                error=f"Text too long ({len(text)} > {max_chars} chars). Consider summarizing.",
            )

        # Use AudioProcessor for actual TTS
        from tools.channels.audio_processor import get_audio_processor

        processor = get_audio_processor()
        return await processor.generate_speech(
            text,
            voice=voice,
            output_format=format,
        )

    async def generate_for_channel(
        self,
        text: str,
        channel: str,
        voice: str | None = None,
    ) -> TTSResult:
        """
        Generate speech optimized for a specific channel.

        Args:
            text: Text to convert
            channel: Target channel (telegram, discord, slack)
            voice: Optional voice override

        Returns:
            TTSResult with channel-optimized audio
        """
        # Channel-specific format preferences
        channel_formats = {
            "telegram": "opus",   # Native voice note format
            "discord": "opus",    # Supported for voice messages
            "slack": "mp3",       # General compatibility
            "web": "mp3",         # Browser compatibility
        }

        format = channel_formats.get(channel, "mp3")
        return await self.generate(text, voice=voice, format=format)

    def get_available_voices(self) -> dict[str, str]:
        """Get available voices with descriptions."""
        return self.VOICES.copy()

    def estimate_cost(self, text: str, hd: bool = False) -> float:
        """
        Estimate TTS cost for given text.

        Args:
            text: Text to generate
            hd: Whether using HD model

        Returns:
            Estimated cost in USD
        """
        tts_config = self.config.get("generation", {}).get("tts", {})
        pricing = tts_config.get("pricing", {})

        if hd:
            rate = pricing.get("hd_per_1k_chars_usd", 0.030)
        else:
            rate = pricing.get("per_1k_chars_usd", 0.015)

        return (len(text) / 1000) * rate


# =============================================================================
# Module-Level Instance
# =============================================================================

_generator_instance: TTSGenerator | None = None


def get_tts_generator() -> TTSGenerator:
    """Get or create the global TTSGenerator instance."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = TTSGenerator()
    return _generator_instance


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI for testing TTS generator."""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="TTS Generator Test")
    parser.add_argument("--list-voices", action="store_true", help="List available voices")
    parser.add_argument("--generate", metavar="TEXT", help="Generate speech from text")
    parser.add_argument("--voice", default="alloy", help="Voice to use")
    parser.add_argument("--channel", default="telegram", help="Target channel")
    parser.add_argument("--output", metavar="FILE", help="Output file")
    parser.add_argument("--estimate", metavar="TEXT", help="Estimate cost for text")

    args = parser.parse_args()

    if args.list_voices:
        generator = TTSGenerator()
        print("Available voices:")
        for voice, desc in generator.get_available_voices().items():
            print(f"  {voice}: {desc}")

    elif args.generate:
        async def run_generate():
            generator = TTSGenerator()

            if not generator.is_enabled():
                print("TTS is disabled. Enable in args/multimodal.yaml")
                return

            result = await generator.generate_for_channel(
                args.generate,
                args.channel,
                voice=args.voice,
            )

            print(f"Success: {result.success}")
            if result.success:
                print(f"Format: {result.format}")
                print(f"Duration: {result.duration_seconds:.1f}s")
                print(f"Cost: ${result.cost_usd:.4f}")

                if args.output and result.audio_bytes:
                    Path(args.output).write_bytes(result.audio_bytes)
                    print(f"Saved to: {args.output}")
            else:
                print(f"Error: {result.error}")

        asyncio.run(run_generate())

    elif args.estimate:
        generator = TTSGenerator()
        cost = generator.estimate_cost(args.estimate)
        print(f"Text length: {len(args.estimate)} chars")
        print(f"Estimated cost: ${cost:.4f}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
